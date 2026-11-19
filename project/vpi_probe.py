# -*- coding: utf-8 -*-
"""vpi_probe.py — bongkar verify_payment_init (10002).

Fakta:
  init v1 -> seq_no + auth_required: [1,2] atau [1]
  get_password_verify_method -> 0 {verify_method: 2}
  verify_payment_init -> 10002 (dan 12301018 di akun lain)

10002 = IVS state invalid. Padahal ivs_required=True.

Hipotesis: verify_payment_init HARUS dipanggil dengan payload yang memuat
metadata IVS / u_token yang didapat dari init_v2.
"""

import json, sys, urllib.request, urllib.error, time

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_5th.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283191104601"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
ck = open(CK).read().strip()
CSRF = ""
for p in ck.split(";"):
    if p.strip().startswith("csrftoken="):
        CSRF = p.split("=", 1)[1].strip()
M = "/api/v4/account/management"


def call(path, body=None, method=None):
    h = {"Cookie": ck, "User-Agent": UA, "X-API-SOURCE": "pc",
         "X-Requested-With": "XMLHttpRequest",
         "Referer": "https://shopee.co.id/user/account/settings",
         "Content-Type": "application/json", "Accept": "application/json",
         "X-CSRFToken": CSRF, "X-Shopee-Language": "id"}
    d = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request("https://shopee.co.id" + path, data=d, headers=h,
                                 method=method or ("POST" if body is not None else "GET"))
    try:
        r = urllib.request.urlopen(req, timeout=50)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}
    except Exception as ex:
        return 0, {"exc": str(ex)[:60]}


print(f"=== VPI PROBE — {CK} ===", flush=True)

s, j = call(f"{M}/change_phone_init", {})
SEQ = (j.get("data") or {}).get("seq_no")
AUTH = (j.get("data") or {}).get("auth_required")
print(f"seq_no={SEQ} auth_required={AUTH}", flush=True)

s, j2 = call(f"{M}/change_phone_init_v2", {})
d2 = j2.get("data") or {}
UT = d2.get("ivs_utoken") or ""
CPT = d2.get("change_phone_token") or ""
print(f"v2: ivs_required={d2.get('ivs_required')} ut={len(UT)}B cp={len(CPT)}B", flush=True)

s, j3 = call(f"{M}/get_password_verify_method?seq_no={SEQ}&scenario=1", None, "GET")
print(f"verify_method={j3.get('data')}", flush=True)
VM = (j3.get("data") or {}).get("verify_method")

# brute payload verify_payment_init
variants = [
    ("seq_only", {"seq_no": SEQ}),
    ("seq_scen", {"seq_no": SEQ, "scenario": 1}),
    ("seq_scen2", {"seq_no": SEQ, "scenario": 2}),
    ("seq_vm", {"seq_no": SEQ, "scenario": 1, "verify_method": VM}),
    ("seq_vm2", {"seq_no": SEQ, "verify_method": VM}),
    ("seq_ut", {"seq_no": SEQ, "scenario": 1, "ivs_utoken": UT}),
    ("seq_cp", {"seq_no": SEQ, "scenario": 1, "change_phone_token": CPT}),
    ("seq_all", {"seq_no": SEQ, "scenario": 1, "ivs_utoken": UT,
                 "change_phone_token": CPT, "verify_method": VM}),
    ("scen3", {"seq_no": SEQ, "scenario": 3}),
    ("scen0", {"seq_no": SEQ, "scenario": 0}),
]

print("\n=== verify_payment_init variasi ===", flush=True)
best = None
for name, b in variants:
    s, j = call(f"{M}/verify_payment_init", b)
    e = j.get("error")
    dd = j.get("data")
    mark = "★" if e != 10002 else " "
    print(f" {mark}[{name:11s}] err={e} data={str(dd)[:120]}", flush=True)
    if e != 10002 and e is not None:
        best = (name, j)
    time.sleep(0.5)

if best:
    print(f"\n🟢 BEDA: {best[0]} -> {str(best[1])[:250]}", flush=True)
else:
    print("\n❌ semua 10002", flush=True)

# cek: apakah ada endpoint ivs yang harus dipanggil dulu
print("\n=== endpoint IVS sebelum verify_payment ===", flush=True)
for p, b in (
    ("/api/v4/anti_fraud/ivs/methods", {"event": 2, "u_token": UT} if UT else None),
    ("/api/v4/account/management/verify_payment_get_method", None),
    ("/api/v4/account/management/get_payment_verify_method", None),
):
    if b is None and "ivs" not in p:
        s, j = call(p, None, "GET")
    else:
        s, j = call(p, b) if b else call(p, {}, "POST")
    print(f"  {p.split('/')[-1]:34s} {s} err={j.get('error')} {str(j.get('data'))[:120]}", flush=True)
    time.sleep(0.5)

json.dump({"seq": SEQ, "auth": AUTH, "vm": VM, "ut_len": len(UT)},
          open("vpi_state.json", "w"), indent=1)
