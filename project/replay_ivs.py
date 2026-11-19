# -*- coding: utf-8 -*-
"""replay_ivs.py — uji apakah header x-sap-sec bisa di-replay dari Python."""
import sys, json
sys.path.insert(0, "/root/shopee-verify")
from change_phone_engine import parse_cookie
import urllib.request, urllib.error

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
CK = parse_cookie(open("/root/shopee-verify/ck_test.txt").read().strip())
JAR = "; ".join(f"{c['name']}={c['value']}" for c in CK)
CSRF = "bb5f05881379dd5d0759d8dc9a12b0fe"

SZ_TOKEN = ("GY79LnMyc2KEKSGbyDqBgw==|Jug49U3W1roGbiRxUvnTZhE1jIfn5rMo1KqYS8bDuDlEdh+oEKI88kN0ZdWx+/KXwVNBjg+Fi3zduA==|HnenNBFFdeCzJK/a|08|3")
SAP_RI = "3f57fd6a6b4bf9697b50783a1601e6874343eba488d730aa8b1e"
SAP_SEC = ("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")


def post(path, body, headers=None):
    h = {"User-Agent": UA, "Cookie": JAR, "Content-Type": "application/json",
         "Accept": "application/json", "x-api-source": "pc",
         "x-requested-with": "XMLHttpRequest", "x-csrftoken": CSRF,
         "x-shopee-language": "id",
         "Referer": "https://shopee.co.id/user/account/profile"}
    if headers:
        h.update(headers)
    data = json.dumps(body).encode()
    req = urllib.request.Request("https://shopee.co.id" + path,
                                 data=data, method="POST", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {"raw": "unparseable"}
    except Exception as e:
        return 0, {"err": str(e)}


FULL_HDR = {
    "x-sap-ri": SAP_RI,
    "x-sap-sec": SAP_SEC,
    "af-ac-enc-sz-token": SZ_TOKEN,
    "x-sz-sdk-version": "1.12.45",
    "x-app-type": "undefined",
}

print("=== A. ivs/methods + header lengkap ===")
st, r = post("/api/v4/anti_fraud/ivs/methods", {}, FULL_HDR)
print(f"HTTP {st}: {json.dumps(r, ensure_ascii=False)[:300]}")

print("\n=== B. ivs/token/verify + header lengkap ===")
st, r = post("/api/v4/anti_fraud/ivs/token/verify", {}, FULL_HDR)
print(f"HTTP {st}: {json.dumps(r, ensure_ascii=False)[:300]}")
