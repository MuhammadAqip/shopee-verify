# -*- coding: utf-8 -*-
"""probe_methods.py — cari body benar untuk ivs/methods."""
import sys, json
sys.path.insert(0, "/root/shopee-verify")
from full_flow import Flow

f = Flow(cookie=open("/root/shopee-verify/ck_new.txt").read().strip())
f.csrf = "432d27359263f259eed77b3f94285c5e"
f.step1_init()
ut = f.u_token
print("u_token:", (ut or "")[:40], "...")

variants = [
    ("{}", {}),
    ("u_token", {"u_token": ut}),
    ("ivs_utoken", {"ivs_utoken": ut}),
    ("u_token+op", {"u_token": ut, "operation": 0}),
    ("u_token+scenario", {"u_token": ut, "scenario": 1}),
    ("u_token+misc", {"u_token": ut, "misc": {"operation": 0}}),
    ("cp_token", {"change_phone_token": f.cp_token}),
    ("u+cp", {"u_token": ut, "change_phone_token": f.cp_token}),
    ("u+cp+misc", {"u_token": ut, "change_phone_token": f.cp_token,
                   "misc": {"operation": 0}}),
]
for lbl, body in variants:
    st, r = f.post("/api/v4/anti_fraud/ivs/methods", body,
                   ref="https://shopee.co.id/verify/ivs")
    d = r.get("data")
    n = len(d) if isinstance(d, list) else 0
    print(f"{lbl:18}: HTTP {st} error={r.get('error')} methods={n}")
    if n:
        for m in d:
            print(f"    type={m.get('type')} vtok={len(m.get('v_token') or '')}")
        break
