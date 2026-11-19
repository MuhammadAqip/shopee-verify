# -*- coding: utf-8 -*-
"""cp_ivs2.py — selesaikan IVS untuk change_phone di akun auth_required=[1].

Fakta:
  ck_1553 auth_required=[1] vm=2 vpi=10002
  10002 = IVS state invalid -> IVS BELUM SELESAI

Urutan benar (dari bundle 027.js + 30.js):
  1. change_phone_init_v2   -> ivs_utoken (428B)
  2. ivs/methods event=2    -> [{type, v_token}]
  3. ivs/method/select      -> pilih method
  4. [method spesifik]      -> password/OTP
  5. ivs/token/verify       -> signature   <-- KUNCI
  6. verify_payment_init    -> HARUS 0 setelah signature ada
  7. precheck -> send_vcode -> verify_vcode -> commit

Step 5 wajib. Schema: {method, event, u_token, v_token, ...} (field 'method').
"""
import json, sys, urllib.request, urllib.error, time, hashlib

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1553.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283191104601"
PASSWORD = sys.argv[3] if len(sys.argv) > 3 else "qwertyui123"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
ck = open(CK).read().strip()
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


log(f"=== CP IVS2 — {CK} ===")

# 0 akun
s, j = call("/api/v4/account/basic/get_account_info")
d = j.get("data") or {}
log(f"[0] uid={d.get('userid')} phone={d.get('phone')}")

# 1 init v1 + v2
s, j1 = call(f"{M}/change_phone_init", {})
SEQ = (j1.get("data") or {}).get("seq_no")
AUTH = (j1.get("data") or {}).get("auth_required")
s, j2 = call(f"{M}/change_phone_init_v2", {})
D2 = j2.get("data") or {}
UT = D2.get("ivs_utoken") or ""
CPT = D2.get("change_phone_token") or ""
log(f"[1] seq={SEQ} auth={AUTH} ut={len(UT)}B cp={len(CPT)}B")

# 2 ivs/methods event=2
log("\n[2] ivs/methods event=2 ChangePhone")
s, j = call("/api/v4/anti_fraud/ivs/methods", {"event": 2, "u_token": UT})
MS = j.get("data") or []
log(f"    err={j.get('error')} methods={[(m.get('type'),len(m.get('v_token') or '')) for m in MS]}")
if not MS:
    log("    ⚠️ kosong — coba event 1 & 6")
    for ev in (1, 6):
        s, j = call("/api/v4/anti_fraud/ivs/methods", {"event": ev, "u_token": UT})
        m2 = j.get("data") or []
        log(f"    event={ev}: err={j.get('error')} {[(x.get('type')) for x in m2]}")
        if m2:
            MS = m2
            break
if not MS:
    log("❌ tidak ada method")
    sys.exit(1)

MTYPE = MS[0]["type"]
VTOK = MS[0]["v_token"]

# pilih semua method satu-satu — utamakan Password(2), lalu OTP(1), lalu PIN(10)
ORDER = [2, 1, 11, 8, 6, 7, 10, 3, 5]
ordered = sorted(MS, key=lambda m: ORDER.index(m["type"]) if m["type"] in ORDER else 99)

SIG = None
RTOK = None
used_type = None
for mi, METH in enumerate(ordered):
    MTYPE = METH["type"]
    VTOK = METH["v_token"]
    log(f"\n[3.{mi}] method/select type={MTYPE} (v_token {len(VTOK)}B)")
    s, j = call("/api/v4/anti_fraud/ivs/method/select",
                {"v_token": VTOK, "method": MTYPE, "event": 2, "u_token": UT})
    log(f"    err={j.get('error')} data={str(j.get('data'))[:130]}")
    if j.get("error") != 0:
        continue
    SEL = j.get("data") or {}
    RTOK = SEL.get("r_token") or SEL.get("rToken")
    log(f"    r_token: {'Y' if RTOK else 'N'}")

    # === token/verify ===
    log("    token/verify:")
    base = {"event": 2, "u_token": UT, "v_token": VTOK}
    cands = [
        ("m", {**base, "method": MTYPE}),
        ("mn", {**base, "method_name": MTYPE}),
        ("m_r", {**base, "method": MTYPE, "r_token": RTOK}),
        ("m_misc", {**base, "method": MTYPE, "misc": {"seed": None, "operation": 0}}),
        ("m_full", {**base, "method": MTYPE, "r_token": RTOK, "shopee_df": None,
                    "misc": {"seed": None, "operation": 0}}),
    ]
    for name, b in cands:
        s, j = call("/api/v4/anti_fraud/ivs/token/verify", b)
        e = j.get("error")
        dd = j.get("data") or {}
        sg = dd.get("signature")
        log(f"      [{name:7s}] err={e} sig={'Y '+str(len(sg))+'B' if sg else 'N'}")
        if sg:
            SIG = sg
            used_type = MTYPE
            st["signature"] = sg
            st["method_type"] = MTYPE
            break
        time.sleep(0.4)
    if SIG:
        break
    # kalau password, coba verify_password endpoint untuk dapat signature
    if MTYPE == 2:
        pw_hash = hashlib.sha256(hashlib.md5(PASSWORD.encode()).hexdigest().encode()).hexdigest()
        for ep in ("/api/v4/anti_fraud/ivs/verify_password",
                   "/api/v4/anti_fraud/ivs/method/verify",
                   "/api/v4/anti_fraud/ivs/password/verify"):
            s, j = call(ep, {"password": pw_hash, "u_token": UT, "event": 2,
                             "v_token": VTOK, "method": 2})
            log(f"      {ep.split('/')[-1]:16s} err={j.get('error')} "
                f"data={str(j.get('data'))[:90]}")
            dd = j.get("data") or {}
            sg = dd.get("signature") if isinstance(dd, dict) else None
            if sg:
                SIG = sg
                used_type = 2
                st["signature"] = sg
                st["method_type"] = 2
                break
            time.sleep(0.4)
    if SIG:
        break

log(f"\n[4] SIGNATURE: {'Y '+str(len(SIG))+'B (type '+str(used_type)+')' if SIG else 'TIDAK DAPAT'}")

# 5 verify_payment_init SETELAH signature
log("\n[5] verify_payment_init (setelah signature)")
pw_hash = hashlib.sha256(hashlib.md5(PASSWORD.encode()).hexdigest().encode()).hexdigest()
vpis = [
    ("seq_sig", {"seq_no": SEQ, "scenario": 1, "ivs_signature": SIG or ""}),
    ("seq_scen", {"seq_no": SEQ, "scenario": 1}),
    ("seq", {"seq_no": SEQ}),
]
for name, b in vpis:
    s, j = call(f"{M}/verify_payment_init", b)
    e = j.get("error")
    log(f"    [{name:9s}] err={e} data={str(j.get('data'))[:130]}")
    if e == 0:
        st["vpi"] = {"name": name, "data": j.get("data")}
        break
    time.sleep(0.5)

# 6 verify_payment_commit
if st.get("vpi"):
    log("\n[6] verify_payment_commit")
    for name, b in (
        ("pw", {"seq_no": SEQ, "answer": pw_hash, "scenario": 1}),
        ("pw_sig", {"seq_no": SEQ, "answer": pw_hash, "scenario": 1,
                    "ivs_signature": SIG or ""}),
    ):
        s, j = call(f"{M}/verify_payment_commit", b)
        e = j.get("error")
        log(f"    [{name:7s}] err={e} data={str(j.get('data'))[:130]}")
        if e == 0:
            st["commit_verify"] = j.get("data")
            break
        time.sleep(0.5)

# 7 precheck
log("\n[7] precheck_v2")
for name, b in (("phone", {"phone": NEWPHONE}),
                ("p_sig", {"phone": NEWPHONE, "ivs_signature": SIG or ""}),
                ("p_seq", {"phone": NEWPHONE, "seq_no": SEQ})):
    s, j = call(f"{M}/change_phone_precheck_v2", b)
    e = j.get("error")
    log(f"    [{name:7s}] err={e} data={str(j.get('data'))[:130]}")
    if e == 0:
        st["precheck"] = j.get("data")
        break
    time.sleep(0.5)

# 8 send OTP
log("\n[8] otp/send_vcode")
s, j = call("/api/v4/otp/send_vcode",
            {"phone": NEWPHONE, "channel": 1, "operation": 0,
             "force_channel": False, "supported_channels": [1], "seed": ""})
log(f"    err={j.get('error')} data={str(j.get('data'))[:150]}")
st["send"] = j.get("data")

json.dump(st, open("cp_ivs2_state.json", "w"), indent=1)
log("\n=== HASIL cp_ivs2_state.json ===")
log(f"  signature: {'Y' if st.get('signature') else 'N'}")
log(f"  vpi: {st.get('vpi')}")
log(f"  precheck: {'Y' if st.get('precheck') else 'N'}")
log(f"  otp: {'Y' if (st.get('send') or {}).get('seed') else 'N'}")
