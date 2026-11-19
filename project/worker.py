# -*- coding: utf-8 -*-
"""
worker.py — proses terpisah pemegang Chromium.

Playwright sync API terikat ke satu thread. Jadi engine dijalankan di proses
sendiri, komunikasi lewat stdin/stdout JSON-lines. Bot Telegram spawn proses ini
sekali dan kirim perintah via pipe.

Protocol:
  -> {"id": 1, "cmd": "check", "phone": "628xxx"}
  <- {"id": 1, "ok": true, "result": {...}}
  -> {"id": 2, "cmd": "ping"}
  <- {"id": 2, "ok": true, "uid": "15539296185"}
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from otp_flow import OTP_JS, otp_msg

BASE = Path("/root/shopee-verify")
CK_DIR = BASE / "cookies"

_state = {"pw": None, "b": None, "ctx": None, "page": None, "key": None,
          "ready": False, "net_mode": "proxy", "proxy": None, "net_err": None}


def log(msg: str):
    print(f"[worker] {msg}", file=sys.stderr, flush=True)


def cookie_files() -> list[Path]:
    out = []
    main = BASE / ".ck_new"
    if main.exists():
        out.append(main)
    if CK_DIR.exists():
        out += [p for p in sorted(CK_DIR.glob("*.txt")) if p.stat().st_size > 100]
    seen, uniq = set(), []
    for p in out:
        k = p.name
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return uniq


FILES: list[Path] = cookie_files()
IDX = {"i": 0, "used": 0}


def load_jar(path: Path) -> dict:
    jar = {}
    for seg in path.read_text().replace("\n", " ").split(";"):
        seg = seg.strip()
        if seg and "=" in seg:
            k, v = seg.split("=", 1)
            jar[k.strip()] = v
    return jar


NET_CONF = BASE / "net.json"


def load_net():
    """Baca net.json -> (mode, proxy_url). Default proxy ke relay lokal."""
    try:
        j = json.loads(NET_CONF.read_text())
        mode = (j.get("mode") or "proxy").lower()
        url = j.get("url") or "http://127.0.0.1:18080"
    except Exception:
        mode, url = "proxy", os.environ.get("SHOPEE_PROXY", "http://127.0.0.1:18080")
    _state["net_mode"] = mode
    _state["proxy"] = url if mode == "proxy" else None


def save_net(mode: str, url: str):
    NET_CONF.write_text(json.dumps({"mode": mode, "url": url}, indent=1))


def apply_net(mode: str, url: str) -> bool:
    """Ganti jaringan: relaunch Chromium tanpa/ dengan proxy."""
    mode = (mode or "direct").lower()
    if mode not in ("proxy", "direct"):
        _state["net_err"] = f"mode tidak dikenal: {mode}"
        return False
    if mode == "proxy" and not url:
        _state["net_err"] = "URL proxy kosong"
        return False
    save_net(mode, url)
    load_net()
    _state["net_err"] = None
    # paksa reboot browser agar proxy benar-benar dipakai
    try:
        if _state["page"]:
            _state["page"].close()
        if _state["ctx"]:
            _state["ctx"].close()
        if _state["b"]:
            _state["b"].close()
        if _state["pw"]:
            _state["pw"].stop()
    except Exception as e:
        log(f"cleanup saat setnet: {e}")
    _state.update({"pw": None, "b": None, "ctx": None, "page": None,
                   "key": None, "ready": False})
    try:
        boot()
        open_ctx(Path("net-switch"))
        log(f"net -> {_state['net_mode']} {_state['proxy'] or ''}")
        return True
    except Exception as e:
        # relay/proxy bisa lambat setelah Chromium restart — coba sekali lagi
        log(f"setnet percobaan 1 gagal: {e} — retry")
        try:
            if _state["ctx"]:
                _state["ctx"].close()
            _state.update({"ctx": None, "page": None, "key": None})
            time.sleep(3)
            open_ctx(Path("net-switch"))
            log(f"net -> {_state['net_mode']} {_state['proxy'] or ''} (retry ok)")
            return True
        except Exception as e2:
            _state["net_err"] = str(e2)[:200]
            log(f"setnet gagal total: {e2}")
            return False


def boot():
    if _state["ready"]:
        return True
    from playwright.sync_api import sync_playwright
    if _state["proxy"] is None and _state["net_mode"] is None:
        load_net()
    proxy_url = _state["proxy"]
    _state["pw"] = sync_playwright().start()
    kwargs = {"headless": True, "args": [
        "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--disable-gpu", "--disable-extensions",
        "--ignore-certificate-errors",
        "--disable-features=IsolateOrigins,site-per-process",
    ]}
    if proxy_url:
        kwargs["proxy"] = {"server": proxy_url}
        log(f"proxy {proxy_url}")
    else:
        log("mode DIRECT (tanpa proxy)")
    _state["b"] = _state["pw"].chromium.launch(**kwargs)
    _state["ready"] = True
    log("chromium booted")
    return True


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

CHECK_JS = r"""
async (a) => {
  // csrftoken wajib: tanpa ini Shopee balas {is_customized, action_type:2}
  // atau {error:"error_forbidden"} — bukan jawaban, dan exist:false-nya palsu.
  function readCsrf() {
    const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? m[1] : '';
  }
  let csrf = readCsrf();
  if (!csrf) {
    try {
      await fetch('https://shopee.co.id/api/v4/account/basic/get_account_info',
                  {credentials:'include'});
      csrf = readCsrf();
    } catch(e) {}
  }
  async function post(url, body) {
    const hex = Array.from(crypto.getRandomValues(new Uint8Array(8)))
                    .map(b => b.toString(16).padStart(2,'0')).join('');
    const h = {
      'Content-Type':'application/json','Accept':'application/json',
      'x-api-source':'pc','x-requested-with':'XMLHttpRequest',
      'x-shopee-language':'id','af-ac-enc-dat': hex,
    };
    if (csrf) h['x-csrftoken'] = csrf;
    try {
      const r = await fetch(url, {method:'POST', headers:h, credentials:'include',
                                  body: JSON.stringify(body)});
      const t = await r.text();
      if (!t) return {__empty:true};
      return JSON.parse(t);
    } catch(e) { return {__exc: String(e)}; }
  }
  const p = a.phone;
  // Respons valid HARUS punya error numerik 0 DAN data.exist boolean.
  // Interstitial challenge balas {is_customized, is_login, action_type, err_msg}
  // atau error !== 0 — keduanya bukan jawaban, jadi ulangi.
  const valid = r => r && !r.__empty && !r.__exc &&
      r.error === 0 && r.data && typeof r.data.exist === 'boolean';
  let ex = null, lastErr = null;
  for (let i = 0; i < 10; i++) {
    const r = await post('/api/v4/account/basic/check_phone_exist', {phone: p});
    if (valid(r)) { ex = r; break; }
    if (r && typeof r.error === 'number' && r.error !== 0) { lastErr = r; }
    await new Promise(res => setTimeout(res, 2500));
  }
  if (!ex) {
    if (lastErr) return {phone: p, exist_raw: lastErr, error: lastErr.error};
    return {phone: p, blocked: true, _reason: 'challenge'};
  }
  const res = {phone: p, exist_raw: ex};
  const d = ex.data || {};
  res.exist = d.exist;
  res.user = d.user || null;
  if (d.exist === true) {
    // endpoint PATOKAN: check_unbind_phone (error 0 = bisa, 12301115 = tidak)
    let ub = null;
    for (let i = 0; i < 6; i++) {
      const u = await post('/api/v4/account/management/check_unbind_phone', {phone: p});
      if (!u.__empty && !u.__exc && typeof u.error === 'number') { ub = u; break; }
      await new Promise(res => setTimeout(res, 2000));
    }
    res.unbind_raw = ub || {error: -999};
  }
  return res;
}
"""

CODE = {
    0: "BISA_UNBIND",
    12301115: "NOT_ALLOW_UNBIND",
    12301116: "RESTRICTED",
    12301004: "REUSE_LIMIT",
    12301029: "BANNED",
    12301031: "RECYCLED",
    12301016: "PHONE_NOT_EXIST",
    10013: "PHONE_NOT_FOUND",
    12301066: "CHANGE_ONGOING",
    12301064: "NEW_DEVICE_COOLDOWN",
    90309999: "RATE_LIMITED",
    10010: "BAD_FINGERPRINT",
    12301028: "PHONE_INVALID",
}


def verdict_of(r: dict) -> str:
    if r.get("blocked"):
        return "RATE_LIMITED"
    ex = r.get("exist")
    if ex is False:
        return "FRESH"
    if ex is not True:
        if r.get("error"):
            return f"UNKNOWN_{r.get('error')}"
        return "ERROR"
    ub = r.get("unbind_raw") or {}
    err = ub.get("error")
    if err in (None, -999):
        return "ERROR"
    return CODE.get(err, f"UNKNOWN_{err}")


def open_ctx(path: Path) -> bool:
    """Cookie login TIDAK dipakai — endpoint cek nomor bersifat publik.

    Cookie akun yang expired merusak init SFU (check_phone_exist balas
    exist:false palsu). Context bersih + proxy residensial = hasil benar.
    `path` diterima hanya demi kompatibilitas pemanggil.
    """
    if _state["ctx"]:
        try:
            _state["ctx"].close()
        except Exception:
            pass
    if _state["page"]:
        try:
            _state["page"].close()
        except Exception:
            pass
    _state["page"] = None
    _state["ctx"] = _state["b"].new_context(
        user_agent=UA, locale="id-ID",
        viewport={"width": 1366, "height": 900},
        timezone_id="Asia/Jakarta", ignore_https_errors=True)
    page = _state["ctx"].new_page()
    _state["page"] = page
    page.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=120000)
    page.wait_for_timeout(7000)
    # csrftoken wajib ada; tanpa itu check_phone_exist balas challenge
    for _ in range(10):
        try:
            got = page.evaluate(
                "() => { const m = document.cookie.match(/(?:^|;\\s*)csrftoken=([^;]+)/);"
                " return !!(m && m[1].length > 10); }")
        except Exception:
            got = False
        if got:
            break
        try:
            page.evaluate("""async () => {
                await fetch('/api/v4/account/basic/get_account_info',
                            {credentials:'include'}).then(r=>r.text());
            }""")
        except Exception:
            pass
        page.wait_for_timeout(1500)
    uid = page.evaluate("""async () => {
        try {
            const r = await fetch('/api/v4/account/basic/get_account_info',
                                  {credentials:'include'});
            const j = await r.json();
            return (j && j.data && j.data.userid) || 0;
        } catch(e) { return 0; }
    }""")
    _state["key"] = "nocookie"
    log(f"ctx ready (tanpa cookie) uid={uid}")
    return True


def ensure() -> bool:
    boot()
    if not FILES:
        return False
    if _state["page"] and _state["key"]:
        return True
    return open_ctx(FILES[IDX["i"] % len(FILES)])


def rotate() -> bool:
    if not FILES:
        return False
    IDX["i"] = (IDX["i"] + 1) % len(FILES)
    IDX["used"] = 0
    _state["key"] = None
    log(f"rotate -> {FILES[IDX['i']].name}")
    return open_ctx(FILES[IDX["i"]])


def do_check(phone: str) -> dict:
    # normalisasi: 08xx / 8xx / +62xx / 62xx -> 62xx
    d = re.sub(r"\D", "", str(phone or ""))
    if d.startswith("620"):
        d = "62" + d[3:]
    elif d.startswith("0"):
        d = "62" + d[1:]
    elif d.startswith("8"):
        d = "62" + d
    if len(d) < 11 or len(d) > 14:
        return {"phone": d or phone, "verdict": "PHONE_INVALID",
                "err": f"panjang {len(d)}"}
    phone = d

    if not ensure():
        return {"phone": phone, "verdict": "NO_COOKIE"}
    page = _state["page"]
    # jangan pernah menilai sebelum csrftoken nyata ada — tanpa itu exist:false palsu
    for _ in range(12):
        try:
            if page.evaluate(
                    "() => { const m = document.cookie.match(/(?:^|;\\s*)csrftoken=([^;]+)/);"
                    " return !!(m && m[1].length > 10); }"):
                break
        except Exception:
            pass
        page.wait_for_timeout(1500)
    else:
        return {"phone": phone, "verdict": "RATE_LIMITED",
                "err": "csrf cookie tidak pernah muncul"}

    try:
        r = page.evaluate(CHECK_JS, {"phone": phone})
    except Exception as e:
        return {"phone": phone, "verdict": "ERROR", "err": str(e)}

    # challenge interstitial bisa lolos walau retry JS sudah 10x -> buka ctx baru
    if r.get("blocked") and r.get("_reason") == "challenge":
        for attempt in range(2):
            log(f"challenge, ctx baru (percobaan {attempt+1})")
            rotate()
            page = _state["page"]
            try:
                r = page.evaluate(CHECK_JS, {"phone": phone})
            except Exception as e:
                return {"phone": phone, "verdict": "ERROR", "err": str(e)}
            if not r.get("blocked"):
                break

    if r.get("blocked") or (r.get("exist_raw") or {}).get("error") == 90309999:
        if rotate():
            try:
                r = page.evaluate(CHECK_JS, {"phone": phone})
            except Exception as e:
                return {"phone": phone, "verdict": "ERROR", "err": str(e)}
            if r.get("blocked"):
                return {"phone": phone, "verdict": "RATE_LIMITED"}
        else:
            return {"phone": phone, "verdict": "RATE_LIMITED"}

    v = verdict_of(r)
    user = r.get("user") or {}
    return {"phone": phone, "verdict": v,
            "username": user.get("username") or "",
            "exist": r.get("exist"),
            "error": (r.get("unbind_raw") or {}).get("error")}



def do_otp(phone: str, step: str, vcode: str = "",
           vcode_token: str = "") -> dict:
    """Jalankan satu langkah alur OTP di dalam halaman Shopee.

    step: send | verify | check | unbind
    """
    if not ensure():
        return {"ok": False, "error": -1, "msg": "worker tidak siap"}
    page = _state["page"]
    try:
        r = page.evaluate(OTP_JS, {"phone": phone, "step": step,
                                   "vcode": vcode,
                                   "vcode_token": vcode_token})
    except Exception as e:
        return {"ok": False, "error": -1, "msg": str(e), "step": step}

    out = {"ok": bool(r.get("ok")), "step": step,
           "error": r.get("error"), "raw": r.get("raw")}

    if step == "send":
        out["seed"] = r.get("seed") or ""
        out["need_captcha"] = bool(r.get("need_captcha"))
        # token utk verify biasanya `seed`; kirim balik ke bot
        out["vcode_token"] = out["seed"]
    elif step == "verify":
        out["vcode_token"] = r.get("token") or vcode_token
    else:
        out["data"] = r.get("data")

    if not out["ok"]:
        out["msg"] = otp_msg(out.get("error"))
    return out


def reply(obj: dict):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    load_net()
    log(f"start, cookies={len(FILES)} net={_state['net_mode']} "
        f"{_state['proxy'] or ''}")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        rid = req.get("id")
        cmd = req.get("cmd")

        try:
            if cmd == "ping":
                ok = ensure()
                reply({"id": rid, "ok": ok, "uid": _state["key"],
                       "cookies": len(FILES), "idx": IDX["i"]})
            elif cmd == "check":
                t0 = time.time()
                res = do_check(req["phone"])
                res["ms"] = int((time.time() - t0) * 1000)
                reply({"id": rid, "ok": True, "result": res})
            elif cmd == "otp":
                res = do_otp(req["phone"], req.get("step", "send"),
                             req.get("vcode", ""), req.get("vcode_token", ""))
                reply({"id": rid, "ok": True, "result": res})
            elif cmd == "reload":
                FILES.clear()
                FILES.extend(cookie_files())
                IDX["i"] = 0
                _state["key"] = None
                reply({"id": rid, "ok": True, "cookies": len(FILES)})
            elif cmd == "addcookie":
                p = CK_DIR / req.get("name", f"ck_{int(time.time())}.txt")
                p.write_text(req["content"])
                FILES.append(p)
                reply({"id": rid, "ok": True, "cookies": len(FILES)})
            elif cmd == "setnet":
                # mode: "proxy" -> pakai relay/HTTP proxy, "direct" -> tanpa proxy
                mode = (req.get("mode") or "direct").lower()
                url = req.get("url") or ""
                ok = apply_net(mode, url)
                reply({"id": rid, "ok": ok, "mode": _state["net_mode"],
                       "url": _state["proxy"], "err": _state.get("net_err")})
            elif cmd == "netinfo":
                reply({"id": rid, "ok": True, "mode": _state["net_mode"],
                       "url": _state["proxy"]})
            elif cmd == "quit":
                reply({"id": rid, "ok": True})
                break
            else:
                reply({"id": rid, "ok": False, "err": "unknown cmd"})
        except Exception as e:
            log(f"ERR {cmd}: {e}")
            reply({"id": rid, "ok": False, "err": str(e)})

    try:
        if _state["b"]:
            _state["b"].close()
        if _state["pw"]:
            _state["pw"].stop()
    except Exception:
        pass


if __name__ == "__main__":
    main()
