"""sec_dump2.py — buka /verify/captcha dengan param LENGKAP, hook SDK.

Dari ivs_js/078.js es():
  /verify/traffic?tracking_id=...&is_logged_in=...&home_url=...
                   &app_key=...&scene=...&client_id=...
                   &redirect_type=...&next=...&should_replace_history=...

Tanpa param itu halaman kosong.
"""
import json, sys, time, urllib.parse

sys.path.insert(0, "/root/shopee-farm")

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1553.txt"
MAXT = int(sys.argv[2]) if len(sys.argv) > 2 else 190

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
OUT = "/root/shopee-verify/sec_dump2.json"
APPKEY = "f9ffc83459897a13dd14c537e84b1753"
T0 = time.time()


def log(*a):
    print(f"[{int(time.time()-T0):3d}s]", *a, flush=True)


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]
cmap = {c["name"]: c["value"] for c in cookies}
client_id = cmap.get("SPC_CLIENTID", "")

try:
    tracking = open("TRACKING.txt").read().strip()
except Exception:
    tracking = ""

q = urllib.parse.urlencode({
    "is_initial": "true",
    "app_key": APPKEY,
    "scene": "crawler_item",
    "client_id": client_id,
    "redirect_type": "1",
    "next": "https://shopee.co.id/",
    "should_replace_history": "true",
    "anti_bot_tracking_id": tracking,
})
URL = f"https://shopee.co.id/verify/captcha?{q}"
log(f"url len: {len(URL)}")

HOOK = r"""
(function(){
  if (window.__SD__) return;
  window.__SD__ = [];
  const P = o => { try { window.__SD__.push(o); } catch(e){} };
  const hit = u => u && (u.indexOf('anti_fraud')>=0 || u.indexOf('captcha')>=0);

  const of = window.fetch;
  window.fetch = async function(...a){
    let r=a[0], url=(typeof r==='string'?r:(r&&r.url)||''), body=a[1]&&a[1].body;
    if (hit(url)) P({t:'REQ',w:'fetch',u:url.slice(-100),b:String(body||'').slice(0,9000)});
    const res = await of.apply(this,a);
    if (hit(url)) { try{ const tx=await res.clone().text();
      P({t:'RES',w:'fetch',u:url.slice(-100),s:res.status,b:tx.slice(0,7000)});}catch(e){} }
    return res;
  };

  const oo=XMLHttpRequest.prototype.open, os=XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open=function(m,u){this.__u=u;return oo.apply(this,arguments)};
  XMLHttpRequest.prototype.send=function(b){
    const u=this.__u||'';
    if(hit(u)) P({t:'REQ',w:'xhr',u:u.slice(-100),b:String(b||'').slice(0,9000)});
    this.addEventListener('load',function(){
      if(hit(u)) P({t:'RES',w:'xhr',u:u.slice(-100),s:this.status,b:String(this.responseText||'').slice(0,7000)});
    });
    return os.apply(this,arguments);
  };

  try{
    const oe=CryptoJS.AES.encrypt;
    CryptoJS.AES.encrypt=function(m,k,c){
      P({t:'ENC',m:String(m).slice(0,5000),k:String(k).slice(0,80)});
      return oe.apply(this,arguments);
    };
  }catch(e){}
})();
"""


def grab(pg):
    try:
        return pg.evaluate("()=>window.__SD__||[]")
    except Exception:
        return []


from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,900",
        "--disable-blink-features=AutomationControlled", "--lang=id-ID"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 900},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    ctx.add_cookies(cookies)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};"
        "Object.defineProperty(navigator,'languages',{get:()=>['id-ID','id','en']});")
    ctx.add_init_script(HOOK)
    pg = ctx.new_page()

    log("=== goto captcha url ===")
    try:
        pg.goto(URL, wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        log(f"  err {str(e)[:50]}")
    pg.wait_for_timeout(6000)

    for sel in ('button:has-text("Setuju")', 'text=Bahasa Indonesia'):
        try:
            l = pg.locator(sel)
            if l.count() and l.first.is_visible():
                l.first.click(timeout=2500, force=True)
                log(f"  ✅ {sel[:22]}")
                pg.wait_for_timeout(2500)
        except Exception:
            pass

    dump = []
    for i in range(16):
        if time.time() - T0 > MAXT:
            break
        dump = grab(pg)
        gen = [x for x in dump if x.get("t") == "RES" and "generate" in (x.get("u") or "")]
        canvas = pg.evaluate("()=>document.querySelectorAll('canvas').length")
        log(f"  [{i+1}] dump={len(dump)} gen={len(gen)} canvas={canvas} url={pg.url.split('shopee.co.id')[-1][:40]}")
        if gen:
            break
        try:
            pg.mouse.move(680, 440)
            pg.mouse.move(720, 455)
        except Exception:
            pass
        pg.wait_for_timeout(4000)

    dump = grab(pg)
    log(f"\n=== {len(dump)} event ===")

    # cari security_data & dfp_token di body
    for e in dump:
        b = e.get("b") or ""
        m = e.get("m") or ""
        if "security_data" in b or "dfp_token" in b:
            log(f"  ★ {e['t']} {e.get('u','')[:60]}")
            log(f"     {b[:600]}")
        if e["t"] == "ENC":
            log(f"  ENC key={e.get('k','')[:35]}")
            log(f"     msg={m[:500]}")

    json.dump(dump, open(OUT, "w"), indent=1)
    pg.screenshot(path="/root/shopee-verify/sd2.png", full_page=False)
    log(f"-> {OUT}")
    br.close()

log("\n=== SELESAI ===")
