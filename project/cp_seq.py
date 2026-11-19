# -*- coding: utf-8 -*-
"""cp_seq.py — jalankan URUTAN LENGKAP sesuai engine Shopee.

Urutan asli (dari change_phone_engine.py yang diturunkan dari bundle):
  1. change_phone_init (v1)          -> seq_no  <-- KUNCI! precheck butuh ini
  2. get_password_verify_method      -> verify_method
  3. verify_payment_init             -> (init verifikasi)
  4. verify_payment_commit           -> answer (password/PIN)
  5. otp/get_settings_v2             -> channel list
  6. otp/send_vcode                  -> OTP terkirim
  7. otp/verify_vcode                -> vcode_token
  8. change_phone_precheck_v2        -> (baru valid setelah seq_no + verify)
  9. change_phone_commit_v2          -> DONE

Sebelumnya kita skip v1 (seq_no) -> precheck 10002. Itu penyebabnya.
"""
import json, sys, urllib.request, urllib.error, time

CKFILE = sys.argv[1] if len(sys.argv) > 1 else "ck_1659.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283191104601"
PASSWORD = sys.argv[3] if len(sys.argv) > 3 else "qwertyui123"
STOP_AT = None
for a in sys.argv:
    if a.startswith("--stop="):
        STOP_AT = a.split("=", 1)[1]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
ck = open(CKFILE).read().strip()
CSRF = ""
for p in ck.split(";"):
    if p.strip().startswith("csrftoken="):
        CSRF = p.split("=", 1)[1].strip()

M = "/api/v4/account/management"
state = {}


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
    op = urllib.request.build_opener()
    try:
        r = op.open(req, timeout=50)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}
    except Exception as ex:
        return 0, {"exc": str(ex)[:70]}


def stop(name):
    if STOP_AT and STOP_AT == name:
        log(f"\n⏸ stop di '{name}'")
        json.dump(state, open("cp_seq_state.json", "w"), indent=1)
        sys.exit(0)


log(f"=== CP SEQ — {CKFILE} → {NEWPHONE} ===")

# 0 akun
s, j = call("/api/v4/account/basic/get_account_info")
d = j.get("data") or {}
log(f"[0] uid={d.get('userid')} user={d.get('username')} phone={d.get('phone')}")
state["account"] = {"uid": d.get("userid"), "phone": d.get("phone")}

# 1 init v1 → seq_no
log("\n[1] change_phone_init (v1) — cari seq_no")
s, j = call(f"{M}/change_phone_init", {})
log(f"    {s} err={j.get('error')} data={str(j.get('data'))[:250]}")
SEQ = None
if j.get("error") == 0:
    SEQ = (j.get("data") or {}).get("seq_no")
    state["v1"] = j.get("data")
    log(f"    seq_no={SEQ}")

if not SEQ:
    log("\n[1b] fallback init_v2 (ivs_required)")
    s, j = call(f"{M}/change_phone_init_v2", {})
    log(f"    {s} err={j.get('error')} data={str(j.get('data'))[:250]}")
    state["v2"] = j.get("data")
    CPT = (j.get("data") or {}).get("change_phone_token")
    state["change_phone_token"] = CPT

stop("init")

# 2 metode verifikasi
if SEQ:
    log("\n[2] get_password_verify_method")
    s, j = call(f"{M}/get_password_verify_method?seq_no={SEQ}&scenario=1", None, "GET")
    log(f"    {s} err={j.get('error')} data={str(j.get('data'))[:200]}")
    state["methods"] = j.get("data")

    # 3 verify_payment_init
    log("\n[3] verify_payment_init")
    s, j = call(f"{M}/verify_payment_init", {"seq_no": SEQ, "scenario": 1})
    log(f"    {s} err={j.get('error')} data={str(j.get('data'))[:200]}")
    state["verify_init"] = j.get("data")

    # 4 verify_payment_commit (password)
    import hashlib
    pw_hash = hashlib.sha256(hashlib.md5(PASSWORD.encode()).hexdigest().encode()).hexdigest()
    log(f"\n[4] verify_payment_commit (password sha256(md5(pw)))")
    s, j = call(f"{M}/verify_payment_commit",
                {"seq_no": SEQ, "answer": pw_hash, "scenario": 1})
    log(f"    {s} err={j.get('error')} data={str(j.get('data'))[:200]}")
    state["verify_commit"] = j.get("data")
    stop("verify")

# 5 channel OTP
log("\n[5] otp/get_settings_v2")
s, j = call("/api/v4/otp/get_settings_v2",
            {"operation": 0, "phone": NEWPHONE, "supported_channels": [1, 2],
             "support_session": False})
log(f"    {s} err={j.get('error')} data={str(j.get('data'))[:250]}")
state["channels"] = j.get("data")

# 6 send OTP
log("\n[6] otp/send_vcode")
s, j = call("/api/v4/otp/send_vcode",
            {"phone": NEWPHONE, "channel": 1, "operation": 0, "force_channel": False,
             "supported_channels": [1, 2], "seed": ""})
log(f"    {s} err={j.get('error')} data={str(j.get('data'))[:250]}")
state["send"] = j.get("data")
stop("send")

# 8 precheck (dengan seq_no)
log("\n[8] change_phone_precheck_v2")
bodies = [{"phone": NEWPHONE, "seq_no": SEQ} if SEQ else {"phone": NEWPHONE}]
for b in bodies:
    s, j = call(f"{M}/change_phone_precheck_v2", b)
    log(f"    err={j.get('error')} data={str(j.get('data'))[:200]}")
    state["precheck"] = {"body": list(b.keys()), "resp": j}

json.dump(state, open("cp_seq_state.json", "w"), indent=1)
log("\n=== SELESAI — cp_seq_state.json ===")
log(f"\nRINGKASAN: seq_no={SEQ} · vcode={'Y' if (state.get('send') or {}).get('seed') else 'N'}")
