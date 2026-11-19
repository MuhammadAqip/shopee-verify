# -*- coding: utf-8 -*-
"""cp_spa.py — jalankan flow change_phone dari DALAM browser (SPA /verify/ivs).

Kenapa: API murni kena 10002 di semua step. Browser asli menjalankan IVS
dengan state machine + SDK. Kita buka halaman change phone di browser
ber-cookie, lalu ikuti UI-nya otomatis dan tangkap request final
(commit / precheck) beserta param aslinya.
"""
import json, sys, time, os

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1553.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283191104601"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
OUT = "/root/shopee-verify/spa_capture.json"

ck = open(CK).read().strip()
cookies = []
for p in ck.split(";"):
    if "=" in p:
        k, v = p.strip().split("=", 1)
        cookies.append({"name": k, "value": v,
                        "domain": ".shopee.co.id", "path": "/"})

from playwright.sync_api import sync_playwright

cap = []

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,1000",
        "--disable-blink-features=AutomationControlled"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 1000},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    ctx.add_cookies(cookies)
    pg = ctx.new_page()

    def onreq(r):
        if "/api/v4/" in r.url and any(k in r.url for k in
                                       ("password", "verify", "precheck",
                                        "change_phone", "otp", "ivs")):
            cap.append({"t": time.strftime("%H:%M:%S"), "m": r.method,
                        "u": r.url.split("shopee.co.id")[-1][:100],
                        "b": (r.post_data or "")[:900]})

    def onresp(r):
        if "/api/v4/" in r.url and any(k in r.url for k in
                                       ("password", "verify", "precheck",
                                        "change_phone", "otp", "ivs")):
            try:
                cap.append({"t": time.strftime("%H:%M:%S"), "RESP": True,
                            "u": r.url.split("shopee.co.id")[-1][:100],
                            "s": r.status, "b": r.text()[:600]})
            except Exception:
                pass

    pg.on("request", onreq)
    pg.on("response", onresp)

    print("=== buka settings lewat proxy (IP residensial) ===", flush=True)
    for attempt in range(3):
        try:
            pg.goto("https://shopee.co.id/user/account/settings",
                    wait_until="domcontentloaded", timeout=90000)
            break
        except Exception as e:
            print(f"  try{attempt}: {str(e)[:50]}", flush=True)
            time.sleep(4)
    pg.wait_for_timeout(8000)
    print(f"url: {pg.url[:85]}", flush=True)
    txt = pg.evaluate("()=>document.body.innerText.slice(0,400)").replace("\n", "|")
    print(f"body: {txt[:250]}", flush=True)

    pg.screenshot(path="/root/shopee-verify/spa_settings.png", full_page=False)

    # cari & klik elemen nomor HP / ubah
    clicked = False
    for sel in ('text=Nomor HP', 'text=Nomor Telepon', 'text=Ubah',
                'text=Ubah Nomor', 'text=Change', 'text=Edit'):
        try:
            loc = pg.locator(sel)
            if loc.count() > 0:
                loc.first.click(timeout=4000, force=True)
                print(f"klik '{sel}'", flush=True)
                clicked = True
                pg.wait_for_timeout(6000)
                break
        except Exception:
            pass

    if not clicked:
        # dump link/button untuk analisa
        els = pg.evaluate("""()=>Array.from(document.querySelectorAll('a,button,div[role=button]'))
            .map(e=>({t:(e.innerText||'').trim().slice(0,40),
                      h:e.getAttribute('href')||''}))
            .filter(x=>x.t).slice(0,50)""")
        print("\n=== elemen ===", flush=True)
        for e in els:
            print(f"  {e['t']!r} -> {e['h'][:45]}", flush=True)

    pg.screenshot(path="/root/shopee-verify/spa_after_click.png", full_page=False)
    print("url akhir:", pg.url[:85], flush=True)

    json.dump(cap, open(OUT, "w"), indent=1, ensure_ascii=False)
    print(f"\n-> {OUT} ({len(cap)} event)", flush=True)

    # ringkas
    print("\n=== request tertangkap ===", flush=True)
    for c in cap:
        if c.get("RESP"):
            print(f"  ← {c['s']} {c['u']}", flush=True)
        else:
            print(f"  → {c['m']} {c['u']}", flush=True)

    br.close()
