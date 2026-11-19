"""VERIFY_FIX.py — verify dengan tracking_id UUID (bukan 1184B).

Kesalahan utama sepanjang ini:
  captcha_extra_info.tracking_id = TRK 1184B  (SALAH)
  captcha_extra_info.tracking_id = data.tracking_id UUID  (BENAR)

Dari OS_CAP2.json:
  captcha_id   = 295f48f1c0d-88e5-41d9-9484-b3e9983baae5-6afe5eb8
  data.tracking_id = 295f48f1c0d-88e5-41d9-9484-b3e9983baae5   <- PAKAI INI

captcha_type 11 = dragdrop
  y_coordinate = 27  (target Y)
  transform_text = ['label_captcha_dragdrop_instr_0']
"""
import json, sys, time, os, base64, hashlib
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_new234.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6282323737822"
CAPF = sys.argv[3] if len(sys.argv) > 3 else "OS_CAP2.json"
PROXY = "http://127.0.0.1:18080"
AESK = b"dRgUkXp2r5u8x/A?D(G+KbPeShVmYq3t"
SADKEY = open("/root/shopee-farm/bot_key.txt").read().strip()
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):3d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/VF.log", "a").write(m + "\n")


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
    r = s.post(f"https://shopee.co.id{p}", json=b or {}, timeout=50)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"_raw": r.text[:200]}


# === load captcha ===
cap = json.load(open(CAPF))
dd = cap.get("data") or {}
body = dd.get("captcha_body") or {}

CAPID = dd.get("captcha_id")            # 54 char dengan suffix
TRKU = dd.get("tracking_id")            # 36 char UUID  <-- KUNCI
CTYPE = dd.get("captcha_type")
SAMPL = dd.get("sampling_frequency") or 20
YC = body.get("y_coordinate")
bg = body.get("bg_img") or ""
pz = body.get("puzzle_img") or ""

log(f"=== verify fix ===")
log(f"  captcha_id  = {CAPID}")
log(f"  tracking_id = {TRKU}   <-- UUID, bukan 1184B")
log(f"  type={CTYPE} sampling={SAMPL} y_coordinate={YC}")
log(f"  bg={len(bg)}B pz={len(pz)}B")

if not (bg.startswith("data:image") and pz.startswith("data:image")):
    log("  ❌ gambar tidak ada")
    sys.exit(1)

# === solve ===
log("\n[solve] SadCaptcha")
os.makedirs("/root/shopee-verify/vfcap", exist_ok=True)
for nm, v in (("bg", bg), ("pz", pz)):
    open(f"/root/shopee-verify/vfcap/{nm}.jpg", "wb").write(
        base64.b64decode(v.split(",", 1)[1]))

prop = None
for ep in ("/puzzle", "/shopee-image-drag", "/pre-analyze"):
    try:
        r = requests.post(f"https://www.sadcaptcha.com/api/v1{ep}",
                          params={"licenseKey": SADKEY},
                          json={"puzzleImageB64": bg.split(",", 1)[1],
                                "pieceImageB64": pz.split(",", 1)[1]}, timeout=70)
        log(f"  {ep} {r.status_code} {r.text[:110]}")
        if r.status_code == 200:
            j = r.json()
            p = j.get("slideXProportion")
            if p is not None:
                prop = p
                log(f"  ★ prop={p}")
                break
    except Exception as e:
        log(f"  {ep} err {str(e)[:50]}")

if prop is None:
    log("  ❌ solve gagal")
    sys.exit(2)

# === hitung target ===
W = 280
tx = round(prop * W, 1)
ty = YC if YC is not None else 0
log(f"\n  target x={tx} y={ty}")

# === build trajectory ===
t0 = int(time.time() * 1000)
evs = []
STEPS = max(20, SAMPL)
for i in range(STEPS):
    pr = (i + 1) / STEPS
    e = pr * pr * (3 - 2 * pr)
    ts = t0 + int(900 * pr)
    evs.append([round(e * tx, 1), round(e * ty, 1), ts, 1])
evs.append([tx, ty, t0 + 1180, 2])

ua = {"slider_start_timestamp": t0, "slider_end_timestamp": t0 + 1180,
      "mouse_events": evs, "touch_events": [],
      "device_orientation_events": [], "captcha": {}, "audio": {}}

# === verify — coba beberapa bentuk payload ===
log("\n[verify]")
BASE = {
    "app_key": "FlashSale.PC",
    "scene": "crawler_item",
    "captcha_type": CTYPE,
    "captcha_answer": int(round(tx)),
    "user_action": json.dumps(ua),
    "phone": NEWPHONE, "email": "", "username": "",
    "captcha_extra_info": {"tracking_id": TRKU},
    "captcha_id": CAPID,
}

VARIANTS = [
    ("base+sec+dfp-empty", dict(BASE), ""),
    ("y-coord", {**BASE, "captcha_answer":
                 json.dumps({"x": int(round(tx)), "y": int(round(ty))})}, ""),
    ("answer-obj", {**BASE, "captcha_answer":
                    {"x": round(prop, 6), "y": ty}}, ""),
    ("no-captcha-id", {k: v for k, v in BASE.items() if k != "captcha_id"}, ""),
]

for nm, pv, sec in VARIANTS:
    st, jv = post("/api/v4/anti_fraud/captcha/verify", {
        "encrypted_data": enc(pv),
        "encrypted_security_data": sec,
        "dfp_token": ""})
    jjv = dec(jv["encrypted_data"]) if jv.get("encrypted_data") else jv
    err = jjv.get("error")
    log(f"  [{nm}] http={st} err={err} {json.dumps(jjv)[:200]}")
    if err == 0:
        d = jjv.get("data") or {}
        tok = d.get("captcha_token") or d.get("token") or d.get("verify_token") or ""
        log(f"  🎉🎉🎉 captcha_token {len(tok)}B")
        json.dump({"token": tok, "raw": jjv}, open("/root/shopee-verify/CTOK.json", "w"), indent=1)

        # send vcode
        log("\n[send_vcode WA]")
        st2, j2 = post("/api/v4/otp/get_settings_v2",
                       {"operation": 8, "phone": NEWPHONE})
        seed = (j2.get("data") or {}).get("seed")
        for ch in (3, 2, 1):
            b = {"phone": NEWPHONE, "channel": ch, "operation": 8,
                 "seed": seed, "captcha_token": tok}
            st3, j3 = post("/api/v4/otp/send_vcode", b)
            log(f"  ch={ch} err={j3.get('error')} {json.dumps(j3)[:160]}")
            if j3.get("error") == 0:
                d3 = j3.get("data") or {}
                log(f"  ✅✅✅ OTP TERKIRIM ch={ch} tracking={d3.get('otp_tracking_id')}")
                json.dump({"phone": NEWPHONE, "ch": ch, "seed": seed,
                           "tracking": d3.get("otp_tracking_id"),
                           "captcha_token": tok},
                          open("/root/shopee-verify/OTP_SENT.json", "w"), indent=1)
                break
            time.sleep(2)
        break
    if err == 31500200:
        log("     31500200 = perlu encrypted_security_data + dfp_token asli")

log("\n=== SELESAI ===")
