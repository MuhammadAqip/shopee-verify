"""OP18_CHANGE.py — change phone via operation=18 (need_captcha:FALSE).

Temuan: get_settings_v2(operation=18) -> scene "phone_otp_account_set_phone",
need_captcha = FALSE. Maka send_vcode op=18 langsung kirim OTP tanpa captcha.

Flow:
  1. cek sesi
  2. change_phone_init_v2 (siapkan state)
  3. get_settings_v2 op=18 -> seed
  4. send_vcode op=18 ch3 (WA) -> otp_tracking_id
  5. kalau 23500101 -> coba ch2, ch1
  6. OTP masuk WA -> panggil verify_vcode op=18 -> selesai
"""
import json, sys, time, os
import requests

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_zax.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283829322571"
PROXY = os.environ.get("SHOPEE_PROXY", "")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/O18.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = {p.split("=", 1)[0].strip(): p.split("=", 1)[1].strip()
           for p in ck.split(";") if "=" in p}

s = requests.Session()
s.cookies.update(cookies)
if PROXY:
    s.proxies = {"http": PROXY, "https": PROXY}
s.headers.update({
    "user-agent": UA, "x-api-source": "pc",
    "x-requested-with": "XMLHttpRequest",
    "referer": "https://shopee.co.id/", "accept": "application/json",
    "content-type": "application/json",
    "x-shopee-language": "id",
    "x-csrftoken": cookies.get("csrftoken", "")})


def post(p, b):
    try:
        r = s.post(f"https://shopee.co.id{p}", json=b, timeout=50)
        return r.status_code, r.json()
    except Exception as e:
        return 0, {"_err": str(e)[:80]}


def get(p):
    try:
        r = s.get(f"https://shopee.co.id{p}", timeout=50)
        return r.status_code, r.json()
    except Exception as e:
        return 0, {"_err": str(e)[:80]}


log(f"=== {cookies.get('SPC_U')} -> {NEWPHONE} (op=18) ===")
log(f"  proxy: {PROXY or 'DIRECT'}")

# === 1. sesi ===
st, j = get("/api/v4/account/basic/get_account_info")
log(f"\n[1] account err={j.get('error')} user={(j.get('data') or {}).get('username')}")
if j.get("error") != 0:
    log("  ❌ cookie mati")
    sys.exit(1)

# === 2. tos consent ===
st, j = get("/api/v4/account/check_tos_consent")
need = (j.get("data") or {}).get("need_tos_consent")
log(f"\n[2] tos need={need}")
if need:
    st, j = post("/api/v4/account/accept_tos_consent", {"scenario": "Login Buyer"})
    log(f"  accept -> err={j.get('error')}")

# === 3. init_v2 ===
st, j = post("/api/v4/account/management/change_phone_init_v2",
             {"phone": NEWPHONE, "seq_no": None})
d = j.get("data") or {}
log(f"\n[3] init_v2 err={j.get('error')} ivs={d.get('ivs_required')} "
    f"cp_token={len(str(d.get('change_phone_token') or ''))}B")
if j.get("error") not in (0, None):
    log(f"  ⛔ init gagal: {json.dumps(j)[:200]}")
    sys.exit(2)

# === 4. get_settings_v2 op=18 ===
log("\n[4] get_settings_v2 op=18 (no captcha)")
st, j = post("/api/v4/otp/get_settings_v2", {"phone": NEWPHONE, "operation": 18})
d = j.get("data") or {}
seed = d.get("seed")
log(f"  err={j.get('error')} need_captcha={d.get('need_captcha')} "
    f"scene={d.get('captcha_scene')} ch={d.get('available_channels')}")
if j.get("error") not in (0, None):
    log(f"  ⛔ {json.dumps(j)[:200]}")
    sys.exit(3)
if d.get("need_captcha"):
    log("  ⚠️ captcha masih diminta — op=18 ternyata butuh captcha juga")
    sys.exit(31)

# === 5. send_vcode op=18 ===
log("\n[5] send_vcode op=18")
tries = []
for ch in [3, 2, 1]:
    st, j = post("/api/v4/otp/send_vcode",
                 {"phone": NEWPHONE, "channel": ch, "operation": 18, "seed": seed})
    err = j.get("error")
    dd = j.get("data") or {}
    trk = dd.get("otp_tracking_id")
    tries.append({"ch": ch, "err": err, "trk": trk})
    log(f"  ch={ch} err={err} trk={str(trk)[:40]}")
    if err == 0:
        log(f"\n  ✅✅✅✅ OTP TERKIRIM ke ch={ch} (WA kalau ch=3)")
        log(f"  seed={seed}")
        log(f"  otp_tracking_id={trk}")
        json.dump({"phone": NEWPHONE, "ch": ch, "seed": seed,
                   "tracking": trk, "operation": 18},
                  open("/root/shopee-verify/OTP_SENT.json", "w"), indent=1)
        sys.exit(0)
    if err not in (23500101,):
        break
    time.sleep(2)

log("\n  ❌ semua channel gagal")
log(f"  tries: {json.dumps(tries)}")
json.dump({"tries": tries}, open("/root/shopee-verify/O18_FAIL.json", "w"), indent=1)
sys.exit(4)
