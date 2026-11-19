# -*- coding: utf-8 -*-
"""get_vtoken2.py — body BENAR untuk ivs/methods: {event:2, u_token}.

Dari bundle 668.e2c7e235735036fe923b.js:
  post("/api/v4/anti_fraud/ivs/methods", {event, u_token},
       {headers:{"x-app-type": tobAppType}})
  event = I.QL.ChangePhone = 2
"""
import sys, json
sys.path.insert(0, "/root/shopee-verify")
from full_flow import Flow

COOKIE = open("/root/shopee-verify/ck_1553.txt").read().strip()
CSRF = "3929567fdad6e3608eb25fd137f69955"
OUT = "/root/shopee-verify/vtoken_1553.json"

f = Flow(cookie=COOKIE)
f.csrf = CSRF

r1 = f.step1_init()
print("init_v2:", r1["ok"])
if not r1["ok"]:
    sys.exit("init gagal")
u_token = f.u_token

EVENTS = [(2, "ChangePhone"), (1, "Login"), (13, "ShopeePayChangePhone"),
          (6, "ChangePassword")]
found = None
for ev, name in EVENTS:
    st, r = f.post("/api/v4/anti_fraud/ivs/methods",
                   {"event": ev, "u_token": u_token},
                   ref="https://shopee.co.id/verify/ivs")
    d = r.get("data")
    n = len(d) if isinstance(d, list) else 0
    print(f"  event={ev:>3} ({name:20}): HTTP {st} error={r.get('error')} methods={n}")
    if n:
        found = d
        for m in d:
            vt = str(m.get("v_token") or "")
            print(f"     ✅ type={m.get('type')} v_token={vt[:60]}… len={len(vt)}")
        break

if not found:
    print("\n❌ semua event gagal. raw terakhir:", json.dumps(r, ensure_ascii=False)[:200])
    sys.exit(1)

r4 = f.step4_password("qwertyui123")
print("\nverify_password:", r4["ok"])

json.dump({"u_token": u_token, "r_token": f.r_token, "cp_token": f.cp_token,
           "methods": found}, open(OUT, "w"), ensure_ascii=False, indent=1)
print(f"\n✅ disimpan {OUT}")

# langsung verifikasi signature
print("\n=== uji ivs/token/verify ===")
for m in found:
    r5 = f.step5_ivs_verify(method=m["type"], event=2,
                            v_token=m["v_token"], operation=0)
    print(f"  type={m['type']}: ok={r5['ok']} error={r5.get('error')} "
          f"sig={str(r5.get('signature'))[:40]}…")
    if r5["ok"]:
        json.dump({"ivs_sig": r5["signature"], "method": m["type"],
                   "u_token": u_token, "r_token": f.r_token,
                   "cp_token": f.cp_token},
                  open("/root/shopee-verify/ivs_ready_1553.json", "w"),
                  ensure_ascii=False, indent=1)
        print("  ✅ SIGNATURE SIAP")
        break
