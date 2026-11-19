# -*- coding: utf-8 -*-
"""cp_ivs.py — lengkapi IVS untuk change_phone lewat API murni.

Fakta:
  change_phone_init (v1)     -> seq_no  ✅
  otp/send_vcode             -> OTP     ✅
  get_password_verify_method -> 10002   ❌ butuh IVS
  verify_payment_init        -> 10002   ❌
  precheck_v2                -> 10002   ❌

10002 = IVS state invalid.

Dugaan: 10002 muncul karena belum lewat change_phone_init_v2 (yang
memberi ivs_utoken) ATAU karena seq_no v1 harus dikawinkan dengan ivs_utoken.

Uji: init_v2 SETELAH v1, lalu pakai keduanya di semua step.
Juga coba event ChangePhone=2 di ivs/methods.
"""
import json, sys, urllib.request, urllib.error, time, hashlib

CKFILE = sys.argv[1] if len(sys.argv) > 1 else "ck_1659.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283191104601"
PASSWORD = sys.argv[3] if len(sys.argv) > 3 else "qwertyui123"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
ck = open(CKFILE).read().strip()
CSRF = ""
for p in ck.split(";"):
    if p.strip().startswith("csrftoken="):
        CSRF = p.split("=", 1)[1].strip()

M = "/api/v4/account/management"
st = {}


def log(*a):
    print(*a, flush=True)


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


log("=== CP IVS — lengkapi IVS untuk change_phone ===")

# 1. init v1 -> seq_no
s, j = call(f"{M}/change_phone_init", {})
SEQ = (j.get("data") or {}).get("seq_no")
log(f"[1] init v1: err={j.get('error')} seq_no={SEQ}")
st["seq_no"] = SEQ

# 2. init v2 -> ivs_utoken (PARALEL dengan v1)
s, j = call(f"{M}/change_phone_init_v2", {})
d2 = j.get("data") or {}
UT = d2.get("ivs_utoken")
CPT = d2.get("change_phone_token")
IVSREQ = d2.get("ivs_required")
log(f"[2] init v2: err={j.get('error')} ivs_required={IVSREQ} ut={len(UT or '')}B cp={len(CPT or '')}B")
st["v2"] = {"ivs_required": IVSREQ, "has_ut": bool(UT), "has_cp": bool(CPT)}

# 3. kalau ada ut, ambil ivs/methods event=2 (ChangePhone)
VTOK = None
MTYPE = None
if UT:
    log("\n[3] ivs/methods event=2 (ChangePhone)")
    s, j = call("/api/v4/anti_fraud/ivs/methods", {"event": 2, "u_token": UT})
    ms = j.get("data") or []
    log(f"    err={j.get('error')} methods={[(m.get('type'),len(m.get('v_token') or '')) for m in ms]}")
    if ms:
        MTYPE = ms[0]["type"]
        VTOK = ms[0]["v_token"]
        # select
        s, j = call("/api/v4/anti_fraud/ivs/method/select",
                    {"v_token": VTOK, "method": MTYPE, "event": 2, "u_token": UT})
        log(f"    select: err={j.get('error')} data={str(j.get('data'))[:120]}")
        st["ivs"] = {"type": MTYPE, "selected": j.get("data")}

# 4. get_password_verify_method — coba dengan seq_no dan tanpa
log("\n[4] get_password_verify_method (3 varian)")
for label, q in (("seq", f"?seq_no={SEQ}&scenario=1"), ("plain", "?scenario=1"),
                 ("noscen", f"?seq_no={SEQ}")):
    s, j = call(f"{M}/get_password_verify_method{q}", None, "GET")
    log(f"    [{label:6s}] err={j.get('error')} data={str(j.get('data'))[:110]}")
    if j.get("error") == 0:
        st["verify_method"] = j.get("data")
        break
    time.sleep(0.5)

# 5. verify_payment_init — varian body
log("\n[5] verify_payment_init (varian)")
bodies = [
    ("seq_scen", {"seq_no": SEQ, "scenario": 1}),
    ("seq_only", {"seq_no": SEQ}),
    ("seq_ut", {"seq_no": SEQ, "scenario": 1, "u_token": UT}),
    ("seq_ut_sig", {"seq_no": SEQ, "scenario": 1, "u_token": UT,
                    "ivs_signature": "", "method_type": MTYPE or 0}),
]
for label, b in bodies:
    s, j = call(f"{M}/verify_payment_init", b)
    log(f"    [{label:11s}] err={j.get('error')} data={str(j.get('data'))[:110]}")
    if j.get("error") == 0:
        st["verify_init"] = {"body": label, "data": j.get("data")}
        break
    time.sleep(0.5)

# 6. precheck — varian
log("\n[6] change_phone_precheck_v2 (varian)")
pk = [
    ("phone", {"phone": NEWPHONE}),
    ("p_seq", {"phone": NEWPHONE, "seq_no": SEQ}),
    ("p_tok", {"phone": NEWPHONE, "change_phone_token": CPT}),
    ("p_both", {"phone": NEWPHONE, "seq_no": SEQ, "change_phone_token": CPT}),
    ("p_np_seq", {"new_phone": NEWPHONE, "seq_no": SEQ}),
    ("p_sig", {"phone": NEWPHONE, "seq_no": SEQ, "ivs_signature": "",
               "ivs_method": MTYPE or 0}),
]
for label, b in pk:
    s, j = call(f"{M}/change_phone_precheck_v2", b)
    e = j.get("error")
    mark = "★" if e not in (10002, None) else " "
    log(f"   {mark}[{label:9s}] err={e} data={str(j.get('data'))[:100]}")
    st.setdefault("precheck", []).append({"v": label, "err": e})
    if e == 0:
        st["precheck_ok"] = {"v": label, "data": j.get("data")}
        break
    time.sleep(0.5)

json.dump(st, open("cp_ivs_state.json", "w"), indent=1)
log("\n=== SELESAI — cp_ivs_state.json ===")
