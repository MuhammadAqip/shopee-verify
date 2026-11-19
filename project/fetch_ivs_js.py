# -*- coding: utf-8 -*-
"""fetch_ivs_js.py — ambil bundle JS dari halaman /verify/ivs, cari
pemanggilan ivs/methods + bentuk body-nya."""
import sys, json, re, os
from playwright.sync_api import sync_playwright

COOKIE = open("/root/shopee-verify/ck_1553.txt").read().strip()
CSRF = "3929567fdad6e3608eb25fd137f69955"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
OUTDIR = "/root/shopee-verify/ivs_js"
os.makedirs(OUTDIR, exist_ok=True)

cookies = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
           for k, _, v in (p.strip().partition("=") for p in COOKIE.split(";"))
           if k and v]
cookies.append({"name": "csrftoken", "value": CSRF,
                "domain": ".shopee.co.id", "path": "/"})

scripts = []

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=["--no-sandbox",
                                                 "--disable-dev-shm-usage"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         ignore_https_errors=True,
                         proxy={"server": "http://127.0.0.1:18080"})
    ctx.add_cookies(cookies)
    pg = ctx.new_page()
    pg.on("response", lambda r: scripts.append(r.url)
          if r.url.endswith(".js") else None)
    try:
        pg.goto("https://shopee.co.id/verify/ivs",
                wait_until="networkidle", timeout=70000)
    except Exception as e:
        print("goto:", str(e)[:90])
    pg.wait_for_timeout(6000)
    # semua script src
    srcs = pg.evaluate(
        "Array.from(document.scripts).map(s=>s.src).filter(Boolean)")
    br.close()

alljs = sorted(set([s for s in scripts + srcs if s]))
print(f"ditemukan {len(alljs)} file JS")

hits = []
for i, url in enumerate(alljs):
    try:
        r = __import__("urllib.request", fromlist=["x"])
        req = r.Request(url, headers={"User-Agent": UA})
        data = r.urlopen(req, timeout=25).read().decode("utf-8", "ignore")
    except Exception as e:
        print(f"  [{i}] SKIP {url[-40:]} ({str(e)[:40]})")
        continue
    fn = os.path.join(OUTDIR, f"{i:03d}.js")
    open(fn, "w", encoding="utf-8").write(data)
    if "ivs/methods" in data or "ivs_method" in data or "ivsMethods" in data:
        hits.append((i, url, fn, len(data)))
        print(f"  [{i}] ✅ HIT {url[-50:]} ({len(data)} B)")
    else:
        print(f"  [{i}]    {url[-50:]} ({len(data)} B)")

print("\n=== FILE YANG PUNYA ivs/methods ===")
for i, url, fn, ln in hits:
    print(f"{fn} <- {url}")
    d = open(fn, encoding="utf-8").read()
    for m in re.finditer(r"ivs/methods", d):
        s = max(0, m.start() - 500)
        print("\n--- konteks ---")
        print(d[s:m.end() + 500])
        print()
