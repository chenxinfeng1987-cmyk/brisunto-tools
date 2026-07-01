"""
GitHub Actions sync runner for PA inventory.
Triggered by sync_trigger.json on PA or scheduled.
Downloads products.json from PA, runs sync, uploads changed files back.
"""
import sys, os, json, time, hashlib, hmac, requests
from datetime import datetime, timedelta, timezone
CN_TZ = timezone(timedelta(hours=8))  # China time
from collections import defaultdict

# === Credentials ===
PA_USER = "brisunto2026"
PA_TOKEN = os.environ["PA_API_TOKEN"]

BASE_URL = "https://openplatform.shopee.cn/api/v2"
PARTNER_ID = int(os.environ["SHOPEE_PARTNER_ID"])
PARTNER_KEY = os.environ["SHOPEE_PARTNER_KEY"]
ACCESS_TOKEN = os.environ["SHOPEE_ACCESS_TOKEN"]
SHOP_ID = int(os.environ["SHOPEE_SHOP_ID"])

def generate_sign(url_path, ts):
    parts = [str(PARTNER_ID), url_path, str(ts), ACCESS_TOKEN, str(SHOP_ID)]
    base_string = "".join(parts)
    return hmac.new(PARTNER_KEY.encode(), base_string.encode(), hashlib.sha256).hexdigest()

def call_api(endpoint, body=None):
    url_path = f"/api/v2/{endpoint}"
    ts = int(time.time())
    sign = generate_sign(url_path, ts)
    params = {"partner_id": PARTNER_ID, "timestamp": ts, "access_token": ACCESS_TOKEN,
              "shop_id": SHOP_ID, "sign": sign}
    r = requests.post(f"{BASE_URL}/{endpoint}", params=params, json=body, timeout=60)
    return r.json()

def pa_download(path):
    r = requests.get(f"https://www.pythonanywhere.com/api/v0/user/{PA_USER}/files/path/{path}",
                     headers={"Authorization": f"Token {PA_TOKEN}"}, timeout=15)
    return r.text if r.ok else None

def pa_upload(path, content):
    r = requests.post(f"https://www.pythonanywhere.com/api/v0/user/{PA_USER}/files/path/{path}",
                      files={"content": ("f", content.encode("utf-8"), "application/octet-stream")},
                      headers={"Authorization": f"Token {PA_TOKEN}"}, timeout=15)
    return r.ok

def pa_delete(path):
    requests.delete(f"https://www.pythonanywhere.com/api/v0/user/{PA_USER}/files/path/{path}",
                    headers={"Authorization": f"Token {PA_TOKEN}"}, timeout=10)

def fetch_orders(from_ts=None):
    now_cn = datetime.now(CN_TZ)
    if from_ts is None:
        from_ts = int(now_cn.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    now_ts = int(now_cn.timestamp())
    resp = call_api("order/get_order_list", {
        "order_status": "COMPLETED",
        "create_time_from": from_ts,
        "create_time_to": now_ts,
        "page_size": 100,
        "page_number": 1,
    })
    if resp.get("error"):
        print(f"API error: {resp}")
        return [], resp.get("message", "Unknown error")
    orders = resp.get("response", {}).get("order_list", [])
    print(f"Fetched {len(orders)} completed orders")
    return orders, None

def get_order_detail(order_sn):
    resp = call_api("order/get_order_detail", {"order_sn_list": [order_sn]})
    items = []
    for o in resp.get("response", {}).get("order_list", []):
        for item in o.get("item_list", []):
            items.append(item)
    return items

def update_report(items_data, products, year, month):
    ym = f"{year}-{month:02d}"
    report_raw = pa_download(f"sales_{ym}.csv")
    existing = {}
    if report_raw:
        for line in report_raw.strip().split("\n")[1:]:
            parts = line.strip().split(",")
            if len(parts) >= 4:
                existing[parts[0]] = {"qty": int(parts[2]), "orders": int(parts[3]), "name": parts[1]}
    for sku, info in items_data.items():
        if sku in existing:
            existing[sku]["qty"] += info["qty"]
            existing[sku]["orders"] += info["orders"]
        else:
            existing[sku] = info
    lines = ["SKU,产品名称,销量,订单数"]
    for sku in sorted(existing.keys()):
        d = existing[sku]
        lines.append(f"{sku},{d['name']},{d['qty']},{d['orders']}")
    pa_upload(f"sales_{ym}.csv", "\n".join(lines))
    print(f"  Report sales_{ym}.csv updated")

def main():
    # Check trigger
    trigger_raw = pa_download("inventory/sync_trigger.json")
    if not trigger_raw:
        print("No trigger file found.")
        return False
    print(f"Trigger found: {trigger_raw[:100]}")

    # Download last_sync.json to determine time range
    last_raw = pa_download("inventory/last_sync.json")
    last_until = None
    if last_raw:
        try:
            last_until = json.loads(last_raw).get("synced_until")
        except: pass
    now_cn = datetime.now(CN_TZ)
    midnight_today = int(now_cn.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    from_ts = max(last_until, midnight_today) if last_until else midnight_today
    print(f"Syncing orders from {datetime.fromtimestamp(from_ts, CN_TZ).strftime('%Y-%m-%d %H:%M:%S')}")

    # Download products.json
    products_raw = pa_download("inventory/static/products.json")
    if not products_raw:
        print("Failed to download products.json - aborting")
        return False
    products = json.loads(products_raw)
    print(f"Loaded {len(products)} products")

    # Fetch orders since last sync
    orders, err = fetch_orders(from_ts)
    if err:
        print(f"Sync aborted: {err}")
        return False
    if not orders:
        pa_upload("inventory/last_sync.json", json.dumps({"synced_until": int(datetime.now(CN_TZ).timestamp())}))
        pa_delete("inventory/sync_trigger.json")
        print("No orders today - nothing to sync")
        return True

    # Process orders
    sku_qty = {}
    sku_details = {}
    for order in orders:
        items = get_order_detail(order.get("order_sn"))
        for item in items:
            sku = item.get("item_sku", "").strip()
            qty = item.get("model_quantity_purchased", 1)
            name = item.get("item_name", "")
            if sku:
                sku_qty[sku] = sku_qty.get(sku, 0) + qty
                if sku not in sku_details:
                    sku_details[sku] = name.replace(",", " ")
                print(f"  {order['order_sn']}: {sku} x{qty}")

    if not sku_qty:
        print("No processable SKUs")
        pa_upload("inventory/last_sync.json", json.dumps({"synced_until": int(datetime.now(CN_TZ).timestamp())}))
        pa_delete("inventory/sync_trigger.json")
        return True

    # Update products stock
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
            print(f"  {item_sku}: {old_stock} → {new_stock} (-{sold})")

    # Upload products.json
    today = datetime.now(CN_TZ)
    pa_upload("inventory/static/products.json", json.dumps(products, ensure_ascii=False, indent=2))
    print(f"Uploaded products.json ({updated} SKUs updated)")

    # Update monthly report
    items_data = {}
    for sku, qty in sku_qty.items():
        items_data[sku] = {"qty": qty, "orders": len(set(o["order_sn"] for o in orders)),
                           "name": sku_details.get(sku, "")}
    update_report(items_data, products, today.year, today.month)

    # Save last sync time, delete trigger
    pa_upload("inventory/last_sync.json", json.dumps({"synced_until": int(datetime.now(CN_TZ).timestamp())}))
    pa_delete("inventory/sync_trigger.json")
    print("Sync complete!")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
