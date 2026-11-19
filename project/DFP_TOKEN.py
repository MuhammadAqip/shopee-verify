"""DFP_TOKEN.py — ambil dfp_token + encrypted_security_data dari SDK browser.

Ditemukan di cap5001_bundle_js.js:
  DfpWeb / DfpNative / getWebToken / getNativeToken / getNativeDfpToken
  captcha_signature / CAPTCHA_SIGNATURE
  /api/v4/anti_fraud/captcha/verify_v2

Alur:
  1. buka shopee.co.id (SDK captcha load)
  2. cari objek DFP di window / webpack
  3. panggil getWebToken() -> dfp_token
  4. cari encrypted_security_data (dari get_config atau SDK state)
  5. tulis ke DFP.json
"""
import json, sys, time

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_new234.txt"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):3d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/DFP.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright

found = {}


def onresp(r):
    u = r.url
    if "get_config" in u:
        try:
            j = r.json()
            found["get_config"] = j
            log(f"  get_config keys={list(j.keys())}")
            for k in ("encrypted_security_data", "security_data", "dfp_token"):
                if j.get(k):
                    found[k] = j[k]
                    log(f"  ★ {k} = {str(j[k])[:60]} len={len(str(j[k]))}")
        except Exception:
            pass
    if "traffic" in u and "/api/v4/" in u:
        try:
            j = r.json()
            log(f"  traffic keys={list(j.keys())}")
            for k in ("encrypted_security_data", "security_data", "token"):
                if j.get(k):
                    found[k] = j[k]
                    log(f"  ★ traffic.{k} len={len(str(j[k]))}")
        except Exception:
            pass


DUMP_JS = r"""
(()=>{
  const out = {globals:{}, dfp:null, tokens:{}};
  // scan window untuk objek DFP / DfpWeb / security
  for (const k in window){
    try{
      const v = window[k];
      if (!v) continue;
      const nm = k.toLowerCase();
      if (nm.includes('dfp') || nm.includes('security') ||
          nm.includes('antifraud') || nm.includes('captcha')){
        if (typeof v === 'function'){
          out.globals[k] = 'fn:' + String(v).slice(0,80);
        } else if (typeof v === 'object'){
          out.globals[k] = 'obj:' + Object.keys(v).slice(0,15).join(',');
        }
      }
    }catch(e){}
  }
  // cari DfpWeb
  try{
    if (window.DfpWeb){
      out.dfp = {type: typeof window.DfpWeb,
                 keys: Object.keys(window.DfpWeb).slice(0,20)};
    }
  }catch(e){}
  // cari di webpack chunk
  try{
    const wc = window.webpackChunk_shopee_antifraud_captcha_pc;
    out.webpack = wc ? ('len='+wc.length) : 'none';
  }catch(e){ out.webpack = 'err'; }
  return out;
})()
"""


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
    pg.on("response", onresp)

    log("=== 1. buka shopee.co.id ===")
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

    # trigger cart/mini -> SDK init
    try:
        pg.evaluate("""async ()=>{
          try{await fetch('/api/v4/cart/mini?need_buyer_dp_info=1',{credentials:'include'});}
          catch(e){}
        }""")
    except Exception:
        pass
    pg.wait_for_timeout(8000)

    log("\n=== 2. dump global DFP / captcha ===")
    d = pg.evaluate(DUMP_JS)
    for k, v in (d.get("globals") or {}).items():
        log(f"  {k} = {v[:110]}")
    log(f"  dfp: {d.get('dfp')}")
    log(f"  webpack: {d.get('webpack')}")

    # === 3. panggil getWebToken ===
    log("\n=== 3. coba getWebToken ===")
    r = pg.evaluate(r"""
    (async ()=>{
      const out = {tried:[]};
      // berbagai lokasi DFP
      const cands = [];
      try{ if(window.DfpWeb) cands.push(['DfpWeb', window.DfpWeb]); }catch(e){}
      try{ if(window.DfpNative) cands.push(['DfpNative', window.DfpNative]); }catch(e){}
      try{ if(window.__dfp) cands.push(['__dfp', window.__dfp]); }catch(e){}

      for (const [nm, obj] of cands){
        for (const fn of ['getWebToken','getToken','getNativeToken','getNativeDfpToken']){
          try{
            if (typeof obj[fn] === 'function'){
              out.tried.push(nm+'.'+fn);
              const v = await obj[fn]();
              out[fn] = (typeof v === 'string') ? v.slice(0,600) : JSON.stringify(v).slice(0,600);
            }
          }catch(e){ out[fn+'_err'] = String(e).slice(0,80); }
        }
      }
      // cari di window fungsi global
      for (const fn of ['getWebToken','getDfpToken','getSecurityData']){
        try{
          if (typeof window[fn] === 'function'){
            out.tried.push('window.'+fn);
            const v = await window[fn]();
            out[fn] = (typeof v === 'string') ? v.slice(0,600) : JSON.stringify(v).slice(0,600);
          }
        }catch(e){ out[fn+'_err'] = String(e).slice(0,80); }
      }
      return out;
    })()
    """)
    for k, v in r.items():
        log(f"  {k}: {str(v)[:300]}")

    # === 4. cari di localStorage / sessionStorage ===
    log("\n=== 4. storage ===")
    st = pg.evaluate("""()=>{
      const out={};
      try{
        for (let i=0;i<localStorage.length;i++){
          const k=localStorage.key(i);
          if(/dfp|sec|token|captcha|sap/i.test(k)){
            out['LS:'+k]=String(localStorage.getItem(k)).slice(0,250);
          }
        }
      }catch(e){}
      try{
        for (let i=0;i<sessionStorage.length;i++){
          const k=sessionStorage.key(i);
          if(/dfp|sec|token|captcha|sap/i.test(k)){
            out['SS:'+k]=String(sessionStorage.getItem(k)).slice(0,250);
          }
        }
      }catch(e){}
      return out;
    }""")
    for k, v in st.items():
        log(f"  {k} = {str(v)[:200]}")

    json.dump({"dump": d, "tokens": r, "storage": st, "found": {k: str(v)[:200] for k, v in found.items()}},
              open("/root/shopee-verify/DFP.json", "w"), indent=1)

    pg.screenshot(path="/root/shopee-verify/DFP.png", full_page=False)
    br.close()

log("\n=== SELESAI ===")
