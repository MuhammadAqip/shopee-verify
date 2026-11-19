# -*- coding: utf-8 -*-
"""
unbind_probe.py — cari endpoint SUMBER KEBENARAN untuk "bisa unbind atau tidak".

Hipotesis: get_unbind_phone_check_result BUKAN patokan.
Flow asli dari bundle SignupByOTP:
    1. POST /api/v4/account/management/check_unbind_phone      {phone}
    2. POST /api/v4/account/management/check_unbind_phone_by_vcode
           {phone, vcode_token, operation}
    3. POST /api/v4/account/management/unbind_phone_by_vcode   (aksi)
    4. POST /api/v4/account/management/get_unbind_phone_check_result  (polling)

operation enum dari bundle: P.jU.General -> cari nilainya.

Script ini probe SEMUA endpoint phone-related dengan berbagai body shape,
dan cetak response mentah supaya bisa dibandingkan.
"""
from __future__ import annotations

import json
import sys
import time
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
    return {s:r.status, n:t.length, b:t};
  } catch(e) { return {s:0,n:0,b:'EXC '+String(e)}; }
}
"""


def jar_from(path):
    jar = {}
    for seg in open(path).read().replace("\n", " ").split(";"):
        seg = seg.strip()
        if seg and "=" in seg:
            k, v = seg.split("=", 1)
            jar[k.strip()] = v
    return jar


def pj(r):
    try:
        return json.loads(r["b"])
    except Exception:
        return {"_raw": r["b"][:300]}


def main():
    ck = sys.argv[1] if len(sys.argv) > 1 else str(BASE / ".ck_new")
    phones = sys.argv[2:] or ["628999888777", "6281234567890", "6281230258217"]
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
        print(f"[warm] {page.url[:70]}\n")

        def call(path, body, method="POST"):
            r = page.evaluate(FETCH, {"url": path, "method": method, "body": body})
            return r["s"], pj(r)

        for ph in phones:
            print("=" * 74)
            print(f"PHONE {ph}")
            print("=" * 74)

            tests = [
                ("check_phone_exist",
                 "/api/v4/account/basic/check_phone_exist", {"phone": ph}),
                ("check_unbind_phone",
                 "/api/v4/account/management/check_unbind_phone", {"phone": ph}),
                ("get_unbind_phone_check_result",
                 "/api/v4/account/management/get_unbind_phone_check_result",
                 {"phone": ph}),
                ("change_phone_precheck_v2",
                 "/api/v4/account/management/change_phone_precheck_v2",
                 {"phone": ph}),
                ("add_phone_init",
                 "/api/v4/account/management/add_phone_init", {"phone": ph}),
            ]
            # operation enum 0..3
            for op in (0, 1, 2, 3):
                tests.append((f"check_unbind_phone_by_vcode op={op}",
                              "/api/v4/account/management/check_unbind_phone_by_vcode",
                              {"phone": ph, "vcode_token": "", "operation": op}))

            for name, path, body in tests:
                s, j = call(path, body)
                short = json.dumps(j, ensure_ascii=False)
                print(f"  [{s}] {name}")
                print(f"      {short[:340]}")
                time.sleep(0.5)

            print()

        b.close()


if __name__ == "__main__":
    main()
