# -*- coding: utf-8 -*-
import sys, json, urllib.request, urllib.error
sys.path.insert(0, "/root/shopee-verify")
from change_phone_engine import parse_cookie

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
CK = parse_cookie(open("/root/shopee-verify/ck_test.txt").read().strip())
JAR = "; ".join(f"{c['name']}={c['value']}" for c in CK)
CSRF = next((c["value"] for c in CK if c["name"] == "csrftoken"), "")


def api(path, body=None, extra=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"User-Agent": UA, "Cookie": JAR, "Content-Type": "application/json",
         "x-api-source": "pc", "x-requested-with": "XMLHttpRequest",
         "x-csrftoken": CSRF, "x-shopee-language": "id",
         "Referer": "https://shopee.co.id/user/account/profile",
         "Accept": "application/json"}
    if extra:
        h.update(extra)
    req = urllib.request.Request("https://shopee.co.id" + path, data=data,
                                 method="POST" if data else "GET", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "body": e.read()[:300].decode(errors="ignore")}
    except Exception as e:
        return {"err": str(e)}


print("=== change_phone_init FULL ===")
r = api("/api/v4/account/management/change_phone_init", {})
print(json.dumps(r, indent=2, ensure_ascii=False))

d = r.get("data") or {}
seq = d.get("seq_no")
print("\nfields:", list(d.keys()))

if seq:
    print("\n=== get_challenge / ivs 相关 ===")
    for p in ["/api/v4/account/management/get_change_phone_info",
              "/api/v4/account/management/get_change_phone_status",
              f"/api/v4/account/management/get_ivs_flow?seq_no={seq}",
              f"/api/v4/account/management/get_verify_method?seq_no={seq}&scenario=1"]:
        print(" ", p.split("/")[-1], "->", json.dumps(api(p), ensure_ascii=False)[:150])
