# -*- coding: utf-8 -*-
"""captcha_flow.py — generate + verify Shopee captcha via API murni.

Kunci dari ivs_js/063.js:
  LIVE key : "dRgUkXp2r5u8x/A?D(G+KbPeShVmYq3t"
  TEST key : "5v8y/B?E(H+MbPeShVmYq3t6w9z$C&F)"

Format: CryptoJS.AES.encrypt(JSON.stringify(obj), key).toString()
        = OpenSSL "Salted__" format, AES-256-CBC, iv = key

generate: POST /api/v4/anti_fraud/captcha/generate
  { encrypted_data: <AES({app_key, scene, captcha_type, image_version,
                          captcha_extra_info:{tracking_id}, captcha_id})> }
  -> { encrypted_data: <AES({error, ...image data...})> }

verify:   POST /api/v4/anti_fraud/captcha/verify
  { encrypted_data: <AES({app_key, scene, captcha_type, captcha_answer,
                          user_action, phone/email/username,
                          captcha_extra_info:{tracking_id}})>,
    encrypted_security_data: <...>, dfp_token: <...> }
"""
import json, sys, base64, hashlib, secrets, urllib.request, urllib.error

APP_KEY = "f9ffc83459897a13dd14c537e84b1753"
KEY_LIVE = b"dRgUkXp2r5u8x/A?D(G+KbPeShVmYq3t"
KEY_TEST = b"5v8y/B?E(H+MbPeShVmYq3t6w9z$C&F)"

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad, unpad
except ImportError:
    print("pip install pycryptodome")
    sys.exit(1)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")


def evp_encrypt(obj, key):
    """CryptoJS.AES.encrypt(obj, key).toString() — OpenSSL Salted format."""
    pt = json.dumps(obj, separators=(",", ":")).encode()
    salt = secrets.token_bytes(8)
    # EVP_BytesToKey: iterative md5 sampai cukup key+iv
    d, prev = b"", b""
    while len(d) < 48:
        prev = hashlib.md5(prev + key + salt).digest()
        d += prev
    k, iv = d[:32], d[32:48]
    ct = AES.new(k, AES.MODE_CBC, iv).encrypt(pad(pt, 16))
    return base64.b64encode(b"Salted__" + salt + ct).decode()


def evp_decrypt(b64, key):
    raw = base64.b64decode(b64)
    if raw[:8] != b"Salted__":
        raise ValueError("not salted")
    salt, ct = raw[8:16], raw[16:]
    d, prev = b"", b""
    while len(d) < 48:
        prev = hashlib.md5(prev + key + salt).digest()
        d += prev
    k, iv = d[:32], d[32:48]
    return json.loads(unpad(AES.new(k, AES.MODE_CBC, iv).decrypt(ct), 16))


def call(path, body, ck=None, csrf=None):
    h = {"User-Agent": UA, "X-API-SOURCE": "pc",
         "X-Requested-With": "XMLHttpRequest",
         "Referer": "https://shopee.co.id/", "Accept": "application/json",
         "Content-Type": "application/json", "X-Shopee-Language": "id"}
    if ck:
        h["Cookie"] = ck
    if csrf:
        h["X-CSRFToken"] = csrf
    d = json.dumps(body).encode()
    req = urllib.request.Request("https://shopee.co.id" + path, data=d,
                                 headers=h, method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=45)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}
    except Exception as ex:
        return 0, {"exc": str(ex)[:60]}


CKF = sys.argv[1] if len(sys.argv) > 1 else "ck_1553.txt"
ck = open(CKF).read().strip()
csrf = ""
for p in ck.split(";"):
    if p.strip().startswith("csrftoken="):
        csrf = p.split("=", 1)[1].strip()

print("=== 1. GENERATE CAPTCHA ===")
for keyname, K in (("LIVE", KEY_LIVE), ("TEST", KEY_TEST)):
    params = {"app_key": APP_KEY, "scene": "ivs", "captcha_type": 0,
              "image_version": "", "captcha_id": ""}
    enc = evp_encrypt(params, K)
    s, j = call("/api/v4/anti_fraud/captcha/generate",
                {"encrypted_data": enc}, ck, csrf)
    print(f"  [{keyname}] HTTP={s} err={j.get('error')} keys={list(j)[:6]}")
    ed = j.get("encrypted_data")
    if ed:
        try:
            dec = evp_decrypt(ed, K)
            print(f"      decrypted: {json.dumps(dec)[:250]}")
            open(f"captcha_{keyname}.json", "w").write(json.dumps(dec))
        except Exception as ex:
            print(f"      decrypt gagal: {ex}")
    else:
        print(f"      raw: {json.dumps(j)[:200]}")
