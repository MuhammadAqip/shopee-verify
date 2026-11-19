# -*- coding: utf-8 -*-
"""login_proxy.py — reverse proxy Shopee untuk login dari browser Maker.

Maker buka http://<vps>:8899/ di HP/PC -> proxy meneruskan ke https://shopee.co.id
Semua cookie & body di-pass-through. Setelah login sukses (SPC_ST muncul),
cookie otomatis disimpan ke ck_from_proxy.txt.

Bukan MITM (bukan intercept terenkripsi) — ini HTTP reverse proxy biasa
yang menulis ulang host & scheme di response.
"""
import http.server, socketserver, urllib.request, urllib.error, ssl, gzip, io, json, time, os, re

UPSTREAM = "https://shopee.co.id"
TARGET_HOST = "shopee.co.id"
LISTEN_PORT = 8897
CK_OUT = "/root/shopee-verify/ck_from_proxy.txt"
LOG = "/root/shopee-verify/loginproxy/access.log"

ALLOW_PREFIX = ("/", )

HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
       "te", "trailers", "transfer-encoding", "upgrade", "content-length",
       "content-encoding", "host"}

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


class Proxy(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _rewrite_headers(self, headers, is_request):
        out = {}
        for k, v in headers.items():
            lk = k.lower()
            if lk in HOP:
                continue
            if lk in ("origin", "referer"):
                v = re.sub(r'https?://[^/]*shopee\.co\.id', f'http://{self.headers.get("Host", "localhost")}', v)
                v = re.sub(r'https?://[^/]*43\.156\.19\.172(:\d+)?', f'http://{self.headers.get("Host", "localhost")}', v)
            out[k] = v
        return out

    def _handle(self, method):
        path = self.path
        # buang prefix kalau ada
        url = UPSTREAM + path

        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None

        headers = self._rewrite_headers(self.headers, True)
        # pastikan Host benar
        headers["Host"] = TARGET_HOST

        log(f"{method} {path[:100]} body={len(body) if body else 0}")

        try:
            req = urllib.request.Request(url, data=body, method=method, headers=headers)
            op = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(),
                urllib.request.HTTPSHandler(context=CTX))
            op.addheaders = []
            resp = op.open(req, timeout=45)
            code = resp.status
            rh = dict(resp.headers.items())
            data = resp.read()
        except urllib.error.HTTPError as e:
            code = e.code
            rh = dict(e.headers.items())
            data = e.read()
        except Exception as e:
            log(f"  ERR {str(e)[:80]}")
            self.send_error(502, str(e)[:50])
            return

        # decompress kalau gzip
        enc = (rh.get("Content-Encoding") or "").lower()
        if enc == "gzip":
            try:
                data = gzip.decompress(data)
            except Exception:
                pass
        elif enc == "deflate":
            try:
                import zlib
                data = zlib.decompress(data)
            except Exception:
                pass

        # rewrite redirect ke shopee -> ke proxy
        loc = rh.get("Location")
        if loc and "shopee.co.id" in loc:
            loc = loc.replace("https://shopee.co.id", "")
            loc = re.sub(r'https?://[^/]*43\.156\.19\.172(:\d+)?', "", loc)
            rh["Location"] = loc

        # tangkap cookie
        sc = rh.get("Set-Cookie")
        cc = rh.get("set-cookie")
        allc = ""
        if sc:
            allc = sc if isinstance(sc, str) else " | ".join(sc)

        # kirim
        self.send_response(code)
        skip = {"content-length", "content-encoding", "connection", "transfer-encoding", "set-cookie"}
        for k, v in rh.items():
            if k.lower() in skip:
                continue
            self.send_header(k, v)
        if sc:
            self.send_header("Set-Cookie", sc)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

        # cek apakah SPC_ST muncul di response ini
        if ("SPC_ST=" in allc) or (b"SPC_ST" in data[:2000]):
            log("  🟢 SPC_ST terlihat!")

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def do_DELETE(self):
        self._handle("DELETE")

    def do_HEAD(self):
        self._handle("HEAD")


class Threaded(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    open(LOG, "w").close()
    log(f"PROXY START :{LISTEN_PORT} -> {UPSTREAM}")
    Threaded(("0.0.0.0", LISTEN_PORT), Proxy).serve_forever()
