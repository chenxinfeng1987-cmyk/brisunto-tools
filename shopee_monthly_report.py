"""
月度 SKU 销量汇总
用法: python3 /home/brisunto2026/shopee_monthly_report.py [2026-06]
如果不传月份，默认上个月
"""
import sys, os, json, time
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, "/home/brisunto2026")
from shopee_api import call_api

def get_orders_in_range(start_ts, end_ts):
    """拉取时间范围内所有已完成订单"""
    all_items = []
    page = 1
    while True:
        resp = call_api("order/get_order_list", {
            "order_status": "COMPLETED",
            "create_time_from": start_ts,
            "create_time_to": end_ts,
            "page_size": 100,
            "page_number": page,
        })
        if resp.get("error"):
            print(f"API 错误: {resp}")
            break
        orders = resp.get("response", {}).get("order_list", [])
        if not orders:
            break
        for order in orders:
            order_sn = order.get("order_sn")
            detail = call_api("order/get_order_detail", {"order_sn_list": [order_sn]})
            if detail.get("error"):
                continue
            for o in detail.get("response", {}).get("order_list", []):
                for item in o.get("item_list", []):
                    sku = item.get("item_sku", "").strip()
                    qty = item.get("model_quantity_purchased", 1)
                    name = item.get("item_name", "")
                    if sku:
                        all_items.append({"sku": sku, "name": name, "qty": qty, "order_sn": order_sn})
        page += 1
        time.sleep(0.5)
    return all_items

def main():
    # 解析月份参数
    if len(sys.argv) > 1:
        ym = sys.argv[1]
    else:
        last = datetime.now().replace(day=1) - timedelta(days=1)
        ym = last.strftime("%Y-%m")

    year, month = ym.split("-")
    start_ts = int(datetime(int(year), int(month), 1).timestamp())
    if int(month) == 12:
        end_ts = int(datetime(int(year)+1, 1, 1).timestamp())
    else:
        end_ts = int(datetime(int(year), int(month)+1, 1).timestamp())

    print(f"拉取 {ym} 订单...")
    items = get_orders_in_range(start_ts, end_ts)

    # 按 SKU 汇总
    summary = defaultdict(lambda: {"qty": 0, "orders": set(), "name": ""})
    for it in items:
        sku = it["sku"]
        summary[sku]["qty"] += it["qty"]
        summary[sku]["orders"].add(it["order_sn"])
        if not summary[sku]["name"]:
            summary[sku]["name"] = it["name"]

    # 输出
    out_path = f"/home/brisunto2026/sales_{ym}.csv"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("SKU,产品名称,销量,订单数\n")
        for sku in sorted(summary.keys()):
            d = summary[sku]
            name_clean = d["name"].replace(",", " ")
            f.write(f"{sku},{name_clean},{d['qty']},{len(d['orders'])}\n")

    total_qty = sum(d["qty"] for d in summary.values())
    print(f"\n{ym} 汇总: {len(summary)} 个 SKU, 共 {total_qty} 件, {len(items)} 条订单明细")
    print(f"报表已保存: {out_path}")
    print(f"\n前十 SKU:")
    for sku in sorted(summary.keys(), key=lambda s: -summary[s]["qty"])[:10]:
        d = summary[sku]
        print(f"  {sku}: {d['qty']} 件 ({len(d['orders'])} 单)")

if __name__ == "__main__":
    main()
