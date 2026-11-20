"""df_source.py — satu sumber kebenaran untuk security_device_fingerprint.

Masalah yang diselesaikan:
  Ada 3 format DF berbeda di repo ini:
    - device_df.json      : 2534 char, blob SZ-SDK — BUKAN fingerprint
                            (prefix JxcBAAAABAAAAIAAA muncul di SEC.txt,
                             SEC_TOKENS.json, SAP_CAPTURE.json, MITM.jsonl
                             di konteks df.infra.sz.shopee.co.id/v2/shpsec/web/report)
    - DFP_TOKEN.txt       : 139 char, 5 segmen pipe (format request HTTP, TERVERIFIKASI
                            sukses di CC_capture.json error=0)
    - ivs_engine.py:44    : 32 hex char (SALAH — hardcode, bukan format Shopee)

Urutan prioritas pengambilan:
  1. DF dari respons init_v2 (paling benar: server yang kasih untuk sesi itu)
  2. DFP_TOKEN.txt / *.fp  (5 segmen pipe — format request HTTP yang terverifikasi)
  3. kosong                (jangan pernah pakai blob SDK atau 32-hex palsu)

device_df.json SENGAJA DITOLAK. df_harvest.py:143 memakai
  best = max(dfs.keys(), key=len)
yang memilih string terpanjang — hasilnya blob report SZ-SDK 2534 char,
bukan device fingerprint. Tidak ada satu pun bukti call sukses memakai
format itu sebagai security_device_fingerprint.

Dipakai oleh: ivs_engine.py, cp_v3.py, changenumfast.py

Alasan desain (dari crosscheck dengan Muse):
  - AES-GCM nonce reuse berbahaya -> DF tidak boleh di-reuse lintas flow
  - Segmen [1] 68B kemungkinan ciphertext+tag, terikat ke nonce segmen [2]
  - Jadi: generate fresh per flow, cache HANYA di dalam flow itu
"""
from __future__ import annotations

import json
import os
import time

BASE = os.path.dirname(os.path.abspath(__file__))

# Kandidat file, urut prioritas. device_df.json TIDAK dimasukkan (ditolak).
CANDIDATES = ("DFP_TOKEN.txt", "device_fp.txt", "device_fp.json")

# DF yang diketahui salah — tolak kalau ketemu
_INVALID = {
    "e6d7f3a1c8b94e2d5f0a7c3b1d8e4f6a",  # hardcode lama ivs_engine.py:44
}

# Prefix blob SZ-SDK yang salah label sebagai DF
_SDK_BLOB_PREFIX = "JxcBAAAABAAAAIAAA"


def _valid(df: str) -> bool:
    """DF valid HARUS 5 segmen pipe (format request HTTP Shopee).

    Fail-closed: kalau bukan format pipe 5 segmen, tolak. Lebih baik kosong
    (dan error jelas) daripada kirim blob yang server tidak kenal.
    """
    if not df or not isinstance(df, str):
        return False
    df = df.strip()
    if df in _INVALID:
        return False
    # blob SZ-SDK salah label
    if df.startswith(_SDK_BLOB_PREFIX):
        return False
    # 32 hex tanpa pipe = format palsu, bukan Shopee
    if len(df) == 32 and "|" not in df and all(c in "0123456789abcdef" for c in df.lower()):
        return False
    parts = df.split("|")
    if len(parts) != 5:
        return False
    # dua segmen pertama wajib base64 non-kosong
    if len(parts[0]) < 8 or len(parts[1]) < 8:
        return False
    return True


def _read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw:
            return ""
        # JSON?
        if raw.startswith("{"):
            return (json.loads(raw).get("security_device_fingerprint") or "").strip()
        # plain text satu baris
        return raw.splitlines()[0].strip()
    except Exception:
        return ""


def from_disk() -> str:
    """Ambil DF dari file, urut prioritas. Kosong kalau tidak ada yang valid."""
    for name in CANDIDATES:
        p = os.path.join(BASE, name)
        if not os.path.exists(p):
            continue
        df = _read_file(p)
        if _valid(df):
            return df
    return ""


def from_init(data: dict) -> str:
    """Ambil DF dari respons init_v2 (sumber paling benar)."""
    if not isinstance(data, dict):
        return ""
    d = data.get("data") if isinstance(data.get("data"), dict) else data
    df = (d.get("security_device_fingerprint") or "").strip()
    return df if _valid(df) else ""


def resolve(init_data: dict | None = None) -> str:
    """DF untuk flow ini: init_v2 dulu, lalu disk, lalu kosong."""
    df = from_init(init_data or {})
    if df:
        return df
    return from_disk()


def describe(df: str) -> str:
    """Ringkasan bentuk DF untuk log — tanpa membocorkan isi."""
    if not df:
        return "kosong"
    segs = df.split("|")
    if len(segs) > 1:
        return f"{len(df)}B/{len(segs)}seg pipe [" + ",".join(str(len(s)) for s in segs) + "]"
    return f"{len(df)}B tanpa pipe"


def save(df: str, name: str = "DFP_TOKEN.txt") -> bool:
    """Simpan DF baru ke disk (hanya kalau valid)."""
    if not _valid(df):
        return False
    p = os.path.join(BASE, name)
    try:
        with open(p, "w", encoding="utf-8") as f:
            f.write(df.strip())
        return True
    except Exception:
        return False


if __name__ == "__main__":
    df = from_disk()
    print("from_disk :", describe(df))
    print("valid     :", _valid(df))
    print()
    print("cek hardcode lama:", _valid("e6d7f3a1c8b94e2d5f0a7c3b1d8e4f6a"), "(harus False)")
