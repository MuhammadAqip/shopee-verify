# -*- coding: utf-8 -*-
"""get_dfp.py — ambil shopee_df dari SDK di halaman live (proxy), lalu
pakai untuk ivs/token/verify dari konteks halaman.

Ini jalur yang benar: SDK menghasilkan device fingerprint ASLI, kita
tidak menebak. Semua di dalam page.evaluate -> SDK auto-sign juga.
"""
import sys, json
sys.path.insert(0, "/root/shopee-verify")
import re

CK_FILE = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_1553.txt"
CK = open(CK_FILE).read().strip()
CSRF = next((c.split("=", 1)[1] for c in CK.split(";")
             if c.strip().startswith("csrftoken=")), "")
PHONE = "6285736070693"
PW = "qwertyui123"

from playwright.sync_api import sync_playwright
from full_go import req as py_req  # noqa

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

cookies = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
           for k, _, v in (p.strip().partition("=") for p in CK.split(";"))
           if k and v]

# token dari Python lewat proxy
import full_go as G
G.CK = CK
G.CSRF = CSRF if hasattr(G, "CSRF") else CSRF
r1 = G.req("/api/v4/account/management/change_phone_init_v2", {},
           ref="https://shopee.co.id/user/account/profile")
d1 = r1.get("data") or {}
cp, ut = d1.get("change_phone_token"), d1.get("ivs_utoken")
print("init:", r1.get("error"), "u_token:", bool(ut))
r2 = G.req("/api/v4/anti_fraud/ivs/methods", {"event": 2, "u_token": ut})
ms = r2.get("data") or []
print("methods:", [(m["type"], len(m["v_token"])) for m in ms])
import hashlib
ph = hashlib.sha256(hashlib.md5(PW.encode()).hexdigest().encode()).hexdigest()
r4 = G.req("/api/v4/account/management/verify_password", {"password": ph},
           ref="https://shopee.co.id/user/account/profile")
rt = (r4.get("data") or {}).get("rc_token")
print("password:", r4.get("error"), "r_token:", bool(rt))
if not (ut and ms and rt):
    sys.exit("token gagal")

pick = next((x for x in ms if x["type"] == 2), ms[0])

JS = """async (a) => {
  const out = {dfp:null, dfp_keys:null, verify:null, err:null};
  try {
    // cari SDK dfp: coba beberapa jalur umum
    const cands = [
      () => window.__dfp__,
      () => window.ShopeeDFP,
      () => window.deviceFingerprint,
      () => (window.__SHOPEE_SDK__||{}).deviceFingerprint,
      () => (window.SAP_SDK||{}).getDeviceFingerprint,
    ];
    for (const f of cands) {
      try { const v = f(); if (v) { out.dfp = v; break; } } catch(e){}
    }
    // fallback: baca cookie fingerprint terformat
    if (!out.dfp) {
      const m = document.cookie.match(/(?:^|;\\s*)shopee_webUnique_ccd=([^;]+)/);
      if (m) out.dfp = decodeURIComponent(m[1]);
    }
    if (out.dfp && typeof out.dfp === 'object') out.dfp_keys = Object.keys(out.dfp);

    const post = async (path, body) => {
      const r = await fetch(path, {method:'POST', credentials:'include',
        headers:{'Content-Type':'application/json','Accept':'application/json',
          'x-api-source':'pc','x-requested-with':'XMLHttpRequest'},
        body: JSON.stringify(body)});
      const t = await r.text();
      try { return JSON.parse(t); } catch(e){ return {raw:t.slice(0,300)}; }
    };
    out.verify = await post('/api/v4/anti_fraud/ivs/token/verify', a.body);
    return out;
  } catch(e) { out.err = String(e); return out; }
}"""

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=False, args=[
        "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--use-gl=swiftshader", "--window-size=1366,768"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 768},
                         timezone_id="Asia/Jakarta",
                         proxy={"server": "http://127.0.0.1:18080"})
    ctx.add_cookies(cookies)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};")
    pg = ctx.new_page()
    print("\n>> buka beranda lewat proxy")
    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(10000)
    print("   URL:", pg.url[:80])

    for m in ([pick] + [x for x in ms if x is not pick]):
        body = {"method_name": m["type"], "event": 2, "u_token": ut,
                "r_token": rt, "v_token": m["v_token"],
                "shopee_df": {"security_device_fingerprint": ""},
                "misc": {"seed": None, "operation": 0}}
        res = pg.evaluate(JS, {"body": body})
        v = res.get("verify") or {}
        print(f"\n   type={m['type']}")
        print(f"     dfp: {str(res.get('dfp'))[:90]}…")
        print(f"     dfp_keys: {res.get('dfp_keys')}")
        print(f"     error={v.get('error')} sig={bool(v.get('signature'))}")
        if res.get("err"):
            print("     err:", res["err"][:100])
        if v.get("error") == 0 and v.get("signature"):
            print("     ✅ SIGNATURE:", v["signature"][:70], "…")
            json.dump({"type": m["type"], "signature": v["signature"],
                       "cp": cp, "ut": ut, "rt": rt, "v_token": m["v_token"]},
                      open("/root/shopee-verify/READY.json", "w"))
            br.close()
            sys.exit(0)
    br.close()
