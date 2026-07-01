"""
Triggers sync by sending command to a PA bash console.
Runs in GitHub Actions. The actual sync runs on PA (whitelisted Shopee IP).
"""
import sys, os, json, requests, re
from datetime import datetime, timezone, timedelta

PA_USER = os.environ["PA_USER"]
PA_PASS = os.environ["PA_PASS"]

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Logging into PA...")

    s = requests.Session()
    r1 = s.get("https://www.pythonanywhere.com/login/", timeout=15)
    m = re.search(r'csrfmiddlewaretoken.*?value="([^"]+)"', r1.text)
    if not m:
        print("Failed to parse PA login page")
        return False
    csrf = m.group(1)
    s.post("https://www.pythonanywhere.com/login/", data={
        "csrfmiddlewaretoken": csrf, "auth-username": PA_USER, "auth-password": PA_PASS,
        "login_view-current_step": "auth"}, headers={"Referer": "https://www.pythonanywhere.com/login/"}, timeout=15)

    # List consoles
    r2 = s.get(f"https://www.pythonanywhere.com/api/v0/user/{PA_USER}/consoles/",
               headers={"Accept": "application/json"}, timeout=10)
    if not r2.ok:
        print(f"Failed to list consoles: {r2.status_code}")
        return False
    consoles = r2.json()
    bash_console = None
    for c in consoles:
        if c.get("executable") == "bash":
            bash_console = c["id"]
            break
    if not bash_console:
        # Try to create a new console
        csrf_token = s.cookies.get("csrftoken", "")
        r_new = s.post(f"https://www.pythonanywhere.com/api/v0/user/{PA_USER}/consoles/",
                       json={"executable": "bash", "arguments": ""},
                       headers={"X-CSRFToken": csrf_token, "Referer": "https://www.pythonanywhere.com/"}, timeout=15)
        if r_new.status_code == 201:
            bash_console = r_new.json().get("id")
            print(f"Created new console #{bash_console}")
        else:
            print(f"Failed to create console: {r_new.status_code}. Open one on PA first.")
            return False

    # Send sync command
    cmd = "cd ~ && python3 sync_shopee_orders.py\n"
    h = {"X-CSRFToken": s.cookies.get("csrftoken", ""), "Referer": "https://www.pythonanywhere.com/"}
    r3 = s.post(f"https://www.pythonanywhere.com/api/v0/user/{PA_USER}/consoles/{bash_console}/send/",
                json={"input": cmd}, headers=h, timeout=10)
    if not r3.ok:
        print(f"Failed to send command: {r3.status_code} {r3.text[:200]}")
        return False

    print(f"Sync command sent to console #{bash_console}")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
