"""OTP_CAPTCHA.py — kirim OTP dengan captcha_scene "signup".

Alur:
  1. change_phone_init -> seq_no
  2. change_phone_init_v2 -> ivs_utoken + cp_token
  3. otp/get_settings_v2 -> need_captcha, captcha_scene="signup", seed
  4. captcha/generate (scene dari get_settings_v2) -> captcha_id + bg/piece
  5. SadCaptcha /puzzle -> slideXProportion
  6. captcha/verify -> captcha_token
  7. otp/send_vcode + captcha_token -> OTP terkirim
  8. otp/verify_vcode -> commit
"""
import json, sys, time, os, base64, hashlib
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1553.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283191104601"
PROXY = "http://127.0.0.1:18080"
AESK = b"dRgUkXp2r5u8x/A?D(G+KbPeShVmYq3t"
SADKEY = open("/root/shopee-farm/bot_key.txt").read().strip()
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/OTPC.log", "a").write(m + "\n")


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
    "x-sz-sdk-version": "1.12.45",
})


def post(p, b=None, q=""):
    r = s.post(f"https://shopee.co.id{p}{q}", json=b or {}, timeout=50)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"_raw": r.text[:200]}


log(f"=== akun {cookies.get('SPC_U')} -> {NEWPHONE} ===")

# 1-2. init
log("\n[1] change_phone_init")
st, j = post("/api/v4/account/management/change_phone_init")
seq = (j.get("data") or {}).get("seq_no")
log(f"  err={j.get('error')} seq={seq}")

log("\n[2] change_phone_init_v2")
st, j = post("/api/v4/account/management/change_phone_init_v2",
             {"phone": NEWPHONE, "seq_no": seq})
d2 = j.get("data") or {}
cp_tok = d2.get("change_phone_token")
ivs_tok = d2.get("ivs_utoken")
log(f"  err={j.get('error')} cp={len(cp_tok) if cp_tok else 0}B ivs={len(ivs_tok) if ivs_tok else 0}B req={d2.get('ivs_required')}")

# 3. get_settings_v2 -> captcha config
log("\n[3] otp/get_settings_v2")
st, j = post("/api/v4/otp/get_settings_v2", {"operation": 8, "phone": NEWPHONE})
d3 = j.get("data") or {}
seed = d3.get("seed")
scene = d3.get("captcha_scene") or "signup"
need_cap = d3.get("need_captcha")
log(f"  err={j.get('error')} need_captcha={need_cap} scene={scene} seed={seed}")
log(f"  channels={d3.get('available_channels')} preferred={d3.get('preferred_channel')}")

captcha_token = ""

# 4. generate captcha (scene dari server)
if need_cap:
    log(f"\n[4] captcha/generate scene={scene}")
    param_sets = [
        {"app_key": "TSS.PC", "scene": scene},
        {"app_key": "f9ffc83459897a13dd14c537e84b1753", "scene": scene},
        {"app_key": "TSS.PC", "scene": "crawler_item"},
        {"app_key": "f9ffc83459897a13dd14c537e84b1753", "scene": "crawler_item"},
    ]
    cap = None
    for ps in param_sets:
        p = {"app_key": ps["app_key"], "scene": ps["scene"],
             "captcha_type": 1, "image_version": "",
             "client_id": cookies.get("SPC_CLIENTID", ""),
             "captcha_id": ""}
        st, j = post("/api/v4/anti_fraud/captcha/generate",
                     {"encrypted_data": enc(p)}, )
        jj = dec(j["encrypted_data"]) if j.get("encrypted_data") else j
        err = jj.get("error")
        log(f"  [{ps['app_key'][:12]}|{ps['scene']}] err={err}")
        if err == 0 and (jj.get("data") or {}).get("captcha_id"):
            cap = jj["data"]
            log(f"  ✅ captcha_id={cap['captcha_id'][:36]} type={cap.get('captcha_type')}")
            json.dump(cap, open("/root/shopee-verify/OTP_CAP.json", "w"), indent=1)
            break
        # simpan tracking untuk retry
        if jj.get("data", {}).get("tracking_id"):
            open("/root/shopee-verify/TRK2.txt", "w").write(jj["data"]["tracking_id"])

    # 5. solve dengan SadCaptcha
    if cap:
        body = cap.get("captcha_body") or {}
        bg = body.get("bg_img") or ""
        pz = body.get("puzzle_img") or ""
        log(f"\n[5] solve: bg={len(bg)}B puzzle={len(pz)}B")
        if bg.startswith("data:image"):
            os.makedirs("/root/shopee-verify/otpcap", exist_ok=True)
            for name, v in (("bg", bg), ("pz", pz)):
                if v.startswith("data:image"):
                    raw = base64.b64decode(v.split(",", 1)[1])
                    open(f"/root/shopee-verify/otpcap/{name}.jpg", "wb").write(raw)

            bgb = bg.split(",", 1)[1]
            pzb = pz.split(",", 1)[1] if pz.startswith("data:") else pz
            r = requests.post("https://www.sadcaptcha.com/api/v1/puzzle",
                              params={"licenseKey": SADKEY},
                              json={"puzzleImageB64": bgb, "pieceImageB64": pzb},
                              timeout=60)
            log(f"  SadCaptcha: {r.status_code} {r.text[:120]}")
            if r.status_code == 200:
                prop = r.json().get("slideXProportion")
                log(f"  ★ prop={prop}")
                # 6. verify
                log("\n[6] captcha/verify")
                W = 280
                target = round((prop or 0) * W, 1)
                t0 = int(time.time() * 1000)
                evs = []
                for i in range(20):
                    pr = (i + 1) / 20
                    e = pr * pr * (3 - 2 * pr)
                    evs.append([round(e * target, 1),
                                round(0.4 * e * target, 1),
                                t0 + int(900 * pr), 1])
                evs.append([target, evs[-1][1], t0 + 1100, 2])
                ua = {"slider_start_timestamp": t0, "slider_end_timestamp": t0 + 1100,
                      "mouse_events": evs, "touch_events": [],
                      "device_orientation_events": [], "captcha": {}, "audio": {}}
                pv = {"app_key": "TSS.PC", "scene": scene,
                      "captcha_type": cap.get("captcha_type"),
                      "captcha_answer": int(round(target)),
                      "user_action": json.dumps(ua),
                      "phone": NEWPHONE, "email": "", "username": "",
                      "captcha_extra_info": {"tracking_id": cap.get("tracking_id", "")}}
                st, jv = post("/api/v4/anti_fraud/captcha/verify", {
                    "encrypted_data": enc(pv),
                    "encrypted_security_data": "",
                    "dfp_token": ""})
                jjv = dec(jv["encrypted_data"]) if jv.get("encrypted_data") else jv
                log(f"  verify err={jjv.get('error')}")
                log(f"  {json.dumps(jjv)[:400]}")
                if jjv.get("error") == 0:
                    captcha_token = (jjv.get("data") or {}).get("captcha_token") or \
                                    (jjv.get("data") or {}).get("token") or ""
                    log(f"  🎉 captcha_token={len(captcha_token)}B")

# 7. send_vcode dengan captcha_token
log("\n[7] otp/send_vcode")
ok = False
for ch in [3, 1, 2]:
    body = {"phone": NEWPHONE, "channel": ch, "operation": 8, "seed": seed}
    if captcha_token:
        body["captcha_token"] = captcha_token
        body["captcha"] = captcha_token
    st, j = post("/api/v4/otp/send_vcode", body)
    log(f"  ch={ch} err={j.get('error')} {json.dumps(j)[:200]}")
    if j.get("error") == 0:
        dd = j.get("data") or {}
        log(f"  ✅ OTP TERKIRIM tracking={dd.get('otp_tracking_id', '')[:40]}")
        json.dump({"tracking": dd.get("otp_tracking_id"), "ch": ch, "seed": seed},
                  open("/root/shopee-verify/OTP_SENT.json", "w"), indent=1)
        ok = True
        break
    time.sleep(2)

if not ok:
    log("  ❌ semua channel gagal")

log("\n=== SELESAI ===")
