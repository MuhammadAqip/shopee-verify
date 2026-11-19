# -*- coding: utf-8 -*-
"""sap_hunt.py — tangkap __ShopeeSSS_root saat muncul + hook assignment.

Strategi: pasang Object.defineProperty trap SEBELUM page load untuk
menangkap saat SDK di-assign ke window.
"""
import json, time

from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"

HOOK = r"""
(function(){
  window.__CAPTURED_OBJS = {};
  window.__ASSIGN_LOG = [];

  const watch = ['__ShopeeSSS_root','__SFUC','__sap_root','__SAP',
                 '__securitySDK','__sapClient','__szSdk','__SecureFetchUtils'];

  watch.forEach(function(name){
    let _v = undefined;
    try {
      Object.defineProperty(window, name, {
        configurable: true,
        get: function(){ return _v; },
        set: function(nv){
          _v = nv;
          window.__ASSIGN_LOG.push({name: name, t: Date.now(), type: typeof nv});
          if (nv && typeof nv === 'object'){
            try {
              const props = Object.getOwnPropertyNames(nv);
              const fns = props.filter(function(k){
                try{ return typeof nv[k] === 'function'; }catch(e){ return false; }
              });
              window.__CAPTURED_OBJS[name] = {
                props: props.slice(0, 50),
                fns: fns.slice(0, 30),
                src: fns.slice(0, 8).map(function(k){
                  try{ return {k: k, src: nv[k].toString().slice(0, 400)}; }catch(e){ return {k: k}; }
                })
              };
            } catch(e){}
          }
        }
      });
    } catch(e){}
  });

  // hook juga: setelah 3 detik, scan semua global yang punya method sign
  setTimeout(function(){
    window.__SCAN = [];
    for (const k of Object.keys(window)){
      try {
        const v = window[k];
        if (!v || typeof v !== 'object') continue;
        const props = Object.getOwnPropertyNames(v);
        const fns = props.filter(function(p){
          try{ return typeof v[p]==='function'; }catch(e){ return false; }
        });
        const sign = fns.filter(function(f){ return /^(sign|getSign|signature|genSec|getSec|computeSign|createSign|buildSign)/i.test(f); });
        if (sign.length) window.__SCAN.push({name: k, sign: sign, allFns: fns.slice(0,15)});
      } catch(e){}
    }
  }, 6000);
})();
"""

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--window-size=1366,900"])
    ctx = br.new_context(user_agent=UA, locale="id-ID", viewport={"width":1366,"height":900}, proxy={"server": PROXY})
    pg = ctx.new_page()
    pg.add_init_script(HOOK)

    print("=== buka shopee (SDK akan init) ===", flush=True)
    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(12000)

    print("\n=== ASSIGN LOG ===", flush=True)
    al = pg.evaluate("()=>window.__ASSIGN_LOG||[]")
    print(json.dumps(al, indent=1)[:1200], flush=True)

    print("\n=== CAPTURED OBJECTS ===", flush=True)
    co = pg.evaluate("()=>window.__CAPTURED_OBJS||{}")
    print(json.dumps(co, indent=1)[:3000], flush=True)

    print("\n=== SCAN GLOBAL SIGN ===", flush=True)
    sc = pg.evaluate("()=>window.__SCAN||[]")
    print(json.dumps(sc, indent=1)[:1500], flush=True)

    # cek __ShopeeSSS_root sekarang
    print("\n=== __ShopeeSSS_root setelah 12s ===", flush=True)
    r = pg.evaluate("""()=>{
      const o = window.__ShopeeSSS_root;
      if (!o) return {err:'null'};
      const props = Object.getOwnPropertyNames(o);
      return {props: props.slice(0,40),
              fns: props.filter(k=>{try{return typeof o[k]==='function'}catch(e){return false}})};
    }""")
    print(json.dumps(r, indent=1)[:1200], flush=True)

    json.dump({"assign": al, "captured": co, "scan": sc, "root": r},
              open("/root/shopee-verify/sap_hunt.json","w"), indent=1)
    print("\n  -> sap_hunt.json", flush=True)

    br.close()

print("\n=== SELESAI ===", flush=True)
