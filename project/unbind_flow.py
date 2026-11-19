# -*- coding: utf-8 -*-
"""
unbind_flow.py — flow UNBIND ASLI Shopee (bukan get_unbind_phone_check_result).

Urutan dari bundle SignupByOTP (sudah diverifikasi):
  1. POST /api/v4/otp/send_vcode
       {phone, channel:1, operation:0, force_channel:false}
       -> {error:0, data:{seed, need_captcha, ...}}
  2. POST /api/v4/account/management/check_unbind_phone_by_vcode
       {phone, vcode_token, operation:0}
  3. POST /api/v4/account/management/unbind_phone_by_vcode   (aksi nyata)

Kode error kunci:
  12301115 = nomor TIDAK terdaftar / tidak bisa di-unbind oleh akun ini
  10002    = body/otp_token salah / sudah kedaluwarsa
  0        = ok
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = Path("/root/shopee-verify")
HOME = "https://shopee.co.id/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

FETCH = r"""
async (a) => {
  const csrfM = document.cookie.match(/(^| )csrftoken=([^;]+)/);
  const csrf = csrfM ? csrfM[2] : '';
  const hex = Array.from(crypto.getRandomValues(new Uint8Array(8)))
                  .map(b => b.toString(16).padStart(2,'0')).join('');
  const h = {'Content-Type':'application/json','Accept':'application/json',
    'x-api-source':'pc','x-requested-with':'XMLHttpRequest',
    'x-shopee-language':'id','af-ac-enc-dat':hex};
  if (csrf) h['x-csrftoken'] = csrf;
  try {
    const r = await fetch(a.url, {method:'POST', headers:h,
      credentials:'include', body:JSON.stringify(a.body)});
    const t = await r.text();
    let j; try { j = JSON.parse(t); } catch(e) { j = {_raw:t.slice(0,300)}; }
    return {s:r.status, j};
  } catch(e) { return {s:0, j:{_exc:String(e)}}; }
}
"""


def jar_from(p):
    jar = {}
    for seg in open(p).read().replace("\n", " ").split(";"):
        seg = seg.strip()
        if seg and "=" in seg:
            k, v = seg.split("=", 1)
            jar[k.strip()] = v
    return jar


def main():
    ck = sys.argv[1] if len(sys.argv) > 1 else str(BASE / ".ck_new")
    phones = sys.argv[2:] or ["628999888777", "6281234567890"]
    jar = jar_from(ck)

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(user_agent=UA, locale="id-ID",
                            viewport={"width": 1366, "height": 900},
                            timezone_id="Asia/Jakarta")
        page = ctx.new_page()
        try:
            ctx.add_cookies([{"name": k, "value": v, "domain": ".shopee.co.id",
                              "path": "/", "secure": True, "sameSite": "None"}
                             for k, v in jar.items()])
        except Exception:
            pass
        cdp = ctx.new_cdp_session(page)
        cdp.send("Network.enable")
        for k, v in jar.items():
            try:
                cdp.send("Network.setCookie", {"name": k, "value": v,
                                               "domain": ".shopee.co.id",
                                               "path": "/", "secure": True})
            except Exception:
                pass
        page.goto(HOME, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)
        print(f"[warm] {page.url[:65]}\n")

        def post(path, body):
            r = page.evaluate(FETCH, {"url": path, "body": body})
            return r["s"], r["j"]

        for ph in phones:
            print("=" * 72)
            print(f"PHONE {ph}")
            print("=" * 72)

            # 0. ada atau nggak
            _, ex = post("/api/v4/account/basic/check_phone_exist", {"phone": ph})
            exist = (ex.get("data") or {}).get("exist")
            print(f"  0. check_phone_exist  -> exist={exist} err={ex.get('error')}")
            if exist is False:
                print("     => FRESH, tidak perlu unbind\n")
                continue

            # 1. kirim OTP untuk keperluan unbind
            _, sv = post("/api/v4/otp/send_vcode",
                         {"phone": ph, "channel": 1, "operation": 0,
                          "force_channel": False})
            print(f"  1. send_vcode         -> {json.dumps(sv, ensure_ascii=False)[:240]}")
            seed = (sv.get("data") or {}).get("seed")
            otp_token = sv.get("data", {}).get("otp_token") or sv.get("otp_token")
            e1 = sv.get("error")

            if e1 not in (0, None):
                print(f"     ! send_vcode gagal err={e1} "
                      f"-> nomor ini tidak bisa dipakai untuk unbind\n")
                continue

            # 2. check_unbind_phone_by_vcode (tanpa otp -> lihat shape jawaban)
            _, cu = post("/api/v4/account/management/check_unbind_phone_by_vcode",
                         {"phone": ph, "vcode_token": otp_token or "",
                          "operation": 0})
            print(f"  2. check_unbind_vcode -> {json.dumps(cu, ensure_ascii=False)[:240]}")

            # 3. cek lagi apakah nomor terikat ke AKUN KITA (bukan orang lain)
            _, info = post("/api/v4/account/basic/get_account_info", {})
            my = (info.get("data") or {}).get("phone")
            print(f"  3. akun kita phone    -> {my}")
            print(f"     match = {my == ph}")
            print()

        b.close()


if __name__ == "__main__":
    main()
