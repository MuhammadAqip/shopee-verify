# -*- coding: utf-8 -*-
"""fresh_ctx.py — FRESH CONTEXT: cookies TANPA jejak lama.

Yang DIBUANG (bawa flag crawler / device lama):
  _sapid, sense_sa_r, _QPWSDCXHZQA, _gcl_au, _fbp, fr, _ga, _ga_*, REC7iLP4Q,
  ssr-tz, SPC_F, SPC_SI (dobel!), SPC_SEC_SI

Yang DIPERTAHANKAN (auth saja):
  csrftoken, SPC_U, SPC_ST, SPC_R_T_ID, SPC_R_T_IV, SPC_T_ID, SPC_T_IV,
  SPC_CLIENTID, REC_T_ID

Lalu browser BERSIH: context baru, tanpa init_script fingerprint apa pun,
tanpa cookie device. Shopee akan generate _sapid/SPC_F/sense baru = device baru.
"""
import sys, json, ssl, urllib.request, urllib.error, urllib.parse

SRC = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_5th_solved.txt"
PW = sys.argv[2] if len(sys.argv) > 2 else "qwertyui123"
NEWPHONE = sys.argv[3] if len(sys.argv) > 3 else "6283191106499"

RAW = open(SRC).read().strip()
PAIRS = []
for p in RAW.split(";"):
    p = p.strip()
    if not p or "=" not in p:
        continue
    k, v = p.split("=", 1)
    PAIRS.append((k.strip(), v.strip()))

DROP = {"_sapid", "sense_sa_r", "_QPWSDCXHZQA", "_gcl_au", "_fbp", "fr",
        "_ga", "ssr-tz", "SPC_F", "SPC_SI", "SPC_SEC_SI", "REC7iLP4Q"}
KEEP = {"csrftoken", "SPC_U", "SPC_ST", "SPC_R_T_ID", "SPC_R_T_IV",
        "SPC_T_ID", "SPC_T_IV", "SPC_CLIENTID", "REC_T_ID"}

clean = {}
for k, v in PAIRS:
    if k in KEEP:
        clean[k] = v

print("=== cookie bersih ===")
for k in clean:
    print(f"   {k} = {clean[k][:40]}")
print(f"total: {len(clean)} (dari {len(PAIRS)})")

CK = "; ".join(f"{k}={v}" for k, v in clean.items())
open("/root/shopee-verify/ck_fresh.txt", "w").write(CK)
CSRF = clean.get("csrftoken", "")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"

_ct = ssl.create_default_context(); _ct.check_hostname = False
_ct.verify_mode = ssl.CERT_NONE
_OP = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}),
    urllib.request.HTTPSHandler(context=_ct))


def api(path, body=None, method="POST",
        ref="https://shopee.co.id/user/account/profile"):
    h = {"User-Agent": UA, "Cookie": CK, "Accept": "application/json",
         "x-api-source": "pc", "x-requested-with": "XMLHttpRequest",
         "x-shopee-language": "id", "Referer": ref, "x-csrftoken": CSRF,
         "Origin": "https://shopee.co.id"}
    d = None
    if body is not None:
        h["Content-Type"] = "application/json"; d = json.dumps(body).encode()
    r = urllib.request.Request("https://shopee.co.id" + path, data=d,
                               method=method, headers=h)
    try:
        with _OP.open(r, timeout=35) as x: return json.loads(x.read())
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read())
        except Exception: return {"http": e.code}
    except Exception as e: return {"err": str(e)[:80]}


print("\n=== tes auth dengan cookie bersih ===")
a = api("/api/v4/account/basic/get_account_info", None, "GET", "https://shopee.co.id/")
D = a.get("data") or {}
print(f"   account={a.get('error')} uid={D.get('userid')} user={D.get('username')} phone={repr(D.get('phone'))}")

print("\n=== tes cart/mini (indikator 90309999) ===")
c = api("/api/v4/cart/mini", {"version_list": [3145728, 65]})
print(f"   error={c.get('error')}")
six = c.get("6")
if isinstance(six, dict):
    print(f"   tid={str(six.get('0'))[:60]}")
