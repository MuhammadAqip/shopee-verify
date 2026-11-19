# -*- coding: utf-8 -*-
"""test_real_request.py — uji request bersih (tanpa header palsu).

Membandingkan hasil untuk semua akun di pool:
  - get_settings_v2 op 0 / 23 / 18
  - health
Kalau header palsu adalah penyebabnya, akun yang tadinya 90309999
sekarang harus lolos (minimal op 0).
"""
import sys
import glob
import json

sys.path.insert(0, "/root/shopee-verify")
import changenumfast as c

PH = "6282374455953"
files = ["/root/shopee-verify/test_ck.txt",
         "/root/shopee-verify/ck_new.txt",
         "/root/shopee-verify/ck_1659.txt"]

print("=" * 70)
print("UJI REQUEST BERSIH (tanpa af-ac-enc-dat / x-sap-ri palsu)")
print("=" * 70)
print(f"proxy: {c.proxy_url()}")
print(f"OP   : {c.OP}   chain: {c.OP_CHAIN}")

for f in files:
    try:
        ck = open(f).read().strip()
    except Exception:
        continue
    a = c.Api(ck)
    acc = a.get("/api/v4/account/basic/get_account_info")
    user = (acc.get("data") or {}).get("username") or f"err{acc.get('error')}"
    print(f"\n--- {f.split('/')[-1]}  user={user} ---")

    print("  headers terkirim:", sorted(a.s.headers.keys()))

    ini = a.post("/api/v4/account/management/change_phone_init_v2",
                 {"phone": PH, "seq_no": None})
    d = ini.get("data") or {}
    print(f"  init_v2 : err={ini.get('error')} ivs={d.get('ivs_required')} "
          f"cp={len(d.get('change_phone_token') or '')}B")

    for op in (0, 23, 18):
        s = a.post("/api/v4/otp/get_settings_v2",
                   {"operation": op, "phone": PH,
                    "supported_channels": [1, 2, 3],
                    "support_session": False})
        sd = s.get("data") or {}
        print(f"  op{op:<3}   : err={s.get('error')} "
              f"ch={sd.get('available_channels')} "
              f"cap={sd.get('need_captcha')}")

print("\n" + "=" * 70)
