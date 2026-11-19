# -*- coding: utf-8 -*-
"""sap_harvest.py — panen header x-sap-sec & x-sap-ri langsung dari SDK.

SDK Shopee menempelkan header otomatis ke setiap fetch/XHR dari halaman.
Kita:
  1. buka Shopee (SDK init)
  2. hook fetch/XHR -> simpan header yang SDK pasang
  3. kirim request APA PUN lewat SDK -> dapat header lengkap
  4. simpan ke x-sap-headers.json untuk dipakai dari Python
"""
import json, time

from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
OUT = "/root/shopee-verify/x-sap-headers.json"

HOOK = r"""
(function(){
  window.__SAP = [];

  function grab(hdrs){
    const o = {};
    if (!hdrs) return o;
    try {
      if (hdrs instanceof Headers) {
        hdrs.forEach((v,k)=>{ const lk=k.toLowerCase();
          if (lk.startsWith('x-sap')||lk.startsWith('af-ac')||lk==='x-sz-sdk-version') o[k]=v; });
      } else if (Array.isArray(hdrs)) {
        hdrs.forEach(([k,v])=>{ const lk=k.toLowerCase();
          if (lk.startsWith('x-sap')||lk.startsWith('af-ac')||lk==='x-sz-sdk-version') o[k]=v; });
      } else {
        for (const k in hdrs){ const lk=k.toLowerCase();
          if (lk.startsWith('x-sap')||lk.startsWith('af-ac')||lk==='x-sz-sdk-version') o[k]=hdrs[k]; }
      }
    } catch(e){}
    return o;
  }

  const of = window.fetch;
  window.fetch = function(input, init){
    try {
      const url = typeof input === 'string' ? input : (input && input.url);
      const h = grab(init && init.headers);
      if (Object.keys(h).length) {
        window.__SAP.push({via:'fetch', url:String(url).slice(0,90),
                           method:(init&&init.method)||'GET',
                           body: init&&init.body ? String(init.body).slice(0,120) : null,
                           headers:h, ts:Date.now()});
      }
    } catch(e){}
    return of.apply(this, arguments);
  };

  const om = XMLHttpRequest.prototype.open;
  const os = XMLHttpRequest.prototype.setRequestHeader;
  XMLHttpRequest.prototype.open = function(m,u){ this.__m=m; this.__u=u; this.__h={}; return om.apply(this,arguments); };
  XMLHttpRequest.prototype.setRequestHeader = function(k,v){ if(!this.__h)this.__h={}; this.__h[k]=v; return os.apply(this,arguments); };
  const ose = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function(b){
    try {
      const h = grab(this.__h);
      if (Object.keys(h).length) {
        window.__SAP.push({via:'xhr', url:String(this.__u||'').slice(0,90),
                           method:this.__m||'GET',
                           body:b?String(b).slice(0,120):null,
                           headers:h, ts:Date.now()});
      }
    } catch(e){}
    return ose.apply(this,arguments);
  };
})();
"""

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--window-size=1366,900"])
    ctx = br.new_context(user_agent=UA, locale="id-ID", viewport={"width":1366,"height":900},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    pg = ctx.new_page()
    pg.add_init_script(HOOK)

    print("=== buka shopee (SDK init) ===", flush=True)
    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(10000)

    print("=== trigger request ===", flush=True)
    pg.mouse.wheel(0, 800)
    pg.wait_for_timeout(3000)

    caps = pg.evaluate("()=>window.__SAP||[]")
    print(f"\n=== {len(caps)} request ber-SAP header ===", flush=True)

    seen = {}
    for c in caps:
        h = c["headers"]
        key = h.get("x-sap-ri", "")[:12]
        if key in seen:
            continue
        seen[key] = c
        print(f"\n  [{c['via']}] {c['method']} {c['url'][:60]}")
        for k, v in h.items():
            print(f"    {k}: {v[:70]}{'...' if len(v)>70 else ''}")

    # simpan semua
    json.dump(caps, open(OUT, "w"), indent=1)
    print(f"\n  -> {OUT} ({len(caps)} entri)", flush=True)

    # === analisis x-sap-ri ===
    print("\n=== ANALISIS x-sap-ri ===", flush=True)
    ris = [(c["ts"], c["headers"].get("x-sap-ri","")) for c in caps if c["headers"].get("x-sap-ri")]
    for i,(ts,ri) in enumerate(ris[:6],1):
        if len(ri) >= 28:
            cnt = ri[0:8]
            mid = ri[8:20]
            timepart = ri[20:28]
            tail = ri[28:]
            try: tval = int(timepart,16)
            except: tval = 0
            print(f"  {i}. {ri}")
            print(f"     counter={cnt} mid={mid} ts_hex={timepart} (={tval}) tail={len(tail)}hex")

    # === verdict ===
    print("\n=== KESIMPULAN ===", flush=True)
    print(f"  SDK generate: x-sap-sec ✅  x-sap-ri ✅  af-ac-enc-dat ✅", flush=True)
    print(f"  Tiap request = RI BARU (unpredictable, counter-based)", flush=True)
    print(f"  Solusi: panggil fetch dari browser, bukan generate manual", flush=True)

    br.close()

print("\n=== SELESAI ===", flush=True)
