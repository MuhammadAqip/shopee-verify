# -*- coding: utf-8 -*-
"""cp_v3.py — flow change_phone dengan SKEMA ASLI token/verify.

Perbaikan dari bundle ivs_js/027.js + 026.js:
  body: {
    method_name: "Password"   <- STRING (bukan int!)
    event:       2
    u_token:     <ivs_utoken>
    r_token:     <rc_token dari verify_payment_init>
    v_token:     <v_token dari method/select>
    shopee_df:   <security_device_fingerprint>
    misc:        {seed: "", operation: 0}
  }
  headers: {"x-app-type": <app_type>}

r_token untuk Password datang dari RESPONSE verify_payment_init,
bukan dari API terpisah. Itu sebabnya error_not_found tadi.
"""
import json, sys, time, secrets, hashlib, urllib.request, urllib.error

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1553.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283191104601"
PASSWORD = sys.argv[3] if len(sys.argv) > 3 else "qwertyui123"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
M = "/api/v4/account/management"
IVS = "/api/v4/anti_fraud/ivs"

ck = open(CK).read().strip()
CSRF = ""
for p in ck.split(";"):
    if p.strip().startswith("csrftoken="):
        CSRF = p.split("=", 1)[1].strip()

cap = json.load(open("aes_pairs.json"))
HD = {h["k"]: h["v"] for h in cap["hdr"] if h.get("v")}
SEC = HD.get("x-sap-sec", "")
SZTOK = HD.get("af-ac-enc-sz-token", "")

# device fingerprint dari capture sebelumnya (kalau ada)
DF = ""
for f in ("device_df.json", "device_fp.json"):
    try:
        DF = json.load(open(f)).get("security_device_fingerprint", "")
        if DF:
            break
    except Exception:
        pass


def mk_ri():
    return (int(time.time()).to_bytes(4, "little").hex()
            + secrets.token_hex(8) + "1601" + secrets.token_hex(12))


def call(path, body=None, method=None, xtra=None):
    h = {"Cookie": ck, "User-Agent": UA, "X-API-SOURCE": "pc",
         "X-Requested-With": "XMLHttpRequest",
         "Referer": "https://shopee.co.id/user/account/settings",
         "Accept": "application/json", "X-CSRFToken": CSRF,
         "X-Shopee-Language": "id", "x-app-type": "3",
         "x-sap-ri": mk_ri(), "x-sap-sec": SEC,
         "af-ac-enc-dat": secrets.token_hex(8),
         "af-ac-enc-sz-token": SZTOK, "x-sz-sdk-version": "1.12.45"}
    if xtra:
        h.update(xtra)
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


NAMES = {1: "OTP", 2: "Password", 3: "ShopeePay", 5: "AuthenticationLink",
         6: "Email", 7: "Qr", 8: "EmailLink", 10: "NewShopeePayPin",
         11: "WhatsAppLink", 14: "SecurityQuestions", 15: "SecurityEmail",
         17: "SecurityDeviceToken", 20: "DEVICE_TOKEN", 100: "SkipVerification"}

log(f"=== v3 SKEMA ASLI — {CK} → {NEWPHONE} ===\n")

# 1
s, j = call(f"{M}/change_phone_init", {})
SEQ = (j.get("data") or {}).get("seq_no")
AUTH = (j.get("data") or {}).get("auth_required")
log(f"[1] init       err={j.get('error')} auth={AUTH}")

# 2
s, j2 = call(f"{M}/change_phone_init_v2", {})
D2 = j2.get("data") or {}
UT = D2.get("ivs_utoken") or ""
CPT = D2.get("change_phone_token") or ""
DF = D2.get("security_device_fingerprint") or DF
log(f"[2] init_v2    err={j2.get('error')} ut={len(UT)}B cp={len(CPT)}B df={len(DF)}B")

# 3
s, j3 = call(f"{IVS}/methods", {"event": 2, "u_token": UT})
_d3 = j3.get("data")
MS = _d3 if isinstance(_d3, list) else ((_d3 or {}).get("methods") or [])
log(f"[3] methods    err={j3.get('error')} {[(m.get('type'), NAMES.get(m.get('type'),'?')) for m in MS]}")

OK = False
for m in MS:
    mt = m.get("type")
    VT = m.get("v_token", "")
    MN = NAMES.get(mt)
    if not MN:
        continue
    log(f"\n--- coba {mt} ({MN}) ---")

    # 4 select
    s, js = call(f"{IVS}/method/select",
                 {"v_token": VT, "method": mt, "event": 2, "u_token": UT})
    log(f"[4] select     err={js.get('error')} {str(js.get('data'))[:100]}")

    # 5 verify_payment_init — rc_token/r_token dari sini
    s, jv = call(f"{M}/verify_payment_init", {"method": mt, "event": 2, "u_token": UT})
    VD = jv.get("data") or {}
    RT = VD.get("rc_token") or VD.get("r_token") or ""
    log(f"[5] vpay_init  err={jv.get('error')} r_token={len(str(RT))}B keys={list(VD)[:6]}")

    # 5b kalau perlu password, kirim
    if jv.get("error") == 0 and VD.get("need_password"):
        ph = hashlib.sha256(hashlib.md5(PASSWORD.encode()).hexdigest().encode()).hexdigest()
        s, jvp = call(f"{M}/verify_payment_commit",
                      {"password": ph, "method": mt, "event": 2, "u_token": UT})
        VD2 = jvp.get("data") or {}
        RT = VD2.get("rc_token") or RT
        log(f"[5b] vpay_commit err={jvp.get('error')} r={len(str(RT))}B")

    if not RT:
        # coba pakai v_token sebagai r_token (fallback SkipVerification)
        log("     ⚠️ r_token kosong -> fallback v_token")
        RT = VT

    # 6 token/verify — SKEMA ASLI
    body = {"method_name": MN, "event": 2, "u_token": UT, "r_token": str(RT),
            "v_token": VT, "shopee_df": DF,
            "misc": {"seed": "", "operation": 0}}
    s, jt = call(f"{IVS}/token/verify", body, xtra={"x-app-type": "3"})
    SIG = (jt.get("data") or {}).get("signature")
    log(f"[6] token/vfy  err={jt.get('error')} sig={'✅ %dB' % len(SIG) if SIG else 'N'}")

    if SIG:
        OK = True
        log("\n🟢🟢 SIGNATURE DAPAT!")

        # 7 precheck
        s, jp = call(f"{M}/change_phone_precheck_v2",
                     {"change_phone_token": CPT, "new_phone": NEWPHONE,
                      "ivs_signature": SIG, "ivs_method_name": MN})
        log(f"[7] precheck   err={jp.get('error')} {str(jp.get('data'))[:150]}")

        # 8 otp settings
        s, jo = call("/api/v4/otp/get_settings_v2",
                     {"operation": 0, "change_phone_token": CPT})
        log(f"[8] otp_set    err={jo.get('error')} {str(jo.get('data'))[:130]}")

        # 9 send
        s, jn = call("/api/v4/otp/send_vcode",
                     {"phone": NEWPHONE, "channel": 1, "operation": 0,
                      "force_channel": False, "supported_channels": [1], "seed": ""})
        log(f"[9] send_vcode err={jn.get('error')} {str(jn.get('data'))[:130]}")

        json.dump({"sig": SIG, "method": MN, "rt": str(RT), "ut": UT,
                   "cpt": CPT, "precheck": jp, "send": jn},
                  open("cp_v3_state.json", "w"), indent=1)
        break
    time.sleep(0.8)

log(f"\n=== {'✅ BERHASIL' if OK else '❌ gagal'} ===")
