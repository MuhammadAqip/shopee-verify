"""WEBPACK_DFP.py — akses module webpack, panggil DfpWeb/getWebToken.

Ditemukan di bundle:
  DfpWeb / DfpNative / getWebToken / getNativeToken / getNativeDfpToken
  security_data / captcha_signature

SDK tersedia via: window.webpackChunk_shopee_antifraud_captcha_pc
Butuh: inject chunk untuk dapat `__webpack_require__`, lalu iterate module,
cari yang punya getWebToken / DfpWeb, panggil.

Output: dfp_token + security_data -> DFP_TOKENS.json
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
    open("/root/shopee-verify/WDFP.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright

EXTRACT = r"""
(async () => {
  const out = {ok:false, modules:[], tokens:{}, err:null};
  try {
    const wc = window.webpackChunk_shopee_antifraud_captcha_pc;
    if (!wc) { out.err = 'no_webpack_chunk'; return out; }

    // inject untuk dapat require
    let req = null;
    const chunkId = 'extract_' + Date.now();
    wc.push([[chunkId], {}, function (r) { req = r; }]);
    if (!req) { out.err = 'no_require'; return out; }
    out.ok = true;

    // iterate semua module id
    const ids = Object.keys(req.m || {});
    out.moduleCount = ids.length;

    const wanted = ['getWebToken','getNativeToken','getNativeDfpToken',
                    'DfpWeb','DfpNative','getDfpToken','securityData',
                    'getSecurityData','captcha_signature'];

    for (const id of ids) {
      let mod;
      try { mod = req(id); } catch(e) { continue; }
      if (!mod || typeof mod !== 'object') continue;

      for (const key of Object.keys(mod)) {
        let v = mod[key];
        if (v && typeof v === 'object') {
          // nested
          for (const k2 of Object.keys(v)) {
            if (wanted.includes(k2) && typeof v[k2] === 'function') {
              out.modules.push({id, path: key+'.'+k2, kind: 'fn'});
            }
          }
          // cek nama constructor
          try {
            const cn = v.constructor && v.constructor.name;
            if (cn && wanted.some(w => cn.includes(w))) {
              out.modules.push({id, path: key, kind: 'cls:'+cn,
                                methods: Object.getOwnPropertyNames(Object.getPrototypeOf(v)).slice(0,15)});
            }
          } catch(e){}
        }
        if (wanted.includes(key) && typeof v === 'function') {
          out.modules.push({id, path: key, kind: 'fn'});
          // langsung coba panggil kalau tanpa argumen
          try {
            const r = await Promise.race([
              Promise.resolve(v()),
              new Promise((_,rj)=>setTimeout(()=>rj(new Error('timeout')),3000))
            ]);
            if (typeof r === 'string' && r.length > 8) {
              out.tokens[key] = r.slice(0, 800);
            }
          } catch(e) { /* butuh argumen */ }
        }
      }
    }

    // panggil method dari objek yang punya getWebToken
    for (const id of ids) {
      let mod;
      try { mod = req(id); } catch(e) { continue; }
      if (!mod || typeof mod !== 'object') continue;
      for (const key of Object.keys(mod)) {
        const v = mod[key];
        if (!v || typeof v !== 'object') continue;
        for (const fnName of ['getWebToken','getNativeToken','getNativeDfpToken']) {
          if (typeof v[fnName] === 'function') {
            try {
              const r = await Promise.race([
                Promise.resolve(v[fnName]()),
                new Promise((_,rj)=>setTimeout(()=>rj(new Error('timeout')),4000))
              ]);
              const s = (typeof r === 'string') ? r : JSON.stringify(r);
              if (s && s.length > 8) out.tokens[key+'.'+fnName] = s.slice(0, 800);
            } catch(e) { out.tokens[key+'.'+fnName+'_err'] = String(e).slice(0,60); }
          }
        }
      }
    }

    return out;
  } catch (e) {
    out.err = String(e).slice(0, 200);
    return out;
  }
})()
"""


def onresp(r):
    u = r.url
    if "get_config" in u:
        try:
            j = r.json()
            for k in ("encrypted_security_data", "security_data", "dfp_token"):
                if j.get(k):
                    log(f"  ★ get_config.{k} len={len(str(j[k]))}")
        except Exception:
            pass


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

    log("=== 1. shopee.co.id ===")
    try:
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    pg.wait_for_timeout(11000)
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
    pg.wait_for_timeout(10000)

    log("\n=== 2. buka /verify/captcha (SDK baru load) ===")
    try:
        pg.goto("https://shopee.co.id/verify/captcha", wait_until="domcontentloaded",
                timeout=50000)
    except Exception:
        pass
    pg.wait_for_timeout(14000)

    log("\n=== 3. extract webpack modules ===")
    res = pg.evaluate(EXTRACT)
    log(f"  ok={res.get('ok')} mods={res.get('moduleCount')} err={res.get('err')}")
    mods = res.get("modules") or []
    log(f"  kandidat module: {len(mods)}")
    for m in mods[:25]:
        log(f"    {m}")

    log("\n=== 4. TOKENS ===")
    toks = res.get("tokens") or {}
    if not toks:
        log("  (kosong)")
    for k, v in toks.items():
        log(f"  {k} = {str(v)[:250]}")
        log(f"      len={len(str(v))}")

    json.dump(res, open("/root/shopee-verify/DFP_TOKENS.json", "w"), indent=1)

    # simpan token yang panjang (kemungkinan dfp_token)
    best = max(toks.items(), key=lambda kv: len(str(kv[1])) if not kv[0].endswith("_err") else 0,
               default=(None, ""))
    if best[0] and not best[0].endswith("_err"):
        open("/root/shopee-verify/DFP_TOKEN.txt", "w").write(str(best[1]))
        log(f"\n  → DFP_TOKEN.txt dari {best[0]} ({len(str(best[1]))}B)")

    pg.screenshot(path="/root/shopee-verify/WDFP.png", full_page=False)
    br.close()

log("\n=== SELESAI ===")
