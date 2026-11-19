"""cap_solve.py — solve captcha pakai SadCaptcha /puzzle.

Dari skill sadcaptcha-shopee-api:
  POST /puzzle {puzzleImageB64, pieceImageB64} -> {slideXProportion}
  camelCase. Tanpa data: prefix.

Tes semua varian (puzzle, shopee-image-drag, pre-analyze) untuk
lihat mana yang cocok dengan captcha_type=10.
"""
import json, base64, sys
import requests

KEY = open("/root/shopee-farm/bot_key.txt").read().strip()
BASE = "https://www.sadcaptcha.com/api/v1"


def b64(path):
    raw = open(path, "rb").read()
    return base64.b64encode(raw).decode()


pz = b64("cappic/bg_img.jpg")
pc = b64("cappic/puzzle_img.jpg")
print(f"puzzle: {len(pz)}B b64 | piece: {len(pc)}B b64")

# 0. credits
print("\n=== credits ===")
r = requests.get(f"{BASE}/license/credits", params={"licenseKey": KEY}, timeout=30)
print(" ", r.text[:120])

# 1. /puzzle
print("\n=== POST /puzzle ===")
try:
    r = requests.post(f"{BASE}/puzzle", params={"licenseKey": KEY},
                      json={"puzzleImageB64": pz, "pieceImageB64": pc}, timeout=60)
    print(f"  {r.status_code} {r.text[:300]}")
    if r.status_code == 200:
        j = r.json()
        prop = j.get("slideXProportion")
        print(f"  ★ slideXProportion = {prop}")
        json.dump({"endpoint": "puzzle", "prop": prop, "raw": j},
                  open("SOLVE.json", "w"), indent=1)
except Exception as e:
    print("  err:", str(e)[:100])

# 2. /shopee-image-drag
print("\n=== POST /shopee-image-drag ===")
try:
    r = requests.post(f"{BASE}/shopee-image-drag", params={"licenseKey": KEY},
                      json={"puzzleImageB64": pz, "pieceImageB64": pc}, timeout=60)
    print(f"  {r.status_code} {r.text[:300]}")
except Exception as e:
    print("  err:", str(e)[:100])

# 3. /shopee-image-crawl-pre-analyze
print("\n=== POST /shopee-image-crawl-pre-analyze ===")
try:
    r = requests.post(f"{BASE}/shopee-image-crawl-pre-analyze",
                      params={"licenseKey": KEY},
                      json={"image_b64": pz}, timeout=60)
    print(f"  {r.status_code} {r.text[:300]}")
except Exception as e:
    print("  err:", str(e)[:100])
