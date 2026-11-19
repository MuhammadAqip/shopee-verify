# -*- coding: utf-8 -*-
"""cp_hdr.py — flow change_phone LENGKAP dengan HEADER x-sap asli.

Insight: header LENGKAP bikin HTTP 403 → 200. Gate anti-bot lolos.
Sekarang jalankan flow penuh dan lihat apakah token/verify juga lolos.

Steps:
  1. change_phone_init          -> seq_no
  2. change_phone_init_v2       -> ivs_utoken, change_phone_token
  3. ivs/methods event=2        -> list metode
  4. ivs/method/select          -> pilih password (2)
  5. verify_password            -> rc_token
  6. ivs/token/verify           -> SIGNATURE  <-- target utama
  7. change_phone_precheck_v2
  8. otp/get_settings_v2
  9. otp/send_vcode
"""
import json, sys, time, secrets, hashlib, urllib.request, urllib.error

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1553.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283191104601"
PASSWORD = sys.argv[3] if len(sys.argv) > 3 else "qwertyui123"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
M = "/api/v4/account/management"

ck = open(CK).read().strip()
CSRF = ""
for p in ck.split(";"):
    if p.strip().startswith("csrftoken="):
        CSRF = p.split("=", 1)[1].strip()

cap = json.load(open("aes_pairs.json"))
HD = {h["k"]: h["v"] for h in cap["hdr"] if h.get("v")}
RI = HD.get("x-sap-ri", "")
SEC = HD.get("x-sap-sec", "")
SZTOK = HD.get("af-ac-enc-sz-token", "")


def mk_ri():
    return (int(time.time()).to_bytes(4, "little").hex()
            + secrets.token_hex(8) + "1601" + secrets.token_hex(12))


def call(path, body=None, method=None):
    h = {"Cookie": ck, "User-Agent": UA, "X-API-SOURCE": "pc",
         "X-Requested-With": "XMLHttpRequest",
         "Referer": "https://shopee.co.id/user/account/settings",
         "Accept": "application/json", "X-CSRFToken": CSRF,
         "X-Shopee-Language": "id",
         "x-sap-ri": mk_ri(), "x-sap-sec": SEC,
         "af-ac-enc-dat": secrets.token_hex(8),
         "af-ac-enc-sz-token": SZTOK, "x-sz-sdk-version": "1.12.45"}
    d = None
    if body is not None:
        h["Content-Type"] = "application/json"
        d = json.dumps(body).encode()
    m = method or ("POST" if d is not None else "GET")
    req = urllib.request.Request("https://shopee.co.id" + path, data=d,
                                 headers=h, method=m)
    try:
        r = urllib.request.urlopen(req, timeout=45)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}
    except Exception as ex:
        return 0, {"exc": str(ex)[:60]}


def log(*a):
    print(*a, flush=True)


log(f"=== FULL FLOW HEADER LENGKAP — {CK} → {NEWPHONE} ===\n")

# 1
s, j = call(f"{M}/change_phone_init", {})
SEQ = (j.get("data") or {}).get("seq_no")
AUTH = (j.get("data") or {}).get("auth_required")
log(f"[1] init      {s} err={j.get('error')} seq={SEQ} auth={AUTH}")

# 2
s, j2 = call(f"{M}/change_phone_init_v2", {})
D2 = j2.get("data") or {}
UT = D2.get("ivs_utoken") or ""
CPT = D2.get("change_phone_token") or ""
log(f"[2] init_v2   {s} err={j2.get('error')} ut={len(UT)}B cp={len(CPT)}B "
    f"ivs_req={D2.get('ivs_required')}")

# 3
s, j3 = call("/api/v4/anti_fraud/ivs/methods", {"event": 2, "u_token": UT})
_d3 = j3.get("data")
MS = _d3 if isinstance(_d3, list) else ((_d3 or {}).get("methods") or [])
log(f"[3] methods   {s} err={j3.get('error')} n={len(MS)} "
    f"{[(m.get('type'), len(m.get('v_token',''))) for m in MS]}")

VT = ""
SIG = None
for m in sorted(MS, key=lambda x: 0 if x.get("type") == 2 else 1):
    mt = m.get("type")
    VT = m.get("v_token", "")
    s, js = call("/api/v4/anti_fraud/ivs/method/select",
                 {"v_token": VT, "method": mt, "event": 2, "u_token": UT})
    log(f"[4] select t={mt}  err={js.get('error')} {str(js.get('data'))[:80]}")
    if js.get("error") != 0:
        continue

    # 5 verify_password
    ph = hashlib.sha256(hashlib.md5(PASSWORD.encode()).hexdigest().encode()).hexdigest()
    s, jv = call("/api/v4/anti_fraud/ivs/verify_password",
                 {"password": ph, "method": 2, "event": 2, "u_token": UT})
    RTC = (jv.get("data") or {}).get("rc_token") or ""
    log(f"[5] verpass   err={jv.get('error')} rtc={len(RTC)}B")

    # 6 token/verify (TARGET)
    body = {"method": mt, "event": 2, "u_token": UT, "v_token": VT,
            "r_token": RTC, "shopee_df": "", "misc": {"seed": "", "operation": 0}}
    s, jt = call("/api/v4/anti_fraud/ivs/token/verify", body)
    SIG = (jt.get("data") or {}).get("signature")
    log(f"[6] token/vfy err={jt.get('error')} sig={'✅ %dB' % len(SIG) if SIG else 'N'}")
    if SIG:
        break
    time.sleep(0.8)

if not SIG:
    log("\n❌ token/verify masih gagal")
    sys.exit(1)

# 7-9
s, jp = call(f"{M}/change_phone_precheck_v2",
             {"change_phone_token": CPT, "new_phone": NEWPHONE,
              "ivs_signature": SIG, "ivs_method": 2})
log(f"\n[7] precheck  err={jp.get('error')} {str(jp.get('data'))[:160]}")

s, jo = call("/api/v4/otp/get_settings_v2",
             {"operation": 0, "change_phone_token": CPT})
log(f"[8] settings  err={jo.get('error')} {str(jo.get('data'))[:160]}")

s, jo2 = call("/api/v4/otp/send_vcode",
              {"phone": NEWPHONE, "channel": 1, "operation": 0,
               "force_channel": False, "supported_channels": [1], "seed": ""})
log(f"[9] send_vcode err={jo2.get('error')} {str(jo2.get('data'))[:160]}")

json.dump({"seq": SEQ, "ut": UT, "cpt": CPT, "sig": SIG,
           "precheck": jp, "send": jo2}, open("cp_hdr_state.json", "w"), indent=1)
log("\n=== SELESAI ===")
