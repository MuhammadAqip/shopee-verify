"""mitm_addon.py — capture LENGKAP semua request/response Shopee ke JSONL.

Dipakai via: mitmdump -s mitm_addon.py --mode upstream:http://127.0.0.1:18080
(upstream = relay residensial yang sudah hidup, jadi IP asli tetap residensial)

Yang direkam:
  - request: url, method, headers (SAP penuh), post body
  - response: status, body
  - JS: setiap file .js yang lewat (nama + size) -> kandidat chunk finalisasi
"""
import json
import time
import os

OUT = "/root/shopee-verify/MITM_FULL.jsonl"
T0 = time.time()
JS = "/root/shopee-verify/mitm_js.txt"


def w(obj):
    obj["t"] = round(time.time() - T0, 2)
    with open(OUT, "a") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def request(flow):
    u = flow.request.url
    if "shopee" not in u and "susercontent" not in u:
        return
    if u.endswith(".js") or ".js?" in u:
        with open(JS, "a") as f:
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
    w({"kind": "REQ", "url": u[:400], "method": flow.request.method,
       "sap": sap, "body": body})


def response(flow):
    u = flow.request.url
    if "/api/" not in u:
        return
    try:
        b = flow.response.get_text(strict=False)[:4000]
    except Exception:
        b = ""
    w({"kind": "RSP", "url": u[:400], "status": flow.response.status_code, "body": b})
