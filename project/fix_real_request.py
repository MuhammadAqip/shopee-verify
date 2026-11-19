# -*- coding: utf-8 -*-
"""fix_real_request.py — samakan request dengan full_flow.py yang TERBUKTI.

ROOT CAUSE 90309999:
  changenumfast.py mengirim header anti-fraud PALSU yang di-generate acak:
    af-ac-enc-dat      = _hex(8)      ← bukan hasil enkripsi, sampah
    x-sap-ri           = MAC acak     ← signature palsu
    af-ac-enc-sz-token = _hex(16)     ← token palsu
    x-sz-sdk-version   = 1.12.45      ← versi ngawur
  Shopee mendeteksi header tidak valid → 90309999 (anti-crawler) untuk
  SEMUA akun, meski cookie sehat.

  full_flow.py — yang BERHASIL ganti nomor 2x — TIDAK mengirim header itu.
  Body-nya juga pakai operation=0, bukan 23.

FIX:
  1. Hapus semua header anti-fraud palsu.
  2. operation default = 0, body lengkap (supported_channels, support_session).
  3. Header persis seperti full_flow: UA, Cookie, Content-Type, Accept,
     x-api-source, x-requested-with, x-csrftoken, x-shopee-language, Referer.

Idempotent: REAL_REQUEST_V1
"""
import io
import re
import shutil
import time

P = "/root/shopee-verify/changenumfast.py"
MARK = "# REAL_REQUEST_V1"

src = io.open(P, encoding="utf-8").read()
if MARK in src:
    print("sudah dipatch")
    raise SystemExit(0)

shutil.copy2(P, P + ".bakrr." + str(int(time.time())))

# ---------------------------------------------------------------------------
# 1) OPERATION 0
# ---------------------------------------------------------------------------
src = src.replace("OP = 23", "# REAL_REQUEST_V1 — operation asli untuk change-phone = 0\nOP = 0", 1)

# ---------------------------------------------------------------------------
# 2) header bersih (hapus yang palsu)
# ---------------------------------------------------------------------------
OLD = '''        self.s.headers.update({
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
            "af-ac-enc-sz-token": _hex(16),
            "x-sz-sdk-version": "1.12.45",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        })'''
NEW = '''        # REAL_REQUEST_V1 — header bersih. TIDAK ada af-ac-enc-dat /
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
        })'''
assert OLD in src, "header tidak ketemu"
src = src.replace(OLD, NEW, 1)

# ---------------------------------------------------------------------------
# 3) _fraud() jadi no-op (tidak inject header palsu)
# ---------------------------------------------------------------------------
OLD2 = '''    def _fraud(self, url, body):
        """Header per-request. af-ac-enc-dat = 8 byte random hex."""
        now = int(time.time() * 1000)
        ts_le = now.to_bytes(8, "little", signed=False)
        rnd = secrets.token_bytes(16)
        mac = hashlib.sha256(ts_le + rnd + url.encode() + body.encode()).digest()[:12]
        ri = (ts_le + rnd + b"\\x01\\x16" + mac).hex()
        return {
            "af-ac-enc-dat": _hex(8),
            "x-sap-ri": ri,
            "x-sap-unc": "",
            "x-sap-time": str(now),
        }'''
NEW2 = '''    def _fraud(self, url, body):
        """REAL_REQUEST_V1 — TIDAK mengirim header anti-fraud palsu.
        Request asli (full_flow.py, terbukti sukses 2x) tidak memakainya.
        Header palsu inilah pemicu 90309999 / TRIGGER_ANTI_CRAWLER.
        """
        return {}'''
assert OLD2 in src, "_fraud tidak ketemu"
src = src.replace(OLD2, NEW2, 1)

# ---------------------------------------------------------------------------
# 4) get_settings_v2 body lengkap + operation 0
# ---------------------------------------------------------------------------
OLD3 = '''        st = a.post("/api/v4/otp/get_settings_v2", {"phone": phone, "operation": op})'''
NEW3 = '''        st = a.post("/api/v4/otp/get_settings_v2",
                    {"operation": op, "phone": phone,
                     "supported_channels": [1, 2, 3],
                     "support_session": False})'''
if OLD3 in src:
    src = src.replace(OLD3, NEW3, 1)

# ---------------------------------------------------------------------------
# 5) send_vcode body lengkap
# ---------------------------------------------------------------------------
OLD4 = '''    j = a.post("/api/v4/otp/send_vcode",
               {"phone": phone, "channel": channel,
                "operation": (op or OP), "seed": seed})
    if j.get("error") == 0:
        d = j.get("data") or {}
        return {"ok": True,
                "trk": d.get("otp_tracking_id"),
                "delivery": d.get("delivery_channel") or channel}
    return {"ok": False, "reason": error_text(j.get("error")),
            "channels": (j.get("data") or {}).get("available_channels") or []}'''
NEW4 = '''    body = {"phone": phone, "channel": channel, "operation": (op or OP),
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
            "channels": (j.get("data") or {}).get("available_channels") or []}'''
assert OLD4 in src, "send_vcode tidak ketemu"
src = src.replace(OLD4, NEW4, 1)

# ---------------------------------------------------------------------------
# 6) check_number: OP_CHAIN mulai dari 0
# ---------------------------------------------------------------------------
src = src.replace("OP_CHAIN = (23, 18)",
                  "OP_CHAIN = (0, 23, 18)   # REAL_REQUEST_V1 — 0 = asli", 1)

io.open(P, "w", encoding="utf-8").write(src)
print("PATCH SELESAI:", P)
