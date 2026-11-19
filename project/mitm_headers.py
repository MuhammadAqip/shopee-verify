# -*- coding: utf-8 -*-
"""mitm_headers.py — capture SEMUA header + cara generate x-sap-sec.

Fokus: bikin headless LOLOS dengan menghilangkan "HeadlessChrome"
dari sec-ch-ua, lalu bandingkan hasil.

Juga hook JS untuk lihat bagaimana SDK generate:
  af-ac-enc-dat, af-ac-enc-sz-token, x-sap-ri, x-sap-sec
"""
import sys, json, ssl, urllib.request, urllib.error, time, os

CK_FILE = "/root/shopee-verify/ck_5th_solved.txt"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
CK = open(CK_FILE).read().strip()

KEEP = {"csrftoken", "SPC_U", "SPC_ST", "SPC_R_T_ID", "SPC_R_T_IV",
        "SPC_T_ID", "SPC_T_IV", "SPC_CLIENTID", "REC_T_ID"}
pairs = [(p.split("=", 1)[0].strip(), p.split("=", 1)[1].strip())
         for p in CK.split(";") if "=" in p]
auth = [(k, v) for k, v in pairs if k in KEEP]

HOOK = r"""
(() => {
  window.__SIG = [];
  const rec = (tag, data) => {
    try { window.__SIG.push({tag, data: String(data).slice(0,200),
                              st: new Error().stack.split('\n').slice(1,3).join('|').slice(0,200)}); }
    catch(e){}
  };
  const _f = window.fetch;
  window.fetch = function(...a) {
    try {
      const u = String(a[0] && (a[0].url || a[0]) || '');
      const o = a[1] || {};
      if (u.includes('/api/v4/')) {
        const h = o.headers || {};
        const hh = {};
        if (h instanceof Headers) { h.forEach((v,k)=>hh[k]=v); }
        else if (Array.isArray(h)) { h.forEach(([k,v])=>hh[k]=v); }
        else { Object.assign(hh, h); }
        rec('REQ ' + u.split('/api/v4/')[1], JSON.stringify(hh).slice(0,400));
      }
    } catch(e) {}
    return _f.apply(this, a);
  };
})();
"""

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage",
        "--window-size=1366,768",
        # HAPUS jejak headless:
        "--headless=new",
        "--disable-features=HeadlessMode",
        "--user-agent=" + UA,
    ])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 768},
                         timezone_id="Asia/Jakarta",
                         proxy={"server": PROXY},
                         extra_http_headers={"Accept-Language": "id-ID,id;q=0.9,en;q=0.8"})
    ctx.add_cookies([{"name": k, "value": v, "domain": ".shopee.co.id",
                      "path": "/"} for k, v in auth])
    # override client hints supaya BUKAN HeadlessChrome
    ctx.add_init_script("""
      Object.defineProperty(navigator, 'userAgentData', {
        get: () => ({
          brands: [
            {brand: "Not:A-Brand", version: "8"},
            {brand: "Chromium", version: "145"},
            {brand: "Google Chrome", version: "145"}
          ],
          mobile: false, platform: "Windows",
          getHighEntropyValues: async () => ({
            architecture: "x86", bitness: "64", model: "", platformVersion: "15.0.0",
            uaFullVersion: "145.0.0.0", fullVersionList: [
              {brand:"Not:A-Brand",version:"8.0.0.0"},
              {brand:"Chromium",version:"145.0.0.0"},
              {brand:"Google Chrome",version:"145.0.0.0"}
            ]
          })
        })
      });
      Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    """)
    ctx.add_init_script(HOOK)

    pg = ctx.new_page()

    REQS = []
    def on_req(req):
        if "/api/v4/" in req.url:
            try:
                REQS.append({"url": req.url.split("shopee.co.id")[-1][:60],
                             "h": dict(req.headers),
                             "b": req.post_data})
            except Exception:
                pass

    def on_resp(resp):
        if "/api/v4/" in resp.url:
            try: t = resp.text()
            except Exception: return
            if "90309999" in t or resp.status == 200:
                for r in REQS[-1:]:
                    r["status"] = resp.status
                    r["err"] = "90309999" if "90309999" in t else "OK"

    pg.on("request", on_req)
    pg.on("response", on_resp)

    print("=== TEST: HEADLESS TANPA 'HeadlessChrome' ===")
    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(8000)
    print("  url:", pg.url[:80])

    pg.goto("https://shopee.co.id/cart", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(8000)
    print("  url cart:", pg.url[:90])

    env = pg.evaluate("""()=>({
      uaData: navigator.userAgentData ? {
        brands: navigator.userAgentData.brands,
        mobile: navigator.userAgentData.mobile,
        platform: navigator.userAgentData.platform
      } : null,
      webdriver: navigator.webdriver,
      hc: navigator.hardwareConcurrency,
      mem: navigator.deviceMemory,
      plugins: navigator.plugins.length,
      langs: navigator.languages
    })""")
    print("  env:", json.dumps(env, indent=1)[:450])

    print(f"\n  REQ tertangkap: {len(REQS)}")
    for r in REQS[-4:]:
        print(f"\n  {r['url']} [{r.get('status')}] {r.get('err')}")
        for k in ("sec-ch-ua", "x-sap-sec", "af-ac-enc-dat",
                  "af-ac-enc-sz-token", "x-sap-ri", "x-sz-sdk-version"):
            v = r["h"].get(k) or r["h"].get(k.title())
            if v:
                print(f"     {k}: {str(v)[:70]}")

    sigs = pg.evaluate("()=>window.__SIG||[]")
    print(f"\n  __SIG: {len(sigs)}")
    for s in sigs[:5]:
        print(f"     [{s['tag']}] {s['data'][:160]}")

    cks = {c["name"]: c["value"] for c in ctx.cookies()}
    open("/root/shopee-verify/dumps/ck_nohl.txt", "w").write(
        "; ".join(f"{k}={v}" for k, v in cks.items()))
    br.close()

print("\n=== cek via Python (cookie baru) ===")
import json as J
_CK = open("/root/shopee-verify/dumps/ck_nohl.txt").read().strip()
CSRF = next((c.split("=", 1)[1] for c in _CK.split(";")
             if c.strip().startswith("csrftoken=")), "")
ct = ssl.create_default_context(); ct.check_hostname = False
ct.verify_mode = ssl.CERT_NONE
op = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}),
    urllib.request.HTTPSHandler(context=ct))
h = {"User-Agent": UA, "Cookie": _CK, "Accept": "application/json",
     "x-api-source": "pc", "x-requested-with": "XMLHttpRequest",
     "Content-Type": "application/json", "x-csrftoken": CSRF,
     "Referer": "https://shopee.co.id/cart", "Origin": "https://shopee.co.id",
     "x-shopee-language": "id"}
r = urllib.request.Request("https://shopee.co.id/api/v4/cart/mini",
                           data=b'{"version_list":[3145728,65]}',
                           method="POST", headers=h)
try:
    with op.open(r, timeout=35) as x:
        j = J.loads(x.read())
    print("  cart/mini:", j.get("error"))
except urllib.error.HTTPError as e:
    print("  HTTP", e.code)
