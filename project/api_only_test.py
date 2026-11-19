# -*- coding: utf-8 -*-
"""api_only_test.py — uji endpoint change_phone via API murni dari IP VPS.

Halaman /user/account/profile kena captcha, TAPI endpoint API-nya
masih bisa dipanggil dengan cookie yang sama + csrftoken.
"""
import sys, json, urllib.request, hashlib
sys.path.insert(0, "/root/shopee-verify")
from change_phone_engine import parse_cookie

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
CK = parse_cookie(open("/root/shopee-verify/ck_test.txt").read().strip())
JAR = "; ".join(f"{c['name']}={c['value']}" for c in CK)
CSRF = next((c["value"] for c in CK if c["name"] == "csrftoken"), "")


def api(path, body=None, method=None):
    url = "https://shopee.co.id" + path
    data = json.dumps(body).encode() if body is not None else None
    m = method or ("POST" if data else "GET")
    req = urllib.request.Request(url, data=data, method=m, headers={
        "User-Agent": UA, "Cookie": JAR, "Content-Type": "application/json",
        "x-api-source": "pc", "x-requested-with": "XMLHttpRequest",
        "x-csrftoken": CSRF, "x-shopee-language": "id",
        "Referer": "https://shopee.co.id/user/account/profile",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "body": e.read()[:200].decode(errors="ignore")}
    except Exception as e:
        return {"err": str(e)}


print("=== 1. account_info ===")
print(json.dumps(api("/api/v4/account/basic/get_account_info"), ensure_ascii=False)[:200])

print("\n=== 2. change_phone_init ===")
r = api("/api/v4/account/management/change_phone_init", {})
print(json.dumps(r, ensure_ascii=False)[:300])
seq = (r.get("data") or {}).get("seq_no") or r.get("seq_no")
print("seq_no:", seq)

if seq:
    print("\n=== 3. get_password_verify_method ===")
    print(json.dumps(api(f"/api/v4/account/management/get_password_verify_method?seq_no={seq}&scenario=1"),
                     ensure_ascii=False)[:250])

    print("\n=== 4. change_phone_precheck_v2 (6285876130683) ===")
    print(json.dumps(api("/api/v4/account/management/change_phone_precheck_v2",
                         {"phone": "6285876130683"}), ensure_ascii=False)[:250])

    print("\n=== 5. otp/get_settings_v2 ===")
    print(json.dumps(api("/api/v4/otp/get_settings_v2",
                         {"operation": 0, "phone": "6285876130683",
                          "supported_channels": [1, 2], "support_session": False}),
                     ensure_ascii=False)[:300])

print("\n=== 6. verify_payment_commit (sha256(md5)) ===")
seq2 = (api("/api/v4/account/management/change_phone_init", {}).get("data") or {}).get("seq_no")
pw = "qwertyui123"
ans = hashlib.sha256(hashlib.md5(pw.encode()).hexdigest().encode()).hexdigest()
for lbl, body in [
    ("answer only", {"seq_no": seq2, "answer": ans, "scenario": 1}),
    ("+identity", {"seq_no": seq2, "answer": ans, "scenario": 1, "identity_token": seq2}),
    ("GET init", None),
]:
    if body is None:
        print(f"  {lbl}:", json.dumps(api(f"/api/v4/account/management/verify_payment_init?seq_no={seq2}&scenario=1"), ensure_ascii=False)[:200])
    else:
        print(f"  {lbl}:", json.dumps(api("/api/v4/account/management/verify_payment_commit", body), ensure_ascii=False)[:220])
