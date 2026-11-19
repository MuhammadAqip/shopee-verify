"""sec_dump.py — tangkap encrypted_security_data + dfp_token + plaintext captcha dari browser.

Hook fetch/XHR/CryptoJS di halaman /verify/captcha.
Tujuan: dapat nilai asli encrypted_security_data + dfp_token + plaintext payload.
"""
import json, sys, time

sys.path.insert(0, "/root/shopee-farm")

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1553.txt"
MAXT = int(sys.argv[2]) if len(sys.argv) > 2 else 200

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
OUT = "/root/shopee-verify/sec_dump.json"
T0 = time.time()


def log(*a):
    print(f"[{int(time.time()-T0):3d}s]", *a, flush=True)


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

HOOK = r"""
(function(){
  if (window.__SECDUMP__) return;
  window.__SECDUMP__ = [];
  const push = (o) => { try { window.__SECDUMP__.push(o); } catch(e){} };

  const of = window.fetch;
  window.fetch = async function(...args){
    let req = args[0];
    let url = typeof req === 'string' ? req : (req && req.url) || '';
    let body = args[1] && args[1].body;
    if (url && url.indexOf('anti_fraud') >= 0)
      push({t:'REQ', api:'fetch', url:url.slice(-95), body:String(body||'').slice(0,9000)});
    const resp = await of.apply(this, args);
    if (url && url.indexOf('anti_fraud') >= 0) {
      try { const txt = await resp.clone().text();
        push({t:'RES', api:'fetch', url:url.slice(-95), status:resp.status, body:txt.slice(0,7000)});
      } catch(e){}
    }
    return resp;
  };

  const oo = XMLHttpRequest.prototype.open;
  const os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(m,u){ this.__u=u; return oo.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function(b){
    const u = this.__u || '';
    if (u.indexOf('anti_fraud') >= 0)
      push({t:'REQ', api:'xhr', url:u.slice(-95), body:String(b||'').slice(0,9000)});
    this.addEventListener('load', function(){
      if (u.indexOf('anti_fraud') >= 0)
        push({t:'RES', api:'xhr', url:u.slice(-95), status:this.status, body:String(this.responseText||'').slice(0,7000)});
    });
    return os.apply(this, arguments);
  };

  try {
    const origEnc = CryptoJS.AES.encrypt;
    CryptoJS.AES.encrypt = function(msg, key, cfg){
      push({t:'ENC', msg:String(msg).slice(0,5000), key:String(key).slice(0,80)});
      return origEnc.apply(this, arguments);
    };
  } catch(e){}
})();
"""


def grab(pg):
    try:
        return pg.evaluate("()=>window.__SECDUMP__||[]")
    except Exception:
        return []


from playwright.sync_api import sync_playwright

dump = []

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

    def modal():
        for sel in ('button:has-text("Setuju")', 'text=Setuju',
                    'text=Bahasa Indonesia'):
            try:
                l = pg.locator(sel)
                if l.count() and l.first.is_visible():
                    l.first.click(timeout=2500, force=True)
                    log(f"  ✅ {sel[:24]}")
                    pg.wait_for_timeout(2000)
                    return
            except Exception:
                pass

    log("=== buka /verify/captcha ===")
    try:
        pg.goto("https://shopee.co.id/verify/captcha",
                wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        log(f"  err {str(e)[:50]}")
    pg.wait_for_timeout(7000)
    modal()

    # tunggu SDK generate captcha
    for i in range(14):
        if time.time() - T0 > MAXT:
            break
        d = grab(pg)
        gen = [x for x in d if 'generate' in (x.get('url') or '') and x['t'] == 'RES']
        log(f"  [{i+1}] dump={len(d)} gen_res={len(gen)} url={pg.url.split('shopee.co.id')[-1][:45]}")
        if gen:
            log("  ✅ generate response tertangkap")
            break
        modal()
        pg.wait_for_timeout(4000)

    # scroll/klik canvas untuk memicu interaksi SDK
    try:
        pg.mouse.move(700, 450)
        pg.wait_for_timeout(500)
        pg.mouse.move(750, 470)
    except Exception:
        pass
    pg.wait_for_timeout(6000)

    dump = grab(pg)
    log(f"\n=== total {len(dump)} event ===")

    # ringkas
    for e in dump:
        t = e.get("t")
        u = e.get("url") or ""
        if t == "ENC":
            log(f"  ENC key={e.get('key')[:40]}")
            log(f"      msg={e.get('msg')[:400]}")
        elif t == "REQ":
            log(f"  REQ {u}")
            log(f"      body={e.get('body')[:400]}")
        elif t == "RES":
            log(f"  RES {e.get('status')} {u}")
            log(f"      {e.get('body')[:250]}")

    json.dump(dump, open(OUT, "w"), indent=1)
    log(f"-> {OUT}")
    pg.screenshot(path="/root/shopee-verify/sec_dump.png", full_page=False)
    br.close()

log("\n=== SELESAI ===")
