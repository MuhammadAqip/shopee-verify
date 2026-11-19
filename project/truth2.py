# -*- coding: utf-8 -*-
"""
truth2.py — probe endpoint SIGNUP/LOGIN: sumber kebenaran status nomor.

Ide: Shopee saat init signup/login dengan nomor HARUS tahu apakah nomor
sudah dipakai akun lain, dan apakah akun itu bisa "diambil alih" (unbindable).

Endpoint yang diuji:
  POST /api/v4/account/signup_by_otp
  POST /api/v4/account/login_by_otp
  POST /api/v4/account/basic/diff_auth_user
  GET  /api/v4/account/get_linked_accounts
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = Path("/root/shopee-verify")
HOME = "https://shopee.co.id/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

FETCH = r"""
async (a) => {
  const csrfM = document.cookie.match(/(^| )csrftoken=([^;]+)/);
  const csrf = csrfM ? csrfM[2] : '';
  const hex = Array.from(crypto.getRandomValues(new Uint8Array(8)))
                  .map(b => b.toString(16).padStart(2,'0')).join('');
  const h = {'Content-Type':'application/json','Accept':'application/json',
    'x-api-source':'pc','x-requested-with':'XMLHttpRequest',
    'x-shopee-language':'id','af-ac-enc-dat':hex};
  if (csrf) h['x-csrftoken'] = csrf;
  try {
    const r = await fetch(a.url, {method:a.method||'POST', headers:h,
      credentials:'include', body:a.body===null?undefined:JSON.stringify(a.body)});
    const t = await r.text();
    let j; try { j = JSON.parse(t); } catch(e) { j = {_raw:t.slice(0,260)}; }
    return {s:r.status, j};
  } catch(e) { return {s:0, j:{_exc:String(e)}}; }
}
"""


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
    phones = sys.argv[2:] or ["628999888777", "6281234567890"]
    jar = jar_from(ck)

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(user_agent=UA, locale="id-ID",
                            viewport={"width": 1366, "height": 900},
                            timezone_id="Asia/Jakarta")
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
        page.goto(HOME, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)
        print(f"[warm] {page.url[:60]}\n")

        def call(path, body=None, method="POST"):
            return page.evaluate(FETCH, {"url": path, "method": method, "body": body})

        for ph in phones:
            print("=" * 74)
            print(f"PHONE {ph}")
            print("=" * 74)

            cases = [
                ("signup_by_otp {phone}",
                 "/api/v4/account/signup_by_otp", {"phone": ph}),
                ("signup_by_otp {phone,password}",
                 "/api/v4/account/signup_by_otp", {"phone": ph, "password": "Test12345!"}),
                ("login_by_otp {phone}",
                 "/api/v4/account/login_by_otp", {"phone": ph}),
                ("diff_auth_user {}",
                 "/api/v4/account/basic/diff_auth_user", {}),
                ("get_linked_accounts",
                 "/api/v4/account/get_linked_accounts", None),
            ]
            for name, path, body in cases:
                m = "GET" if body is None else "POST"
                r = call(path, body, m)
                print(f"  [{r['s']}] {name}")
                print(f"       {json.dumps(r['j'], ensure_ascii=False)[:300]}")
            print()

        b.close()


if __name__ == "__main__":
    main()
