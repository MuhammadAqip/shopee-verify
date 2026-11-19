"""cap_gen.py — captcha/generate dengan encrypted_data BENAR.

Temuan dari ivs_js/063.js:
  body = {encrypted_data: CryptoJS.AES.encrypt(JSON.stringify(p), KEY)}
  p = {app_key, scene, captcha_type, image_version,
       captcha_extra_info:{tracking_id}, captcha_id}
  response juga encrypted_data -> decrypt dengan key yang sama

KEY LIVE = "dRgUkXp2r5u8x/A?D(G+KbPeShVmYq3t"

Tes berbagai scene untuk cari yang valid.
"""
import json, sys, base64, hashlib, os
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1553.txt"
PROXY = "http://127.0.0.1:18080"
KEY_LIVE = b"dRgUkXp2r5u8x/A?D(G+KbPeShVmYq3t"
KEY_TEST = b"5v8y/B?E(H+MbPeShVmYq3t6w9z$C&F)"


def log(*a):
    print(*a, flush=True)


def evp(pw, salt):
    d = b""
    prev = b""
    while len(d) < 48:
        prev = hashlib.md5(prev + pw + salt).digest()
        d += prev
    return d[:32], d[32:48]


def aes_enc(obj, live=True):
    pw = KEY_LIVE if live else KEY_TEST
    salt = os.urandom(8)
    key, iv = evp(pw, salt)
    pt = json.dumps(obj, separators=(",", ":")).encode()
    ct = AES.new(key, AES.MODE_CBC, iv).encrypt(pad(pt, 16))
    return base64.b64encode(b"Salted__" + salt + ct).decode()


def aes_dec(b64, live=True):
    pw = KEY_LIVE if live else KEY_TEST
    try:
        raw = base64.b64decode(b64)
        if not raw.startswith(b"Salted__"):
            return {"_raw": b64[:100], "_noheader": True}
        salt = raw[8:16]
        key, iv = evp(pw, salt)
        pt = unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(raw[16:]), 16)
        return json.loads(pt)
    except Exception as e:
        return {"_err": str(e)[:80]}


ck = open(CK).read().strip()
cookies = {p.split("=", 1)[0].strip(): p.split("=", 1)[1].strip()
           for p in ck.split(";") if "=" in p}

s = requests.Session()
s.cookies.update(cookies)
s.proxies = {"http": PROXY, "https": PROXY}
s.headers.update({
    "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"),
    "x-api-source": "pc",
    "af-ac-enc-dat": "0123456789abcdef",
    "x-sz-sdk-version": "1.12.45",
    "x-requested-with": "XMLHttpRequest",
    "referer": "https://shopee.co.id/",
    "accept": "application/json",
    "content-type": "application/json",
})

# 1. get_config dulu -> ambil tracking_id
log("=== get_config ===")
r = s.get("https://shopee.co.id/api/v4/anti_fraud/captcha/get_config", timeout=40)
log(f"  {r.status_code} {r.text[:250]}")
try:
    cfg = r.json()
except Exception:
    cfg = {}
tracking = (cfg.get("data") or {}).get("tracking_id") or cfg.get("tracking_id")
log(f"  tracking_id: {str(tracking)[:60]}")

# 2. coba generate dengan berbagai scene
SCENES = ["captcha", "login", "verify", "buyer_login", "account",
          "change_phone", "ivs", "sms_login", "antibot", "default",
          "pc_login", "shopee_login", "d-nonptcha-sync"]

for scene in SCENES:
    p = {
        "app_key": "f9ffc83459897a13dd14c537e84b1753",
        "scene": scene,
        "captcha_type": 1,
        "image_version": "",
        "captcha_extra_info": {"tracking_id": tracking} if tracking else None,
        "captcha_id": "",
    }
    body = {"encrypted_data": aes_enc(p, True)}
    try:
        r = s.post("https://shopee.co.id/api/v4/anti_fraud/captcha/generate",
                   json=body, timeout=40)
        j = r.json()
        err = j.get("error")
        log(f"\n[{scene}] {r.status_code} error={err}")
        if j.get("encrypted_data"):
            d = aes_dec(j["encrypted_data"], True)
            log(f"  ✅ DECRYPT: {json.dumps(d)[:350]}")
        else:
            log(f"  plain: {json.dumps(j)[:250]}")
    except Exception as e:
        log(f"\n[{scene}] ERR {str(e)[:70]}")
