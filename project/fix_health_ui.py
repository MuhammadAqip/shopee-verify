# -*- coding: utf-8 -*-
"""fix_health_ui.py — UI untuk state baru: ok / ivs / limited / dead.

Sebelumnya bot hanya tahu "limited" → tampil warning anti-crawler di semua akun.
Sekarang tiap state punya pesan sendiri, dan hanya `limited` yang memblokir.

Idempotent: HEALTH_UI_V3
"""
import io
import shutil
import time

P = "/root/shopee-verify/shopee_bot.py"
MARK = "# HEALTH_UI_V3"

src = io.open(P, encoding="utf-8").read()
if MARK in src:
    print("sudah dipatch")
    raise SystemExit(0)

shutil.copy2(P, P + ".bakhu." + str(int(time.time())))

OLD = '''                warn = ""
                if h.get("state") == "limited":
                    bl = ", ".join(h.get("blocked") or [])
                    warn = (f"\\n⚠️ <b>AKUN KENA FLAG ANTI-CRAWLER</b>\\n"
                            f"<i>{len(h.get('blocked') or [])} endpoint diblok: "
                            f"{esc(bl)}</i>\\n"
                            f"❗ Ganti nomor kemungkinan besar GAGAL di akun ini.\\n"
                            f"💡 Pakai cookie akun lain untuk hasil terbaik.\\n")
                    cs["flagged"] = True'''

NEW = '''                st_h = h.get("state")

                # HEALTH_UI_V3 — blokir hanya kalau benar-benar tidak bisa
                if st_h == "ivs":
                    NET_TMP.pop(uid, None)
                    _chg_edit(wait,
                        f"🔐 <b>Akun terdeteksi</b>\\n\\n"
                        f"👤 <code>{esc(acc['username'])}</code>\\n"
                        f"<i>{time.time()-t0:.2f}s</i>\\n\\n"
                        f"❌ <b>Akun minta verifikasi identitas (IVS)</b>\\n"
                        f"Shopee minta selfie + KTP sebelum nomor bisa diganti.\\n\\n"
                        f"💡 Selesaikan IVS di app Shopee dulu, "
                        f"lalu kirim cookie lagi.",
                        InlineKeyboardMarkup(row_width=2).add(
                            InlineKeyboardButton("🔁 Coba Akun Lain",
                                                 callback_data="chg:start"),
                            InlineKeyboardButton("🏠 Menu",
                                                 callback_data="mm_home")))
                    log.info("CHG ivs uid=%s user=%s", uid, acc["username"])
                    return

                if st_h == "limited":
                    NET_TMP.pop(uid, None)
                    _chg_edit(wait,
                        f"🔐 <b>Akun terdeteksi</b>\\n\\n"
                        f"👤 <code>{esc(acc['username'])}</code>\\n"
                        f"<i>{time.time()-t0:.2f}s</i>\\n\\n"
                        f"⚠️ <b>Nomor tidak bisa diganti sekarang</b>\\n"
                        f"<i>{esc(h.get('reason',''))}</i>\\n\\n"
                        f"💡 Tunggu beberapa jam, atau pakai akun lain.",
                        InlineKeyboardMarkup(row_width=2).add(
                            InlineKeyboardButton("🔁 Coba Akun Lain",
                                                 callback_data="chg:start"),
                            InlineKeyboardButton("🏠 Menu",
                                                 callback_data="mm_home")))
                    log.info("CHG limited uid=%s user=%s %s",
                             uid, acc["username"], h.get("ops"))
                    return

                warn = ""'''

assert OLD in src, "blok health UI tidak ketemu"
src = src.replace(OLD, NEW, 1)

# kartu sukses: tambah tanda sehat
OLD2 = '''                    f"✅ Verified: {acc.get('verified')}\\n"
                    f"<i>{time.time()-t0:.2f}s</i>\\n"
                    f"{warn}\\n"'''
NEW2 = '''                    f"✅ Verified: {acc.get('verified')}\\n"
                    f"🟢 Status: siap ganti nomor\\n"
                    f"<i>{time.time()-t0:.2f}s</i>\\n"
                    f"{warn}\\n"'''
if OLD2 in src:
    src = src.replace(OLD2, NEW2, 1)

io.open(P, "w", encoding="utf-8").write(src)
print("PATCH SELESAI:", P)
