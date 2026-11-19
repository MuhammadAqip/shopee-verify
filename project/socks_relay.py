# -*- coding: utf-8 -*-
"""
socks_relay.py — HTTP proxy lokal yang meneruskan ke SOCKS5 upstream
(dengan autentikasi). Chromium tidak bisa SOCKS5+auth, jadi ini jembatannya.

Jalankan:
    python3 socks_relay.py 18080
lalu di Playwright:
    proxy={"server": "http://127.0.0.1:18080"}

Upstream diambil dari env:
    UP_USER, UP_PASS, UP_HOST, UP_PORT
"""
from __future__ import annotations

import os
import socket
import socketserver
import struct
import sys
import threading

UP_HOST = os.environ.get("UP_HOST", "sg.gb.vsproxy.org")
UP_PORT = int(os.environ.get("UP_PORT", "12000"))
UP_USER = os.environ.get("UP_USER", "")
UP_PASS = os.environ.get("UP_PASS", "")


def read_exact(sock, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("upstream closed")
        buf += chunk
    return buf


def socks5_connect(host: str, port: int) -> socket.socket:
    s = socket.create_connection((UP_HOST, UP_PORT), timeout=45)
    s.settimeout(45)
    # greeting: versi 5, 1 metode (user/pass = 0x02)
    s.sendall(b"\x05\x01\x02")
    resp = read_exact(s, 2)
    if resp[0] != 5 or resp[1] != 2:
        raise ConnectionError(f"socks greet rejected: {resp!r}")
    # auth
    u, p = UP_USER.encode(), UP_PASS.encode()
    s.sendall(bytes([1, len(u)]) + u + bytes([len(p)]) + p)
    ar = read_exact(s, 2)
    if ar[1] != 0:
        raise ConnectionError("socks auth failed")
    # connect (domain)
    hb = host.encode()
    req = bytes([5, 1, 0, 3, len(hb)]) + hb + struct.pack(">H", port)
    s.sendall(req)
    rep = read_exact(s, 4)
    if rep[1] != 0:
        raise ConnectionError(f"socks connect failed code={rep[1]}")
    atyp = rep[3]
    if atyp == 1:
        read_exact(s, 4)
    elif atyp == 3:
        ln = read_exact(s, 1)[0]
        read_exact(s, ln)
    elif atyp == 4:
        read_exact(s, 16)
    read_exact(s, 2)
    return s


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        cli = self.request
        try:
            cli.settimeout(60)
            head = b""
            while b"\r\n\r\n" not in head:
                chunk = cli.recv(4096)
                if not chunk:
                    return
                head += chunk
                if len(head) > 65536:
                    return

            line = head.split(b"\r\n", 1)[0].decode("latin-1")
            parts = line.split()
            if len(parts) < 3:
                return
            method, target = parts[0], parts[1]

            if method.upper() == "CONNECT":
                host, _, port = target.rpartition(":")
                port = int(port or 443)
                up = socks5_connect(host, port)
                cli.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                rest = head.split(b"\r\n\r\n", 1)[1] if b"\r\n\r\n" in head else b""
                if rest:
                    up.sendall(rest)
                self.pipe(cli, up)
                return

            # HTTP biasa
            if target.startswith("http://"):
                rest_path = target[7:]
                hostpart, _, path = rest_path.partition("/")
                host, _, port = hostpart.partition(":")
                port = int(port or 80)
                path = "/" + path if path else "/"
            elif target.startswith("/"):
                hosthdr = ""
                for ln in head.split(b"\r\n")[1:]:
                    if ln.lower().startswith(b"host:"):
                        hosthdr = ln.split(b":", 1)[1].strip().decode()
                        break
                host, _, port = hosthdr.partition(":")
                port = int(port or 80)
                path = target
            else:
                cli.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                return

            up = socks5_connect(host, port)
            lines = head.split(b"\r\n")
            lines[0] = f"{method} {path} HTTP/1.1".encode()
            out = b"\r\n".join(lines)
            if b"Proxy-Connection" in out:
                out = out.replace(b"Proxy-Connection", b"Connection")
            up.sendall(out)
            self.pipe(cli, up)
        except Exception:
            try:
                cli.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            except Exception:
                pass
        finally:
            try:
                cli.close()
            except Exception:
                pass

    @staticmethod
    def pipe(a, b):
        def fwd(src, dst):
            try:
                while True:
                    data = src.recv(8192)
                    if not data:
                        break
                    dst.sendall(data)
            except Exception:
                pass
            finally:
                try:
                    dst.shutdown(socket.SHUT_WR)
                except Exception:
                    pass
        t = threading.Thread(target=fwd, args=(b, a), daemon=True)
        t.start()
        fwd(a, b)
        t.join(timeout=60)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18080
    print(f"[relay] 0.0.0.0:{port} -> socks5://{UP_HOST}:{UP_PORT}")
    Server(("127.0.0.1", port), Handler).serve_forever()
