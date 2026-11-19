# -*- coding: utf-8 -*-
"""
walk_phone_page.py — buka halaman ganti nomor dengan MITM aktif,
lalu klik seluruh alur supaya semua endpoint muncul.

Target halaman: https://shopee.co.id/user/account/phone
(kalau kena captcha, fallback: panggil endpoint langsung lewat page.evaluate)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = Path("/root/shopee-verify")
PROXY = "http://127.0.0.1:8080"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

PAGES = [
    "https://shopee.co.id/user/account/phone",
    "https://shopee.co.id/user/account/profile",
    "https://shopee.co.id/user/account/settings",
]


def jar_from(p):
    jar = {}
    for seg in open(p).read().replace("\n", " ").split(";"):
        seg = seg.strip()
        if seg and "=" in seg:
            k, v = seg.split("=", 1)
            jar[k.strip()] = v
    return jar


def main():
    ck = sys.argv[1] if len(sys.argv) > 1 else str(BASE / ".ck_new")
    jar = jar_from(ck)

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, proxy={"server": PROXY},
                               args=[
            "--no-sandbox", "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--ignore-certificate-errors"])
        ctx = b.new_context(user_agent=UA, locale="id-ID",
                            viewport={"width": 1366, "height": 900},
                            timezone_id="Asia/Jakarta",
                            ignore_https_errors=True)
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        page = ctx.new_page()
        try:
            ctx.add_cookies([{"name": k, "value": v, "domain": ".shopee.co.id",
                              "path": "/", "secure": True, "sameSite": "None"}
                             for k, v in jar.items()])
        except Exception:
            pass
        cdp = ctx.new_cdp_session(page)
        cdp.send("Network.enable")
        for k, v in jar.items():
            try:
                cdp.send("Network.setCookie", {"name": k, "value": v,
                                               "domain": ".shopee.co.id",
                                               "path": "/", "secure": True})
            except Exception:
                pass

        print("[warm] homepage")
        page.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(6000)
        print(f"  {page.url[:70]}")

        for url in PAGES:
            print(f"\n[goto] {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=90000)
            except Exception as e:
                print("  err:", e)
                continue
            page.wait_for_timeout(7000)
            print(f"  landed: {page.url[:75]}")

            # hapus modal
            try:
                page.evaluate("""() => {
                    document.querySelectorAll('[class*=modal],[role=dialog],[class*=overlay]')
                    .forEach(el => { const cs=getComputedStyle(el);
                      if(cs.position==='fixed'||cs.position==='absolute') el.remove(); });
                    document.body.style.overflow='auto';
                }""")
            except Exception:
                pass

            txt = ""
            try:
                txt = page.inner_text("body")
            except Exception:
                pass
            print(f"  text: {txt[:220].replace(chr(10),' | ')}")

            # klik semua tombol yang relevan
            for label in ("Ubah", "Ganti", "Verifikasi", "Lanjut", "Mulai",
                          "Kirim", "Konfirmasi", "Ya"):
                try:
                    els = page.query_selector_all(f"button:has-text('{label}')")
                    for el in els[:2]:
                        if el.is_visible():
                            print(f"  [click] {label}")
                            el.click(timeout=4000)
                            page.wait_for_timeout(4000)
                except Exception:
                    pass

            page.screenshot(path=str(BASE / f"walk_{url.split('/')[-1]}.png"),
                            full_page=True)

        # dump link yang mengandung 'phone'
        try:
            hrefs = page.eval_on_selector_all("a[href]",
                                              "els => els.map(e => e.href)")
            uniq = sorted({h for h in hrefs if "phone" in h.lower()
                           or "email" in h.lower()})
            print("\n[links phone/email]")
            for h in uniq[:20]:
                print("  ", h[:110])
        except Exception:
            pass

        page.wait_for_timeout(4000)
        b.close()
    print("\n[done] cek /root/shopee-verify/mitm_phone.jsonl")


if __name__ == "__main__":
    main()
