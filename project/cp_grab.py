# -*- coding: utf-8 -*-
"""cp_grab.py — download bundle settings & cari endpoint change_phone.

Dari HTML /user/account/settings kita dapat 321 URL script.
Filter yang mengandung 'usersetting' / 'usersettings' / 'privacy' / 'account'
lalu scan semua endpoint management/* dan urutan pemanggilannya.
"""
import re, os, json, urllib.request, ssl

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
OUTDIR = "/root/shopee-verify/cpjs"
os.makedirs(OUTDIR, exist_ok=True)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=CTX))
    return op.open(req, timeout=70).read()


def log(*a):
    print(*a, flush=True)


log("=== ambil HTML settings ===")
html = get("https://shopee.co.id/user/account/settings").decode("utf-8", "ignore")
urls = sorted(set(re.findall(r'https://[^"\']+\.js', html)))
log(f"  {len(urls)} script")

# prioritas
KEY = ("usersetting", "privacy", "account", "bundle", "antifraud")
prio = [u for u in urls if any(k in u.lower() for k in KEY)]
log(f"  {len(prio)} prioritas")

downloaded = 0
for u in prio:
    name = u.split("/")[-1].split("?")[0]
    if not name.endswith(".js"):
        name += ".js"
    path = os.path.join(OUTDIR, name)
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        continue
    try:
        data = get(u)
        if len(data) > 200:
            open(path, "wb").write(data)
            downloaded += 1
            log(f"  ✓ {name[:60]} {len(data)}B")
    except Exception as e:
        log(f"  ✗ {name[:40]} {str(e)[:40]}")

log(f"\n=== {downloaded} baru diunduh ===")

# scan semua
TARGETS = ("get_password_verify_method", "verify_payment_init",
           "verify_payment_commit", "change_phone_precheck_v2",
           "change_phone_commit_v2", "change_phone_init",
           "verify_password")
found = {}
for f in os.listdir(OUTDIR):
    if not f.endswith(".js"):
        continue
    try:
        t = open(os.path.join(OUTDIR, f), encoding="utf-8", errors="ignore").read()
    except Exception:
        continue
    for pat in TARGETS:
        for m in re.finditer(re.escape(pat), t):
            a = max(0, m.start() - 350)
            b = min(len(t), m.end() + 350)
            found.setdefault(pat, []).append((f, t[a:b].replace("\n", " ")))

log(f"\n=== HASIL SCAN ===")
for pat in TARGETS:
    hits = found.get(pat, [])
    log(f"\n{'='*15} {pat} ({len(hits)}x) {'='*15}")
    for f, ctx in hits[:2]:
        log(f"  [{f[:35]}]")
        log(f"  {ctx[:650]}")

json.dump({k: [(f, c[:700]) for f, c in v[:3]] for k, v in found.items()},
          open("/root/shopee-verify/cp_bundle2.json", "w"), indent=1)
log("\n-> cp_bundle2.json")
