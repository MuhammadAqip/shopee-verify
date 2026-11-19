# -*- coding: utf-8 -*-
"""sdk_instrument.py — instrumentasi SDK saat runtime.

Pendekatan RE dinamis:
  1. Buka shopee.co.id (SDK load)
  2. Hook CryptoJS AES.encrypt -> rekam (plaintext, key)
  3. Hook XMLHttpRequest.setRequestHeader -> rekam header x-sap-*
  4. Trigger request API -> SDK generate header
  5. Tangkap PASANGAN (payload, key, header) -> bisa direplikasi di Python

Hasil: aes_pairs.json  {key, plaintext, ciphertext, header_name}
"""
import json, sys, time, base64

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
OUT = "/root/shopee-verify/aes_pairs.json"


def log(*a):
    print(*a, flush=True)


from playwright.sync_api import sync_playwright

HOOK = r"""
(() => {
  window.__AES = [];
  window.__HDR = [];
  window.__READY = false;

  // Polling untuk CryptoJS yang di-load SDK
  let tries = 0;
  const iv = setInterval(() => {
    tries++;
    const C = window.CryptoJS;
    if (C && C.AES && C.AES.encrypt && !C.__hooked) {
      C.__hooked = true;
      const orig = C.AES.encrypt;
      C.AES.encrypt = function(msg, key, cfg) {
        let plain = null, k = null;
        try {
          plain = (msg && msg.toString) ? msg.toString(C.enc.Utf8) : String(msg);
        } catch(e) { try { plain = String(msg); } catch(e2){} }
        try {
          k = (key && key.toString) ? key.toString(C.enc.Utf8) : String(key);
        } catch(e) { try { k = String(key); } catch(e2){} }
        const out = orig.apply(this, arguments);
        try {
          window.__AES.push({
            key: k, plain: plain ? plain.slice(0, 4000) : null,
            cipher: out ? out.toString() : null,
            cfg: cfg ? {mode: cfg.mode && cfg.mode.name, pad: cfg.pad && cfg.pad.name} : null,
            t: Date.now()
          });
        } catch(e) {}
        return out;
      };
      window.__READY = true;
      clearInterval(iv);
    }
    if (tries > 200) clearInterval(iv);
  }, 100);

  // Hook setRequestHeader
  const os = XMLHttpRequest.prototype.setRequestHeader;
  XMLHttpRequest.prototype.setRequestHeader = function(k, v) {
    try {
      if (/x-sap|af-ac|x-sz/i.test(k)) {
        window.__HDR.push({k: k, v: String(v), url: this.__u || '', t: Date.now()});
      }
    } catch(e) {}
    return os.apply(this, arguments);
  };
  const oo = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(m, u) { this.__u = u; return oo.apply(this, arguments); };

  // Hook fetch Headers
  const of = window.fetch;
  window.fetch = function(input, init) {
    try {
      const h = (init && init.headers) || {};
      const entries = (h instanceof Headers) ? Array.from(h.entries())
        : Array.isArray(h) ? h : Object.entries(h);
      for (const [k, v] of entries) {
        if (/x-sap|af-ac|x-sz/i.test(k)) {
          window.__HDR.push({k: k, v: String(v), url: String(input).slice(0,120), t: Date.now()});
        }
      }
    } catch(e) {}
    return of.apply(this, arguments);
  };

  window.__dump = () => ({aes: window.__AES.slice(-30), hdr: window.__HDR.slice(-60), ready: window.__READY});
})();
"""

res = {"aes": [], "hdr": [], "ready": False}

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,1000"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 1000},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    ctx.add_init_script(HOOK)
    pg = ctx.new_page()

    log("=== 1. buka homepage (SDK init) ===")
    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(9000)

    log("=== 2. trigger API call (search) ===")
    r = pg.evaluate("""async ()=>{
      try{
        const res = await fetch('/api/v4/search/search_prefills', {
          credentials:'include',
          headers:{'X-API-SOURCE':'pc','X-Requested-With':'XMLHttpRequest',
                   'Accept':'application/json'}
        });
        return {s: res.status};
      }catch(e){ return {err:String(e).slice(0,60)}; }
    }""")
    log(f"  search_prefills: {r}")
    pg.wait_for_timeout(3000)

    log("=== 3. trigger cart/mini (proteksi tinggi) ===")
    r2 = pg.evaluate("""async ()=>{
      try{
        const res = await fetch('/api/v4/cart/mini', {
          method:'POST', credentials:'include',
          headers:{'X-API-SOURCE':'pc','X-Requested-With':'XMLHttpRequest',
                   'Content-Type':'application/json','Accept':'application/json'},
          body: JSON.stringify({version_list:[3145728,65]})
        });
        let j=null; try{j=await res.json();}catch(e){}
        return {s:res.status, e:j&&j.error};
      }catch(e){ return {err:String(e).slice(0,60)}; }
    }""")
    log(f"  cart/mini: {r2}")
    pg.wait_for_timeout(4000)

    d = pg.evaluate("()=>window.__dump()")
    res = d
    log(f"\n=== CryptoJS hooked: {d.get('ready')} ===")
    log(f"=== AES calls: {len(d.get('aes') or [])} ===")
    for a in (d.get("aes") or [])[:6]:
        log(f"  key={str(a.get('key'))[:40]!r} plain={str(a.get('plain'))[:70]!r}")
        log(f"     cipher={str(a.get('cipher'))[:70]}")

    log(f"\n=== header x-sap/af-ac captured: {len(d.get('hdr') or [])} ===")
    seen = set()
    for h in (d.get("hdr") or []):
        kk = (h["k"], h["v"][:20])
        if kk in seen:
            continue
        seen.add(kk)
        log(f"  {h['k']}: {h['v'][:70]}")

    json.dump(res, open(OUT, "w"), indent=1)
    log(f"\n-> {OUT}")
    br.close()
