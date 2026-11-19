# -*- coding: utf-8 -*-
"""test_full_body.py — uji ivs/token/verify dengan BODY LENGKAP dari DevTools.

Body: method_name, event, u_token, r_token, v_token, misc.operation,
      security_device_fingerprint
"""
import sys, json, urllib.request, urllib.error
sys.path.insert(0, "/root/shopee-verify")
from change_phone_engine import parse_cookie

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

COOKIE_RAW = (
    "csrftoken=REDACTED; "
    "SPC_x=[REDACTED]; "
    "SPC_X=REDACTED; SPC_x=[REDACTED]; "
    "REC_T_ID=03f463ba-e11b-11f1-a4bb-aecc58483425; "
    "SPC_x=[REDACTED]==.AOTlH1W5fwg2BZWWz5TGkiFgRCPqRMUnSWEn0MEsqiju; "
    "SPC_x=[REDACTED]=; "
    "SPC_x=[REDACTED]=; "
    "shopee_webUnique_ccd=GY79LnMyc2KEKSGbyDqBgw%3D%3D%7CJug49U3W1roGbiRxUvnTZhE1jIfn5rMo1KqYS8bDuDlEdh%2BoEKI88kN0ZdWx%2B%2FKXwVNBjg%2BFi3zduA%3D%3D%7CHnenNBFFdeCzJK%2Fa%7C08%7C3; "
    "language=id; ssr-tz=Asia/Jakarta; "
    "AC_CERT_D=gqRjZGVrxHeFomtpuDE0MjUxOmNhcHRjaGFfY29va2llX2tleaJrdtEAAqRhbGdv0gAAAGSjZGVrwKJjdMRAAAAADGwl7dJF/SbJKL341oEJflWzNSQXdheVEX19MTNYOhLoa8WxYWzVFxowNBFlHR88Zx5e9diMU0FYCSU8L6pjaXBoZXJ0ZXh0xQMxAAAADH112Y2pBPWSAQw3AdMusaegaB8ulHXG3VvbTOCzlJpX2V1HS5lXcvgkiA4FUFMAR/MOUaqcg9+NvcImxuNxU/slPDSuy6GtReLKKwgqDkvnfvzYiqDgMa4qIXtCx56IoOekU1e/t8KR9xnT8jR+30RAONWacmwT9Er6qSPlNBSH1eK4khTJi2gz82lkbxa/l5vFtm/XiUTdSMOzNL7yLEPHw3uR1n/hDQjbsu4YnFLBu5FXLEatQTL/QV9ouia0/uiC+j+lbGOpUmEegmxeeAuzlGEC2NWnYjhwpJoCZLJ1uXgIc98drZLdIXowGm2dELaX3votV1yGnUiocU01BnXLsglSYXCxSHJRD0lHUz+0M4pipT5bN8XxivY1DPwoqObZ4Q/FP6Xi9JJ1n7yJaUukYG5y8S3/ln8OOwXfBh5wgF2SSDc9PBl76Mv3j7A2r6XtsJJvgdabre4aH4lilZBvN5sIj72RzzIosoQMnDRosVYclKwKZ60MfXNQCnNonbymZpV3KukXCZYbT6AGm6IPPbKUxa8/QVeuZaSIpKlNMzyJ2Z8dTMsjT/U2xVrumAmG0dkYWf9JZDAQnEG729Gs1LE9LZXkpP/7YqsOqL3AH8uHRw406omXA6HB3ywCAulcJCaZY0SzpYdWYJL67gvlrGjA3bEJI7CybER7/nimP/AJOM8q7iVcuHLrVkfRQH6/qhVhLyY5YpTe1OQ1AaiYeIZphwT5QAvF1iaLTFUYPPaltA3Zd5nvD2q0sQ8qU3MbDAivFP98fwj3E4LbyzsVHOqhCFy0nshkCM3rRB/1qwg2sAZ9jqZFMT69Qda8YbaJtEBfdJFmpscSpZDXoxUsiPX4ASZhotkzqlgeYZhJ2kjqEBeq5Yd+6sIpSk5EXxIkIsX/VCUX/s8JqcKd5xk6F3c6PwToYkVbRCmZyUxPWe02vUWt1tE1nw5fHu2V/LIHqSf5rmYoY2HhX95tK/w4NWMJmoCvk1aCvOmJoGL5hed7+T5jRxAalHsV9bdxWRXNiNhRlAX7aVVXVRQFZLTdSyz33UI7VN1H7n5hrwcHVU6lLqM08tl2e1ctxQ=="
)
CSRF = "bb5f05881379dd5d0759d8dc9a12b0fe"

U_TOKEN = ("U2FsdGVkX19dU0IYqsh7w1i1Gz9xfxYgaGrwqF4rVYezciEaHxyTeJFAt/HXSbx0wx2YCuxvzjTT9D51smlVeSIQP1tGL10AEa8qVt4ozgmcz3CXu2bIJLwPjBaf9uTF/GTO/pDTXK2UUuckcW55s/v3LI45J0+BKTQeEvGErr+HfNfnQHNDtJ4Vbxv+NIpnneVKmUiob9fmF8z3tquYqpfIXQiJSRf6+vjIUvD7+zR8nYq0PWGsHtfeKrx9NmltiKkRKoBHWBMrxhhfelwwi5dj92DzNtY1FP5XYU0PQBFLj0E7Ft9SlguTRgvgDvqU1EXJZVNPDQ1R0u6ZFxjsWMnEnigGI7Hv86RF+JIksjEAI3gWJbNKyiq1SpxiIKjyx7074DT3fCelubK18CeRVPKUr/hiTmUeFNfMmoCaEqyapr2nulE4LVI+CN1jrRu6p5kpIac9zEvnCnwB9yVZ5g==")
R_TOKEN = "EJOg4LVkAEmfNNGQ3tClawGlu3QE+/d4ZvG7CJQQgMlG9XOW5qiLi4ZWrLpWZLsRLeX3MsyNKfSyn/xtkg5MCPE3DbqZtCIJx2PlSJ4d1ocFqWKM3/epaJiu/h2kr4914KmefPhWUL4yX8sQUKnmZyQ/HWWvaRB8tWX8PABk2WSuxsxSnQexImdk3zuF"
V_TOKEN = "EeEPg5u9gxsQJeghn/1I10Zav+9k1f+nnx8QvJt0cZbl+y4TCpHkTyDv1EVsPJMepUy68orjoVp6Fjvef//39VHx4VlqZqvJLL1Z"
FP = "GY79LnMyc2KEKSGbyDqBgw==|Jug49U3W1roGbiRxUvnTZhE1jIfn5rMo1KqYS8bDuDlEdh+oEKI88kN0ZdWx+/KXwVNBjg+Fi3zduA==|HnenNBFFdeCzJK/a|08|3"


def post(path, body, extra=None):
    h = {"User-Agent": UA, "Cookie": COOKIE_RAW,
         "Content-Type": "application/json", "Accept": "application/json",
         "x-api-source": "pc", "x-requested-with": "XMLHttpRequest",
         "x-csrftoken": CSRF, "x-shopee-language": "id",
         "Referer": "https://shopee.co.id/verify/ivs"}
    if extra:
        h.update(extra)
    req = urllib.request.Request("https://shopee.co.id" + path,
                                 data=json.dumps(body).encode(),
                                 method="POST", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b)
        except Exception:
            return e.code, {"raw": b[:200].decode(errors="ignore")}
    except Exception as e:
        return 0, {"err": str(e)}


BODY = {
    "method_name": 2,
    "event": 2,
    "u_token": U_TOKEN,
    "r_token": R_TOKEN,
    "v_token": V_TOKEN,
    "misc": {"operation": 0},
    "security_device_fingerprint": FP,
}

print("=== 1. change_phone_init_v2 (verifikasi cookie baru) ===")
st, r = post("/api/v4/account/management/change_phone_init_v2", {})
print(f"HTTP {st} error={r.get('error')}")
if r.get("error") == 0:
    d = r["data"]
    print(f"  token: {str(d.get('change_phone_token'))[:40]}…")
    print(f"  ivs_required: {d.get('ivs_required')}")

print("\n=== 2. ivs/token/verify — BODY LENGKAP ===")
st, r = post("/api/v4/anti_fraud/ivs/token/verify", BODY)
print(f"HTTP {st}")
print(json.dumps(r, ensure_ascii=False)[:600])

print("\n=== 3. ivs/token/verify + x-sap-sec header ===")
HDR = {"x-sap-ri": "3f57fd6a6b4bf9697b50783a1601e6874343eba488d730aa8b1e",
       "af-ac-enc-dat": "ba7d4a9ed67b8641",
       "af-ac-enc-sz-token": "GY79LnMyc2KEKSGbyDqBgw==|Jug49U3W1roGbiRxUvnTZhE1jIfn5rMo1KqYS8bDuDlEdh+oEKI88kN0ZdWx+/KXwVNBjg+Fi3zduA==|HnenNBFFdeCzJK/a|08|3",
       "x-sz-sdk-version": "1.12.45"}
st, r = post("/api/v4/anti_fraud/ivs/token/verify", BODY, HDR)
print(f"HTTP {st}")
print(json.dumps(r, ensure_ascii=False)[:400])
