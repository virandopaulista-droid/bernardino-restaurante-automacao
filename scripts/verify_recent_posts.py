import os
import urllib.request
import json

TOKEN = os.environ["FB_PAGE_ACCESS_TOKEN"]
PAGE_ID = os.environ["FB_PAGE_ID"]
IG_ID = os.environ.get("IG_BUSINESS_ID")


def call(path, params=""):
    url = f"https://graph.facebook.com/v21.0/{path}?{params}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


print("=== Facebook Page feed (últimos 10 posts) ===")
try:
    data = call(f"{PAGE_ID}/posts", "fields=message,created_time,attachments{media_type,url}&limit=10")
    for p in data.get("data", []):
        msg = (p.get("message") or "").replace("\n", " ")[:70]
        print(p.get("created_time"), "|", msg)
except Exception as e:
    print("ERRO ao buscar feed do Facebook:", e)

print()
print("=== Instagram media (últimos 10) ===")
if IG_ID:
    try:
        data = call(f"{IG_ID}/media", "fields=caption,timestamp,media_type,media_product_type&limit=10")
        for p in data.get("data", []):
            cap = (p.get("caption") or "").replace("\n", " ")[:70]
            print(p.get("timestamp"), "|", p.get("media_product_type"), p.get("media_type"), "|", cap)
    except Exception as e:
        print("ERRO ao buscar media do Instagram:", e)
else:
    print("(sem IG_BUSINESS_ID)")
