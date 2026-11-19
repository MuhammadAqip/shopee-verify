"""FINAL_OTP.py — verify captcha DENGAN encrypted_security_data + dfp_token.

Pipeline lengkap:
  1. browser: getLongToken() + getWebDeviceFingerprint() -> SEC + DFP
  2. generate captcha (FlashSale.PC, tracking dari get_config)
  3. SadCaptcha solve
  4. verify dengan SEC + DFP  <- KUNCI
  5. send_vcode WA

Semua dalam satu run. Tanpa retry.
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
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/FO.log", "a").write(m + "\n")


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
    "user-agent": UA, "x-api-source": "pc",
    "x-requested-with": "XMLHttpRequest",
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

# === [A] browser: SEC + DFP + TRACKING ===
log("\n[A] browser: getLongToken + getWebDeviceFingerprint + tracking")
from playwright.sync_api import sync_playwright

EXTRACT = r"""
(async () => {
  const out = {sec:null, dfp:null, trk:null, trkShort:null, err:null};
  try{
    const wc = window.webpackChunkshopee_pc;
    if(!wc){out.err='no_chunk';return out;}
    let req=null; wc.push([[('f'+Date.now())],{},function(r){req=r;}]);
    if(!req){out.err='no_req';return out;}
    const m = req(16223);
    if(!m){out.err='no_16223';return out;}
    // sec
    try{
      const v=await Promise.race([m.getLongToken(),
        new Promise((_,rj)=>setTimeout(()=>rj(new Error('to')),9000))]);
      if(typeof v==='string'&&v.length>100) out.sec=v;
    }catch(e){}
    // dfp
    try{
      const v=await Promise.race([m.getWebDeviceFingerprint(),
        new Promise((_,rj)=>setTimeout(()=>rj(new Error('to')),9000))]);
      const s=(typeof v==='string')?v:JSON.stringify(v);
      if(s&&s.length>4) out.dfp=s;
    }catch(e){}
    // tracking dari sessionStorage
    try{
      out.trk = sessionStorage.getItem('@shopee-ac/tracking_id');
      out.trkShort = sessionStorage.getItem('@shopee/antifraud/captcha-tracking-id');
    }catch(e){}
    return out;
  }catch(e){out.err=String(e).slice(0,150);return out;}
})()
"""

TRK = {"long": "", "short": ""}


def onresp(r):
    u = r.url
    if "get_config" in u:
        try:
            j = r.json()
            if j.get("tracking_id"):
                TRK["long"] = j["tracking_id"]
                log(f"  net get_config tracking {len(TRK['long'])}B")
        except Exception:
            pass


SEC = ""
DFP = ""

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
    pg.wait_for_timeout(14000)
    for sel in ('button:has-text("Setuju")', 'text=Bahasa Indonesia'):
        try:
            l = pg.locator(sel)
            if l.count() and l.first.is_visible():
                l.first.click(timeout=2000, force=True)
                pg.wait_for_timeout(1200)
        except Exception:
            pass
    try:
        pg.evaluate("""async ()=>{try{await fetch('/api/v4/cart/mini?need_buyer_dp_info=1',
          {credentials:'include'});}catch(e){}}""")
    except Exception:
        pass
    pg.wait_for_timeout(12000)

    r = pg.evaluate(EXTRACT)
    SEC = r.get("sec") or ""
    DFP = r.get("dfp") or ""
    if not TRK["long"] and r.get("trk"):
        TRK["long"] = r["trk"]
    if r.get("trkShort"):
        TRK["short"] = r["trkShort"]

    log(f"  SEC {len(SEC)}B | DFP {len(DFP)}B")
    log(f"  TRK long {len(TRK['long'])}B | short {len(TRK['short'])}B")
    log(f"  DFP val: {DFP[:120]}")
    br.close()

if len(SEC) < 100 or len(DFP) < 10:
    log("  ❌ token tidak lengkap")
    sys.exit(1)

# === [B] settings ===
log("\n[B] otp/get_settings_v2")
st, j = post("/api/v4/otp/get_settings_v2", {"operation": 8, "phone": NEWPHONE})
d = j.get("data") or {}
seed = d.get("seed")
scene = d.get("captcha_scene") or "signup"
log(f"  err={j.get('error')} scene={scene} channels={d.get('available_channels')} "
    f"preferred={d.get('preferred_channel')}")
if j.get("error") not in (0, None):
    log("  ⛔ cooldown — STOP")
    sys.exit(2)

# === [C] generate captcha ===
log("\n[C] captcha/generate")
p = {"app_key": "FlashSale.PC", "scene": "crawler_item", "captcha_type": 1,
     "image_version": "", "client_id": cookies.get("SPC_CLIENTID", ""),
     "captcha_extra_info": {"tracking_id": TRK["long"]}, "captcha_id": ""}
st, jg = post("/api/v4/anti_fraud/captcha/generate",
              {"encrypted_data": enc(p)})
jjg = dec(jg["encrypted_data"]) if jg.get("encrypted_data") else jg
err = jjg.get("error")
data = jjg.get("data") or {}
body = data.get("captcha_body") or {}
log(f"  err={err} id={str(data.get('captcha_id',''))[:40]} type={data.get('captcha_type')}")
log(f"  bg={len(body.get('bg_img') or '')}B pz={len(body.get('puzzle_img') or '')}B")

if err != 0 or not body.get("bg_img"):
    log("  ⛔ generate gagal — STOP")
    sys.exit(3)

json.dump(jjg, open("/root/shopee-verify/FO_CAP.json", "w"), indent=1)

CAPID = data.get("captcha_id")
TRKU = data.get("tracking_id")
CTYPE = data.get("captcha_type")
SAMPL = data.get("sampling_frequency") or 20
YC = body.get("y_coordinate")
bg = body["bg_img"]
pz = body["puzzle_img"]

# === [D] solve ===
log("\n[D] SadCaptcha")
prop = None
try:
    rr = requests.post("https://www.sadcaptcha.com/api/v1/puzzle",
                       params={"licenseKey": SADKEY},
                       json={"puzzleImageB64": bg.split(",", 1)[1],
                             "pieceImageB64": pz.split(",", 1)[1]}, timeout=75)
    log(f"  {rr.status_code} {rr.text[:110]}")
    if rr.status_code == 200:
        prop = rr.json().get("slideXProportion")
except Exception as e:
    log(f"  err {str(e)[:60]}")

if prop is None:
    log("  ⛔ solve gagal — STOP")
    sys.exit(4)

W = 280
tx = round(prop * W, 1)
ty = YC if YC is not None else 0
log(f"  prop={prop} -> x={tx} y={ty}")

# === [E] verify dengan SEC + DFP ===
log("\n[E] captcha/verify — SEC + DFP")
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
      "device_orientation_events": [],
      "captcha": {"slider_start_timestamp": t0,
                  "slider_end_timestamp": t0 + 1180,
                  "has_slidable_puzzle": True},
      "audio": {}}

# captcha_answer = OBJECT (dari 063.js):
#   {captcha_id, slider:{x_pixels}, animated:{chars}, audio}
ANSWER = {
    "captcha_id": CAPID,
    "slider": {"x_pixels": int(round(tx))},
}

pv = {"app_key": "FlashSale.PC", "scene": "crawler_item",
      "captcha_type": CTYPE, "captcha_answer": ANSWER,
      "user_action": json.dumps(ua),
      "phone": NEWPHONE, "email": "",
      "username": "",
      "encrypted_security_data": SEC,
      "dfp_token": DFP,
      "tracking_id": TRKU}

st, jv = post("/api/v4/anti_fraud/captcha/verify", {
    "encrypted_data": enc(pv),
    "encrypted_security_data": SEC,
    "dfp_token": DFP})
jjv = dec(jv["encrypted_data"]) if jv.get("encrypted_data") else jv
errv = jjv.get("error")
log(f"  err={errv}")
log(f"  {json.dumps(jjv)[:350]}")

# kalau gagal, coba verify_v2
if errv != 0:
    log("\n[E2] coba verify_v2")
    st2, jv2 = post("/api/v4/anti_fraud/captcha/verify_v2", {
        "encrypted_data": enc(pv),
        "encrypted_security_data": SEC,
        "dfp_token": DFP})
    jj2 = dec(jv2["encrypted_data"]) if jv2.get("encrypted_data") else jv2
    log(f"  v2 err={jj2.get('error')} {json.dumps(jj2)[:250]}")
    if jj2.get("error") == 0:
        jjv = jj2
        errv = 0

if errv != 0:
    log("  ⛔ verify gagal — STOP")
    sys.exit(5)

dd = jjv.get("data") or {}
ctok = dd.get("captcha_token") or dd.get("token") or dd.get("verify_token") or ""
log(f"  🎉🎉🎉 captcha_token {len(ctok)}B")
json.dump({"token": ctok, "raw": jjv}, open("/root/shopee-verify/FO_CTOK.json", "w"), indent=1)

# === [F] send vcode ===
log("\n[F] send_vcode WA")
for ch in (3, 2, 1):
    b = {"phone": NEWPHONE, "channel": ch, "operation": 8, "seed": seed}
    if ctok:
        b["captcha_token"] = ctok
    st3, j3 = post("/api/v4/otp/send_vcode", b)
    log(f"  ch={ch} err={j3.get('error')} {json.dumps(j3)[:180]}")
    if j3.get("error") == 0:
        d3 = j3.get("data") or {}
        log(f"\n  ✅✅✅✅ OTP TERKIRIM ke {NEWPHONE} via ch={ch}")
        log(f"      otp_tracking_id = {d3.get('otp_tracking_id')}")
        json.dump({"phone": NEWPHONE, "ch": ch, "seed": seed,
                   "otp_tracking_id": d3.get("otp_tracking_id"),
                   "captcha_token": ctok, "sec": SEC, "dfp": DFP},
                  open("/root/shopee-verify/OTP_SENT.json", "w"), indent=1)
        break
    time.sleep(2)

log("\n=== SELESAI ===")
