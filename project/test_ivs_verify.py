# -*- coding: utf-8 -*-
"""test_ivs_verify.py — uji anti_fraud/ivs/token/verify dengan signature asli dari DevTools."""
import sys, json
sys.path.insert(0, "/root/shopee-verify")
from ivs_flow import Shopee, IVS_TYPE

SIG = ("U2FsdGVkX1+nb/k5viyAqrYWHIpHAcfmoMgDUdbwS23LUkv43Byud/xdqHKDFZM4jdIBaNwG0I4F"
       "8shTpTgHlL1FvoDHBwJQTAPYOBYB00GuALmU8YBwfTi6D1lUez6Ehs6/xJsFlMbK8xkMwzI9QHoK5G"
       "2Zc/E5koJfs51frDsFXx59cJlaZ6qwHsu4RV5Ejgal7tFVBLVqi/TbmkEAEJFfDgt/C/pyD2G/KVmu"
       "VYBbu8hVxRc8KWjNkUTv9+l5qZMM8W1GW6Y4F3U6eGkTstAxHw02DHxP+7BVAVNpCE/DqBSWu+snnL"
       "wytMUZ+NoWqdR7CmCZxTi/EgVw453TDLOE3tLMPr+PIlg9mVJfiXQYor1tvH4nI4lJxTljt5+phJlj"
       "5dHfkmD4xj4DZ97ivYM/1AFmEfyamCrs065GXvxpsGkvtW7uw9CuLhcp45klw8BzNGf3Im8Bm5e9BC"
       "wIS8p5VouHTl6Fu5GODJBmqfUFHJ5x+7yihSBV5bsZcDlknN5a0JhiwE7rYfu0Ey8ODPJON69p3PnN"
       "25aD0CjQUuo7p0RSMaayR3WOpBqqnNn5aL8stG4q5Kpd6bBwB0yAiIOBjVgunfy6n9WFw5GiL8NTrx"
       "YCaxQQSFsQwlVZ7GgwpSLRLH51Ixdh/MfB+6t20AkTeib/N5n88mlg5ZwgXZAc8gVrMSp9CuYJzgjF"
       "bWbPbyQGT23nWJCHv5+1fRICbGnfTyC2nRGcA7JOG4UWykOEOQuPXD9ntSZtTQp+Y5tI21VxRCc0mL"
       "2TpKrH+oPRwq+KpYFJfBwAPQN7zzOYJssKTAUIImyaayyYUeXqqdnBx4LZP4O8OpR773+1lXG3D+hx"
       "Iq5y2v6Ra2F1Xq6ClIz1Re8NhuOInINAn/JEeNDt")

s = Shopee(open("/root/shopee-verify/ck_test.txt").read().strip())
r1 = s.init()
print("1. init_v2:", r1["ok"], "ivs_required:", r1["ivs_required"])
tok = r1["token"]

PHONE_BARU = "6285876130683"
PW = "qwertyui123"

print("\n2. ivs/methods -> 49900000 (butuh x-sap-sec, skip)")
print("3. ivs/method/select -> coba langsung dengan type=2")

r3 = s.ivs_select(2, None)
print("   select:", json.dumps(r3["raw"], ensure_ascii=False)[:180])

print("\n4. verify_password")
r4 = s.verify_password(PW)
print("   ok:", r4["ok"], "rc_token:", bool(r4["rc_token"]))
print("   raw:", json.dumps(r4["raw"], ensure_ascii=False)[:200])

print("\n5. ivs/token/verify (pakai signature dari DevTools)")
variants = [
    ("signature only", {"signature": SIG, "event": 2}),
    ("sig+rc_token", {"signature": SIG, "event": 2, "rc_token": r4["rc_token"]}),
    ("ivs_signature", {"ivs_signature": SIG, "event": 2}),
    ("sig+type", {"signature": SIG, "event": 2, "type": 2}),
    ("sig+type+rc", {"signature": SIG, "event": 2, "type": 2, "rc_token": r4["rc_token"]}),
]
for lbl, body in variants:
    r = s.api("/api/v4/anti_fraud/ivs/token/verify", body)
    print(f"   {lbl:16}: {json.dumps(r, ensure_ascii=False)[:200]}")
