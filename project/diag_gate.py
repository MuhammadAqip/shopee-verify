# -*- coding: utf-8 -*-
"""diag_gate.py — diagnosa APA yang sebenarnya render di /verify/traffic.
Screenshot + dump DOM + cek apakah canvas/img ada.
"""
import sys, json
from playwright.sync_api import sync_playwright

COOKIE = open("/root/shopee-verify/ck_clean.txt").read().strip()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
cookies = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
           for k, _, v in (p.strip().partition("=") for p in COOKIE.split(";"))
           if k and v]

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=False, args=[
        "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--use-gl=swiftshader", "--window-size=1366,768"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 768},
                         timezone_id="Asia/Jakarta",
                         proxy={"server": "http://127.0.0.1:18080"})
    ctx.add_cookies(cookies)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};")
    pg = ctx.new_page()

    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(9000)
    print("URL:", pg.url[:100])

    dom = pg.evaluate("""() => {
      const q = s => document.querySelectorAll(s).length;
      return {
        url: location.href,
        canvas_false: q('canvas[draggable=false]'),
        canvas_true: q('canvas[draggable=true]'),
        aside: q('aside'),
        imgs: q('img'),
        new_captcha: q('#NEW_CAPTCHA'),
        captchaMask: q('#captchaMask'),
        iframe: q('iframe'),
        iframe_srcs: Array.from(document.querySelectorAll('iframe')).map(f=>f.src).slice(0,5),
        body_len: document.body.innerText.length,
        body_head: document.body.innerText.slice(0,300),
      };
    }""")
    print(json.dumps(dom, ensure_ascii=False, indent=1))

    pg.screenshot(path="/root/shopee-verify/gate.png", full_page=False)
    print("\nscreenshot -> /root/shopee-verify/gate.png")

    # HTML mentah bagian captcha
    html = pg.content()
    open("/root/shopee-verify/gate.html", "w").write(html)
    for kw in ("NEW_CAPTCHA", "captchaMask", "draggable", "puzzle"):
        print(f"  '{kw}' di HTML: {html.count(kw)}x")

    br.close()
