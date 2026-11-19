# -*- coding: utf-8 -*-
"""probe_verify_body.py — cari body tepat untuk anti_fraud/ivs/token/verify."""
import sys, json, secrets
sys.path.insert(0, "/root/shopee-verify")
from ivs_flow import Shopee

s = Shopee(open("/root/shopee-verify/ck_test.txt").read().strip())
r1 = s.init()
tok = r1["token"]
ut = r1["ivs_utoken"]
r4 = s.verify_password("qwertyui123")
rc = r4["rc_token"]
enc = secrets.token_hex(8)

print("rc_token len:", len(rc or ""))
print()

variants = [
    ("{}", {}),
    ("rc_token", {"rc_token": rc}),
    ("rc_token+op", {"rc_token": rc, "operation": 2}),
    ("rc+scenario", {"rc_token": rc, "scenario": 1}),
    ("rc+cp_token", {"rc_token": rc, "change_phone_token": tok}),
    ("rc+utoken", {"rc_token": rc, "ivs_utoken": ut}),
    ("all three", {"rc_token": rc, "ivs_utoken": ut, "change_phone_token": tok}),
    ("verify_token", {"verify_token": rc}),
    ("answer", {"answer": rc}),
    ("token", {"token": rc}),
]
for lbl, body in variants:
    r = s.api("/api/v4/anti_fraud/ivs/token/verify", body,
              extra={"af-ac-enc-dat": enc})
    print(f"POST {lbl:16}: {json.dumps(r, ensure_ascii=False)[:180]}")
