# -*- coding: utf-8 -*-
"""verify_full.py — akun email-only (phone kosong) -> PASANG NOMOR.

Cookie: hasil gate_solver (punya shopee_webUnique_ccd).
Langkah: init_v2 -> methods(type 8) -> select -> token/verify -> signature
         -> precheck -> otp settings -> send_vcode -> [OTP] -> verify -> commit
"""
import sys, json, time, urllib.request, urllib.error, ssl

CK_FILE = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_1445_solved.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6285736070693"
VCODE = sys.argv[3] if len(sys.argv) > 3 else ""

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
         "Origin": "https://shopee.co.id", "x-app-type": "undefined",
         "x-sz-sdk-version": "1.12.45"}
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


def j(o, n=200):
    return json.dumps(o, ensure_ascii=False)[:n]


print(f"cookie : {CK_FILE}")
print(f"nomor  : {NEWPHONE}")

print("\n=== 0. account ===")
a = api("/api/v4/account/basic/get_account_info", None, "GET",
        ref="https://shopee.co.id/")
D = a.get("data") or {}
print(f"error={a.get('error')} uid={D.get('userid')} user={D.get('username')} "
      f"phone='{D.get('phone')}' verified={D.get('phone_verified')}")
if a.get("error") != 0:
    sys.exit(">> cookie mati")

print("\n=== 1. init_v2 ===")
r1 = api("/api/v4/account/management/change_phone_init_v2", {})
d1 = r1.get("data") or {}
cp, ut = d1.get("change_phone_token"), d1.get("ivs_utoken")
print(f"error={r1.get('error')} cp={bool(cp)} u_token={bool(ut)} "
      f"ivs_required={d1.get('ivs_required')}")
if not cp:
    sys.exit(">> init gagal")

sig = None
if d1.get("ivs_required"):
    print("\n=== 2. ivs/methods ===")
    r2 = api("/api/v4/anti_fraud/ivs/methods", {"event": 2, "u_token": ut})
    ms = r2.get("data") or []
    NAMES = {1: "OTP", 2: "Password", 3: "ShopeePay", 5: "AuthLink",
             6: "Email", 7: "Qr", 8: "EmailLink", 10: "ShopeePayPin",
             11: "WhatsAppLink", 14: "SecurityQuestions"}
    print(f"error={r2.get('error')} n={len(ms)}")
    for m in ms:
        print(f"   type={m['type']} ({NAMES.get(m['type'],'?')}) len={len(m['v_token'])}")
    if not ms:
        sys.exit(">> no methods")

    for m in ms:
        t = m["type"]
        print(f"\n=== 3. select type={t} ===")
        sel = api("/api/v4/anti_fraud/ivs/method/select",
                  {"method_name": t, "event": 2, "u_token": ut,
                   "v_token": m["v_token"], "misc": {"operation": 0}})
        print(f"   error={sel.get('error')} {j(sel.get('data'), 120)}")

        print(f"=== 4. token/verify type={t} ===")
        tv = api("/api/v4/anti_fraud/ivs/token/verify",
                 {"method_name": t, "event": 2, "u_token": ut,
                  "r_token": "", "v_token": m["v_token"],
                  "shopee_df": {"security_device_fingerprint": ""},
                  "misc": {"seed": None, "operation": 0}})
        e = tv.get("error")
        print(f"   error={e} sig={bool(tv.get('signature'))} {j(tv, 120)}")
        if e == 0 and tv.get("signature"):
            sig = tv["signature"]
            json.dump({"type": t, "signature": sig, "cp": cp, "ut": ut,
                       "v_token": m["v_token"]},
                      open("/root/shopee-verify/READY_EMAIL.json", "w"))
            print("   ✅ SIGNATURE:", sig[:60])
            break

if not sig:
    print("\n>> signature belum dapat. Coba lanjut precheck (mungkin ivs opsional)")
else:
    print("\n>> signature OK, lanjut pasang nomor")

print("\n=== 5. precheck_v2 ===")
r5 = api("/api/v4/account/management/change_phone_precheck_v2",
         {"new_phone": NEWPHONE, "change_phone_token": cp})
print(f"error={r5.get('error')} {j(r5, 220)}")

print("\n=== 6. otp/get_settings_v2 (akun email: pakai change_phone_token) ===")
cands = [
    {"operation": 0, "phone": NEWPHONE},
    {"operation": 0, "phone": NEWPHONE, "change_phone_token": cp},
    {"operation": 0, "phone": NEWPHONE, "scene": "change_phone"},
]
for b in cands:
    r6 = api("/api/v4/account/management/otp/get_settings_v2", b)
    print(f"  {j(b,60)} -> error={r6.get('error')} {j(r6.get('data'),160)}")
    if r6.get("error") == 0:
        ch = (r6.get("data") or {}).get("available_channels") or []
        print("   channels:", ch)
        break

print("\n=== 7. send_vcode ===")
r7 = api("/api/v4/account/management/otp/send_vcode",
         {"phone": NEWPHONE, "operation": 0, "change_phone_token": cp})
print(f"error={r7.get('error')} {j(r7, 240)}")

if VCODE:
    print("\n=== 8. verify_vcode ===")
    r8 = api("/api/v4/account/management/otp/verify_vcode",
             {"phone": NEWPHONE, "vcode": VCODE, "operation": 0})
    print(f"error={r8.get('error')} {j(r8, 240)}")
    vt = (r8.get("data") or {}).get("vcode_token")
    if vt and sig:
        print("\n=== 9. commit_v2 ===")
        md = json.load(open("/root/shopee-verify/READY_EMAIL.json")) if sig else {}
        r9 = api("/api/v4/account/management/change_phone_commit_v2",
                 {"change_phone_token": cp, "new_phone": NEWPHONE,
                  "vcode_token": vt, "ivs_signature": sig,
                  "ivs_method": md.get("type", 8)})
        print(f"error={r9.get('error')} {j(r9, 300)}")
        if r9.get("error") == 0:
            print("\n🎉 NOMOR TERPASANG")
            ac = api("/api/v4/account/basic/get_account_info", None, "GET",
                     ref="https://shopee.co.id/")
            print("verify:", j((ac.get("data") or {}), 200))
