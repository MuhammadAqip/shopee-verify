# -*- coding: utf-8 -*-
"""fix_health_v2.py — perbaiki account_health() yang FALSE POSITIVE.

TEMUAN:
  `order_list` dan `cart/get` SELALU membalas 90309999 untuk request web-PC,
  bahkan dengan UA mobile Shopee asli. Itu BUKAN tanda akun ke-flag, itu
  perilaku normal (endpoint butuh verifikasi tambahan).

  Bukti: akun yang `get_settings_v2 op23 -> error:0` (sehat) tetap
  dapat 90309999 di order_list.

AKIBAT BUG LAMA:
  account_health() membaca 90309999 sebagai "limited" → bot menampilkan
  "AKUN KENA FLAG ANTI-CRAWLER" di SEMUA akun, termasuk yang sehat.
  Lebih buruk: fungsi ini nembak 3 endpoint berat tiap cookie masuk,
  menambah counter anti-abuse.

FIX:
  account_health() sekarang HANYA memakai sinyal yang benar:
    - get_account_info gagal         → dead
    - get_settings_v2 op23/op18:
        * error 0                    → ok
        * 23500158 / 23500152        → limited (counter OTP akun)
        * 23500101                   → captcha (bukan flag akun)
        * 90309999                   → limited (flag sejati)
  Tidak lagi memanggil order_list / cart.

Idempotent: HEALTH_V2
"""
import io
import re
import shutil
import time

P = "/root/shopee-verify/changenumfast.py"
MARK = "# HEALTH_V2"

src = io.open(P, encoding="utf-8").read()
if MARK in src:
    print("sudah dipatch")
    raise SystemExit(0)

shutil.copy2(P, P + ".bakh2." + str(int(time.time())))

# ---------------------------------------------------------------------------
# ganti seluruh fungsi account_health
# ---------------------------------------------------------------------------
NEW = '''# HEALTH_V2
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


'''

i = src.find("# ANTICRAWLER_GUARD_V1\ndef account_health(")
if i == -1:
    i = src.find("def account_health(")
assert i != -1, "account_health tidak ketemu"

# temukan akhir fungsi (baris berikutnya yang diawali 'def ' setelah body)
m = re.search(r"\ndef (?!account_health)", src[i:])
end = i + m.start() + 1 if m else len(src)

src = src[:i] + NEW + src[end:]

io.open(P, "w", encoding="utf-8").write(src)
print("PATCH SELESAI:", P)
