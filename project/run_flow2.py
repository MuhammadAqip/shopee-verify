# -*- coding: utf-8 -*-
"""run_flow2.py — jalankan flow lengkap dengan cookie baru."""
import sys, json
sys.path.insert(0, "/root/shopee-verify")
from full_flow import Flow

PHONE_BARU = "6285876130683"
PW = "qwertyui123"

f = Flow(cookie=open("/root/shopee-verify/ck_new.txt").read().strip())
f.csrf = "432d27359263f259eed77b3f94285c5e"

print("=== 1. init_v2 ===")
r = f.step1_init()
print(json.dumps(r, ensure_ascii=False))
if not r["ok"]:
    sys.exit("init gagal")

print("\n=== 4. verify_password ===")
r = f.step4_password(PW)
print(json.dumps(r, ensure_ascii=False))
if not r["ok"]:
    print("\n>> password ditolak. coba lanjut ke ivs verify dgn r_token kosong?")
    sys.exit("password gagal")

print("\n=== 5. ivs/token/verify ===")
r = f.step5_ivs_verify(method=2, event=2, v_token=None, operation=0)
print(json.dumps(r, ensure_ascii=False))
if not r["ok"]:
    sys.exit("ivs verify gagal")

print("\n=== 6. precheck_v2 ===")
r = f.step6_precheck(PHONE_BARU)
print(json.dumps(r, ensure_ascii=False)[:400])

print("\n=== 7. otp/get_settings_v2 ===")
r = f.step7_channels(PHONE_BARU)
print(json.dumps(r, ensure_ascii=False)[:400])

json.dump({"cp_token": f.cp_token, "u_token": f.u_token,
           "r_token": getattr(f, "r_token", None),
           "ivs_sig": f.ivs_sig, "method": f.method},
          open("/root/shopee-verify/flow_state.json", "w"))
print("\n[state disimpan ke flow_state.json]")
