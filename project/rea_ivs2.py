# -*- coding: utf-8 -*-
"""rea_ivs2.py — RE lengkap IVS: methods -> select -> verify password/pin.

Target: temukan endpoint + body untuk:
  - PASSWORD   (type 2)  -> verifikasi password akun
  - SHOPEEPAY  (type 10) -> verifikasi PIN ShopeePay
  - OTP        (type 1)

Alur dari bundle (ivs_js/027.js):
  /anti_fraud/ivs/methods        {event, u_token}       -> [{type, v_token}]
  /anti_fraud/ivs/method/select  {event, u_token, method, v_token}
  /anti_fraud/ivs/token/verify   {event, u_token, v_token, ...}
"""
import sys
import json
import time

sys.path.insert(0, "/root/shopee-verify")
import changenumfast as c

CK = "/root/shopee-verify/ck_new.txt"
PH = "6282374455953"
EV = 2   # enum event yang diterima

IVS_TYPE = {1: "OTP", 2: "PASSWORD", 3: "SHOPEEPAY", 5: "AUTH_LINK",
            6: "EMAIL", 7: "QR", 8: "EMAIL_LINK", 10: "NEW_SHOPEEPAY_PIN",
            11: "WHATSAPP_LINK", 14: "SECURITY_QUESTIONS",
            15: "SECURITY_EMAIL", 20: "DEVICE_TOKEN", 100: "SKIP"}

ck = open(CK).read().strip()
a = c.Api(ck)


def show(label, r, n=320):
    print(f"  {label}")
    print(f"    err={r.get('error')} data={json.dumps(r.get('data'))[:n]}")
    return r


print("=" * 68)
print("1. INIT_V2 → ivs_utoken")
print("=" * 68)
ini = a.post("/api/v4/account/management/change_phone_init_v2",
             {"phone": PH, "seq_no": None})
d = ini.get("data") or {}
ut = d.get("ivs_utoken") or ""
print(f"  err={ini.get('error')} ivs_required={d.get('ivs_required')} "
      f"utoken={len(ut)}B")

print("\n" + "=" * 68)
print("2. IVS/METHODS — semua method tersedia")
print("=" * 68)
m = a.post("/api/v4/anti_fraud/ivs/methods", {"event": EV, "u_token": ut})
methods = m.get("data") or []
print(f"  err={m.get('error')} jumlah method={len(methods)}")
for i, mm in enumerate(methods):
    t = mm.get("type")
    print(f"    [{i}] type={t} ({IVS_TYPE.get(t,'?')}) "
          f"v_token={len(mm.get('v_token') or '')}B")

if not methods:
    print("  ❌ tidak ada method. Stop.")
    sys.exit(1)

print("\n" + "=" * 68)
print("3. IVS/METHOD/SELECT — pilih tiap method")
print("=" * 68)
for mm in methods:
    t = mm.get("type")
    vt = mm.get("v_token")
    for body_name, body in [
        ("event,u_token,method,v_token",
         {"event": EV, "u_token": ut, "method": t, "v_token": vt}),
        ("event,u_token,type,v_token",
         {"event": EV, "u_token": ut, "type": t, "v_token": vt}),
        ("event,method,v_token",
         {"event": EV, "method": t, "v_token": vt}),
    ]:
        r = a.post("/api/v4/anti_fraud/ivs/method/select", body)
        e = r.get("error")
        if e == 0:
            show(f"type={t} ({IVS_TYPE.get(t,'?')}) body=[{body_name}]", r, 500)
            break
        elif body_name.startswith("event,u_token,method"):
            show(f"type={t} body=[{body_name}]", r, 200)

print("\n" + "=" * 68)
print("4. COBA VERIFY PASSWORD (tanpa password dulu, lihat error shape)")
print("=" * 68)
for path in ["/api/v4/account/management/verify_password",
             "/api/v4/account/basic/verify_password",
             "/api/v4/account/management/verify_payment",
             "/api/v4/anti_fraud/ivs/token/verify"]:
    r = a.post(path, {"password": "", "event": EV, "u_token": ut})
    show(path.split("/")[-1], r, 220)
