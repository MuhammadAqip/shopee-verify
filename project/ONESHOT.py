"""ONESHOT.py — SATU percobaan bersih, TANPA RETRY.

Temuan kunci:
  cap_correct.log  -> 31500000 (sudah issue)
  cap_correct2.log -> error:0 + captcha       (window baru)
  => 31500000 = state window, BUKAN payload salah
  => retry menghanguskan window -> 23500158

Aturan main:
  - generate SEKALI. Kalau error!=0, STOP (jangan retry).
  - verify SEKALI. Kalau token didapat, langsung send_vcode.
  - send_vcode sekali per channel, urut WA dulu.

Akun baru: ck_new234.txt (13489643217)
Nomor: 6282323737822

Steps:
  1. cek cookie hidup
  2. get_config lewat BROWSER -> tracking 1184B
  3. generate SEKALI (TSS.PC + crawler_item)
  4. kalau error:0 -> extract bg/puzzle -> SadCaptcha -> verify SEKALI
  5. token -> send_vcode WA
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
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/OS.log", "a").write(m + "\n")


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
            return {"_plain": raw[:200].decode("utf-8", "ignore")}
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
        return r.status_code, {"_raw": r.text[:200]}


log(f"=== {cookies.get('SPC_U')} -> {NEWPHONE} ===")

# === 1. sesi hidup? ===
st, j = s.get("https://shopee.co.id/api/v4/account/basic/get_account_info",
              timeout=40).json(), None
st, j = None, None
r = s.get("https://shopee.co.id/api/v4/account/basic/get_account_info", timeout=40)
j = r.json()
user = (j.get("data") or {}).get("username")
log(f"[1] account err={j.get('error')} user={user}")
if j.get("error") != 0:
    log("  ❌ cookie mati")
    sys.exit(1)

# === 2. init + settings (cek nomor masih bersih) ===
log("\n[2] change_phone_init")
st, j = post("/api/v4/account/management/change_phone_init")
seq = (j.get("data") or {}).get("seq_no")
log(f"  err={j.get('error')} seq={seq}")

st, j = post("/api/v4/account/management/change_phone_init_v2",
             {"phone": NEWPHONE, "seq_no": seq})
d2 = j.get("data") or {}
cp_tok = d2.get("change_phone_token")
log(f"  init2 err={j.get('error')} cp={len(cp_tok) if cp_tok else 0}B "
    f"ivs_required={d2.get('ivs_required')}")

log("\n[3] otp/get_settings_v2  (cek nomor bersih)")
st, j = post("/api/v4/otp/get_settings_v2", {"operation": 8, "phone": NEWPHONE})
d3 = j.get("data") or {}
seed = d3.get("seed")
scene = d3.get("captcha_scene") or "signup"
need = d3.get("need_captcha")
log(f"  err={j.get('error')} need_captcha={need} scene={scene}")
log(f"  seed={str(seed)[:24]} channels={d3.get('available_channels')} "
    f"preferred={d3.get('preferred_channel')}")

if j.get("error") not in (0, None):
    log(f"  ⛔ settings gagal ({j.get('error')}) — nomor/akun cooldown, STOP")
    sys.exit(1)

# === 4. get_config via BROWSER -> tracking ===
log("\n[4] get_config via browser (tracking)")
from playwright.sync_api import sync_playwright

TRK = {"v": ""}
capfiles = []
UA = s.headers["user-agent"]


def onresp(rr):
    u = rr.url
    if "get_config" in u:
        try:
            b = rr.text()
            jj = json.loads(b)
            if jj.get("tracking_id"):
                TRK["v"] = jj["tracking_id"]
                log(f"  ★ tracking {len(TRK['v'])}B")
                open("/root/shopee-verify/TRK_OS.txt", "w").write(TRK["v"])
        except Exception:
            pass
    if "captcha/generate" in u or "captcha/verify" in u:
        try:
            b = rr.text()
        except Exception:
            b = ""
        capfiles.append({"u": u.split("shopee.co.id")[-1][:70], "s": rr.status, "b": b[:2500]})
        log(f"  NET {rr.status} {u.split('shopee.co.id')[-1][:50]} :: {b[:110]}")


with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,900",
        "--disable-blink-features=AutomationControlled", "--lang=id-ID"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 900},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    ctx.add_cookies([{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
                     for k, v in cookies.items()])
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};"
        "Object.defineProperty(navigator,'languages',{get:()=>['id-ID','id','en']});")
    pg = ctx.new_page()
    pg.on("response", onresp)

    try:
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    pg.wait_for_timeout(10000)
    for sel in ('button:has-text("Setuju")', 'text=Bahasa Indonesia'):
        try:
            l = pg.locator(sel)
            if l.count() and l.first.is_visible():
                l.first.click(timeout=2000, force=True)
                pg.wait_for_timeout(1500)
        except Exception:
            pass

    # trigger cart/mini sekali -> SDK panggil get_config
    try:
        r2 = pg.evaluate("""async ()=>{
          try{const res=await fetch('/api/v4/cart/mini?need_buyer_dp_info=1',
            {credentials:'include'});const j=await res.json();
            return {err:j.error, six:j['6']};}catch(e){return {ex:String(e).slice(0,40)}}
        }""")
        log(f"  cart/mini: err={r2.get('err')}")
        six = r2.get("six") or {}
        if isinstance(six, dict) and six.get("0") and not TRK["v"]:
            TRK["v"] = six["0"]
            log(f"  ★ fallback tracking dari cart {len(TRK['v'])}B")
    except Exception:
        pass

    pg.wait_for_timeout(6000)
    if not TRK["v"]:
        try:
            pg.goto("https://shopee.co.id/verify/captcha",
                    wait_until="domcontentloaded", timeout=50000)
            pg.wait_for_timeout(9000)
        except Exception:
            pass

    ctx.storage_state(path="/root/shopee-verify/os_state.json")
    br.close()

if not TRK["v"]:
    log("  ❌ tidak dapat tracking — STOP")
    sys.exit(1)

log(f"  tracking final: {len(TRK['v'])}B  ({TRK['v'][:40]})")

# === 5. GENERATE SEKALI ===
log("\n[5] captcha/generate — SEKALI, tanpa retry")
p = {"app_key": "TSS.PC", "scene": "crawler_item", "captcha_type": 1,
     "image_version": "", "client_id": cookies.get("SPC_CLIENTID", ""),
     "captcha_extra_info": {"tracking_id": TRK["v"]}, "captcha_id": ""}
st, j = post("/api/v4/anti_fraud/captcha/generate",
             {"encrypted_data": enc(p)})
log(f"  http={st} keys={list(j.keys())}")

jj = dec(j["encrypted_data"]) if j.get("encrypted_data") else j
err = jj.get("error")
log(f"  error={err}")
log(f"  {json.dumps(jj)[:400]}")

if err != 0:
    log("  ⛔ generate gagal — STOP (jangan retry, biar window tidak hangus)")
    if err == 31500000:
        log("     31500000 = window tertutup. Tunggu 8-10 menit.")
    if err == 31500200:
        log("     31500200 = captcha valid tapi butuh encrypted_security_data (SDK).")
    sys.exit(2)

data = jj.get("data") or {}
cap_id = data.get("captcha_id")
body = data.get("captcha_body") or {}
bg = body.get("bg_img") or ""
pz = body.get("puzzle_img") or ""
log(f"  🎉 CAPTCHA! id={cap_id}")
log(f"     type={data.get('captcha_type')} sampling={data.get('sampling_frequency')}")
log(f"     bg={len(bg)}B puzzle={len(pz)}B")
json.dump(jj, open("/root/shopee-verify/OS_CAP.json", "w"), indent=1)

if not (bg.startswith("data:image") and pz.startswith("data:image")):
    log("  ⛔ gambar tidak valid — STOP")
    sys.exit(3)

# === 6. SOLVE ===
log("\n[6] SadCaptcha solve")
os.makedirs("/root/shopee-verify/oscap", exist_ok=True)
for nm, v in (("bg", bg), ("pz", pz)):
    open(f"/root/shopee-verify/oscap/{nm}.jpg", "wb").write(
        base64.b64decode(v.split(",", 1)[1]))

try:
    r3 = requests.post("https://www.sadcaptcha.com/api/v1/puzzle",
                       params={"licenseKey": SADKEY},
                       json={"puzzleImageB64": bg.split(",", 1)[1],
                             "pieceImageB64": pz.split(",", 1)[1]}, timeout=70)
    log(f"  {r3.status_code} {r3.text[:120]}")
    prop = r3.json().get("slideXProportion") if r3.status_code == 200 else None
except Exception as e:
    log(f"  err {str(e)[:60]}")
    prop = None

if prop is None:
    log("  ⛔ solve gagal — STOP")
    sys.exit(4)

log(f"  ★ slideXProportion={prop}")

# === 7. VERIFY SEKALI ===
W = 280
target = round(prop * W, 1)
t0 = int(time.time() * 1000)
evs = []
for i in range(20):
    pr = (i + 1) / 20
    e = pr * pr * (3 - 2 * pr)
    ts = t0 + int(900 * pr)
    evs.append([round(e * target, 1), round(0.35 * e * target, 1), ts, 1])
evs.append([target, evs[-1][1], t0 + 1180, 2])

ua = {"slider_start_timestamp": t0, "slider_end_timestamp": t0 + 1180,
      "mouse_events": evs, "touch_events": [],
      "device_orientation_events": [], "captcha": {}, "audio": {}}

pv = {"app_key": "TSS.PC", "scene": "crawler_item",
      "captcha_type": data.get("captcha_type"),
      "captcha_answer": int(round(target)),
      "user_action": json.dumps(ua),
      "phone": NEWPHONE, "email": "", "username": user or "",
      "captcha_extra_info": {"tracking_id": TRK["v"]},
      "captcha_id": cap_id}

log(f"\n[7] captcha/verify — SEKALI  (answer={int(round(target))}px)")
st, jv = post("/api/v4/anti_fraud/captcha/verify", {
    "encrypted_data": enc(pv),
    "encrypted_security_data": "",
    "dfp_token": ""})
jjv = dec(jv["encrypted_data"]) if jv.get("encrypted_data") else jv
log(f"  http={st} error={jjv.get('error')}")
log(f"  {json.dumps(jjv)[:400]}")

ctok = ""
if jjv.get("error") == 0:
    dd = jjv.get("data") or {}
    ctok = dd.get("captcha_token") or dd.get("token") or dd.get("verify_token") or ""
    log(f"  🎉🎉 captcha_token {len(ctok)}B")
else:
    log("  ⛔ verify gagal — STOP (tanpa retry)")

# === 8. SEND VCODE WA ===
log("\n[8] otp/send_vcode — WA (ch3) dulu")
for ch in ([3] + ([2, 1] if not ctok else [])) if True else []:
    body = {"phone": NEWPHONE, "channel": ch, "operation": 8, "seed": seed}
    if ctok:
        body["captcha_token"] = ctok
    st, j2 = post("/api/v4/otp/send_vcode", body)
    err2 = j2.get("error")
    log(f"  ch={ch} err={err2} {json.dumps(j2)[:200]}")
    if err2 == 0:
        dd = j2.get("data") or {}
        log(f"  ✅✅✅ OTP TERKIRIM ke {NEWPHONE} via ch={ch}")
        log(f"      otp_tracking_id={dd.get('otp_tracking_id')}")
        json.dump({"phone": NEWPHONE, "ch": ch, "seed": seed,
                   "tracking": dd.get("otp_tracking_id"),
                   "seq": seq, "cp_tok": cp_tok, "captcha_token": ctok},
                  open("/root/shopee-verify/OTP_SENT.json", "w"), indent=1)
        break
    if ch == 3 and not ctok:
        log("     23500101 = butuh captcha_token; lanjut ch2/ch1 tanpa token")
    time.sleep(2)

log("\n=== SELESAI ===")
