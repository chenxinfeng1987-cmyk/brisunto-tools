import sys, os, json, time
from datetime import datetime, timedelta
from collections import defaultdict

# Detect environment
ON_PYTHONANYWHERE = os.path.exists("/home/brisunto2026")

if ON_PYTHONANYWHERE:
    sys.path.insert(0, "/home/brisunto2026")
    INVENTORY_DIR = "/home/brisunto2026"
    HOME_DIR = "/home/brisunto2026"
else:
    sys.path.insert(0, r"D:\TOPPULS\外贸开发\shopee_upload")
    INVENTORY_DIR = r"D:\TOPPULS\外贸开发\库存系统"
    HOME_DIR = r"D:\TOPPULS\外贸开发"

from shopee_api import call_api

PRODUCTS_JSON = os.path.join(INVENTORY_DIR, "static", "products.json")

def get_order_list(order_status="COMPLETED", create_time_from=None, create_time_to=None):
    now = int(time.time())
    if create_time_from is None:
        create_time_from = now - 86400
    if create_time_to is None:
        create_time_to = now
    body = {
        "order_status": order_status,
        "time_range_field": "create_time",
        "time_from": create_time_from,
        "time_to": create_time_to,
        "page_size": 100,
        "cursor": "",
    }
    return call_api("order/get_order_list", body, method="GET")

def get_order_detail(order_sn):
    body = {"order_sn_list": [order_sn]}
    return call_api("order/get_order_detail", body, method="GET")

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def update_monthly_report(items_data, year, month):
    """追加当日订单到月度报表"""
    ym = f"{year}-{month:02d}"
    report_path = os.path.join(HOME_DIR, f"sales_{ym}.csv")
    
    # 读取已有数据
    existing = {}
    if os.path.exists(report_path):
        with open(report_path, "r", encoding="utf-8") as f:
            for line in f.readlines()[1:]:  # skip header
                parts = line.strip().split(",")
                if len(parts) >= 4:
                    sku = parts[0]
                    existing[sku] = {"qty": int(parts[2]), "orders": int(parts[3]), "name": parts[1]}

    # 合并当日数据
    for sku, info in items_data.items():
        if sku in existing:
            existing[sku]["qty"] += info["qty"]
            existing[sku]["orders"] += info["orders"]
        else:
            existing[sku] = info

    # 写回
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("SKU,产品名称,销量,订单数\n")
        for sku in sorted(existing.keys()):
            d = existing[sku]
            f.write(f"{sku},{d['name']},{d['qty']},{d['orders']}\n")
    
    print(f"  月度报表已更新: sales_{ym}.csv")
    return report_path

def main():
    today = datetime.now()
    today_start = int(datetime(today.year, today.month, today.day).timestamp())
    today_end = int((today + timedelta(days=1)).timestamp())

    print(f"[{today.strftime('%Y-%m-%d %H:%M:%S')}] 开始拉取 Shopee 订单...")

    resp = get_order_list("COMPLETED", today_start, today_end)
    if resp.get("error"):
        print(f"API 错误: {resp}")
        return

    orders = resp.get("response", {}).get("order_list", [])
    print(f"获取到 {len(orders)} 笔已完成订单")

    if not orders:
        return

    # 收集 SKU 数据
    sku_qty = {}
    sku_details = {}
    for order in orders:
        order_sn = order.get("order_sn")
        detail = get_order_detail(order_sn)
        if detail.get("error"):
            print(f"  订单 {order_sn} 详情获取失败: {detail}")
            continue
        items = detail.get("response", {}).get("order_list", [])
        for o in items:
            for item in o.get("item_list", []):
                sku = item.get("item_sku", "").strip()
                qty = item.get("model_quantity_purchased", 1)
                name = item.get("item_name", "")
                if sku:
                    sku_qty[sku] = sku_qty.get(sku, 0) + qty
                    if sku not in sku_details:
                        sku_details[sku] = name
                    print(f"  {order_sn}: {sku} x{qty}")

    if not sku_qty:
        print("没有需要同步的 SKU")
        return

    # 更新月度报表
    items_data = {}
    for sku, qty in sku_qty.items():
        items_data[sku] = {
            "qty": qty,
            "orders": len(set(o.get("order_sn") for o in orders)),
            "name": sku_details.get(sku, "").replace(",", " ")
        }
    update_monthly_report(items_data, today.year, today.month)

    # 更新本地库存
    if os.path.exists(PRODUCTS_JSON):
        products = load_json(PRODUCTS_JSON)
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
                print(f"  ✔ {item_sku}: {old_stock} → {new_stock} (-{sold})")
        save_json(PRODUCTS_JSON, products)
        print(f"库存更新: {updated} 个 SKU")
    else:
        print(f"products.json 不存在 ({PRODUCTS_JSON})，跳过库存更新")

    print("完成！")

if __name__ == "__main__":
    main()
