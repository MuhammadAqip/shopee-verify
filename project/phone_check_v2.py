# -*- coding: utf-8 -*-
"""
phone_check_v2.py — CEK NOMOR SHOPEE (endpoint benar).

Patokan final:
  1. POST /api/v4/account/basic/check_phone_exist        {phone}
         exist=false -> FRESH
         exist=true  -> lanjut
  2. POST /api/v4/account/management/check_unbind_phone   {phone}
         error=0        -> BISA_UNBIND
         error=12301115 -> NOT_ALLOW_UNBIND
         error=12301116 -> RESTRICTED
         error=12301004 -> REUSE_LIMIT
         error=12301029 -> BANNED
         error=10013/12301016 -> PHONE_NOT_FOUND
         error=90309999 -> RATE_LIMITED (proxy mati / IP flagged)

Tidak butuh login. Wajib proxy residensial Indonesia.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = Path("/root/shopee-verify")
HOME = "https://shopee.co.id/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

RELAY = "http://127.0.0.1:18080"

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
    0: ("BISA_UNBIND", "Terdaftar - BISA di-unbind"),
    12301115: ("NOT_ALLOW_UNBIND", "Terdaftar - TIDAK boleh unbind"),
    12301116: ("RESTRICTED", "Terdaftar - akun/nomor di-restrict"),
    12301004: ("REUSE_LIMIT", "Terdaftar - limit pemakaian"),
    12301029: ("BANNED", "Terdaftar - akun banned"),
    12301031: ("RECYCLED", "Nomor daur ulang"),
    12301016: ("PHONE_NOT_EXIST", "Tidak terdaftar"),
    10013: ("PHONE_NOT_FOUND", "Tidak terdaftar"),
    12301066: ("CHANGE_ONGOING", "Ada request ganti berjalan"),
    12301064: ("NEW_DEVICE_COOLDOWN", "Cooldown device baru"),
    90309999: ("RATE_LIMITED", "Rate limit - ganti proxy"),
    10010: ("BAD_FINGERPRINT", "Device fingerprint invalid"),
    12301028: ("PHONE_INVALID", "Format nomor tidak valid"),
    12304004: ("INVALID_REGION", "Region tidak valid"),
}


def norm(p: str) -> str:
    d = re.sub(r"\D", "", str(p or ""))
    if not d:
        return ""
    if d.startswith("0"):
        d = "62" + d[1:]
    elif d.startswith("8"):
        d = "62" + d
    elif d.startswith("620"):
        d = "62" + d[3:]
    return d


def verdict_of(exist: bool | None, err: int | None) -> tuple[str, str]:
    if exist is False:
        return "FRESH", "Belum terdaftar (fresh)"
    name, label = CODE.get(err, (f"UNKNOWN_{err}", f"Kode tidak dikenal ({err})"))
    return name, label


def new_page(pw, proxy_url: str = RELAY):
    b = pw.chromium.launch(headless=True, proxy={"server": proxy_url}, args=[
        "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--ignore-certificate-errors"])
    ctx = b.new_context(user_agent=UA, locale="id-ID",
                        viewport={"width": 1366, "height": 900},
                        timezone_id="Asia/Jakarta", ignore_https_errors=True)
    page = ctx.new_page()
    page.goto(HOME, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(5000)
    return b, page


def check_one(page, phone: str) -> dict:
    p = norm(phone)
    out = {"input": phone, "phone": p}
    if not p or len(p) < 10:
        out.update(verdict="INVALID", label="Nomor tidak valid")
        return out

    ex = page.evaluate(FETCH, {"url": "/api/v4/account/basic/check_phone_exist",
                               "body": {"phone": p}})["j"]
    d = ex.get("data") or {}
    exist = d.get("exist")
    uname = ((d.get("user") or {}).get("username"))

    err = None
    raw = None
    if exist is True:
        ub = page.evaluate(FETCH, {"url": "/api/v4/account/management/check_unbind_phone",
                                   "body": {"phone": p}})["j"]
        err = ub.get("error")
        raw = ub

    name, label = verdict_of(exist, err)
    out.update(verdict=name, label=label, exist=exist, username=uname,
               error=err, raw=raw)
    return out


ICON = {"FRESH": "🟢", "BISA_UNBIND": "🔵", "NOT_ALLOW_UNBIND": "🔴",
        "RESTRICTED": "🔴", "REUSE_LIMIT": "🟠", "BANNED": "⛔",
        "RECYCLED": "🟠", "RATE_LIMITED": "⏳", "PHONE_NOT_FOUND": "🟢",
        "PHONE_NOT_EXIST": "🟢", "INVALID": "⚪"}


def main():
    args = sys.argv[1:]
    if not args:
        print("usage: phone_check_v2.py <nomor...> | --file f.txt")
        return
    phones = []
    if args[0] == "--file":
        for line in open(args[1]):
            s = line.strip()
            if s and not s.startswith("#"):
                phones.append(s)
    else:
        phones = args

    print(f"[*] {len(phones)} nomor | proxy {RELAY}")
    results = []
    t0 = time.time()

    with sync_playwright() as pw:
        b, page = new_page(pw)
        for i, ph in enumerate(phones, 1):
            try:
                r = check_one(page, ph)
            except Exception as e:
                r = {"input": ph, "phone": norm(ph), "verdict": "ERROR",
                     "label": f"exception: {e}"}
            results.append(r)
            ic = ICON.get(r["verdict"], "·")
            u = f" @{r['username']}" if r.get("username") else ""
            print(f"  [{i:>3}/{len(phones)}] {ic} {r['phone']:15} "
                  f"{r['verdict']:18}{u}")
            time.sleep(0.9)
        b.close()

    out = BASE / "check_v2_result.json"
    out.write_text(json.dumps(results, indent=1, ensure_ascii=False))

    from collections import Counter
    c = Counter(r["verdict"] for r in results)
    print(f"\n{'='*60}\nSELESAI {len(results)} nomor dalam {time.time()-t0:.0f}s")
    for k, v in sorted(c.items(), key=lambda x: -x[1]):
        print(f"  {ICON.get(k,'·')} {k:20} {v:>5}  ({v*100//len(results)}%)")
    print(f"\n[+] {out}")


if __name__ == "__main__":
    main()
