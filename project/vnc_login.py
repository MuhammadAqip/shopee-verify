# -*- coding: utf-8 -*-
"""vnc_login.py — browser login, VNC persistent, tunggu Maker login manual.

Tidak ada timeout pendek. Browser tetap terbuka sampai Maker selesai login
atau script dihentikan manual.

Setelah login terdeteksi (SPC_ST muncul + bukan /buyer/login):
  - test cart/mini 90309999
  - simpan cookie ke ck_after_login.txt
  - JIKA BERSIH -> langsung jalankan IVS + precheck
"""
import sys, json, ssl, urllib.request, urllib.error, urllib.parse, os, time

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
STATE = "/root/shopee-verify/LOGIN_STATE.json"

json.dump({"stage": "starting"}, open(STATE, "w"))

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=False, args=[
        "--no-sandbox", "--disable-dev-shm-usage",
        "--window-size=1366,768", "--start-maximized"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 768},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    pg = ctx.new_page()

    GATE = []

    def on_resp(r):
        if "/api/v4" in r.url:
            try: t = r.text()
            except Exception: return
            if "90309999" in t:
                GATE.append((r.url.split("shopee.co.id")[-1][:45],
                             time.strftime("%H:%M:%S")))

    pg.on("response", on_resp)

    print("=== buka /buyer/login ===", flush=True)
    pg.goto("https://shopee.co.id/buyer/login", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(6000)
    print("url:", pg.url, flush=True)
    print(">>> SILAKAN LOGIN DI VNC <<<", flush=True)

    json.dump({"stage": "login_page", "vnc": "43.156.19.172:5900"},
              open(STATE, "w"))

    done = False
    for i in range(360):  # 360 * 5s = 30 menit
        pg.wait_for_timeout(5000)
        try:
            cur = pg.url
            cks = {c["name"]: c["value"] for c in ctx.cookies()}
        except Exception:
            print("browser closed", flush=True)
            break

        has_st = bool(cks.get("SPC_ST"))
        in_login = "/buyer/login" in cur or "/login" in cur

        if i % 6 == 0:
            print(f"[{i*5//60}m{ (i*5)%60:02d}s] {cur[:55]} "
                  f"ST={'Y' if has_st else 'N'} gate={len(GATE)}", flush=True)

        # login selesai = SPC_ST ada DAN tidak di halaman login
        if has_st and not in_login:
            print("\n>>> LOGIN TERDETEKSI <<<", flush=True)
            pg.wait_for_timeout(4000)
            cks = {c["name"]: c["value"] for c in ctx.cookies()}
            open("/root/shopee-verify/ck_after_login.txt", "w").write(
                "; ".join(f"{k}={v}" for k, v in cks.items()))

            # test gate
            print("=== tes cart/mini ===", flush=True)
            pg.goto("https://shopee.co.id/cart", wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(8000)
            print(f"  url: {pg.url[:90]}", flush=True)
            print(f"  90309999 events: {len(GATE)}", flush=True)
            clean = len(GATE) == 0
            print(f"  GATE CLEAN: {clean}", flush=True)

            json.dump({"stage": "logged_in", "gate_clean": clean,
                       "gate_events": len(GATE), "url": pg.url},
                      open(STATE, "w"))

            cks2 = {c["name"]: c["value"] for c in ctx.cookies()}
            open("/root/shopee-verify/ck_after_login.txt", "w").write(
                "; ".join(f"{k}={v}" for k, v in cks2.items()))
            print(f"  cookie: {len(cks2)} -> ck_after_login.txt", flush=True)

            pg.screenshot(path="/root/shopee-verify/after_login.png", full_page=True)
            done = True
            break

    if not done:
        print("timeout / closed tanpa login", flush=True)
        json.dump({"stage": "timeout"}, open(STATE, "w"))
    else:
        print("\nMENUNGGU 60s sebelum browser ditutup...", flush=True)
        pg.wait_for_timeout(60000)

    br.close()

print("=== selesai ===", flush=True)
