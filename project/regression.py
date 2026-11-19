# -*- coding: utf-8 -*-
"""regression.py — uji menyeluruh sebelum launch.

Cakupan:
  1. Syntax & import
  2. Handler terdaftar
  3. Audit callback & cabang
  4. Modul HTTP (helper, account, health, number, error format)
  5. Panel admin kredit (CRUD + log + clamp)
  6. State machine Change Number (cookie -> phone -> chan -> otp)
  7. Infrastruktur (service, port, relay IP)
  8. Log bersih (tidak ada traceback baru)
"""
import io
import json
import os
import re
import subprocess
import sys
import time

os.environ.setdefault("SHOPEE_BOT_TOKEN", "0:test")
BASE = "/root/shopee-verify"
sys.path.insert(0, BASE)

PASS = []
FAIL = []


def t(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  ✅ {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL.append(name)
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


print("=" * 66)
print("REGRESSION — 8 BLOK PENGUJIAN")
print("=" * 66)

# ------------------------------------------------------------------ 1 syntax
print("\n[1] SYNTAX & IMPORT")
for fn in ("shopee_bot.py", "changenumfast.py"):
    p = os.path.join(BASE, fn)
    r = subprocess.run([sys.executable, "-c",
                        f"import ast;ast.parse(open({p!r}).read())"],
                       capture_output=True)
    t(f"{fn} syntax", r.returncode == 0, r.stderr.decode()[:60])

import shopee_bot as B
import changenumfast as cn
t("import shopee_bot", True)
t("import changenumfast", True)

# ------------------------------------------------------------------ 2 handler
print("\n[2] HANDLER TERDAFTAR")
cb = [getattr(h.get("function"), "__name__", "?")
      for h in B.bot.callback_query_handlers]
msg = [getattr(h.get("function"), "__name__", "?")
       for h in B.bot.message_handlers]
for n in ("on_main_menu", "on_admin", "on_adc", "on_chg", "on_otp", "on_buy"):
    t(f"cb {n}", n in cb)
for n in ("chg_early_router", "adc_router", "auto_detect_phone",
          "on_admin_input"):
    t(f"msg {n}", n in msg)
t("chg_early_router sebelum auto_detect",
  msg.index("chg_early_router") < msg.index("auto_detect_phone"),
  f"{msg.index('chg_early_router')} < {msg.index('auto_detect_phone')}")

# ------------------------------------------------------------------ 3 audit
print("\n[3] AUDIT CALLBACK & CABANG")
for script, key in (("audit_callbacks.py", "PUNYA HANDLER"),
                    ("audit_branches2.py", "TOMBOL OK")):
    r = subprocess.run([sys.executable, os.path.join(BASE, script)],
                       capture_output=True, cwd=BASE,
                       env={**os.environ})
    out = r.stdout.decode()
    t(script.replace(".py", ""), r.returncode == 0 and key in out,
      out.strip().splitlines()[-1][:60] if out.strip() else "no output")

# ------------------------------------------------------------------ 4 http
print("\n[4] MODUL HTTP")
ck = open(os.path.join(BASE, "test_ck.txt")).read().strip()
t("is_cookie", cn.is_cookie(ck))
t("is_cookie negatif", not cn.is_cookie("halo"))
t("norm_phone 08", cn.norm_phone("08123456789") == "628123456789")
t("norm_phone +62", cn.norm_phone("+628123456789") == "628123456789")
t("norm_phone invalid", cn.norm_phone("xx") is None)

acc = cn.check_account(ck)
t("check_account", acc.get("ok"), f"{acc.get('username')}")
t("account punya phone", bool(acc.get("phone")))

h = cn.account_health(ck)
t("account_health", h.get("state") in ("ok", "limited", "dead"), h.get("state"))
t("health punya blocked list", isinstance(h.get("blocked"), list))

num = cn.check_number(ck, "6282374455953")
t("check_number return dict", isinstance(num, dict))
t("check_number ada ok", "ok" in num)
if not num.get("ok"):
    t("error punya code", num.get("code") is not None, str(num.get("code")))
    t("error punya hint", bool(num.get("hint")))
else:
    t("number punya cp", len(num.get("cp") or "") > 200)
    t("number punya channels", len(num.get("channels") or []) > 0)

t("HINTS 90309999", 90309999 in cn.HINTS)
t("HINTS 23500158", 23500158 in cn.HINTS)
t("err_obj", cn.err_obj(123).get("code") == 123)

# ------------------------------------------------------------------ 5 kredit
print("\n[5] PANEL KREDIT")
ADM = 7341376283
b4 = B.get_user(ADM).get("saldo", 0)
_, after = B._cred_add(ADM, 30, ADM)
t("tambah kredit", after == b4 + 30, f"{b4}->{after}")
_, back = B._cred_add(ADM, -30, ADM)
t("kurangi kredit", back == b4, f"{after}->{back}")
_, zero = B._cred_add(ADM, -(b4 + 500), ADM)
t("clamp >= 0", zero == 0)
if b4:
    B._cred_add(ADM, b4, ADM)

rows, total = B._cred_users()
t("_cred_users list", isinstance(rows, list), f"total={total}")
t("_cred_txt ada saldo", "Saldo" in B._cred_txt(ADM))
kb, _, _ = B._cred_kb_users()
t("_cred_kb ada tombol", bool(kb.inline_keyboard))
db = B._load_db()
t("credit_log tercatat", len(db.get("credit_log") or []) > 0)

# ------------------------------------------------------------------ 6 state
print("\n[6] STATE MACHINE CHANGE NUMBER")
src = io.open(os.path.join(BASE, "shopee_bot.py"), encoding="utf-8").read()
for st in ("chg_cookie", "chg_phone", "chg_chan", "chg_otp", "chg_wait"):
    t(f"step {st}", f'"{st}"' in src or f"'{st}'" in src)
t("_chg_edit ada", "def _chg_edit" in src)
t("_chg_chan_kb ada", "def _chg_chan_kb" in src)
t("HEALTH_WIRE aktif", "HEALTH_WIRE_V1" in src)
t("tombol channel dinamis", 'callback_data=f"chg:ch:' in src)

# ------------------------------------------------------------------ 7 infra
print("\n[7] INFRASTRUKTUR")
for svc in ("shopee-bot", "socks-relay", "mitm-chain"):
    r = subprocess.run(["systemctl", "is-active", svc], capture_output=True)
    t(f"service {svc}", r.stdout.decode().strip() == "active",
      r.stdout.decode().strip())

r = subprocess.run(["ss", "-ltn"], capture_output=True)
ports = r.stdout.decode()
t("port 8080", ":8080" in ports)
t("port 18080", ":18080" in ports)

r = subprocess.run(["curl", "-s", "--max-time", "25", "-x",
                    "http://127.0.0.1:18080", "https://api.ipify.org"],
                   capture_output=True)
ip = r.stdout.decode().strip()
t("relay keluar IP", bool(re.match(r"^\d+\.\d+\.\d+\.\d+$", ip)), ip)

# ------------------------------------------------------------------ 8 log
print("\n[8] LOG BERSIH")
r = subprocess.run(["tail", "-n", "400", "/var/log/shopee-bot.log"],
                   capture_output=True)
tail = r.stdout.decode()
t("tidak ada Traceback", "Traceback (most recent call last)" not in tail)
t("tidak ada 409 Conflict", "409: Conflict" not in tail)
t("tidak ada NameError", "NameError" not in tail)
t("tidak ada ImportError", "ImportError" not in tail)

# ------------------------------------------------------------------ hasil
print("\n" + "=" * 66)
print(f"LULUS: {len(PASS)}   GAGAL: {len(FAIL)}")
if FAIL:
    print("\nYANG GAGAL:")
    for f in FAIL:
        print(f"  - {f}")
    sys.exit(1)
print("SEMUA BLOK BERSIH ✅")
sys.exit(0)
