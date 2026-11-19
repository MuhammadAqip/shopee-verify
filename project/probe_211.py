# -*- coding: utf-8 -*-
"""probe_211.py — cari parameter yang hilang untuk error 211.

Fokus: shopee_df valid (dari cookie shopee_webUnique_ccd), x-app-type header.
"""
import sys, json, hashlib, urllib.request, urllib.error
sys.path.insert(0, "/root/shopee-verify")

PHONE = "6285736070693"
PW = "qwertyui123"
CK = open("/root/shopee-verify/ck_clean.txt").read().strip()
CSRF = next(c.split("=", 1)[1] for c in CK.split(";")
            if c.strip().startswith("csrftoken="))
FP = next(c.split("=", 1)[1] for c in CK.split(";")
          if c.strip().startswith("shopee_webUnique_ccd="))
FP = urllib.parse.unquote(FP) if hasattr(urllib, "parse") else FP
import urllib.parse
FP = urllib.parse.unquote(FP)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
BASE = "https://shopee.co.id"
print("FP cookie:", FP[:80], "…")


def req(path, body=None, method="POST", ref="https://shopee.co.id/verify/ivs",
        extra=None):
    h = {"User-Agent": UA, "Cookie": CK, "Accept": "application/json",
         "x-api-source": "pc", "x-requested-with": "XMLHttpRequest",
         "x-csrftoken": CSRF, "x-shopee-language": "id", "Referer": ref}
    if extra:
        h.update(extra)
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


acc = req("/api/v4/account/basic/get_account_info", None, "GET")
print("account:", acc.get("error"))
r1 = req("/api/v4/account/management/change_phone_init_v2", {},
         ref="https://shopee.co.id/user/account/profile")
dd = r1.get("data") or {}
cp, ut = dd.get("change_phone_token"), dd.get("ivs_utoken")
r2 = req("/api/v4/anti_fraud/ivs/methods", {"event": 2, "u_token": ut})
methods = r2.get("data") or []
print("methods:", [(m["type"], len(m["v_token"])) for m in methods])
ph = hashlib.sha256(hashlib.md5(PW.encode()).hexdigest().encode()).hexdigest()
r4 = req("/api/v4/account/management/verify_password", {"password": ph},
         ref="https://shopee.co.id/user/account/profile")
rt = (r4.get("data") or {}).get("rc_token")
print("password:", r4.get("error"), "r_token", bool(rt))

m = next((x for x in methods if x["type"] == 2), methods[0])

variants = []
# A: shopee_df = FP asli
variants.append(("shopee_df=REDACTED", {
    "method_name": m["type"], "event": 2, "u_token": ut, "r_token": rt,
    "v_token": m["v_token"], "shopee_df": {"security_device_fingerprint": FP},
    "misc": {"seed": None, "operation": 0}}, {"x-app-type": "undefined"}))
# B: shopee_df string FP
variants.append(("shopee_df=REDACTED", {
    "method_name": m["type"], "event": 2, "u_token": ut, "r_token": rt,
    "v_token": m["v_token"], "shopee_df": FP,
    "misc": {"seed": None, "operation": 0}}, {"x-app-type": "undefined"}))
# C: security_device_fingerprint top-level
variants.append(("fp top-level", {
    "method_name": m["type"], "event": 2, "u_token": ut, "r_token": rt,
    "v_token": m["v_token"], "security_device_fingerprint": FP,
    "misc": {"seed": None, "operation": 0}}, {"x-app-type": "undefined"}))
# D: tanpa x-app-type
variants.append(("no x-app-type", {
    "method_name": m["type"], "event": 2, "u_token": ut, "r_token": rt,
    "v_token": m["v_token"], "shopee_df": {"security_device_fingerprint": FP},
    "misc": {"seed": None, "operation": 0}}, {}))
# E: misc operation=2
variants.append(("op=2", {
    "method_name": m["type"], "event": 2, "u_token": ut, "r_token": rt,
    "v_token": m["v_token"], "shopee_df": {"security_device_fingerprint": FP},
    "misc": {"seed": None, "operation": 2}}, {"x-app-type": "undefined"}))
# F: seed "" bukan None
variants.append(("seed=''", {
    "method_name": m["type"], "event": 2, "u_token": ut, "r_token": rt,
    "v_token": m["v_token"], "shopee_df": {"security_device_fingerprint": FP},
    "misc": {"seed": "", "operation": 0}}, {"x-app-type": "undefined"}))

for lbl, body, hdr in variants:
    r = req("/api/v4/anti_fraud/ivs/token/verify", body, extra=hdr)
    e, s = r.get("error"), bool(r.get("signature"))
    print(f"{lbl:22}: error={e} sig={s}")
    if e == 0 and r.get("signature"):
        print("  ✅ SIGNATURE:", r["signature"][:70], "…")
        json.dump({"type": m["type"], "signature": r["signature"],
                   "cp": cp, "ut": ut, "rt": rt, "v_token": m["v_token"]},
                  open("/root/shopee-verify/READY.json", "w"))
        break
