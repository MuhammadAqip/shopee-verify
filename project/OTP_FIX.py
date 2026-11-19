"""OTP_FIX.py — flow LENGKAP dengan get_config dulu.

ck_1659: ivs_required=False. Sisa: captcha (scene signup) -> token -> OTP.

Urutan benar (dari cap_full_flow + get_config plaintext):
  1. change_phone_init -> seq
  2. change_phone_init_v2 -> cp_token (tanpa IVS)
  3. otp/get_settings_v2 -> need_captcha, scene, seed
  4. captcha/get_config (PLAINTEXT) -> tracking_id  <- WAJIB DULU
  5. captcha/generate + tracking_id -> captcha_id + images
  6. SadCaptcha /puzzle -> prop
  7. captcha/verify -> captcha_token
  8. send_vcode + captcha_token -> OTP
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
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/OTPF.log", "a").write(m + "\n")


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
    "referer": "https://shopee.co.id/", "accept": "application/json",
    "content-type": "application/json",
    "x-csrftoken": cookies.get("csrftoken", ""),
    "af-ac-enc-dat": "0123456789abcdef",
    "x-sz-sdk-version": "1.12.45"})


def post(p, b=None):
    r = s.post(f"https://shopee.co.id{p}", json=b or {}, timeout=50)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"_raw": r.text[:220]}


log(f"=== {cookies.get('SPC_U')} -> {NEWPHONE} ===")

log("\n[1] change_phone_init")
st, j = post("/api/v4/account/management/change_phone_init")
seq = (j.get("data") or {}).get("seq_no")
log(f"  err={j.get('error')} seq={seq}")

log("\n[2] change_phone_init_v2")
st, j = post("/api/v4/account/management/change_phone_init_v2",
             {"phone": NEWPHONE, "seq_no": seq})
d2 = j.get("data") or {}
cp_tok = d2.get("change_phone_token")
log(f"  err={j.get('error')} cp={len(cp_tok) if cp_tok else 0}B ivs_required={d2.get('ivs_required')}")

log("\n[3] otp/get_settings_v2")
st, j = post("/api/v4/otp/get_settings_v2", {"operation": 8, "phone": NEWPHONE})
d3 = j.get("data") or {}
seed = d3.get("seed")
scene = d3.get("captcha_scene") or "signup"
need = d3.get("need_captcha")
log(f"  err={j.get('error')} need_captcha={need} scene={scene} seed={seed}")
log(f"  channels={d3.get('available_channels')}")

# === 4. GET_CONFIG (PLAINTEXT) — WAJIB ===
log("\n[4] captcha/get_config")
tracking = ""
for body in ({"app_key": APPKEY, "scene": scene},
             {"app_key": APPKEY, "scene": scene,
              "client_id": cookies.get("SPC_CLIENTID", "")},
             {"app_key": APPKEY, "scene": "signup",
              "client_id": cookies.get("SPC_CLIENTID", "")}):
    st, j = post("/api/v4/anti_fraud/captcha/get_config", body)
    err = j.get("error")
    tk = j.get("tracking_id") or (j.get("data") or {}).get("tracking_id")
    log(f"  keys={list(body.keys())} err={err} trk={len(tk) if tk else 0}B")
    if tk:
        tracking = tk
        break
    if err == 0 and j.get("bundle_url"):
        log(f"  bundle={j.get('bundle_url', '')[-30:]}")

captcha_token = ""
if tracking:
    log("\n[5] captcha/generate")
    for ak, sc in (("TSS.PC", scene), (APPKEY, scene),
                   ("TSS.PC", "crawler_item"), (APPKEY, "crawler_item")):
        p = {"app_key": ak, "scene": sc, "captcha_type": 1, "image_version": "",
             "client_id": cookies.get("SPC_CLIENTID", ""),
             "captcha_extra_info": {"tracking_id": tracking}, "captcha_id": ""}
        st, j = post("/api/v4/anti_fraud/captcha/generate",
                     {"encrypted_data": enc(p)})
        jj = dec(j["encrypted_data"]) if j.get("encrypted_data") else j
        err = jj.get("error")
        log(f"  [{ak[:10]}|{sc}] err={err}")
        if err == 0 and (jj.get("data") or {}).get("captcha_id"):
            cap = jj["data"]
            log(f"  ✅ captcha_id={cap['captcha_id'][:34]} type={cap.get('captcha_type')}")
            json.dump(cap, open("/root/shopee-verify/FIX_CAP.json", "w"), indent=1)

            body = cap.get("captcha_body") or {}
            bg = body.get("bg_img") or ""
            pz = body.get("puzzle_img") or ""
            log(f"  bg={len(bg)}B pz={len(pz)}B")

            if bg.startswith("data:image"):
                os.makedirs("/root/shopee-verify/fixcap", exist_ok=True)
                for nm, v in (("bg", bg), ("pz", pz)):
                    if v.startswith("data:image"):
                        open(f"/root/shopee-verify/fixcap/{nm}.jpg", "wb").write(
                            base64.b64decode(v.split(",", 1)[1]))
                log("\n[6] SadCaptcha /puzzle")
                r = requests.post("https://www.sadcaptcha.com/api/v1/puzzle",
                                  params={"licenseKey": SADKEY},
                                  json={"puzzleImageB64": bg.split(",", 1)[1],
                                        "pieceImageB64": pz.split(",", 1)[1]},
                                  timeout=60)
                log(f"  {r.status_code} {r.text[:110]}")
                if r.status_code == 200:
                    prop = r.json().get("slideXProportion")
                    log(f"  ★ prop={prop}")
                    target = round((prop or 0) * 280, 1)
                    t0 = int(time.time() * 1000)
                    evs = []
                    for i in range(20):
                        pr = (i + 1) / 20
                        e = pr * pr * (3 - 2 * pr)
                        evs.append([round(e * target, 1), round(0.4 * e * target, 1),
                                    t0 + int(900 * pr), 1])
                    evs.append([target, evs[-1][1], t0 + 1100, 2])
                    ua = {"slider_start_timestamp": t0,
                          "slider_end_timestamp": t0 + 1100,
                          "mouse_events": evs, "touch_events": [],
                          "device_orientation_events": [],
                          "captcha": {}, "audio": {}}

                    log("\n[7] captcha/verify")
                    for ans in (int(round(target)), round(prop, 6),
                                int(round(target))):
                        pv = {"app_key": "TSS.PC", "scene": sc,
                              "captcha_type": cap.get("captcha_type"),
                              "captcha_answer": ans,
                              "user_action": json.dumps(ua),
                              "phone": NEWPHONE, "email": "", "username": "",
                              "captcha_extra_info": {"tracking_id": tracking}}
                        st, jv = post("/api/v4/anti_fraud/captcha/verify", {
                            "encrypted_data": enc(pv),
                            "encrypted_security_data": "",
                            "dfp_token": ""})
                        jjv = dec(jv["encrypted_data"]) if jv.get("encrypted_data") else jv
                        log(f"  ans={ans} err={jjv.get('error')} {json.dumps(jjv)[:200]}")
                        if jjv.get("error") == 0:
                            dd = jjv.get("data") or {}
                            captcha_token = (dd.get("captcha_token") or dd.get("token")
                                             or dd.get("verify_token") or "")
                            log(f"  🎉 captcha_token {len(captcha_token)}B")
                            break
            break

# === 8. send_vcode ===
log("\n[8] otp/send_vcode")
ok = False
for ch in [3, 2, 1]:
    body = {"phone": NEWPHONE, "channel": ch, "operation": 8, "seed": seed}
    if captcha_token:
        body["captcha_token"] = captcha_token
    st, j = post("/api/v4/otp/send_vcode", body)
    err = j.get("error")
    log(f"  ch={ch} err={err} {json.dumps(j)[:170]}")
    if err == 0:
        dd = j.get("data") or {}
        log(f"  ✅✅ OTP TERKIRIM ch={ch} tracking={dd.get('otp_tracking_id', '')[:40]}")
        json.dump({"tracking": dd.get("otp_tracking_id"), "ch": ch,
                   "seed": seed, "cp_tok": cp_tok, "seq": seq},
                  open("/root/shopee-verify/OTP_SENT.json", "w"), indent=1)
        ok = True
        break
    time.sleep(3)

if not ok:
    log("  ❌ gagal")

open("/root/shopee-verify/ck_otp_out.txt", "w").write(
    "; ".join(f"{k}={v}" for k, v in s.cookies.get_dict().items()))
log("\n=== SELESAI ===")
