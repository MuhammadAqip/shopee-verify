# -*- coding: utf-8 -*-
"""
phone_check.py — CEK NOMOR SHOPEE (terdaftar? bisa di-unbind?).

Alur per nomor:
  1. check_phone_exist {phone}
       error 0 + data.exist=false  -> FRESH (belum terdaftar)
       error 0 + data.exist=true   -> TERDAFTAR, lanjut
  2. get_unbind_phone_check_result {phone}
       data.account_status_check_failed   == false -> BISA UNBIND
       data.account_status_check_failed   == true  -> TIDAK BISA unbind
       data.phone_reuse_limit_check_failed== true  -> kena limit reuse
  3. change_phone_precheck_v2 {phone}
       error 0  -> lolos precheck (nomor boleh dipakai untuk ganti)
       error !=0-> ditolak, lihat kode

Semua via page.evaluate(fetch) — SFU signing otomatis dari halaman Shopee.
Warm di homepage (JANGAN /user/account/profile yang kena captcha).

Usage:
  python3 phone_check.py .ck_new 6281234567890
  python3 phone_check.py .ck_new --file numbers.txt
  python3 phone_check.py .ck_new --stdin      # satu nomor per baris
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HOME = "https://shopee.co.id/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

FETCH_JS = r"""
async (a) => {
  const m = document.cookie.match(/(^| )csrftoken=([^;]+)/);
  const csrf = m ? m[2] : '';
  const hex = Array.from(crypto.getRandomValues(new Uint8Array(8)))
                  .map(b => b.toString(16).padStart(2,'0')).join('');
  const h = {
    'Content-Type':'application/json',
    'Accept':'application/json',
    'x-api-source':'pc',
    'x-requested-with':'XMLHttpRequest',
    'x-shopee-language':'id',
    'af-ac-enc-dat': hex,
  };
  if (csrf) h['x-csrftoken'] = csrf;
  for (let i = 0; i < 3; i++) {
    try {
      const r = await fetch(a.url, {method:a.method||'GET', headers:h,
        credentials:'include', body:a.body?JSON.stringify(a.body):undefined});
      const t = await r.text();
      if (t.length === 0 && i < 2) { await new Promise(s=>setTimeout(s,900)); continue; }
      return {s:r.status, n:t.length, b:t};
    } catch(e) {
      if (i === 2) return {s:0,n:0,b:'EXC: '+String(e)};
      await new Promise(s=>setTimeout(s,900));
    }
  }
}
"""


def parse_cookie(raw: str) -> dict[str, str]:
    out = {}
    for seg in raw.replace("\n", " ").split(";"):
        seg = seg.strip()
        if seg and "=" in seg:
            k, v = seg.split("=", 1)
            out[k.strip()] = v
    return out


def normalize_phone(p: str) -> str:
    """62xxx / 0xxx / +62xxx -> 62xxx (tanpa +)."""
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


# ---------------- kode error Shopee ----------------
ERR = {
    0: "OK",
    10002: "Parameter tidak valid (shape body salah)",
    10013: "Nomor tidak terikat ke akun ini / tidak bisa unbind",
    90309999: "Anti-fraud token ditolak (perlu SFU/browser)",
    19: "Failed to authenticate (sesi/SFU mati)",
}


def call(page, path: str, body: dict | None = None, method: str = "POST") -> dict:
    res = page.evaluate(FETCH_JS, {"url": path, "method": method, "body": body})
    raw = res["b"]
    try:
        j = json.loads(raw)
    except Exception:
        j = {"_raw": raw[:400]}
    return {"http": res["s"], "json": j, "len": res["n"]}


def check_one(page, phone: str, verbose: bool = True) -> dict:
    p = normalize_phone(phone)
    out = {"input": phone, "phone": p, "verdict": "?", "detail": {}}
    if not p or len(p) < 10:
        out["verdict"] = "INVALID"
        return out

    if verbose:
        print(f"\n{'='*68}\n[*] NOMOR: {phone}  ->  {p}")

    # --- 1. check_phone_exist ---
    r1 = call(page, "/api/v4/account/basic/check_phone_exist", {"phone": p})
    j1 = r1["json"]
    out["detail"]["check_exist"] = j1
    err1 = j1.get("error")

    if err1 not in (0, None):
        # kadang butuh otp_token; fallback pakai bentuk kedua
        r1b = call(page, "/api/v4/account/basic/check_phone_exist", {})
        if (r1b["json"].get("error") in (0, None)):
            j1 = r1b["json"]
            out["detail"]["check_exist"] = {"primary": j1 and out["detail"]["check_exist"],
                                            "fallback": j1}
        else:
            out["verdict"] = "ERROR"
            out["error_code"] = err1
            out["error_msg"] = j1.get("error_msg") or ERR.get(err1, "unknown")
            if verbose:
                print(f"  [1] check_exist  -> error {err1}: {out['error_msg']}")
            return out

    data1 = j1.get("data") or {}
    exist = data1.get("exist")
    user = data1.get("user")
    out["detail"]["exist"] = exist
    out["detail"]["user"] = user

    if verbose:
        if exist:
            uname = (user or {}).get("username") if isinstance(user, dict) else None
            uid = (user or {}).get("userid") if isinstance(user, dict) else None
            print(f"  [1] check_exist  -> TERDAFTAR  user={uname} uid={uid}")
        else:
            print("  [1] check_exist  -> FRESH (belum terdaftar)")

    # FRESH -> stop di sini
    if exist is False:
        out["verdict"] = "FRESH"
        return out

    # --- 2. get_unbind_phone_check_result ---
    r2 = call(page, "/api/v4/account/management/get_unbind_phone_check_result", {"phone": p})
    j2 = r2["json"]
    out["detail"]["unbind_check"] = j2
    e2 = j2.get("error")
    d2 = j2.get("data") or {}

    if e2 == 0 and d2:
        acct_fail = bool(d2.get("account_status_check_failed"))
        reuse_fail = bool(d2.get("phone_reuse_limit_check_failed"))
        out["detail"]["account_status_check_failed"] = acct_fail
        out["detail"]["phone_reuse_limit_check_failed"] = reuse_fail
        if not acct_fail and not reuse_fail:
            out["verdict"] = "TERDAFTAR_UNBINDABLE"       # bisa di-unbind
        elif reuse_fail:
            out["verdict"] = "TERDAFTAR_REUSE_LIMIT"      # kena limit pemakaian
        else:
            out["verdict"] = "TERDAFTAR_LOCKED"           # tidak bisa unbind
        if verbose:
            print(f"  [2] unbind_check -> account_status_check_failed={acct_fail} "
                  f"phone_reuse_limit_check_failed={reuse_fail}")
            print(f"      => {out['verdict']}")
    else:
        out["detail"]["unbind_check_error"] = e2
        if verbose:
            print(f"  [2] unbind_check -> error {e2}: {ERR.get(e2,'unknown')}")

    # --- 3. change_phone_precheck_v2 ---
    r3 = call(page, "/api/v4/account/management/change_phone_precheck_v2", {"phone": p})
    j3 = r3["json"]
    out["detail"]["precheck"] = j3
    e3 = j3.get("error")
    if verbose:
        if e3 in (0, None):
            print("  [3] precheck     -> OK (nomor boleh dipakai untuk ganti)")
        else:
            print(f"  [3] precheck     -> error {e3}: {ERR.get(e3,'ditolak')}")

    # verdict final kalau #2 gagal
    if out["verdict"] == "?":
        out["verdict"] = "TERDAFTAR_CEK_GAGAL" if e2 not in (0, None) else "TERDAFTAR"
    return out


ICON = {
    "FRESH": "🟢",
    "TERDAFTAR_UNBINDABLE": "🔵",
    "TERDAFTAR_LOCKED": "🔴",
    "TERDAFTAR_REUSE_LIMIT": "🟠",
    "INVALID": "⚪",
    "ERROR": "⚫",
    "TERDAFTAR": "🔵",
    "TERDAFTAR_CEK_GAGAL": "🟡",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cookie_file")
    ap.add_argument("phone", nargs="?", help="satu nomor")
    ap.add_argument("--file", help="file berisi nomor, satu per baris")
    ap.add_argument("--stdin", action="store_true", help="baca nomor dari stdin")
    ap.add_argument("--json-out", default="/root/shopee-verify/phone_check_result.json")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    phones: list[str] = []
    if args.phone:
        phones.append(args.phone)
    if args.file:
        phones += [l.strip() for l in open(args.file) if l.strip()]
    if args.stdin:
        phones += [l.strip() for l in sys.stdin if l.strip()]
    if not phones:
        print("[-] tidak ada nomor. pakai: phone_check.py .ck_new 628xxx | --file f | --stdin")
        return

    jar = parse_cookie(open(args.cookie_file).read().strip())
    results = []

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=not args.headed, args=[
            "--no-sandbox", "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(user_agent=UA, locale="id-ID",
                            viewport={"width": 1366, "height": 900},
                            timezone_id="Asia/Jakarta")
        page = ctx.new_page()

        objs = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/",
                 "secure": True, "sameSite": "None"} for k, v in jar.items()]
        try:
            ctx.add_cookies(objs)
        except Exception:
            pass
        cdp = ctx.new_cdp_session(page)
        cdp.send("Network.enable")
        for k, v in jar.items():
            try:
                cdp.send("Network.setCookie", {"name": k, "value": v,
                                               "domain": ".shopee.co.id", "path": "/",
                                               "secure": True, "httpOnly": False})
            except Exception:
                pass

        print("[warm] homepage")
        page.goto(HOME, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)
        print(f"  landed: {page.url[:85]}")

        # sanity: sesi harus hidup
        s = call(page, "/api/v4/account/basic/get_account_info", None, "GET")
        uid = ((s["json"].get("data") or {}).get("userid"))
        if not uid:
            print(f"[!] sesi tidak valid: {json.dumps(s['json'])[:180]}")
            if "verify" in page.url:
                print("[!] browser kena captcha, tapi coba lanjut (fetch tetap bawa cookie)")
        else:
            print(f"[ok] sesi hidup: userid={uid}")

        for i, ph in enumerate(phones, 1):
            print(f"\n--- [{i}/{len(phones)}] ---")
            try:
                res = check_one(page, ph)
            except Exception as e:
                res = {"input": ph, "verdict": "ERROR", "error_msg": str(e)}
            results.append(res)
            if i < len(phones):
                time.sleep(1.2)

        # kalau landing ke captcha, coba sekali lagi warm
        b.close()

    Path(args.json_out).write_text(json.dumps(results, indent=1, ensure_ascii=False))

    print(f"\n{'='*68}\nRINGKASAN\n{'='*68}")
    for r in results:
        v = r.get("verdict", "?")
        d = r.get("detail", {})
        u = d.get("user") or {}
        uname = f" @{u.get('username')}" if isinstance(u, dict) and u.get("username") else ""
        extra = ""
        if "account_status_check_failed" in d:
            extra = (f" [acct_fail={d['account_status_check_failed']}"
                     f" reuse_fail={d.get('phone_reuse_limit_check_failed')}]")
        print(f"  {ICON.get(v,'·')} {r.get('phone',''):15} {v:24}{uname}{extra}")
    print(f"\n[+] json -> {args.json_out}")


if __name__ == "__main__":
    main()
