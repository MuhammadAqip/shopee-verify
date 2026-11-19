"""cap_correct.py — generate captcha pakai SCENE "crawler_item" + appkey "TSS.PC".

Dari ivs_js/078.js:
  if (m === ChallengeType.Captcha) {
     k = PC ? `${F || "TSS"}.PC` : ...
     renderPopup({ appKey: k, scene: "crawler_item",
                   clientId, antiBotTrackingId, ... })
  }

  -> appKey untuk PC = "TSS.PC" (atau prefiks + .PC)
  -> scene = "crawler_item"

Ini schema yang BENAR. Generate dengan params ini.
"""
import json, sys, base64, hashlib, os
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1553.txt"
PROXY = "http://127.0.0.1:18080"
KEY_LIVE = b"dRgUkXp2r5u8x/A?D(G+KbPeShVmYq3t"
APPKEY = "f9ffc83459897a13dd14c537e84b1753"


def log(*a):
    print(*a, flush=True)


def evp(pw, salt):
    d, prev = b"", b""
    while len(d) < 48:
        prev = hashlib.md5(prev + pw + salt).digest()
        d += prev
    return d[:32], d[32:48]


def enc(obj):
    salt = os.urandom(8)
    key, iv = evp(KEY_LIVE, salt)
    ct = AES.new(key, AES.MODE_CBC, iv).encrypt(
        pad(json.dumps(obj, separators=(",", ":")).encode(), 16))
    return base64.b64encode(b"Salted__" + salt + ct).decode()


def dec(b64):
    try:
        raw = base64.b64decode(b64)
        if not raw.startswith(b"Salted__"):
            return {"_nohdr": raw[:60]}
        key, iv = evp(KEY_LIVE, raw[8:16])
        return json.loads(unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(raw[16:]), 16))
    except Exception as e:
        return {"_err": str(e)[:60]}


ck = open(CK).read().strip()
cookies = {p.split("=", 1)[0].strip(): p.split("=", 1)[1].strip()
           for p in ck.split(";") if "=" in p}
client_id = cookies.get("SPC_CLIENTID", "")

s = requests.Session()
s.cookies.update(cookies)
s.proxies = {"http": PROXY, "https": PROXY}
s.headers.update({
    "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"),
    "x-api-source": "pc", "af-ac-enc-dat": "0123456789abcdef",
    "x-sz-sdk-version": "1.12.45", "x-requested-with": "XMLHttpRequest",
    "referer": "https://shopee.co.id/", "accept": "application/json",
    "content-type": "application/json"})

# 1. get_config (GET, tanpa auth) -> tracking_id
log("=== tracking dari browser ===")
try:
    tracking = open("TRACKING.txt").read().strip()
except Exception:
    tracking = ""
log(f"  len={len(tracking)} {tracking[:45]}")

# 2. generate berbagai kombinasi appkey + scene
COMBOS = [
    ("TSS.PC", "crawler_item"),
    (APPKEY, "crawler_item"),
    ("TSS.PC", "captcha"),
    (APPKEY, "crawler_item"),
    ("TSS", "crawler_item"),
    ("TSS.PC", "crawler"),
    (client_id, "crawler_item"),
]

for appkey, scene in COMBOS:
    p = {"app_key": appkey, "scene": scene, "captcha_type": 1,
         "image_version": "", "client_id": client_id,
         "captcha_extra_info": {"tracking_id": tracking} if tracking else None,
         "captcha_id": ""}
    try:
        rr = s.post("https://shopee.co.id/api/v4/anti_fraud/captcha/generate",
                    json={"encrypted_data": enc(p)}, timeout=40)
        jj = rr.json()
        log(f"\n[{appkey} | {scene}] {rr.status_code} err={jj.get('error')}")
        if jj.get("encrypted_data"):
            d = dec(jj["encrypted_data"])
            log(f"  ✅ {json.dumps(d)[:400]}")
            if d.get("error") == 0 or d.get("captcha"):
                log("  🎉🎉🎉 CAPTCHA DIDAPAT!")
                json.dump(d, open("/root/shopee-verify/CAPTCHA.json", "w"), indent=1)
                break
        else:
            log(f"  plain: {json.dumps(jj)[:200]}")
    except Exception as e:
        log(f"\n[{appkey}|{scene}] ERR {str(e)[:60]}")
