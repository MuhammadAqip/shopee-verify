# -*- coding: utf-8 -*-
"""sap_cdp.py — capture header x-sap via CDP Network domain.

CDP melihat header FINAL yang benar-benar terkirim di level network,
jadi tidak bisa dilewati interceptor JS apa pun.
"""
import json, time

from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
OUT = "/root/shopee-verify/x-sap-headers.json"

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--window-size=1366,900"])
    ctx = br.new_context(user_agent=UA, locale="id-ID", viewport={"width":1366,"height":900},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    pg = ctx.new_page()

    cdp = ctx.new_cdp_session(pg)
    cdp.send("Network.enable")

    CAPS = []

    def on_req(p):
        try:
            url = p["request"]["url"]
            if "/api/v4/" not in url:
                return
            hs = p["request"].get("headers", {})
            sap = {k: v for k, v in hs.items()
                   if k.lower().startswith("x-sap")
                   or k.lower().startswith("af-ac")
                   or k.lower() == "x-sz-sdk-version"}
            if sap:
                CAPS.append({
                    "method": p["request"]["method"],
                    "url": url.split("shopee.co.id")[-1][:100],
                    "headers": sap,
                    "postData": (p["request"].get("postData") or "")[:150],
                })
        except Exception:
            pass

    cdp.on("Network.requestWillBeSent", on_req)

    print("=== buka shopee ===", flush=True)
    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(12000)

    print("=== trigger ===", flush=True)
    pg.mouse.wheel(0, 900)
    pg.wait_for_timeout(4000)
    pg.mouse.wheel(0, -400)
    pg.wait_for_timeout(2000)

    print(f"\n=== {len(CAPS)} request API ber-SAP ===", flush=True)

    seen = set()
    uniq = []
    for c in CAPS:
        ri = c["headers"].get("x-sap-ri", "")
        if ri[:16] in seen:
            continue
        seen.add(ri[:16])
        uniq.append(c)

    for i, c in enumerate(uniq[:8], 1):
        print(f"\n--- [{i}] {c['method']} {c['url'][:65]} ---", flush=True)
        for k, v in c["headers"].items():
            print(f"   {k}: {v[:75]}{'...' if len(v) > 75 else ''}", flush=True)

    json.dump(uniq, open(OUT, "w"), indent=1)
    print(f"\n  -> {OUT} ({len(uniq)} unik, {len(CAPS)} total)", flush=True)

    # analisis RI
    print("\n=== ANALISIS x-sap-ri ===", flush=True)
    for i, c in enumerate(uniq[:8], 1):
        ri = c["headers"].get("x-sap-ri", "")
        sec = c["headers"].get("x-sap-sec", "")
        if len(ri) < 28:
            continue
        p1, p2, p3, p4 = ri[0:8], ri[8:20], ri[20:28], ri[28:]
        try:
            tv = int(p3, 16)
        except Exception:
            tv = 0
        print(f"  {i}. ri[0:8]={p1} ri[8:20]={p2} ri[20:28]={p3}({tv}) tail={len(p4)}hex sec={len(sec)}B")

    # tes generate untuk request BARU
    print("\n=== TES: header untuk request BARU (cart/mini) ===", flush=True)
    before = len(CAPS)
    r = pg.evaluate("""async ()=>{
      const res = await fetch('/api/v4/cart/mini', {
        method:'POST', credentials:'include',
        headers:{'Accept':'application/json','X-Requested-With':'XMLHttpRequest',
                 'X-API-SOURCE':'pc','X-Shopee-Language':'id','Content-Type':'application/json'},
        body: JSON.stringify({version_list:[3145728,65]})
      });
      let j=null; try{j=await res.json();}catch(e){}
      return {s:res.status, e:j && j.error};
    }""")
    print("  response:", json.dumps(r), flush=True)
    pg.wait_for_timeout(2500)

    if len(CAPS) > before:
        newh = CAPS[-1]["headers"]
        print("\n  header yang SDK generate untuk cart/mini:", flush=True)
        for k, v in newh.items():
            print(f"    {k}: {v[:75]}{'...' if len(v) > 75 else ''}", flush=True)
        json.dump({"cart_mini_headers": newh, "response": r},
                  open("/root/shopee-verify/x-sap-cart.json", "w"), indent=1)
        print("\n  -> x-sap-cart.json", flush=True)

    br.close()

print("\n=== SELESAI ===", flush=True)
