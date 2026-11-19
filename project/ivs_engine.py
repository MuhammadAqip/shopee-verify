# -*- coding: utf-8 -*-
"""ivs_engine.py — IVS lengkap: methods -> select -> verify password/pin -> token.

Alur (dari full_flow.py, TERBUKTI):
  1. change_phone_init_v2          -> change_phone_token, ivs_utoken, ivs_required
  2. anti_fraud/ivs/methods        {event:2, u_token} -> [{type, v_token}]
  3. anti_fraud/ivs/method/select  {event:2, u_token, method, v_token} -> err 0
  4. verify_password {password = sha256(md5(pw).hexdigest())} -> rc_token
     atau verify_payment {pin} -> rc_token
  5. anti_fraud/ivs/token/verify   -> ivs_signature
  6. change_phone_precheck_v2
  7. get_settings_v2               {operation:0, phone, supported_channels}
  8. send_vcode
  9. verify_vcode                  -> vcode_token
 10. change_phone_commit_v2        {change_phone_token, new_phone, vcode_token,
                                    ivs_signature, ivs_method}

Semua request TANPA header anti-fraud palsu (REAL_REQUEST_V1).
"""
import hashlib

import changenumfast as c

# --- enum IVS (dari bundle ivs_js/027.js) ---------------------------------
IVS_TYPE = {
    1: "OTP",
    2: "PASSWORD",
    3: "SHOPEEPAY",
    5: "AUTH_LINK",
    6: "EMAIL",
    7: "QR",
    8: "EMAIL_LINK",
    10: "NEW_SHOPEEPAY_PIN",
    11: "WHATSAPP_LINK",
    14: "SECURITY_QUESTIONS",
    15: "SECURITY_EMAIL",
    20: "DEVICE_TOKEN",
    100: "SKIP",
}

IVS_EVENT = 2          # enum event untuk change-phone
IVS_OP = 0             # operation asli

DEVICE_FP = "e6d7f3a1c8b94e2d5f0a7c3b1d8e4f6a"


def sha_md5(pw):
    """Hash password Shopee: sha256(md5(pw).hexdigest())."""
    inner = hashlib.md5(pw.encode("utf-8")).hexdigest()
    return hashlib.sha256(inner.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 1. INIT
# ---------------------------------------------------------------------------
def init(cookie, phone):
    a = c.Api(cookie)
    r = a.post("/api/v4/account/management/change_phone_init_v2",
               {"phone": phone, "seq_no": None})
    d = r.get("data") or {}
    return {
        "ok": r.get("error") == 0,
        "error": r.get("error"),
        "change_phone_token": d.get("change_phone_token") or "",
        "ivs_required": bool(d.get("ivs_required")),
        "ivs_utoken": d.get("ivs_utoken") or "",
        "ttl": d.get("expire_in") or d.get("ttl"),
    }


# ---------------------------------------------------------------------------
# 2. METHODS
# ---------------------------------------------------------------------------
def methods(cookie, utoken):
    a = c.Api(cookie)
    r = a.post("/api/v4/anti_fraud/ivs/methods",
               {"event": IVS_EVENT, "u_token": utoken})
    out = []
    for m in (r.get("data") or []):
        t = m.get("type")
        out.append({"type": t, "name": IVS_TYPE.get(t, f"TYPE_{t}"),
                    "v_token": m.get("v_token") or "",
                    "masked": m.get("masked") or "",
                    "meta": m.get("meta") or {}})
    return {"ok": r.get("error") == 0, "error": r.get("error"), "methods": out}


# ---------------------------------------------------------------------------
# 3. SELECT
# ---------------------------------------------------------------------------
def select(cookie, utoken, method, v_token):
    a = c.Api(cookie)
    r = a.post("/api/v4/anti_fraud/ivs/method/select",
               {"event": IVS_EVENT, "u_token": utoken,
                "method": method, "v_token": v_token})
    d = r.get("data") or {}
    return {"ok": r.get("error") == 0, "error": r.get("error"),
            "data": d, "v_token": v_token,
            "masked_username": d.get("masked_username") or ""}


# ---------------------------------------------------------------------------
# 4a. VERIFY PASSWORD
# ---------------------------------------------------------------------------
def verify_password(cookie, password):
    a = c.Api(cookie)
    body = {"password": sha_md5(password), "scene": "ivs",
            "security_device_fingerprint": DEVICE_FP}
    for path in ("/api/v4/account/management/verify_password",
                 "/api/v4/account/basic/verify_password"):
        r = a.post(path, body)
        if r.get("error") in (0, None) or r.get("error") != 10002:
            d = r.get("data") or {}
            tok = d.get("rc_token") or d.get("token") or ""
            return {"ok": r.get("error") == 0, "error": r.get("error"),
                    "rc_token": tok, "raw": d, "path": path}
    return {"ok": False, "error": "not_found", "rc_token": ""}


# ---------------------------------------------------------------------------
# 4b. VERIFY SHOPEEPAY PIN
# ---------------------------------------------------------------------------
def verify_pin(cookie, pin):
    a = c.Api(cookie)
    body = {"pin": pin, "scene": "ivs",
            "security_device_fingerprint": DEVICE_FP}
    for path in ("/api/v4/account/management/verify_payment",
                 "/api/v4/payment/verify_pin",
                 "/api/v4/shopee_pay/verify_pin"):
        r = a.post(path, body)
        if r.get("error") not in (10002, "error_not_found", None):
            d = r.get("data") or {}
            tok = d.get("rc_token") or d.get("token") or ""
            return {"ok": r.get("error") == 0, "error": r.get("error"),
                    "rc_token": tok, "raw": d, "path": path}
    return {"ok": False, "error": "not_found", "rc_token": ""}


# ---------------------------------------------------------------------------
# 5. IVS TOKEN VERIFY -> ivs_signature
# ---------------------------------------------------------------------------
def token_verify(cookie, utoken, v_token, r_token, method, misc=None):
    a = c.Api(cookie)
    body = {
        "method_name": method,
        "event": IVS_EVENT,
        "u_token": utoken,
        "r_token": r_token,
        "v_token": v_token,
        "misc": misc or {"operation": IVS_OP},
        "security_device_fingerprint": DEVICE_FP,
    }
    r = a.post("/api/v4/anti_fraud/ivs/token/verify", body)
    d = r.get("data") or {}
    sig = d.get("ivs_signature") or d.get("signature") or ""
    return {"ok": r.get("error") == 0, "error": r.get("error"),
            "ivs_signature": sig, "raw": d}


# ---------------------------------------------------------------------------
# FULL IVS (password / pin)
# ---------------------------------------------------------------------------
def solve_ivs(cookie, phone, method, secret):
    """method: 2=PASSWORD, 10=NEW_SHOPEEPAY_PIN, 3=SHOPEEPAY."""
    out = {"step": "init", "ok": False}
    ini = init(cookie, phone)
    out["init"] = ini
    if not ini["ok"] or not ini["ivs_required"]:
        return {"ok": not ini["ivs_required"], "skipped": True,
                "change_phone_token": ini["change_phone_token"], "step": "init"}

    ut = ini["ivs_utoken"]

    out["step"] = "methods"
    mm = methods(cookie, ut)
    out["methods"] = mm
    if not mm["ok"]:
        return out
    pick = next((m for m in mm["methods"] if m["type"] == method), None)
    if not pick:
        out["error"] = f"method {method} tidak tersedia"
        return out

    out["step"] = "select"
    sel = select(cookie, ut, method, pick["v_token"])
    out["select"] = sel
    if not sel["ok"]:
        return out

    out["step"] = "verify"
    if method == 2:
        ver = verify_password(cookie, secret)
    else:
        ver = verify_pin(cookie, secret)
    out["verify"] = ver
    if not ver["ok"] or not ver["rc_token"]:
        return out

    out["step"] = "token"
    tv = token_verify(cookie, ut, pick["v_token"], ver["rc_token"], method)
    out["token"] = tv
    if not tv["ok"]:
        return out

    out["step"] = "done"
    out["ok"] = True
    out["ivs_signature"] = tv["ivs_signature"]
    out["change_phone_token"] = ini["change_phone_token"]
    out["ivs_method"] = str(method)
    return out
