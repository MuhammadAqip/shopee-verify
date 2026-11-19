# -*- coding: utf-8 -*-
"""browser_api.py — SEMUA API dipanggil DARI DALAM BROWSER.

Kenapa: x-sap-sec, x-sap-ri, af-ac-enc-dat, af-ac-enc-sz-token itu
di-generate SDK di dalam halaman. Kita tidak bisa replikasi.
Jadi: buka Shopee -> page.evaluate(fetch) -> semua header otomatis benar.

Ini menyelesaikan masalah:
  * 90309999 (cart/mini)
  * 10002 (precheck)
  * signature valid
"""
import sys, json, ssl, urllib.request, urllib.error, urllib.parse, time

CK_FILE = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_5th_solved.txt"
PW = sys.argv[2] if len(sys.argv) > 2 else "qwertyui123"
NEWPHONE = sys.argv[3] if len(sys.argv) > 3 else "6283191106499"
PHONE_CC = "62"

CK = open(CK_FILE).read().strip()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"

KEEP = {"csrftoken", "SPC_U", "SPC_ST", "SPC_R_T_ID", "SPC_R_T_IV",
        "SPC_T_ID", "SPC_T_IV", "SPC_CLIENTID", "REC_T_ID"}
pairs = [(p.split("=", 1)[0].strip(), p.split("=", 1)[1].strip())
         for p in CK.split(";") if "=" in p]
auth = [(k, v) for k, v in pairs if k in KEEP]

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,768"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 768},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    ctx.add_cookies([{"name": k, "value": v, "domain": ".shopee.co.id",
                      "path": "/"} for k, v in auth])
    pg = ctx.new_page()

    print("=== 1. buka homepage (SDK init) ===")
    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(9000)
    print("  url:", pg.url[:80])

    # helper: panggil API dari dalam halaman
    JS = """
    async ([path, body, method]) => {
      const opt = {
        method: method,
        credentials: 'include',
        headers: {
          'Accept': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
          'X-Shopee-Language': 'id',
          'X-API-SOURCE': 'pc',
          'Content-Type': 'application/json'
        }
      };
      if (body !== null) opt.body = JSON.stringify(body);
      const res = await fetch(path, opt);
      let j = null;
      try { j = await res.json(); } catch(e) { j = null; }
      return {status: res.status, json: j};
    }
    """

    def call(path, body=None, method="POST"):
        try:
            r = pg.evaluate(JS, [path, body, method])
            return r
        except Exception as e:
            return {"error": str(e)[:100]}

    print("\n=== 2. tes cart/mini (indikator 90309999) ===")
    r = call("/api/v4/cart/mini", {"version_list": [3145728, 65]})
    j = r.get("json") or {}
    print(f"  status={r.get('status')} error={j.get('error')}")
    six = j.get("6")
    if isinstance(six, dict):
        print(f"  tid={str(six.get('0'))[:50]}")
    GATE_CLEAN = j.get("error") != 90309999
    print(f"  GATE CLEAN: {GATE_CLEAN}")

    print("\n=== 3. account info ===")
    r = call("/api/v4/account/basic/get_account_info", None, "GET")
    j = r.get("json") or {}
    D = j.get("data") or {}
    print(f"  status={r.get('status')} error={j.get('error')} "
          f"uid={D.get('userid')} user={D.get('username')} phone={repr(D.get('phone'))}")

    print("\n=== 4. change_phone_init_v2 ===")
    r = call("/api/v4/account/management/change_phone_init_v2", {})
    j = r.get("json") or {}
    d = j.get("data") or {}
    cp, ut = d.get("change_phone_token"), d.get("ivs_utoken")
    print(f"  status={r.get('status')} error={j.get('error')} cp={bool(cp)} ut={bool(ut)}")

    if cp and ut:
        print("\n=== 5. ivs/methods ===")
        r = call("/api/v4/anti_fraud/ivs/methods", {"event": 2, "u_token": ut})
        j = r.get("json") or {}
        ms = j.get("data") or []
        print(f"  error={j.get('error')} methods={[(m.get('type'), len(m.get('v_token',''))) for m in ms if isinstance(m, dict)]}")

        types = [m.get("type") for m in ms if isinstance(m, dict)]
        pick = 2 if 2 in types else (10 if 10 in types else (types[0] if types else None))
        vt = next((m.get("v_token") for m in ms if isinstance(m, dict) and m.get("type") == pick), None)

        if pick and vt:
            print(f"\n=== 6. method/select type={pick} ===")
            r = call("/api/v4/anti_fraud/ivs/method/select",
                     {"method_name": pick, "event": 2, "u_token": ut,
                      "v_token": vt, "misc": {"operation": 0}})
            print(f"  error={(r.get('json') or {}).get('error')}")

            if pick in (2, 10):
                # password / PIN -> butuh verify_password
                pw_field = "password" if pick == 2 else "pin"
                print(f"\n=== 7. verify_password ({pw_field}) ===")
                import hashlib
                ph = hashlib.sha256(hashlib.md5(PW.encode()).hexdigest().encode()).hexdigest()
                r = call("/api/v4/account/management/verify_password", {pw_field: ph})
                j = r.get("json") or {}
                rc = (j.get("data") or {}).get("rc_token")
                print(f"  error={j.get('error')} rc={bool(rc)}")

            print("\n=== 8. ivs/token/verify ===")
            BODY = {
                "method_name": pick, "event": 2,
                "u_token": ut, "v_token": vt,
                "r_token": "",
                "shopee_df": {"security_device_fingerprint": ""},
                "misc": {"seed": None, "operation": 0}
            }
            r = call("/api/v4/anti_fraud/ivs/token/verify", BODY)
            j = r.get("json") or {}
            sig = j.get("signature")
            print(f"  error={j.get('error')} signature={bool(sig)} len={len(sig or '')}")

            if sig:
                json.dump({"signature": sig, "cp": cp, "ut": ut, "type": pick},
                          open("/root/shopee-verify/READY_BROWSER.json", "w"))

                print("\n=== 9. precheck_v2 ===")
                for body in [
                    {"new_phone": NEWPHONE, "change_phone_token": cp,
                     "ivs_signature": sig, "ivs_method": pick},
                    {"new_phone": NEWPHONE, "change_phone_token": cp,
                     "ivs_signature": sig, "ivs_method": pick, "country_code": PHONE_CC},
                ]:
                    r = call("/api/v4/account/management/change_phone_precheck_v2", body)
                    j = r.get("json") or {}
                    print(f"  keys={list(body)[:3]} status={r.get('status')} error={j.get('error')}")
                    if j.get("error") == 0:
                        print("  ✅ PRECHECK OK!")
                        print("  data:", json.dumps(j.get("data"), ensure_ascii=False)[:200])
                        break

    # simpan cookie hasil
    cks = {c["name"]: c["value"] for c in ctx.cookies()}
    open("/root/shopee-verify/ck_browser_api.txt", "w").write(
        "; ".join(f"{k}={v}" for k, v in cks.items()))
    print(f"\n  cookie -> ck_browser_api.txt ({len(cks)})")

    pg.screenshot(path="/root/shopee-verify/browser_api.png", full_page=True)
    br.close()

print("\n=== SELESAI ===")
