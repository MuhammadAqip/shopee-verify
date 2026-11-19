# -*- coding: utf-8 -*-
"""hdr_test.py — A/B test: apakah x-sap-* header mempengaruhi 90309999.

Skenario:
  A. tanpa header
  B. header x-sap-ri PALSU (random)
  C. header x-sap-ri ASLI (dari capture)
  D. header LENGKAP asli (ri+sec+af-ac)
  E. header ri asli + af-ac random

Target: /api/v4/cart/mini (yang selalu 90309999)
"""
import json, sys, time, secrets, urllib.request, urllib.error

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1659.txt"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

ck = open(CK).read().strip()
CSRF = ""
for p in ck.split(";"):
    if p.strip().startswith("csrftoken="):
        CSRF = p.split("=", 1)[1].strip()

cap = json.load(open("aes_pairs.json"))
ri_real = next(h["v"] for h in cap["hdr"] if h["k"] == "x-sap-ri")
sec_real = next(h["v"] for h in cap["hdr"] if h["k"] == "x-sap-sec")
af_real = next(h["v"] for h in cap["hdr"] if h["k"] == "af-ac-enc-dat")
sztok = next((h["v"] for h in cap["hdr"]
              if h["k"] == "af-ac-enc-sz-token" and h["v"]), "")


def mk_ri(ts=None):
    ts = ts or int(time.time())
    return (ts.to_bytes(4, "little").hex()
            + secrets.token_hex(8)
            + "1601"
            + secrets.token_hex(12))


def call(hdrs, path="/api/v4/cart/mini", body=None):
    h = {"Cookie": ck, "User-Agent": UA, "X-API-SOURCE": "pc",
         "X-Requested-With": "XMLHttpRequest",
         "Referer": "https://shopee.co.id/", "Accept": "application/json",
         "Content-Type": "application/json", "X-CSRFToken": CSRF,
         "X-Shopee-Language": "id"}
    h.update(hdrs)
    d = json.dumps(body or {"version_list": [3145728, 65]}).encode()
    req = urllib.request.Request("https://shopee.co.id" + path, data=d,
                                 headers=h, method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=45)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}
    except Exception as ex:
        return 0, {"exc": str(ex)[:50]}


print(f"=== HEADER A/B TEST — {CK} ===\n")
print(f"ri_real:  {ri_real}")
print(f"ri_fake:  {mk_ri()}")
print(f"af_real:  {af_real}")
print(f"sztok:    {sztok[:60]}\n")

tests = [
    ("A. tanpa header", {}),
    ("B. ri PALSU", {"x-sap-ri": mk_ri()}),
    ("C. ri ASLI", {"x-sap-ri": ri_real}),
    ("D. LENGKAP asli", {"x-sap-ri": ri_real, "x-sap-sec": sec_real,
                         "af-ac-enc-dat": af_real,
                         "af-ac-enc-sz-token": sztok,
                         "x-sz-sdk-version": "1.12.45"}),
    ("E. ri asli + af random", {"x-sap-ri": ri_real,
                                "af-ac-enc-dat": secrets.token_hex(8),
                                "x-sz-sdk-version": "1.12.45"}),
    ("F. ri BARU (live)", {"x-sap-ri": mk_ri(int(time.time())),
                           "af-ac-enc-dat": secrets.token_hex(8),
                           "x-sz-sdk-version": "1.12.45"}),
]

for name, hd in tests:
    s, j = call(hd)
    e = j.get("error")
    print(f"{name:26s} HTTP={s} err={e}")
    time.sleep(1.2)

# kontrol: endpoint yang selama ini lolos
print("\n=== kontrol /search/search_prefills ===")
for name, hd in tests[:4]:
    s, j = call(hd, "/api/v4/search/search_prefills?keyword=x", body=None)
    print(f"{name:26s} HTTP={s} err={j.get('error')}")
    time.sleep(1.0)
