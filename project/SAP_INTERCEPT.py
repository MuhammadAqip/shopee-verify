"""SAP_INTERCEPT.py — tangkap header SAP yang bikin halaman TIDAK redirect.

Teori: /user/account/phone render normal kalau request bawa x-sap-* header
yang valid. Kalau header tidak ada/salah -> redirect /verify/traffic/error.

Script ini:
  1. buka shopee.co.id
  2. inject hook SEBELUM navigasi: intercept semua request header
  3. navigate ke /user/account/phone
  4. bandingkan: request yang redirect vs yang sukses
  5. simpan semua header ke SAP_CAPTURE.json
"""
import json, sys, time, os

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_zax.txt"
PROXY = os.environ.get("SHOPEE_PROXY", "http://127.0.0.1:18080")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/SI.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright

REQS = []


def onreq(r):
    """Tangkap semua request ke shopee.co.id."""
    u = r.url
    if "shopee.co.id" not in u:
        return
    try:
        h = dict(r.headers)
    except Exception:
        h = {}
    sap = {k: v for k, v in h.items() if k.lower().startswith(("x-sap", "af-", "x-sz"))}
    entry = {
        "url": u[:150],
        "method": r.method,
        "sap_headers": sap,
        "all_header_keys": sorted(h.keys())[:30],
        "post_data": (r.post_data or "")[:800] if r.post_data else None,
        "resource_type": r.resource_type,
    }
    REQS.append(entry)
    if sap or "/api/v4/account" in u:
        log(f"  REQ {r.method} {u.split('shopee.co.id')[-1][:60]}")
        for k, v in sap.items():
            log(f"      {k}: {str(v)[:70]}")


def onresp(r):
    u = r.url
    if "shopee.co.id" not in u:
        return
    if r.status in (301, 302, 303, 307, 308):
        loc = ""
        try:
            loc = r.headers.get("location", "")
        except Exception:
            pass
        log(f"  REDIRECT {r.status} {u.split('shopee.co.id')[-1][:50]} -> {loc[:60]}")


with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,900",
        "--disable-blink-features=AutomationControlled", "--lang=id-ID"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 900},
                         timezone_id="Asia/Jakarta",
                         proxy={"server": PROXY} if PROXY else None)
    ctx.add_cookies(cookies)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};")
    pg = ctx.new_page()
    pg.on("request", onreq)
    pg.on("response", onresp)

    log("=== buka home (SDK bangun header SAP di sini) ===")
    try:
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    pg.wait_for_timeout(13000)

    # ambil SAP header yang SDK simpan di window
    sap_globals = pg.evaluate("""()=>{
      const out={};
      // cari object SAP di window
      for(const k of Object.keys(window)){
        if(/sap|security|antifraud/i.test(k) && k!=='renderCaptchaDesktop'
           && k!=='renderCaptchaPopupDesktop' && !k.startsWith('webpackChunk')){
          try{
            const v=window[k];
            out[k]=(typeof v==='object')?Object.keys(v).slice(0,15):typeof v;
          }catch(e){}
        }
      }
      return out;
    }""")
    log(f"  SAP globals: {sap_globals}")

    log("\n=== navigate /user/account/phone dengan hook active ===")
    try:
        pg.goto("https://shopee.co.id/user/account/phone",
                wait_until="domcontentloaded", timeout=55000)
    except Exception:
        pass
    pg.wait_for_timeout(12000)

    st = pg.evaluate("""()=>({url:location.href,
      n:[...document.querySelectorAll('canvas')].length,
      txt:(document.body.innerText||'').slice(0,200)})""")
    log(f"\n  final URL: {st['url'][:110]}")
    log(f"  canvas={st['n']} txt={st['txt'][:130].replace(chr(10),' | ')}")

    # analisa request yang punya SAP header
    with_sap = [r for r in REQS if r["sap_headers"]]
    log(f"\n  total req: {len(REQS)} | dengan SAP header: {len(with_sap)}")

    if with_sap:
        log("\n=== SAP HEADER LENGKAP (sample) ===")
        for r in with_sap[:5]:
            log(f"  {r['method']} {r['url'].split('shopee.co.id')[-1][:50]}")
            for k, v in r["sap_headers"].items():
                log(f"      {k} = {str(v)[:80]}")

    json.dump({"reqs": REQS, "sap_globals": sap_globals, "final": st},
              open("/root/shopee-verify/SAP_CAPTURE.json", "w"), indent=1)
    log("\n  → SAP_CAPTURE.json")

    pg.screenshot(path="/root/shopee-verify/SI.png", full_page=True)
    br.close()

log("\n=== SELESAI ===")
