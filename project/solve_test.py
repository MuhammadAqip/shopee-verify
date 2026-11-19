# -*- coding: utf-8 -*-
"""solve_test.py — tes solver v6 (TERBUKTI) di halaman profil Shopee, TANPA PROXY."""
import sys, time, re
sys.path.insert(0, "/root/shopee-farm")
sys.path.insert(0, "/root/shopee-verify")
from change_phone_engine import parse_cookie
from playwright.sync_api import sync_playwright
import shopee_v6 as V6

KEY = sys.argv[1] if len(sys.argv) > 1 else "6a65a6faee08ae961f05b57bd5789959"
CK = open("/root/shopee-verify/ck_test.txt").read().strip()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

def detect(p):
    for t, sels in (("image_crawl", [V6.IC_PIECE]),
                    ("puzzle", [V6.PZ_PIECE]),
                    ("image_drag", [V6.ID_VERIFY])):
        if p.evaluate(V6.JS_PRESENT, sels):
            return t
    return None

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1420, "height": 900},
                         timezone_id="Asia/Jakarta")
    ctx.add_cookies(parse_cookie(CK))
    ctx.add_cookies([{"name": "shopee_webLanguage", "value": "id",
                      "domain": ".shopee.co.id", "path": "/"}])
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
    p = ctx.new_page()
    p.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    p.wait_for_timeout(6000)
    p.goto("https://shopee.co.id/user/account/profile",
           wait_until="domcontentloaded", timeout=90000)
    p.wait_for_timeout(9000)
    print("URL :", p.url[:70])
    print("STATE:", p.evaluate(V6.JS_STATE))
    t = detect(p)
    print("TIPE :", t)
    if t == "image_crawl":
        r = V6.solve_image_crawl(p, KEY)
        print("SOLVE:", r)
    elif t == "puzzle":
        print("SOLVE:", V6.solve_puzzle_slide(p, KEY))
    elif t == "image_drag":
        print("SOLVE:", V6.solve_image_drag(p, KEY))
    p.wait_for_timeout(3500)
    print("URL2 :", p.url[:70])
    print("STATE2:", p.evaluate(V6.JS_STATE))
    import json, urllib.request
    print("kredit:", json.loads(urllib.request.urlopen(
        f"https://www.sadcaptcha.com/api/v1/license/credits?licenseKey={KEY}",
        timeout=20).read())["credits"])
    br.close()
