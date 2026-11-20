# -*- coding: utf-8 -*-
"""df_harvest.py — panen security_device_fingerprint dari request NYATA.

Dari sumber:
  sfu_deob.js: useSecurityDfp -> i.R({}) -> {device_sz_fingerprint}
  dataFormatter -> {security_device_fingerprint: value} -> masuk ke e.data (body)

Jadi: tiap POST yang pakai useSecurityDfp punya DF di BODY.
Hook fetch/axios di browser, tangkap SEMUA body yang punya key itu.

Target endpoint yang pasti pakai DFP:
  - /api/v4/cart/mini   (POST)
  - /api/v4/pdp/get_pc
  - /api/v4/account/management/change_phone_init_v2
  - /api/v4/anti_fraud/ivs/token/verify  <-- TARGET

Hasil: df_samples.json
"""
import json, sys, time

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
CKF = sys.argv[1] if len(sys.argv) > 1 else None
OUT = "/root/shopee-verify/df_samples.json"


def log(*a):
    print(*a, flush=True)


from playwright.sync_api import sync_playwright

HOOK = r"""
(() => {
  window.__CAP = [];
  const REC = (url, method, body, hdrs) => {
    try {
      const s = typeof body === 'string' ? body : '';
      const m = s.match(/"(?:security_)?device_sz_fingerprint"\s*:\s*"([^"]{50,})"/);
      if (m) {
        window.__CAP.push({u: String(url).slice(-60), m: method, df: m[1],
                           len: m[1].length, t: Date.now()});
      }
      // juga tangkap x-sap headers
      if (hdrs) {
        const h = hdrs instanceof Headers ? Object.fromEntries(hdrs) : hdrs;
        const ri = h['x-sap-ri'] || (Array.isArray(h) ? (h.find(x=>x[0]==='x-sap-ri')||[])[1] : null);
        const sec = h['x-sap-sec'] || (Array.isArray(h) ? (h.find(x=>x[0]==='x-sap-sec')||[])[1] : null);
        if (ri || sec) window.__CAP.push({u: String(url).slice(-60), hdr: true,
                                          ri: ri, sec: sec ? sec.length : 0, t: Date.now()});
      }
    } catch(e) {}
  };

  const of = window.fetch;
  window.fetch = function(input, init) {
    try {
      const url = typeof input === 'string' ? input : (input && input.url);
      REC(url, (init && init.method) || 'GET', init && init.body, init && init.headers);
    } catch(e) {}
    return of.apply(this, arguments);
  };

  // XHR
  const oo = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(m,u){ this.__m=m; this.__u=u; return oo.apply(this,arguments); };
  const os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function(b){
    try { REC(this.__u, this.__m, b, null); } catch(e){}
    return os.apply(this, arguments);
  };
  const osr = XMLHttpRequest.prototype.setRequestHeader;
  XMLHttpRequest.prototype.setRequestHeader = function(k,v){
    try { if (/x-sap-(ri|sec)/i.test(k)) { this.__ri = this.__ri||{}; this.__ri[k]=v; } } catch(e){}
    return osr.apply(this, arguments);
  };

  window.__get = () => window.__CAP.slice(-60);
})();
"""

res = []

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,1000",
        "--disable-blink-features=AutomationControlled"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 1000},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    if CKF:
        ck = open(CKF).read().strip()
        cookies = []
        for p in ck.split(";"):
            if "=" in p:
                k, v = p.strip().split("=", 1)
                cookies.append({"name": k, "value": v,
                                "domain": ".shopee.co.id", "path": "/"})
        ctx.add_cookies(cookies)
        log(f"cookie dari {CKF}: {len(cookies)} buah")
    ctx.add_init_script(HOOK)
    pg = ctx.new_page()

    log("=== buka shopee ===")
    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(14000)

    # trigger beberapa POST
    log("\n=== trigger POST ber-DFP ===")
    for ep, body in (
        ("/api/v4/cart/mini", {"version_list": [3145728, 65]}),
        ("/api/v4/account/management/change_phone_init", {}),
        ("/api/v4/account/management/change_phone_init_v2", {}),
    ):
        rr = pg.evaluate("""async ([ep, body]) => {
          try {
            const res = await fetch(ep, {method:'POST', credentials:'include',
              headers:{'Content-Type':'application/json','X-API-SOURCE':'pc',
                       'X-Requested-With':'XMLHttpRequest','Accept':'application/json'},
              body: JSON.stringify(body)});
            let j=null; try{j=await res.json();}catch(e){}
            return {s:res.status, e:j&&j.error, keys:j&&j.data?Object.keys(j.data).slice(0,8):null};
          } catch(e) { return {err:String(e).slice(0,50)}; }
        }""", [ep, body])
        log(f"  {ep.split('/')[-1]}: {rr}")
        pg.wait_for_timeout(2200)

    cap = pg.evaluate("()=>window.__get()")
    log(f"\n=== capture: {len(cap)} ===")
    dfs = {}
    for c in cap:
        if c.get("df"):
            dfs[c["df"]] = c
            log(f"  DF {c['len']}B dari {c['u']}")
        elif c.get("hdr"):
            log(f"  HDR ri={str(c.get('ri'))[:40]} sec={c.get('sec')}B dari {c['u']}")

    res = {"cap": cap, "dfs": list(dfs.keys())}
    json.dump(res, open(OUT, "w"), indent=1)

    if dfs:
        # JANGAN max(key=len) — itu memilih blob report SZ-SDK 2534 char
        # (prefix JxcBAAAABAAAAIAAA) yang muncul juga di SEC.txt,
        # SAP_CAPTURE.json, MITM.jsonl di konteks /v2/shpsec/web/report.
        # DF yang benar = 5 segmen pipe.
        valid = [d for d in dfs.keys() if d.count("|") == 4]
        if valid:
            best = min(valid, key=len)
            json.dump({"security_device_fingerprint": best},
                      open("device_df.json", "w"))
            log(f"\n🟢 DF FRESH tersimpan: {len(best)}B")
            log(f"   {best[:100]}...")
        else:
            log(f"\n⚠️ {len(dfs)} kandidat tapi TIDAK ADA yang format pipe 5 segmen.")
            log("   device_df.json tidak ditulis (fail-closed).")
    else:
        log("\n❌ DF tidak tertangkap")

    br.close()
