# -*- coding: utf-8 -*-
"""
inject_login.py — suntik cookie ala TuyulHelper lalu buka halaman profil.

Teknik (dari background.js tuyul, diringkas ke Python):
  1. chrome.cookies.set  -> Playwright add_cookies (domain .shopee.co.id, path /)
  2. fallback CDP Network.setCookie untuk cookie yang ditolak normalisasi
  3. Navigate ke /user/account/profile, tangkap semua XHR/Fetch
  4. Simpan HAR-lite: url, method, req body, resp body
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PROFILE_URL = "https://shopee.co.id/user/account/profile"
HOME = "https://shopee.co.id/"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

INTEREST = (
    "account", "profile", "email", "phone", "otp", "vcode", "verify",
    "verification", "ivs", "user/", "sms", "security",
)


def parse_cookie(raw: str) -> dict[str, str]:
    out = {}
    for seg in raw.replace("\n", " ").split(";"):
        seg = seg.strip()
        if not seg or "=" not in seg:
            continue
        k, v = seg.split("=", 1)
        out[k.strip()] = v
    return out


def main() -> None:
    print("[*] step 1: parse cookie")
    ck = open(sys.argv[1]).read().strip()
    jar = parse_cookie(ck)
    print(f"    {len(jar)} cookie: {sorted(jar)}")
    uid = jar.get("SPC_U", "?")
    print(f"    SPC_U = {uid}")

    out_path = Path("/root/shopee-verify/profile_capture.jsonl")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fh = out_path.open("w")

    captured = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        ctx = browser.new_context(
            user_agent=UA,
            locale="id-ID",
            viewport={"width": 1366, "height": 900},
            timezone_id="Asia/Jakarta",
        )

        # --- injeksi 1: Playwright native ---
        cookie_objs = [
            {
                "name": k,
                "value": v,
                "domain": ".shopee.co.id",
                "path": "/",
                "secure": True,
                "sameSite": "None",
            }
            for k, v in jar.items()
        ]
        try:
            ctx.add_cookies(cookie_objs)
            print(f"[*] step 2: add_cookies OK ({len(cookie_objs)} pair)")
        except Exception as e:
            print(f"[!] add_cookies gagal: {e}")

        page = ctx.new_page()

        # --- injeksi 2: CDP (fallback, ala declarativeNetRequest) ---
        cdp = ctx.new_cdp_session(page)
        cdp.send("Network.enable")
        ok = 0
        for k, v in jar.items():
            try:
                cdp.send("Network.setCookie", {
                    "name": k, "value": v,
                    "domain": ".shopee.co.id", "path": "/",
                    "secure": True, "httpOnly": False,
                    "sameSite": "None",
                })
                ok += 1
            except Exception:
                pass
        print(f"[*] step 3: CDP setCookie {ok}/{len(jar)}")

        got = {c["name"] for c in ctx.cookies()}
        print(f"[*] step 4: cookie terpasang = {len(got)} | SPC_ST = {'SPC_ST' in got}")

        # --- capture traffic ---
        def on_response(resp):
            nonlocal captured
            url = resp.url
            if "shopee.co.id/api/" not in url and "/api/v4/" not in url:
                return
            if not any(k in url.lower() for k in INTEREST):
                return
            try:
                body = resp.text()[:6000]
            except Exception:
                body = ""
            req = resp.request
            try:
                pd = req.post_data
            except Exception:
                pd = None
            rec = {
                "ts": time.time(),
                "status": resp.status,
                "method": req.method,
                "url": url,
                "req_body": pd[:2000] if pd else None,
                "resp_body": body,
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            captured += 1
            print(f"  [{resp.status}] {req.method} {url[-95:]}")
            if pd:
                print(f"         REQ  {pd[:160]}")
            print(f"         RESP {body[:200]}")

        page.on("response", on_response)

        print(f"\n[*] step 5: warm {HOME}")
        page.goto(HOME, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)
        print(f"    landed: {page.url[:110]}")

        if "login" in page.url.lower():
            print("[!] DIREJECT: redirected ke login — cookie invalid/expired")
            print("[!] cek SPC_ST ikut terhapus server?")
            got2 = {c["name"] for c in ctx.cookies()}
            print(f"    SPC_ST after load = {'SPC_ST' in got2}")
            browser.close()
            fh.close()
            return

        print(f"\n[*] step 6: {PROFILE_URL}")
        page.goto(PROFILE_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(7000)
        print(f"    landed: {page.url[:110]}")

        print(f"\n[*] step 7: judul halaman -> {page.title()[:80]}")
        txt = page.inner_text("body")[:1500]
        print("[*] teks halaman (1400 char pertama):")
        print(txt)

        # cari tombol/link terkait email & phone
        print("\n[*] step 8: elemen email/phone di halaman")
        for sel in ["a", "button", "div[role=button]"]:
            try:
                els = page.query_selector_all(sel)
                for el in els:
                    try:
                        t = (el.inner_text() or "").strip()
                    except Exception:
                        continue
                    if not t or len(t) > 60:
                        continue
                    low = t.lower()
                    if any(k in low for k in ("email", "nomor", "phone", "ganti", "ubah", "verifikasi", "verif", "hp")):
                        print(f"    <{sel}> {t!r}")
            except Exception as e:
                print(f"    {sel}: {e}")

        page.screenshot(path="/root/shopee-verify/profile.png", full_page=True)
        print("\n[*] screenshot -> /root/shopee-verify/profile.png")

        browser.close()

    fh.close()
    print(f"\n[+] capture {captured} request -> {out_path}")


if __name__ == "__main__":
    main()
