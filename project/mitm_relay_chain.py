#!/usr/bin/env python3
"""mitm_relay_chain.py — mitmproxy yang nerusin SEMUA traffic lewat relay residensial.

Kenapa file ini: `--mode upstream:http://127.0.0.1:18080` -> 502 di mitmproxy 12.
Solusi: subclass HTTPFlow, paksa flow.server_conn.address ke relay, jadi
mitmproxy connect ke relay sebagai HTTP proxy biasa (bukan upstream mode).

Jalan: python3 mitm_relay_chain.py
  listen 8080 (proxy)  -> relay 18080 (socks5 residensial) -> Shopee

Capture: /root/shopee-verify/MITM_FULL.jsonl  +  mitm_js.txt
"""
import json
import time
import sys

from mitmproxy import http, options
from mitmproxy.tools import dump

RELAY_HOST = "127.0.0.1"
RELAY_PORT = 18080
OUT = "/root/shopee-verify/MITM_FULL.jsonl"
JSF = "/root/shopee-verify/mitm_js.txt"
T0 = time.time()


def _w(obj):
    obj["t"] = round(time.time() - T0, 2)
    with open(OUT, "a") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


class Chain:
    """Nerusin request lewat relay HTTP proxy (relay -> socks5 -> internet)."""

    def request(self, flow: http.HTTPFlow):
        # paksa mitmproxy connect ke relay, bukan langsung ke target
        try:
            flow.server_conn.via = ("http", (RELAY_HOST, RELAY_PORT))
        except Exception:
            pass

        u = flow.request.url
        if "shopee" not in u and "susercontent" not in u:
            return
        if u.endswith(".js") or ".js?" in u:
            with open(JSF, "a") as f:
                f.write(u + "\n")
        if "/api/" not in u:
            return
        h = dict(flow.request.headers)
        sap = {k: v for k, v in h.items()
               if k.lower().startswith(("x-sap", "af-", "x-sz"))}
        body = None
        try:
            if flow.request.content:
                body = flow.request.get_text(strict=False)[:6000]
        except Exception:
            pass
        _w({"kind": "REQ", "url": u[:400], "method": flow.request.method,
            "sap": sap, "body": body})

    def response(self, flow: http.HTTPFlow):
        if "/api/" not in flow.request.url:
            return
        try:
            b = flow.response.get_text(strict=False)[:4000]
        except Exception:
            b = ""
        _w({"kind": "RSP", "url": flow.request.url[:400],
            "status": flow.response.status_code, "body": b})


if __name__ == "__main__":
    import asyncio

    async def main():
        opts = options.Options(
            listen_port=8080,
            ssl_insecure=True,
            http2=False,
        )
        m = dump.DumpMaster(opts, with_termlog=False, with_dumper=False)
        m.addons.add(Chain())
        print("mitm chain listening :8080 -> relay :18080", flush=True)
        await m.run()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
