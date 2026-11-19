# -*- coding: utf-8 -*-
"""get_sig1553.py — flow seleksi metode + verify sesuai bundle.

Bundle urutan: methods -> method/select -> verify_token(detail).
Body verify: {method_name,event,u_token,r_token,v_token,shopee_df,
              misc:{seed,operation}}
"""
import sys, json
sys.path.insert(0, "/root/shopee-verify")
from full_flow import Flow

COOKIE = open("/root/shopee-verify/ck_1553.txt").read().strip()
CSRF = "3929567fdad6e3608eb25fd137f69955"
OUT = "/root/shopee-verify/ivs_ready_1553.json"

f = Flow(cookie=COOKIE)
f.csrf = CSRF
assert f.step1_init()["ok"], "init gagal"
u_token = f.u_token

st, r = f.post("/api/v4/anti_fraud/ivs/methods",
               {"event": 2, "u_token": u_token},
               ref="https://shopee.co.id/verify/ivs")
methods = r.get("data") or []
print("methods:", [(m["type"], len(m["v_token"])) for m in methods])

if not f.step4_password("qwertyui123")["ok"]:
    sys.exit("password gagal")
r_token = f.r_token
print("password: OK r_token", len(r_token))

pick = next((m for m in methods if m["type"] == 2), methods[0])

print("\n=== ivs/method/select ===")
st, sel = f.post("/api/v4/anti_fraud/ivs/method/select",
                 {"method_name": pick["type"], "event": 2,
                  "u_token": u_token, "v_token": pick["v_token"],
                  "misc": {"operation": 0}},
                 ref="https://shopee.co.id/verify/ivs")
print(f"HTTP {st} {json.dumps(sel, ensure_ascii=False)[:220]}")

print("\n=== ivs/token/verify ===")
body = {"method_name": pick["type"], "event": 2,
        "u_token": u_token, "r_token": r_token,
        "v_token": pick["v_token"],
        "shopee_df": {"security_device_fingerprint": ""},
        "misc": {"seed": None, "operation": 0}}
st, ver = f.post("/api/v4/anti_fraud/ivs/token/verify", body,
                 ref="https://shopee.co.id/verify/ivs")
print(f"HTTP {st} error={ver.get('error')} sig={bool(ver.get('signature'))}")
if ver.get("error") == 0:
    print("✅ SIGNATURE:", ver["signature"][:70], "…")
    json.dump({"u_token": u_token, "r_token": r_token,
               "cp_token": f.cp_token, "method": pick["type"],
               "v_token": pick["v_token"], "ivs_sig": ver["signature"]},
              open(OUT, "w"), ensure_ascii=False, indent=1)
    print("disimpan", OUT)
else:
    print(json.dumps(ver, ensure_ascii=False)[:300])
    # variasi tanpa shopee_df
    for lbl, b in [
        ("tanpa shopee_df", {k: v for k, v in body.items() if k != "shopee_df"}),
        ("shopee_df string", {**body, "shopee_df": ""}),
        ("misc kosong", {**body, "misc": {}}),
        ("seed 0", {**body, "misc": {"seed": 0, "operation": 0}}),
    ]:
        st, v2 = f.post("/api/v4/anti_fraud/ivs/token/verify", b,
                        ref="https://shopee.co.id/verify/ivs")
        print(f"  {lbl:18}: error={v2.get('error')} sig={bool(v2.get('signature'))}")
        if v2.get("error") == 0:
            print("  ✅ SIGNATURE:", v2["signature"][:70])
            break
