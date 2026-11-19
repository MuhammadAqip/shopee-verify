# -*- coding: utf-8 -*-
import sys, json
sys.path.insert(0, "/root/shopee-verify")
from ivs_flow import Shopee

s = Shopee(open("/root/shopee-verify/ck_test.txt").read().strip())
r1 = s.init()
print("init ok:", r1["ok"], "ivs_required:", r1["ivs_required"])
ut = r1["ivs_utoken"]
tok = r1["token"]

cands = [
    ("POST {}", {}),
    ("POST utoken", {"ivs_utoken": ut}),
    ("POST ivs_token", {"ivs_token": ut}),
    ("POST change_phone_token", {"change_phone_token": tok}),
    ("POST both", {"ivs_utoken": ut, "change_phone_token": tok}),
    ("GET", None),
]
for lbl, body in cands:
    r = s.api("/api/v4/anti_fraud/ivs/methods", body,
              method="POST" if body is not None else "GET")
    out = json.dumps(r, ensure_ascii=False)
    print(f"{lbl:28}: {out[:200]}")
