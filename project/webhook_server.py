# -*- coding: utf-8 -*-
"""webhook_server.py — penerima callback QRIS GoPay Merchant (GPM).

Mengikuti pola shopbot/app/webhook.py:
  POST /webhook/gpm
  Header X-Signature : HMAC-SHA256(raw_body, secret) hex  (secret = API key / webhook secret)
  Header X-Callback-Event: transaction.received
  Body: {"event","timestamp","transaction":{"id","amount","status",...}}

`order_id` yang kita kirim saat generate-qris DIPANTULKAN sebagai
`transaction.id` di webhook. Jadi kita cocokkan langsung ke orders.

Selalu balas 200 setelah signature valid — provider akan retry kalau non-2xx.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import sys
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import uvicorn

BASE = Path("/root/shopee-verify")
DB_PATH = BASE / "bot_db.json"
LOG = logging.getLogger("webhook")

PAID = {"settlement", "success", "succeeded", "paid", "capture", "captured"}


def _secrets() -> list[str]:
    out = []
    for k in ("GPM_WEBHOOK_SECRET", "GPM_API_KEY"):
        v = (os.environ.get(k) or "").strip()
        if v and v not in out:
            out.append(v)
    return out


def verify_sig(raw: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    got = signature.strip()
    if got.lower().startswith("sha256="):
        got = got[7:]
    for s in _secrets():
        mac = hmac.new(s.encode(), raw, hashlib.sha256).hexdigest()
        if hmac.compare_digest(mac, got.lower()):
            return True
    return False


def _load() -> dict:
    try:
        return json.loads(DB_PATH.read_text())
    except Exception:
        return {"users": {}, "orders": {}, "stats": {}}


def _save(db: dict):
    tmp = DB_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(db, indent=1, ensure_ascii=False))
    tmp.replace(DB_PATH)


def mark_paid(refs: list[str], amount) -> dict | None:
    """Tandai order lunas + tambah saldo. Idempoten.

    `refs` berisi semua id yang mungkin dikirim GPM (order_id kita dan/atau
    transaction_id uuid). Semua alias mengarah ke record yang sama, jadi
    penandaan `paid` harus dilakukan ke SEMUA alias — kalau tidak, webhook
    berikutnya yang datang lewat alias lain akan memproses ulang.
    """
    db = _load()
    orders = db.setdefault("orders", {})
    keys = [r for r in refs if r in orders]
    if not keys:
        return None
    hits = [orders[k] for k in keys]
    primary = next((h for h in hits if h.get("status") == "paid"), None)
    if primary:
        LOG.info("ref=%s sudah paid, dilewati", refs[0])
        return primary

    hit = hits[0]
    aliases = set(hit.get("refs") or []) | set(keys) | {
        k for k, v in orders.items() if v is hit}
    for k in aliases:
        if k in orders:
            orders[k]["status"] = "paid"
            orders[k]["paid_at"] = int(time.time())
            if amount is not None:
                orders[k]["paid_amount"] = amount

    uid = str(hit["uid"])
    u = db.setdefault("users", {}).setdefault(uid, {
        "id": hit["uid"], "saldo": 0, "created": int(time.time()),
        "total_checks": 0, "name": ""})
    u["saldo"] = int(u.get("saldo", 0)) + int(hit.get("poin", 0))
    _save(db)
    return {"order": hit, "saldo": u["saldo"]}


def notify(hit: dict):
    """Kirim konfirmasi ke Telegram (best-effort, tidak memblokir webhook)."""
    try:
        import urllib.request
        token = os.environ.get("SHOPEE_BOT_TOKEN", "").strip()
        if not token:
            return
        od = hit["order"]
        text = (f"✅ <b>Pembayaran diterima</b>\n"
                f"Order: <code>{od.get('order_id','-')}</code>\n"
                f"+<code>{od.get('poin',0)}</code> cek\n"
                f"Saldo: <code>{hit['saldo']}</code>")
        body = json.dumps({"chat_id": od.get("chat") or od.get("uid"),
                           "text": text, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=body,
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=12).read()
    except Exception as e:
        LOG.warning("notify gagal: %s", e)


app = FastAPI(title="shopee-bot-gpm-webhook", docs_url=None, redoc_url=None)


@app.get("/webhook/gpm")
async def gpm_ping():
    return {"ok": True, "provider": "gopay-merchant",
            "event": "transaction.received"}


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/webhook/gpm")
async def gpm_callback(request: Request):
    raw = await request.body()
    sig = request.headers.get("X-Signature")

    if not verify_sig(raw, sig):
        LOG.warning("signature invalid ip=%s",
                    request.client.host if request.client else "?")
        raise HTTPException(status_code=401, detail="invalid signature")

    try:
        body = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="bad json")

    event = body.get("event") or request.headers.get("X-Callback-Event", "")
    if event != "transaction.received":
        LOG.info("event lain diabaikan: %s", event)
        return JSONResponse({"success": True})

    tx = body.get("transaction") or {}
    refs = [str(v) for v in (tx.get("id"), tx.get("order_id"),
                             tx.get("reference")) if v]
    status = str(tx.get("status") or "").strip().lower()
    amount = tx.get("amount")

    if not refs:
        LOG.warning("payload tanpa id: %s", body)
        return JSONResponse({"success": True})

    if status not in PAID:
        LOG.info("belum lunas ref=%s status=%s", refs[0], status)
        return JSONResponse({"success": True})

    try:
        hit = mark_paid(refs, amount)
        if hit:
            LOG.info("ref=%s LUNAS -> saldo %s", refs[0], hit["saldo"])
            import threading
            threading.Thread(target=notify, args=(hit,), daemon=True).start()
        else:
            LOG.warning("ref=%s lunas tapi order tidak ada di DB", refs[0])
    except Exception:
        LOG.exception("mark_paid gagal ref=%s", refs[0])

    return JSONResponse({"success": True})


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    host = os.environ.get("WEBHOOK_HOST", "0.0.0.0")
    port = int(os.environ.get("WEBHOOK_PORT", "8082"))
    LOG.info("webhook listening %s:%s", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=True)


if __name__ == "__main__":
    main()
