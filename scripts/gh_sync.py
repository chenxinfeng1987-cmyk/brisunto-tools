"""
GitHub Actions: creates sync_trigger.json on PA to signal the poller.
The actual sync runs on PA console via sync_poller.py (whitelisted Shopee IP).
"""
import sys, os, json, requests
from datetime import datetime, timezone, timedelta

PA_TOKEN = os.environ["PA_API_TOKEN"]
PA_USER = "brisunto2026"

def pa_upload(path, content):
    r = requests.post(f"https://www.pythonanywhere.com/api/v0/user/{PA_USER}/files/path/{path}",
                      files={"content": ("f", content.encode("utf-8"), "application/octet-stream")},
                      headers={"Authorization": f"Token {PA_TOKEN}"}, timeout=15)
    return r.ok

def main():
    now = datetime.now()
    trigger = json.dumps({"triggered_at": now.isoformat(), "status": "pending"})
    if pa_upload("inventory/sync_trigger.json", trigger):
        print(f"Trigger file created at {now.strftime('%Y-%m-%d %H:%M:%S')}")
        print("PA console poller will pick it up within 60s")
        return True
    else:
        print("Failed to create trigger file")
        return False

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
