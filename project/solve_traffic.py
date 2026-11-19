# -*- coding: utf-8 -*-
"""solve_traffic.py — buka /verify/traffic dengan cookie, solve captcha
pakai shopee_v6 (solver terbukti), lalu ambil ivs_signature.

Runner: xvfb-run (headed), proxy residensial ID, stealth.
"""
import sys, os, json, time
sys.path.insert(0, "/root/shopee-farm")
sys.path.insert(0, "/root/shopee-verify")
from playwright.sync_api import sync_playwright
import shopee_v6 as V6

COOKIE_FILE = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_1553.txt"
CSRF = sys.argv[2] if len(sys.argv) > 2 else "3929567fdad6e3608eb25fd137f69955"
PHONE = "6285736070693"
KEY = open("/root/shopee-farm/bot_key.txt").read().strip()

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
COOKIE = open(COOKIE_FILE).read().strip()

cookies = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
           for k, _, v in (p.strip().partition("=") for p in COOKIE.split(";"))
           if k and v]
if not any(c["name"] == "csrftoken" for c in cookies):
    cookies.append({"name": "csrftoken", "value": CSRF,
                    "domain": ".shopee.co.id", "path": "/"})
cookies.append({"name": "shopee_webLanguage", "value": "id",
                "domain": ".shopee.co.id", "path": "/"})


def dismiss_lang(pg):
    for _ in range(4):
        try:
            el = pg.locator("text=Bahasa Indonesia").first
            if el.is_visible(timeout=1200):
                el.click()
                pg.wait_for_timeout(1500)
        except Exception:
            pass


def cdp(pg):
    return pg.context.new_cdp_session(pg)


with sync_playwright() as pw:
    br = pw.chromium.launch(
        headless=False,
        args=["--no-sandbox", "--disable-dev-shm-usage",
              "--disable-blink-features=AutomationControlled",
              "--use-gl=swiftshader", "--window-size=1366,768"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 768},
                         timezone_id="Asia/Jakarta",
                         proxy={"server": "http://127.0.0.1:18080"})
    ctx.add_cookies(cookies)
    ctx.add_init_script("""
      Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
      Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
      Object.defineProperty(navigator,'languages',{get:()=>['id-ID','id','en-US','en']});
      window.chrome={runtime:{}};
    """)
    pg = ctx.new_page()
    dismiss_lang(pg)

    print(">> goto homepage")
    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(8000)
    dismiss_lang(pg)
    print("   URL:", pg.url[:85])

    if "/verify/traffic" in pg.url or "/verify/captcha" in pg.url:
        print("\n>> captcha gate terdeteksi. solve...")
        solvers = [("image_crawl", V6.solve_image_crawl),
                   ("image_drag", V6.solve_image_drag),
                   ("puzzle", V6.solve_puzzle_slide)]
        solved = False
        for attempt in range(4):
            for name, fn in solvers:
                try:
                    ok = fn(pg, KEY)
                except Exception as e:
                    print(f"   {name}: err {str(e)[:70]}")
                    continue
                print(f"   attempt{attempt+1} {name} -> {ok}")
                if ok:
                    solved = True
                    break
            pg.wait_for_timeout(3500)
            if "/verify/" not in pg.url:
                print("   ✅ lolos gate:", pg.url[:80])
                break
            if solved:
                break
            try:
                pg.reload(wait_until="domcontentloaded", timeout=60000)
                pg.wait_for_timeout(4000)
                dismiss_lang(pg)
            except Exception:
                pass

    print("\n>> final URL:", pg.url[:90])
    me = pg.evaluate("""async()=>{const r=await fetch('/api/v4/account/basic/get_account_info',
      {credentials:'include',headers:{'x-api-source':'pc','x-requested-with':'XMLHttpRequest'}});
      return await r.text();}""")
    print("   account:", me[:130])

    print("\n>> simpan cookie hasil (untuk dipakai Python)")
    ck = ctx.cookies()
    jar = "; ".join(f"{c['name']}={c['value']}" for c in ck
                    if "shopee" in c["domain"])
    open("/root/shopee-verify/ck_solved.txt", "w").write(jar)
    print("   tersimpan ck_solved.txt", len(jar), "B, nama cookie:",
          len([c for c in ck if "shopee" in c["domain"]]))

    br.close()
