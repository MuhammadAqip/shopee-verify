# -*- coding: utf-8 -*-
"""login_proxy3.py — FIX Set-Cookie multi-value (bug utama).

Bedanya dari v2:
  * Set-Cookie dikirim ULANG satu-per-satu (bukan dict collision)
  * Cookie domain dibuang supaya browser simpan untuk IP
  * Tracking POST login_by_password + capture SPC_ST ke file
"""
import http.server, socketserver, urllib.request, urllib.error, ssl, gzip, zlib
import json, time, os, re, sys

LISTEN_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8895
UPSTREAM = "https://shopee.co.id"
TARGET_HOST = "shopee.co.id"
LOG = "/root/shopee-verify/loginproxy/access3.log"
CK_OUT = "/root/shopee-verify/ck_from_proxy.txt"
HOST_SELF = f"43.156.19.172:{LISTEN_PORT}"

HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
       "te", "trailers", "transfer-encoding", "upgrade", "content-length",
       "content-encoding", "host"}

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

CAPTURED = {}


def log(m):
    line = f"[{time.strftime('%H:%M:%S')}] {m}"
    print(line, flush=True)
    try:
        open(LOG, "a").write(line + "\n")
    except Exception:
        pass


def rewrite(data, ct):
    if not data or len(data) > 3_000_000:
        return data
    if not any(x in (ct or "") for x in ("html", "javascript", "json")):
        return data
    try:
        s = data.decode("utf-8", "ignore")
    except Exception:
        return data
    o = s
    s = s.replace("https://shopee.co.id", "").replace("http://shopee.co.id", "")
    s = s.replace(f"http://{HOST_SELF}", "").replace(f"https://{HOST_SELF}", "")
    s = s.replace(f"//{HOST_SELF}", "").replace(HOST_SELF, "shopee.co.id")
    if "html" in (ct or ""):
        inj = '<base href="/"><meta http-equiv="Content-Security-Policy" content="">'
        if "<head" in s.lower():
            s = re.sub(r'(<head[^>]*>)', r'\1' + inj, s, count=1, flags=re.I)
    return s.encode("utf-8") if s != o else data


class Proxy(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _h(self, method):
        url = UPSTREAM + self.path
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else None
        hd = {}
        for k, v in self.headers.items():
            if k.lower() in HOP:
                continue
            if k.lower() in ("origin", "referer") and "43.156.19.172" in v:
                v = "https://shopee.co.id"
            hd[k] = v
        hd["Host"] = TARGET_HOST
        hd["Accept-Encoding"] = "gzip"

        log(f"{method} {self.path[:90]} b={len(body) if body else 0}")

        try:
            req = urllib.request.Request(url, data=body, method=method, headers=hd)
            op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=CTX))
            resp = op.open(req, timeout=50)
            code = resp.status
            # === FIX: get_all untuk multi-value header ===
            rh_items = resp.getheaders()
            data = resp.read()
        except urllib.error.HTTPError as e:
            code = e.code
            rh_items = e.headers.items()
            data = e.read()
        except Exception as e:
            log(f"  ERR {str(e)[:60]}")
            self.send_error(502, "up")
            return

        # decompress
        enc = ""
        rh = {}
        setcookies = []
        for k, v in rh_items:
            lk = k.lower()
            if lk == "set-cookie":
                setcookies.append(v)
            else:
                rh[k] = v
                if lk == "content-encoding":
                    enc = v.lower()
        if enc == "gzip":
            try: data = gzip.decompress(data)
            except Exception: pass
        elif enc == "deflate":
            try: data = zlib.decompress(data)
            except Exception: pass

        ct = rh.get("Content-Type", "")
        data = rewrite(data, ct)

        loc = rh.get("Location")
        if loc:
            if "shopee.co.id" in loc:
                loc = loc.replace("https://shopee.co.id", "").replace("http://shopee.co.id", "")
            if HOST_SELF in loc:
                loc = loc.replace(HOST_SELF, "shopee.co.id")
            rh["Location"] = loc

        # === FIX: bersihkan Set-Cookie satu-satu ===
        cleaned = []
        for sc in setcookies:
            sc = re.sub(r';\s*[Dd]omain=[^;]*', '', sc)
            sc = re.sub(r';\s*[Ss]ecure\b', '', sc)
            sc = re.sub(r';\s*[Ss]ame[Ss]ite=[^;]*', '', sc)
            cleaned.append(sc)
            nm = sc.split("=", 1)[0].strip()
            val = sc.split("=", 1)[1].split(";", 1)[0].strip() if "=" in sc else ""
            if nm and val:
                CAPTURED[nm] = val

        if "SPC_ST" in CAPTURED:
            open(CK_OUT, "w").write("; ".join(f"{k}={v}" for k, v in CAPTURED.items()))
            log(f"  🟢 SPC_ST OK — {len(CAPTURED)} cookie")

        # kirim response
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
        # === FIX: kirim SEMUA Set-Cookie ===
        for sc in cleaned:
            self.send_header("Set-Cookie", sc)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

        # deteksi login sukses
        if "login_by_password" in self.path:
            try:
                j = json.loads(data)
                log(f"  login response: error={j.get('error')} msg={str(j.get('error_msg') or '')[:50]}")
                if j.get("error") == 0:
                    log("  ✅✅ LOGIN SUKSES SERVER-SIDE")
            except Exception:
                log(f"  login body: {data[:200]}")

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
