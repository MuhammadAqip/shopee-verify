# -*- coding: utf-8 -*-
"""verify_email.py — akun email-only (phone kosong).

type=8 EmailLink, type=6 Email. Tanpa password.
"""
import sys, json, urllib.request, urllib.error, ssl

CK_FILE = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_1445.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6285736070693"
CK = open(CK_FILE).read().strip()
CSRF = next((c.split("=", 1)[1] for c in CK.split(";")
             if c.strip().startswith("csrftoken=")), "")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"

_ct = ssl.create_default_context()
_ct.check_hostname = False
_ct.verify_mode = ssl.CERT_NONE
_OP = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}),
    urllib.request.HTTPSHandler(context=_ct))


def api(path, body=None, method="POST",
        ref="https://shopee.co.id/user/account/profile"):
    h = {"User-Agent": UA, "Cookie": CK, "Accept": "application/json",
         "x-api-source": "pc", "x-requested-with": "XMLHttpRequest",
         "x-shopee-language": "id", "Referer": ref, "x-csrftoken": CSRF,
         "Origin": "https://shopee.co.id", "x-app-type": "undefined"}
    d = None
    if body is not None:
        h["Content-Type"] = "application/json"
        d = json.dumps(body).encode()
    r = urllib.request.Request("https://shopee.co.id" + path, data=d,
                               method=method, headers=h)
    try:
        with _OP.open(r, timeout=35) as x:
            return json.loads(x.read())
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read())
        except Exception: return {"http": e.code}
    except Exception as e:
        return {"err": str(e)[:80]}


print("=== 1. init_v2 ===")
r1 = api("/api/v4/account/management/change_phone_init_v2", {})
d1 = r1.get("data") or {}
cp, ut = d1.get("change_phone_token"), d1.get("ivs_utoken")
print("error:", r1.get("error"), "cp:", bool(cp), "ut:", bool(ut))
if not cp:
    sys.exit(1)

print("\n=== 2. ivs/methods {event:2} ===")
r2 = api("/api/v4/anti_fraud/ivs/methods", {"event": 2, "u_token": ut})
ms = r2.get("data") or []
NAMES = {1: "OTP", 2: "Password", 3: "ShopeePay", 5: "AuthenticationLink",
         6: "Email", 7: "Qr", 8: "EmailLink", 10: "NewShopeePayPin",
         11: "WhatsAppLink", 14: "SecurityQuestions"}
print("error:", r2.get("error"))
for m in ms:
    print(f"   type={m['type']} ({NAMES.get(m['type'],'?')}) len={len(m['v_token'])}")
if not ms:
    sys.exit(1)

print("\n=== 3. pilih & select tiap method ===")
for m in ms:
    t = m["type"]
    sel = api("/api/v4/anti_fraud/ivs/method/select",
              {"method_name": t, "event": 2, "u_token": ut,
               "v_token": m["v_token"], "misc": {"operation": 0}})
    ds = sel.get("data") or {}
    print(f"   type={t} {NAMES.get(t,'?')}: error={sel.get('error')} "
          f"data={json.dumps(ds, ensure_ascii=False)[:140]}")

    # EmailLink / Email: coba langsung ke token/verify (tanpa password)
    if t in (6, 8):
        tv = api("/api/v4/anti_fraud/ivs/token/verify",
                 {"method_name": t, "event": 2, "u_token": ut,
                  "r_token": "", "v_token": m["v_token"],
                  "shopee_df": {"security_device_fingerprint": ""},
                  "misc": {"seed": None, "operation": 0}})
        print(f"      token/verify: error={tv.get('error')} "
              f"sig={bool(tv.get('signature'))}")
        if tv.get("error") == 0 and tv.get("signature"):
            json.dump({"type": t, "signature": tv["signature"], "cp": cp,
                       "ut": ut, "v_token": m["v_token"]},
                      open("/root/shopee-verify/READY_EMAIL.json", "w"))
            print("      ✅ SIGNATURE EMAIL:", tv["signature"][:60])
