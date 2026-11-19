# -*- coding: utf-8 -*-
"""full_flow.py — FLOW GANTI NOMOR SHOPEE LENGKAP dari Python.

TERBUKTI: ivs/token/verify LOLOS tanpa x-sap-sec.
Body butuh: method_name, event, u_token, r_token, v_token, misc, fp.
"""
import sys, json, hashlib, urllib.request, urllib.error
sys.path.insert(0, "/root/shopee-verify")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
CSRF = "bb5f05881379dd5d0759d8dc9a12b0fe"
FP = "GY79LnMyc2KEKSGbyDqBgw==|Jug49U3W1roGbiRxUvnTZhE1jIfn5rMo1KqYS8bDuDlEdh+oEKI88kN0ZdWx+/KXwVNBjg+Fi3zduA==|HnenNBFFdeCzJK/a|08|3"
COOKIE_RAW = open("/root/shopee-verify/ck_1533.txt").read().strip()


class Flow:
    def __init__(self, cookie=COOKIE_RAW):
        self.cookie = cookie
        self.csrf = CSRF
        self.cp_token = None
        self.u_token = None
        self.ivs_sig = None
        self.method = None

    def post(self, path, body, ref="https://shopee.co.id/verify/ivs"):
        h = {"User-Agent": UA, "Cookie": self.cookie,
             "Content-Type": "application/json", "Accept": "application/json",
             "x-api-source": "pc", "x-requested-with": "XMLHttpRequest",
             "x-csrftoken": self.csrf, "x-shopee-language": "id",
             "Referer": ref}
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

    def step1_init(self):
        st, r = self.post("/api/v4/account/management/change_phone_init_v2", {})
        d = r.get("data") or {}
        self.cp_token = d.get("change_phone_token")
        self.u_token = d.get("ivs_utoken")
        return {"ok": r.get("error") == 0,
                "cp_token": bool(self.cp_token),
                "u_token": bool(self.u_token),
                "ivs_required": d.get("ivs_required")}

    def step4_password(self, pw):
        ans = hashlib.sha256(hashlib.md5(pw.encode()).hexdigest().encode()).hexdigest()
        st, r = self.post("/api/v4/account/management/verify_password",
                          {"password": ans},
                          ref="https://shopee.co.id/user/account/profile")
        d = r.get("data") or {}
        self.r_token = d.get("rc_token")
        return {"ok": r.get("error") == 0, "error": r.get("error"),
                "r_token": bool(self.r_token)}

    def step5_ivs_verify(self, method=2, event=2, v_token=None, operation=0):
        body = {"method_name": method, "event": event,
                "u_token": self.u_token, "r_token": self.r_token,
                "misc": {"operation": operation},
                "security_device_fingerprint": FP}
        if v_token:
            body["v_token"] = v_token
        st, r = self.post("/api/v4/anti_fraud/ivs/token/verify", body)
        self.ivs_sig = r.get("signature")
        self.method = method
        return {"ok": r.get("error") == 0 and bool(self.ivs_sig),
                "error": r.get("error"),
                "signature": bool(self.ivs_sig),
                "http": st}

    def step6_precheck(self, phone):
        st, r = self.post("/api/v4/account/management/change_phone_precheck_v2",
                          {"phone": phone})
        return {"ok": r.get("error") == 0, "error": r.get("error"), "raw": r}

    def step7_channels(self, phone):
        st, r = self.post("/api/v4/otp/get_settings_v2",
                          {"operation": 0, "phone": phone,
                           "supported_channels": [1, 2, 3],
                           "support_session": False})
        d = r.get("data") or {}
        return {"ok": r.get("error") == 0, "error": r.get("error"),
                "channels": d.get("available_channels") or [],
                "preferred": d.get("preferred_channel"),
                "seed": d.get("seed")}

    def step8_send(self, phone, channel=1, seed=None, supported=None):
        body = {"phone": phone, "channel": channel, "operation": 0,
                "force_channel": False,
                "supported_channels": supported or [channel]}
        if seed: body["seed"] = seed
        st, r = self.post("/api/v4/otp/send_vcode", body)
        d = r.get("data") or {}
        return {"ok": r.get("error") == 0, "error": r.get("error"),
                "seed": d.get("seed") or d.get("otp_tracking_id"),
                "tracking": d.get("otp_tracking_id")}

    def step9_verify_otp(self, phone, vcode, token):
        st, r = self.post("/api/v4/otp/verify_vcode",
                          {"phone": phone, "vcode": vcode,
                           "vcode_token": token, "operation": 0})
        d = r.get("data") or {}
        return {"ok": r.get("error") == 0, "error": r.get("error"),
                "vcode_token": d.get("vcode_token") or d.get("token")}

    def step10_commit(self, phone, vcode_token):
        body = {"change_phone_token": self.cp_token, "new_phone": phone,
                "vcode_token": vcode_token,
                "ivs_signature": self.ivs_sig,
                "ivs_method": str(self.method or 2)}
        st, r = self.post("/api/v4/account/management/change_phone_commit_v2", body)
        return {"ok": r.get("error") == 0, "error": r.get("error"),
                "raw": r, "data": r.get("data")}
