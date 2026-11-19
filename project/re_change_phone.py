# -*- coding: utf-8 -*-
"""re_change_phone.py — RE flow ganti nomor Shopee lewat cookie.

Masuk lewat API langsung (halaman /user/account/profile kena captcha,
tapi endpoint API-nya tetap bisa dipanggil dengan cookie + csrftoken).

Alur yang ingin dipetakan:
  1. init  -> dapat change_phone_token
  2. verifikasi identitas (password / OTP / PIN shopeepay)
  3. kirim OTP ke nomor BARU (pilih channel: SMS / WhatsApp)
  4. verify OTP -> commit ganti nomor
"""
from __future__ import annotations

import json
import sys
from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

POST_JS = r"""
async (a) => {
  const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  const csrf = m ? m[1] : '';
  const hex = Array.from(crypto.getRandomValues(new Uint8Array(8)))
                  .map(b => b.toString(16).padStart(2,'0')).join('');
  const h = {'Content-Type':'application/json','Accept':'application/json',
    'x-api-source':'pc','x-requested-with':'XMLHttpRequest',
    'x-shopee-language':'id','af-ac-enc-dat':hex};
  if (csrf) h['x-csrftoken'] = csrf;
  const r = await fetch(a.url, {method: a.method || 'POST', headers: h,
    credentials: 'include',
    body: a.body === null ? undefined : JSON.stringify(a.body)});
  const t = await r.text();
  let j; try { j = JSON.parse(t); } catch(e) { j = {_raw: t.slice(0,400)}; }
  return {status: r.status, body: j};
}
"""


def parse_cookie(raw: str) -> list[dict]:
    out = []
    for part in raw.replace("\n", ";").split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            out.append({"name": k.strip(), "value": v.strip(),
                        "domain": ".shopee.co.id", "path": "/"})
    return out


def run(raw_cookie: str, actions: list[tuple]):
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled"])
        ctx = br.new_context(user_agent=UA, locale="id-ID",
                             viewport={"width": 1366, "height": 900},
                             timezone_id="Asia/Jakarta",
                             proxy={"server": "http://127.0.0.1:18080"})
        ctx.add_cookies(parse_cookie(raw_cookie))
        ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        pg = ctx.new_page()
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded",
                timeout=90000)
        pg.wait_for_timeout(5000)

        for name, path, body, method in actions:
            try:
                r = pg.evaluate(POST_JS, {"url": "https://shopee.co.id" + path,
                                          "body": body, "method": method})
                print(f"\n[{name}] {method} {path}")
                print("  status:", r["status"])
                print("  body  :", json.dumps(r["body"], ensure_ascii=False)[:600])
            except Exception as e:
                print(f"\n[{name}] EXC: {e}")
        br.close()


if __name__ == "__main__":
    ck = open("/root/shopee-verify/ck_test.txt").read().strip()
    # tahap 1: init flow ganti nomor
    import json as _j
    tok = None
    # pakai token yang sudah didapat sebelumnya
    run(ck, [
        ("verify_methods", "/api/v4/account/management/get_password_verify_method", {}, "POST"),
        ("precheck", "/api/v4/account/management/change_phone_precheck_v2", {"change_phone_token": "TOKEN"}, "POST"),
    ])
