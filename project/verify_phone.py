# -*- coding: utf-8 -*-
"""verify_phone.py — akun email -> pasang nomor pertama kali.

init_v2 (lihat state) -> tentukan flow -> otp settings -> send -> verify -> commit
"""
import sys, json, hashlib, urllib.request, urllib.error, ssl

CK_FILE = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_email.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6285736070693"
PW = sys.argv[3] if len(sys.argv) > 3 else ""

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
    data = None
    if body is not None:
        h["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    r = urllib.request.Request("https://shopee.co.id" + path, data=data,
                               method=method, headers=h)
    try:
        with _OP.open(r, timeout=35) as x:
            return json.loads(x.read())
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read())
        except Exception: return {"http": e.code}
    except Exception as e:
        return {"err": str(e)[:90]}


print(f"cookie : {CK_FILE}")
print(f"nomor  : {NEWPHONE}\n")

print("=== 0. account ===")
a = api("/api/v4/account/basic/get_account_info", None, "GET",
        ref="https://shopee.co.id/")
print(json.dumps(a, ensure_ascii=False)[:400])
if a.get("error") != 0:
    sys.exit("\n>> cookie mati")
D = a.get("data") or {}
print(f"   uid={D.get('userid')} user={D.get('username')} "
      f"phone={D.get('phone')} email={D.get('email')} "
      f"phone_verified={D.get('phone_verified')}")

print("\n=== 1. init_v2 (state apa) ===")
r1 = api("/api/v4/account/management/change_phone_init_v2", {})
print(json.dumps(r1, ensure_ascii=False)[:300])
d1 = r1.get("data") or {}
for k in ("change_phone_token", "ivs_utoken", "ivs_required",
          "is_delayed", "has_phone_pix_key"):
    v = d1.get(k)
    print(f"   {k}: {str(v)[:50]}{'...' if isinstance(v, str) and len(v) > 50 else ''}")
cp, ut = d1.get("change_phone_token"), d1.get("ivs_utoken")

print("\n=== 2. otp/get_settings_v2 ===")
r2 = api("/api/v4/account/management/otp/get_settings_v2",
         {"operation": 0, "phone": NEWPHONE})
print(json.dumps(r2, ensure_ascii=False)[:400])

print("\n=== 3. cek endpoint verify/initial ===")
for ep in ("/api/v4/account/management/change_phone_precheck_v2",
           "/api/v4/account/basic/check_phone_exist"):
    body = {"new_phone": NEWPHONE}
    if cp:
        body["change_phone_token"] = cp
    r = api(ep, body)
    print(f"  {ep.split('/')[-1]}: {json.dumps(r, ensure_ascii=False)[:220]}")
