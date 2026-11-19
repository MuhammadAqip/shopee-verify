# -*- coding: utf-8 -*-
"""
scenario_probe.py — `scenario` adalah kunci yang kita lewatkan.

TuyulHelper pakai:
  check-exist  {phone, scenario:1}
  check-numbers {numbers:[], delay_seconds:2, scenario:2}

Test semua scenario 0..5 untuk:
  * check_phone_exist
  * change_phone_precheck_v2
  * get_unbind_phone_check_result
  * check_unbind_phone
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
    const r = await fetch(a.url, {method:'POST', headers:h,
      credentials:'include', body:JSON.stringify(a.body)});
    const t = await r.text();
    let j; try { j = JSON.parse(t); } catch(e) { j = {_raw:t.slice(0,200)}; }
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
        page.wait_for_timeout(7000)
        print(f"[warm] {page.url[:60]}\n")

        # baseline akun sendiri, supaya tahu jawaban "pasti bisa"
        me = page.evaluate(FETCH, {"url": "/api/v4/account/basic/get_account_info",
                                   "body": None})
        my = None
        try:
            my = page.evaluate("""async () => {
                const r = await fetch('/api/v4/account/basic/get_account_info',
                                      {credentials:'include'});
                const j = await r.json();
                return (j && j.data && j.data.phone) || null;
            }""")
        except Exception:
            pass
        print(f"[baseline] phone akun kita: {my}\n")

        EPS = [
            ("check_phone_exist", "/api/v4/account/basic/check_phone_exist"),
            ("get_unbind_phone_check_result",
             "/api/v4/account/management/get_unbind_phone_check_result"),
            ("change_phone_precheck_v2",
             "/api/v4/account/management/change_phone_precheck_v2"),
            ("check_unbind_phone",
             "/api/v4/account/management/check_unbind_phone"),
        ]

        targets = [("SELF", my)] if my else []
        targets += [("OTHER", p) for p in phones]

        for tag, ph in targets:
            print("=" * 76)
            print(f"{tag}: {ph}")
            print("=" * 76)
            for name, path in EPS:
                for sc in (0, 1, 2, 3):
                    r = page.evaluate(FETCH, {"url": path,
                                              "body": {"phone": ph, "scenario": sc}})
                    txt = json.dumps(r["j"], ensure_ascii=False)
                    print(f"  scenario={sc} {name:32} {txt[:200]}")
                print()

        b.close()


if __name__ == "__main__":
    main()
