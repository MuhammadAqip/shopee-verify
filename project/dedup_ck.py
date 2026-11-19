# -*- coding: utf-8 -*-
"""dedup_ck.py — dedupe cookie jar hasil browser (Shopee menolak duplikat)."""
import sys

src = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_solved.txt"
dst = sys.argv[2] if len(sys.argv) > 2 else "/root/shopee-verify/ck_clean.txt"

seen = {}
order = []
for part in open(src).read().strip().split(";"):
    part = part.strip()
    if not part or "=" not in part:
        continue
    k, _, v = part.partition("=")
    k, v = k.strip(), v.strip()
    if not k or not v:
        continue
    if k not in seen:
        order.append(k)
    seen[k] = v          # nilai terakhir menang

jar = "; ".join(f"{k}={seen[k]}" for k in order)
open(dst, "w").write(jar)
print(f"{len(order)} cookie unik -> {dst} ({len(jar)} B)")
print("SPC_SEC_SI:", seen.get("SPC_SEC_SI", "")[:30], "…")
print("SPC_ST    :", seen.get("SPC_ST", "")[:30], "…")
