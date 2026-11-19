# -*- coding: utf-8 -*-
"""browser_ck.py — buka shopee pakai cookie, cek apakah sesi hidup di browser
(lalu ambil cookie hasil browser yang mungkin lebih lengkap).
"""
import sys, json
from playwright.sync_api import sync_playwright

CK_FILE = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_email.txt"
CK = open(CK_FILE).read().strip()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"

cookies = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
           for k, _, v in (p.strip().partition("=") for p in CK.split(";"))
           if k and v]
print(f"inject {len(cookies)} cookie")

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=False, args=[
        "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--use-gl=swiftshader", "--window-size=1366,768"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 768},
                         timezone_id="Asia/Jakarta",
                         proxy={"server": PROXY})
    ctx.add_cookies(cookies)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};")
    pg = ctx.new_page()

    # cek API dari konteks halaman
    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(8000)
    print("URL:", pg.url[:80])

    r = pg.evaluate("""async () => {
      const r = await fetch('/api/v4/account/basic/get_account_info',
        {credentials:'include', headers:{'x-api-source':'pc',
         'x-requested-with':'XMLHttpRequest'}});
      const t = await r.text();
      try { return JSON.parse(t); } catch(e){ return {raw:t.slice(0,200)}; }
    }""")
    print("account:", json.dumps(r, ensure_ascii=False)[:350])

    # login? cek teks header
    txt = pg.evaluate("()=>document.body.innerText.slice(0,200)")
    print("body:", txt.replace("\n", " | ")[:180])
    print("login link ada:", "Log In" in txt)

    if r.get("error") == 0:
        ck2 = ctx.cookies()
        s = "; ".join(f"{c['name']}={c['value']}" for c in ck2)
        open("/root/shopee-verify/ck_email_browser.txt", "w").write(s)
        print(f"\n>> HIDUP. {len(ck2)} cookie disimpan ck_email_browser.txt")
        print("   names:", [c["name"] for c in ck2])
    else:
        print("\n>> MATI di browser juga")
    pg.screenshot(path="/root/shopee-verify/email_gate.png")
    br.close()
