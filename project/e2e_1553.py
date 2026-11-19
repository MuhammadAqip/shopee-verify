# -*- coding: utf-8 -*-
"""e2e_1553.py — End-to-end ganti nomor akun 15539296185 -> 6285736070693.

Pakai v_token DevTools (type 2 + type 10). Semua lewat Python.
"""
import sys, json, hashlib
sys.path.insert(0, "/root/shopee-verify")
from full_flow import Flow

PHONE_BARU = "6285736070693"
PW = "qwertyui123"

V_TOKEN = {
    2: "EeEPg5u9gxsQJeghn/1I10Zav+9k1f+nnx8QvJt0cZbl+y4TCpHkTyDv1EVsPJMepUy68orjoVp6Fjvef//39VHx4VlqZqvJLL1Z",
    10: "U2FsdGVkX1/BGTxNJVRA3kJQ+JbfMeLyXtDtf2vnnH/R3saWZ9jp6TqnP+uxO8wsd+ysCdewgLPNxuTXo6i3HBBS0p6ihEAPHv9Yy2Ahai2A3GRT9aQKOGqFWL7jKpKDlVYKYbl8gXDqg2erxSknpNQPOfF2ra/VZzuCYl9T2leKe1bN/25xniGTBrvcxIfKsJwRdWofYNHnTFJJX6nEn2VA41MhhpgXZUykXX7XH8HWVcLUCWkpjto5zLQhdZ47Tt+lSUdtwdLXsdx+Zq4SUtvuRYFirKf2z1ecy2sxEGe11D67oMObcxqo6A5LAORJRd7l0HfrD0P/j/Nr8yDxmFvMf88U6UyyFsz8+EpaIfOiaDXqr1w8OZ8jMMnGz3qw3atmAvrob9GDPyvAXoOG94/SDnITwk6zB4utuPwIYDZa86p4yYgujOlo0cyglz1CeZnwoIs1C8HJo3PUF+Xt0IlAFr0swBq3HDIRyS91qss4qasM952LimAGaK2oEj00w4U32EcDDAJwYrEIyxB/eMOJb196Vgt+k/mb3/p0hi/N9VAf6IvSz5Cz8Sl2IxlSePulksCDIeOlonNmyaaqOgqYiPvjuuy87FUwZ5Ddezornt4WPFGt4Qn1NxJLk/Gycdzt14zfLHvQzFVit1zg0WYqmaBiqFUElkUs2DgHyTfeDyqrLFURxddNh4vcu8KrOGn/f84AdWssrrK9V3HwIFcHpKEfPoJrtJDpu5HOAcCyI/P2uFGSbYVfcYC/QKD0PchZVa3r4ZyAnda0j4g8JYUtr1nPD3DVr6w1qA1YQlGa1OU5VGMQA02T3f7hlHFfS3MPGSfyplWEt6Kars5BoXoUSL2e+GZcc6/Ag8BPOliZsMO0HZmKiXSFX/UjTx6lJGHHkQvxXFW+ziAzgdoL3fLatoMHXhuuLBDTQf30eQEvLTsONLHJrG2Q8cYTgpIP",
}

f = Flow(cookie=open("/root/shopee-verify/ck_1553.txt").read().strip())
f.csrf = "3929567fdad6e3608eb25fd137f69955"

print("=== 1. change_phone_init_v2 ===")
r1 = f.step1_init()
print(json.dumps(r1, ensure_ascii=False))
if not r1["ok"]:
    sys.exit("init gagal — cookie expired?")

print("\n=== 2. verify_password ===")
r4 = f.step4_password(PW)
print(json.dumps(r4, ensure_ascii=False))
if not r4["ok"]:
    sys.exit("password gagal")

print("\n=== 3. ivs/token/verify (method=2 PASSWORD) ===")
r5 = f.step5_ivs_verify(method=2, event=2, v_token=V_TOKEN[2], operation=0)
print(json.dumps(r5, ensure_ascii=False))
if not r5["ok"]:
    print(">> coba method=10 (PIN):")
    r5 = f.step5_ivs_verify(method=10, event=2, v_token=V_TOKEN[10], operation=0)
    print(json.dumps(r5, ensure_ascii=False))
    if not r5["ok"]:
        sys.exit("IVS gagal — v_token akun ini beda")

print("\n=== 4. change_phone_precheck_v2 ===")
r6 = f.step6_precheck(PHONE_BARU)
print(json.dumps(r6, ensure_ascii=False)[:400])

print("\n=== 5. otp/get_settings_v2 ===")
r7 = f.step7_channels(PHONE_BARU)
print(json.dumps(r7, ensure_ascii=False)[:400])

json.dump({"cp_token": f.cp_token, "u_token": f.u_token,
           "r_token": getattr(f, "r_token", None),
           "ivs_sig": f.ivs_sig, "method": f.method,
           "phone": PHONE_BARU},
          open("/root/shopee-verify/flow_state_1553.json", "w"))
print("\n[state disimpan]")
