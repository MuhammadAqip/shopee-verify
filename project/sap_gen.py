# -*- coding: utf-8 -*-
"""sap_gen.py — GENERATE x-sap-sec & x-sap-ri langsung dari SDK Shopee.

Pendekatan: buka Shopee di browser, panggil `window.trackingSDK` dan
interceptor yang sudah terpasang untuk membuat header kita sendiri
untuk request API apa pun (termasuk change_phone_precheck_v2).

Tidak perlu reverse algoritma — SDK menghasilkan header otomatis.
"""
import json, time, sys

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,900"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 900},
                         proxy={"server": PROXY})

    # inject cookie akun
    CK = open("/root/shopee-verify/ck_1659.txt").read().strip()
    pairs = [(p.split("=", 1)[0].strip(), p.split("=", 1)[1].strip())
             for p in CK.split(";") if "=" in p]
    ctx.add_cookies([{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
                     for k, v in pairs])

    pg = ctx.new_page()
    print("=== buka homepage untuk init SDK ===", flush=True)
    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(9000)

    # === 1. dump struktur trackingSDK ===
    print("\n=== STRUKTUR trackingSDK ===", flush=True)
    sdk = pg.evaluate("""()=>{
      const t = window.trackingSDK;
      if (!t) return {err:'no trackingSDK'};
      const props = Object.getOwnPropertyNames(t).map(k=>{
        let tp = typeof t[k];
        let sample = null;
        try{ if(tp==='string') sample = t[k].slice(0,60); }catch(e){}
        return {k, tp, sample};
      });
      const proto = Object.getOwnPropertyNames(Object.getPrototypeOf(t)||{})
        .filter(k=>typeof t[k]==='function');
      return {props, methods:proto, ver:window.__SAP_VERSION__};
    }""")
    print(json.dumps(sdk, indent=1)[:2500], flush=True)

    # === 2. cari fungsi yang bisa generate header ===
    print("\n=== CARI FUNGSI GENERATE HEADER ===", flush=True)
    gen = pg.evaluate("""()=>{
      const out = {};
      const t = window.trackingSDK;
      const checks = ['getSignature','sign','generateHeaders','getHeaders',
                      'buildHeaders','createSign','getSec','getRi',
                      'getSecureHeaders','signRequest','computeSignature',
                      'getClientCheckData','getSecret','encrypt'];
      for (const name of checks){
        if (t && typeof t[name] === 'function') out[name] = 'SDK';
      }
      // cek juga di window
      for (const name of checks){
        if (typeof window[name] === 'function') out['window.'+name] = 'WIN';
      }
      // cek interceptor
      if (window.__INTERCEPTOR__) out.__INTERCEPTOR__ = typeof window.__INTERCEPTOR__;
      return out;
    }""")
    print("  ", json.dumps(gen), flush=True)

    # === 3. TEST: kirim request lewat interceptor SDK ===
    print("\n=== TEST: gen header via fetch hook SDK ===", flush=True)
    test = pg.evaluate("""async ()=>{
      try {
        // fetch biasa -> SDK otomatis tambah header
        const r = await fetch('/api/v4/account/basic/get_account_info', {
          credentials:'include',
          headers:{'Accept':'application/json','X-Requested-With':'XMLHttpRequest',
                   'X-API-SOURCE':'pc','X-Shopee-Language':'id'}
        });
        const txt = await r.text();
        let j = null; try{j=JSON.parse(txt);}catch(e){}
        return {s:r.status, err:j&&j.error, data:j&&j.data?{uid:j.data.userid,user:j.data.username}:null,
                hasAC: !!window.__SAP_CAPTURED && window.__SAP_CAPTURED.length};
      } catch(e){ return {err:e.toString().slice(0,100)}; }
    }""")
    print("  ", json.dumps(test)[:400], flush=True)

    # === 4. tangkap header yang di-generate SDK untuk request itu ===
    print("\n=== HEADER YANG DI-GENERATE SDK ===", flush=True)
    hdrs = pg.evaluate("""()=>{
      const c = window.__SAP_CAPTURED || [];
      if (!c.length) return {err:'tidak ada capture'};
      // ambil yang terbaru
      const last = c[c.length-1];
      return last;
    }""")
    print(json.dumps(hdrs, indent=1)[:1200] if isinstance(hdrs, dict) else hdrs, flush=True)

    # === 5. generate N set header untuk request berbeda ===
    print("\n=== GENERATE 3 SET HEADER (ri harus beda tiap request) ===", flush=True)
    multi = pg.evaluate("""async ()=>{
      const out = [];
      for (let i=0;i<3;i++){
        const before = (window.__SAP_CAPTURED||[]).length;
        await fetch('/api/v4/pages/get_footer_layout', {credentials:'include',
          headers:{'Accept':'application/json','X-API-SOURCE':'pc'}});
        const c = window.__SAP_CAPTURED||[];
        if (c.length > before) out.push(c[c.length-1].headers);
        await new Promise(r=>setTimeout(r,300));
      }
      return out;
    }""")
    for i, h in enumerate(multi, 1):
        print(f"\n  --- SET {i} ---", flush=True)
        for k, v in h.items():
            print(f"    {k}: {v[:80]}", flush=True)

    # === 6. simpan ===
    json.dump({"sdk": sdk, "gen": gen, "headers_sample": multi,
               "captured_last": hdrs},
              open("/root/shopee-verify/sap_generated.json", "w"), indent=1)
    print("\n  -> sap_generated.json", flush=True)

    # === 7. TES LANGSUNG: cart/mini dengan header SDK ===
    print("\n=== TES cart/mini DENGAN SDK HEADER ===", flush=True)
    r = pg.evaluate("""async ()=>{
      const res = await fetch('/api/v4/cart/mini', {
        method:'POST', credentials:'include',
        headers:{'Accept':'application/json','X-Requested-With':'XMLHttpRequest',
                 'X-API-SOURCE':'pc','X-Shopee-Language':'id',
                 'Content-Type':'application/json'},
        body: JSON.stringify({version_list:[3145728,65]})
      });
      let j=null; try{j=await res.json();}catch(e){}
      return {s:res.status, e:j&&j.error,
              tid: j&&j['6']&&j['6']['0'] ? j['6']['0'].slice(0,40) : null};
    }""")
    print("  ", json.dumps(r), flush=True)

    br.close()

print("\n=== SELESAI ===", flush=True)
