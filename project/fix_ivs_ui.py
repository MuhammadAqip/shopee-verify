# -*- coding: utf-8 -*-
"""fix_ivs_ui.py — IVS lengkap di bot + health tanpa counter OTP.

Struktur asli (dibaca dulu, baru dipatch):
  NET_TMP[uid] = {"step": "chg_<x>", "chg": cs, "msg": pesan}
  chg_handle_text(m, uid, txt) -> bool

Perubahan:
  1. account_health -> cn_health yang TIDAK memanggil get_settings_v2.
     (get_settings_v2 menaikkan counter OTP → akun terlihat "diblokir")
  2. State IVS: tampilkan tombol inline per method dari ivs/methods.
  3. Handler `ivsm:<t>` -> pilih method -> minta password / PIN / kode.
  4. Input password/PIN -> verify -> token_verify -> ivs_signature.
  5. Lanjut ke chg_phone dengan signature tersimpan.

Idempotent: IVS_UI_V2
"""
import io
import re
import shutil
import time

P = "/root/shopee-verify/shopee_bot.py"
MARK = "# IVS_UI_V2"

src = io.open(P, encoding="utf-8").read()
if MARK in src:
    print("sudah dipatch")
    raise SystemExit(0)

shutil.copy2(P, P + ".bakivs." + str(int(time.time())))

# ---------------------------------------------------------------------------
# 1. cn_health (tanpa get_settings_v2)
# ---------------------------------------------------------------------------
NEW_HEALTH = '''# IVS_UI_V2 — health TANPA get_settings_v2 (tidak menaikkan counter OTP)
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


'''

i = src.find("def _chg_edit(")
assert i != -1, "_chg_edit tidak ketemu"
src = src[:i] + NEW_HEALTH + src[i:]

# ganti pemakaian account_health -> cn_health
src = re.sub(r"\b_cn\.account_health\(", "_cn_h(", src)
src = src.replace("_cn_h(", "cn_health(", 0)  # no-op guard

# ---------------------------------------------------------------------------
# 2. blok IVS: tampilkan tombol method
# ---------------------------------------------------------------------------
OLD_IVS = '''                if st_h == "ivs":
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
                    return'''

NEW_IVS = '''                if st_h == "ivs":
                    # IVS_UI_V2 — ambil method lalu tampilkan tombol
                    ut = h.get("ivs_utoken") or ""
                    mm = cnivs.methods(cs["cookie"], ut) if ut else \\
                        {"ok": False, "methods": [], "error": "no_utoken"}
                    if not mm.get("ok") or not mm.get("methods"):
                        NET_TMP.pop(uid, None)
                        _chg_edit(wait,
                            f"🔐 <b>Akun terdeteksi</b>\\n\\n"
                            f"👤 <code>{esc(acc['username'])}</code>\\n"
                            f"<i>{time.time()-t0:.2f}s</i>\\n\\n"
                            f"❌ <b>Akun minta verifikasi IVS</b>\\n"
                            f"Shopee tidak menawarkan metode apa pun "
                            f"(error <code>{esc(str(mm.get('error')))}</code>).\\n\\n"
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

                    names = "\\n".join(
                        f"• <b>{esc(m['name'])}</b>" for m in mm["methods"])
                    _chg_edit(wait,
                        f"🔐 <b>Akun terdeteksi</b>\\n\\n"
                        f"👤 <code>{esc(acc['username'])}</code>\\n"
                        f"<i>{time.time()-t0:.2f}s</i>\\n\\n"
                        f"⚠️ <b>Akun minta verifikasi IVS</b>\\n"
                        f"Shopee menawarkan {len(mm['methods'])} metode:\\n"
                        f"{names}\\n\\n"
                        f"👇 <b>Pilih metode verifikasi:</b>",
                        kb)
                    log.info("CHG ivs uid=%s user=%s methods=%s", uid,
                             acc["username"],
                             [m["type"] for m in mm["methods"]])
                    return'''

assert OLD_IVS in src, "blok IVS tidak ketemu"
src = src.replace(OLD_IVS, NEW_IVS, 1)

# ---------------------------------------------------------------------------
# 3. import ivs_engine
# ---------------------------------------------------------------------------
if "import ivs_engine as cnivs" not in src:
    assert "import changenumfast as cn" in src or "_cn" in src
    # cari baris import changenumfast
    m = re.search(r"^(import changenumfast as \w+|from changenumfast import .+)$",
                  src, re.M)
    assert m, "import changenumfast tidak ketemu"
    src = (src[:m.end()] + "\nimport ivs_engine as cnivs  # IVS_UI_V2"
           + src[m.end():])

# ---------------------------------------------------------------------------
# 4. handler callback ivsm:
# ---------------------------------------------------------------------------
HANDLER = '''# IVS_UI_V2 — pilih metode IVS
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
                  f"🔑 <b>Verifikasi dengan Password</b>\\n\\n"
                  f"Kirim password akun Shopee lo.\\n"
                  f"<i>(pesan lo dihapus otomatis)</i>",
                  InlineKeyboardMarkup().add(
                      InlineKeyboardButton("❌ Batal", callback_data="chg:start")))
        return

    if t in (3, 10):
        NET_TMP[uid] = {"step": "chg_ivs_pin", "chg": cs, "msg": msg}
        _chg_edit(msg,
                  f"💳 <b>Verifikasi dengan PIN ShopeePay</b>\\n\\n"
                  f"Kirim PIN 6 digit ShopeePay lo.\\n"
                  f"<i>(pesan lo dihapus otomatis)</i>",
                  InlineKeyboardMarkup().add(
                      InlineKeyboardButton("❌ Batal", callback_data="chg:start")))
        return

    r = cnivs.select(cs["cookie"], cs["ivs_utoken"], t, m["v_token"])
    if not r.get("ok"):
        NET_TMP.pop(uid, None)
        _chg_edit(msg,
                  f"❌ <b>Gagal pilih metode</b>\\n"
                  f"<code>{esc(m['name'])}</code> ditolak "
                  f"(error <code>{esc(str(r.get('error')))}</code>).\\n\\n"
                  f"💡 Coba metode lain atau akun lain.",
                  InlineKeyboardMarkup().add(
                      InlineKeyboardButton("🔁 Ulang", callback_data="chg:start")))
        return
    NET_TMP[uid] = {"step": "chg_ivs_code", "chg": cs, "msg": msg}
    _chg_edit(msg,
              f"📧 <b>Verifikasi via {esc(m['name'])}</b>\\n\\n"
              f"Shopee mengirim kode / link ke akun lo.\\n\\n"
              f"Kirim kodenya di sini.",
              InlineKeyboardMarkup().add(
                  InlineKeyboardButton("❌ Batal", callback_data="chg:start")))


'''

j = src.find("def chg_cb(")
assert j != -1, "chg_cb tidak ketemu"
src = src[:j] + HANDLER + src[j:]

# ---------------------------------------------------------------------------
# 5. tangani input password/pin/kode (sebelum blok chg_phone)
# ---------------------------------------------------------------------------
ANCHOR = '''    # ------------------------------------------------------------------
    # 2) NOMOR BARU → cek fresh / bisa unbind
    # ------------------------------------------------------------------
    if step == "chg_phone":'''

INSERT = '''    # ------------------------------------------------------------------
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
                      f"❌ <b>Verifikasi gagal</b>\\n\\n"
                      f"Metode: <b>{esc(str(t))}</b>\\n"
                      f"Error: <code>{esc(str(ver.get('error')))}</code>\\n\\n"
                      f"💡 Password/PIN salah. Pilih metode lagi:",
                      kb)
            return True

        tv = cnivs.token_verify(cs["cookie"], ut, vt,
                                ver.get("rc_token") or "", t)
        if not tv.get("ok"):
            NET_TMP.pop(uid, None)
            _chg_edit(msg,
                      f"❌ <b>Token IVS gagal</b>\\n\\n"
                      f"Error: <code>{esc(str(tv.get('error')))}</code>",
                      InlineKeyboardMarkup().add(
                          InlineKeyboardButton("🔁 Ulang",
                                               callback_data="chg:start")))
            return True

        cs["ivs_signature"] = tv.get("ivs_signature") or ""
        cs["ivs_method_str"] = str(t)
        NET_TMP[uid] = {"step": "chg_phone", "chg": cs, "msg": msg}
        _chg_edit(msg,
                  f"✅ <b>IVS terverifikasi</b>\\n\\n"
                  f"👤 <code>{esc(cs.get('username') or '')}</code>\\n"
                  f"📞 Nomor lama: <code>{esc(str(cs.get('old_phone')))}</code>\\n"
                  f"🔐 Metode: <b>{esc(str(t))}</b>\\n"
                  f"🟢 Siap ganti nomor\\n\\n"
                  f"Kirim <b>nomor baru</b> "
                  f"(<code>08xxx</code> / <code>628xxx</code>):",
                  CHG_BACK)
        log.info("CHG ivs ok uid=%s method=%s sig=%sB", uid, t,
                 len(cs["ivs_signature"]))
        return True

''' + ANCHOR

assert ANCHOR in src, "anchor chg_phone tidak ketemu"
src = src.replace(ANCHOR, INSERT, 1)

io.open(P, "w", encoding="utf-8").write(src)
print("PATCH SELESAI:", P)
