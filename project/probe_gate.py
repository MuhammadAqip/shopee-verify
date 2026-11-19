# -*- coding: utf-8 -*-
"""probe_gate.py — NAPAK TILAS: apakah gerbang /verify/traffic nempel di
IP VPS ini (bukan di cookie)?

Tes A: buka shopee.co.id TANPA cookie sama sekali dari IP VPS.
Tes B: buka shopee.co.id TANPA cookie dari proxy residensial.
Hasil: kalau A gagal & B lolos -> flag di IP, bukan cookie.
"""
import sys, json
from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")


def probe(label, proxy):
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=False, args=[
            "--no-sandbox", "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--use-gl=swiftshader", "--window-size=1366,768"])
        ctx = br.new_context(user_agent=UA, locale="id-ID",
                             viewport={"width": 1366, "height": 768},
                             timezone_id="Asia/Jakarta",
                             proxy=proxy)
        ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
            "window.chrome={runtime:{}};")
        pg = ctx.new_page()
        try:
            pg.goto("https://shopee.co.id/", wait_until="domcontentloaded",
                    timeout=75000)
        except Exception as e:
            print(f"[{label}] goto err: {str(e)[:80]}")
        pg.wait_for_timeout(9000)
        d = pg.evaluate("""() => ({
          url: location.href.slice(0,110),
          title: document.title,
          canvas: document.querySelectorAll('canvas').length,
          new_captcha: document.querySelectorAll('#NEW_CAPTCHA').length,
          text: document.body.innerText.slice(0,150),
        })""")
        print(f"\n[{label}]")
        print(json.dumps(d, ensure_ascii=False, indent=1))
        pg.screenshot(path=f"/root/shopee-verify/gate_{label}.png")
        br.close()
        return d


a = probe("direct", None)
b = probe("proxy", {"server": "http://127.0.0.1:18080"})

print("\n=== KESIMPULAN ===")
ta, tb = "/verify/traffic" in a["url"], "/verify/traffic" in b["url"]
print(f"direct -> gate: {ta}")
print(f"proxy  -> gate: {tb}")
if ta and not tb:
    print(">> FLAG DI IP VPS. Proxy menyelesaikan.")
elif ta and tb:
    print(">> Keduanya kena. Bukan cuma IP — fingerprint/headless juga.")
else:
    print(">> Bersih.")
