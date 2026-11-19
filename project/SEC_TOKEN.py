"""SEC_TOKEN.py — ambil encrypted_security_data + dfp_token dari SDK Shopee.

Module 16223 exports:
  getLongToken()              -> 17460B (encrypted_security_data)
  getWebDeviceFingerprint()   -> dfp_token
  initSecuritySdk(...)        -> wajib dipanggil dulu

Alur:
  1. buka shopee.co.id, tunggu SDK load
  2. initSecuritySdk()
  3. getLongToken() -> SEC
  4. getWebDeviceFingerprint() -> DFP
  5. dump ke SEC_TOKENS.json
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
    open("/root/shopee-verify/SEC.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright

EXTRACT = r"""
(async () => {
  const out = {steps:[], sec:null, dfp:null, err:null};
  try {
    const wc = window.webpackChunkshopee_pc;
    if (!wc) { out.err='no_chunk'; return out; }
    let req=null;
    wc.push([[('sec'+Date.now())],{},function(r){req=r;}]);
    if (!req) { out.err='no_req'; return out; }

    const m = req(16223);
    if (!m) { out.err='no_module'; return out; }
    out.exports = Object.keys(m);

    // 1. initSecuritySdk (opsional, coba tanpa argumen dulu)
    for (const args of [[], [{}], [undefined, true]]) {
      try {
        const r = await Promise.race([Promise.resolve(m.initSecuritySdk(...args)),
          new Promise((_,rj)=>setTimeout(()=>rj(new Error('to')),4000))]);
        out.steps.push({step:'init',args:args.length,ok:true,
                        ret:(typeof r==='string')?r.slice(0,120):JSON.stringify(r).slice(0,120)});
        break;
      } catch(e) {
        out.steps.push({step:'init',args:args.length,ok:false,
                        err:String(e).slice(0,80)});
      }
    }

    await new Promise(r=>setTimeout(r,2000));

    // 2. getLongToken -> encrypted_security_data
    try {
      const v = await Promise.race([m.getLongToken(),
        new Promise((_,rj)=>setTimeout(()=>rj(new Error('to')),8000))]);
      if (typeof v === 'string' && v.length > 100) {
        out.sec = v;
        out.steps.push({step:'getLongToken', ok:true, len:v.length});
      } else {
        out.steps.push({step:'getLongToken', ok:false, val:String(v).slice(0,100)});
      }
    } catch(e) {
      out.steps.push({step:'getLongToken', err:String(e).slice(0,80)});
    }

    // 3. getWebDeviceFingerprint -> dfp_token
    try {
      const v = await Promise.race([m.getWebDeviceFingerprint(),
        new Promise((_,rj)=>setTimeout(()=>rj(new Error('to')),8000))]);
      const s = (typeof v === 'string') ? v : JSON.stringify(v);
      if (s && s.length > 4) {
        out.dfp = s;
        out.steps.push({step:'getWebDeviceFingerprint', ok:true, len:s.length,
                        val:s.slice(0,200)});
      } else {
        out.steps.push({step:'getWebDeviceFingerprint', ok:false, val:s});
      }
    } catch(e) {
      out.steps.push({step:'getWebDeviceFingerprint', err:String(e).slice(0,80)});
    }

    // 4. getLongToken dengan argumen (kalau tanpa arg gagal)
    if (!out.sec) {
      for (const args of [['TSS.PC'], [{appKey:'TSS.PC'}], ['FlashSale.PC']]) {
        try {
          const v = await Promise.race([m.getLongToken(...args),
            new Promise((_,rj)=>setTimeout(()=>rj(new Error('to')),8000))]);
          if (typeof v === 'string' && v.length > 100) {
            out.sec = v;
            out.steps.push({step:'getLongToken_args', args:JSON.stringify(args),
                            ok:true, len:v.length});
            break;
          }
        } catch(e) {}
      }
    }

    return out;
  } catch(e) {
    out.err = String(e).slice(0, 200);
    return out;
  }
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

    log("=== buka shopee.co.id ===")
    try:
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    pg.wait_for_timeout(15000)
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
    pg.wait_for_timeout(13000)

    log("\n=== extract tokens ===")
    res = pg.evaluate(EXTRACT)
    log(f"  err={res.get('err')}")
    for s in (res.get("steps") or []):
        log(f"  {s}")

    sec = res.get("sec") or ""
    dfp = res.get("dfp") or ""

    log(f"\n  encrypted_security_data: {len(sec)}B")
    if sec:
        log(f"    head: {sec[:100]}")
    log(f"  dfp_token: {len(dfp)}B")
    if dfp:
        log(f"    val: {dfp[:200]}")

    json.dump({"sec": sec, "dfp": dfp, "steps": res.get("steps")},
              open("/root/shopee-verify/SEC_TOKENS.json", "w"), indent=1)

    if sec:
        open("/root/shopee-verify/SEC.txt", "w").write(sec)
        log("  → SEC.txt")
    if dfp:
        open("/root/shopee-verify/DFP_TOKEN.txt", "w").write(dfp)
        log("  → DFP_TOKEN.txt")

    br.close()

log("\n=== SELESAI ===")
