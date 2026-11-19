# -*- coding: utf-8 -*-
"""cp_bundle_re.py — RE bundle halaman settings untuk urutan change_phone.

Bundle halaman settings TIDAK ter-cache (kena captcha). Kita download
langsung bundle JS dari CDN Shopee (sudah tahu polanya: sfu-stable.*.js)
dan cari semua endpoint management/*.

Output: daftar endpoint + parameter + urutan pemanggilan.
"""
import re, json, urllib.request, ssl, os

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

CANDIDATES = [
    "https://down-id.img.susercontent.com/file/id-11134207-7ras8-m0fhm4u2vy2v0b",
]

# Cari bundle dari halaman login (tidak kena captcha) + settings via raw
def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=CTX))
    return op.open(req, timeout=60).read()


def log(*a):
    print(*a, flush=True)


# 1. Ambil halaman settings HTML mentah (tanpa JS, tanpa cookie)
log("=== ambil HTML /user/account/settings ===")
try:
    html = get("https://shopee.co.id/user/account/settings").decode("utf-8", "ignore")
    log(f"  {len(html)}B")
except Exception as e:
    log(f"  err: {str(e)[:60]}")
    html = ""

# 2. Ekstrak URL .js
js = set(re.findall(r'https://[^"\']+\.js', html))
log(f"\n=== {len(js)} script di HTML ===")
for u in list(js)[:25]:
    log(f"  {u.split('/')[-1][:60]}")

# 3. fallback: pakai bundle yang sudah kita punya
os.makedirs("/root/shopee-verify/cpjs", exist_ok=True)
found = {}

def scan(name, text):
    hits = {}
    for pat in ("get_password_verify_method", "verify_payment_init",
                "verify_payment_commit", "change_phone_precheck_v2",
                "change_phone_commit_v2", "change_phone_init"):
        for m in re.finditer(re.escape(pat), text):
            a = max(0, m.start() - 320)
            b = min(len(text), m.end() + 320)
            hits.setdefault(pat, []).append(text[a:b].replace("\n", " "))
    if hits:
        found[name] = hits

# scan semua file js yang ada
for d in ("ivs_js", "sdkjs", "cpjs"):
    p = f"/root/shopee-verify/{d}"
    if not os.path.isdir(p):
        continue
    for f in os.listdir(p):
        if not f.endswith(".js"):
            continue
        try:
            t = open(os.path.join(p, f), encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        scan(f"{d}/{f}", t)

log(f"\n=== {len(found)} file punya endpoint management ===")
for f, hits in found.items():
    log(f"\n--- {f} ---")
    for pat, ctxs in hits.items():
        log(f"  {pat}: {len(ctxs)}x")
        for c in ctxs[:1]:
            log(f"    {c[:400]}")

json.dump({k: {p: v[:2] for p, v in h.items()} for k, h in found.items()},
          open("/root/shopee-verify/cp_bundle.json", "w"), indent=1)
log("\n-> cp_bundle.json")
