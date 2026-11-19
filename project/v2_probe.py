# -*- coding: utf-8 -*-
"""
v2_probe.py — probe jalur `/api/v2/user/phone/update/`.

Temuan dari bundle:
    POST /api/v2/user/phone/update/
    body: {client_type, system_version, longitude, latitude,
           phone, vcode, otp_seed, decision_token, force_seed}

`force_seed` + `decision_token` = kunci. Ini jalur bind phone yang lebih tua
(yang masih dipakai homepagefe) dan TIDAK lewat change_phone_init_v2.

Langkah:
  1. get_account_info -> baseline
  2. send_vcode {phone, channel, operation} -> dapat seed
  3. POST /api/v2/user/phone/update/ dengan seed (vcode dummy)
     -> lihat error code: beda antara "nomor bisa" vs "tidak"
  4. cek check_phone_exist & get_unbind untuk perbandingan
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
    let j; try { j = JSON.parse(t); } catch(e) { j = {_raw:t.slice(0,300)}; }
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


def norm(p):
    d = "".join(c for c in str(p or "") if c.isdigit())
    if d.startswith("0"):
        d = "62" + d[1:]
    elif d.startswith("8"):
        d = "62" + d
    return d


def main():
    ck = sys.argv[1] if len(sys.argv) > 1 else str(BASE / ".ck_new")
    raw = sys.argv[2:] or ["089601416330", "087876125616"]
    phones = [norm(x) for x in raw]
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
        print(f"[warm] {page.url[:60]}")

        me = page.evaluate(FETCH, {"url": "/api/v4/account/basic/get_account_info",
                                   "body": None})
        print(f"[me] {json.dumps(me['j'])[:200]}\n")

        def P(path, body):
            return page.evaluate(FETCH, {"url": path, "body": body})

        for ph in phones:
            print("=" * 74)
            print(f"PHONE {ph}")
            print("=" * 74)

            # --- 1. check_phone_exist
            ex = P("/api/v4/account/basic/check_phone_exist", {"phone": ph})["j"]
            d = ex.get("data") or {}
            print(f"  exist       : {d.get('exist')} @{((d.get('user') or {}).get('username'))}")

            # --- 2. unbind check
            ub = P("/api/v4/account/management/get_unbind_phone_check_result",
                   {"phone": ph})["j"]
            print(f"  unbind      : {json.dumps(ub.get('data'))}")

            # --- 3. send_vcode (operation 0=GENERAL)
            sv = P("/api/v4/otp/send_vcode",
                   {"phone": ph, "channel": 1, "operation": 0,
                    "force_channel": False})["j"]
            seed = (sv.get("data") or {}).get("seed")
            print(f"  send_vcode  : err={sv.get('error')} seed={str(seed)[:40]}")

            # --- 4. /api/v2/user/phone/update/ dengan seed
            for force in (True, False):
                body = {
                    "client_type": 1, "system_version": 35,
                    "longitude": 106.8456, "latitude": -6.2088,
                    "phone": ph, "vcode": "000000",
                    "otp_seed": seed or "",
                    "decision_token": "",
                    "force_seed": force,
                }
                r = P("/api/v2/user/phone/update/", body)["j"]
                print(f"  v2update force={force!s:5}: {json.dumps(r, ensure_ascii=False)[:230]}")

            # --- 5. v1 change_phone_commit (jalur lain)
            ci = P("/api/v4/account/management/change_phone_init", {})["j"]
            seq = (ci.get("data") or {}).get("seq_no")
            print(f"  change_init : {json.dumps(ci, ensure_ascii=False)[:180]}")
            if seq:
                cc = P("/api/v4/account/management/change_phone_commit",
                       {"seq_no": seq, "phone": ph, "otp_code": "000000",
                        "otp_seed": seed or ""})["j"]
                print(f"  commit{seq[:8]}: {json.dumps(cc, ensure_ascii=False)[:230]}")

            print()
            time.sleep(1.5)

        b.close()


if __name__ == "__main__":
    main()
