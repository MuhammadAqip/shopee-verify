"""HOOK_GEN.py — tangkap payload captcha/generate ASLI dari SDK.

Tujuan: lihat APAKAH SDK sendiri kena Block, atau SDK dapat captcha.
Kalau SDK dapat captcha tapi kita tidak -> beda payload.
Kalau SDK juga kena Block -> server-side block, tidak bisa diakali payload.

Hook:
  - fetch + XMLHttpRequest: semua body request/response ke captcha/*
  - CryptoJS.AES.decrypt/encrypt: tangkap plaintext sebelum enkripsi

Jalankan di ck_1659 (ivs_required=False) dengan IP RI.
"""
import json, sys, time, base64

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1659.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283191104601"
BUDGET = int(sys.argv[3]) if len(sys.argv) > 3 else 500

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):3d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/HOOK.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright

HOOK_JS = r"""
(function(){
  window.__cap = [];
  function rec(o){ try{ window.__cap.push(o); if(window.__cap.length>200) window.__cap.shift(); }catch(e){} }

  // ---- fetch ----
  var of = window.fetch;
  window.fetch = function(){
    var args = arguments;
    var url = (typeof args[0]==='string')?args[0]:(args[0]&&args[0].url)||'';
    var opt = args[1]||{};
    var body = opt.body;
    var isCap = url.indexOf('captcha')>=0 || url.indexOf('anti_fraud')>=0;
    if (isCap) rec({k:'req',u:url.slice(-70),m:opt.method||'GET',b:String(body||'').slice(0,3000)});
    return of.apply(this, args).then(function(res){
      if (isCap) {
        var cl = res.clone();
        cl.text().then(function(t){ rec({k:'res',u:url.slice(-70),s:res.status,b:t.slice(0,3000)}); }).catch(function(){});
      }
      return res;
    });
  };

  // ---- XHR ----
  var oo = XMLHttpRequest.prototype.open;
  var os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(m,u){ this.__u=u; this.__m=m; return oo.apply(this,arguments); };
  XMLHttpRequest.prototype.send = function(b){
    var self=this; var isCap=(this.__u||'').indexOf('captcha')>=0;
    if(isCap) rec({k:'xreq',u:(this.__u||'').slice(-70),m:this.__m,b:String(b||'').slice(0,3000)});
    this.addEventListener('load',function(){
      if(isCap) rec({k:'xres',u:(self.__u||'').slice(-70),s:self.status,b:String(self.responseText||'').slice(0,3000)});
    });
    return os.apply(this,arguments);
  };

  // ---- CryptoJS decrypt hook (kalau tersedia) ----
  function hookCJS(){
    if (!window.CryptoJS || !CryptoJS.AES || CryptoJS.AES.__h) return;
    var od = CryptoJS.AES.decrypt;
    CryptoJS.AES.decrypt = function(cipher, key, cfg){
      var r = od.apply(this, arguments);
      try {
        var t = r.toString(CryptoJS.enc.Utf8);
        if (t && t.length>10 && t.indexOf('{')>=0)
          rec({k:'plain',t:'decrypt',v:t.slice(0,3000)});
      } catch(e){}
      return r;
    };
    var oe = CryptoJS.AES.encrypt;
    CryptoJS.AES.encrypt = function(msg, key, cfg){
      try {
        var m = (msg && msg.toString)? msg.toString() : String(msg);
        if (m && m.length>10) rec({k:'plain',t:'encrypt',v:m.slice(0,3000)});
      } catch(e){}
      return oe.apply(this, arguments);
    };
    CryptoJS.AES.__h = true;
  }
  hookCJS();
  setInterval(hookCJS, 800);
  rec({k:'init',ok:true});
})();
"""

net = []


def onresp(r):
    u = r.url
    if "/api/v4/" not in u:
        return
    short = u.split("shopee.co.id")[-1].split("?")[0][:70]
    try:
        b = r.text()
    except Exception:
        b = ""
    net.append({"u": short, "s": r.status, "b": b[:1200]})
    if "captcha" in short or "otp" in short:
        log(f"  NET {r.status} {short} :: {b[:130]}")


def modals(pg):
    for sel in ('button:has-text("Setuju")', 'text=Setuju',
                'text=Bahasa Indonesia'):
        try:
            l = pg.locator(sel)
            if l.count() and l.first.is_visible():
                l.first.click(timeout=2000, force=True)
                pg.wait_for_timeout(1500)
                return True
        except Exception:
            pass
    return False


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
    pg.add_init_script(HOOK_JS)
    pg.on("response", onresp)

    log("=== 1. home (hook aktif) ===")
    for a in range(4):
        try:
            pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=60000)
        except Exception:
            time.sleep(3)
            continue
        pg.wait_for_timeout(9000)
        modals(pg)
        log(f"  [{a+1}] {pg.url.split('shopee.co.id')[-1][:45]}")
        if "/verify/" not in pg.url:
            break

    log("\n=== 2. trigger generate ===")
    # page-context fetch ke cart/mini -> SDK trigger captcha
    for a in range(3):
        try:
            r = pg.evaluate("""async ()=>{
              try{const res=await fetch('/api/v4/cart/mini?need_buyer_dp_info=1',
                {credentials:'include'});const j=await res.json();
                return {s:res.status, err:j.error};}catch(e){return {ex:String(e).slice(0,40)}}
            }""")
            log(f"  cart#{a+1} {r}")
        except Exception:
            pass
        pg.wait_for_timeout(6000)

    # paksa halaman captcha kalau belum
    if "/verify/" not in pg.url:
        try:
            pg.goto("https://shopee.co.id/verify/captcha", wait_until="domcontentloaded",
                    timeout=50000)
        except Exception:
            pass
    pg.wait_for_timeout(12000)
    modals(pg)
    pg.wait_for_timeout(5000)

    log(f"\n=== 3. url: {pg.url[:100]} ===")
    pg.screenshot(path="/root/shopee-verify/HOOK_page.png", full_page=False)

    # === 4. ambil hasil hook ===
    log("\n=== 4. HASIL HOOK ===")
    try:
        cap = pg.evaluate("()=>window.__cap||[]")
    except Exception as e:
        cap = []
        log(f"  eval err {str(e)[:50]}")

    log(f"  total captured: {len(cap)}")
    plains = [c for c in cap if c.get("k") == "plain"]
    reqs = [c for c in cap if c.get("k") in ("req", "xreq")]
    ress = [c for c in cap if c.get("k") in ("res", "xres")]

    log(f"  plain={len(plains)} req={len(reqs)} res={len(ress)}")

    # plaintext = paling berharga
    if plains:
        log("\n--- PLAINTEXT (encrypt/decrypt) ---")
        for p in plains[:12]:
            log(f"  [{p.get('t')}] {p.get('v', '')[:600]}")
    else:
        log("  ⚠ tidak ada plaintext tertangkap (CryptoJS hook tidak kena)")

    if reqs:
        log("\n--- REQUEST captcha ---")
        for q in reqs[:6]:
            log(f"  {q.get('m')} {q.get('u')}")
            log(f"     {q.get('b', '')[:400]}")

    if ress:
        log("\n--- RESPONSE captcha ---")
        for q in ress[:8]:
            log(f"  {q.get('s')} {q.get('u')}")
            log(f"     {q.get('b', '')[:350]}")

    # === 5. cek canvas / UI captcha ===
    log("\n=== 5. canvas state ===")
    st = pg.evaluate("""()=>{
      const cs=[...document.querySelectorAll('canvas')].map(c=>{
        const r=c.getBoundingClientRect(); return {w:c.width,h:c.height,x:r.x,y:r.y};
      });
      return {n:cs.length, cs:cs.slice(0,6),
              txt:(document.body.innerText||'').slice(0,200)};
    }""")
    log(f"  canvas={st.get('n')} {st.get('cs')}")
    log(f"  txt: {st.get('txt', '')[:160].replace(chr(10), ' | ')}")

    # simpan
    json.dump({"cap": cap[-160:], "net": net[-60:], "url": pg.url},
              open("/root/shopee-verify/HOOK.json", "w"), indent=1)
    cks = ctx.cookies()
    open("/root/shopee-verify/ck_hook.txt", "w").write(
        "; ".join(f"{c['name']}={c['value']}" for c in cks))
    br.close()

log("\n=== SELESAI ===")
