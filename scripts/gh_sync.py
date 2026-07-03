"""
GitHub Actions: deducts stock for READY_TO_SHIP (paid) Shopee orders.
Tracks synced order IDs on PA to prevent double-deduction.
Looks back 7 days to catch orders paid after creation.
"""
import sys, os, json, requests, hashlib, hmac, time
from datetime import datetime, timezone, timedelta

PARTNER_ID = int(os.environ["SHOPEE_PARTNER_ID"])
PARTNER_KEY = os.environ["SHOPEE_PARTNER_KEY"]
SHOP_ID = int(os.environ["SHOPEE_SHOP_ID"])
PA_API_TOKEN = os.environ["PA_API_TOKEN"]
PA_USER = "brisunto2026"
REFRESH_TOKEN = os.environ["SHOPEE_REFRESH_TOKEN"]
BASE_URL = "https://openplatform.shopee.cn/api/v2"
LOOKBACK_DAYS = 7

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

def pa_download(path):
    r = requests.get(f"https://www.pythonanywhere.com/api/v0/user/{PA_USER}/files/path/home/{PA_USER}/{path}",
        headers={"Authorization": f"Token {PA_API_TOKEN}"}, timeout=15)
    if r.status_code == 200:
        return r.text
    return None

def pa_upload(path, content):
    r = requests.post(f"https://www.pythonanywhere.com/api/v0/user/{PA_USER}/files/path/{path}",
        files={"content": ("f", content.encode("utf-8"), "application/octet-stream")},
        headers={"Authorization": f"Token {PA_API_TOKEN}"}, timeout=15)
    return r.ok

def main():
    if not refresh_access_token():
        return False

    today = datetime.now()
    ts_to = int(today.timestamp())
    ts_from = int((today - timedelta(days=LOOKBACK_DAYS)).timestamp())

    # Load already-synced order IDs from PA
    synced = set()
    raw = pa_download("inventory/synced_orders.json")
    if raw:
        try:
            synced = set(json.loads(raw))
            print(f"Loaded {len(synced)} previously synced orders")
        except:
            pass
    if not synced:
        print("No previous sync history, will process all orders")

    new_orders = []
    for status in ["READY_TO_SHIP", "PROCESSED", "SHIPPED"]:
        cursor = ""
        while True:
            resp = call_api("order/get_order_list", {
                "order_status": status, "time_range_field": "create_time",
                "time_from": ts_from, "time_to": ts_to, "page_size": 100, "cursor": cursor
            })
            if resp.get("error"):
                print(f"API error ({status}): {resp['error']} - {resp.get('message', '')}")
                return False

            orders = resp.get("response", {}).get("order_list", [])
            for o in orders:
                sn = o.get("order_sn")
                if sn and sn not in synced:
                    new_orders.append(o)
            cursor = resp.get("response", {}).get("next_cursor", "")
            if not cursor or not orders:
                break

    print(f"Found {len(new_orders)} new orders to process")
    if not new_orders:
        print("Nothing to sync")
        return True

    sku_qty = {}
    for order in new_orders:
        sn = order.get("order_sn")
        detail = call_api("order/get_order_detail", {"order_sn_list": [sn], "response_optional_fields": "item_list"}, "GET")
        if detail.get("error"):
            print(f"  Order {sn} detail failed: {detail.get('error')}")
            continue
        items = detail.get("response", {}).get("order_list", [])
        for o in items:
            for item in o.get("item_list", []):
                sku = item.get("model_sku", "").strip()
                qty = item.get("model_quantity_purchased", 1)
                if sku:
                    sku_qty[sku] = sku_qty.get(sku, 0) + qty
                    print(f"  {sn}: {sku} x{qty}")

    if not sku_qty:
        print("No SKUs to sync")
        return True

    # Download products.json to map SKU -> row number
    raw = pa_download("inventory/static/products.json")
    if not raw:
        print("Failed to download products.json")
        return False

    products = json.loads(raw)
    plist = products.get("products", products if isinstance(products, list) else [])
    sku_to_row = {p.get("item", "").strip(): str(p.get("row", "")) for p in plist}

    # Download stock.json (actual inventory used by Flask app)
    raw_stock = pa_download("inventory/stock.json")
    if not raw_stock:
        # Initialize empty stock.json if not exists
        STOCK = {}
    else:
        STOCK = json.loads(raw_stock)

    updated = 0
    for sku, sold in sku_qty.items():
        row = sku_to_row.get(sku)
        if not row:
            print(f"  SKIP {sku}: no row found in products.json")
            continue
        entry = STOCK.setdefault(row, {"qty": 0, "alert": 0, "location": ""})
        old_qty = entry.get("qty", 0)
        try:
            new_qty = int(old_qty) - sold
        except (ValueError, TypeError):
            new_qty = 0 - sold
        entry["qty"] = new_qty
        updated += 1
        print(f"  {sku} (row {row}): {old_qty} -> {new_qty} (-{sold})")

    if updated:
        pa_upload("inventory/stock.json", json.dumps(STOCK, ensure_ascii=False, indent=2))
        pa_upload("inventory/static/products.json", json.dumps(products, ensure_ascii=False, indent=2))
        print(f"Updated stock.json ({updated} SKUs) and products.json")
    else:
        print("No products to update")

    # Reload PA web app so changes take effect
    r = requests.post(f"https://www.pythonanywhere.com/api/v0/user/{PA_USER}/webapps/{PA_USER}.pythonanywhere.com/reload/",
        headers={"Authorization": f"Token {PA_API_TOKEN}"}, timeout=15)
    if r.ok:
        print("Web app reloaded")
    else:
        print(f"Web app reload failed: {r.status_code}")

    # Save synced order IDs back to PA
    all_synced = synced | {o.get("order_sn") for o in new_orders}
    pa_upload("inventory/synced_orders.json", json.dumps(list(all_synced), ensure_ascii=False))
    print(f"Saved {len(all_synced)} total synced order IDs")

    # Monthly sales report
    ym = f"{today.year}-{today.month:02d}"
    report = f"sales_{ym}.csv"
    raw2 = pa_download(report)
    existing = {}
    if raw2:
        for line in raw2.strip().split("\n")[1:]:
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
