# -*- coding: utf-8 -*-
"""changenumfast.py — versi HTTP/API murni untuk Change Number Shopee.

TANPA browser. Tanpa Playwright. Cepat (~1-2 detik per request).

Yang dibutuhkan dari browser hanya SEKALI (di-cache ke file):
  - cookie session (dari user)
  - header anti-fraud: af-ac-enc-dat, x-sap-ri, x-sap-sec, af-ac-enc-sz-token
    → dibangkitkan ulang tiap request dengan algoritma yang sudah di-RE

Untuk commit final: endpoint change_phone_commit_v2 TIDAK ADA di web PC;
satu-satunya jalan adalah panggil service modul 66199 via webpack → butuh
browser SATU KALI untuk commit. Semua step lain (init/settings/send/verify)
full HTTP.

Mode:
  - check_account(cookie)          → username + phone      [HTTP, <2s]
  - check_number(cookie, phone)    → cp/seed/channels      [HTTP, <3s]
  - request_otp(...)               → trk                   [HTTP, <2s]
  - commit_change(...)             → final                 [browser, ~14s]
"""
import hashlib
import json
import os
import random
import secrets
import string
import time

import requests

BASE = "https://shopee.co.id"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

# REAL_REQUEST_V1 — operation asli untuk change-phone = 0
OP = 0

CHANNEL_NAME = {1: "SMS", 2: "Voice Call", 3: "WhatsApp", 4: "Email", 5: "Zalo", 6: "Viber"}

NUMBER_BAD = {
    23500158: "Nomor ini diblokir Shopee (terlalu banyak OTP hari ini). Coba nomor lain.",
    23500152: "Rate limit untuk nomor ini. Coba nomor lain.",
    10001:    "Nomor tidak valid.",
    10002:    "Nomor tidak valid / parameter ditolak.",
    10013:    "Nomor tidak bisa dipakai untuk akun ini.",
    23500000: "Kode/nomor tidak cocok.",
}


# CHG_ERR_DETAIL_V8  (19: cookie expired, saran Muse)
HINTS = {
    19: "Cookie expired. Ambil cookie baru dari browser.",
    23500158: "Nomor/akun diblok sementara oleh anti-abuse Shopee. "
              "Tunggu beberapa jam atau ganti nomor.",
    23500152: "Rate limit nomor. Tunggu 15-30 menit.",
    23500101: "Shopee minta captcha untuk operasi ini.",
    90309999: "AKUN KENA FLAG ANTI-CRAWLER Shopee (endpoint diblok). "
              "Ganti cookie akun baru — akun ini tidak bisa dipakai lagi "
              "hari ini.",
    23500000: "Kode OTP salah atau sudah kedaluwarsa.",
    31500000: "Sesi OTP kedaluwarsa. Minta kode baru.",
    31500200: "Payload captcha kurang lengkap.",
    31600000: "Butuh header x-sap valid.",
    10002:    "Parameter wajib hilang / route salah.",
    10013:    "State server tidak sesuai untuk flow ini.",
}


PROXY_ERR = -997
NET_ERR = -999


def error_text(code):
    if code == PROXY_ERR:
        return "PROXY MATI — request tidak bisa keluar lewat relay. " \
               "Bot akan keluar dari IP VPS dan akun kena flag."
    if code == NET_ERR:
        return "Jaringan gagal (bukan dari Shopee)."
    return NUMBER_BAD.get(code, f"Shopee menolak (error {code}).")


def err_obj(code, msg=""):
    """Objek error seragam untuk bot: code + reason + hint."""
    return {"ok": False,
            "code": code,
            "reason": msg or error_text(code),
            "hint": HINTS.get(code, "")}


def norm_phone(raw):
    s = "".join(ch for ch in str(raw or "") if ch.isdigit() or ch == "+").replace("+", "")
    if s.startswith("0"):
        s = "62" + s[1:]
    elif s.startswith("8"):
        s = "62" + s
    if not s.startswith("62"):
        return None
    if not (10 <= len(s) <= 15):
        return None
    return s


def is_cookie(txt):
    return ("SPC_" in txt or "csrftoken" in txt) and "=" in txt


def _hex(n):
    return secrets.token_hex(n)


def _cookie_dict(ck):
    d = {}
    for p in ck.split(";"):
        if "=" in p:
            k, v = p.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def _cookie_str(d):
    return "; ".join(f"{k}={v}" for k, v in d.items())


# PROXY_ENFORCE_V1
import os as _os

PROXY_CHAIN = ("SHOPEE_MITM", "SHOPEE_PROXY", "HTTPS_PROXY", "https_proxy")
PROXY_DEFAULT = "http://127.0.0.1:18080"


def proxy_url():
    """URL proxy yang WAJIB dipakai. Tidak pernah None selama relay hidup."""
    for k in PROXY_CHAIN:
        v = (_os.environ.get(k) or "").strip()
        if v:
            return v
    return PROXY_DEFAULT


def proxies_dict():
    u = proxy_url()
    return {"http": u, "https": u}


def proxy_info(timeout=25):
    """Cek IP keluar lewat proxy. Untuk verifikasi config."""
    px = proxies_dict()
    try:
        r = requests.get("https://api.ipify.org", proxies=px, timeout=timeout)
        return {"ok": True, "proxy": px["https"], "ip": r.text.strip()}
    except Exception as e:
        return {"ok": False, "proxy": px["https"], "error": str(e)}


class Api:
    """HTTP client dengan header anti-fraud Shopee."""

    def __init__(self, cookie, timeout=25, proxy=None):
        self.timeout = timeout
        self.cd = _cookie_dict(cookie)
        self.s = requests.Session()
        # PROXY_ENFORCE_V1 — WAJIB lewat proxy residensial.
        if proxy is False:
            self.s.proxies = {}
        elif proxy:
            self.s.proxies = {"http": proxy, "https": proxy}
        else:
            self.s.proxies = proxies_dict()
        # REAL_REQUEST_V1 — header bersih. TIDAK ada af-ac-enc-dat /
        # x-sap-ri / af-ac-enc-sz-token palsu. Itu yang memicu 90309999.
        self.s.headers.update({
            "User-Agent": UA,
            "Accept": "application/json",
            "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
            "Content-Type": "application/json",
            "Origin": BASE,
            "Referer": BASE + "/user/account/phone",
            "x-requested-with": "XMLHttpRequest",
            "x-api-source": "pc",
            "x-shopee-language": "id",
            "x-csrftoken": self.cd.get("csrftoken", ""),
        })
        self.s.cookies.update({k: v for k, v in self.cd.items()})

    def _fraud(self, url, body):
        """REAL_REQUEST_V1 — TIDAK mengirim header anti-fraud palsu.
        Request asli (full_flow.py, terbukti sukses 2x) tidak memakainya.
        Header palsu inilah pemicu 90309999 / TRIGGER_ANTI_CRAWLER.
        """
        return {}

    def post(self, path, body=None):
        url = BASE + path
        raw = json.dumps(body or {}, separators=(",", ":"))
        h = {"Content-Type": "application/json"}
        h.update(self._fraud(url, raw))
        try:
            r = self.s.post(url, data=raw, headers=h, timeout=self.timeout)
        except Exception as e:
            msg = str(e)
            if "proxy" in msg.lower() or "tunnel" in msg.lower() \
                    or "connect" in msg.lower():
                return {"error": -997,
                        "error_msg": f"PROXY mati ({self.s.proxies.get('https')}): "
                                     f"{msg[:80]}"}
            return {"error": -999, "error_msg": f"network: {msg[:80]}"}
        try:
            j = r.json()
            if isinstance(j, dict) and "error_msg" not in j and "error" in j:
                j["error_msg"] = ""
            return j
        except Exception:
            return {"error": -998, "error_msg": f"http {r.status_code}: {r.text[:160]}"}

    def get(self, path):
        url = BASE + path
        h = self._fraud(url, "")
        try:
            r = self.s.get(url, headers=h, timeout=self.timeout)
        except Exception as e:
            msg = str(e)
            if "proxy" in msg.lower() or "tunnel" in msg.lower() \
                    or "connect" in msg.lower():
                return {"error": -997,
                        "error_msg": f"PROXY mati ({self.s.proxies.get('https')}): "
                                     f"{msg[:80]}"}
            return {"error": -999, "error_msg": f"network: {msg[:80]}"}
        try:
            return r.json()
        except Exception:
            return {"error": -998, "error_msg": f"http {r.status_code}"}


# ---------------------------------------------------------------------------
# API steps (full HTTP)
# ---------------------------------------------------------------------------

def check_account(cookie):
    """Ambil username + nomor lama. <2s."""
    a = Api(cookie)
    j = a.get("/api/v4/account/basic/get_account_info")
    if j.get("error") not in (0, None):
        e = err_obj(j.get("error"), j.get("error_msg") or "")
        e["reason"] = e["reason"] or f"Cookie tidak valid / sesi mati."
        if e.get("code") in (19, -1, 10002):
            e["hint"] = "Cookie expired. Ambil cookie baru dari browser."
        return e
    d = j.get("data") or {}
    return {"ok": True,
            "username": d.get("username") or "?",
            "phone": d.get("phone") or "?",
            "verified": d.get("phone_verified"),
            "uid": d.get("userid")}


# OP FALLBACK V3 — op=23 bisa diblok per-nomor, op=18 tetap jalan.
# OP_CHAIN_V10 — Muse crosscheck: op=18 scene "set_phone" (bukan change),
# vcode_token-nya BELUM TERBUKTI diterima commit_change. Jangan dipakai
# sebagai fallback otomatis — hanya op yang jadi jalur asli.
# op=0 (scene others) = SMS-only, fallback terakhir kalau WA diblok.
OP_CHAIN = (23, 0)
OP_CHAIN_EXTENDED = (23, 18, 8, 0)   # manual only — untuk tes akun test
OP_BLOCKED = {23500158, 23500152, 90309999}


# HEALTH_V2
def account_health(cookie, timeout=20):
    """Status akun berbasis HANYA get_settings_v2 (sinyal yang benar).

    order_list / cart SELALU 90309999 untuk web-PC — bukan indikator flag.

    Return: {"state": "ok"|"limited"|"ivs"|"dead",
             "blocked": [...], "reason": "..."}
    """
    a = Api(cookie, timeout=timeout)
    j = a.get("/api/v4/account/basic/get_account_info")
    if j.get("error") not in (0, None):
        return {"state": "dead", "blocked": [],
                "reason": f"Cookie mati / auth gagal (error {j.get('error')})."}

    probe_phone = "628000000000"
    ini = a.post("/api/v4/account/management/change_phone_init_v2",
                 {"phone": probe_phone, "seq_no": None})
    d = ini.get("data") or {}
    if ini.get("error") == 0 and d.get("ivs_required"):
        return {"state": "ivs", "blocked": [],
                "reason": "Akun minta verifikasi identitas (IVS). "
                          "Selesaikan IVS di app Shopee dulu."}

    seen = {}
    for op in (23, 18):
        s = a.post("/api/v4/otp/get_settings_v2",
                   {"phone": probe_phone, "operation": op})
        seen[op] = s.get("error")

    codes = {c for c in seen.values() if c is not None}
    if 0 in codes:
        return {"state": "ok", "blocked": [], "ops": seen, "reason": ""}

    if 23500101 in codes:
        return {"state": "ok", "blocked": [], "ops": seen,
                "reason": "Nomor uji butuh captcha, akun sendiri sehat."}

    if any(c in (23500158, 23500152, 90309999) for c in codes):
        return {"state": "limited", "blocked": ["otp_settings"], "ops": seen,
                "reason": "Akun diblok sementara untuk OTP "
                          f"(op23={seen.get(23)}, op18={seen.get(18)}). "
                          "Tunggu beberapa jam atau pakai akun lain."}

    return {"state": "limited", "blocked": [], "ops": seen,
            "reason": f"Endpoint OTP menolak (op23={seen.get(23)}, "
                      f"op18={seen.get(18)})."}


def check_number(cookie, phone):
    """init_v2 + get_settings_v2. Coba op=23 lalu fallback op=18. <3s."""
    a = Api(cookie)

    ini = a.post("/api/v4/account/management/change_phone_init_v2",
                 {"phone": phone, "seq_no": None})
    if ini.get("error") != 0:
        return err_obj(ini.get("error"), ini.get("error_msg") or "")
    d = ini.get("data") or {}
    if d.get("ivs_required"):
        return {"ok": False, "code": "ivs",
                "reason": "Akun minta verifikasi identitas (IVS).",
                "hint": "Akun ini tidak bisa ganti nomor via bot. Pakai akun lain."}
    if d.get("ongoing_request_phone"):
        return {"ok": False, "code": "ongoing",
                "reason": f"Akun masih punya permintaan menggantung ke "
                          f"{d['ongoing_request_phone']}.",
                "hint": "Tunggu 15 menit atau selesaikan permintaan itu dulu."}
    cp = d.get("change_phone_token") or ""
    if not cp:
        return {"ok": False, "code": "no_token",
                "reason": "Shopee tidak mengembalikan change_phone_token.",
                "hint": "Coba ulang beberapa saat lagi."}

    # CHG_CAPTCHA_GUARD_V8
    # Kumpulkan SEMUA op yang get_settings-nya sukses, pilih yang tanpa captcha.
    last_err = None
    candidates = []      # (op, seed, channels, need_captcha, preferred)
    for op in OP_CHAIN:
        st = a.post("/api/v4/otp/get_settings_v2",
                    {"operation": op, "phone": phone,
                     "supported_channels": [1, 2, 3],
                     "support_session": False})
        err = st.get("error")
        if err == 0:
            sd = st.get("data") or {}
            chans = [c for c in (sd.get("available_channels") or [])
                     if c in CHANNEL_NAME]
            if not chans:
                last_err = "no_channel"
                continue
            candidates.append((op, sd.get("seed") or "", chans,
                               bool(sd.get("need_captcha")),
                               sd.get("preferred_channel"),
                               sd.get("masked_phone") or ""))
            # CHG_CHANNEL_PRIORITY_V9
            # Jangan break di op tanpa-captcha kalau channel-nya cuma SMS —
            # op berikutnya (23/18) bisa kasih WhatsApp tanpa captcha juga.
            if not sd.get("need_captcha") and any(c != 1 for c in chans):
                break
            continue
        if err in OP_BLOCKED:
            last_err = err
            continue
        return err_obj(err, st.get("error_msg") or "")

    if candidates:
        # prioritas: need_captcha=False
        free = [c for c in candidates if not c[3]]
        pick = free[0] if free else candidates[0]
        op, seed, chans, nc, pref, masked = pick
        if nc:
            # semua op butuh captcha → JANGAN bilang ok
            return {"ok": False, "code": 23500101,
                    "reason": "Shopee minta captcha untuk nomor ini.",
                    "hint": "Nomor ini terkunci captcha. Coba nomor lain.",
                    "need_captcha": True,
                    "channels": chans,
                    "op": op,
                    "ops_tried": [c[0] for c in candidates]}
        return {"ok": True,
                "phone": phone,
                "cp": cp,
                "op": op,
                "seed": seed,
                "channels": chans,
                "preferred": pref,
                "need_captcha": False,
                "masked": masked,
                "ops_ok": [c[0] for c in candidates]}

    if last_err == "no_channel":
        return {"ok": False, "code": "no_channel",
                "reason": "Shopee tidak menawarkan channel OTP untuk nomor ini.",
                "hint": "Nomor mungkin tidak aktif di WA/SMS/Voice. Coba nomor lain."}

    code = last_err if isinstance(last_err, int) else 23500158

    # ANTICRAWLER_GUARD_V1 — bedakan "nomor diblok" vs "akun kena flag"
    if code == 23500158:
        h = account_health(cookie)
        if h["state"] == "limited":
            return {"ok": False, "code": 90309999,
                    "reason": "AKUN kena flag anti-crawler Shopee.",
                    "hint": (f"{len(h['blocked'])} endpoint diblok "
                             f"({', '.join(h['blocked'])}). "
                             "Nomor ini tidak bersalah — akunnya yang diblok. "
                             "Pakai cookie akun lain.")}
        return {"ok": False, "code": code,
                "reason": "Nomor ini sudah terlalu banyak minta OTP.",
                "hint": ("Tunggu 15-60 menit, atau pakai nomor lain. "
                         "Akun masih sehat.")}

    return {"ok": False, "code": code,
            "reason": error_text(code),
            "hint": HINTS.get(code, "Coba nomor lain atau tunggu.")}

    if last_err == "no_channel":
        return {"ok": False, "code": "no_channel",
                "reason": "Shopee tidak menawarkan channel OTP untuk nomor ini.",
                "hint": "Nomor mungkin tidak aktif di WA/SMS/Voice. Coba nomor lain."}
    return {"ok": False, "code": last_err or 23500158,
            "reason": error_text(last_err or 23500158),
            "hint": HINTS.get(last_err or 23500158, "Coba nomor lain atau tunggu.")}


def request_otp(cookie, phone, cp, seed, channel, op=None):
    """send_vcode. op default dari OP (23), bisa dioverride hasil check_number."""
    a = Api(cookie)
    body = {"phone": phone, "channel": channel, "operation": (op or OP),
            "force_channel": False, "supported_channels": [1, 2, 3]}
    if seed:
        body["seed"] = seed
    j = a.post("/api/v4/otp/send_vcode", body)
    if j.get("error") == 0:
        d = j.get("data") or {}
        return {"ok": True,
                "trk": d.get("otp_tracking_id"),
                "delivery": d.get("delivery_channel") or channel,
                "op": op or OP}
    return {"ok": False, "reason": error_text(j.get("error")),
            "channels": (j.get("data") or {}).get("available_channels") or []}


def verify_vcode(cookie, phone, code, cp, op=None):
    """verify_vcode → vcode_token. op harus sama dengan yang dipakai send_vcode."""
    a = Api(cookie)
    j = a.post("/api/v4/otp/verify_vcode",
               {"phone": phone, "vcode": code,
                "operation": (op or OP), "m_token": cp})
    if j.get("error") != 0:
        return err_obj(j.get("error"), j.get("error_msg") or "")
    vt = (j.get("data") or {}).get("vcode_token") or ""
    if not vt:
        return {"ok": False, "code": "no_token",
                "reason": "vcode_token kosong dari Shopee.",
                "hint": "Coba ulang atau minta kode baru."}
    return {"ok": True, "vcode_token": vt}


# ---------------------------------------------------------------------------
# Commit — satu-satunya step yang butuh webpack service (browser)
# ---------------------------------------------------------------------------

def commit_change(cookie, phone, cp, vt, headless=True):
    """Commit ganti nomor — HTTP langsung, TANPA webpack.

    COMMIT_HTTP_V1 (2026-11-20): jalur webpack mati total sejak Shopee migrasi
    bundler ke rspack. Modul 66199 tidak ada di bundle manapun yang bisa
    dijangkau (dipindai 540-564 modul di /verify/captcha: nol yang mengekspor
    changePhoneCommitV2). Terbukti berhasil lewat HTTP biasa pada akun
    4mmwafs78t → 6289611116321, error 0 / is_delayed false.

    KUNCI: field keenam `client_info.identifier.security_device_fingerprint`
    WAJIB. Tanpa itu selalu 10002. DF harus format pipe-5 segmen (139B),
    bukan blob SDK 2534B dan bukan hex32.
    """
    import df_source

    df = df_source.from_disk()
    a = Api(cookie)
    body = {
        "change_phone_token": cp,
        "new_phone": phone,
        "vcode_token": vt,
        "ivs_signature": "",
        "ivs_method": None,
        "client_info": {"identifier": {"security_device_fingerprint": df}},
    }
    r = a.post("/api/v4/account/management/change_phone_commit_v2", body)
    if r.get("error") != 0:
        e = err_obj(r.get("error"), r.get("error_msg") or "")
        if r.get("error") == 10002:
            e["hint"] = ("10002 = client_info/DF ditolak. Pastikan DF format "
                         "pipe-5 (24|92|16|2|1), bukan blob SDK.")
        return e

    info = check_account(cookie)
    return {"ok": True,
            "new_phone": info.get("phone") or phone,
            "username": info.get("username") or "?",
            "verified": info.get("verified"),
            "is_delayed": (r.get("data") or {}).get("is_delayed")}


# ---------------------------------------------------------------------------
# Orkestrasi lengkap (untuk CLI / tes)
# ---------------------------------------------------------------------------

def full_change(cookie, phone, code=None, channel=3, on_log=print):
    """Cek akun → cek nomor → kirim OTP. Kalau code ada, lanjut verify+commit."""
    t0 = time.time()

    acc = check_account(cookie)
    if not acc.get("ok"):
        return acc
    on_log(f"[{time.time()-t0:.1f}s] akun: {acc['username']} | {acc['phone']}")

    num = check_number(cookie, phone)
    if not num.get("ok"):
        return num
    on_log(f"[{time.time()-t0:.1f}s] nomor OK op={num.get('op')} "
           f"channels={num['channels']} captcha={num['need_captcha']}")

    otp = request_otp(cookie, phone, num["cp"], num["seed"], channel,
                      op=num.get("op"))
    if not otp.get("ok"):
        return otp
    on_log(f"[{time.time()-t0:.1f}s] OTP terkirim trk={otp['trk']}")

    if not code:
        return {"ok": True, "stage": "otp_sent", "trk": otp.get("trk"),
                "phone": phone, "username": acc["username"],
                "old_phone": acc["phone"], "cp": num["cp"],
                "op": num.get("op")}

    v = verify_vcode(cookie, phone, code, num["cp"], op=num.get("op"))
    if not v.get("ok"):
        return v
    on_log(f"[{time.time()-t0:.1f}s] verify OK")

    cm = commit_change(cookie, phone, num["cp"], v["vcode_token"])
    if cm.get("ok"):
        on_log(f"[{time.time()-t0:.1f}s] COMMIT OK → {cm['new_phone']}")
    return cm


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("usage: changenumfast.py <cookie_file> <phone> [code] [channel]")
        raise SystemExit(1)
    ck = open(sys.argv[1]).read().strip()
    ph = norm_phone(sys.argv[2])
    code = sys.argv[3] if len(sys.argv) > 3 else None
    ch = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    t0 = time.time()
    r = full_change(ck, ph, code=code, channel=ch)
    print(json.dumps(r, indent=2, ensure_ascii=False))
    print(f"TOTAL {time.time()-t0:.1f}s")
