# -*- coding: utf-8 -*-
"""
verdict_test.py — verifikasi HIPOTESIS patokan unbind.

Data dari Maker:
    089601416330  -> acct=false reuse=false  -> TIDAK BISA unbind
    087876125616  -> acct=true  reuse=false  -> BISA unbind

Artinya patokannya TERBALIK dari tebakan awal:
    account_status_check_failed == TRUE  -> BISA unbind
    account_status_check_failed == FALSE -> TIDAK bisa

Kenapa masuk akal: field bernama "check_FAILED". Kalau pengecekan status akun
GAGAL, artinya sistem tidak bisa memblokir -> nomor lolos -> BISA di-unbind.
Kalau pengecekan BERHASIL (false), sistem menolak -> TIDAK bisa.

Script ini memverifikasi dengan mengumpulkan banyak sample dan mencari
korelasi terhadap signal lain (send_vcode, error code).
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
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
        print(f"[warm] {page.url[:60]}\n")

        rows = []
        for ph in phones:
            ex = page.evaluate(FETCH, {"url": "/api/v4/account/basic/check_phone_exist",
                                       "body": {"phone": ph}})["j"]
            ub = page.evaluate(FETCH, {"url": "/api/v4/account/management/get_unbind_phone_check_result",
                                       "body": {"phone": ph}})["j"]
            d = ub.get("data") or {}
            acct = d.get("account_status_check_failed")
            reuse = d.get("phone_reuse_limit_check_failed")
            exist = (ex.get("data") or {}).get("exist")
            uname = ((ex.get("data") or {}).get("user") or {}).get("username")

            # hipotesis: acct=true -> bisa unbind
            if exist is False:
                verdict = "FRESH"
            elif acct is True and reuse is False:
                verdict = "BISA_UNBIND"
            elif acct is False and reuse is False:
                verdict = "TIDAK_BISA"
            elif reuse is True:
                verdict = "REUSE_LIMIT"
            else:
                verdict = "UNKNOWN"

            rows.append({"phone": ph, "exist": exist, "username": uname,
                         "acct_fail": acct, "reuse_fail": reuse, "verdict": verdict})
            print(f"  {ph}  exist={exist!s:5} acct={acct!s:5} reuse={reuse!s:5} "
                  f"-> {verdict:12} @{uname or '-'}")
            time.sleep(1.0)

        print("\n" + "=" * 70)
        print("HASIL")
        print("=" * 70)
        for r in rows:
            print(f"  {r['phone']:15} acct_fail={r['acct_fail']!s:5} -> {r['verdict']}")
        print("\nCounter:", dict(Counter(r["verdict"] for r in rows)))

        out = BASE / "verdict_test.json"
        out.write_text(json.dumps(rows, indent=1, ensure_ascii=False))
        print(f"[+] {out}")
        b.close()


if __name__ == "__main__":
    main()
