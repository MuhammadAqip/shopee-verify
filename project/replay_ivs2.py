# -*- coding: utf-8 -*-
"""replay_ivs2.py — diagnosa mendalam: apakah 49900000 dari signature atau body?"""
import sys, json
sys.path.insert(0, "/root/shopee-verify")
import replay_ivs as R


def show(lbl, path, body, hdr=None):
    st, r = R.post(path, body, hdr)
    e = r.get("error")
    print(f"{lbl:44} HTTP {st} error={e}")
    return r


FULL = R.FULL_HDR
NOHDR = {}

print("=== Baseline: endpoint yang JALAN tanpa header ===")
show("change_phone_init_v2 (no hdr)", "/api/v4/account/management/change_phone_init_v2", {})
show("init_v2 + FULL hdr", "/api/v4/account/management/change_phone_init_v2", {}, FULL)

print("\n=== /anti_fraud/* berlapis ===")
show("ivs/methods (no hdr)", "/api/v4/anti_fraud/ivs/methods", {})
show("ivs/methods (FULL)", "/api/v4/anti_fraud/ivs/methods", {}, FULL)
show("ivs/method/select (FULL)", "/api/v4/anti_fraud/ivs/method/select",
     {"type": 2, "v_token": "x"}, FULL)
show("ivs/token/verify (FULL)", "/api/v4/anti_fraud/ivs/token/verify", {}, FULL)

print("\n=== POST vs GET pada ivs/methods ===")
import urllib.request
for m in ("POST", "GET", "PUT"):
    h = dict(FULL)
    h.update({"User-Agent": R.UA, "Cookie": R.JAR, "Accept": "application/json",
              "x-api-source": "pc", "x-requested-with": "XMLHttpRequest",
              "x-csrftoken": R.CSRF, "x-shopee-language": "id"})
    data = b"{}" if m != "GET" else None
    req = urllib.request.Request(
        "https://shopee.co.id/api/v4/anti_fraud/ivs/methods",
        data=data, method=m, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            print(f"  {m:5}: HTTP {resp.status} {resp.read()[:120]}")
    except urllib.error.HTTPError as e:
        print(f"  {m:5}: HTTP {e.code} {e.read()[:120]}")
    except Exception as e:
        print(f"  {m:5}: EXC {e}")
