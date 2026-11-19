# -*- coding: utf-8 -*-
"""run_flow3.py — flow lengkap termasuk ivs/methods untuk v_token."""
import sys, json
sys.path.insert(0, "/root/shopee-verify")
from full_flow import Flow

f = Flow(cookie=open("/root/shopee-verify/ck_new.txt").read().strip())
f.csrf = "432d27359263f259eed77b3f94285c5e"
PHONE = "6285876130683"

print("=== 1. init_v2 ===")
r1 = f.step1_init()
print(json.dumps(r1, ensure_ascii=False))

print("\n=== 2. ivs/methods ===")
st, r = f.post("/api/v4/anti_fraud/ivs/methods", {}, ref="https://shopee.co.id/verify/ivs")
print(f"HTTP {st} error={r.get('error')}")
methods = r.get("data") or []
for m in methods:
    print(f"  type={m.get('type')}  v_token_len={len(m.get('v_token') or '')}")

if not methods:
    print(json.dumps(r, ensure_ascii=False)[:300])
    sys.exit("ivs/methods gagal")

print("\n=== 4. verify_password ===")
r4 = f.step4_password("qwertyui123")
print(json.dumps(r4, ensure_ascii=False))

# pilih PASSWORD (type=2), fallback ke pertama
pick = next((m for m in methods if m.get("type") == 2), methods[0])
print(f"\n=== 3. ivs/method/select (type={pick['type']}) ===")
st, r = f.post("/api/v4/anti_fraud/ivs/method/select",
               {"method_name": pick["type"], "v_token": pick["v_token"],
                "u_token": f.u_token},
               ref="https://shopee.co.id/verify/ivs")
print(f"HTTP {st} {json.dumps(r, ensure_ascii=False)[:250]}")

print(f"\n=== 5. ivs/token/verify (method={pick['type']}) ===")
r5 = f.step5_ivs_verify(method=pick["type"], event=2,
                        v_token=pick["v_token"], operation=0)
print(json.dumps(r5, ensure_ascii=False))
if not r5["ok"]:
    sys.exit("ivs verify gagal")

print("\n=== 6. precheck_v2 ===")
r6 = f.step6_precheck(PHONE)
print(json.dumps(r6, ensure_ascii=False)[:400])

print("\n=== 7. otp/get_settings_v2 ===")
r7 = f.step7_channels(PHONE)
print(json.dumps(r7, ensure_ascii=False)[:400])

json.dump({"cp_token": f.cp_token, "u_token": f.u_token,
           "r_token": getattr(f, "r_token", None),
           "ivs_sig": f.ivs_sig, "method": pick["type"]},
          open("/root/shopee-verify/flow_state.json", "w"))
print("\n[state disimpan]")
