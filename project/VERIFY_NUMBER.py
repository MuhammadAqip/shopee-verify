"""VERIFY_NUMBER.py — VERIFIKASI NOMOR via OTP (bukan ganti nomor).

Yang SUDAH TERBUKTI jalan di ck_1553:
  change_phone_init    -> seq_no + auth_required
  change_phone_init_v2 -> ivs_utoken + change_phone_token
  ivs/methods          -> 2 metode
  method/select        -> error 0
  otp/get_settings_v2  -> channels + seed
  otp/send_vcode       -> OTP TERKIRIM ke nomor target

Yang gagal: token/verify (211) -> ivs_signature -> precheck/commit

Jalan pintas: kalau OTP sudah terkirim, coba verify_vcode LANGSUNG
tanpa ivs_signature. Kalau server terima, nomor terverifikasi.

Flow:
  1. init -> seq_no
  2. init_v2 -> ivs_utoken + change_phone_token
  3. otp/get_settings_v2
  4. otp/send_vcode  (channel WA)
  5. tunggu kode -> otp/verify_vcode
  6. change_phone_commit_v2
"""
import json, sys, time, requests

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1553.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283191104601"
PROXY = "http://127.0.0.1:18080"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/VERIFY.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = {p.split("=", 1)[0].strip(): p.split("=", 1)[1].strip()
           for p in ck.split(";") if "=" in p}
csrf = cookies.get("csrftoken", "")

s = requests.Session()
s.cookies.update(cookies)
s.proxies = {"http": PROXY, "https": PROXY}
s.headers.update({
    "user-agent": UA, "x-api-source": "pc",
    "x-requested-with": "XMLHttpRequest",
    "referer": "https://shopee.co.id/user/account/settings",
    "accept": "application/json", "content-type": "application/json",
    "x-csrftoken": csrf,
    "af-ac-enc-dat": "0123456789abcdef",
    "x-sz-sdk-version": "1.12.45",
})


def post(path, body=None, q=""):
    r = s.post(f"https://shopee.co.id{path}{q}", json=body or {}, timeout=45)
    try:
        j = r.json()
    except Exception:
        j = {"_raw": r.text[:200]}
    return r.status_code, j


def get(path, q=""):
    r = s.get(f"https://shopee.co.id{path}{q}", timeout=45)
    try:
        j = r.json()
    except Exception:
        j = {"_raw": r.text[:200]}
    return r.status_code, j


log(f"=== akun {cookies.get('SPC_U')} -> nomor {NEWPHONE} ===")

# === 0. konfirmasi sesi hidup ===
st, j = get("/api/v4/account/basic/get_account_info")
log(f"0. account_info: {st} err={j.get('error')} user={(j.get('data') or {}).get('username')}")
if j.get("error") != 0:
    log("  ❌ COOKIE MATI — stop")
    sys.exit(1)

# === 1. change_phone_init ===
log("\n=== 1. change_phone_init ===")
st, j = post("/api/v4/account/management/change_phone_init")
log(f"  {st} err={j.get('error')} {json.dumps(j)[:300]}")
init = j.get("data") or {}
seq = init.get("seq_no") or init.get("seq")
log(f"  seq_no={seq} auth_required={init.get('auth_required')}")
if j.get("error") not in (0, None):
    log("  ❌ init gagal")

# === 2. change_phone_init_v2 ===
log("\n=== 2. change_phone_init_v2 ===")
body2 = {"phone": NEWPHONE}
if seq:
    body2["seq_no"] = seq
st, j = post("/api/v4/account/management/change_phone_init_v2", body2)
log(f"  {st} err={j.get('error')} {json.dumps(j)[:400]}")
d2 = j.get("data") or {}
utoken = d2.get("ivs_utoken")
cp_token = d2.get("change_phone_token") or d2.get("token")
log(f"  ivs_utoken={len(utoken) if utoken else 0}B cp_token={len(cp_token) if cp_token else 0}B ivs_required={d2.get('ivs_required')}")

# === 3. otp/get_settings_v2 ===
log("\n=== 3. otp/get_settings_v2 ===")
st, j = post("/api/v4/otp/get_settings_v2", {"operation": 8, "phone": NEWPHONE})
log(f"  {st} err={j.get('error')} {json.dumps(j)[:300]}")
chans = (j.get("data") or {}).get("available_channels") or []
log(f"  channels={chans}")

# === 4. otp/send_vcode ===
log("\n=== 4. otp/send_vcode ===")
ok_send = False
tracking = ""
for ch in ([3, 1, 2] if not chans else [c for c in [3, 1, 2] if c in chans] + chans):
    st, j = post("/api/v4/otp/send_vcode",
                 {"phone": NEWPHONE, "channel": ch, "operation": 8})
    err = j.get("error")
    log(f"  channel={ch} {st} err={err} {json.dumps(j)[:220]}")
    if err == 0:
        dd = j.get("data") or {}
        tracking = dd.get("otp_tracking_id") or dd.get("tracking_id") or ""
        ok_send = True
        log(f"  ✅ OTP TERKIRIM ch={ch} tracking={tracking[:40]}")
        break
    if err in (23500101, 23500152):
        log("  rate limit / captcha — coba channel lain")
        time.sleep(3)

if not ok_send:
    log("  ❌ send_vcode gagal semua channel")

# === 5. tunggu kode ===
if ok_send:
    log("\n=== 5. tunggu kode OTP ===")
    log(f"  OTP dikirim ke {NEWPHONE} via channel WA/SMS")
    log("  tulis kode ke /root/shopee-verify/OTP.txt")
    code = ""
    for i in range(120):     # max 6 menit
        try:
            c = open("/root/shopee-verify/OTP.txt").read().strip()
            if c and len(c) >= 4:
                code = c
                break
        except Exception:
            pass
        time.sleep(3)

    if code:
        log(f"  ✅ kode diterima: {code}")
        log("\n=== 6. otp/verify_vcode ===")
        body6 = {"phone": NEWPHONE, "code": code, "vcode": code,
                 "operation": 8, "otp_tracking_id": tracking}
        st, j = post("/api/v4/otp/verify_vcode", body6)
        log(f"  {st} err={j.get('error')} {json.dumps(j)[:400]}")
        d6 = j.get("data") or {}
        verify_token = d6.get("verify_token") or d6.get("token") or d6.get("otp_token")

        if j.get("error") == 0:
            log("  ✅✅ OTP VERIFIED")
            log("\n=== 7. change_phone_commit_v2 ===")
            body7 = {"phone": NEWPHONE, "seq_no": seq,
                     "change_phone_token": cp_token,
                     "verify_token": verify_token,
                     "otp_tracking_id": tracking}
            st, j = post("/api/v4/account/management/change_phone_commit_v2", body7)
            log(f"  {st} err={j.get('error')} {json.dumps(j)[:400]}")
            if j.get("error") == 0:
                log("  🎉🎉🎉 NOMOR BERHASIL DIGANTI")
                json.dump(j, open("/root/shopee-verify/CHANGE_OK.json", "w"), indent=1)
            else:
                log("  commit gagal — coba varian lain")
                for v in ("change_phone_commit", "change_phone_commit_v2"):
                    for bb in ({"phone": NEWPHONE, "seq_no": seq, "verify_token": verify_token},
                               {"phone": NEWPHONE, "seq_no": seq}):
                        st2, j2 = post(f"/api/v4/account/management/{v}", bb)
                        log(f"    {v} {list(bb)} -> err={j2.get('error')}")
                        if j2.get("error") == 0:
                            log("    🎉 BERHASIL")
                            break
        else:
            log("  verify_vcode gagal")
    else:
        log("  ⏰ timeout tunggu kode")

# simpan sesi
open("/root/shopee-verify/ck_verify_out.txt", "w").write(
    "; ".join(f"{k}={v}" for k, v in s.cookies.get_dict().items()))
log("\n=== SELESAI ===")
