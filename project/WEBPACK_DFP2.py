"""WEBPACK_DFP2.py — brute-call SEMUA fungsi yang export, cari token.

Module cuma 4, jadi bisa brute: panggil setiap function export,
kalau return string panjang (>=32 char) atau object berisi string,
itu kemungkinan token.
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
    open("/root/shopee-verify/WD2.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright

BRUTE = r"""
(async () => {
  const out = {modsDetail:[], hits:[], err:null};
  try {
    const wc = window.webpackChunk_shopee_antifraud_captcha_pc;
    if (!wc) { out.err='no_chunk'; return out; }
    let req = null;
    wc.push([[('b'+Date.now())], {}, function(r){ req=r; }]);
    if (!req) { out.err='no_req'; return out; }

    const ids = Object.keys(req.m || {});
    out.modCount = ids.length;

    // rekam struktur tiap module
    const fnTargets = [];
    const objTargets = [];

    for (const id of ids){
      let mod;
      try{ mod = req(id); }catch(e){ continue; }
      if (!mod || typeof mod !== 'object') continue;
      const keys = Object.keys(mod);
      out.modsDetail.push({id, keys: keys.slice(0,20)});

      for (const k of keys){
        const v = mod[k];
        if (typeof v === 'function'){
          const src = String(v);
          if (src.length > 60) fnTargets.push({id, k, src: src.slice(0,90)});
        } else if (v && typeof v === 'object'){
          const mk = Object.keys(v);
          objTargets.push({id, k, keys: mk.slice(0,20)});
        }
      }
    }

    out.fnCount = fnTargets.length;
    out.objCount = objTargets.length;
    out.fnSample = fnTargets.slice(0,40);

    // panggil semua fn export (max 60) dengan timeout pendek
    for (const t of fnTargets.slice(0, 60)){
      let mod;
      try{ mod = req(t.id); }catch(e){ continue; }
      const f = mod[t.k];
      if (typeof f !== 'function') continue;
      try{
        const r = await Promise.race([
          Promise.resolve(f()),
          new Promise((_,rj)=>setTimeout(()=>rj(new Error('to')), 2500))
        ]);
        const s = (typeof r === 'string') ? r : JSON.stringify(r);
        if (s && s.length > 24 && s !== 'undefined' && s !== '{}'){
          out.hits.push({id: t.id, k: t.k, len: s.length, val: s.slice(0, 700)});
        }
      }catch(e){}
    }

    // panggil method di obj export
    for (const t of objTargets.slice(0, 40)){
      let mod;
      try{ mod = req(t.id); }catch(e){ continue; }
      const o = mod[t.k];
      if (!o || typeof o !== 'object') continue;
      for (const mk of Object.keys(o)){
        const f = o[mk];
        if (typeof f !== 'function') continue;
        try{
          const r = await Promise.race([
            Promise.resolve(f()),
            new Promise((_,rj)=>setTimeout(()=>rj(new Error('to')), 2000))
          ]);
          const s = (typeof r === 'string') ? r : JSON.stringify(r);
          if (s && s.length > 24 && s !== 'undefined' && s !== '{}'){
            out.hits.push({id: t.id, k: t.k+'.'+mk, len: s.length, val: s.slice(0, 700)});
          }
        }catch(e){}
      }
    }

    // objek yang punya prototype method
    for (const t of objTargets.slice(0, 40)){
      let mod;
      try{ mod = req(t.id); }catch(e){ continue; }
      const o = mod[t.k];
      if (!o || typeof o !== 'object' || !o.constructor) continue;
      try{
        const proto = Object.getPrototypeOf(o);
        if (!proto) continue;
        for (const mk of Object.getOwnPropertyNames(proto)){
          if (mk === 'constructor') continue;
          const f = o[mk];
          if (typeof f !== 'function') continue;
          try{
            const r = await Promise.race([
              Promise.resolve(f.call(o)),
              new Promise((_,rj)=>setTimeout(()=>rj(new Error('to')), 2000))
            ]);
            const s = (typeof r === 'string') ? r : JSON.stringify(r);
            if (s && s.length > 24 && s !== 'undefined' && s !== '{}'){
              out.hits.push({id: t.id, k: t.k+'#'+mk, len: s.length, val: s.slice(0,700)});
            }
          }catch(e){}
        }
      }catch(e){}
    }

    return out;
  } catch(e){ out.err = String(e).slice(0,200); return out; }
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
        "window.chrome={runtime:{}};")
    pg = ctx.new_page()

    log("=== buka /verify/captcha ===")
    try:
        pg.goto("https://shopee.co.id/verify/captcha", wait_until="domcontentloaded",
                timeout=55000)
    except Exception:
        pass
    pg.wait_for_timeout(16000)

    log("\n=== brute modules ===")
    res = pg.evaluate(BRUTE)
    log(f"  modCount={res.get('modCount')} fn={res.get('fnCount')} obj={res.get('objCount')} err={res.get('err')}")

    log("\n--- module structure ---")
    for m in (res.get("modsDetail") or [])[:10]:
        log(f"  id={m['id']} keys={m['keys']}")

    log("\n--- fn sample ---")
    for f in (res.get("fnSample") or [])[:25]:
        log(f"  {f['id']}.{f['k']}  {f['src'][:80]}")

    hits = res.get("hits") or []
    log(f"\n--- HITS ({len(hits)}) ---")
    hits.sort(key=lambda x: -x["len"])
    for h in hits[:20]:
        log(f"  {h['id']}.{h['k']} len={h['len']}")
        log(f"     {h['val'][:300]}")

    json.dump(res, open("/root/shopee-verify/WD2.json", "w"), indent=1)

    if hits:
        open("/root/shopee-verify/DFP_TOKEN.txt", "w").write(hits[0]["val"])
        log(f"\n  → DFP_TOKEN.txt ({hits[0]['len']}B) dari {hits[0]['id']}.{hits[0]['k']}")

    br.close()

log("\n=== SELESAI ===")
