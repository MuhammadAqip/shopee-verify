# -*- coding: utf-8 -*-
"""sap_find.py — temukan modul SAP yang sebenarnya.

Dari bundle: module 18218 export `initNewSAPSDK`. Metadata nama:
  SapSignatureLevel, AntiCrawlerClientId, ChallengeType, PlatformEnum,
  RedirectType, ActionType, createSecureFetchUtils.

Cari di webpack runtime dengan nama-nama ini.
"""
import json, time

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
    pg = ctx.new_page()

    print("=== buka shopee ===", flush=True)
    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(10000)

    # === 1. semua global window yang terkait sap ===
    print("\n=== SEMUA GLOBAL __xxx ===", flush=True)
    g = pg.evaluate("""()=>{
      const out = [];
      for (const k of Object.keys(window)){
        if (k.startsWith('__') || /sap|sz|sec|anticrawl|crawler|verif/i.test(k)){
          let t = typeof window[k];
          let v = null;
          if (t === 'string' || t === 'number' || t === 'boolean') v = String(window[k]).slice(0,60);
          out.push([k, t, v]);
        }
      }
      return out;
    }""")
    for row in g:
        print(f"  {row[0]:<35} {row[1]:<10} {row[2] or ''}", flush=True)

    # === 2. cari webpack require + scan semua modul ===
    print("\n=== SCAN WEBPACK MODULES ===", flush=True)
    scan = pg.evaluate("""()=>{
      const chunks = window.rspackChunkshopee_pc;
      if (!chunks) return {err:'no rspackChunkshopee_pc'};
      let req = null;
      try {
        chunks.push([[Math.floor(Math.random()*1e7)], {}, function(r){ req = r; }]);
      } catch(e){ return {err:'push fail: '+e}; }
      if (!req) return {err:'no require'};

      // kumpulkan semua module id
      const ids = [];
      try {
        // akses modules via require.m or __webpack_modules__
        const m = req.m || {};
        for (const k in m) ids.push(k);
      } catch(e){}

      // cari module yang punya initNewSAPSDK
      const found = [];
      for (const id of ids.slice(0, 3000)) {
        try {
          const mod = req(id);
          if (!mod) continue;
          const keys = Object.keys(mod);
          const hit = keys.filter(k => /sap|signature|anticrawl|securefetch/i.test(k));
          if (hit.length >= 2) {
            found.push({id, keys: keys.slice(0, 20)});
          }
        } catch(e){}
      }
      return {total: ids.length, found: found.slice(0, 10)};
    }""")
    print("  ", json.dumps(scan, indent=1)[:1500], flush=True)

    # === 3. cari text 'x-sap-sec' di semua modul function source ===
    print("\n=== CARI FUNGSI DENGAN 'x-sap-sec' ===", flush=True)
    src = pg.evaluate("""()=>{
      const chunks = window.rspackChunkshopee_pc;
      let req = null;
      try { chunks.push([[Math.floor(Math.random()*1e7)], {}, function(r){ req = r; }]); } catch(e){}
      if (!req) return {err:'no req'};
      const ids = [];
      try { const m = req.m || {}; for (const k in m) ids.push(k); } catch(e){}
      const out = [];
      for (const id of ids.slice(0, 3000)) {
        try {
          const mod = req(id);
          if (!mod || typeof mod !== 'object') continue;
          for (const k of Object.keys(mod)) {
            const fn = mod[k];
            if (typeof fn === 'function') {
              const s = fn.toString();
              if (s.includes('x-sap-sec') || s.includes('x-sap-ri') ||
                  s.includes('initNewSAPSDK') || s.includes('SapSignatureLevel')) {
                out.push({id, key:k, len:s.length, head:s.slice(0, 200)});
              }
            }
          }
        } catch(e){}
      }
      return {n: out.length, items: out.slice(0, 6)};
    }""")
    print("  ", json.dumps(src, indent=1)[:2000], flush=True)

    # === 4. cari di proto chain / closures ===
    print("\n=== CEK window.__INTERCEPTOR__ dll ===", flush=True)
    probe = pg.evaluate("""()=>{
      const names = ['__INTERCEPTOR__','__sap','__SAP__','sap','SAP','sz','SecuritySDK','securitySDK'];
      const out = {};
      for (const n of names) {
        if (window[n] !== undefined) out[n] = typeof window[n];
      }
      // cek apakah ada objek dengan fungsi spesifik
      return out;
    }""")
    print("  ", json.dumps(probe), flush=True)

    # simpan
    json.dump({"globals": g, "scan": scan, "src": src, "probe": probe},
              open("/root/shopee-verify/sap_find.json", "w"), indent=1)
    print("\n  -> sap_find.json", flush=True)

    br.close()

print("\n=== SELESAI ===", flush=True)
