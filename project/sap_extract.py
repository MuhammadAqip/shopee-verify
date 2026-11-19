# -*- coding: utf-8 -*-
"""sap_extract.py — ekstrak ALGORITMA x-sap-sec & x-sap-ri dari SDK Shopee
DENGAN MENJALANKAN SDK-NYA di browser (bukan statis).

Cara: buka shopee.co.id, hook fetch untuk tangkap header asli,
lalu panggil SDK dari global untuk generate signature kita sendiri.
"""
import json, time, sys

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"

from playwright.sync_api import sync_playwright

CAPTURED = []

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,900"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 900},
                         proxy={"server": PROXY})
    pg = ctx.new_page()

    # hook XHR + fetch SEBELUM halaman load
    pg.add_init_script("""
      window.__SAP_CAPTURED = [];
      const origFetch = window.fetch;
      window.fetch = function(...args){
        try{
          let url = typeof args[0]==='string'?args[0]:args[0].url;
          let opts = args[1]||{};
          let hs = opts.headers||{};
          let hdrs = {};
          if (hs instanceof Headers) hs.forEach((v,k)=>{hdrs[k]=v});
          else if (Array.isArray(hs)) hs.forEach(([k,v])=>{hdrs[k]=v});
          else Object.assign(hdrs, hs);
          const sap = {};
          for (const k in hdrs){
            const lk=k.toLowerCase();
            if (lk.startsWith('x-sap')||lk.startsWith('af-ac')||lk==='x-sz-sdk-version')
              sap[k]=hdrs[k];
          }
          if (Object.keys(sap).length){
            window.__SAP_CAPTURED.push({url:url.slice(0,80), method:opts.method||'GET',
                                        headers:sap, body:(opts.body||'').toString().slice(0,100)});
          }
        }catch(e){}
        return origFetch.apply(this, args);
      };
      const origOpen = XMLHttpRequest.prototype.open;
      const origSet = XMLHttpRequest.prototype.setRequestHeader;
      XMLHttpRequest.prototype.open = function(m,u){ this.__m=m; this.__u=u; return origOpen.apply(this,arguments); };
      XMLHttpRequest.prototype.setRequestHeader = function(k,v){
        if (!this.__h) this.__h={};
        this.__h[k]=v;
        return origSet.apply(this,arguments);
      };
      const origSend = XMLHttpRequest.prototype.send;
      XMLHttpRequest.prototype.send = function(body){
        try{
          const sap={};
          for (const k in (this.__h||{})){
            const lk=k.toLowerCase();
            if (lk.startsWith('x-sap')||lk.startsWith('af-ac')||lk==='x-sz-sdk-version')
              sap[k]=this.__h[k];
          }
          if (Object.keys(sap).length){
            window.__SAP_CAPTURED.push({url:(this.__u||'').slice(0,80),
                                        method:this.__m||'GET', headers:sap,
                                        body:(body||'').toString().slice(0,100)});
          }
        }catch(e){}
        return origSend.apply(this,arguments);
      };
    """)

    print("=== buka homepage ===", flush=True)
    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(10000)

    print("=== scroll & interaksi (trigger API) ===", flush=True)
    pg.mouse.move(400, 300)
    pg.mouse.wheel(0, 900)
    pg.wait_for_timeout(3000)
    pg.mouse.wheel(0, 900)
    pg.wait_for_timeout(3000)

    cap = pg.evaluate("()=>window.__SAP_CAPTURED||[]")
    print(f"\n=== {len(cap)} request dengan SAP header ===", flush=True)
    for it in cap[:8]:
        print(f"\n  {it['method']} {it['url']}")
        for k, v in it['headers'].items():
            print(f"    {k}: {v[:70]}{'...' if len(v) > 70 else ''}")

    # === cari SDK di global ===
    print("\n=== cari SDK di window ===", flush=True)
    sdk = pg.evaluate("""()=>{
      const out = {};
      for (const k of Object.keys(window)) {
        if (/sap|sz|sec|sign|dfp|sdk|anticrawl/i.test(k)) {
          try{ out[k] = typeof window[k]; }catch(e){}
        }
      }
      return out;
    }""")
    print("  ", json.dumps(sdk)[:600], flush=True)

    # coba akses modul webpack
    print("\n=== coba akses webpack module 18218 ===", flush=True)
    res = pg.evaluate("""()=>{
      try {
        // cari webpack chunk
        const chunks = window.rspackChunkshopee_pc || window.webpackChunkshopee_pc;
        if (!chunks) return {err:'no chunks', keys:Object.keys(window).filter(k=>/chunk/i.test(k)).slice(0,5)};
        let found = null;
        // push dummy module to access require
        const mod = {};
        chunks.push([[Math.floor(Math.random()*1e6)], {}, function(r){
          found = r;
        }]);
        if (!found) return {err:'no require'};
        // cari module exports yang punya SAP
        const names = ['initNewSAPSDK','createSecureFetchUtils','SapSignatureLevel'];
        const out = {};
        for (const k of Object.keys(found.m||{})) {
          // skip
        }
        // coba require modul yang kemungkinan SAP
        return {ok:true, hasM:!!found.m, sample:Object.keys(found).slice(0,8)};
      } catch(e) { return {err: e.toString().slice(0,100)}; }
    }""")
    print("  ", json.dumps(res)[:500], flush=True)

    # simpan hasil
    json.dump({"captured": cap, "sdk": sdk}, open("/root/shopee-verify/sap_capture.json", "w"), indent=1)
    print("\n  -> sap_capture.json", flush=True)

    # === coba decode format x-sap-ri ===
    print("\n=== analisis x-sap-ri ===", flush=True)
    for it in cap[:5]:
        h = it['headers']
        ri = next((v for k, v in h.items() if k.lower() == 'x-sap-ri'), None)
        sec = next((v for k, v in h.items() if k.lower() == 'x-sap-sec'), None)
        if ri:
            print(f"  {it['url'][:45]}")
            print(f"    RI  len={len(ri)}: {ri[:80]}")
            print(f"    SEC len={len(sec or '')}: {(sec or '')[:80]}")
            # cek prefix
            if len(ri) >= 8:
                try:
                    ts = int(ri[:8], 16)
                    print(f"    prefix hex {ri[:8]} -> ts={ts} (now={int(time.time())})")
                except Exception as e:
                    print(f"    prefix bukan ts: {e}")

    br.close()

print("\n=== SELESAI ===", flush=True)
