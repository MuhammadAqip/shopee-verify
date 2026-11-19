"""ck_alive.py — cek semua cookie, mana yang masih hidup.

error 19 = Failed to authenticate = cookie mati.
error 0  = hidup.
"""
import sys, json, glob
import requests

PROXY = "http://127.0.0.1:18080"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

files = sorted(glob.glob("/root/shopee-verify/ck_*.txt"))
seen = {}
print(f"cek {len(files)} file\n")
for f in files:
    try:
        ck = open(f).read().strip()
    except Exception:
        continue
    if not ck or "=" not in ck:
        continue
    cookies = {p.split("=", 1)[0].strip(): p.split("=", 1)[1].strip()
               for p in ck.split(";") if "=" in p}
    uid = cookies.get("SPC_U", "")
    if uid in seen:
        continue
    s = requests.Session()
    s.cookies.update(cookies)
    s.proxies = {"http": PROXY, "https": PROXY}
    s.headers.update({"user-agent": UA, "x-api-source": "pc",
                      "x-requested-with": "XMLHttpRequest",
                      "referer": "https://shopee.co.id/",
                      "accept": "application/json"})
    try:
        r = s.get("https://shopee.co.id/api/v4/account/basic/get_account_info",
                  timeout=30)
        j = r.json()
        err = j.get("error")
        uname = (j.get("data") or {}).get("username", "")
        status = "ALIVE" if err == 0 else f"DEAD({err})"
    except Exception as e:
        err, uname, status = "EXC", "", f"ERR({str(e)[:20]})"
    seen[uid] = status
    mark = "✅" if err == 0 else "  "
    print(f"{mark} {f.split('/')[-1]:24s} uid={uid:14s} {status:12s} {uname}")

print("\n=== ALIVE ===")
for u, st in seen.items():
    if st == "ALIVE":
        print(f"  {u}")
