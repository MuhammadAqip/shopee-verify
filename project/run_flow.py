# -*- coding: utf-8 -*-
"""run_flow.py — jalankan flow lengkap sampai dapat ivs_signature."""
import sys, json
sys.path.insert(0, "/root/shopee-verify")
from full_flow import Flow

PHONE_BARU = "6285876130683"
PW = "qwertyui123"

f = Flow()
print("=== 1. init_v2 ===")
r = f.step1_init()
print(json.dumps(r, ensure_ascii=False))
if not r["ok"]:
    sys.exit("init gagal")

print("\n=== 4. verify_password ===")
r = f.step4_password(PW)
print(json.dumps(r, ensure_ascii=False))
if not r["ok"]:
    sys.exit("password gagal")

print("\n=== 5. ivs/token/verify ===")
r = f.step5_ivs_verify(method=2, event=2, v_token=None, operation=0)
print(json.dumps(r, ensure_ascii=False))
if not r["ok"]:
    sys.exit("ivs verify gagal")

print("\n=== 6. precheck_v2 (nomor baru) ===")
r = f.step6_precheck(PHONE_BARU)
print(json.dumps(r, ensure_ascii=False)[:300])

print("\n=== 7. otp/get_settings_v2 ===")
r = f.step7_channels(PHONE_BARU)
print(json.dumps(r, ensure_ascii=False)[:300])
