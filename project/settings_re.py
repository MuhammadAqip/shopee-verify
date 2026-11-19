# -*- coding: utf-8 -*-
"""settings_re.py — capture bundle halaman /user/account/settings + ganti nomor.

Tujuan: temukan
  - get_password_verify_method
  - verify_payment_init / commit
  - change_phone_precheck_v2
dan lihat PARAMETER yang dikirim browser asli (termasuk ivs_signature).

Metode: buka settings di browser (pakai cookie hidup), klik alur ubah nomor,
capture SEMUA request ke endpoint tsb.
"""
import json, sys, re, time, os

CKFILE = sys.argv[1] if len(sys.argv) > 1 else "ck_1659.txt"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

ck = open(CKFILE).read().strip()
cookies = []
for p in ck.split(";"):
    if "=" in p:
        k, v = p.strip().split("=", 1)
        cookies.append({"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"})

OUT = "/root/shopee-verify/settings_capture.json"

from playwright.sync_api import sync_playwright

cap = []
scripts = []

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,1000",
        "--disable-blink-features=AutomationControlled"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 1000},
                         timezone_id="Asia/Jakarta")
    ctx.add_cookies(cookies)
    pg = ctx.new_page()

    def onreq(r):
        if "/api/v4/" in r.url:
            try:
                b = r.post_data
            except Exception:
                b = None
            if any(k in r.url for k in ("password", "verify_payment", "precheck",
                                        "change_phone", "otp", "ivs")):
                cap.append({"url": r.url.split("shopee.co.id")[-1][:110],
                            "method": r.method, "body": (b or "")[:1200]})

    def onresp(r):
        if "/api/v4/" in r.url:
            if any(k in r.url for k in ("password", "verify_payment", "precheck",
                                        "change_phone", "otp", "ivs")):
                try:
                    for it in cap:
                        if it["url"] == r.url.split("shopee.co.id")[-1][:110] and "resp" not in it:
                            it["resp"] = r.text()[:800]
                            it["status"] = r.status
                            break
                except Exception:
                    pass
            if r.url.endswith(".js"):
                scripts.append(r.url)

    pg.on("request", onreq)
    pg.on("response", onresp)

    print("=== buka /user/account/settings ===", flush=True)
    try:
        pg.goto("https://shopee.co.id/user/account/settings",
                wait_until="domcontentloaded", timeout=90000)
    except Exception as e:
        print("goto err:", str(e)[:70], flush=True)
    pg.wait_for_timeout(9000)

    print(f"url: {pg.url[:90]}", flush=True)
    body = pg.evaluate("()=>document.body.innerText.slice(0,600)").replace("\n", " | ")
    print(f"body: {body[:300]}", flush=True)

    # cari tombol ubah nomor
    clicked = False
    for t in ("Ubah", "Ganti", "Nomor HP", "Ubah Nomor", "Change", "Edit"):
        try:
            loc = pg.get_by_text(t)
            if loc.count() > 0:
                loc.first.click(timeout=4000, force=True)
                print(f"klik '{t}'", flush=True)
                clicked = True
                pg.wait_for_timeout(6000)
                break
        except Exception:
            pass

    if not clicked:
        print("tombol tidak ketemu — coba list link", flush=True)
        links = pg.evaluate("""()=>Array.from(document.querySelectorAll('a,button'))
            .map(e=>({t:(e.innerText||'').trim().slice(0,30),
                      h:e.getAttribute('href')||''}))
            .filter(x=>x.t).slice(0,40)""")
        for l in links:
            if l["t"]:
                print(f"  {l['t']}  -> {l['h'][:50]}", flush=True)

    pg.screenshot(path="/root/shopee-verify/settings_page.png", full_page=False)
    print("screenshot -> settings_page.png", flush=True)

    # simpan daftar script
    uniq = sorted(set(scripts))
    print(f"\n=== {len(uniq)} script ===", flush=True)
    for s in uniq[:20]:
        print("  ", s.split("/")[-1][:60], flush=True)

    json.dump({"captured": cap, "scripts": uniq, "url": pg.url},
              open(OUT, "w"), indent=1)
    print(f"\n-> {OUT} ({len(cap)} request)", flush=True)
    br.close()
