# -*- coding: utf-8 -*-
"""relogin.py — login ULANG di browser fresh context.

Tujuan: dapat SPC_ST BARU tanpa flag crawler.
Login lewat UI asli (bukan API) supaya semua token di-generate normal.

Mode pakai:
  python3 relogin.py <phone_or_email> <password>
  atau tanpa argumen -> buka form login, Maker isi manual
"""
import sys, json, ssl, urllib.request, urllib.error, urllib.parse

IDENT = sys.argv[1] if len(sys.argv) > 1 else ""
PASSW = sys.argv[2] if len(sys.argv) > 2 else ""
WAIT_MANUAL = len(sys.argv) <= 2

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"

GATE = []
LOG = []

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=False, args=[
        "--no-sandbox", "--disable-dev-shm-usage",
        "--window-size=1366,768"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 768},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    pg = ctx.new_page()

    def on_resp(r):
        if "/api/v4" in r.url:
            try: t = r.text()
            except Exception: return
            LOG.append((r.url.split("shopee.co.id")[-1][:55], r.status, t[:200]))
            if "90309999" in t:
                GATE.append((r.url.split("shopee.co.id")[-1][:50], t[:180]))

    pg.on("response", on_resp)

    print("=== 1. buka halaman login (tanpa cookie apa pun) ===")
    pg.goto("https://shopee.co.id/buyer/login", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(8000)
    print("   url:", pg.url[:80])
    print("   body:", pg.evaluate("()=>document.body.innerText.slice(0,220)").replace("\n", " | ")[:200])

    cks = {c["name"]: c["value"] for c in ctx.cookies()}
    print("   cookie baru:", len(cks))
    print("   _sapid:", str(cks.get("_sapid"))[:45])
    print("   SPC_ST:", "ADA" if cks.get("SPC_ST") else "belum")

    if IDENT and PASSW:
        print("\n=== 2. isi form login otomatis ===")
        try:
            # input pertama = phone/email
            inputs = pg.locator("input")
            n = inputs.count()
            print(f"   input ditemukan: {n}")
            filled = False
            for i in range(n):
                el = inputs.nth(i)
                try:
                    t = el.get_attribute("type") or "text"
                    ph = (el.get_attribute("placeholder") or "").lower()
                    nm = (el.get_attribute("name") or "").lower()
                    if t in ("text", "tel", "email") and el.is_visible() and not filled:
                        el.click(force=True)
                        el.type(IDENT, delay=55)
                        print(f"   ident -> input#{i} (ph={ph[:25]})")
                        filled = True
                        break
                except Exception:
                    continue

            if filled:
                pg.wait_for_timeout(1200)
                # klik Lanjut / Next
                for txt in ("Lanjut", "Next", "Selanjutnya", "LOGIN", "Login"):
                    try:
                        loc = pg.get_by_text(txt, exact=True)
                        if loc.count() > 0:
                            loc.last.click(timeout=5000, force=True)
                            print(f"   klik '{txt}'")
                            break
                    except Exception:
                        continue
                pg.wait_for_timeout(6000)
                print("   url:", pg.url[:80])
                print("   body:", pg.evaluate("()=>document.body.innerText.slice(0,300)").replace("\n", " | ")[:270])

                # password
                try:
                    pwin = pg.locator('input[type="password"]').first
                    pwin.wait_for(state="visible", timeout=12000)
                    pwin.click(force=True)
                    pwin.type(PASSW, delay=55)
                    print("   password terisi")
                    pg.wait_for_timeout(1200)
                    for txt in ("LOGIN", "Login", "Masuk"):
                        try:
                            loc = pg.get_by_text(txt, exact=True)
                            if loc.count() > 0:
                                loc.last.click(timeout=6000, force=True)
                                print(f"   klik '{txt}'")
                                break
                        except Exception:
                            continue
                except Exception as e:
                    print("   password err:", str(e)[:70])
        except Exception as e:
            print("   form err:", str(e)[:90])
    else:
        print("\n=== 2. MODE MANUAL — lo isi sendiri ===")
        print("   Browser terbuka. Silakan:")
        print("   1. Isi nomor/email + password")
        print("   2. Selesaikan captcha kalau muncul")
        print("   3. Isi OTP kalau diminta")
        print(f"   Menunggu 240 detik...")

    # tunggu login selesai
    for i in range(48):
        pg.wait_for_timeout(5000)
        cur = pg.url
        cks = {c["name"]: c["value"] for c in ctx.cookies()}
        logged = bool(cks.get("SPC_ST")) and "login" not in cur
        if i % 4 == 0:
            print(f"   [{i*5:3d}s] url={cur[:55]} SPC_X=REDACTED'ADA' if cks.get('SPC_ST') else 'belum'} gate={len(GATE)}")
        if logged and "user" in cur:
            print(f"\n   ✅ LOGIN SUKSES pada {i*5}s")
            break

    print("\n=== 3. status akhir ===")
    print("   url:", pg.url[:90])
    cks = {c["name"]: c["value"] for c in ctx.cookies()}
    print("   cookie:", len(cks))
    for k in ("_sapid", "SPC_F", "SPC_ST", "SPC_SI"):
        print(f"      {k} = {str(cks.get(k))[:50]}")
    print("   90309999 terdeteksi:", len(GATE))

    # simpan
    open("/root/shopee-verify/ck_relogin.txt", "w").write(
        "; ".join(f"{k}={v}" for k, v in cks.items()))
    print("   -> ck_relogin.txt")

    pg.screenshot(path="/root/shopee-verify/relogin.png", full_page=True)
    print("\n=== request terakhir ===")
    for u, s, t in LOG[-8:]:
        print(f"   {u} -> {s}")
        if "90309999" in t:
            print(f"      ⚠️ {t[:110]}")

    br.close()
