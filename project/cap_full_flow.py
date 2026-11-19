"""cap_full_flow.py — flow captcha LENGKAP, semua plaintext.

Schema ASLI dari browser capture:
  POST /captcha/get_config  {app_key, scene, tracking_id}   <- PLAINTEXT
  POST /captcha/generate    {encrypted_data}                 <- AES

app_key get_config = f9ffc83459897a13dd14c537e84b1753
scene              = crawler_item

Uji get_config dengan client_id + cookie lengkap.
"""
import json, sys, base64, hashlib, os
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1553.txt"
PROXY = "http://127.0.0.1:18080"
KEY = b"dRgUkXp2r5u8x/A?D(G+KbPeShVmYq3t"
APPKEY = "f9ffc83459897a13dd14c537e84b1753"
GEN_KEY = "TSS.PC"
SCENE = "crawler_item"


def log(*a):
    print(*a, flush=True)


def evp(pw, salt):
    d, prev = b"", b""
    while len(d) < 48:
        prev = hashlib.md5(prev + pw + salt).digest()
        d += prev
    return d[:32], d[32:48]


def enc(o):
    salt = os.urandom(8)
    k, iv = evp(KEY, salt)
    ct = AES.new(k, AES.MODE_CBC, iv).encrypt(
        pad(json.dumps(o, separators=(",", ":")).encode(), 16))
    return base64.b64encode(b"Salted__" + salt + ct).decode()


def dec(b):
    try:
        raw = base64.b64decode(b)
        if not raw.startswith(b"Salted__"):
            return {"_nohdr": raw[:60]}
        k, iv = evp(KEY, raw[8:16])
        return json.loads(unpad(AES.new(k, AES.MODE_CBC, iv).decrypt(raw[16:]), 16))
    except Exception as e:
        return {"_err": str(e)[:60]}


ck = open(CK).read().strip()
cookies = {p.split("=", 1)[0].strip(): p.split("=", 1)[1].strip()
           for p in ck.split(";") if "=" in p}
cid = cookies.get("SPC_CLIENTID", "")
trk = open("TRACKING.txt").read().strip() if os.path.exists("TRACKING.txt") else ""

s = requests.Session()
s.cookies.update(cookies)
s.proxies = {"http": PROXY, "https": PROXY}
s.headers.update({
    "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"),
    "x-api-source": "pc", "af-ac-enc-dat": "0123456789abcdef",
    "x-sz-sdk-version": "1.12.45", "x-requested-with": "XMLHttpRequest",
    "referer": f"https://shopee.co.id/verify/captcha",
    "accept": "application/json", "content-type": "application/json"})
log(f"client_id={cid} tracking={len(trk)}B")

# === 1. get_config PLAINTEXT (pola browser) ===
log("\n=== get_config (plaintext, pola browser) ===")
for body in (
    {"app_key": APPKEY, "scene": SCENE, "tracking_id": trk},
    {"app_key": APPKEY, "scene": SCENE, "client_id": cid, "tracking_id": trk},
    {"app_key": GEN_KEY, "scene": SCENE, "client_id": cid, "tracking_id": trk},
):
    r = s.post("https://shopee.co.id/api/v4/anti_fraud/captcha/get_config",
               json=body, timeout=40)
    j = r.json()
    log(f"  keys={list(body.keys())} -> {r.status_code} err={j.get('error')}")
    if j.get("error") == 0 or j.get("tracking_id"):
        log(f"  ✅ {json.dumps(j)[:400]}")
        if j.get("tracking_id"):
            trk = j["tracking_id"]
            open("TRACKING2.txt", "w").write(trk)
            log(f"  ★ tracking baru {len(trk)}B")
        break

# === 2. generate ===
log("\n=== generate ===")
p = {"app_key": GEN_KEY, "scene": SCENE, "captcha_type": 1, "image_version": "",
     "client_id": cid,
     "captcha_extra_info": {"tracking_id": trk} if trk else None,
     "captcha_id": ""}
r = s.post("https://shopee.co.id/api/v4/anti_fraud/captcha/generate",
           json={"encrypted_data": enc(p)}, timeout=40)
j = r.json()
log(f"  {r.status_code} err={j.get('error')}")
if j.get("encrypted_data"):
    d = dec(j["encrypted_data"])
    log(f"  ✅ {json.dumps(d)[:500]}")
    if d.get("error") == 0 and d.get("data", {}).get("captcha_id"):
        log("  🎉 CAPTCHA BARU DIDAPAT")
        json.dump(d["data"], open("CAPTCHA2.json", "w"), indent=1)
else:
    log(f"  plain: {json.dumps(j)[:250]}")
