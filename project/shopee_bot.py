# -*- coding: utf-8 -*-
"""
shopee_bot.py — Telegram bot CEK NOMOR SHOPEE.

Arsitektur:
  bot (thread utama)  --pipe JSON-->  worker.py (Chromium)

Perintah:
  /start  /help  /saldo  /harga  /topup  /stats
  /cek 628xxx          cek 1 nomor
  /cek (reply)         cek dari teks pesan
  kirim .txt           batch dari file
  /admin /addcookie /reloadcookie /resetcookie

Harga: PRICE_PER_CHECK poin per nomor cek.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import re
import subprocess
import sys
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import telebot
from telebot import types
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from gpm_client import GPM, GPMError

# ================= KONFIG =================
BASE = Path("/root/shopee-verify")
PY = "/root/sniffenv/bin/python3"
WORKER = str(BASE / "worker.py")

BOT_TOKEN = os.environ.get("SHOPEE_BOT_TOKEN", "").strip()
ADMIN_IDS = {int(x) for x in os.environ.get("SHOPEE_ADMIN_IDS", "7341376283").split(",")
             if x.strip().isdigit()}

DB_PATH = BASE / "bot_db.json"
RESULT_DIR = BASE / "results"
COOKIE_DIR = BASE / "cookies"
RESULT_DIR.mkdir(exist_ok=True)
COOKIE_DIR.mkdir(exist_ok=True)

PRICE_PER_CHECK = int(os.environ.get("PRICE_PER_CHECK", "100"))
MAX_PER_CEK = 50
MAX_PER_BATCH = 500


def get_setting(key: str, default):
    """Baca setting admin dari DB (fallback ke default)."""
    try:
        with _db_lock:
            db = _load_db()
            return db.get("settings", {}).get(key, default)
    except Exception:
        return default


def set_setting(key: str, val):
    with _db_lock:
        db = _load_db()
        db.setdefault("settings", {})[key] = val
        _save_db(db)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("shopee-bot")

if not BOT_TOKEN:
    log.error("SHOPEE_BOT_TOKEN kosong. Isi env atau edit BOT_TOKEN di file ini.")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")


# ================= DB =================
_db_lock = threading.Lock()


def _load_db() -> dict:
    if DB_PATH.exists():
        try:
            return json.loads(DB_PATH.read_text())
        except Exception:
            pass
    return {"users": {}, "orders": {}, "stats": {"total_checks": 0}}


def _save_db(db: dict):
    tmp = DB_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(db, indent=1, ensure_ascii=False))
    tmp.replace(DB_PATH)


def _u(db, uid):
    return db["users"].setdefault(str(uid), {
        "id": uid, "saldo": 0, "created": int(time.time()),
        "total_checks": 0, "name": ""})


def get_user(uid: int) -> dict:
    with _db_lock:
        db = _load_db()
        u = _u(db, uid)
        _save_db(db)
        return dict(u)


def add_saldo(uid: int, amount: int) -> int:
    with _db_lock:
        db = _load_db()
        u = _u(db, uid)
        u["saldo"] = int(u.get("saldo", 0)) + amount
        _save_db(db)
        return u["saldo"]


def charge(uid: int, n: int) -> tuple[bool, int]:
    cost = n * PRICE_PER_CHECK
    with _db_lock:
        db = _load_db()
        u = _u(db, uid)
        cur = int(u.get("saldo", 0))
        if cur < cost:
            return False, cur
        u["saldo"] = cur - cost
        u["total_checks"] = int(u.get("total_checks", 0)) + n
        db["stats"]["total_checks"] = int(db["stats"].get("total_checks", 0)) + n
        _save_db(db)
        return True, u["saldo"]


# ================= WORKER CLIENT =================
class WorkerClient:
    """Bicara ke worker.py lewat stdin/stdout, satu job sekaligus."""

    def __init__(self):
        self.p = None
        self._id = 0
        self._lock = threading.Lock()
        self._q: dict[int, queue.Queue] = {}
        self._reader = None

    def start(self):
        with self._lock:
            if self.p and self.p.poll() is None:
                return
            self.p = subprocess.Popen(
                [PY, WORKER], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, bufsize=1)
            self._reader = threading.Thread(target=self._read_loop, daemon=True)
            self._reader.start()
            log.info("worker started pid=%s", self.p.pid)

    def _read_loop(self):
        for line in self.p.stdout:
            try:
                obj = json.loads(line)
            except Exception:
                continue
            q = self._q.pop(obj.get("id"), None)
            if q:
                q.put(obj)

    def call(self, cmd: str, timeout: int = 90, **kw) -> dict:
        self.start()
        with self._lock:
            self._id += 1
            rid = self._id
            q = queue.Queue()
            self._q[rid] = q
            payload = {"id": rid, "cmd": cmd, **kw}
            try:
                self.p.stdin.write(json.dumps(payload) + "\n")
                self.p.stdin.flush()
            except Exception as e:
                return {"ok": False, "err": f"pipe: {e}"}
        try:
            return q.get(timeout=timeout)
        except queue.Empty:
            return {"ok": False, "err": "timeout"}


WK = WorkerClient()
_check_lock = threading.Lock()


def do_check(phone: str) -> dict:
    with _check_lock:
        r = WK.call("check", phone=phone, timeout=120)
    if not r.get("ok"):
        return {"phone": phone, "verdict": "ERROR", "err": r.get("err")}
    return r["result"]


# ================= FORMAT =================
ICON = {"FRESH": "🟢", "BISA_UNBIND": "🔵", "NOT_ALLOW_UNBIND": "🔴",
        "RESTRICTED": "🔴", "LOCKED": "🔴", "REUSE_LIMIT": "🟠",
        "BANNED": "⛔", "RECYCLED": "🟠", "CHANGE_ONGOING": "⏳",
        "NEW_DEVICE_COOLDOWN": "⏳", "PHONE_INVALID": "⚪",
        "PHONE_NOT_FOUND": "🟢", "PHONE_NOT_EXIST": "🟢",
        "TERDAFTAR_UNKNOWN": "🟡", "RATE_LIMITED": "⏳",
        "ERROR": "⚫", "NO_COOKIE": "🚫"}
LABEL = {"FRESH": "Belum terdaftar (fresh)",
         "BISA_UNBIND": "Terdaftar · BISA di-unbind",
         "NOT_ALLOW_UNBIND": "Terdaftar · TIDAK boleh unbind",
         "RESTRICTED": "Terdaftar · akun/nomor di-restrict",
         "LOCKED": "Terdaftar · TIDAK bisa unbind",
         "REUSE_LIMIT": "Terdaftar · kena limit pemakaian",
         "BANNED": "Terdaftar · akun dibanned",
         "RECYCLED": "Nomor daur ulang",
         "CHANGE_ONGOING": "Ada request ganti nomor berjalan",
         "NEW_DEVICE_COOLDOWN": "Cooldown device baru",
         "PHONE_INVALID": "Format nomor tidak valid",
         "PHONE_NOT_FOUND": "Belum terdaftar (fresh)",
         "PHONE_NOT_EXIST": "Belum terdaftar (fresh)",
         "TERDAFTAR_UNKNOWN": "Terdaftar · status unbind tak diketahui",
         "RATE_LIMITED": "Rate limit, coba lagi",
         "ERROR": "Error", "NO_COOKIE": "Cookie server habis"}


def esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt_one(r: dict) -> str:
    v = r.get("verdict", "?")
    out = [f"{ICON.get(v,'·')} <b>{r.get('phone','')}</b>",
           f"   {LABEL.get(v, v)}"]
    if r.get("username"):
        out.append(f"   Akun: <code>{esc(r['username'])}</code>")
    if r.get("error") is not None:
        out.append(f"   code: <code>{r.get('error')}</code>")
    return "\n".join(out)


def norm(p: str) -> str:
    d = re.sub(r"\D", "", str(p or ""))
    if not d:
        return ""
    if d.startswith("0"):
        d = "62" + d[1:]
    elif d.startswith("8"):
        d = "62" + d
    elif d.startswith("620"):
        d = "62" + d[3:]
    return d


def extract_phones(text: str) -> list[str]:
    """Ambil nomor Indonesia. Total 10-13 digit setelah normalisasi ke 62xxx."""
    out, seen = [], set()
    for c in re.findall(r"(?:\+?62|0)8\d{7,12}", text or ""):
        n = norm(c)
        if n and 10 <= len(n) <= 13 and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


NET_TMP: dict[int, dict] = {}


# ================= HANDLERS =================
@bot.message_handler(commands=["start", "help", "menu"])
def cmd_start(m: Message):
    uid = m.from_user.id
    u = get_user(uid)
    bot.reply_to(m, f"""<b>🔍 SHOPEE PHONE CHECKER</b>

Halo <b>{esc(m.from_user.first_name or 'bro')}</b>
Saldo: <code>{u['saldo']}</code> poin
Harga: <code>{PRICE_PER_CHECK}</code> poin / nomor

Kirim nomor langsung (10-13 digit) atau pilih menu.""",
                 reply_markup=kb_main(uid))


def kb_main(uid: int):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("🔍 Cek Nomor", callback_data="mm_cek"),
           InlineKeyboardButton("💰 Saldo", callback_data="mm_saldo"))
    kb.add(InlineKeyboardButton("💳 Topup", callback_data="topup"),
           InlineKeyboardButton("💵 Harga", callback_data="mm_harga"))
    kb.add(InlineKeyboardButton("📊 Statistik", callback_data="mm_stats"),
           InlineKeyboardButton("❓ Bantuan", callback_data="mm_help"))
    kb.add(InlineKeyboardButton("🔐 Verify / Ganti Nomor", callback_data="otp_menu"))
    kb.add(InlineKeyboardButton("📱 Change Number", callback_data="chg:start"))
    if is_admin(uid):
        kb.add(InlineKeyboardButton("🔧 Panel Admin", callback_data="adm_home"))
    return kb


@bot.callback_query_handler(func=lambda c: c.data.startswith("mm_"))
def on_main_menu(c):
    act = c.data[3:]
    uid = c.from_user.id
    bot.answer_callback_query(c.id)

    if act == "cek":
        _menu(c, """🔍 <b>Cek Nomor</b>

Kirim nomor langsung ke chat ini — tanpa command.
Bisa banyak sekaligus (pisah spasi / enter / koma).

Format diterima:
<code>089601416330</code>
<code>089601416330 087876125616</code>
<code>+628****6330</code>

Bisa juga kirim file <b>.txt</b> (1 nomor per baris).
Maks per cek: <code>{}</code> nomor.""".format(get_setting("max_cek", MAX_PER_CEK)))

    elif act == "saldo":
        u = get_user(uid)
        _menu(c, f"""💰 <b>Saldo</b>

<code>{u['saldo']}</code> poin
≈ {u['saldo'] // PRICE_PER_CHECK} kali cek

Total cek: <code>{u.get('total_checks', 0)}</code>""",
              [[("💳 Topup", "topup")]])

    elif act == "harga":
        _menu(c, f"""💵 <b>Harga</b>

Cek nomor: <code>{PRICE_PER_CHECK}</code> poin
Batch: <code>{PRICE_PER_CHECK}</code> poin / nomor

<b>Paket topup</b>
Rp 10.000 → 100 cek
Rp 25.000 → 250 cek
Rp 50.000 → 500 cek
Rp 100.000 → 1000 cek""", [[("💳 Topup sekarang", "topup")]])

    elif act == "stats":
        with _db_lock:
            db = _load_db()
        ping = WK.call("ping", timeout=120)
        cookies = ping.get("cookies", 0) if ping.get("ok") else 0
        _menu(c, f"""📊 <b>Statistik</b>

Users: <code>{len(db['users'])}</code>
Total cek: <code>{db['stats'].get('total_checks', 0)}</code>
Cookie pool: <code>{cookies}</code>
Worker: {'✅' if ping.get('ok') else '❌ ' + str(ping.get('err'))}
Harga: <code>{PRICE_PER_CHECK}</code> poin""")

    elif act == "help":
        _menu(c, f"""❓ <b>Bantuan</b>

<b>Cara cek</b>
Kirim nomor langsung — bot auto-proses.
Bisa banyak: <code>0896... 0878... 0877...</code>
Atau kirim file <b>.txt</b> (maks {MAX_PER_BATCH} nomor).

<b>Hasil</b>
🟢 Fresh — nomor belum dipakai
🔵 Bisa unbind — terdaftar, bisa dilepas
🔴 Tidak bisa — terkunci
⛔ Restrict / banned
⏳ Rate limited

Maks <code>{get_setting("max_cek", MAX_PER_CEK)}</code> nomor per 1x kirim.""")

    elif act == "home":
        u = get_user(uid)
        _menu(c, f"""<b>🔍 SHOPEE PHONE CHECKER</b>

Saldo: <code>{u['saldo']}</code> poin""", None, kb_main(uid))


def _menu(c, text: str, rows=None, kb=None):
    """Edit pesan jadi menu. `rows` = [[(label, cbdata)]]."""
    if kb is None:
        kb = InlineKeyboardMarkup(row_width=2)
        for row in (rows or []):
            kb.add(*[InlineKeyboardButton(t, callback_data=d) for t, d in row])
        kb.add(InlineKeyboardButton("⬅️ Kembali", callback_data="mm_home"))
    try:
        bot.edit_message_text(text, c.message.chat.id, c.message.message_id,
                              reply_markup=kb, parse_mode="HTML")
    except Exception:
        bot.send_message(c.message.chat.id, text, reply_markup=kb,
                         parse_mode="HTML")


@bot.message_handler(commands=["saldo"])
def cmd_saldo(m: Message):
    u = get_user(m.from_user.id)
    bot.reply_to(m, f"""💰 <b>Saldo</b>

<code>{u['saldo']}</code> poin
≈ {u['saldo'] // PRICE_PER_CHECK} kali cek

Total cek: <code>{u.get('total_checks',0)}</code>""",
                 reply_markup=InlineKeyboardMarkup().add(
                     InlineKeyboardButton("💳 Topup", callback_data="topup")))


@bot.message_handler(commands=["harga"])
def cmd_harga(m: Message):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("💳 Topup sekarang", callback_data="topup"))
    bot.reply_to(m, f"""💵 <b>Harga</b>

Cek nomor: <code>{PRICE_PER_CHECK}</code> poin
Batch: <code>{PRICE_PER_CHECK}</code> poin / nomor

<b>Paket topup</b>
Rp 10.000 → 100 cek
Rp 25.000 → 250 cek
Rp 50.000 → 500 cek
Rp 100.000 → 1000 cek""", reply_markup=kb)


@bot.message_handler(commands=["stats"])
def cmd_stats(m: Message):
    with _db_lock:
        db = _load_db()
    ping = WK.call("ping", timeout=120)
    cookies = ping.get("cookies", 0) if ping.get("ok") else 0
    bot.reply_to(m, f"""📊 <b>Statistik</b>

Users: <code>{len(db['users'])}</code>
Total cek: <code>{db['stats'].get('total_checks',0)}</code>
Cookie pool: <code>{cookies}</code>
Worker: {'✅' if ping.get('ok') else '❌ ' + str(ping.get('err'))}
Harga: <code>{PRICE_PER_CHECK}</code> poin""")


@bot.message_handler(commands=["cek"])
def cmd_cek(m: Message):
    uid = m.from_user.id
    parts = (m.text or "").split(maxsplit=1)
    phones = extract_phones(parts[1]) if len(parts) > 1 else []
    if not phones and m.reply_to_message:
        phones = extract_phones(m.reply_to_message.text or "")
    if phones:
        run_cek(m, phones)
        return
    bot.reply_to(m, "❌ Tidak ada nomor valid.\nContoh: <code>/cek 6281234567890</code>")


def run_cek(m: Message, phones: list[str]):
    """Jalankan cek untuk daftar nomor (dipakai /cek & auto-detect & file)."""
    uid = m.from_user.id
    max_cek = int(get_setting("max_cek", MAX_PER_CEK))

    if len(phones) > max_cek:
        bot.reply_to(m, f"❌ Maks <code>{max_cek}</code> nomor sekali cek.\n"
                        f"Kamu kirim <code>{len(phones)}</code>. "
                        f"Pisah jadi beberapa pesan atau pakai file .txt.")
        return

    ok, sisa = charge(uid, len(phones))
    if not ok:
        bot.reply_to(m, f"❌ Saldo kurang.\nButuh <code>{len(phones)*PRICE_PER_CHECK}</code>, "
                        f"punya <code>{sisa}</code>.\n\n/topup")
        return

    sent = bot.reply_to(
        m,
        f"✅ <b>{len(phones)} nomor diterima</b>\n"
        f"⏳ Sedang diproses — mohon tunggu...\n\n"
        f"<i>Biaya: {len(phones) * PRICE_PER_CHECK} poin</i>")

    results = []
    last_edit = 0.0
    for i, p in enumerate(phones, 1):
        results.append(do_check(p))
        now = time.time()
        # edit progres maks 1×/detik supaya tidak kena flood Telegram
        if len(phones) > 1 and (now - last_edit > 1.0 or i == len(phones)):
            last_edit = now
            try:
                bot.edit_message_text(
                    f"✅ <b>{len(phones)} nomor diterima</b>\n"
                    f"⏳ Diproses {i}/{len(phones)} — <code>{p}</code>",
                    chat_id=sent.chat.id, message_id=sent.message_id,
                    parse_mode="HTML")
            except Exception:
                pass

    txt = "\n\n".join(fmt_one(r) for r in results)
    txt += f"\n\n<b>Sisa saldo:</b> <code>{sisa}</code> poin"

    if len(txt) > 3900:
        fp = RESULT_DIR / f"cek_{uid}_{int(time.time())}.txt"
        fp.write_text("\n".join(
            f"{r['phone']} | {r['verdict']} | {r.get('username','')}" for r in results))
        bot.edit_message_text(f"✅ Selesai {len(phones)} nomor. Hasil dikirim sebagai file.",
                              chat_id=sent.chat.id, message_id=sent.message_id)
        bot.send_document(m.chat.id, fp.open("rb"))
    else:
        try:
            bot.edit_message_text(txt, chat_id=sent.chat.id, message_id=sent.message_id)
        except Exception:
            bot.send_message(m.chat.id, txt)


# ==== CHG EARLY ROUTER ====
@bot.message_handler(func=lambda m: str((NET_TMP.get(m.from_user.id) or {}).get("step") or "").startswith("chg_"),
                     content_types=["text"])
def chg_early_router(m: Message):
    """Tangkap SEMUA input Change Number sebelum handler lain."""
    uid = m.from_user.id
    txt = (m.text or "").strip()
    log.info("CHG EARLY uid=%s len=%d", uid, len(txt))
    # ADMIN_CREDIT_V1 — panel kredit admin (input teks)
    if is_admin(uid):
        try:
            if adc_handle_text(m, uid, txt):
                return
        except Exception:
            log.exception("adc text")
    try:
        if chg_handle_text(m, uid, txt):
            return
    except Exception:
        log.exception("CHG EARLY fail uid=%s", uid)
        bot.reply_to(m, "❌ Error internal: cek log bot.")


@bot.message_handler(func=lambda m: m.chat.type == "private",
                     content_types=["text"])
def auto_detect_phone(m: Message):
    """Kirim nomor langsung (tanpa command) -> langsung dicek.

    Hanya untuk pesan berisi ANGKA SAJA (minimal 10 digit, maksimal 13 digit),
    supaya tidak menabrak percakapan biasa atau input admin.
    """
    if m.from_user.id in NET_TMP:
        return
    st = NET_TMP.get(m.from_user.id) or {}
    if str(st.get("step") or "").startswith("chg_"):
        return
    txt = (m.text or "").strip()
    log.info("auto_detect: uid=%s len=%d head=%r", m.from_user.id, len(txt), txt[:30])
    if not txt or txt.startswith("/"):
        return
    if not re.fullmatch(r"[\d\s,;+\-\.]+", txt):
        log.info("auto_detect: bukan angka-only, skip")
        return
    phones = extract_phones(txt)
    log.info("auto_detect: %d nomor terdeteksi", len(phones))
    if not phones:
        return
    run_cek(m, phones)


@bot.message_handler(content_types=["document"])
def handle_doc(m: Message):
    uid = m.from_user.id
    doc = m.document
    if not (doc.file_name or "").lower().endswith(".txt"):
        bot.reply_to(m, "❌ Cuma file <b>.txt</b>")
        return
    try:
        fi = bot.get_file(doc.file_id)
        raw = bot.download_file(fi.file_path).decode("utf-8", "ignore")
    except Exception as e:
        bot.reply_to(m, f"❌ Gagal unduh: {e}")
        return

    phones = extract_phones(raw)
    if not phones:
        bot.reply_to(m, "❌ Tidak ada nomor valid.")
        return
    if len(phones) > MAX_PER_BATCH:
        bot.reply_to(m, f"❌ {len(phones)} nomor, maks {MAX_PER_BATCH}.")
        return

    ok, sisa = charge(uid, len(phones))
    if not ok:
        bot.reply_to(m, f"❌ Saldo kurang untuk {len(phones)} nomor "
                        f"(butuh {len(phones)*PRICE_PER_CHECK}, punya {sisa}).\n/topup")
        return

    sent = bot.reply_to(m, f"⏳ Batch {len(phones)} nomor...")
    t0 = time.time()
    results = []
    last = 0

    for i, p in enumerate(phones, 1):
        results.append(do_check(p))
        now = time.time()
        if now - last > 3 or i == len(phones):
            last = now
            c = Counter(r["verdict"] for r in results)
            try:
                bot.edit_message_text(
                    f"⏳ <b>Batch</b> {i}/{len(phones)} ({i*100//len(phones)}%)\n"
                    f"🟢 {c.get('FRESH',0)} · 🔵 {c.get('BISA_UNBIND',0)} · "
                    f"🔴 {c.get('NOT_ALLOW_UNBIND',0)+c.get('LOCKED',0)} · "
                    f"⏳ {c.get('RATE_LIMITED',0)}\n"
                    f"⏱ {int(now-t0)}s",
                    chat_id=sent.chat.id, message_id=sent.message_id)
            except Exception:
                pass

    c = Counter(r["verdict"] for r in results)
    fp = RESULT_DIR / f"batch_{uid}_{int(time.time())}.txt"
    with fp.open("w") as f:
        f.write(f"# Shopee Phone Check {datetime.now():%Y-%m-%d %H:%M}\n")
        f.write(f"# total {len(results)}\n\n")
        for r in results:
            f.write(f"{r['phone']} | {r['verdict']} | {r.get('username','')}\n")

    summary = f"""✅ <b>Batch selesai</b> — {len(results)} nomor

🟢 Fresh: <code>{c.get('FRESH',0)}</code>
🔵 Bisa unbind: <code>{c.get('BISA_UNBIND',0)}</code>
🔴 Tidak bisa: <code>{c.get('NOT_ALLOW_UNBIND',0)+c.get('LOCKED',0)}</code>
⛔ Restrict/banned: <code>{c.get('RESTRICTED',0)+c.get('BANNED',0)}</code>
🟠 Limit/daur ulang: <code>{c.get('REUSE_LIMIT',0)+c.get('RECYCLED',0)}</code>
🟡 Tak diketahui: <code>{c.get('TERDAFTAR_UNKNOWN',0)}</code>
⏳ Rate limited: <code>{c.get('RATE_LIMITED',0)}</code>
⚫ Error: <code>{c.get('ERROR',0)}</code>

Sisa saldo: <code>{sisa}</code> poin
Durasi: {int(time.time()-t0)}s"""
    try:
        bot.edit_message_text(summary, chat_id=sent.chat.id, message_id=sent.message_id)
    except Exception:
        bot.send_message(m.chat.id, summary)
    bot.send_document(m.chat.id, fp.open("rb"))


@bot.message_handler(commands=["topup"])
def cmd_topup(m: Message):
    bot.reply_to(m, "💳 <b>Topup Saldo</b>\n\nPilih paket (QRIS):",
                 reply_markup=kb_topup())


def kb_topup():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("Rp 10.000", callback_data="buy_10000"),
           InlineKeyboardButton("Rp 25.000", callback_data="buy_25000"))
    kb.add(InlineKeyboardButton("Rp 50.000", callback_data="buy_50000"),
           InlineKeyboardButton("Rp 100.000", callback_data="buy_100000"))
    kb.add(InlineKeyboardButton("⬅️ Kembali", callback_data="mm_home"))
    return kb


PAKET = {10000: 100, 25000: 250, 50000: 500, 100000: 1000}


@bot.callback_query_handler(func=lambda c: c.data.startswith("buy_"))
def on_buy(c):
    amount = int(c.data.split("_")[1])
    poin = PAKET.get(amount, 0)
    bot.answer_callback_query(c.id, "Menyiapkan QRIS...")
    if not poin:
        bot.send_message(c.message.chat.id, "❌ Paket tidak dikenal.")
        return
    try:
        g = GPM()
        bal = g.balance()
    except GPMError as e:
        bot.send_message(c.message.chat.id, f"❌ GPM error: <code>{esc(e)}</code>")
        return

    oid = f"TU{int(time.time())}{c.from_user.id % 10000}"
    try:
        q = g.qris(amount, oid)
    except GPMError as e:
        bot.send_message(c.message.chat.id, f"❌ Gagal buat QRIS: <code>{esc(e)}</code>")
        return

    # order_id yang kita kirim dipantulkan sebagai transaction.id di webhook,
    # tapi GPM juga punya transaction_id (uuid). Simpan semua sebagai alias.
    real_ref = q.get("order_id") or oid
    refs = q.get("refs") or [real_ref]
    with _db_lock:
        db = _load_db()
        rec = {"order_id": real_ref, "refs": refs, "uid": c.from_user.id,
               "amount": amount, "poin": poin, "status": "pending",
               "created": int(time.time()), "qr": q["qr_string"],
               "chat": c.message.chat.id}
        for r in refs:
            db.setdefault("orders", {})[r] = rec
        _save_db(db)
    oid = real_ref

    caption = (f"💳 <b>Topup Rp {amount:,}</b>\n"
               f"Dapat <code>{poin}</code> cek\n"
               f"Order: <code>{oid}</code>\n"
               f"Berlaku: <code>{q['expiry'] or '-'}</code>\n\n"
               f"Scan QRIS di bawah, saldo masuk otomatis setelah dibayar.")
    try:
        png = qr_png(q["qr_string"])
        bot.send_photo(c.message.chat.id, png, caption=caption)
    except Exception as e:
        log.warning("qr png gagal: %s", e)
        bot.send_message(c.message.chat.id,
                         caption + f"\n\n<code>{esc(q['qr_string'])}</code>")

    threading.Thread(target=_poll_order, args=(oid,), daemon=True).start()


def qr_png(data: str):
    """Render QR ke PNG bytes. Coba qrcode, fallback segno."""
    import io
    try:
        import qrcode
        img = qrcode.make(data)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf
    except Exception:
        pass
    try:
        import segno
        buf = io.BytesIO()
        segno.make(data, error="m").save(buf, kind="png", scale=8)
        buf.seek(0)
        return buf
    except Exception as e:
        raise RuntimeError(f"library QR tidak tersedia: {e}")


POLL_FAST = float(os.environ.get("POLL_FAST", "1.5"))   # detik, 2 menit pertama
POLL_SLOW = float(os.environ.get("POLL_SLOW", "5"))     # detik, setelah itu
POLL_FAST_WINDOW = 120                                   # durasi fase cepat


def _settle_order(oid: str, poin: int, uid, chat) -> int | None:
    """Tambah saldo sekali. Return saldo baru, atau None bila sudah paid."""
    with _db_lock:
        db = _load_db()
        od = db.get("orders", {}).get(oid)
        if not od or od.get("status") == "paid":
            return None
        # tandai semua alias agar tidak dobel
        aliases = set(od.get("refs") or []) | {oid}
        for k in aliases:
            if k in db.get("orders", {}):
                db["orders"][k]["status"] = "paid"
                db["orders"][k]["paid_at"] = int(time.time())
        u = _u(db, od["uid"])
        u["saldo"] = int(u.get("saldo", 0)) + int(poin)
        _save_db(db)
        return u["saldo"]


def _poll_order(oid: str, timeout: int = 900):
    """Jaring pengaman bila webhook tidak sampai.

    Fase cepat: cek tiap POLL_FAST (1.5s) selama 2 menit pertama — biasanya
    QRIS lunas dalam hitungan detik setelah scan. Setelah itu melambat ke
    POLL_SLOW supaya tidak menghajar API provider untuk order yang ditinggal.
    """
    g = GPM()
    t0 = time.time()
    while time.time() - t0 < timeout:
        elapsed = time.time() - t0
        time.sleep(POLL_FAST if elapsed < POLL_FAST_WINDOW else POLL_SLOW)
        try:
            st = g.status(oid)
        except GPMError:
            continue
        if not st["paid"]:
            continue
        with _db_lock:
            db = _load_db()
            od = db.get("orders", {}).get(oid)
            if not od:
                # ref tidak dikenal -> coba lookup via alias
                return
            poin = int(od.get("poin", 0))
            chat = od.get("chat") or od["uid"]
            if od.get("status") == "paid":
                return
        saldo = _settle_order(oid, poin, od["uid"], chat)
        if saldo is None:
            return
        try:
            bot.send_message(
                chat,
                f"✅ <b>Pembayaran diterima</b>\n"
                f"Order: <code>{oid}</code>\n"
                f"+<code>{poin}</code> cek\n"
                f"Saldo: <code>{saldo}</code>")
        except Exception:
            pass
        return
    try:
        with _db_lock:
            db = _load_db()
            od = db.get("orders", {}).get(oid) or {}
            if od.get("status") == "pending":
                od["status"] = "expired"
                _save_db(db)
        if od:
            bot.send_message(od.get("chat") or od["uid"],
                             f"⌛ <code>{oid}</code> kedaluwarsa. Buat ulang /topup.")
    except Exception:
        pass


@bot.message_handler(commands=["cekorder"])
def cmd_cekorder(m: Message):
    parts = (m.text or "").split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(m, "Format: <code>/cekorder TUxxxx</code>")
        return
    oid = parts[1].strip()
    try:
        st = GPM().status(oid)
    except GPMError as e:
        bot.reply_to(m, f"❌ {esc(e)}")
        return
    with _db_lock:
        db = _load_db()
        od = db.get("orders", {}).get(oid) or {}
    bot.reply_to(m, f"<b>{oid}</b>\n"
                    f"GPM: <code>{st['status'] or '-'}</code> "
                    f"{'✅' if st['paid'] else '⏳'}\n"
                    f"Lokal: <code>{od.get('status','-')}</code> "
                    f"poin <code>{od.get('poin','-')}</code>")


@bot.callback_query_handler(func=lambda c: c.data == "topup")
def on_topup(c):
    bot.answer_callback_query(c.id)
    try:
        bot.edit_message_text("💳 <b>Topup Saldo</b>\n\nPilih paket (QRIS):",
                              c.message.chat.id, c.message.message_id,
                              reply_markup=kb_topup(), parse_mode="HTML")
    except Exception:
        bot.send_message(c.message.chat.id,
                         "💳 <b>Topup Saldo</b>\n\nPilih paket (QRIS):",
                         reply_markup=kb_topup(), parse_mode="HTML")



# ================= VERIFY / GANTI NOMOR =================
OTP_PENDING: dict[int, dict] = {}   # uid -> {phone, step, token, ts}

OTP_STEP_TXT = {
    "send": "minta kode OTP",
    "verify": "verifikasi kode",
    "check": "cek izin unbind",
    "unbind": "lepas nomor",
}


def _otp_call(uid: int, phone: str, step: str, vcode: str = "",
              token: str = "", timeout: int = 150) -> dict:
    r = WK.call("otp", phone=phone, step=step, vcode=vcode,
                vcode_token=token, timeout=timeout)
    if not r.get("ok"):
        return {"ok": False, "error": -1, "msg": r.get("err") or "worker error"}
    return r.get("result") or {}


def kb_otp(uid: int):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("📲 Verify Nomor (kirim OTP)",
                                callback_data="otp_new"))
    if OTP_PENDING.get(uid):
        kb.add(InlineKeyboardButton("✅ Saya sudah terima kode",
                                    callback_data="otp_have_code"))
    kb.add(InlineKeyboardButton("🔓 Ganti / Lepas Nomor", callback_data="otp_unbind"))
    kb.add(InlineKeyboardButton("⬅️ Kembali", callback_data="mm_home"))
    return kb


def txt_otp(uid: int) -> str:
    pend = OTP_PENDING.get(uid)
    s = ("🔐 <b>Verify & Ganti Nomor</b>\n\n"
         "Flow OTP langsung ke Shopee.\n\n"
         "<b>Verify Nomor</b> — pastikan nomor aktif & bisa terima kode.\n"
         "<b>Ganti/Lepas Nomor</b> — lepas nomor lama dari akun "
         "(butuh OTP dari nomor tersebut).\n\n"
         "<i>Biaya: 1 kredit per percobaan OTP.</i>")
    if pend:
        s += (f"\n\n<b>Menunggu kode:</b>\n"
              f"Nomor: <code>{esc(pend['phone'])}</code>\n"
              f"Langkah: {OTP_STEP_TXT.get(pend['step'], pend['step'])}\n"
              f"Berlaku ±5 menit.")
    return s


@bot.callback_query_handler(func=lambda c: c.data.startswith("otp_"))
def on_otp(c):
    uid = c.from_user.id
    act = c.data[4:]
    bot.answer_callback_query(c.id)

    if act == "menu":
        OTP_PENDING.pop(uid, None)
        _edit_or_send(c, txt_otp(uid), kb_otp(uid))
        return

    if act in ("new", "unbind"):
        step = "send"
        NET_TMP[uid] = {"step": "otp_phone", "mode": act}
        _edit_or_send(c,
            f"{'📲 <b>Verify Nomor</b>' if act=='new' else '🔓 <b>Ganti / Lepas Nomor</b>'}\n\n"
            "Kirim nomor HP (10-13 digit):\n"
            "<code>089601416330</code>",
            InlineKeyboardMarkup().add(
                InlineKeyboardButton("❌ Batal", callback_data="otp_menu")))
        return

    if act == "have_code":
        pend = OTP_PENDING.get(uid)
        if not pend:
            bot.answer_callback_query(c.id, "Tidak ada OTP aktif", show_alert=True)
            return
        NET_TMP[uid] = {"step": "otp_code", "mode": pend["mode"]}
        _edit_or_send(c,
            f"🔢 Kirim kode OTP untuk <code>{esc(pend['phone'])}</code>\n\n"
            "<i>6 digit dari SMS/WhatsApp.</i>",
            InlineKeyboardMarkup().add(
                InlineKeyboardButton("❌ Batal", callback_data="otp_menu")))
        return

    if act == "resend":
        pend = OTP_PENDING.get(uid)
        if not pend:
            bot.answer_callback_query(c.id, "Tidak ada OTP aktif", show_alert=True)
            return
        r = _otp_call(uid, pend["phone"], "send")
        if r.get("ok"):
            pend["token"] = r.get("vcode_token") or pend["token"]
            pend["ts"] = time.time()
            _edit_or_send(c,
                f"📲 Kode dikirim ulang ke <code>{esc(pend['phone'])}</code>\n"
                "Tekan <b>Saya sudah terima kode</b> setelah masuk.",
                InlineKeyboardMarkup(row_width=1).add(
                    InlineKeyboardButton("✅ Saya sudah terima kode",
                                         callback_data="otp_have_code"),
                    InlineKeyboardButton("❌ Batal", callback_data="otp_menu")))
        else:
            bot.answer_callback_query(
                c.id, f"Gagal kirim ulang: {r.get('msg')}", show_alert=True)
        return


def _edit_or_send(c, text: str, kb):
    try:
        bot.edit_message_text(text, c.message.chat.id, c.message.message_id,
                              reply_markup=kb, parse_mode="HTML")
    except Exception:
        bot.send_message(c.message.chat.id, text, reply_markup=kb,
                         parse_mode="HTML")


def _otp_send_kode(m: Message, phone: str, mode: str):
    """Minta OTP pertama kali, lalu pasang state menunggu kode."""
    uid = m.from_user.id
    sent = bot.reply_to(m, f"⏳ Mengirim OTP ke <code>{esc(phone)}</code>...")
    r = _otp_call(uid, phone, "send")
    if not r.get("ok"):
        bot.edit_message_text(
            f"❌ Gagal kirim OTP\n"
            f"<code>{esc(r.get('msg') or r.get('error'))}</code>",
            chat_id=sent.chat.id, message_id=sent.message_id, parse_mode="HTML")
        return
    OTP_PENDING[uid] = {"phone": phone, "step": "send",
                        "token": r.get("vcode_token") or "",
                        "mode": mode, "ts": time.time()}
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("✅ Saya sudah terima kode",
                                callback_data="otp_have_code"),
           InlineKeyboardButton("🔁 Kirim ulang", callback_data="otp_resend"),
           InlineKeyboardButton("❌ Batal", callback_data="otp_menu"))
    bot.edit_message_text(
        f"📲 <b>Kode dikirim</b>\n\n"
        f"Nomor: <code>{esc(phone)}</code>\n"
        f"Seed: <code>{(r.get('vcode_token') or '')[:8]}…</code>\n\n"
        f"Masukkan kode 6 digit setelah masuk.",
        chat_id=sent.chat.id, message_id=sent.message_id,
        reply_markup=kb, parse_mode="HTML")


def _otp_verify_kode(m: Message, code: str):
    """Verifikasi kode lalu lanjut ke cek/unbind."""
    uid = m.from_user.id
    pend = OTP_PENDING.get(uid)
    if not pend:
        bot.reply_to(m, "❌ Tidak ada sesi OTP. Mulai dari menu.")
        return
    if time.time() - pend.get("ts", 0) > 300:
        OTP_PENDING.pop(uid, None)
        bot.reply_to(m, "❌ Sesi OTP kedaluwarsa (5 menit). Ulangi.")
        return

    phone = pend["phone"]
    mode = pend.get("mode", "new")
    sent = bot.reply_to(m, f"⏳ Memverifikasi kode <code>{code}</code>...")

    v = _otp_call(uid, phone, "verify", vcode=code, token=pend["token"])
    if not v.get("ok"):
        bot.edit_message_text(
            f"❌ <b>Kode ditolak</b>\n<code>{esc(v.get('msg'))}</code>\n\n"
            f"Coba lagi atau kirim ulang kode.",
            chat_id=sent.chat.id, message_id=sent.message_id, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(row_width=1).add(
                InlineKeyboardButton("🔁 Kirim ulang", callback_data="otp_resend"),
                InlineKeyboardButton("❌ Batal", callback_data="otp_menu")))
        return

    token = v.get("vcode_token") or pend["token"]
    pend["token"] = token
    pend["step"] = "verify"

    # langkah lanjutan: cek izin unbind
    ck = _otp_call(uid, phone, "check", token=token)
    if not ck.get("ok"):
        bot.edit_message_text(
            f"✅ <b>Kode valid</b>\n\n"
            f"Nomor <code>{esc(phone)}</code> aktif dan bisa terima OTP.\n\n"
            f"⚠️ Cek izin unbind gagal: <code>{esc(ck.get('msg'))}</code>\n"
            f"<i>Nomor tetap terverifikasi.</i>",
            chat_id=sent.chat.id, message_id=sent.message_id, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("⬅️ Menu", callback_data="otp_menu")))
        OTP_PENDING.pop(uid, None)
        return

    if mode == "unbind":
        ub = _otp_call(uid, phone, "unbind", token=token)
        if ub.get("ok"):
            OTP_PENDING.pop(uid, None)
            bot.edit_message_text(
                f"🔓 <b>Nomor dilepas</b>\n\n"
                f"<code>{esc(phone)}</code> berhasil di-unbind dari akun.\n"
                f"Sekarang nomor ini bisa dipakai daftar akun baru.",
                chat_id=sent.chat.id, message_id=sent.message_id,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("⬅️ Menu", callback_data="otp_menu")))
        else:
            bot.edit_message_text(
                f"⚠️ <b>Kode valid, tapi unbind ditolak</b>\n\n"
                f"<code>{esc(ub.get('msg'))}</code>\n\n"
                f"Nomor <b>terverifikasi aktif</b>, tapi belum bisa dilepas.",
                chat_id=sent.chat.id, message_id=sent.message_id,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("⬅️ Menu", callback_data="otp_menu")))
            OTP_PENDING.pop(uid, None)
    else:
        OTP_PENDING.pop(uid, None)
        bot.edit_message_text(
            f"✅ <b>Nomor terverifikasi</b>\n\n"
            f"<code>{esc(phone)}</code> aktif dan bisa menerima OTP.\n\n"
            f"Status dalam sistem: <code>{esc(str(ck.get('data'))[:80])}</code>",
            chat_id=sent.chat.id, message_id=sent.message_id,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("⬅️ Menu", callback_data="otp_menu")))


# ================= PANEL ADMIN =================


def kb_admin():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("🌐 Jaringan", callback_data="adm_net"))
    kb.add(InlineKeyboardButton("🔌 Pool Proxy", callback_data="adm_pool"))
    kb.add(InlineKeyboardButton("🖥 Status", callback_data="adm_status"),
           InlineKeyboardButton("🔄 Restart Worker", callback_data="adm_restart"))
    kb.add(InlineKeyboardButton("💳 Kredit User", callback_data="adm_cred"))
    kb.add(InlineKeyboardButton("💰 Saldo GPM", callback_data="adm_gpm"),
           InlineKeyboardButton("⚙️ Setting", callback_data="adm_set"))
    kb.add(InlineKeyboardButton("⬅️ Menu Utama", callback_data="mm_home"))
    return kb


def txt_admin() -> str:
    ni = WK.call("netinfo", timeout=30) if WK.p else {}
    mode = ni.get("mode", "?")
    url = ni.get("url") or "-"
    pool = _proxy_pool()
    aktif = next((p for p in pool if p.get("active")), None)
    return (f"🔧 <b>Panel Admin</b>\n\n"
            f"Jaringan: <code>{mode}</code>\n"
            f"Endpoint: <code>{esc(url)}</code>\n"
            f"Pool proxy: <code>{len(pool)}</code> entri · "
            f"aktif: <code>{esc((aktif or {}).get('name', '-'))}</code>\n\n"
            f"Pilih menu:")


@bot.message_handler(commands=["admin"])
def cmd_admin(m: Message):
    if not is_admin(m.from_user.id):
        bot.reply_to(m, "❌ Bukan admin.")
        return
    bot.reply_to(m, txt_admin(), reply_markup=kb_admin())


def _proxy_pool() -> list[dict]:
    with _db_lock:
        db = _load_db()
        return db.get("proxy_pool", [])


def _save_pool(pool: list[dict]):
    with _db_lock:
        db = _load_db()
        db["proxy_pool"] = pool
        _save_db(db)


# ADMIN_CREDIT_V1
def _cred_users(limit=30):
    """Daftar user terurut saldo desc."""
    with _db_lock:
        db = _load_db()
    rows = []
    for k, v in (db.get("users") or {}).items():
        rows.append({"id": int(v.get("id") or k),
                     "name": v.get("name") or "",
                     "saldo": int(v.get("saldo", 0)),
                     "checks": int(v.get("total_checks", 0))})
    rows.sort(key=lambda r: r["saldo"], reverse=True)
    return rows[:limit], len(rows)


def _cred_kb_users():
    rows, total = _cred_users(30)
    kb = InlineKeyboardMarkup(row_width=2)
    btns = []
    for r in rows:
        label = f"{(r['name'] or str(r['id']))[:14]} · {r['saldo']}"
        btns.append(InlineKeyboardButton(label,
                                         callback_data=f"adc_u:{r['id']}"))
    for i in range(0, len(btns), 2):
        kb.add(*btns[i:i + 2])
    kb.add(InlineKeyboardButton("🔍 Cari ID / Username",
                                callback_data="adc_find"))
    kb.add(InlineKeyboardButton("⬅️ Kembali", callback_data="adm_back"))
    return kb, rows, total


def _cred_kb_amount(uid):
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(InlineKeyboardButton("+10", callback_data=f"adc_a:{uid}:10"),
           InlineKeyboardButton("+50", callback_data=f"adc_a:{uid}:50"),
           InlineKeyboardButton("+100", callback_data=f"adc_a:{uid}:100"))
    kb.add(InlineKeyboardButton("+500", callback_data=f"adc_a:{uid}:500"),
           InlineKeyboardButton("+1.000", callback_data=f"adc_a:{uid}:1000"),
           InlineKeyboardButton("+5.000", callback_data=f"adc_a:{uid}:5000"))
    kb.add(InlineKeyboardButton("✏️ Nominal Lain",
                                callback_data=f"adc_custom:{uid}"),
           InlineKeyboardButton("➖ Kurangi",
                                callback_data=f"adc_minus:{uid}"))
    kb.add(InlineKeyboardButton("⬅️ Daftar User", callback_data="adm_cred"))
    return kb


def _cred_txt(uid):
    u = get_user(uid)
    lines = [f"💳 <b>Kredit User</b>",
             "",
             f"🆔 ID: <code>{uid}</code>",
             f"👤 Nama: <code>{esc(u.get('name') or '-')}</code>",
             f"💰 Saldo: <code>{int(u.get('saldo', 0)):,}</code> poin",
             f"🔍 Total cek: <code>{int(u.get('total_checks', 0)):,}</code>",
             "",
             f"≈ <b>{int(u.get('saldo', 0)) // PRICE_PER_CHECK}</b> kali cek "
             f"(@{PRICE_PER_CHECK} poin)",
             "",
             "Pilih nominal untuk ditambahkan:"]
    return "\n".join(lines)


def _cred_add(uid, amount, by):
    """Tambah/kurangi saldo + catat log."""
    with _db_lock:
        db = _load_db()
        u = _u(db, uid)
        before = int(u.get("saldo", 0))
        after = before + int(amount)
        if after < 0:
            after = 0
        u["saldo"] = after
        logd = db.setdefault("credit_log", [])
        logd.append({"uid": uid, "by": by, "delta": after - before,
                     "before": before, "after": after,
                     "ts": int(time.time())})
        db["credit_log"] = logd[-1000:]
        _save_db(db)
    return before, after


# ==== ADMIN CREDIT HANDLER ====
@bot.callback_query_handler(func=lambda c: c.data.startswith("adc_"))
def on_adc(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id, "Bukan admin", show_alert=True)
        return
    d = c.data[4:]
    admin = c.from_user.id

    def _edit(txt, kb):
        try:
            bot.edit_message_text(txt, c.message.chat.id, c.message.message_id,
                                  reply_markup=kb, parse_mode="HTML")
        except Exception as e:
            if "not modified" not in str(e).lower():
                bot.send_message(c.message.chat.id, txt, reply_markup=kb,
                                 parse_mode="HTML")

    # ---- daftar user ----
    if d in ("list", "", "home"):
        bot.answer_callback_query(c.id)
        kb, rows, total = _cred_kb_users()
        _edit(f"💳 <b>Kredit User</b>\n\n"
              f"Total user: <code>{total}</code>\n"
              f"Ditampilkan: <code>{len(rows)}</code> (saldo tertinggi)\n\n"
              f"Pilih user:", kb)
        return

    # ---- cari user ----
    if d == "find":
        bot.answer_callback_query(c.id)
        NET_TMP[admin] = {"step": "adc_find", "msg": c.message}
        _edit("🔍 <b>Cari User</b>\n\n"
              "Kirim <b>ID</b> atau <b>username</b>:\n"
              "<i>(atau ketik ID langsung)</i>",
              InlineKeyboardMarkup().add(
                  InlineKeyboardButton("⬅️ Kembali", callback_data="adm_cred")))
        return

    # ---- pilih user ----
    if d.startswith("u:"):
        bot.answer_callback_query(c.id)
        uid = int(d.split(":")[1])
        NET_TMP.pop(admin, None)
        _edit(_cred_txt(uid), _cred_kb_amount(uid))
        return

    # ---- tambah nominal ----
    if d.startswith("a:"):
        parts = d.split(":")
        uid, amt = int(parts[1]), int(parts[2])
        before, after = _cred_add(uid, amt, admin)
        bot.answer_callback_query(c.id, f"+{amt} ✅ saldo {after:,}")
        log.info("CREDIT admin=%s uid=%s +%d %d->%d", admin, uid, amt, before, after)
        u = get_user(uid)
        _edit(f"✅ <b>Kredit ditambahkan</b>\n\n"
              f"🆔 <code>{uid}</code> · {esc(u.get('name') or '-')}\n"
              f"➕ <code>+{amt:,}</code>\n"
              f"💰 <code>{before:,}</code> → <code>{after:,}</code>\n"
              f"≈ <b>{after // PRICE_PER_CHECK}</b> kali cek\n\n"
              f"Tambah lagi:",
              _cred_kb_amount(uid))
        return

    # ---- kurangi ----
    if d.startswith("minus:"):
        uid = int(d.split(":")[1])
        bot.answer_callback_query(c.id)
        NET_TMP[admin] = {"step": "adc_minus", "uid": uid, "msg": c.message}
        u = get_user(uid)
        _edit(f"➖ <b>Kurangi Saldo</b>\n\n"
              f"🆔 <code>{uid}</code>\n"
              f"💰 Sekarang: <code>{int(u.get('saldo', 0)):,}</code>\n\n"
              f"Kirim jumlah yang mau dikurangi:",
              InlineKeyboardMarkup().add(
                  InlineKeyboardButton("⬅️ Batal", callback_data=f"adc_u:{uid}")))
        return

    # ---- nominal custom ----
    if d.startswith("custom:"):
        uid = int(d.split(":")[1])
        bot.answer_callback_query(c.id)
        NET_TMP[admin] = {"step": "adc_custom", "uid": uid, "msg": c.message}
        u = get_user(uid)
        _edit(f"✏️ <b>Nominal Custom</b>\n\n"
              f"🆔 <code>{uid}</code>\n"
              f"💰 Saldo: <code>{int(u.get('saldo', 0)):,}</code>\n\n"
              f"Kirim jumlah poin (angka).\n"
              f"Boleh negatif untuk mengurangi.\n"
              f"Contoh: <code>250</code> atau <code>-100</code>",
              InlineKeyboardMarkup().add(
                  InlineKeyboardButton("⬅️ Batal", callback_data=f"adc_u:{uid}")))
        return


def adc_handle_text(m, uid, txt):
    """Tangani input teks panel kredit. Return True kalau ditangani."""
    st = NET_TMP.get(uid) or {}
    step = st.get("step") or ""
    if not step.startswith("adc_"):
        return False

    msg = st.get("msg") or m

    def _edit(t, kb):
        try:
            bot.edit_message_text(t, msg.chat.id, msg.message_id,
                                  reply_markup=kb, parse_mode="HTML")
        except Exception as e:
            if "not modified" not in str(e).lower():
                bot.send_message(msg.chat.id, t, reply_markup=kb,
                                 parse_mode="HTML")

    # ---- cari user ----
    if step == "adc_find":
        q = txt.strip().lstrip("@")
        target = None
        with _db_lock:
            db = _load_db()
        users = db.get("users") or {}
        if q.isdigit() and q in users:
            target = int(q)
        else:
            for k, v in users.items():
                if (v.get("name") or "").lower() == q.lower():
                    target = int(v.get("id") or k)
                    break
        if target is None:
            _edit(f"❌ User <code>{esc(q)}</code> tidak ditemukan.\n\n"
                  "Coba ID atau username lain:",
                  InlineKeyboardMarkup().add(
                      InlineKeyboardButton("⬅️ Kembali",
                                           callback_data="adm_cred")))
            return True
        NET_TMP[uid] = {"step": "", "msg": msg}
        _edit(_cred_txt(target), _cred_kb_amount(target))
        return True

    # ---- nominal custom ----
    if step == "adc_custom":
        try:
            amt = int(txt.strip().replace(".", "").replace(",", ""))
        except ValueError:
            _edit("❌ Bukan angka. Kirim angka seperti <code>250</code>",
                  InlineKeyboardMarkup().add(
                      InlineKeyboardButton("⬅️ Batal",
                                           callback_data=f"adc_u:{st.get('uid')}")))
            return True
        tgt = st.get("uid")
        before, after = _cred_add(tgt, amt, uid)
        NET_TMP.pop(uid, None)
        log.info("CREDIT admin=%s uid=%s %+d %d->%d", uid, tgt, amt, before, after)
        u = get_user(tgt)
        sign = "+" if amt >= 0 else ""
        _edit(f"✅ <b>Saldo diperbarui</b>\n\n"
              f"🆔 <code>{tgt}</code> · {esc(u.get('name') or '-')}\n"
              f"🔧 <code>{sign}{amt:,}</code>\n"
              f"💰 <code>{before:,}</code> → <code>{after:,}</code>\n"
              f"≈ <b>{after // PRICE_PER_CHECK}</b> kali cek",
              _cred_kb_amount(tgt))
        return True

    # ---- kurangi ----
    if step == "adc_minus":
        try:
            amt = abs(int(txt.strip().replace(".", "").replace(",", "")))
        except ValueError:
            _edit("❌ Bukan angka.",
                  InlineKeyboardMarkup().add(
                      InlineKeyboardButton("⬅️ Batal",
                                           callback_data=f"adc_u:{st.get('uid')}")))
            return True
        tgt = st.get("uid")
        before, after = _cred_add(tgt, -amt, uid)
        NET_TMP.pop(uid, None)
        log.info("CREDIT admin=%s uid=%s -%d %d->%d", uid, tgt, amt, before, after)
        u = get_user(tgt)
        _edit(f"✅ <b>Saldo dikurangi</b>\n\n"
              f"🆔 <code>{tgt}</code> · {esc(u.get('name') or '-')}\n"
              f"➖ <code>-{amt:,}</code>\n"
              f"💰 <code>{before:,}</code> → <code>{after:,}</code>",
              _cred_kb_amount(tgt))
        return True

    return False


@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_"))
def on_admin(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id, "Bukan admin", show_alert=True)
        return
    act = c.data[4:]
    bot.answer_callback_query(c.id)

    if act == "home":
        try:
            bot.edit_message_text(txt_admin(), c.message.chat.id,
                                  c.message.message_id,
                                  reply_markup=kb_admin(), parse_mode="HTML")
        except Exception:
            bot.send_message(c.message.chat.id, txt_admin(),
                             reply_markup=kb_admin(), parse_mode="HTML")
        return

    if act == "status":
        ni = WK.call("netinfo", timeout=30)
        ping = WK.call("ping", timeout=90)
        bot.send_message(c.message.chat.id,
                         f"🖥 <b>Status</b>\n\n"
                         f"Worker: {'✅' if ping.get('ok') else '❌'}\n"
                         f"Mode: <code>{ni.get('mode','?')}</code>\n"
                         f"Endpoint: <code>{esc(ni.get('url') or '-')}</code>\n"
                         f"Cookie: <code>{ping.get('cookies','?')}</code>",
                         reply_markup=kb_admin())
        return

    if act == "restart":
        bot.send_message(c.message.chat.id, "🔄 restart worker...")
        try:
            WK.call("quit", timeout=10)
        except Exception:
            pass
        try:
            WK.p.kill()
        except Exception:
            pass
        WK.p = None
        ok = WK.call("ping", timeout=180)
        bot.send_message(c.message.chat.id,
                         f"{'✅' if ok.get('ok') else '❌'} worker hidup",
                         reply_markup=kb_admin())
        return

    # ADMIN_CREDIT_BRANCH_V2 — panel kredit user
    if act == "cred":
        kb, rows, total = _cred_kb_users()
        try:
            bot.edit_message_text(
                f"💳 <b>Kredit User</b>\n\n"
                f"Total user: <code>{total}</code>\n"
                f"Ditampilkan: <code>{len(rows)}</code> (saldo tertinggi)\n\n"
                f"Pilih user:",
                c.message.chat.id, c.message.message_id,
                reply_markup=kb, parse_mode="HTML")
        except Exception as e:
            if "not modified" not in str(e).lower():
                bot.send_message(c.message.chat.id,
                                 "💳 <b>Kredit User</b>\n\nPilih user:",
                                 reply_markup=kb, parse_mode="HTML")
        return

    if act == "gpm":
        try:
            g = GPM()
            bal = g.balance()
            bot.send_message(c.message.chat.id,
                             f"💰 <b>Saldo GPM</b>\n\n<code>Rp {bal:,.2f}</code>",
                             reply_markup=kb_admin())
        except GPMError as e:
            bot.send_message(c.message.chat.id, f"❌ {esc(e)}", reply_markup=kb_admin())
        return

    if act == "net":
        ni = WK.call("netinfo", timeout=30)
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton(
                   ("✅ " if ni.get("mode") == "proxy" else "") + "Pakai Proxy",
                   callback_data="net_proxy"),
               InlineKeyboardButton(
                   ("✅ " if ni.get("mode") == "direct" else "") + "Direct (tanpa proxy)",
                   callback_data="net_direct"),
               InlineKeyboardButton("⬅️ Kembali", callback_data="adm_back"))
        bot.send_message(c.message.chat.id,
                         f"🌐 <b>Jaringan</b>\n\n"
                         f"Mode sekarang: <code>{ni.get('mode','?')}</code>\n"
                         f"Endpoint: <code>{esc(ni.get('url') or '-')}</code>",
                         reply_markup=kb)
        return

    if act == "pool":
        pool = _proxy_pool()
        lines = [f"🔌 <b>Pool Proxy</b> ({len(pool)})", ""]
        for i, p in enumerate(pool, 1):
            mark = "✅" if p.get("active") else "▫️"
            lines.append(f"{mark} <code>{i}. {esc(p.get('name','-'))}</code>\n"
                         f"    <code>{esc(p.get('url','-')[:60])}</code>")
        if not pool:
            lines.append("<i>kosong</i>")
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton("➕ Tambah Proxy", callback_data="pool_add"),
               InlineKeyboardButton("🧪 Tes Semua", callback_data="pool_test"),
               InlineKeyboardButton("🗑 Hapus", callback_data="pool_del"),
               InlineKeyboardButton("⬅️ Kembali", callback_data="adm_back"))
        bot.send_message(c.message.chat.id, "\n".join(lines), reply_markup=kb)
        return

    if act == "set":
        mx = get_setting("max_cek", MAX_PER_CEK)
        kb = InlineKeyboardMarkup(row_width=3)
        for n in (10, 25, 50, 100, 200, 500):
            mark = "✅ " if n == mx else ""
            kb.add(InlineKeyboardButton(f"{mark}{n}", callback_data=f"setmax_{n}"))
        kb.add(InlineKeyboardButton("✏️ Input manual", callback_data="setmax_manual"))
        kb.add(InlineKeyboardButton("⬅️ Kembali", callback_data="adm_back"))
        bot.send_message(c.message.chat.id,
                         f"⚙️ <b>Setting</b>\n\n"
                         f"Maks nomor per 1x cek: <code>{mx}</code>",
                         reply_markup=kb)
        return

    if act == "back":
        bot.send_message(c.message.chat.id, txt_admin(), reply_markup=kb_admin())
        return


@bot.callback_query_handler(func=lambda c: c.data.startswith("setmax_"))
def on_setmax(c):
    if not is_admin(c.from_user.id):
        return
    val = c.data[7:]
    bot.answer_callback_query(c.id)
    if val == "manual":
        NET_TMP[c.from_user.id] = {"step": "max_cek"}
        bot.send_message(c.message.chat.id,
                         "Kirim angka batas maksimal nomor per 1x cek (1-500).")
        return
    n = int(val)
    set_setting("max_cek", n)
    bot.send_message(c.message.chat.id,
                     f"✅ Maks per cek: <code>{n}</code> nomor",
                     reply_markup=kb_admin())


@bot.callback_query_handler(func=lambda c: c.data in ("net_proxy", "net_direct"))
def on_net(c):
    if not is_admin(c.from_user.id):
        return
    bot.answer_callback_query(c.id)
    if c.data == "net_direct":
        bot.send_message(c.message.chat.id, "⏳ ganti ke DIRECT...")
        r = WK.call("setnet", mode="direct", timeout=240)
        bot.send_message(c.message.chat.id,
                         f"{'✅' if r.get('ok') else '❌'} mode="
                         f"<code>{r.get('mode')}</code>\n"
                         f"{('<i>'+esc(r.get('err') or '')+'</i>') if r.get('err') else ''}",
                         reply_markup=kb_admin())
        return
    # proxy: pakai entri aktif di pool, kalau kosong tanya URL
    pool = _proxy_pool()
    aktif = next((p for p in pool if p.get("active")), None)
    if not aktif:
        NET_TMP[c.from_user.id] = {"step": "url"}
        bot.send_message(c.message.chat.id,
                         "Kirim URL proxy, contoh:\n"
                         "<code>http://127.0.0.1:18080</code>")
        return
    bot.send_message(c.message.chat.id, f"⏳ ganti ke proxy {esc(aktif['name'])}...")
    r = WK.call("setnet", mode="proxy", url=aktif["url"], timeout=240)
    bot.send_message(c.message.chat.id,
                     f"{'✅' if r.get('ok') else '❌'} <code>{esc(r.get('url') or '')}</code>",
                     reply_markup=kb_admin())


@bot.callback_query_handler(func=lambda c: c.data in ("pool_add", "pool_test", "pool_del"))
def on_pool(c):
    if not is_admin(c.from_user.id):
        return
    bot.answer_callback_query(c.id)
    if c.data == "pool_add":
        NET_TMP[c.from_user.id] = {"step": "pool_add"}
        bot.send_message(c.message.chat.id,
                         "Kirim <code>nama|url</code>\n"
                         "contoh:\n<code>relay|http://127.0.0.1:18080</code>")
        return
    if c.data == "pool_del":
        NET_TMP[c.from_user.id] = {"step": "pool_del"}
        bot.send_message(c.message.chat.id, "Kirim nomor entri yang dihapus (lihat daftar).")
        return
    # test semua
    import urllib.request
    pool = _proxy_pool()
    bot.send_message(c.message.chat.id, f"🧪 tes {len(pool)} proxy...")
    out = []
    for p in pool:
        url = p.get("url", "")
        st = "❌"
        try:
            ph = urllib.request.ProxyHandler({"http": url, "https": url})
            op = urllib.request.build_opener(ph)
            with op.open("https://api.ipify.org?format=json", timeout=25) as r:
                ip = json.loads(r.read()).decode() if False else r.read().decode()
            st = f"✅ {ip[:40]}"
        except Exception as e:
            st = f"❌ {e.__class__.__name__}"
        out.append(f"<code>{esc(p.get('name','-'))}</code> → {esc(st)}")
    bot.send_message(c.message.chat.id, "\n".join(out) or "<i>pool kosong</i>",
                     reply_markup=kb_admin())


@bot.message_handler(func=lambda m: m.from_user.id in NET_TMP, content_types=["text"])
def on_admin_input(m: Message):
    st = NET_TMP.get(m.from_user.id) or {}
    step = st.get("step")
    txt = (m.text or "").strip()

    # --- Change Number flow ditangani chg_early_router (di atas) ---
    # --- input OTP (semua user, bukan cuma admin) ---
    if step == "otp_phone":
        NET_TMP.pop(m.from_user.id, None)
        ph = extract_phones(txt)
        if not ph:
            bot.reply_to(m, "❌ Nomor tidak valid. Kirim 10-13 digit, "
                            "contoh <code>089601416330</code>")
            return
        _otp_send_kode(m, ph[0], st.get("mode", "new"))
        return

    if step == "otp_code":
        NET_TMP.pop(m.from_user.id, None)
        code = re.sub(r"\D", "", txt)
        if len(code) < 4 or len(code) > 8:
            bot.reply_to(m, "❌ Kode harus 4-8 digit.")
            return
        _otp_verify_kode(m, code)
        return

    if step and step.startswith("otp_"):
        return

    if not is_admin(m.from_user.id):
        return

    if step == "url":
        NET_TMP.pop(m.from_user.id, None)
        bot.reply_to(m, "⏳ set proxy...")
        r = WK.call("setnet", mode="proxy", url=txt, timeout=240)
        bot.reply_to(m, f"{'✅' if r.get('ok') else '❌'} <code>{esc(r.get('url') or '')}</code>\n"
                        f"{esc(r.get('err') or '')}", reply_markup=kb_admin())
        return

    if step == "max_cek":
        NET_TMP.pop(m.from_user.id, None)
        try:
            n = int(txt)
        except Exception:
            bot.reply_to(m, "Bukan angka.")
            return
        if not (1 <= n <= 500):
            bot.reply_to(m, "Harus 1-500.")
            return
        set_setting("max_cek", n)
        bot.reply_to(m, f"✅ Maks per cek: <code>{n}</code> nomor",
                     reply_markup=kb_admin())
        return

    if step == "pool_add":
        NET_TMP.pop(m.from_user.id, None)
        if "|" not in txt:
            bot.reply_to(m, "Format salah. Pakai <code>nama|url</code>.")
            return
        name, url = [x.strip() for x in txt.split("|", 1)]
        pool = _proxy_pool()
        for p in pool:
            p["active"] = False
        pool.append({"name": name, "url": url, "active": True,
                     "added": int(time.time())})
        _save_pool(pool)
        bot.reply_to(m, f"✅ <code>{esc(name)}</code> ditambahkan & diaktifkan.\n"
                        f"Tekan <b>Jaringan → Pakai Proxy</b> untuk memakainya.",
                     reply_markup=kb_admin())
        return

    if step == "pool_del":
        NET_TMP.pop(m.from_user.id, None)
        try:
            i = int(txt) - 1
        except Exception:
            bot.reply_to(m, "Nomor tidak valid.")
            return
        pool = _proxy_pool()
        if not (0 <= i < len(pool)):
            bot.reply_to(m, "Nomor di luar rentang.")
            return
        gone = pool.pop(i)
        if not any(p.get("active") for p in pool) and pool:
            pool[0]["active"] = True
        _save_pool(pool)
        bot.reply_to(m, f"🗑 <code>{esc(gone.get('name','-'))}</code> dihapus.",
                     reply_markup=kb_admin())
        return


@bot.message_handler(commands=["addcookie"])
def cmd_addcookie(m: Message):
    if not is_admin(m.from_user.id):
        return
    parts = (m.text or "").split(maxsplit=1)
    if len(parts) < 2 or "=" not in parts[1]:
        bot.reply_to(m, "Format: <code>/addcookie csrftoken=...; SPC_X=REDACTED;</code>")
        return
    r = WK.call("addcookie", content=parts[1].strip(),
                name=f"ck_{int(time.time())}.txt", timeout=30)
    bot.reply_to(m, f"{'✅' if r.get('ok') else '❌'} cookie ditambah. "
                    f"Total: <code>{r.get('cookies','?')}</code>")


@bot.message_handler(commands=["reloadcookie"])
def cmd_reloadcookie(m: Message):
    if not is_admin(m.from_user.id):
        return
    r = WK.call("reload", timeout=30)
    bot.reply_to(m, f"{'✅' if r.get('ok') else '❌'} pool: <code>{r.get('cookies','?')}</code>")


@bot.message_handler(commands=["resetcookie"])
def cmd_resetcookie(m: Message):
    if not is_admin(m.from_user.id):
        return
    try:
        WK.call("quit", timeout=10)
    except Exception:
        pass
    try:
        WK.p.kill()
    except Exception:
        pass
    WK.p = None
    ok = WK.call("ping", timeout=120)
    bot.reply_to(m, f"{'✅' if ok.get('ok') else '❌'} worker restart. "
                    f"cookies=<code>{ok.get('cookies','?')}</code>")



# CHG_FLOW_REBUILD_V6
import changenumfast as _cn
import ivs_engine as cnivs  # IVS_UI_V2

CHG_BACK = InlineKeyboardMarkup().add(
    InlineKeyboardButton("❌ Batal", callback_data="mm_home"))


# IVS_UI_V2 — health TANPA get_settings_v2 (tidak menaikkan counter OTP)
def cn_health(cookie):
    """Status akun tanpa menyentuh endpoint OTP.

    get_settings_v2 MENAIKKAN counter anti-abuse per akun. Memanggilnya
    saat cookie masuk membuat akun sehat terlihat "diblokir".

    - get_account_info gagal      -> dead
    - init_v2 ivs_required True   -> ivs
    - init_v2 error 0             -> ok
    - selain itu                  -> limited
    """
    try:
        a = cn.Api(cookie)
        r = a.get("/api/v4/account/basic/get_account_info")
        if r.get("error") not in (0, None):
            return {"state": "dead",
                    "reason": f"Cookie mati / auth gagal (error {r.get('error')})."}
        ini = a.post("/api/v4/account/management/change_phone_init_v2",
                     {"phone": "628000000000", "seq_no": None})
        d = ini.get("data") or {}
        e = ini.get("error")
        if e == 0 and d.get("ivs_required"):
            return {"state": "ivs", "reason": "Akun minta verifikasi IVS.",
                    "ivs_utoken": d.get("ivs_utoken") or "",
                    "change_phone_token": d.get("change_phone_token") or ""}
        if e == 0:
            return {"state": "ok", "reason": "",
                    "change_phone_token": d.get("change_phone_token") or ""}
        return {"state": "limited",
                "reason": f"Init ganti nomor ditolak (error {e})."}
    except Exception as ex:
        return {"state": "dead", "reason": f"{type(ex).__name__}: {ex}"}


def _chg_edit(msg, text, kb=None):
    """Edit pesan yang sama. Kalau gagal, kirim baru."""
    try:
        bot.edit_message_text(text, chat_id=msg.chat.id, message_id=msg.message_id,
                              reply_markup=kb, parse_mode="HTML")
        return msg
    except Exception as e:
        if "message is not modified" in str(e).lower():
            return msg
        try:
            return bot.send_message(msg.chat.id, text, reply_markup=kb,
                                    parse_mode="HTML")
        except Exception:
            log.exception("chg edit/send")
            return msg


def _chg_err(r):
    """Format error Shopee untuk user — kode + pesan asli."""
    code = r.get("code") or r.get("error")
    reason = r.get("reason") or r.get("error_msg") or ""
    if code is None and not reason:
        return "❌ Gagal tanpa keterangan."
    out = []
    if code is not None:
        out.append(f"❌ <b>Error {code}</b>")
    if reason:
        out.append(f"<i>{esc(reason)}</i>")
    hint = r.get("hint")
    if hint:
        out.append(f"\n💡 {esc(hint)}")
    return "\n".join(out)


def _chg_chan_kb(cs):
    kb = InlineKeyboardMarkup(row_width=2)
    btns = []
    for ch in cs.get("channels", []):
        nm = _cn.CHANNEL_NAME.get(ch, f"Ch{ch}")
        ic = {1: "💬", 2: "📞", 3: "🟢", 4: "📧"}.get(ch, "📨")
        btns.append(InlineKeyboardButton(f"{ic} {nm}", callback_data=f"chg:ch:{ch}"))
    for i in range(0, len(btns), 2):
        kb.add(*btns[i:i + 2])
    kb.add(InlineKeyboardButton("❌ Batal", callback_data="mm_home"))
    return kb


# IVS_UI_V2 — pilih metode IVS
@bot.callback_query_handler(func=lambda c: c.data.startswith("ivsm:"))
def on_ivsm(c):
    uid = c.from_user.id
    try:
        c.answer()
    except Exception:
        pass
    st = NET_TMP.get(uid) or {}
    cs = st.get("chg") or {}
    if st.get("step") != "chg_ivsm":
        return
    t = int(c.data.split(":")[1])
    m = next((x for x in cs.get("ivs_methods") or [] if x["type"] == t), None)
    if not m:
        return
    cs["ivs_method"] = t
    cs["ivs_vtoken"] = m["v_token"]
    msg = st.get("msg") or c.message

    if t == 2:
        NET_TMP[uid] = {"step": "chg_ivs_pw", "chg": cs, "msg": msg}
        _chg_edit(msg,
                  f"🔑 <b>Verifikasi dengan Password</b>\n\n"
                  f"Kirim password akun Shopee lo.\n"
                  f"<i>(pesan lo dihapus otomatis)</i>",
                  InlineKeyboardMarkup().add(
                      InlineKeyboardButton("❌ Batal", callback_data="chg:start")))
        return

    if t in (3, 10):
        NET_TMP[uid] = {"step": "chg_ivs_pin", "chg": cs, "msg": msg}
        _chg_edit(msg,
                  f"💳 <b>Verifikasi dengan PIN ShopeePay</b>\n\n"
                  f"Kirim PIN 6 digit ShopeePay lo.\n"
                  f"<i>(pesan lo dihapus otomatis)</i>",
                  InlineKeyboardMarkup().add(
                      InlineKeyboardButton("❌ Batal", callback_data="chg:start")))
        return

    r = cnivs.select(cs["cookie"], cs["ivs_utoken"], t, m["v_token"])
    if not r.get("ok"):
        NET_TMP.pop(uid, None)
        _chg_edit(msg,
                  f"❌ <b>Gagal pilih metode</b>\n"
                  f"<code>{esc(m['name'])}</code> ditolak "
                  f"(error <code>{esc(str(r.get('error')))}</code>).\n\n"
                  f"💡 Coba metode lain atau akun lain.",
                  InlineKeyboardMarkup().add(
                      InlineKeyboardButton("🔁 Ulang", callback_data="chg:start")))
        return
    NET_TMP[uid] = {"step": "chg_ivs_code", "chg": cs, "msg": msg}
    _chg_edit(msg,
              f"📧 <b>Verifikasi via {esc(m['name'])}</b>\n\n"
              f"Shopee mengirim kode / link ke akun lo.\n\n"
              f"Kirim kodenya di sini.",
              InlineKeyboardMarkup().add(
                  InlineKeyboardButton("❌ Batal", callback_data="chg:start")))


def chg_cb(c, uid, act):
    st = NET_TMP.get(uid) or {}
    cs = st.get("chg") or {}
    msg = st.get("msg") or c.message
    bot.answer_callback_query(c.id)

    if act == "start":
        NET_TMP[uid] = {"step": "chg_cookie", "chg": {}, "msg": msg}
        _chg_edit(msg,
            "📱 <b>Change Number</b>\n\n"
            "Kirim <b>cookie akun Shopee</b>\n"
            "(harus ada <code>SPC_U</code> + <code>csrftoken</code>)",
            CHG_BACK)
        return

    if act == "retry":
        NET_TMP[uid] = {"step": "chg_phone", "chg": cs, "msg": msg}
        _chg_edit(msg,
            f"👤 <code>{esc(cs.get('username','?'))}</code>\n"
            f"📞 Lama: <code>{esc(str(cs.get('old_phone','?')))}</code>\n\n"
            "Kirim <b>nomor baru</b>:\n"
            "<code>08xxx</code> atau <code>628xxx</code>",
            CHG_BACK)
        return

    if act.startswith("ch:"):
        ch = int(act.split(":")[1])
        if not cs.get("phone") or not cs.get("cp"):
            _chg_edit(msg, "⚠️ Sesi habis. Ulangi.", CHG_BACK)
            return
        NET_TMP[uid] = {"step": "chg_wait", "chg": cs, "msg": msg}
        _chg_edit(msg,
            f"⏳ Kirim OTP via <b>{_cn.CHANNEL_NAME.get(ch, ch)}</b>…", None)

        def _w():
            try:
                t0 = time.time()
                r = _cn.request_otp(cs["cookie"], cs["phone"], cs["cp"],
                                    cs.get("seed", ""), ch, op=cs.get("op"))
                if not r.get("ok"):
                    NET_TMP[uid] = {"step": "chg_chan", "chg": cs, "msg": msg}
                    _chg_edit(msg,
                        f"{_chg_err(r)}\n\nPilih channel lain:",
                        _chg_chan_kb(cs))
                    return
                cs["channel"] = ch
                cs["op"] = r.get("op", cs.get("op"))
                NET_TMP[uid] = {"step": "chg_otp", "chg": cs, "msg": msg}
                _chg_edit(msg,
                    f"✅ <b>OTP terkirim</b> via "
                    f"{_cn.CHANNEL_NAME.get(ch, ch)}\n"
                    f"📞 <code>{esc(cs['phone'])}</code>\n"
                    f"<i>{time.time()-t0:.2f}s</i>\n\n"
                    "Kirim <b>kode 6 digit</b>.",
                    CHG_BACK)
                log.info("CHG otp ok uid=%s ch=%s op=%s %.2fs",
                         uid, ch, cs.get("op"), time.time()-t0)
            except Exception:
                log.exception("chg otp")
                _chg_edit(msg, "❌ Error internal.", CHG_BACK)

        threading.Thread(target=_w, daemon=True).start()
        return


def chg_handle_text(m, uid, txt):
    st = NET_TMP.get(uid) or {}
    step = st.get("step") or ""
    if not step.startswith("chg_"):
        return False
    cs = st.setdefault("chg", {})

    # ------------------------------------------------------------------
    # 1) COOKIE → PESAN BARU berisi data akun
    # ------------------------------------------------------------------
    if step == "chg_cookie":
        log.info("CHG cookie uid=%s is_cookie=%s", uid, _cn.is_cookie(txt))
        if not _cn.is_cookie(txt):
            bot.reply_to(m, "❌ Bukan cookie Shopee (butuh <code>SPC_</code>).")
            return True
        cs["cookie"] = txt
        wait = bot.reply_to(m, "⏳ Cek akun…")

        def _w():
            try:
                t0 = time.time()
                acc = _cn.check_account(cs["cookie"])
                if not acc.get("ok"):
                    NET_TMP.pop(uid, None)
                    _chg_edit(wait,
                        f"{_chg_err(acc)}\n\nKirim ulang cookie.",
                        InlineKeyboardMarkup().add(
                            InlineKeyboardButton("📱 Mulai Lagi",
                                                 callback_data="chg:start")))
                    return
                cs["username"] = acc["username"]
                cs["old_phone"] = acc["phone"]

                # HEALTH_WIRE_V1 — cek flag anti-crawler sebelum lanjut
                h = {"state": "ok", "blocked": [], "reason": ""}
                try:
                    h = cn_health(cs["cookie"])
                except Exception:
                    log.exception("health check")

                if h.get("state") == "dead":
                    NET_TMP.pop(uid, None)
                    _chg_edit(wait,
                        f"❌ <b>Cookie mati</b>\n\n{esc(h.get('reason',''))}\n\n"
                        f"Ambil cookie baru.",
                        InlineKeyboardMarkup().add(
                            InlineKeyboardButton("📱 Mulai Lagi",
                                                 callback_data="chg:start")))
                    return

                st_h = h.get("state")

                # HEALTH_UI_V3 — blokir hanya kalau benar-benar tidak bisa
                if st_h == "ivs":
                    # IVS_UI_V2 — ambil method lalu tampilkan tombol
                    ut = h.get("ivs_utoken") or ""
                    mm = cnivs.methods(cs["cookie"], ut) if ut else \
                        {"ok": False, "methods": [], "error": "no_utoken"}
                    if not mm.get("ok") or not mm.get("methods"):
                        NET_TMP.pop(uid, None)
                        _chg_edit(wait,
                            f"🔐 <b>Akun terdeteksi</b>\n\n"
                            f"👤 <code>{esc(acc['username'])}</code>\n"
                            f"<i>{time.time()-t0:.2f}s</i>\n\n"
                            f"❌ <b>Akun minta verifikasi IVS</b>\n"
                            f"Shopee tidak menawarkan metode apa pun "
                            f"(error <code>{esc(str(mm.get('error')))}</code>).\n\n"
                            f"💡 Selesaikan IVS di app Shopee dulu.",
                            InlineKeyboardMarkup(row_width=2).add(
                                InlineKeyboardButton("🔁 Coba Akun Lain",
                                                     callback_data="chg:start"),
                                InlineKeyboardButton("🏠 Menu",
                                                     callback_data="mm_home")))
                        return

                    cs["ivs_utoken"] = ut
                    cs["ivs_methods"] = mm["methods"]
                    NET_TMP[uid] = {"step": "chg_ivsm", "chg": cs, "msg": wait}

                    ICON = {"PASSWORD": "🔑", "NEW_SHOPEEPAY_PIN": "💳",
                            "SHOPEEPAY": "💳", "EMAIL": "📧",
                            "EMAIL_LINK": "📧", "OTP": "📱",
                            "WHATSAPP_LINK": "💬", "QR": "📷",
                            "AUTH_LINK": "🔗", "SECURITY_EMAIL": "📧",
                            "SECURITY_QUESTIONS": "❓",
                            "DEVICE_TOKEN": "📱", "SKIP": "⏭"}
                    kb = InlineKeyboardMarkup(row_width=2)
                    for m in mm["methods"]:
                        kb.row(InlineKeyboardButton(
                            f"{ICON.get(m['name'], '•')} {m['name']}",
                            callback_data=f"ivsm:{m['type']}"))
                    kb.row(InlineKeyboardButton("❌ Batal",
                                                callback_data="chg:start"))

                    names = "\n".join(
                        f"• <b>{esc(m['name'])}</b>" for m in mm["methods"])
                    _chg_edit(wait,
                        f"🔐 <b>Akun terdeteksi</b>\n\n"
                        f"👤 <code>{esc(acc['username'])}</code>\n"
                        f"<i>{time.time()-t0:.2f}s</i>\n\n"
                        f"⚠️ <b>Akun minta verifikasi IVS</b>\n"
                        f"Shopee menawarkan {len(mm['methods'])} metode:\n"
                        f"{names}\n\n"
                        f"👇 <b>Pilih metode verifikasi:</b>",
                        kb)
                    log.info("CHG ivs uid=%s user=%s methods=%s", uid,
                             acc["username"],
                             [m["type"] for m in mm["methods"]])
                    return

                if st_h == "limited":
                    NET_TMP.pop(uid, None)
                    _chg_edit(wait,
                        f"🔐 <b>Akun terdeteksi</b>\n\n"
                        f"👤 <code>{esc(acc['username'])}</code>\n"
                        f"<i>{time.time()-t0:.2f}s</i>\n\n"
                        f"⚠️ <b>Nomor tidak bisa diganti sekarang</b>\n"
                        f"<i>{esc(h.get('reason',''))}</i>\n\n"
                        f"💡 Tunggu beberapa jam, atau pakai akun lain.",
                        InlineKeyboardMarkup(row_width=2).add(
                            InlineKeyboardButton("🔁 Coba Akun Lain",
                                                 callback_data="chg:start"),
                            InlineKeyboardButton("🏠 Menu",
                                                 callback_data="mm_home")))
                    log.info("CHG limited uid=%s user=%s %s",
                             uid, acc["username"], h.get("ops"))
                    return

                warn = ""

                # PESAN BARU (bukan edit) — data akun + minta nomor
                card = bot.send_message(m.chat.id,
                    f"🔐 <b>Akun terdeteksi</b>\n\n"
                    f"👤 Username: <code>{esc(acc['username'])}</code>\n"
                    f"📞 Nomor lama: <code>{esc(str(acc['phone']))}</code>\n"
                    f"✅ Verified: {acc.get('verified')}\n"
                    f"🟢 Status: siap ganti nomor\n"
                    f"<i>{time.time()-t0:.2f}s</i>\n"
                    f"{warn}\n"
                    f"Kirim <b>nomor baru</b> yang mau dipasang:\n"
                    f"<code>08xxx</code> atau <code>628xxx</code>",
                    reply_markup=CHG_BACK)

                # hapus pesan "Cek akun…" biar bersih
                try:
                    bot.delete_message(wait.chat.id, wait.message_id)
                except Exception:
                    pass

                NET_TMP[uid] = {"step": "chg_phone", "chg": cs, "msg": card}
                log.info("CHG acct ok uid=%s user=%s %.2fs",
                         uid, acc["username"], time.time()-t0)
            except Exception:
                log.exception("chg cookie")
                _chg_edit(wait, "❌ Error internal.", CHG_BACK)

        threading.Thread(target=_w, daemon=True).start()
        return True

    # ------------------------------------------------------------------
    # 1b) IVS: password / pin / kode
    # ------------------------------------------------------------------
    if step in ("chg_ivs_pw", "chg_ivs_pin", "chg_ivs_code"):
        try:
            m.delete()
        except Exception:
            pass
        msg = st.get("msg") or m
        t = cs.get("ivs_method")
        ut = cs.get("ivs_utoken")
        vt = cs.get("ivs_vtoken")
        _chg_edit(msg, f"⏳ Verifikasi IVS (metode {t})…", None)

        if step == "chg_ivs_pw":
            ver = cnivs.verify_password(cs["cookie"], txt)
        elif step == "chg_ivs_pin":
            ver = cnivs.verify_pin(cs["cookie"], txt)
        else:
            ver = {"ok": True, "rc_token": txt.strip()}

        if not ver.get("ok"):
            NET_TMP[uid] = {"step": "chg_ivsm", "chg": cs, "msg": msg}
            kb = InlineKeyboardMarkup(row_width=2)
            for mm2 in cs.get("ivs_methods") or []:
                kb.row(InlineKeyboardButton(
                    f"• {mm2['name']}", callback_data=f"ivsm:{mm2['type']}"))
            kb.row(InlineKeyboardButton("❌ Batal", callback_data="chg:start"))
            _chg_edit(msg,
                      f"❌ <b>Verifikasi gagal</b>\n\n"
                      f"Metode: <b>{esc(str(t))}</b>\n"
                      f"Error: <code>{esc(str(ver.get('error')))}</code>\n\n"
                      f"💡 Password/PIN salah. Pilih metode lagi:",
                      kb)
            return True

        tv = cnivs.token_verify(cs["cookie"], ut, vt,
                                ver.get("rc_token") or "", t)
        if not tv.get("ok"):
            NET_TMP.pop(uid, None)
            _chg_edit(msg,
                      f"❌ <b>Token IVS gagal</b>\n\n"
                      f"Error: <code>{esc(str(tv.get('error')))}</code>",
                      InlineKeyboardMarkup().add(
                          InlineKeyboardButton("🔁 Ulang",
                                               callback_data="chg:start")))
            return True

        cs["ivs_signature"] = tv.get("ivs_signature") or ""
        cs["ivs_method_str"] = str(t)
        NET_TMP[uid] = {"step": "chg_phone", "chg": cs, "msg": msg}
        _chg_edit(msg,
                  f"✅ <b>IVS terverifikasi</b>\n\n"
                  f"👤 <code>{esc(cs.get('username') or '')}</code>\n"
                  f"📞 Nomor lama: <code>{esc(str(cs.get('old_phone')))}</code>\n"
                  f"🔐 Metode: <b>{esc(str(t))}</b>\n"
                  f"🟢 Siap ganti nomor\n\n"
                  f"Kirim <b>nomor baru</b> "
                  f"(<code>08xxx</code> / <code>628xxx</code>):",
                  CHG_BACK)
        log.info("CHG ivs ok uid=%s method=%s sig=%sB", uid, t,
                 len(cs["ivs_signature"]))
        return True

    # ------------------------------------------------------------------
    # 2) NOMOR BARU → cek fresh / bisa unbind
    # ------------------------------------------------------------------
    if step == "chg_phone":
        ph = _cn.norm_phone(txt)
        if not ph:
            bot.reply_to(m, "❌ Nomor tidak valid.\nContoh: <code>08123456789</code>")
            return True
        msg = st.get("msg") or m
        NET_TMP[uid] = {"step": "chg_wait", "chg": cs, "msg": msg}
        _chg_edit(msg,
            f"⏳ Cek nomor <code>{esc(ph)}</code>\n"
            f"fresh & bisa unbind…", None)

        def _w():
            try:
                t0 = time.time()
                r = _cn.check_number(cs["cookie"], ph)
                if not r.get("ok"):
                    NET_TMP[uid] = {"step": "chg_phone", "chg": cs, "msg": msg}
                    _chg_edit(msg,
                        f"{_chg_err(r)}\n\n"
                        f"Kirim <b>nomor lain</b>:",
                        InlineKeyboardMarkup().add(
                            InlineKeyboardButton("🔁 Nomor Lain",
                                                 callback_data="chg:retry")))
                    log.info("CHG num reject uid=%s ph=%s code=%s %s",
                             uid, ph, r.get("code"), r.get("reason"))
                    return

                cs.update({"phone": ph, "cp": r["cp"],
                           "seed": r.get("seed", ""),
                           "channels": r.get("channels", []),
                           "op": r.get("op")})
                NET_TMP[uid] = {"step": "chg_chan", "chg": cs, "msg": msg}

                chs = cs["channels"]
                names = ", ".join(_cn.CHANNEL_NAME.get(c, str(c)) for c in chs)
                cap = "⚠️ butuh captcha" if r.get("need_captcha") else "✅ tanpa captcha"
                _chg_edit(msg,
                    f"✅ <b>Nomor fresh</b> — bisa dipakai\n\n"
                    f"📞 <code>{esc(ph)}</code>\n"
                    f"🔓 Unbind: OK\n"
                    f"{cap}\n"
                    f"📡 Channel ({len(chs)}): {names}\n"
                    f"⚙️ Op: {r.get('op')}\n"
                    f"<i>{time.time()-t0:.2f}s</i>\n\n"
                    "Pilih <b>channel OTP</b>:",
                    _chg_chan_kb(cs))
                log.info("CHG num ok uid=%s ph=%s op=%s ch=%s %.2fs",
                         uid, ph, r.get("op"), chs, time.time()-t0)
            except Exception:
                log.exception("chg num")
                _chg_edit(msg, "❌ Error internal.", CHG_BACK)

        threading.Thread(target=_w, daemon=True).start()
        return True

    # ------------------------------------------------------------------
    # 3) KODE OTP → verify + commit
    # ------------------------------------------------------------------
    if step == "chg_otp":
        code = re.sub(r"\D", "", txt)
        if len(code) < 4:
            bot.reply_to(m, "❌ Kirim kode OTP (angka).")
            return True
        msg = st.get("msg") or m
        NET_TMP[uid] = {"step": "chg_wait", "chg": cs, "msg": msg}
        _chg_edit(msg, f"⏳ Verify <code>{code}</code>…", None)

        def _w():
            try:
                t0 = time.time()
                v = _cn.verify_vcode(cs["cookie"], cs["phone"], code, cs["cp"],
                                     op=cs.get("op"))
                if not v.get("ok"):
                    NET_TMP[uid] = {"step": "chg_otp", "chg": cs, "msg": msg}
                    _chg_edit(msg,
                        f"{_chg_err(v)}\n\n"
                        "Kirim kode benar, atau ulangi:",
                        InlineKeyboardMarkup(row_width=2).add(
                            InlineKeyboardButton("🔁 Nomor Lagi",
                                                 callback_data="chg:retry"),
                            InlineKeyboardButton("🏠 Menu",
                                                 callback_data="mm_home")))
                    log.info("CHG verify fail uid=%s %s", uid, v)
                    return

                _chg_edit(msg,
                    f"✅ Kode valid <i>{time.time()-t0:.2f}s</i>\n"
                    f"⏳ Commit ke Shopee…", None)

                cm = _cn.commit_change(cs["cookie"], cs["phone"], cs["cp"],
                                       v["vcode_token"])
                NET_TMP.pop(uid, None)
                if cm.get("ok"):
                    _chg_edit(msg,
                        f"🎉 <b>NOMOR BERHASIL DIGANTI</b>\n\n"
                        f"👤 <code>{esc(cm.get('username','?'))}</code>\n"
                        f"📞 <code>{esc(str(cs.get('old_phone')))}</code>\n"
                        f"   → <code>{esc(str(cm.get('new_phone')))}</code>\n"
                        f"✅ verified: {cm.get('verified')}\n"
                        f"<i>total {time.time()-t0:.1f}s</i>",
                        InlineKeyboardMarkup(row_width=2).add(
                            InlineKeyboardButton("📱 Ganti Lagi",
                                                 callback_data="chg:start"),
                            InlineKeyboardButton("🏠 Menu",
                                                 callback_data="mm_home")))
                    log.info("CHG OK uid=%s %s -> %s", uid,
                             cs.get("old_phone"), cm.get("new_phone"))
                else:
                    _chg_edit(msg,
                        f"{_chg_err(cm)}\n\nCoba lagi:",
                        InlineKeyboardMarkup(row_width=2).add(
                            InlineKeyboardButton("🔁 Nomor Lagi",
                                                 callback_data="chg:retry"),
                            InlineKeyboardButton("🏠 Menu",
                                                 callback_data="mm_home")))
                    log.info("CHG commit fail uid=%s %s", uid, cm)
            except Exception:
                log.exception("chg commit")
                NET_TMP.pop(uid, None)
                _chg_edit(msg, "❌ Error internal.", CHG_BACK)

        threading.Thread(target=_w, daemon=True).start()
        return True

    if step == "chg_wait":
        return True

    return False


@bot.message_handler(
    func=lambda m: is_admin(m.from_user.id)
    and str((NET_TMP.get(m.from_user.id) or {}).get("step") or "").startswith("adc_"),
    content_types=["text"])
def adc_router(m: Message):
    """Router input teks panel kredit admin."""
    uid = m.from_user.id
    txt = (m.text or "").strip()
    try:
        adc_handle_text(m, uid, txt)
    except Exception:
        log.exception("adc router")
        bot.reply_to(m, "❌ Error internal panel kredit.")


@bot.callback_query_handler(func=lambda c: c.data.startswith("chg:"))
def on_chg(c):
    d = c.data[4:]
    uid = c.from_user.id
    if d.startswith("ch:"):
        chg_cb(c, uid, "ch:" + d.split(":")[1])
    else:
        chg_cb(c, uid, d)


# ==== /CHANGE NUMBER ====



# ================= MAIN =================
def set_commands():
    """Daftarkan command list ke Telegram (menu biru di kiri input)."""
    cmds = [
        types.BotCommand("start", "Menu utama"),
        types.BotCommand("cek", "Cek nomor (bisa langsung kirim nomor)"),
        types.BotCommand("saldo", "Lihat saldo"),
        types.BotCommand("topup", "Isi saldo via QRIS"),
        types.BotCommand("harga", "Daftar harga"),
        types.BotCommand("stats", "Statistik sistem"),
        types.BotCommand("admin", "Panel admin"),
    ]
    try:
        bot.set_my_commands(cmds)
        log.info("setMyCommands ok (%d)", len(cmds))
    except Exception as e:
        log.warning("setMyCommands gagal: %s", e)
    # scope admin: sembunyikan admin dari user biasa
    for uid in ADMIN_IDS:
        try:
            bot.set_my_commands(
                cmds + [types.BotCommand("addcookie", "Tambah cookie Shopee"),
                        types.BotCommand("reloadcookie", "Reload cookie pool")],
                scope=types.BotCommandScopeChat(uid))
        except Exception as e:
            log.warning("setMyCommands admin %s gagal: %s", uid, e)


def main():
    log.info("bot start | admin=%s | price=%d", ADMIN_IDS, PRICE_PER_CHECK)
    threading.Thread(target=lambda: WK.call("ping", timeout=180), daemon=True).start()
    threading.Thread(target=set_commands, daemon=True).start()
    if os.environ.get("RKT_WEBHOOK") == "1":
        log.info("mode=WEBHOOK (polling off)")
        import time as _t
        while True:
            _t.sleep(3600)
    bot.infinity_polling(timeout=30, long_polling_timeout=25)


if __name__ == "__main__":
    main()
