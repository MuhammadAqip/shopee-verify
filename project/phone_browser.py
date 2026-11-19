# -*- coding: utf-8 -*-
"""
phone_browser.py — jalankan endpoint change_phone DI DALAM konteks halaman Shopee.

Kenapa begini: endpoint account/management/* dijaga SFU (secure fetch utils).
Client `b.AV.post(...)` menyuntik header anti-fraud + SDK yang di-load dari
chunk 9211/7327. Tanpa itu semua jawab `error: 19 Failed to authenticate`
bahkan saat cookie hidup (cart/get membalas is_login:true).

Dengan page.evaluate + fetch, request mewarisi cookie DAN signing SDK milik
situs sendiri — strategi yang sama dengan `transacting-api-automation` Rule 1.

Mode:
  recon  -> hanya endpoint baca (precheck/phone_validation/get_linked_accounts)
  chain  -> jalankan alur ganti nomor sampai sebelum commit
"""
from __future__ import annotations

import argparse
import json
import sys

from playwright.sync_api import sync_playwright

WARMUP = "https://shopee.co.id/user/account/phone"
HOME = "https://shopee.co.id/"

FETCH_JS = r"""
async (a) => {
  let csrf = '';
  const m = document.cookie.match(/(^| )csrftoken=([^;]+)/);
  if (m) csrf = m[2];
  // af-ac-enc-dat: 16 hex byte, pola sama dengan bundel produksi
  const hex = Array.from(crypto.getRandomValues(new Uint8Array(8)))
                  .map(b => b.toString(16).padStart(2, '0')).join('');
  const headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'x-api-source': 'pc',
    'x-requested-with': 'XMLHttpRequest',
    'x-shopee-language': 'id',
    'af-ac-enc-dat': hex,
  };
  if (csrf) headers['x-csrftoken'] = csrf;
  try {
    const r = await fetch(a.url, {
      method: a.method || 'GET',
      headers,
      credentials: 'include',
      body: a.body ? JSON.stringify(a.body) : undefined,
    });
    const txt = await r.text();
    return { s: r.status, len: txt.length, b: txt.slice(0, 1200) };
  } catch (e) {
    return { s: 0, len: 0, b: 'EXC: ' + String(e) };
  }
}
"""


def cookies_to_list(cookie_str: str) -> list[dict]:
    out = []
    for seg in cookie_str.split(";"):
        seg = seg.strip()
        if not seg or "=" not in seg:
            continue
        k, v = seg.split("=", 1)
        out.append({
            "name": k.strip(),
            "value": v,
            "domain": ".shopee.co.id",
            "path": "/",
        })
    return out


def call(page, url: str, method: str = "GET", body: dict | None = None, label: str = "") -> dict:
    res = page.evaluate(FETCH_JS, {"url": url, "method": method, "body": body})
    tag = label or url.rsplit("/", 1)[-1]
    print(f"  [{tag}] HTTP {res['s']} len={res['len']}")
    txt = res["b"]
    try:
        parsed = json.loads(txt)
        print("        " + json.dumps(parsed, ensure_ascii=False)[:500])
        return {"http": res["s"], "json": parsed}
    except Exception:
        print("        " + txt[:300])
        return {"http": res["s"], "raw": txt}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cookie_file")
    ap.add_argument("--new-phone", default="6281234567890")
    ap.add_argument("--headless", action="store_true", default=True)
    ap.add_argument("--headed", dest="headless", action="store_false")
    args = ap.parse_args()

    with open(args.cookie_file) as f:
        cookie_str = f.read().strip()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=args.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
            locale="id-ID",
            viewport={"width": 1366, "height": 900},
        )
        ctx.add_cookies(cookies_to_list(cookie_str))
        page = ctx.new_page()

        print("[warm] " + HOME)
        page.goto(HOME, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)

        print("\n[1] get_account_info")
        call(page, "/api/v4/account/basic/get_account_info", label="account_info")

        print("\n[2] get_phone_validation_list")
        call(page, "/api/v4/account/basic/get_phone_validation_list", label="validation_list")

        print("\n[3] change_phone_init_v2")
        init = call(page, "/api/v4/account/management/change_phone_init_v2",
                    "POST", {}, "change_init_v2")
        token = None
        j = init.get("json") or {}
        data = j.get("data") if isinstance(j.get("data"), dict) else j
        token = (data or {}).get("change_phone_token") or (data or {}).get("token")
        if token:
            print(f"        change_phone_token = {token[:50]}")

        print("\n[4] check_phone_exist")
        call(page, "/api/v4/account/basic/check_phone_exist", "POST",
             {"phone": args.new_phone}, "check_exist")

        print("\n[5] change_phone_precheck_v2")
        call(page, "/api/v4/account/management/change_phone_precheck_v2", "POST",
             {"phone": args.new_phone}, "precheck_v2")

        print("\n[6] get_linked_accounts")
        call(page, "/api/v4/account/get_linked_accounts", label="linked")

        print("\n[7] get_password_verify_method (scenario=ChangePhone)")
        call(page, "/api/v4/account/management/get_password_verify_method?seq_no=0&scenario=1",
             label="verify_method")

        print("\n[8] otp/get_settings_v2 (nomor baru)")
        call(page, "/api/v4/otp/get_settings_v2", "POST",
             {"phone": args.new_phone, "operation": 0, "channel": 1}, "otp_settings")

        print("\n[done]")
        browser.close()


if __name__ == "__main__":
    main()
