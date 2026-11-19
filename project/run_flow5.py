# -*- coding: utf-8 -*-
"""run_flow5.py — uji IVS VERIFY memakai PASANGAN token dari sesi yang sama
(u_token, r_token, v_token harus dari satu sesi akun).

Cookie ck_1533 = akun 15330433233 (sama dengan sesi DevTools Maker).
v_token DevTools diambil dari akun itu juga.
"""
import sys, json, hashlib, urllib.request, urllib.error
sys.path.insert(0, "/root/shopee-verify")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
FP = ("GY79LnMyc2KEKSGbyDqBgw==|Jug49U3W1roGbiRxUvnTZhE1jIfn5rMo1KqYS8bDuDlEd"
      "h+oEKI88kN0ZdWx+/KXwVNBjg+Fi3zduA==|HnenNBFFdeCzJK/a|08|3")

COOKIE = open("/root/shopee-verify/ck_1533.txt").read().strip()
CSRF = "bb5f05881379dd5d0759d8dc9a12b0fe"

V_TOKEN = ("EeEPg5u9gxsQJeghn/1I10Zav+9k1f+nnx8QvJt0cZbl+y4TCpHkTyDv1EVsPJMepUy"
           "68orjoVp6Fjvef//39VHx4VlqZqvJLL1Z")
U_TOKEN_DT = ("U2FsdGVkX19dU0IYqsh7w1i1Gz9xfxYgaGrwqF4rVYezciEaHxyTeJFAt/HXSbx0wx2YC"
              "uxvzjTT9D51smlVeSIQP1tGL10AEa8qVt4ozgmcz3CXu2bIJLwPjBaf9uTF/GTO/pDTXK2UU"
              "uckcW55s/v3LI45J0+BKTQeEvGErr+HfNfnQHNDtJ4Vbxv+NIpnneVKmUiob9fmF8z3tquYqp"
              "fIXQiJSRf6+vjIUvD7+zR8nYq0PWGsHtfeKrx9NmltiKkRKoBHWBMrxhhfelwwi5dj92DzNt"
              "Y1FP5XYU0PQBFLj0E7Ft9SlguTRgvgDvqU1EXJZVNPDQ1R0u6ZFxjsWMnEnigGI7Hv86RF+J"
              "IksjEAI3gWJbNKyiq1SpxiIKjyx7074DT3fCelubK18CeRVPKUr/hiTmUeFNfMmoCaEqyapr"
              "2nulE4LVI+CN1jrRu6p5kpIac9zEvnCnwB9yVZ5g==")
R_TOKEN_DT = ("EJOg4LVkAEmfNNGQ3tClawGlu3QE+/d4ZvG7CJQQgMlG9XOW5qiLi4ZWrLpWZLsRLeX3"
              "MsyNKfSyn/xtkg5MCPE3DbqZtCIJx2PlSJ4d1ocFqWKM3/epaJiu/h2kr4914KmefPhWUL"
              "4yX8sQUKnmZyQ/HWWvaRB8tWX8PABk2WSuxsxSnQexImdk3zuF")


def post(path, body, ref="https://shopee.co.id/verify/ivs"):
    h = {"User-Agent": UA, "Cookie": COOKIE,
         "Content-Type": "application/json", "Accept": "application/json",
         "x-api-source": "pc", "x-requested-with": "XMLHttpRequest",
         "x-csrftoken": CSRF, "x-shopee-language": "id", "Referer": ref}
    req = urllib.request.Request("https://shopee.co.id" + path,
                                 data=json.dumps(body).encode(),
                                 method="POST", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        b = e.read()
        try: return e.code, json.loads(b)
        except Exception: return e.code, {"raw": b[:200].decode(errors="ignore")}
    except Exception as e:
        return 0, {"err": str(e)}


print("=== A. Init baru untuk akun 15330433233 ===")
st, r = post("/api/v4/account/management/change_phone_init_v2", {},
             ref="https://shopee.co.id/user/account/profile")
print(f"HTTP {st} error={r.get('error')}")
d = r.get("data") or {}
print(f"  ivs_required={d.get('ivs_required')} u_token={bool(d.get('ivs_utoken'))}")
u_fresh = d.get("ivs_utoken")
cp_token = d.get("change_phone_token")

print("\n=== B. verify_password ===")
ans = hashlib.sha256(hashlib.md5(b"qwertyui123").hexdigest().encode()).hexdigest()
st, r = post("/api/v4/account/management/verify_password", {"password": ans},
             ref="https://shopee.co.id/user/account/profile")
d2 = r.get("data") or {}
print(f"HTTP {st} error={r.get('error')} r_token={bool(d2.get('rc_token'))}")
r_fresh = d2.get("rc_token")

# Coba 4 kombinasi: fresh/fresh, fresh/dt, dt/dt, dt/fresh
combos = [
    ("fresh u + fresh r", u_fresh, r_fresh),
    ("dt u + dt r (sesi DevTools penuh)", U_TOKEN_DT, R_TOKEN_DT),
    ("fresh u + dt r", u_fresh, R_TOKEN_DT),
    ("dt u + fresh r", U_TOKEN_DT, r_fresh),
]
for lbl, u, rt in combos:
    if not u or not rt:
        print(f"{lbl:36}: SKIP (token kosong)"); continue
    body = {"method_name": 2, "event": 2, "u_token": u, "r_token": rt,
            "v_token": V_TOKEN, "misc": {"operation": 0},
            "security_device_fingerprint": FP}
    st, r = post("/api/v4/anti_fraud/ivs/token/verify", body)
    e = r.get("error")
    sig = bool(r.get("signature"))
    print(f"{lbl:36}: HTTP {st} error={e} sig={sig}")
    if e == 0 and sig:
        print("   ✅ SIGNATURE:", r["signature"][:60], "…")
        break
