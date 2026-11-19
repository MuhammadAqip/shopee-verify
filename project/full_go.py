# -*- coding: utf-8 -*-
"""full_go.py — FLOW LENGKAP dengan cookie Maker, lewat PROXY (bukan direct).

Bukti dari probe_gate.py: IP VPS = flag, proxy = bersih.
Semua request lewat proxy:18080. Cookie Maker dipakai apa adanya.
"""
import sys, json, hashlib, urllib.request, urllib.error, urllib.parse, ssl

PHONE = "6285736070693"
PW = "qwertyui123"
CK_FILE = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_1553.txt"
CK = open(CK_FILE).read().strip()
CSRF = next((c.split("=", 1)[1] for c in CK.split(";")
             if c.strip().startswith("csrftoken=")), "")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
BASE = "https://shopee.co.id"
PROXY = "http://127.0.0.1:18080"

opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
opener.add_handler(urllib.request.HTTPSHandler(context=ctx))


def req(path, body=None, method="POST",
        ref="https://shopee.co.id/verify/ivs", extra=None):
    h = {"User-Agent": UA, "Cookie": CK, "Accept": "application/json",
         "Accept-Language": "en-US,en;q=0.9",
         "x-api-source": "pc", "x-app-type": "undefined",
         "x-requested-with": "XMLHttpRequest",
         "x-shopee-language": "id", "Referer": ref,
         "Origin": "https://shopee.co.id"}
    if CSRF:
        h["x-csrftoken"] = CSRF
    if extra:
        h.update(extra)
    data = None
    if body is not None:
        h["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        with opener.open(r, timeout=35) as x:
            return json.loads(x.read())
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read())
        except Exception: return {"http": e.code}
    except Exception as e:
        return {"err": str(e)[:100]}


def show(t, r, n=200):
    print(f"{t}: {json.dumps(r, ensure_ascii=False)[:n]}")
    return r


print(f"cookie: {CK_FILE}  csrf={'ada' if CSRF else 'TIDAK'}")
print(f"proxy : {PROXY}\n")

print("=== 0. account (GET) ===")
acc = req("/api/v4/account/basic/get_account_info", None, "GET",
          ref="https://shopee.co.id/")
show("account", acc, 150)
if acc.get("error") != 0:
    print(">> cookie mati, stop"); sys.exit(1)

print("\n=== 1. init_v2 ===")
r1 = req("/api/v4/account/management/change_phone_init_v2", {},
         ref="https://shopee.co.id/user/account/profile")
show("init", r1)
d1 = r1.get("data") or {}
cp, ut = d1.get("change_phone_token"), d1.get("ivs_utoken")
if not cp:
    sys.exit("init gagal")

print("\n=== 2. ivs/methods {event:2,u_token} ===")
r2 = req("/api/v4/anti_fraud/ivs/methods", {"event": 2, "u_token": ut})
ms = r2.get("data") or []
show("methods", r2, 120)
if not ms:
    sys.exit("methods gagal")
for m in ms:
    print(f"   type={m['type']} len={len(m['v_token'])}")

print("\n=== 3. ivs/method/select (type=2) ===")
pick = next((x for x in ms if x["type"] == 2), ms[0])
st = req("/api/v4/anti_fraud/ivs/method/select",
         {"method_name": pick["type"], "event": 2, "u_token": ut,
          "v_token": pick["v_token"], "misc": {"operation": 0}})
show("select", st, 180)

print("\n=== 4. verify_password ===")
ph = hashlib.sha256(hashlib.md5(PW.encode()).hexdigest().encode()).hexdigest()
r4 = req("/api/v4/account/management/verify_password", {"password": ph},
         ref="https://shopee.co.id/user/account/profile")
rt = (r4.get("data") or {}).get("rc_token")
show("password", r4, 100)
if not rt:
    sys.exit("password gagal")

print("\n=== 5. ivs/token/verify ===")
sig = None
for m in ([pick] + [x for x in ms if x is not pick]):
    body = {"method_name": m["type"], "event": 2, "u_token": ut,
            "r_token": rt, "v_token": m["v_token"],
            "shopee_df": {"security_device_fingerprint": ""},
            "misc": {"seed": None, "operation": 0}}
    r5 = req("/api/v4/anti_fraud/ivs/token/verify", body)
    e = r5.get("error")
    print(f"   type={m['type']}: error={e} sig={bool(r5.get('signature'))}")
    if e == 0 and r5.get("signature"):
        sig = r5["signature"]
        print("   ✅ SIGNATURE:", sig[:60], "…")
        json.dump({"type": m["type"], "signature": sig, "cp": cp, "ut": ut,
                   "rt": rt, "v_token": m["v_token"]},
                  open("/root/shopee-verify/READY.json", "w"))
        break
if not sig:
    sys.exit("ivs verify gagal")

print("\n=== 6. precheck_v2 ===")
r6 = req("/api/v4/account/management/change_phone_precheck_v2",
         {"new_phone": PHONE, "change_phone_token": cp},
         ref="https://shopee.co.id/user/account/profile")
show("precheck", r6)

print("\n=== 7. otp/get_settings_v2 ===")
r7 = req("/api/v4/otp/get_settings_v2", {"operation": 0, "phone": PHONE},
         ref="https://shopee.co.id/user/account/profile")
show("channels", r7)
ch = (r7.get("data") or {}).get("available_channels") or []
print("   available_channels:", ch)
open("/root/shopee-verify/CHANNELS.txt", "w").write(json.dumps(ch))
