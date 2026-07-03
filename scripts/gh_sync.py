"""
GitHub Actions: directly calls Shopee API and updates products.json on PA.
Refreshes access token first, since it expires every 4 hours.
IP whitelist is disabled on Shopee, so any IP can connect.
"""
import sys, os, json, requests, hashlib, hmac, time
from datetime import datetime, timezone, timedelta

PARTNER_ID = int(os.environ["SHOPEE_PARTNER_ID"])
PARTNER_KEY = os.environ["SHOPEE_PARTNER_KEY"]
SHOP_ID = int(os.environ["SHOPEE_SHOP_ID"])
PA_API_TOKEN = os.environ["PA_API_TOKEN"]
PA_USER = "brisunto2026"
REFRESH_TOKEN = os.environ["SHOPEE_REFRESH_TOKEN"]
MERCHANT_ID = int(os.environ.get("SHOPEE_MERCHANT_ID", 3969241))
BASE_URL = "https://openplatform.shopee.cn/api/v2"

ACCESS_TOKEN = None

def generate_sign(url_path, ts, access_token="", shop_id=""):
    parts = [str(PARTNER_ID), url_path, str(ts)]
    if access_token: parts.append(access_token)
    if shop_id: parts.append(str(shop_id))
    return hmac.new(PARTNER_KEY.encode(), "".join(parts).encode(), hashlib.sha256).hexdigest()

def call_api(endpoint, body, method="GET"):
    global ACCESS_TOKEN
    url_path = f"/api/v2/{endpoint}"
    ts = int(time.time())
    sign = generate_sign(url_path, ts, ACCESS_TOKEN, str(SHOP_ID))
    params = {"partner_id": PARTNER_ID, "timestamp": ts, "access_token": ACCESS_TOKEN, "shop_id": SHOP_ID, "sign": sign}
    if method == "POST":
        r = requests.post(f"{BASE_URL}/{endpoint}", params=params, json=body, timeout=30)
    else:
        params.update(body)
        r = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=30)
    return r.json()

def refresh_access_token():
    global ACCESS_TOKEN
    url_path = "/api/v2/auth/access_token/get"
    ts = int(time.time())
    sign = generate_sign(url_path, ts)
    params = {"partner_id": PARTNER_ID, "timestamp": ts, "sign": sign}
    body = {"refresh_token": REFRESH_TOKEN, "partner_id": PARTNER_ID, "shop_id": SHOP_ID}
    r = requests.post(f"{BASE_URL}/auth/access_token/get", params=params, json=body, timeout=30)
    data = r.json()
    if "access_token" not in data:
        print(f"Token refresh failed: {data} (status {r.status_code})")
        return False
    ACCESS_TOKEN = data["access_token"]
    print(f"Access token refreshed (expires in {data.get('expire_in', '?')}s)")
    return True

def pa_upload(path, content):
    r = requests.post(f"https://www.pythonanywhere.com/api/v0/user/{PA_USER}/files/path/{path}",
        files={"content": ("f", content.encode("utf-8"), "application/octet-stream")},
        headers={"Authorization": f"Token {PA_API_TOKEN}"}, timeout=15)
    return r.ok

def main():
    if not refresh_access_token():
        return False

    today = datetime.now()
    ts_from = int(datetime(today.year, today.month, today.day).timestamp())
    ts_to = int((today + timedelta(days=1)).timestamp())

    print(f"Fetching completed orders from {today.strftime('%Y-%m-%d')}...")
    resp = call_api("order/get_order_list", {
        "order_status": "COMPLETED", "time_range_field": "create_time",
        "time_from": ts_from, "time_to": ts_to, "page_size": 100, "cursor": ""
    })
    if resp.get("error"):
        print(f"API error: {resp['error']} - {resp.get('message', '')}")
        return False

    orders = resp.get("response", {}).get("order_list", [])
    print(f"Got {len(orders)} completed orders")
    if not orders:
        return True

    sku_qty = {}
    for order in orders:
        sn = order.get("order_sn")
        detail = call_api("order/get_order_detail", {"order_sn_list": [sn]}, "GET")
        if detail.get("error"):
            print(f"  Order {sn} detail failed: {detail.get('error')}")
            continue
        items = detail.get("response", {}).get("order_list", [])
        for o in items:
            for item in o.get("item_list", []):
                sku = item.get("item_sku", "").strip()
                qty = item.get("model_quantity_purchased", 1)
                if sku:
                    sku_qty[sku] = sku_qty.get(sku, 0) + qty
                    print(f"  {sn}: {sku} x{qty}")

    if not sku_qty:
        print("No SKUs to sync")
        return True

    r = requests.get(f"https://www.pythonanywhere.com/api/v0/user/{PA_USER}/files/path/home/{PA_USER}/inventory/static/products.json",
        headers={"Authorization": f"Token {PA_API_TOKEN}"})
    if r.status_code != 200:
        print(f"Failed to download products.json: {r.status_code}")
        return False

    products = r.json()
    updated = 0
    for p in products:
        item_sku = p.get("item", "").strip()
        if item_sku in sku_qty:
            sold = sku_qty[item_sku]
            old_stock = p.get("stock", 0)
            try:
                new_stock = int(old_stock) - sold
            except (ValueError, TypeError):
                new_stock = 0
            p["stock"] = new_stock
            updated += 1
            print(f"  {item_sku}: {old_stock} -> {new_stock} (-{sold})")

    if updated:
        pa_upload("inventory/static/products.json", json.dumps(products, ensure_ascii=False, indent=2))
        print(f"Uploaded products.json ({updated} SKUs updated)")
    else:
        print("No products to update")

    ym = f"{today.year}-{today.month:02d}"
    report = f"sales_{ym}.csv"
    r2 = requests.get(f"https://www.pythonanywhere.com/api/v0/user/{PA_USER}/files/path/home/{PA_USER}/{report}",
        headers={"Authorization": f"Token {PA_API_TOKEN}"})
    existing = {}
    if r2.status_code == 200:
        for line in r2.text.strip().split("\n")[1:]:
            parts = line.split(",")
            if len(parts) >= 4:
                existing[parts[0]] = {"qty": int(parts[2]), "orders": int(parts[3]), "name": parts[1]}

    for sku, qty in sku_qty.items():
        if sku in existing:
            existing[sku]["qty"] += qty
            existing[sku]["orders"] += 1
        else:
            existing[sku] = {"qty": qty, "orders": 1, "name": sku}

    csv_lines = ["SKU,产品名称,销量,订单数"]
    for sku in sorted(existing):
        d = existing[sku]
        csv_lines.append(f"{sku},{d['name']},{d['qty']},{d['orders']}")

    if pa_upload(report, "\n".join(csv_lines)):
        print(f"Monthly report updated: {report}")

    print("Sync completed!")
    return True

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
