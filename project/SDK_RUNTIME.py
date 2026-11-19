"""SDK_RUNTIME.py — jalankan SDK captcha 50017751 DI DALAM browser.

Karena string ter-obfuscate dan endpoint = verify_v2, cara paling cepat:
  1. buka /verify/captcha
  2. tunggu SDK inisialisasi (window global)
  3. panggil SDK lewat API-nya sendiri (renderCaptcha / initCaptcha / dst)
  4. tangkap captcha yang muncul -> solve via SadCaptcha -> SDK submit sendiri

Hook: intercept fetch/XHR supaya payload verify_v2 ketangkap plaintext.
"""
import json, sys, time, re

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_fresh_1659.txt"
BUDGET = int(sys.argv[2]) if len(sys.argv) > 2 else 400

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):3d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/SR.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright

HOOK = r"""
(function(){
  window.__cap = [];
  function rec(o){ try{window.__cap.push(o);if(window.__cap.length>300)window.__cap.shift();}catch(e){} }

  // tangkap semua fetch ke anti_fraud
  var of=window.fetch;
  window.fetch=function(){
    var a=arguments,url=(typeof a[0]==='string')?a[0]:(a[0]&&a[0].url)||'',opt=a[1]||{};
    var isCap=url.indexOf('anti_fraud')>=0||url.indexOf('captcha')>=0;
    if(isCap) rec({k:'req',u:url.slice(-60),m:opt.method||'GET',b:String(opt.body||'').slice(0,4000)});
    return of.apply(this,a).then(function(res){
      if(isCap){var c=res.clone();c.text().then(function(t){
        rec({k:'res',u:url.slice(-60),s:res.status,b:t.slice(0,4000)});}).catch(function(){});}
      return res;});
  };

  // tangkap CryptoJS encrypt/decrypt
  function hookCJS(){
    if(!window.CryptoJS||!CryptoJS.AES||CryptoJS.AES.__h2) return;
    var od=CryptoJS.AES.decrypt;
    CryptoJS.AES.decrypt=function(c,k,c2){
      var r=od.apply(this,arguments);
      try{var t=r.toString(CryptoJS.enc.Utf8);
        if(t&&t.length>8&&t.indexOf('{')>=0) rec({k:'plain',t:'DEC',v:t.slice(0,4000)});
      }catch(e){}
      return r;};
    var oe=CryptoJS.AES.encrypt;
    CryptoJS.AES.encrypt=function(m,k,c2){
      try{var s=(m&&m.toString)?m.toString():String(m);
        if(s&&s.length>8) rec({k:'plain',t:'ENC',v:s.slice(0,4000)});
      }catch(e){}
      return oe.apply(this,arguments);};
    CryptoJS.AES.__h2=true;
  }
  hookCJS(); setInterval(hookCJS,600);

  // dump global SDK candidates
  window.__sdk = function(){
    var out={};
    for (var k in window){
      try{
        var v=window[k];
        if(!v) continue;
        if(typeof v==='object' || typeof v==='function'){
          var nm=k.toLowerCase();
          if(nm.indexOf('captcha')>=0||nm.indexOf('sap')>=0||nm.indexOf('sec')>=0
             ||nm.indexOf('verify')>=0||nm.indexOf('sfu')>=0||nm.indexOf('antibot')>=0){
            out[k]=typeof v==='function'
              ? 'fn:'+String(v).slice(0,90)
              : 'obj:'+Object.keys(v).slice(0,12).join(',');
          }
        }
      }catch(e){}
    }
    return out;
  };
})();
"""

net = []


def onresp(r):
    u = r.url
    if "/api/v4/" not in u:
        return
    short = u.split("shopee.co.id")[-1].split("?")[0][:70]
    if "captcha" in short or "otp" in short:
        try:
            b = r.text()
        except Exception:
            b = ""
        net.append({"u": short, "s": r.status, "b": b[:1500]})
        log(f"  NET {r.status} {short[:50]} :: {b[:110]}")


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
    pg = ctx.new_page()
    pg.add_init_script(HOOK)
    pg.on("response", onresp)

    log("=== 1. /verify/captcha ===")
    try:
        pg.goto("https://shopee.co.id/verify/captcha", wait_until="domcontentloaded",
                timeout=55000)
    except Exception as e:
        log(f"  err {str(e)[:50]}")
    pg.wait_for_timeout(15000)

    for sel in ('button:has-text("Setuju")', 'text=Bahasa Indonesia'):
        try:
            l = pg.locator(sel)
            if l.count() and l.first.is_visible():
                l.first.click(timeout=2000, force=True)
                pg.wait_for_timeout(1200)
        except Exception:
            pass

    # === 2. dump global SDK ===
    log("\n=== 2. global SDK ===")
    try:
        g = pg.evaluate("()=>window.__sdk?window.__sdk():{}")
        for k, v in list(g.items())[:25]:
            log(f"  {k} = {v[:110]}")
    except Exception as e:
        log(f"  err {str(e)[:50]}")

    # === 3. tunggu canvas ===
    log("\n=== 3. tunggu canvas ===")
    for i in range(14):
        pg.wait_for_timeout(4000)
        st = pg.evaluate("""()=>{
          const cs=[...document.querySelectorAll('canvas')].map(c=>{
            const r=c.getBoundingClientRect();return {w:Math.round(r.width),h:Math.round(r.height)};
          }).filter(o=>o.w>20&&o.h>10);
          const ifr=[...document.querySelectorAll('iframe')].map(f=>f.src.slice(0,60));
          return {n:cs.length, cs, ifr,
                  txt:(document.body.innerText||'').slice(0,150)};
        }""")
        log(f"  [{i*4+4:2d}s] canvas={st['n']} iframe={len(st.get('ifr', []))} {st.get('txt', '')[:70]}")
        if st["n"] or st.get("ifr"):
            log(f"  cs={st['cs']} ifr={st.get('ifr')}")
            break

    # === 4. dump hook ===
    log("\n=== 4. HOOK RESULT ===")
    try:
        cap = pg.evaluate("()=>window.__cap||[]")
    except Exception:
        cap = []
    log(f"  total {len(cap)}")
    for c in cap[-25:]:
        k = c.get("k")
        if k == "plain":
            log(f"  [{c.get('t')}] {c.get('v', '')[:500]}")
        elif k == "req":
            log(f"  REQ {c.get('m')} {c.get('u')} :: {c.get('b', '')[:300]}")
        elif k == "res":
            log(f"  RES {c.get('s')} {c.get('u')} :: {c.get('b', '')[:250]}")

    pg.screenshot(path="/root/shopee-verify/SR.png", full_page=False)
    json.dump({"cap": cap[-60:], "net": net[-40:], "g": g},
              open("/root/shopee-verify/SR.json", "w"), indent=1)
    br.close()

log("\n=== SELESAI ===")
