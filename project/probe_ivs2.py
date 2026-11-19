# -*- coding: utf-8 -*-
"""probe_ivs2.py — cari body benar untuk anti_fraud/ivs/methods."""
import sys, json, secrets
sys.path.insert(0, "/root/shopee-verify")
from ivs_flow import Shopee

s = Shopee(open("/root/shopee-verify/ck_test.txt").read().strip())
r1 = s.init()
print("init ok:", r1["ok"])
ut = r1["ivs_utoken"]
tok = r1["token"]

# af-ac-enc-dat = 16 hex (per skill: anti-fraud header)
enc = secrets.token_hex(8)

variants = [
    ("empty + encdat", {}, {"af-ac-enc-dat": enc}),
    ("utoken + encdat", {"ivs_utoken": ut}, {"af-ac-enc-dat": enc}),
    ("ivs_token+encdat", {"ivs_token": ut}, {"af-ac-enc-dat": enc}),
    ("cptoken+encdat", {"change_phone_token": tok}, {"af-ac-enc-dat": enc}),
    ("all+encdat", {"ivs_utoken": ut, "change_phone_token": tok,
                    "scenario": 1}, {"af-ac-enc-dat": enc}),
    ("empty+scenario", {"scenario": 1}, {"af-ac-enc-dat": enc}),
    ("empty+operation", {"operation": 1}, {"af-ac-enc-dat": enc}),
]

for lbl, body, extra in variants:
    r = s.api("/api/v4/anti_fraud/ivs/methods", body, method="POST", extra=extra)
    out = json.dumps(r, ensure_ascii=False)
    print(f"{lbl:22}: {out[:220]}")
