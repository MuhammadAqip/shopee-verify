# -*- coding: utf-8 -*-
"""
mitm_capture.py — mitmproxy addon: rekam semua request Shopee account/phone.

Filter ketat: hanya /api/v4/account/*, /api/v4/otp/*, /api/v2/authentication/*
Simpan JSONL + body lengkap. Kredensial di-mask.

Jalankan:
  mitmdump -s mitm_capture.py --listen-port 8080 -q \
           --set outfile=/root/shopee-verify/mitm_phone.jsonl
"""
from __future__ import annotations

import json
import os
import time

from mitmproxy import ctx, http

OUT = os.environ.get("MITM_OUT", "/root/shopee-verify/mitm_phone.jsonl")

WATCH = ("/api/v4/account", "/api/v4/otp", "/api/v2/authentication",
         "/api/v4/verify", "/api/v4/ivs", "/api/v4/payment")

SENSITIVE = ("spc_st", "csrftoken", "spc_r_t_id", "spc_t_id", "spc_sec_si",
             "password", "otp_code", "vcode", "cookie")


def mask(s: str, keep: int = 24) -> str:
    if not s:
        return s
    if len(s) <= keep:
        return "***"
    return s[:keep] + f"…({len(s)}B)"


class Capture:
    def __init__(self):
        self.fh = None

    def load(self, loader):
        loader.add_option("outfile", str, OUT, "JSONL output")

    def running(self):
        path = ctx.options.outfile or OUT
        self.fh = open(path, "a", buffering=1)
        ctx.log.info(f"[mitm] capture -> {path}")

    def response(self, flow: http.HTTPFlow):
        url = flow.request.pretty_url
        if not any(w in url for w in WATCH):
            return
        try:
            req_txt = flow.request.get_text(strict=False) or ""
            res_txt = flow.response.get_text(strict=False) or ""
        except Exception:
            req_txt, res_txt = "", ""

        rec = {
            "ts": int(time.time()),
            "status": flow.response.status_code,
            "method": flow.request.method,
            "url": url.split("?")[0],
            "query": flow.request.query.multi_items() or None,
            "req_headers": {k: v for k, v in flow.request.headers.items()
                            if k.lower().startswith(("x-", "content-", "af-", "sec-"))
                            and k.lower() != "cookie"},
            "req_body": req_txt[:3000] if req_txt else None,
            "res_body": res_txt[:5000] if res_txt else None,
        }
        self.fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        ctx.log.info(f"{rec['status']} {rec['method']} {rec['url'][-60:]}")


addons = [Capture()]
