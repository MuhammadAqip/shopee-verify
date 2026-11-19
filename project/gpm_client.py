# -*- coding: utf-8 -*-
"""gpm_client.py — QRIS GoPay Merchant untuk topup saldo bot.

Base : https://gopay.hidepulsa.net   ·   Auth: header X-API-Key
  POST /api/payment/generate-qris  {amount, order_id}
  GET  /api/payment/status/<order_id>
  POST /api/payment/cancel/<order_id>
  GET  /api/wallet/balance
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request

BASE_DEFAULT = "https://gopay.hidepulsa.net"
PAID = {"settlement", "success", "succeeded", "paid", "capture", "captured"}


class GPMError(Exception):
    pass


def _env(key: str, default: str = "") -> str:
    return (os.environ.get(key) or default).strip()


class GPM:
    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 timeout: int = 25):
        self.key = (api_key or _env("GPM_API_KEY")).strip()
        self.base = (base_url or _env("GPM_BASE_URL", BASE_DEFAULT)).rstrip("/")
        self.timeout = timeout

    def _req(self, method: str, path: str, body: dict | None = None) -> dict:
        if not self.key:
            raise GPMError("GPM_API_KEY kosong")
        # Cloudflare 1010 memblokir TLS fingerprint urllib; curl lolos.
        import subprocess
        args = ["curl", "-sS", "--max-time", str(self.timeout),
                "-X", method,
                "-H", f"X-API-Key: {self.key}",
                "-H", "Accept: application/json",
                "-H", "Content-Type: application/json",
                "-w", "\n%{http_code}"]
        if body is not None:
            args += ["-d", json.dumps(body)]
        args.append(self.base + path)
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=self.timeout + 10)
        except subprocess.TimeoutExpired:
            raise GPMError("timeout")
        out = (r.stdout or "").rstrip("\n")
        if "\n" not in out:
            raise GPMError(f"curl gagal: {(r.stderr or '')[:120]}")
        raw, code = out.rsplit("\n", 1)
        try:
            code_i = int(code.strip())
        except Exception:
            code_i = 0
        try:
            j = json.loads(raw) if raw.strip() else {}
        except Exception:
            raise GPMError(f"respons bukan JSON: {raw[:120]}")
        if code_i >= 400:
            msg = j.get("message") or j.get("error") or j.get("title") or f"HTTP {code_i}"
            if code_i == 401:
                msg = "API key GPM ditolak (401)"
            if code_i in (502, 503, 504):
                msg = f"provider down (HTTP {code_i}) — coba lagi nanti"
            raise GPMError(msg)
        return j if isinstance(j, dict) else {"data": j}

    def balance(self) -> float:
        j = self._req("GET", "/api/wallet/balance")
        d = j.get("data") or j
        for k in ("effective_balance", "net", "overall", "balance"):
            if k in d:
                try:
                    return float(d[k])
                except Exception:
                    pass
        return 0.0

    def qris(self, amount: int, order_id: str) -> dict:
        j = self._req("POST", "/api/payment/generate-qris",
                      {"amount": int(amount), "order_id": order_id})
        p = j.get("data") if isinstance(j.get("data"), dict) else j
        qr = (p.get("qr_string") or p.get("qris") or p.get("qr")
              or j.get("qr_string") or "")
        if not qr:
            raise GPMError("respons tanpa qr_string")
        # GPM memberi `order_id` (milik kita, dipantulkan) DAN `transaction_id`
        # (uuid internal). Webhook bisa mengirim salah satunya sebagai
        # transaction.id, jadi KEDUANYA harus disimpan sebagai kunci.
        refs = []
        for k in ("order_id", "transaction_id", "id", "reference"):
            v = p.get(k) or j.get(k)
            if v and str(v) not in refs:
                refs.append(str(v))
        if order_id not in refs:
            refs.insert(0, order_id)
        return {
            "order_id": refs[0],
            "refs": refs,
            "qr_string": qr,
            "qr_url": p.get("qr_url") or j.get("qr_url") or "",
            "checkout_url": p.get("checkout_url") or j.get("checkout_url") or "",
            "expiry": str(p.get("expiry_time") or p.get("expiry") or ""),
            "raw": j,
        }

    def status(self, order_id: str) -> dict:
        j = self._req("GET", f"/api/payment/status/{order_id}")
        d = j.get("data") if isinstance(j.get("data"), dict) else j
        st = str(d.get("status") or d.get("transaction_status")
                 or j.get("status") or "").lower()
        return {"status": st, "paid": st in PAID, "raw": j}

    def cancel(self, order_id: str) -> dict:
        return self._req("POST", f"/api/payment/cancel/{order_id}")

    @staticmethod
    def verify_sig(raw: bytes, sig: str | None, *secrets: str | None) -> bool:
        if not sig:
            return False
        got = sig.strip()
        if got.lower().startswith("sha256="):
            got = got[7:]
        for s in secrets:
            s = (s or "").strip()
            if not s:
                continue
            mac = hmac.new(s.encode(), raw, hashlib.sha256).hexdigest()
            if hmac.compare_digest(mac, got.lower()):
                return True
        return False
