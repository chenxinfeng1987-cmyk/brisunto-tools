import json, os, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
FIN_LEDGER = os.path.join(ROOT, "fin_ledger.json")
FIN_SALES = os.path.join(ROOT, "fin_sales.json")

PLATFORMS = ["shopee", "aliexpress", "pdd", "1688", "taobao", "other"]

def load_ledger():
    if os.path.exists(FIN_LEDGER):
        try:
            with open(FIN_LEDGER, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return []

def save_ledger(ledger):
    with open(FIN_LEDGER, "w", encoding="utf-8") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=2)

def load_sales():
    if os.path.exists(FIN_SALES):
        try:
            with open(FIN_SALES, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return []

def save_sales(sales):
    with open(FIN_SALES, "w", encoding="utf-8") as f:
        json.dump(sales, f, ensure_ascii=False, indent=2)

def next_id(items):
    return max((x["id"] for x in items), default=0) + 1

def get_stats(ledger):
    income_total = sum(e["amount"] for e in ledger if e["type"] == "income")
    expense_total = sum(e["amount"] for e in ledger if e["type"] == "expense")
    by_platform = {}
    for p in PLATFORMS:
        inc = sum(e["amount"] for e in ledger if e["type"] == "income" and e["platform"] == p)
        exp = sum(e["amount"] for e in ledger if e["type"] == "expense" and e["platform"] == p)
        shipping = sum(e["amount"] for e in ledger if e["type"] == "expense" and e["platform"] == p and e["category"] == "shipping")
        procurement = sum(e["amount"] for e in ledger if e["type"] == "expense" and e["platform"] == p and e["category"] == "procurement")
        by_platform[p] = {"income": inc, "expense": exp, "shipping": shipping, "procurement": procurement}
    return {"income_total": income_total, "expense_total": expense_total, "balance": income_total - expense_total, "by_platform": by_platform}
