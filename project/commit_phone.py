# -*- coding: utf-8 -*-
"""commit_phone.py — langkah 6-10 pakai signature dari IVS UI.

Bentuk URL: /verify/ivs selesai -> redirect ke `next` dengan
?signature=...&ivs_method=2&state=...&ivs_flow_no=...
Signature itu dipakai precheck + commit.
"""
import sys, json, ssl, urllib.request, urllib.error, urllib.parse

CK_FILE = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_5th_solved.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6285736070693"
VCODE = sys.argv[3] if len(sys.argv) > 3 else ""
READY = sys.argv[4] if len(sys.argv) > 4 else "/root/shopee-verify/READY_PW.json"

CK = open(CK_FILE).read().strip()
CSRF = next((c.split("=", 1)[1] for c in CK.split(";")
             if c.strip().startswith("csrftoken=")), "")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"

_ct = ssl.create_default_context(); _ct.check_hostname = False
_ct.verify_mode = ssl.CERT_NONE
_OP = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}),
    urllib.request.HTTPSHandler(context=_ct))


def api(path, body=None, method="POST",
        ref="https://shopee.co.id/user/account/profile"):
    h = {"User-Agent": UA, "Cookie": CK, "Accept": "application/json",
         "x-api-source": "pc", "x-requested-with": "XMLHttpRequest",
         "x-shopee-language": "id", "Referer": ref, "x-csrftoken": CSRF,
         "Origin": "https://shopee.co.id"}
    d = None
    if body is not None:
        h["Content-Type"] = "application/json"; d = json.dumps(body).encode()
    r = urllib.request.Request("https://shopee.co.id" + path, data=d,
                               method=method, headers=h)
    try:
        with _OP.open(r, timeout=35) as x: return json.loads(x.read())
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read())
        except Exception: return {"http": e.code}
    except Exception as e: return {"err": str(e)[:80]}


R = json.load(open(READY)) if __import__("os").path.exists(READY) else {}
SIG = R.get("signature")
METHOD = R.get("type", 2)
STATE = R.get("state")
FLOW = R.get("ivs_flow_no")
CP = R.get("cp")
print(f"sig: {bool(SIG)} method={METHOD} state={STATE} flow={FLOW} cp={bool(CP)}")
if not SIG:
    sys.exit(">> butuh READY_PW.json berisi signature")

print("\n=== 6. precheck (dengan signature) ===")
tries = [
    {"new_phone": NEWPHONE, "change_phone_token": CP,
     "ivs_signature": SIG, "ivs_method": METHOD},
    {"new_phone": NEWPHONE, "ivs_signature": SIG, "ivs_method": METHOD},
    {"new_phone": NEWPHONE, "change_phone_token": CP},
]
ok6 = None
for b in tries:
    r = api("/api/v4/account/management/change_phone_precheck_v2", b)
    print(f"  keys={list(b)} -> error={r.get('error')} "
          f"{json.dumps(r.get('data'), ensure_ascii=False)[:150]}")
    if r.get("error") == 0:
        ok6 = r
        break

if not ok6:
    print(">> precheck gagal, coba endpoint lain")

print("\n=== 7. otp/get_settings_v2 ===")
for b in [{"operation": 0, "phone": NEWPHONE, "change_phone_token": CP},
          {"operation": 0, "phone": NEWPHONE},
          {"operation": 0, "phone": NEWPHONE, "ivs_signature": SIG}]:
    r = api("/api/v4/account/management/otp/get_settings_v2", b)
    e = r.get("error")
    print(f"  {list(b)} -> error={e} {json.dumps(r.get('data'), ensure_ascii=False)[:180]}")
    if e == 0:
        ch = (r.get("data") or {}).get("available_channels") or []
        print("   channels:", ch)
        break

print("\n=== 8. send_vcode ===")
for b in [{"phone": NEWPHONE, "operation": 0, "change_phone_token": CP,
           "ivs_signature": SIG, "ivs_method": METHOD},
          {"phone": NEWPHONE, "operation": 0},
          {"phone": NEWPHONE, "operation": 0, "change_phone_token": CP}]:
    r = api("/api/v4/account/management/otp/send_vcode", b)
    e = r.get("error")
    print(f"  {list(b)} -> error={e} {json.dumps(r, ensure_ascii=False)[:200]}")
    if e == 0:
        break

if VCODE:
    print("\n=== 9. verify_vcode ===")
    r = api("/api/v4/account/management/otp/verify_vcode",
            {"phone": NEWPHONE, "vcode": VCODE, "operation": 0})
    print(f"  error={r.get('error')} {json.dumps(r, ensure_ascii=False)[:250]}")
    vt = (r.get("data") or {}).get("vcode_token")
    if vt:
        print("\n=== 10. commit_v2 ===")
        r10 = api("/api/v4/account/management/change_phone_commit_v2",
                  {"change_phone_token": CP, "new_phone": NEWPHONE,
                   "vcode_token": vt, "ivs_signature": SIG,
                   "ivs_method": METHOD})
        print(f"  error={r10.get('error')} {json.dumps(r10, ensure_ascii=False)[:300]}")
        if r10.get("error") == 0:
            a = api("/api/v4/account/basic/get_account_info", None, "GET",
                    ref="https://shopee.co.id/")
            D = a.get("data") or {}
            print(f"\n🎉 NOMOR: {D.get('phone')} verified={D.get('phone_verified')}")
