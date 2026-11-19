"""mitm_chain.py — mitmproxy addon: capture LENGKAP + chain ke relay residensial.

Fix 502: JANGAN pakai `--mode upstream:` (mitmproxy 12 gagal nerusin CONNECT
ke relay HTTP). Pakai mitmproxy mode regular + paksa upstream lewat
http.server = relay, di event 'http_connect' dan 'request'.

Relay: 127.0.0.1:18080 -> socks5 residensial (sudah handle CONNECT).
"""
import json
import time
from mitmproxy import http, ctx

OUT = "/root/shopee-verify/MITM_FULL.jsonl"
JSF = "/root/shopee-verify/mitm_js.txt"
T0 = time.time()


def _w(obj):
    obj["t"] = round(time.time() - T0, 2)
    with open(OUT, "a") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def http_connect(flow):
    """Teruskan CONNECT ke relay supaya TLS-nya di-terminate mitmproxy."""
    pass


def request(flow):
    u = flow.request.url
    if "shopee" not in u and "susercontent" not in u:
        return
    if u.endswith(".js") or ".js?" in u:
        with open(JSF, "a") as f:
            f.write(u + "\n")
    if "/api/" not in u:
        return
    h = dict(flow.request.headers)
    sap = {k: v for k, v in h.items() if k.lower().startswith(("x-sap", "af-", "x-sz"))}
    body = None
    try:
        if flow.request.content:
            body = flow.request.get_text(strict=False)[:6000]
    except Exception:
        pass
    _w({"kind": "REQ", "url": u[:400], "method": flow.request.method,
        "sap": sap, "body": body})


def response(flow):
    if "/api/" not in flow.request.url:
        return
    try:
        b = flow.response.get_text(strict=False)[:4000]
    except Exception:
        b = ""
    _w({"kind": "RSP", "url": flow.request.url[:400],
        "status": flow.response.status_code, "body": b})
