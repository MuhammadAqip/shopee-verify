# -*- coding: utf-8 -*-
"""mitm_ivs.py — addon mitmproxy: tangkap v_token dari /anti_fraud/ivs/methods."""
from __future__ import annotations

import json
import os
import time

from mitmproxy import ctx, http

OUT = os.environ.get("MITM_OUT", "/root/shopee-verify/mitm_ivs.jsonl")


def _dump(flow: http.HTTPFlow, tag: str, payload):
    rec = {"t": round(time.time(), 3), "tag": tag,
           "method": flow.request.method, "url": flow.request.url,
           "status": flow.response.status_code if flow.response else None,
           "req_body": flow.request.get_text(strict=False)[:4000],
           "resp_body": payload[:8000] if isinstance(payload, str) else payload}
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    ctx.log.info(f"[IVS] {tag} {flow.request.method} {flow.request.url.split('?')[0]}")


def response(flow: http.HTTPFlow) -> None:
    u = flow.request.url
    if "/anti_fraud/ivs" in u:
        _dump(flow, "ivs", flow.response.get_text(strict=False))


def request(flow: http.HTTPFlow) -> None:
    u = flow.request.url
    if "/api/v4/account/management/change_phone" in u:
        _dump(flow, "cp_req", None)
