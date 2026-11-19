# -*- coding: utf-8 -*-
"""ivs_flow.py — flow ganti nomor Shopee lengkap (BY COOKIE). Tanpa proxy.

Urutan (dari DevTools Maker):
  1. change_phone_init_v2       -> change_phone_token, ivs_utoken
  2. anti_fraud/ivs/methods     -> [{type, v_token}]
  3. anti_fraud/ivs/method/select -> pilih type
  4. account/management/verify_password -> rc_token
  5. anti_fraud/ivs/token/verify -> ivs_signature
  6. change_phone_precheck_v2
  7. otp/get_settings_v2 -> channels
  8. otp/send_vcode -> OTP dikirim
  9. otp/verify_vcode -> vcode_token
 10. change_phone_commit_v2 -> nomor terganti
"""
import sys, json, urllib.request, urllib.error, hashlib
sys.path.insert(0, "/root/shopee-verify")
from change_phone_engine import parse_cookie

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
IVS_TYPE = {1: "OTP", 2: "PASSWORD", 10: "SHOPEEPAY_PIN"}


class Shopee:
    def __init__(self, cookie_raw):
        self.ck = parse_cookie(cookie_raw)
        self.jar = "; ".join(f"{c['name']}={c['value']}" for c in self.ck)
        self.csrf = next((c["value"] for c in self.ck if c["name"] == "csrftoken"), "")

    def api(self, path, body=None, method=None, extra=None):
        data = json.dumps(body).encode() if body is not None else None
        h = {"User-Agent": UA, "Cookie": self.jar,
             "Content-Type": "application/json",
             "x-api-source": "pc", "x-requested-with": "XMLHttpRequest",
             "x-csrftoken": self.csrf, "x-shopee-language": "id",
             "Referer": "https://shopee.co.id/user/account/profile",
             "Accept": "application/json",
             "af-ac-enc-dat": ""}
        if extra:
            h.update(extra)
        m = method or ("POST" if data else "GET")
        req = urllib.request.Request("https://shopee.co.id" + path,
                                     data=data, method=m, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            b = e.read()[:300].decode(errors="ignore")
            return {"http_error": e.code, "body": b}
        except Exception as e:
            return {"err": str(e)}

    # ---------- step 1 ----------
    def init(self):
        r = self.api("/api/v4/account/management/change_phone_init_v2", {})
        d = r.get("data") or {}
        return {"ok": r.get("error") == 0, "raw": r,
                "token": d.get("change_phone_token"),
                "ivs_required": d.get("ivs_required"),
                "ivs_utoken": d.get("ivs_utoken")}

    # ---------- step 2 ----------
    def ivs_methods(self):
        r = self.api("/api/v4/anti_fraud/ivs/methods")
        return {"ok": r.get("error") == 0, "raw": r,
                "methods": [{"type": m.get("type"),
                             "name": IVS_TYPE.get(m.get("type"), str(m.get("type"))),
                             "v_token": m.get("v_token")}
                            for m in (r.get("data") or [])]}

    # ---------- step 3 ----------
    def ivs_select(self, mtype, v_token):
        r = self.api("/api/v4/anti_fraud/ivs/method/select",
                     {"type": mtype, "v_token": v_token})
        return {"ok": r.get("error") == 0, "raw": r, "data": r.get("data")}

    # ---------- step 4 ----------
    def verify_password(self, pw):
        ans = hashlib.sha256(hashlib.md5(pw.encode()).hexdigest().encode()).hexdigest()
        r = self.api("/api/v4/account/management/verify_password",
                     {"password": ans})
        if r.get("error") not in (0, None):
            r2 = self.api("/api/v4/account/management/verify_password",
                          {"password": ans, "answer": ans})
            if r2.get("error") == 0:
                r = r2
        d = r.get("data") or {}
        return {"ok": r.get("error") == 0, "raw": r, "rc_token": d.get("rc_token")}

    # ---------- step 5 ----------
    def ivs_verify(self, rc_token, mtype, v_token=None):
        body = {"rc_token": rc_token}
        if v_token:
            body["v_token"] = v_token
        r = self.api("/api/v4/anti_fraud/ivs/token/verify", body)
        d = r.get("data") or {}
        return {"ok": r.get("error") == 0, "raw": r,
                "ivs_signature": d.get("ivs_signature") or d.get("signature"),
                "data": d}

    # ---------- step 6 ----------
    def precheck(self, phone):
        r = self.api("/api/v4/account/management/change_phone_precheck_v2",
                     {"phone": phone})
        return {"ok": r.get("error") == 0, "error": r.get("error"), "raw": r}

    # ---------- step 7 ----------
    def channels(self, phone):
        r = self.api("/api/v4/otp/get_settings_v2",
                     {"operation": 0, "phone": phone,
                      "supported_channels": [1, 2, 3], "support_session": False})
        d = r.get("data") or {}
        return {"ok": r.get("error") == 0, "error": r.get("error"), "raw": r,
                "channels": d.get("available_channels") or [],
                "preferred": d.get("preferred_channel"),
                "seed": d.get("seed")}

    # ---------- step 8 ----------
    def send_otp(self, phone, channel=1, seed=None, supported=None):
        body = {"phone": phone, "channel": channel, "operation": 0,
                "force_channel": False,
                "supported_channels": supported or [channel]}
        if seed:
            body["seed"] = seed
        r = self.api("/api/v4/otp/send_vcode", body)
        d = r.get("data") or {}
        return {"ok": r.get("error") == 0, "error": r.get("error"), "raw": r,
                "seed": d.get("seed") or d.get("otp_tracking_id"),
                "tracking": d.get("otp_tracking_id")}

    # ---------- step 9 ----------
    def verify_otp(self, phone, vcode, token):
        r = self.api("/api/v4/otp/verify_vcode",
                     {"phone": phone, "vcode": vcode, "vcode_token": token,
                      "operation": 0})
        d = r.get("data") or {}
        return {"ok": r.get("error") == 0, "error": r.get("error"), "raw": r,
                "vcode_token": d.get("vcode_token") or d.get("token")}

    # ---------- step 10 ----------
    def commit(self, change_token, phone, vcode_token, ivs_sig, ivs_method=""):
        body = {"change_phone_token": change_token, "new_phone": phone,
                "vcode_token": vcode_token, "ivs_signature": ivs_sig,
                "ivs_method": ivs_method}
        r = self.api("/api/v4/account/management/change_phone_commit_v2", body)
        d = r.get("data") or {}
        return {"ok": r.get("error") == 0, "error": r.get("error"), "raw": r,
                "data": d}


def main():
    ck = open("/root/shopee-verify/ck_test.txt").read().strip()
    s = Shopee(ck)
    print("=== 1. init_v2 ===")
    r1 = s.init()
    print("ok:", r1["ok"], "ivs_required:", r1["ivs_required"],
          "token:", bool(r1["token"]))
    if not r1["ok"]:
        print(json.dumps(r1["raw"], ensure_ascii=False)[:300]); return

    print("\n=== 2. ivs/methods ===")
    r2 = s.ivs_methods()
    print("ok:", r2["ok"])
    for m in r2["methods"]:
        print(f"  type={m['type']:>3} {m['name']:>12}  v_token={len(m['v_token'] or '')} char")
    if not r2["methods"]:
        print(json.dumps(r2["raw"], ensure_ascii=False)[:300]); return

    print("\n=== 3. ivs/method/select ===")
    pick = r2["methods"][0]
    r3 = s.ivs_select(pick["type"], pick["v_token"])
    print(f"ok: {r3['ok']} (type={pick['type']} {pick['name']})")
    print(json.dumps(r3["raw"], ensure_ascii=False)[:250])


if __name__ == "__main__":
    main()
