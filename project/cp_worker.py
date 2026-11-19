# -*- coding: utf-8 -*-
"""cp_worker.py — worker ganti nomor Shopee by cookie.

Protokol baris JSON lewat stdin/stdout (sama seperti worker.py).

Session disimpan per uid, satu browser context per cookie.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from change_phone_engine import (ENGINE_JS, parse_cookie, VERIFY_METHOD,
                                 OTP_CHANNEL, err_msg)

BASE = Path("/root/shopee-verify")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

SESS: dict[str, dict] = {}


def log(msg):
    sys.stderr.write(f"[cp] {msg}\n")
    sys.stderr.flush()


class Sess:
    def __init__(self, uid: str, cookie_raw: str):
        self.uid = uid
        self.cookie_raw = cookie_raw
        self.pw = None
        self.br = None
        self.ctx = None
        self.page = None
        self.account = {}
        self.seq_no = None
        self.change_token = None
        self.new_phone = None
        self.channel_seed = None
        self.channels = []
        self.otp_seed = None

    def open(self):
        self.close()
        self.pw = sync_playwright().start()
        self.br = self.pw.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled"])
        self.ctx = self.br.new_context(
            user_agent=UA, locale="id-ID",
            viewport={"width": 1366, "height": 900},
            timezone_id="Asia/Jakarta",
            proxy={"server": "http://127.0.0.1:18080"})
        self.ctx.add_cookies(parse_cookie(self.cookie_raw))
        self.ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        self.page = self.ctx.new_page()
        self.page.goto("https://shopee.co.id/", wait_until="domcontentloaded",
                       timeout=90000)
        self.page.wait_for_timeout(5000)
        acc = self.S(step="account")
        if acc.get("error") != 0:
            raise RuntimeError(f"cookie invalid (error {acc.get('error')})")
        self.account = acc.get("data") or {}
        return self.account

    def close(self):
        for x in ("ctx", "br"):
            try:
                getattr(self, x) and getattr(self, x).close()
            except Exception:
                pass
        try:
            self.pw and self.pw.stop()
        except Exception:
            pass
        self.pw = self.br = self.ctx = self.page = None

    def S(self, **kw):
        if not self.page:
            raise RuntimeError("session belum dibuka")
        return self.page.evaluate(ENGINE_JS, kw)

    def alive(self):
        return bool(self.page)


def get_sess(uid: str, cookie: str | None = None) -> Sess:
    s = SESS.get(uid)
    if s and s.alive() and (cookie is None or cookie == s.cookie_raw):
        return s
    if s:
        s.close()
    if not cookie:
        raise RuntimeError("sesi tidak ada, kirim cookie dulu")
    s = Sess(uid, cookie)
    SESS[uid] = s
    s.open()
    return s


# ---------------- commands ----------------

def cmd_login(a) -> dict:
    s = get_sess(a["uid"], a["cookie"])
    d = s.account
    return {"ok": True, "account": {
        "userid": d.get("userid"), "username": d.get("username"),
        "phone": d.get("phone"), "phone_verified": d.get("phone_verified"),
        "payment_password": d.get("payment_password"),
        "has_pin": bool(d.get("payment_password")),
    }}


def cmd_init(a) -> dict:
    s = get_sess(a["uid"])
    r = s.S(step="init")
    if not r.get("ok"):
        return {"ok": False, "err": err_msg(r.get("error")),
                "raw": r.get("raw")}
    s.seq_no = r.get("seq_no")
    s.change_token = r.get("change_phone_token")
    # metode verifikasi
    m = s.S(step="methods", seq_no=s.seq_no) if s.seq_no else {}
    vm = m.get("verify_method")
    return {"ok": True, "seq_no": s.seq_no,
            "change_phone_token": bool(s.change_token),
            "ivs_required": r.get("ivs_required"),
            "verify_method": vm,
            "verify_method_name": VERIFY_METHOD.get(vm, str(vm))}


def cmd_verify(a) -> dict:
    """a: {answer} — password plain; di-hash sha256(md5(pw)) di sini."""
    import hashlib
    s = get_sess(a["uid"])
    pw = a.get("answer") or ""
    ans = hashlib.sha256(
        hashlib.md5(pw.encode()).hexdigest().encode()).hexdigest()
    vi = s.S(step="verify_init", seq_no=s.seq_no)
    v = s.S(step="verify", seq_no=s.seq_no, answer=ans)
    return {"ok": bool(v.get("ok")), "error": v.get("error"),
            "msg": err_msg(v.get("error")) if not v.get("ok") else "",
            "init_raw": vi.get("raw"), "raw": v.get("raw")}


def cmd_channels(a) -> dict:
    """a: {phone} nomor baru."""
    s = get_sess(a["uid"])
    phone = a["phone"]
    s.new_phone = phone
    r = s.S(step="channels", phone=phone)
    d = r.get("data") or {}
    s.channel_seed = d.get("seed")
    s.channels = d.get("available_channels") or []
    return {"ok": bool(r.get("ok")), "error": r.get("error"),
            "channels": [{"id": c, "name": OTP_CHANNEL.get(c, str(c))}
                         for c in s.channels],
            "preferred": d.get("preferred_channel"),
            "need_login": d.get("need_login"),
            "need_captcha": d.get("need_captcha"),
            "masked_phone": d.get("masked_phone")}


def cmd_send(a) -> dict:
    s = get_sess(a["uid"])
    ch = int(a.get("channel") or 1)
    r = s.S(step="send", phone=s.new_phone, channel=ch,
            seed=s.channel_seed, supported_channels=s.channels or [ch])
    if r.get("ok"):
        s.otp_seed = r.get("seed") or s.channel_seed
    return {"ok": bool(r.get("ok")), "error": r.get("error"),
            "msg": err_msg(r.get("error")) if not r.get("ok") else "",
            "channel": OTP_CHANNEL.get(ch, str(ch)),
            "seed": r.get("seed"), "raw": r.get("raw")}


def cmd_verify_otp(a) -> dict:
    s = get_sess(a["uid"])
    r = s.S(step="verify_otp", phone=s.new_phone, vcode=a["vcode"],
            vcode_token=s.otp_seed or "")
    if r.get("ok") and r.get("token"):
        s.otp_seed = r["token"]
    return {"ok": bool(r.get("ok")), "error": r.get("error"),
            "msg": err_msg(r.get("error")) if not r.get("ok") else "",
            "token": bool(r.get("token")), "raw": r.get("raw")}


def cmd_precheck(a) -> dict:
    s = get_sess(a["uid"])
    r = s.S(step="precheck", phone=s.new_phone)
    return {"ok": bool(r.get("ok")), "error": r.get("error"),
            "msg": err_msg(r.get("error")) if not r.get("ok") else "",
            "data": r.get("data")}


def cmd_commit(a) -> dict:
    s = get_sess(a["uid"])
    r = s.S(step="commit", phone=s.new_phone,
            change_phone_token=s.change_token,
            vcode_token=s.otp_seed,
            ivs_signature=a.get("ivs_signature", ""),
            ivs_method=a.get("ivs_method", ""))
    return {"ok": bool(r.get("ok")), "error": r.get("error"),
            "msg": err_msg(r.get("error")) if not r.get("ok") else "",
            "data": r.get("data"), "raw": r.get("raw")}


def cmd_status(a) -> dict:
    s = SESS.get(a["uid"])
    if not s:
        return {"ok": False, "err": "tidak ada sesi"}
    return {"ok": True, "alive": s.alive(), "account": s.account,
            "seq_no": bool(s.seq_no), "new_phone": s.new_phone,
            "channels": s.channels, "otp_sent": bool(s.otp_seed)}


def cmd_close(a) -> dict:
    s = SESS.pop(a["uid"], None)
    if s:
        s.close()
    return {"ok": True}


CMDS = {
    "login": cmd_login, "init": cmd_init, "verify": cmd_verify,
    "channels": cmd_channels, "send": cmd_send,
    "verify_otp": cmd_verify_otp, "precheck": cmd_precheck,
    "commit": cmd_commit, "status": cmd_status, "close": cmd_close,
}


def reply(o):
    sys.stdout.write(json.dumps(o, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    log("cp_worker start")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        rid, cmd = req.get("id"), req.get("cmd")
        fn = CMDS.get(cmd)
        if not fn:
            reply({"id": rid, "ok": False, "err": f"cmd tidak dikenal: {cmd}"})
            continue
        try:
            r = fn(req)
            reply({"id": rid, **r})
        except Exception as e:
            log(f"{cmd} ERROR: {e}")
            reply({"id": rid, "ok": False, "err": str(e)})


if __name__ == "__main__":
    main()
