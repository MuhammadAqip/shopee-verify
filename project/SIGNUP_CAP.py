"""SIGNUP_CAP.py — captcha scene "signup" untuk OTP.

Bukti:
  get_settings_v2 -> captcha_scene = "signup"
  get_config      -> SUKSES (error:0) di IP RI residential
  generate crawler_item -> Block (karena cart/mini di-flag)
  generate signup       -> BELUM DICODA dengan get_config fresh

Alur:
  1. get_config (scene signup) -> tracking_id
  2. generate (scene signup, tracking dari 1) -> captcha
  3. SadCaptcha solve
  4. verify -> captcha_token
  5. send_vcode + captcha_token
"""
import json, sys, time, os, base64, hashlib
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1659.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283191104601"
PROXY = "http://127.0.0.1:18080"
AESK = b"dRgUkXp2r5u8x/A?D(G+KbPeShVmYq3t"
SADKEY = open("/root/shopee-farm/bot_key.txt").read().strip()
APPKEY = "f9ffc83459897a13dd14c537e84b1753"
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):3d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/SIGNUP.log", "a").write(m + "\n")


def evp(pw, salt):
    d, prev = b"", b""
    while len(d) < 48:
        prev = hashlib.md5(prev + pw + salt).digest()
        d += prev
    return d[:32], d[32:48]


def enc(o):
    salt = os.urandom(8)
    k, iv = evp(AESK, salt)
    ct = AES.new(k, AES.MODE_CBC, iv).encrypt(
        pad(json.dumps(o, separators=(",", ":")).encode(), 16))
    return base64.b64encode(b"Salted__" + salt + ct).decode()


def dec(b):
    try:
        raw = base64.b64decode(b)
        if not raw.startswith(b"Salted__"):
            return {"_nohdr": raw[:60]}
        k, iv = evp(AESK, raw[8:16])
        return json.loads(unpad(AES.new(k, AES.MODE_CBC, iv).decrypt(raw[16:]), 16))
    except Exception as e:
        return {"_err": str(e)[:60]}


ck = open(CK).read().strip()
cookies = {p.split("=", 1)[0].strip(): p.split("=", 1)[1].strip()
           for p in ck.split(";") if "=" in p}

s = requests.Session()
s.cookies.update(cookies)
s.proxies = {"http": PROXY, "https": PROXY}
s.headers.update({
    "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"),
    "x-api-source": "pc", "x-requested-with": "XMLHttpRequest",
    "referer": "https://shopee.co.id/verify/captcha",
    "accept": "application/json", "content-type": "application/json",
    "x-csrftoken": cookies.get("csrftoken", ""),
    "af-ac-enc-dat": "0123456789abcdef",
    "x-sz-sdk-version": "1.12.45"})


def post(p, b=None):
    r = s.post(f"https://shopee.co.id{p}", json=b or {}, timeout=50)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"_raw": r.text[:200]}


log(f"=== {cookies.get('SPC_U')} -> {NEWPHONE} ===")

# 1. init
log("\n[1] change_phone_init")
st, j = post("/api/v4/account/management/change_phone_init")
seq = (j.get("data") or {}).get("seq_no")
log(f"  err={j.get('error')} seq={seq}")

st, j = post("/api/v4/account/management/change_phone_init_v2",
             {"phone": NEWPHONE, "seq_no": seq})
cp_tok = (j.get("data") or {}).get("change_phone_token")
log(f"  init2 err={j.get('error')} cp={len(cp_tok) if cp_tok else 0}B")

# 2. get_settings
log("\n[2] otp/get_settings_v2")
st, j = post("/api/v4/otp/get_settings_v2", {"operation": 8, "phone": NEWPHONE})
d3 = j.get("data") or {}
seed = d3.get("seed")
scene = d3.get("captcha_scene") or "signup"
log(f"  err={j.get('error')} scene={scene} seed={seed} need={d3.get('need_captcha')}")

# 3. get_config — FOKUS scene signup
log("\n[3] get_config scene=signup")
trk = ""
for ak in (APPKEY, "TSS.PC"):
    for sc in ("signup", "crawler_item", scene):
        st, j = post("/api/v4/anti_fraud/captcha/get_config",
                     {"app_key": ak, "scene": sc,
                      "client_id": cookies.get("SPC_CLIENTID", "")})
        err = j.get("error")
        tk = j.get("tracking_id") or ""
        log(f"  [{ak[:10]}|{sc}] {st} err={err} trk={len(tk)}B")
        if tk and err == 0:
            trk = tk
            open("/root/shopee-verify/TRK_SIGNUP.txt", "w").write(tk)
            log(f"  ✅ tracking dari scene={sc} appkey={ak[:10]}")
            break
    if trk:
        break

if not trk:
    log("  ⚠ get_config tidak beri tracking via Python (butuh x-sap)")
    # fallback: ambil dari file browser
    for f in ("TRK_SIGNUP.txt", "TRACKING.txt"):
        try:
            v = open(f"/root/shopee-verify/{f}").read().strip()
            if v:
                trk = v
                log(f"  pakai cadangan {f}: {len(v)}B")
                break
        except Exception:
            pass

# 4. generate dengan scene signup
cap = None
if trk:
    log("\n[4] generate scene=signup")
    for ak, sc in (("TSS.PC", scene), (APPKEY, scene),
                   ("TSS.PC", "signup"), (APPKEY, "signup")):
        p = {"app_key": ak, "scene": sc, "captcha_type": 1, "image_version": "",
             "client_id": cookies.get("SPC_CLIENTID", ""),
             "captcha_extra_info": {"tracking_id": trk}, "captcha_id": ""}
        st, j = post("/api/v4/anti_fraud/captcha/generate",
                     {"encrypted_data": enc(p)})
        jj = dec(j["encrypted_data"]) if j.get("encrypted_data") else j
        err = jj.get("error")
        data = jj.get("data") or {}
        log(f"  [{ak[:10]}|{sc}] err={err} cap_id={str(data.get('captcha_id', ''))[:22]}")
        if err == 0 and data.get("captcha_id"):
            cap = data
            log(f"  🎉 CAPTCHA! id={data['captcha_id'][:34]} type={data.get('captcha_type')}")
            json.dump(cap, open("/root/shopee-verify/SIGNUP_CAP.json", "w"), indent=1)
            break

# 5. solve + verify
ctok = ""
if cap:
    body = cap.get("captcha_body") or {}
    bg = body.get("bg_img") or ""
    pz = body.get("puzzle_img") or ""
    log(f"\n[5] solve bg={len(bg)}B pz={len(pz)}B")
    if bg.startswith("data:image"):
        os.makedirs("/root/shopee-verify/sgcap", exist_ok=True)
        for nm, v in (("bg", bg), ("pz", pz)):
            if v.startswith("data:image"):
                open(f"/root/shopee-verify/sgcap/{nm}.jpg", "wb").write(
                    base64.b64decode(v.split(",", 1)[1]))
        try:
            r = requests.post("https://www.sadcaptcha.com/api/v1/puzzle",
                              params={"licenseKey": SADKEY},
                              json={"puzzleImageB64": bg.split(",", 1)[1],
                                    "pieceImageB64": pz.split(",", 1)[1]}, timeout=60)
            log(f"  sad {r.status_code} {r.text[:100]}")
            if r.status_code == 200:
                prop = r.json().get("slideXProportion")
                log(f"  ★ prop={prop}")
                tgt = round((prop or 0) * 280, 1)
                t0 = int(time.time() * 1000)
                evs = []
                for i in range(20):
                    pr = (i + 1) / 20
                    e = pr * pr * (3 - 2 * pr)
                    evs.append([round(e * tgt, 1), round(0.4 * e * tgt, 1),
                                t0 + int(900 * pr), 1])
                evs.append([tgt, evs[-1][1], t0 + 1100, 2])
                ua = {"slider_start_timestamp": t0,
                      "slider_end_timestamp": t0 + 1100, "mouse_events": evs,
                      "touch_events": [], "device_orientation_events": [],
                      "captcha": {}, "audio": {}}
                log("\n[6] verify")
                pv = {"app_key": "TSS.PC", "scene": scene,
                      "captcha_type": cap.get("captcha_type"),
                      "captcha_answer": int(round(tgt)),
                      "user_action": json.dumps(ua), "phone": NEWPHONE,
                      "email": "", "username": "",
                      "captcha_extra_info": {"tracking_id": trk}}
                st, jv = post("/api/v4/anti_fraud/captcha/verify", {
                    "encrypted_data": enc(pv),
                    "encrypted_security_data": "", "dfp_token": ""})
                jjv = dec(jv["encrypted_data"]) if jv.get("encrypted_data") else jv
                log(f"  err={jjv.get('error')} {json.dumps(jjv)[:250]}")
                if jjv.get("error") == 0:
                    dd = jjv.get("data") or {}
                    ctok = dd.get("captcha_token") or dd.get("token") or ""
                    log(f"  🎉 captcha_token {len(ctok)}B")
        except Exception as e:
            log(f"  err {str(e)[:60]}")
else:
    log("\n[4] generate GAGAL semua skenario")

# 6. send_vcode
log("\n[7] otp/send_vcode")
for ch in [3, 2, 1]:
    body = {"phone": NEWPHONE, "channel": ch, "operation": 8, "seed": seed}
    if ctok:
        body["captcha_token"] = ctok
    st, j = post("/api/v4/otp/send_vcode", body)
    err = j.get("error")
    log(f"  ch={ch} err={err} {json.dumps(j)[:180]}")
    if err == 0:
        dd = j.get("data") or {}
        log(f"  ✅✅✅ OTP TERKIRIM ch={ch} tracking={str(dd.get('otp_tracking_id', ''))[:40]}")
        json.dump({"tracking": dd.get("otp_tracking_id"), "ch": ch, "seed": seed,
                   "seq": seq, "cp_tok": cp_tok},
                  open("/root/shopee-verify/OTP_SENT.json", "w"), indent=1)
        break
    time.sleep(3)

open("/root/shopee-verify/ck_signup_out.txt", "w").write(
    "; ".join(f"{k}={v}" for k, v in s.cookies.get_dict().items()))
log("\n=== SELESAI ===")
