# -*- coding: utf-8 -*-
"""
truth_probe.py — cari endpoint yang BENAR untuk patokan "bisa unbind".

Yang SUDAH diketahui tidak berguna:
  * get_unbind_phone_check_result -> selalu {acct:false, reuse:false} = POLLING
    kosong, bukan indikator apa pun.
  * check_unbind_phone (tanpa vcode) -> 12301115 (butuh vcode_token)
  * change_phone_precheck_v2 / add_phone_init -> 10002 (butuh state IVS)

Yang diuji sekarang: endpoint yang memberi state NYATA per nomor.
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
    let j; try { j = JSON.parse(t); } catch(e) { j = {_raw:t.slice(0,250)}; }
    return {s:r.status, j, n:t.length};
  } catch(e) { return {s:0, j:{_exc:String(e)}, n:0}; }
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
            r = page.evaluate(FETCH, {"url": path, "method": method, "body": body})
            return r

        # ---------- akun sendiri sebagai baseline ----------
        print("=" * 74)
        print("BASELINE: akun kita sendiri")
        print("=" * 74)
        me = call("/api/v4/account/basic/get_account_info", None, "GET")["j"]
        myphone = (me.get("data") or {}).get("phone")
        print(f"  phone kita: {myphone}")

        for ep, body in [
            ("/api/v4/account/management/check_unbind_phone", {"phone": myphone}),
            ("/api/v4/account/management/get_unbind_phone_check_result", {"phone": myphone}),
        ]:
            r = call(ep, body)
            print(f"  {ep.split('/')[-1]:38} {json.dumps(r['j'], ensure_ascii=False)[:200]}")

        # ---------- nomor orang lain ----------
        for ph in phones:
            print("\n" + "=" * 74)
            print(f"TARGET {ph}")
            print("=" * 74)

            tests = [
                ("check_unbind_phone",
                 "/api/v4/account/management/check_unbind_phone", {"phone": ph}),
                ("get_phone_validation_list",
                 "/api/v4/account/basic/get_phone_validation_list", None),
                ("check_phone_exist (otp_token kosong)",
                 "/api/v4/account/basic/check_phone_exist", {"otp_token": "", "phone": ph}),
                ("get_unbind_phone_check_result",
                 "/api/v4/account/management/get_unbind_phone_check_result", {"phone": ph}),
            ]

            for name, path, body in tests:
                method = "GET" if body is None else "POST"
                r = call(path, body, method)
                print(f"  [{r['s']}] {name}")
                print(f"       {json.dumps(r['j'], ensure_ascii=False)[:290]}")

            # send_vcode: apakah Shopee mau kirim OTP ke nomor orang lain?
            r = call("/api/v4/otp/send_vcode",
                     {"phone": ph, "channel": 1, "operation": 0, "force_channel": False})
            print(f"  [{r['s']}] send_vcode operation=0")
            print(f"       {json.dumps(r['j'], ensure_ascii=False)[:290]}")

        b.close()


if __name__ == "__main__":
    main()
