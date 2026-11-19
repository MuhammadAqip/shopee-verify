# -*- coding: utf-8 -*-
"""df_gen.py — generate security_device_fingerprint FRESH dari SDK.

Dari sfu_deob.js modul 4786 (createSecureFetchUtils):
  i.R({})  -> { device_sz_fingerprint: <base64>, sz-token?: <...> }

SDK meng-expose `createSecureFetchUtils`. Kita:
  1. Buka halaman shopee (SDK load)
  2. Panggil SDK untuk generate DF
  3. Simpan DF + SZ token
  4. Kembalikan DF valid yang BISA PAKAI di token/verify

Juga tangkap:
  - apapun yang SDK hasilkan saat token/verify dijalankan
"""
import json, sys, time

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
OUT = "/root/shopee-verify/df_fresh.json"


def log(*a):
    print(*a, flush=True)


from playwright.sync_api import sync_playwright

# Hook yang dipasang sebelum SDK load
HOOK = r"""
(() => {
  window.__DF = [];
  window.__SZ = [];
  window.__SDK = null;

  // Polling untuk SDK global
  let n = 0;
  const iv = setInterval(() => {
    n++;
    // cari objek yang punya createSecureFetchUtils
    for (const k of Object.keys(window)) {
      try {
        const v = window[k];
        if (v && typeof v === 'object' && typeof v.createSecureFetchUtils === 'function') {
          window.__SDK = v;
          break;
        }
      } catch(e) {}
    }
    if (window.__SDK || n > 300) clearInterval(iv);
  }, 100);

  // Hook fetch: rekam body yang punya device_sz_fingerprint
  const of = window.fetch;
  window.fetch = function(input, init) {
    try {
      let b = init && init.body;
      if (typeof b === 'string' && b.indexOf('device_sz_fingerprint') !== -1) {
        const m = b.match(/"security_device_fingerprint"\s*:\s*"([^"]+)"/)
               || b.match(/"device_sz_fingerprint"\s*:\s*"([^"]+)"/);
        if (m) window.__DF.push({v: m[1], src: 'fetch-body', t: Date.now()});
      }
    } catch(e) {}
    return of.apply(this, arguments);
  };

  window.__getDF = () => ({df: window.__DF.slice(-5), sz: window.__SZ.slice(-5),
                           hasSdk: !!window.__SDK,
                           sdkKeys: window.__SDK ? Object.keys(window.__SDK).slice(0,30) : []});
})();
"""


with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,1000",
        "--disable-blink-features=AutomationControlled"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 1000},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    ctx.add_init_script(HOOK)
    pg = ctx.new_page()

    log("=== 1. buka homepage ===")
    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(12000)

    d = pg.evaluate("()=>window.__getDF()")
    log(f"  hasSdk: {d.get('hasSdk')}")
    log(f"  sdkKeys: {d.get('sdkKeys')}")

    # Coba panggil SDK secara eksplisit
    log("\n=== 2. panggil SDK untuk generate DF ===")
    r = pg.evaluate("""async () => {
      try {
        const out = {};
        // cari semua global yang punya initNewSAPSDK / createSecureFetchUtils
        const globals = [];
        for (const k of Object.keys(window)) {
          try {
            const v = window[k];
            if (!v) continue;
            if (typeof v.createSecureFetchUtils === 'function' ||
                typeof v.initNewSAPSDK === 'function') {
              globals.push(k);
            }
          } catch(e) {}
        }
        out.globals = globals;
        // juga cek window.__ShopeeSSS_root
        out.rootKeys = window.__ShopeeSSS_root
          ? Object.keys(window.__ShopeeSSS_root).slice(0, 20) : null;
        return out;
      } catch(e) { return {err: String(e).slice(0,80)}; }
    }""")
    log(f"  {r}")

    # Trigger API POST yang PAKAI useSecurityDfp — misal item/get atau cart
    log("\n=== 3. trigger POST ber-DFP ===")
    for ep, body in (
        ("/api/v4/cart/mini", {"version_list": [3145728, 65]}),
        ("/api/v4/pdp/get_pc", {"itemid": 1, "shopid": 1}),
        ("/api/v4/search/search_items", {"by": "relevancy", "keyword": "test",
                                          "limit": 20, "newest": 0, "order": "desc",
                                          "page_type": "search", "scenario": "PAGE_GLOBAL_SEARCH",
                                          "version": 2}),
    ):
        rr = pg.evaluate("""async ([ep, body]) => {
          try {
            const res = await fetch(ep, {
              method: 'POST', credentials: 'include',
              headers: {'Content-Type':'application/json','X-API-SOURCE':'pc',
                        'X-Requested-With':'XMLHttpRequest','Accept':'application/json'},
              body: JSON.stringify(body)
            });
            let j = null; try { j = await res.json(); } catch(e) {}
            return {s: res.status, e: j && j.error};
          } catch(e) { return {err: String(e).slice(0,60)}; }
        }""", [ep, body])
        log(f"  {ep}: {rr}")
        pg.wait_for_timeout(2500)

    d2 = pg.evaluate("()=>window.__getDF()")
    log(f"\n=== 4. DF tertangkap: {len(d2.get('df') or [])} ===")
    for x in (d2.get("df") or []):
        log(f"  {len(x['v'])}B  {x['v'][:70]}...")

    json.dump(d2, open(OUT, "w"), indent=1)
    log(f"-> {OUT}")
    br.close()
