import requests, hashlib, hmac, time, json, sys, os
from urllib.parse import urlencode

PARTNER_ID = 2035803
PARTNER_KEY = "shpk4e514b47724f6778565a694d664f446c704765705a666542476e69716878"
ACCESS_TOKEN = "566e41435263544d5a70636f66786675"
REFRESH_TOKEN = "5758746357684e487a4a464a74644b4e"
SHOP_ID = 1025905569
MERCHANT_ID = 3969241

BASE_URL = "https://openplatform.shopee.cn/api/v2"

CATEGORY_RULES = [
    (101796, ["wrench", "spanner", "ratchet", "socket", "扳手", "套筒", "棘轮"]),
    (101798, ["plier", "cutter", "nipp", "pincer", "钳子", "剪", "老虎"]),
    (101458, ["timing", "test", "diagnostic", "repair", "puller", "extract", "injector", "engine", "tension", "brake", "测试", "诊断", "拉", "拆", "刹车", "引擎", "皮带", "汽保"]),
    (101800, ["drill", "screwdriver", "driver", "bit ", "电钻", "螺丝刀"]),
    (101811, []),
]

def get_category_for_product(name_en, name_cn=""):
    text = (str(name_en or "") + " " + str(name_cn or "")).lower()
    for cat_id, keywords in CATEGORY_RULES:
        if not keywords:
            continue
        for kw in keywords:
            if kw.lower() in text:
                return cat_id
    return 101811

def generate_sign(url_path, ts, access_token="", shop_id=""):
    parts = [str(PARTNER_ID), url_path, str(ts)]
    if access_token:
        parts.append(access_token)
    if shop_id:
        parts.append(str(shop_id))
    base_string = "".join(parts)
    return hmac.new(PARTNER_KEY.encode('utf-8'), base_string.encode('utf-8'), hashlib.sha256).hexdigest()

def common_params(ts):
    return {"partner_id": PARTNER_ID, "timestamp": ts, "access_token": ACCESS_TOKEN, "shop_id": SHOP_ID}

def call_api(endpoint, body=None, method="POST"):
    url_path = f"/api/v2/{endpoint}"
    ts = int(time.time())
    sign = generate_sign(url_path, ts, ACCESS_TOKEN, SHOP_ID)
    params = {"partner_id": PARTNER_ID, "timestamp": ts, "access_token": ACCESS_TOKEN, "shop_id": SHOP_ID, "sign": sign}
    url = f"{BASE_URL}/{endpoint}"
    headers = {"Content-Type": "application/json"}
    if method == "POST":
        r = requests.post(url, params=params, json=body, headers=headers, timeout=60)
    else:
        if body:
            params.update(body)
        r = requests.get(url, params=params, headers=headers, timeout=60)
    return r.json()

def upload_image(image_path):
    url_path = "/api/v2/media_space/upload_image"
    ts = int(time.time())
    sign = generate_sign(url_path, ts, ACCESS_TOKEN, SHOP_ID)
    params = {"partner_id": PARTNER_ID, "timestamp": ts, "access_token": ACCESS_TOKEN, "shop_id": SHOP_ID, "sign": sign}
    url = f"{BASE_URL}/media_space/upload_image"
    with open(image_path, "rb") as f:
        files = [("image", (os.path.basename(image_path), f, "image/jpeg"))]
        r = requests.post(url, params=params, files=files, timeout=120)
    result = r.json()
    if result.get("error") in ("", None) and result.get("response"):
        return result["response"]["image_info"]["image_id"]
    else:
        raise Exception(f"Upload image failed: {result}")

def get_categories():
    return call_api("product/get_category", method="GET")

def get_attributes(category_id):
    return call_api("product/get_attribute_tree", {"category_id": category_id})

def add_item(product):
    return call_api("product/add_item", product)

if __name__ == "__main__":
    if not all([PARTNER_ID, PARTNER_KEY, ACCESS_TOKEN, SHOP_ID]):
        print("请先在脚本中配置 PARTNER_ID, PARTNER_KEY, ACCESS_TOKEN, SHOP_ID")
        sys.exit(1)
