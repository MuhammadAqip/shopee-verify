"""RANDOM_NONCE.py — fix af-ac-enc-dat jadi RANDOM 8-byte hex.

Ditemukan di sfu-stable.js:
  function B(){
    var t = hexEncode(8 random bytes);
    return {"af-ac-enc-dat": t};
  }

Selama ini gue pakai "0123456789abcdef" statis = SALAH.
SDK asli generate nonce baru tiap request.

Pipeline:
  1. browser: ambil SEC + DFP
  2. requests: generate + verify DENGAN nonce random per request
  3. cek apakah 31500200 hilang
"""
import json, sys, time, base64, os, secrets
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_zax.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283829322571"
PROXY = os.environ.get("SHOPEE_PROXY", "")
AESK = b"dRgUkXp2r5u8x/A?D(G+KbPeShVmYq3t"
SADKEY = open("/root/shopee-farm/bot_key.txt").read().strip()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/RN.log", "a").write(m + "\n")


def evp(pw, salt):
    d, prev = b"", b""
    while len(d) < 48:
        prev = hashlib.md5(prev + pw + salt).digest()
        d += prev
    return d[:32], d[32:48]


import hashlib


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


def nonce():
    """8 random bytes -> hex (sesuai SDK function B())."""
    return secrets.token_hex(8)


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
    "x-csrftoken": cookies.get("csrftoken", ""),
    "x-sz-sdk-version": "1.12.45"})


def post(p, b=None, extra=None):
    h = {"af-ac-enc-dat": nonce()}   # ← RANDOM per request!
    if extra:
        h.update(extra)
    r = s.post(f"https://shopee.co.id{p}", json=b or {}, headers=h, timeout=50)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"_raw": r.text[:200]}


def get(p, extra=None):
    h = {"af-ac-enc-dat": nonce()}
    if extra:
        h.update(extra)
    r = s.get(f"https://shopee.co.id{p}", headers=h, timeout=50)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"_raw": r.text[:200]}


log(f"=== {cookies.get('SPC_U')} -> {NEWPHONE} ===")
log(f"  proxy: {PROXY or 'DIRECT'}")

# === 1. cek sesi ===
st, j = get("/api/v4/account/basic/get_account_info")
log(f"[1] account err={j.get('error')} user={(j.get('data') or {}).get('username')}")
if j.get("error") != 0:
    log("  ❌ cookie mati")
    sys.exit(1)

# === 2. ambil SEC + DFP via browser ===
log("\n[2] browser: SEC + DFP")
from playwright.sync_api import sync_playwright

cookies_pw = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
              for k, v in cookies.items()]

EXTRACT = r"""
(async () => {
  const out = {sec:null, dfp:null, err:null};
  try{
    const wc = window.webpackChunkshopee_pc;
    if(!wc){out.err='no_chunk';return out;}
    let req=null; wc.push([[('rn'+Date.now())],{},function(rr){req=rr;}]);
    if(!req){out.err='no_req';return out;}
    const m = req(16223);
    if(!m){out.err='no_16223';return out;}
    try{
      const v=await Promise.race([m.getLongToken(),
        new Promise((_,rj)=>setTimeout(()=>rj(new Error('to')),8000))]);
      if(typeof v==='string'&&v.length>100) out.sec=v;
    }catch(e){}
    try{
      const v=await Promise.race([m.getWebDeviceFingerprint(),
        new Promise((_,rj)=>setTimeout(()=>rj(new Error('to')),8000))]);
      const s=(typeof v==='string')?v:JSON.stringify(v);
      if(s&&s.length>4) out.dfp=s;
    }catch(e){}
    return out;
  }catch(e){out.err=String(e).slice(0,150);return out;}
})()
"""

SEC = DFP = ""
with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,900",
        "--disable-blink-features=AutomationControlled", "--lang=id-ID"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 900},
                         timezone_id="Asia/Jakarta",
                         proxy={"server": PROXY} if PROXY else None)
    ctx.add_cookies(cookies_pw)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};")
    pg = ctx.new_page()
    try:
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    pg.wait_for_timeout(12000)
    r = pg.evaluate(EXTRACT)
    SEC = r.get("sec") or ""
    DFP = r.get("dfp") or ""
    log(f"  SEC {len(SEC)}B | DFP {len(DFP)}B | err={r.get('err')}")
    br.close()

if len(SEC) < 100:
    log("  ❌ SEC gagal")
    sys.exit(2)

# === 3. settings ===
log("\n[3] get_settings_v2")
st, j = post("/api/v4/otp/get_settings_v2", {"operation": 8, "phone": NEWPHONE})
d = j.get("data") or {}
seed = d.get("seed")
log(f"  err={j.get('error')} channels={d.get('available_channels')} "
    f"scene={d.get('captcha_scene')}")
if j.get("error") not in (0, None):
    log("  ⛔ cooldown")
    sys.exit(3)

# === 4. init_v2 ===
log("\n[4] change_phone_init_v2")
st, j = post("/api/v4/account/management/change_phone_init_v2",
             {"phone": NEWPHONE, "seq_no": None})
log(f"  err={j.get('error')} ivs={(j.get('data') or {}).get('ivs_required')}")

# === 5. get_config (tracking) ===
log("\n[5] get_config")
st, jc = post("/api/v4/anti_fraud/captcha/get_config",
              {"app_key": "f9ffc83459897a13dd14c537e84b1753",
               "scene": "crawler_item", "tracking_id": ""})
TRK = jc.get("tracking_id") or ""
log(f"  err={jc.get('error')} tracking {len(TRK)}B")

# === 6. generate dengan RANDOM nonce ===
log("\n[6] generate — nonce RANDOM")
p = {"app_key": "FlashSale.PC", "scene": "crawler_item", "captcha_type": 1,
     "image_version": "", "client_id": cookies.get("SPC_CLIENTID", ""),
     "captcha_extra_info": {"tracking_id": TRK}, "captcha_id": ""}
st, jg = post("/api/v4/anti_fraud/captcha/generate", {"encrypted_data": enc(p)})
jjg = dec(jg["encrypted_data"]) if jg.get("encrypted_data") else jg
err = jjg.get("error")
data = jjg.get("data") or {}
body = data.get("captcha_body") or {}
log(f"  err={err} id={str(data.get('captcha_id',''))[:36]} type={data.get('captcha_type')}")
log(f"  bg={len(body.get('bg_img') or '')}B pz={len(body.get('puzzle_img') or '')}B")

if err != 0 or not body.get("bg_img"):
    log(f"  ⛔ generate gagal ({err})")
    sys.exit(4)

CAPID = data.get("captcha_id")
TRKU = data.get("tracking_id")
CTYPE = data.get("captcha_type")
SAMPL = data.get("sampling_frequency") or 20
YC = body.get("y_coordinate") or 0
bg = body["bg_img"]
pz = body["puzzle_img"]
json.dump(jjg, open("/root/shopee-verify/RN_CAP.json", "w"), indent=1)

# === 7. solve ===
log("\n[7] SadCaptcha")
prop = None
try:
    rr = requests.post("https://www.sadcaptcha.com/api/v1/puzzle",
                       params={"licenseKey": SADKEY},
                       json={"puzzleImageB64": bg.split(",", 1)[1],
                             "pieceImageB64": pz.split(",", 1)[1]}, timeout=75)
    log(f"  {rr.status_code} {rr.text[:100]}")
    if rr.status_code == 200:
        prop = rr.json().get("slideXProportion")
except Exception as e:
    log(f"  err {str(e)[:50]}")

if prop is None:
    log("  ⛔ solve gagal")
    sys.exit(5)

W = 280
tx = round(prop * W, 1)
log(f"  prop={prop} x={tx} y={YC}")

# === 8. verify dengan nonce random + SEC + DFP ===
t0 = int(time.time() * 1000)
evs = []
STEPS = max(20, SAMPL)
for i in range(STEPS):
    pr = (i + 1) / STEPS
    e = pr * pr * (3 - 2 * pr)
    evs.append([round(e * tx, 1), round(e * YC, 1), t0 + int(900 * pr), 1])
evs.append([tx, YC, t0 + 1180, 2])

ua = {"slider_start_timestamp": t0, "slider_end_timestamp": t0 + 1180,
      "mouse_events": evs, "touch_events": [],
      "device_orientation_events": [],
      "captcha": {"slider_start_timestamp": t0,
                  "slider_end_timestamp": t0 + 1180,
                  "has_slidable_puzzle": True},
      "audio": {}}

pv = {"app_key": "FlashSale.PC", "scene": "crawler_item",
      "captcha_type": CTYPE,
      "captcha_answer": {"captcha_id": CAPID,
                         "slider": {"x_pixels": int(round(tx))}},
      "user_action": json.dumps(ua),
      "phone": NEWPHONE, "email": "", "username": "",
      "encrypted_security_data": SEC,
      "dfp_token": DFP,
      "tracking_id": TRKU}

log(f"\n[8] verify — nonce random")
log(f"  jarak SEC->verify: {time.time()-T0:.1f}s (limit 180s)")
st, jv = post("/api/v4/anti_fraud/captcha/verify", {
    "encrypted_data": enc(pv),
    "encrypted_security_data": SEC,
    "dfp_token": DFP})
jjv = dec(jv["encrypted_data"]) if jv.get("encrypted_data") else jv
errv = jjv.get("error")
log(f"  err={errv}  {json.dumps(jjv)[:250]}")

if errv != 0:
    log("  ⛔ verify gagal")
    sys.exit(6)

dd = jjv.get("data") or {}
tok = dd.get("captcha_token") or dd.get("token") or dd.get("signature") or ""
log(f"  🎉🎉🎉 TOKEN {len(str(tok))}B")

# === 9. send_vcode ===
log("\n[9] send_vcode WA")
for ch in (3, 2, 1):
    b = {"phone": NEWPHONE, "channel": ch, "operation": 8, "seed": seed,
         "captcha_token": tok}
    st, j3 = post("/api/v4/otp/send_vcode", b)
    log(f"  ch={ch} err={j3.get('error')} {json.dumps(j3)[:150]}")
    if j3.get("error") == 0:
        d3 = j3.get("data") or {}
        log(f"\n  ✅✅✅✅ OTP TERKIRIM ch={ch} tracking={d3.get('otp_tracking_id')}")
        json.dump({"phone": NEWPHONE, "ch": ch, "seed": seed,
                   "tracking": d3.get("otp_tracking_id")},
                  open("/root/shopee-verify/OTP_SENT.json", "w"), indent=1)
        break
    time.sleep(2)

log("\n=== SELESAI ===")
