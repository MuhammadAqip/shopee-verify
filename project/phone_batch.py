# -*- coding: utf-8 -*-
"""
phone_batch.py — batch CEK NOMOR SHOPEE, satu browser, banyak nomor.

Optimasi:
  * satu Chromium hidup untuk seluruh batch (bukan relaunch per nomor)
  * nomor di-loop di dalam page.evaluate (satu round-trip per nomor, ~150 ms)
  * throttling + deteksi soft-block (body kosong / 90309999 berulang)
  * resume: nomor yang sudah ada di hasil tidak diulang
  * JSONL append (tahan crash)

Usage:
  python3 phone_batch.py .ck_new numbers.txt
  python3 phone_batch.py .ck_new numbers.txt --out hasil.jsonl --delay 0.8
  python3 phone_batch.py .ck_new numbers.txt --resume
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

# satu skrip JS: cek exist + unbind sekaligus
CHECK_JS = r"""
async (a) => {
  const csrfM = document.cookie.match(/(^| )csrftoken=([^;]+)/);
  const csrf = csrfM ? csrfM[2] : '';
  async function post(url, body) {
    const hex = Array.from(crypto.getRandomValues(new Uint8Array(8)))
                    .map(b => b.toString(16).padStart(2,'0')).join('');
    const h = {
      'Content-Type':'application/json','Accept':'application/json',
      'x-api-source':'pc','x-requested-with':'XMLHttpRequest',
      'x-shopee-language':'id','af-ac-enc-dat': hex,
    };
    if (csrf) h['x-csrftoken'] = csrf;
    for (let i = 0; i < 3; i++) {
      try {
        const r = await fetch(url, {method:'POST', headers:h, credentials:'include',
                                    body: JSON.stringify(body)});
        const t = await r.text();
        if (!t) { await new Promise(s=>setTimeout(s,700)); continue; }
        return JSON.parse(t);
      } catch(e) { await new Promise(s=>setTimeout(s,700)); }
    }
    return {error:-999, error_msg:'empty/exception'};
  }
  const p = a.phone;
  const ex = await post('/api/v4/account/basic/check_phone_exist', {phone: p});
  const res = {phone: p, exist_raw: ex};
  const e1 = ex && ex.error;
  if (e1 !== 0 && e1 !== null) return res;
  const d = (ex && ex.data) || {};
  res.exist = d.exist;
  res.user = d.user || null;
  if (d.exist === true) {
    res.unbind_raw = await post('/api/v4/account/management/get_unbind_phone_check_result', {phone: p});
  }
  return res;
}
"""


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


def verdict_of(r: dict) -> str:
    if r.get("error"):
        return "ERROR"
    ex = r.get("exist")
    if ex is False:
        return "FRESH"
    if ex is not True:
        return "ERROR"
    ub = (r.get("unbind_raw") or {})
    d = ub.get("data") or {}
    if ub.get("error") != 0 or not d:
        return "TERDAFTAR_CEK_GAGAL"
    if d.get("phone_reuse_limit_check_failed"):
        return "REUSE_LIMIT"
    if d.get("account_status_check_failed"):
        return "LOCKED"
    return "BISA_UNBIND"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cookie_file")
    ap.add_argument("numbers_file")
    ap.add_argument("--out", default="/root/shopee-verify/batch_result.jsonl")
    ap.add_argument("--delay", type=float, default=0.8)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--max", type=int, default=0)
    args = ap.parse_args()

    nums = []
    seen = set()
    for line in open(args.numbers_file):
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        n = norm(raw)
        if n and n not in seen:
            seen.add(n)
            nums.append(n)

    if args.max:
        nums = nums[: args.max]

    done = set()
    out = Path(args.out)
    if args.resume and out.exists():
        for line in out.open():
            try:
                done.add(json.loads(line)["phone"])
            except Exception:
                pass
        print(f"[resume] {len(done)} nomor sudah ada, dilewati")
        nums = [n for n in nums if n not in done]

    if not nums:
        print("[-] tidak ada nomor baru")
        return

    print(f"[*] {len(nums)} nomor akan dicek | delay {args.delay}s")

    jar = {}
    for seg in open(args.cookie_file).read().replace("\n", " ").split(";"):
        seg = seg.strip()
        if seg and "=" in seg:
            k, v = seg.split("=", 1)
            jar[k.strip()] = v

    fh = out.open("a")
    stats: dict[str, int] = {}
    empty_streak = 0
    t0 = time.time()

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

        print("[warm] homepage")
        page.goto(HOME, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)
        print(f"  landed: {page.url[:80]}")

        sess = page.evaluate("""async () => {
            try {
              const r = await fetch('/api/v4/account/basic/get_account_info', {credentials:'include'});
              const j = await r.json();
              return (j && j.data && j.data.userid) || 0;
            } catch(e) { return 0; }
        }""")
        if not sess:
            print("[!] sesi mati — get_account_info tidak balas userid")
            print("    cek: cookie expired? coba warm ulang / ganti cookie")
            return
        print(f"[ok] sesi hidup userid={sess}")

        for i, phone in enumerate(nums, 1):
            try:
                r = page.evaluate(CHECK_JS, {"phone": phone})
            except Exception as e:
                r = {"phone": phone, "error": -998, "error_msg": str(e)}

            v = verdict_of(r)
            stats[v] = stats.get(v, 0) + 1

            # deteksi soft-block
            if r.get("error") == -999:
                empty_streak += 1
            else:
                empty_streak = 0

            user = r.get("user") or {}
            uname = user.get("username") or ""
            rec = {
                "phone": phone,
                "verdict": v,
                "username": uname,
                "exist": r.get("exist"),
                "unbind": (r.get("unbind_raw") or {}).get("data"),
                "err": r.get("error_msg") or r.get("error"),
                "ts": int(time.time()),
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()

            pct = i * 100 // len(nums)
            eta = ((time.time() - t0) / i) * (len(nums) - i) if i else 0
            print(f"  [{i:>5}/{len(nums)}] {pct:3}%  {phone:15} {v:20} "
                  f"{('@' + uname) if uname else '':18} eta {eta:.0f}s")

            if empty_streak >= 8:
                print("  [!] 8x kosong berturut — kemungkinan soft-block. "
                      "istirahat 45s + reload homepage")
                time.sleep(45)
                page.goto(HOME, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(5000)
                empty_streak = 0

            time.sleep(args.delay)

        b.close()
    fh.close()

    dur = time.time() - t0
    print(f"\n{'='*64}\nSELESAI {len(nums)} nomor dalam {dur:.1f}s "
          f"({len(nums)/max(dur,1):.1f} nomor/detik)")
    for k, v in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {k:22} {v:>6}  ({v*100//max(len(nums),1)}%)")
    print(f"\n[+] {out}")


if __name__ == "__main__":
    main()
