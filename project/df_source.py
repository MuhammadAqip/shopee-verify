"""df_source.py — satu sumber kebenaran untuk security_device_fingerprint.

Masalah yang diselesaikan:
  Ada 3 format DF berbeda di repo ini:
    - device_df.json      : 2534 char, protobuf-ish, 2 pipe (format penuh SDK)
    - DFP_TOKEN.txt       : 139 char, 5 segmen pipe (format request HTTP)
    - ivs_engine.py:44    : 32 hex char (SALAH — hardcode, bukan format Shopee)

Urutan prioritas pengambilan:
  1. DF dari respons init_v2 (paling benar: server yang kasih untuk sesi itu)
  2. DFP_TOKEN.txt / *.fp  (5 segmen pipe — format request HTTP yang terverifikasi)
  3. device_df.json        (format SDK penuh — valid untuk endpoint SDK-body)
  4. kosong                (jangan pernah hardcode 32-hex palsu)

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

# Kandidat file, urut prioritas
CANDIDATES = ("DFP_TOKEN.txt", "device_fp.txt", "device_fp.json", "device_df.json")

# DF yang diketahui salah — tolak kalau ketemu
_INVALID = {
    "e6d7f3a1c8b94e2d5f0a7c3b1d8e4f6a",  # hardcode lama ivs_engine.py:44
}


def _valid(df: str) -> bool:
    """DF dianggap valid kalau bukan placeholder dan panjangnya masuk akal."""
    if not df or not isinstance(df, str):
        return False
    df = df.strip()
    if df in _INVALID:
        return False
    # 32 hex tanpa pipe = format palsu, bukan Shopee
    if len(df) == 32 and "|" not in df and all(c in "0123456789abcdef" for c in df.lower()):
        return False
    return len(df) >= 16


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
