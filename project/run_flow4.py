# -*- coding: utf-8 -*-
"""run_flow4.py — pakai v_token dari DevTools Maker (satu-satunya data
yang tidak bisa kita generate sendiri), sisa flow semua dari Python."""
import sys, json
sys.path.insert(0, "/root/shopee-verify")
from full_flow import Flow

PHONE = "6285876130683"

# v_token dari DevTools Maker (screenshot flow ivs/methods)
# type 2 = PASSWORD, type 10 = ShopeePay PIN
V_TOKEN_PASSWORD = ("EeEPg5u9gxsQJeghn/1I10Zav+9k1f+nnx8QvJt0cZbl+y4TCpHkTyDv1EVsPJMepUy"
                    "68orjoVp6Fjvef//39VHx4VlqZqvJLL1Z")

f = Flow(cookie=open("/root/shopee-verify/ck_new.txt").read().strip())
f.csrf = "432d27359263f259eed77b3f94285c5e"

print("=== 1. init_v2 ===")
r1 = f.step1_init()
print(json.dumps(r1, ensure_ascii=False))

print("\n=== 4. verify_password ===")
r4 = f.step4_password("qwertyui123")
print(json.dumps(r4, ensure_ascii=False))
if not r4["ok"]:
    sys.exit("password gagal")

print("\n=== 5. ivs/token/verify (v_token dari DevTools, method=2) ===")
r5 = f.step5_ivs_verify(method=2, event=2, v_token=V_TOKEN_PASSWORD, operation=0)
print(json.dumps(r5, ensure_ascii=False))
if not r5["ok"]:
    print("\n>> coba tanpa v_token:")
    r5b = f.step5_ivs_verify(method=2, event=2, v_token=None, operation=0)
    print(json.dumps(r5b, ensure_ascii=False))
    if not r5b["ok"]:
        sys.exit("ivs verify gagal keduanya")
    f.ivs_sig = r5b.get("signature") or f.ivs_sig

print("\n=== 6. precheck_v2 ===")
r6 = f.step6_precheck(PHONE)
print(json.dumps(r6, ensure_ascii=False)[:400])

print("\n=== 7. otp/get_settings_v2 ===")
r7 = f.step7_channels(PHONE)
print(json.dumps(r7, ensure_ascii=False)[:400])

json.dump({"cp_token": f.cp_token, "u_token": f.u_token,
           "r_token": getattr(f, "r_token", None),
           "ivs_sig": f.ivs_sig, "method": 2},
          open("/root/shopee-verify/flow_state.json", "w"))
print("\n[state disimpan ke flow_state.json]")
