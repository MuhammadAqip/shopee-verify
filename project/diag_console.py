# -*- coding: utf-8 -*-
"""diag_console.py — tangkap console error + failed request saat /verify/traffic."""
import sys, json
from playwright.sync_api import sync_playwright

COOKIE = open("/root/shopee-verify/ck_clean.txt").read().strip()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
cookies = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
           for k, _, v in (p.strip().partition("=") for p in COOKIE.split(";"))
           if k and v]

logs, fails, reqs = [], [], []

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
    pg.on("console", lambda m: logs.append((m.type, m.text[:220])))
    pg.on("requestfailed", lambda r: fails.append(
        (r.url[:120], r.failure)))
    pg.on("response", lambda r: reqs.append(
        (r.status, r.url[:110])) if r.status >= 400 else None)

    pg.goto("https://shopee.co.id/verify/traffic",
            wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(14000)

    print("URL:", pg.url[:90])
    print("\n=== CONSOLE (error/warning) ===")
    for t, m in logs:
        if t in ("error", "warning"):
            print(f"  [{t}] {m}")
    print("\n=== REQUEST FAILED ===")
    for u, f in fails[:12]:
        print(f"  {u}  <- {f}")
    print("\n=== HTTP >=400 ===")
    for s, u in reqs[:12]:
        print(f"  {s} {u}")

    print("\n=== #main / root ===")
    d = pg.evaluate("""() => {
      const m = document.getElementById('main');
      const r = document.getElementById('root');
      return {
        main_exists: !!m, main_children: m ? m.children.length : 0,
        root_exists: !!r, root_children: r ? r.children.length : 0,
        body_text: document.body.innerText.slice(0,200),
        react: typeof window.__REACT_DEVTOOLS_GLOBAL_HOOK__,
        scripts: document.scripts.length,
      };
    }""")
    print(json.dumps(d, ensure_ascii=False, indent=1))
    pg.screenshot(path="/root/shopee-verify/gate2.png")
    br.close()
