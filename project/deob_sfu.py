#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""deob_sfu.py — deobfuscate sfu-stable.js string table.

Alfabet custom: evdqphkgrfmiotbyjlxczanswuTMBGWXRCAEPIZNHFLUDSVKOQJY4912758063+/=
Tiap string literal di-decode, lalu seluruh file diganti pakai versi plaintext.

Output: sfu_deob.js (file baru, string sudah plaintext)
"""
import re, base64, sys, json

SRC = sys.argv[1] if len(sys.argv) > 1 else "sdkjs/sfu-stable.c3d38f8e0e81e513.2023.js"
DST = sys.argv[2] if len(sys.argv) > 2 else "sfu_deob.js"

ALPHA = "evdqphkgrfmiotbyjlxczanswuTMBGWXRCAEPIZNHFLUDSVKOQJY4912758063+/="
STD = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
TBL = str.maketrans(ALPHA, STD)

print(f"baca {SRC}", flush=True)
s = open(SRC, encoding="utf-8", errors="ignore").read()
print(f"  {len(s)}B", flush=True)

decoded_count = 0
mapping = {}


def dec(c):
    try:
        raw = base64.b64decode(c.translate(TBL) + "=" * (-len(c) % 4))
        txt = raw.decode("utf-8")
        return txt
    except Exception:
        return None


out = []
i = 0
n = len(s)
in_str = False
buf = []
quote = None
result = []

# sapu string literal dengan regex, ganti yang berhasil di-decode
pat = re.compile(r'"([A-Za-z0-9+/=]{16,})"|\'([A-Za-z0-9+/=]{16,})\'')

def repl(m):
    global decoded_count
    body = m.group(1) or m.group(2)
    q = '"' if m.group(1) else "'"
    t = dec(body)
    if t and t.isprintable() and len(t) >= 3:
        decoded_count += 1
        mapping[body[:40]] = t[:120]
        esc = t.replace("\\", "\\\\").replace(q, "\\" + q)
        esc = esc.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        return f"{q}{esc}{q}"
    return m.group(0)

new = pat.sub(repl, s)
open(DST, "w", encoding="utf-8").write(new)

print(f"\n=== {decoded_count} string didekode ===", flush=True)
print(f"-> {DST} ({len(new)}B)", flush=True)

json.dump(mapping, open("sfu_strings.json", "w"), indent=1, ensure_ascii=False)

# sekarang cari header name & fungsi kripto
KEYS = ["x-sap", "sap-sec", "sap-ri", "Signature", "signature",
        "af-ac", "enc-dat", "sz-token", "HmacSHA", "sha256", "AES",
        "encrypt", "hmac", "secret", "appkey", "app_key"]
print("\n=== cari keyword di file deob ===", flush=True)
for k in KEYS:
    hits = [m.start() for m in re.finditer(re.escape(k), new)]
    if hits:
        print(f"  {k:16s}: {len(hits)} hit @ {hits[:4]}", flush=True)
