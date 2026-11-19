# -*- coding: utf-8 -*-
"""rea_ivs.py — RE endpoint IVS Shopee: temukan enum `event` + body yang benar.

Langkah:
  1. init_v2 -> ivs_utoken
  2. coba banyak nilai `event` di /anti_fraud/ivs/methods
  3. kalau dapat, lanjut select method -> verify password/pin
"""
import sys
import json
import itertools

sys.path.insert(0, "/root/shopee-verify")
import changenumfast as c

CK = "/root/shopee-verify/ck_new.txt"
PH = "6282374455953"

ck = open(CK).read().strip()
a = c.Api(ck)

print("=" * 64)
print("STEP 1 — init_v2")
print("=" * 64)
ini = a.post("/api/v4/account/management/change_phone_init_v2",
             {"phone": PH, "seq_no": None})
d = ini.get("data") or {}
ut = d.get("ivs_utoken") or ""
print(f"err={ini.get('error')} ivs_required={d.get('ivs_required')} "
      f"utoken={len(ut)}B")

CANDIDATES = [
    "AccountChangePhone", "AccountChangePhoneNumber", "AccountChangePhoneNumberV2",
    "ChangePhone", "change_phone", "account_change_phone",
    "AccountSetPhone", "AccountUpdatePhone", "UpdatePhone",
    "PhoneChange", "ChangePhoneNumber", "Login", "AccountLogin",
    "AccountVerifyPhone", "IVSChangePhone", "IvsChangePhone",
    "AccountBindPhone", "BindPhone", "AccountAddPhone",
]
NUMS = list(range(1, 40)) + [100, 101, 102, 200, 201, 500, 501, 502, 503]

print("\n" + "=" * 64)
print("STEP 2 — cari nilai `event` yang diterima ivs/methods")
print("=" * 64)

hits = []
for ev in CANDIDATES + NUMS:
    m = a.post("/api/v4/anti_fraud/ivs/methods", {"event": ev, "u_token": ut})
    err = m.get("error")
    data = m.get("data")
    if err == 0 and data:
        print(f"  ✅ event={ev!r} → {json.dumps(data)[:400]}")
        hits.append((ev, data))
        break
    elif err not in (211, 49900000, None):
        print(f"  ?  event={ev!r} → err={err} {m.get('error_msg','')[:60]}")
    if isinstance(ev, int) and ev > 40 and err == 211:
        pass

if not hits:
    print("\n  ❌ tidak ada event yang diterima.")
    print("  Cek: mungkin butuh header x-app-type atau ivs_utoken berbeda.")

print("\n" + "=" * 64)
print("HASIL:")
for ev, data in hits:
    print(f"  event={ev!r}")
    print(f"  {json.dumps(data, indent=2)[:800]}")
