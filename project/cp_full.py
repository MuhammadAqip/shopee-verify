# -*- coding: utf-8 -*-
"""cp_full.py — FLOW GANTI NOMOR LENGKAP (tanpa IVS).

Temuan kunci:
  /api/v4/account/management/change_phone_init_v2
    -> change_phone_token, ivs_required: FALSE

Artinya ganti nomor TIDAK butuh IVS/anti-bot challenge.
Cookie 1659 (cart ter-flag) pun LOLOS init_v2.

Langkah:
  1. init_v2        -> change_phone_token
  2. precheck_v2    -> cek nomor baru valid & bisa dipakai
  3. otp/send_vcode -> kirim OTP ke nomor baru
  4. otp/verify_vcode -> verifikasi OTP
  5. commit_v2      -> commit perubahan

Usage:
  python3 cp_full.py <ckfile> <newphone> [--commit]
  python3 cp_full.py ck_1659.txt 6283191104601
"""
import json, sys, urllib.request, urllib.error, time

CKFILE = sys.argv[1] if len(sys.argv) > 1 else "ck_1659.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283191104601"
DO_COMMIT = "--commit" in sys.argv
OTP_CODE = None
for a in sys.argv:
    if a.startswith("--otp="):
        OTP_CODE = a.split("=", 1)[1]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
ck = open(CKFILE).read().strip()
CSRF = ""
for p in ck.split(";"):
    if p.strip().startswith("csrftoken="):
        CSRF = p.split("=", 1)[1].strip()

M = "/api/v4/account/management"


def log(*a):
    print(*a, flush=True)


def call(path, body=None):
    h = {"Cookie": ck, "User-Agent": UA, "X-API-SOURCE": "pc",
         "X-Requested-With": "XMLHttpRequest",
         "Referer": "https://shopee.co.id/user/account/settings",
         "Content-Type": "application/json", "Accept": "application/json",
         "X-CSRFToken": CSRF, "X-Shopee-Language": "id"}
    d = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request("https://shopee.co.id" + path, data=d,
                                 headers=h, method="POST" if body is not None else "GET")
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


log(f"=== CP FULL — {CKFILE} -> {NEWPHONE} ===")

# 0. info akun
s, j = call("/api/v4/account/basic/get_account_info")
d = j.get("data") or {}
log(f"[0] uid={d.get('userid')} user={d.get('username')} phone={d.get('phone')}")

# 1. init_v2
log("\n[1] change_phone_init_v2")
s, j = call(f"{M}/change_phone_init_v2", {})
if j.get("error") != 0:
    log(f"    ❌ {j.get('error')} — berhenti")
    sys.exit(1)
d = j.get("data") or {}
CPT = d.get("change_phone_token")
log(f"    ✅ token={CPT[:24]}... ivs_required={d.get('ivs_required')}")

# 2. precheck_v2
log(f"\n[2] change_phone_precheck_v2 -> {NEWPHONE}")
s, j = call(f"{M}/change_phone_precheck_v2", {"phone": NEWPHONE})
log(f"    {s} err={j.get('error')} data={str(j.get('data'))[:220]}")
if j.get("error") not in (0, None):
    log("    ⚠️ precheck gagal, tetap coba send_vcode")

state = {"change_phone_token": CPT, "new_phone": NEWPHONE, "precheck": j}
json.dump(state, open("cp_state.json", "w"), indent=1)

# 3. send OTP — coba beberapa endpoint
log("\n[3] kirim OTP ke nomor baru")
attempts = [
    (f"{M}/send_vcode", {"phone": NEWPHONE, "change_phone_token": CPT}),
    (f"{M}/change_phone_send_vcode", {"phone": NEWPHONE, "change_phone_token": CPT}),
    ("/api/v4/otp/send_vcode", {"phone": NEWPHONE, "change_phone_token": CPT}),
    (f"{M}/send_vcode", {"new_phone": NEWPHONE, "change_phone_token": CPT}),
]
vcode_token = None
for path, body in attempts:
    s, j = call(path, body)
    e = j.get("error")
    log(f"    {path.split('/')[-1]:22s} err={e} data={str(j.get('data'))[:120]}")
    if e == 0:
        dd = j.get("data") or {}
        vcode_token = dd.get("vcode_token") or dd.get("token")
        state["send"] = {"path": path, "resp": dd}
        log(f"    ✅ TERKIRIM vcode_token={str(vcode_token)[:20]}")
        break
    time.sleep(0.6)

state["vcode_token"] = vcode_token
json.dump(state, open("cp_state.json", "w"), indent=1)

# 4. verify OTP (kalau ada kode)
if OTP_CODE and vcode_token:
    log(f"\n[4] verify_vcode OTP={OTP_CODE}")
    for path in (f"{M}/verify_vcode", f"{M}/change_phone_verify_vcode",
                 "/api/v4/otp/verify_vcode"):
        s, j = call(path, {"vcode": OTP_CODE, "vcode_token": vcode_token,
                           "code": OTP_CODE, "change_phone_token": CPT})
        e = j.get("error")
        log(f"    {path.split('/')[-1]:22s} err={e} data={str(j.get('data'))[:120]}")
        if e == 0:
            state["verify"] = j.get("data")
            log("    ✅ OTP VERIFIED")
            break
        time.sleep(0.6)

# 5. commit
if DO_COMMIT:
    log("\n[5] change_phone_commit_v2")
    bodies = [
        {"change_phone_token": CPT, "new_phone": NEWPHONE,
         "vcode_token": vcode_token},
        {"change_phone_token": CPT, "phone": NEWPHONE,
         "vcode_token": vcode_token},
        {"change_phone_token": CPT, "new_phone": NEWPHONE,
         "vcode_token": vcode_token, "ivs_signature": "", "ivs_method": 0},
    ]
    for b in bodies:
        s, j = call(f"{M}/change_phone_commit_v2", b)
        e = j.get("error")
        log(f"    err={e} data={str(j.get('data'))[:180]}")
        if e == 0:
            log("    🟢🟢 COMMIT BERHASIL!")
            state["commit"] = j.get("data")
            break
        time.sleep(0.8)

json.dump(state, open("cp_state.json", "w"), indent=1)
log("\n=== SELESAI — state: cp_state.json ===")
