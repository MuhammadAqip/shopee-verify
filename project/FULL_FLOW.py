# -*- coding: utf-8 -*-
"""FULL_FLOW.py — ganti nomor akun 15539296185 -> 6285736070693.

Cookie bersih (ck_clean.txt) + captcha solve via SadCaptcha (shopee_v6).
"""
import sys, json, hashlib, urllib.request, urllib.error
sys.path.insert(0, "/root/shopee-verify")

PHONE = "6285736070693"
PW = "qwertyui123"
CK = open("/root/shopee-verify/ck_clean.txt").read().strip()
CSRF = next(c.split("=", 1)[1] for c in CK.split(";")
            if c.strip().startswith("csrftoken="))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
BASE = "https://shopee.co.id"


def req(path, body=None, method="POST", ref="https://shopee.co.id/verify/ivs"):
    h = {"User-Agent": UA, "Cookie": CK, "Accept": "application/json",
         "x-api-source": "pc", "x-requested-with": "XMLHttpRequest",
         "x-csrftoken": CSRF, "x-shopee-language": "id", "Referer": ref}
    data = None
    if body is not None:
        h["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=30) as x:
            return json.loads(x.read())
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read())
        except Exception: return {"http": e.code}
    except Exception as e:
        return {"err": str(e)}


def show(tag, r, n=180):
    print(f"{tag}: {json.dumps(r, ensure_ascii=False)[:n]}")
    return r


print("=== 0. account ===")
acc = req("/api/v4/account/basic/get_account_info", None, "GET")
d = acc.get("data") or {}
show("account", acc, 140)
if acc.get("error") != 0:
    sys.exit("cookie mati")

print("\n=== 1. change_phone_init_v2 ===")
r1 = req("/api/v4/account/management/change_phone_init_v2", {},
         ref="https://shopee.co.id/user/account/profile")
show("init", r1)
dd = r1.get("data") or {}
if r1.get("error") != 0:
    sys.exit("init gagal")
cp, ut = dd.get("change_phone_token"), dd.get("ivs_utoken")

print("\n=== 2. ivs/methods {event:2,u_token} ===")
r2 = req("/api/v4/anti_fraud/ivs/methods", {"event": 2, "u_token": ut})
methods = r2.get("data") or []
show("methods", r2, 110)
if not methods:
    sys.exit("methods gagal")
for m in methods:
    print(f"   type={m['type']} v_token_len={len(m['v_token'])}")

print("\n=== 4. verify_password ===")
ph = hashlib.sha256(hashlib.md5(PW.encode()).hexdigest().encode()).hexdigest()
r4 = req("/api/v4/account/management/verify_password", {"password": ph},
         ref="https://shopee.co.id/user/account/profile")
rt = (r4.get("data") or {}).get("rc_token")
show("password", r4, 100)
if not rt:
    sys.exit("password gagal")

print("\n=== 5. ivs/token/verify ===")
sig = None
for m in methods:
    body = {"method_name": m["type"], "event": 2, "u_token": ut,
            "r_token": rt, "v_token": m["v_token"],
            "shopee_df": {"security_device_fingerprint": ""},
            "misc": {"seed": None, "operation": 0}}
    r5 = req("/api/v4/anti_fraud/ivs/token/verify", body)
    print(f"   type={m['type']}: error={r5.get('error')} sig={bool(r5.get('signature'))}")
    if r5.get("error") == 0 and r5.get("signature"):
        sig = r5["signature"]
        print("   ✅ SIGNATURE:", sig[:60], "…")
        json.dump({"type": m["type"], "signature": sig, "cp": cp, "ut": ut,
                   "rt": rt, "v_token": m["v_token"]},
                  open("/root/shopee-verify/READY.json", "w"))
        break
if not sig:
    sys.exit("ivs verify gagal")

print("\n=== 6. precheck_v2 nomor baru ===")
r6 = req("/api/v4/account/management/change_phone_precheck_v2",
         {"new_phone": PHONE, "change_phone_token": cp},
         ref="https://shopee.co.id/user/account/profile")
show("precheck", r6)

print("\n=== 7. otp/get_settings_v2 ===")
r7 = req("/api/v4/otp/get_settings_v2", {"operation": 0, "phone": PHONE},
         ref="https://shopee.co.id/user/account/profile")
show("channels", r7)
ch = (r7.get("data") or {}).get("available_channels") or []
print("   available:", ch, "(1=SMS 2=WA 3=? )")
