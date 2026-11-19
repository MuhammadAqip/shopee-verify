# -*- coding: utf-8 -*-
"""v2_flow.py — flow change_phone V2 (yang aktif). Tanpa proxy."""
import sys, json, urllib.request, urllib.error
sys.path.insert(0, "/root/shopee-verify")
from change_phone_engine import parse_cookie

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
CK = parse_cookie(open("/root/shopee-verify/ck_test.txt").read().strip())
JAR = "; ".join(f"{c['name']}={c['value']}" for c in CK)
CSRF = next((c["value"] for c in CK if c["name"] == "csrftoken"), "")
FP = "a1b2c3d4e5f60718293a4b5c6d7e8f90"   # fingerprint stabil


def api(path, body=None, headers_extra=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"User-Agent": UA, "Cookie": JAR, "Content-Type": "application/json",
         "x-api-source": "pc", "x-requested-with": "XMLHttpRequest",
         "x-csrftoken": CSRF, "x-shopee-language": "id",
         "Referer": "https://shopee.co.id/user/account/profile",
         "Accept": "application/json"}
    if headers_extra:
        h.update(headers_extra)
    req = urllib.request.Request("https://shopee.co.id" + path, data=data,
                                 method="POST" if data else "GET", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "body": e.read()[:300].decode(errors="ignore")}
    except Exception as e:
        return {"err": str(e)}


print("=== change_phone_init_v2 ===")
r = api("/api/v4/account/management/change_phone_init_v2", {})
print(json.dumps(r, indent=2, ensure_ascii=False)[:600])
d = r.get("data") or {}
tok = d.get("change_phone_token")
print("\nchange_phone_token:", bool(tok), "fields:", list(d.keys()))

if tok:
    print("\n=== precheck_v2 ===")
    print(json.dumps(api("/api/v4/account/management/change_phone_precheck_v2",
                         {"phone": "6285876130683"}), ensure_ascii=False)[:200])
    print("\n=== otp/get_settings_v2 ===")
    print(json.dumps(api("/api/v4/otp/get_settings_v2",
                         {"operation": 0, "phone": "6285876130683",
                          "supported_channels": [1, 2], "support_session": False}),
                     ensure_ascii=False)[:250])
    print("\n=== otp/send_vcode ===")
    print(json.dumps(api("/api/v4/otp/send_vcode",
                         {"phone": "6285876130683", "channel": 1, "operation": 0,
                          "force_channel": False, "supported_channels": [1]}),
                     ensure_ascii=False)[:300])
