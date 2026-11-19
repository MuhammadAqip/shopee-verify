# -*- coding: utf-8 -*-
"""sap_deep.py — bongkar __ShopeeSSS_root & __SFUC.

Dugaan:
  __SFUC = SapSignatureLevel enum (8 = HIGH?)
  __ShopeeSSS_root = SDK root object dengan fungsi sign
"""
import json

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--window-size=1366,900"])
    ctx = br.new_context(user_agent=UA, locale="id-ID", viewport={"width":1366,"height":900}, proxy={"server": PROXY})
    pg = ctx.new_page()

    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(9000)

    # === 1. __ShopeeSSS_root ===
    print("=== __ShopeeSSS_root ===", flush=True)
    r = pg.evaluate("""()=>{
      const o = window.__ShopeeSSS_root;
      if (!o) return {err:'null'};
      const out = {type: typeof o, keys: [], methods: [], samples: {}};
      try {
        out.keys = Object.keys(o).slice(0,40);
        // semua properti, termasuk non-enumerable
        out.allProps = Object.getOwnPropertyNames(o).slice(0,60);
        for (const k of out.allProps) {
          try {
            const v = o[k];
            const t = typeof v;
            if (t === 'function') out.methods.push(k+':'+v.length);
            else if (t === 'string' || t === 'number') out.samples[k] = String(v).slice(0,60);
            else if (t === 'object' && v) out.samples[k] = '[obj:'+Object.keys(v).slice(0,6).join(',')+']';
          } catch(e){}
        }
      } catch(e){ out.err = e.toString().slice(0,100); }
      return out;
    }""")
    print(json.dumps(r, indent=1)[:2500], flush=True)

    # === 2. __SFUC ===
    print("\n=== __SFUC ===", flush=True)
    r2 = pg.evaluate("""()=>{
      const v = window.__SFUC;
      const out = {type: typeof v, val: null};
      try{ if(typeof v !== 'object') out.val = String(v); }catch(e){}
      if (typeof v === 'object' && v){
        out.keys = Object.keys(v);
        out.props = Object.getOwnPropertyNames(v);
      }
      return out;
    }""")
    print(json.dumps(r2, indent=1)[:600], flush=True)

    # === 3. cari objek lain yang punya method signature ===
    print("\n=== OBJEK DENGAN METHOD SIGN === ", flush=True)
    r3 = pg.evaluate("""()=>{
      const found = [];
      const check = (obj, name) => {
        if (!obj || typeof obj !== 'object') return;
        try {
          const ks = Object.getOwnPropertyNames(obj);
          const fns = ks.filter(k=>{ try{return typeof obj[k]==='function'}catch(e){return false} });
          const hits = fns.filter(k=>/sign|sec|ri$|token|header|generate|encrypt|check/i.test(k));
          if (hits.length >= 1 && fns.length >= 1) {
            found.push({name, fns: fns.slice(0,12), hits});
          }
        } catch(e){}
      };
      // periksa global yang menarik
      for (const k of ['__ShopeeSSS_root','__spt','__sbi','trackingSDK','__STORE__',
                       '__PAGE_CONTEXT__','__USER_AUTHENTICATION_CONTEXT__']){
        if (window[k]) check(window[k], k);
      }
      return found;
    }""")
    print(json.dumps(r3, indent=1)[:2000], flush=True)

    # === 4. coba panggil fungsi sign kalau ada ===
    print("\n=== COBA PANGGIL SIGN ===", flush=True)
    r4 = pg.evaluate("""async ()=>{
      const o = window.__ShopeeSSS_root;
      if (!o) return {err:'null'};
      const results = {};
      const tryFn = async (n, args) => {
        try {
          if (typeof o[n] === 'function') {
            const v = await o[n](...(args||[]));
            results[n] = typeof v === 'string' ? v.slice(0,100) : JSON.stringify(v).slice(0,120);
          }
        } catch(e){ results[n] = 'ERR:'+e.toString().slice(0,60); }
      };
      // coba fungsi yang ada di allProps
      const names = Object.getOwnPropertyNames(o).filter(k=>{
        try{return typeof o[k]==='function'}catch(e){return false}
      });
      results.__available = names.slice(0,20);
      // coba generate
      for (const n of names){
        if (/sign|sec|header|gen/i.test(n)){
          await tryFn(n, []);
        }
      }
      return results;
    }""")
    print(json.dumps(r4, indent=1)[:1500], flush=True)

    # === 5. DEEP: dapatkan argument list dari fungsi sign ===
    print("\n=== SIGNATURE FUNGSI (arg names) ===", flush=True)
    r5 = pg.evaluate("""()=>{
      const o = window.__ShopeeSSS_root;
      if (!o) return {err:'null'};
      const out = {};
      for (const k of Object.getOwnPropertyNames(o)){
        try{
          if (typeof o[k]==='function'){
            const src = o[k].toString();
            out[k] = {len: src.length, head: src.slice(0,200)};
          }
        }catch(e){}
      }
      return out;
    }""")
    print(json.dumps(r5, indent=1)[:2500], flush=True)

    json.dump({"root": r, "sfuc": r2, "objs": r3, "call": r4, "src": r5},
              open("/root/shopee-verify/sap_deep.json","w"), indent=1)
    print("\n  -> sap_deep.json", flush=True)

    br.close()

print("\n=== SELESAI ===", flush=True)
