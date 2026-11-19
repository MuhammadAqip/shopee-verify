"""sdk_ver.py — ambil versi SDK live terbaru + appkey aktif.

Buka homepage (yang render tanpa captcha), dump semua script URL
yang mengandung 'sfu' / 'sap', lalu download yang terbaru.
"""
import json, sys, time, re

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"

from playwright.sync_api import sync_playwright

scripts = []

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,900",
        "--disable-blink-features=AutomationControlled", "--lang=id-ID"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 900},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    pg = ctx.new_page()

    def onresp(r):
        u = r.url
        if any(k in u for k in ("sfu-", "sap.", "sap-", "sdkjs")) and u.endswith(".js"):
            scripts.append(u)

    pg.on("response", onresp)

    print("=== buka homepage ===", flush=True)
    try:
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=70000)
    except Exception as e:
        print("err:", str(e)[:60], flush=True)
    pg.wait_for_timeout(16000)

    # juga ambil dari performance entries
    perf = pg.evaluate("""()=>performance.getEntriesByType('resource')
      .map(e=>e.name).filter(n=>/\\.js(\\?|$)/.test(n))""")
    print(f"\n=== {len(perf)} script di performance ===", flush=True)
    sfu = [u for u in perf if any(k in u for k in ("sfu", "sap", "sdk"))]
    for u in sfu[:15]:
        print(" ", u.split("/")[-1], flush=True)

    # cek global SDK version
    ver = pg.evaluate("""()=>({
      sapVer: window.__SAP_VERSION__ || null,
      sdkVer: window.__SDK_VERSION__ || null,
      sfc: window.__SFUC || null,
      root: window.__ShopeeSSS_root ? Object.keys(window.__ShopeeSSS_root) : null
    })""")
    print(f"\n=== globals ===\n  {ver}", flush=True)

    all_sfu = list(set(scripts + sfu))
    print(f"\n=== {len(all_sfu)} SDK script ===", flush=True)
    for u in all_sfu:
        print(" ", u, flush=True)

    json.dump({"scripts": all_sfu, "ver": ver}, open("sdk_live.json", "w"), indent=1)
    br.close()
