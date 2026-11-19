"""cap_gen2.py — lengkapi params: tracking_id dari get_config + client_id asli.

Error 31500000 kemungkinan = PARAM_INVALID karena:
  - tracking_id None
  - client_id tidak dikirim (wajib dari get_config)

Ambil get_config dengan POST + app_key encrypted juga.
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
    d = b""
    prev = b""
    while len(d) < 48:
        prev = hashlib.md5(prev + pw + salt).digest()
        d += prev
    return d[:32], d[32:48]


def enc(obj):
    salt = os.urandom(8)
    key, iv = evp(KEY_LIVE, salt)
    pt = json.dumps(obj, separators=(",", ":")).encode()
    ct = AES.new(key, AES.MODE_CBC, iv).encrypt(pad(pt, 16))
    return base64.b64encode(b"Salted__" + salt + ct).decode()


def dec(b64):
    try:
        raw = base64.b64decode(b64)
        if not raw.startswith(b"Salted__"):
            return {"_nohdr": b64[:80]}
        key, iv = evp(KEY_LIVE, raw[8:16])
        return json.loads(unpad(AES.new(key, AES.MODE_CBC, iv)
                                .decrypt(raw[16:]), 16))
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

log(f"client_id: {client_id}")

# 1. get_config — coba GET dan POST encrypted
log("\n=== get_config (GET) ===")
r = s.get("https://shopee.co.id/api/v4/anti_fraud/captcha/get_config", timeout=40)
log(f"  {r.status_code} {r.text[:400]}")

log("\n=== get_config (POST encrypted) ===")
cfg_body = {"encrypted_data": enc({"app_key": APPKEY, "scene": "captcha",
                                   "client_id": client_id})}
r2 = s.post("https://shopee.co.id/api/v4/anti_fraud/captcha/get_config",
            json=cfg_body, timeout=40)
log(f"  {r2.status_code} {r2.text[:400]}")
if r2.json().get("encrypted_data"):
    log(f"  ✅ {json.dumps(dec(r2.json()['encrypted_data']))[:400]}")

# 2. ambil tracking dari semua sumber
tracking = None
for resp in (r, r2):
    try:
        j = resp.json()
        d = j.get("data") or j
        tracking = d.get("tracking_id") or tracking
        if j.get("encrypted_data"):
            dd = dec(j["encrypted_data"])
            tracking = dd.get("tracking_id") or tracking
    except Exception:
        pass
log(f"\ntracking: {str(tracking)[:60]}")

# 3. generate dengan client_id + tracking
if tracking:
    log("\n=== generate (full params) ===")
    p = {"app_key": APPKEY, "scene": "captcha", "captcha_type": 1,
         "image_version": "", "client_id": client_id,
         "captcha_extra_info": {"tracking_id": tracking}, "captcha_id": ""}
    r3 = s.post("https://shopee.co.id/api/v4/anti_fraud/captcha/generate",
                json={"encrypted_data": enc(p)}, timeout=40)
    log(f"  {r3.status_code} {r3.text[:300]}")
    if r3.json().get("encrypted_data"):
        d = dec(r3.json()["encrypted_data"])
        log(f"  ✅ DECRYPT: {json.dumps(d)[:600]}")
else:
    log("\n!! tracking_id tidak didapat")
