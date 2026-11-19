# -*- coding: utf-8 -*-
"""headed_sig.py — HEADED browser via xvfb + stealth, ambil ivs_signature.

Perbaikan sesuai skill shopee-antifraud-reversing:
  - headless=False (xvfb)  -> lolos /verify/traffic
  - TANPA --disable-web-security (bunuh SAP SDK)
  - proxy residensial ID (:18080 relay)
  - page-context fetch supaya SDK auto-sign
"""
import sys, json
sys.path.insert(0, "/root/shopee-verify")
from full_flow import Flow
from playwright.sync_api import sync_playwright

COOKIE = open("/root/shopee-verify/ck_1553.txt").read().strip()
CSRF = "3929567fdad6e3608eb25fd137f69955"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
OUT = "/root/shopee-verify/ivs_ready_1553.json"
PHONE = "6285736070693"

# token dari Python (sudah terbukti)
f = Flow(cookie=COOKIE)
f.csrf = CSRF
assert f.step1_init()["ok"], "init gagal"
u_token = f.u_token
st, r = f.post("/api/v4/anti_fraud/ivs/methods",
               {"event": 2, "u_token": u_token},
               ref="https://shopee.co.id/verify/ivs")
methods = r.get("data") or []
print("methods:", [(m["type"], len(m["v_token"])) for m in methods])
assert methods, f"methods gagal: {r}"

assert f.step4_password("qwertyui123")["ok"], "password gagal"
r_token = f.r_token
print("r_token:", len(r_token))

cookies = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
           for k, _, v in (p.strip().partition("=") for p in COOKIE.split(";"))
           if k and v]

# JS: fetch dari konteks halaman -> SDK tanda tangan otomatis
JS = """async (a) => {
  const post = async (path, body) => {
    const r = await fetch(path, {method:'POST', credentials:'include',
      headers:{'Content-Type':'application/json','Accept':'application/json',
        'x-api-source':'pc','x-requested-with':'XMLHttpRequest'},
      body: JSON.stringify(body)});
    const t = await r.text();
    try { return JSON.parse(t); } catch(e) { return {raw:t.slice(0,400), http:r.status}; }
  };
  const out = {};
  out.verify = await post('/api/v4/anti_fraud/ivs/token/verify', a.body);
  return out;
}"""

with sync_playwright() as pw:
    br = pw.chromium.launch(
        headless=False,                       # HEADED via xvfb
        args=["--no-sandbox", "--disable-dev-shm-usage",
              "--disable-blink-features=AutomationControlled",
              "--use-gl=swiftshader",
              "--window-size=1366,768"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 768},
                         timezone_id="Asia/Jakarta",
                         proxy={"server": "http://127.0.0.1:18080"})
    ctx.add_cookies(cookies)
    ctx.add_init_script("""
      Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
      Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
      Object.defineProperty(navigator,'languages',{get:()=>['id-ID','id','en-US','en']});
      window.chrome={runtime:{}};
    """)
    pg = ctx.new_page()

    print("\n>> warm-up homepage (headed)")
    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(9000)
    print("   URL:", pg.url[:80])

    me = pg.evaluate("""async()=>{const r=await fetch('/api/v4/account/basic/get_account_info',
        {credentials:'include',headers:{'x-api-source':'pc','x-requested-with':'XMLHttpRequest'}});
        return await r.text();}""")
    print("   account:", me[:120])

    print("\n>> ke /verify/ivs (headed)")
    pg.goto("https://shopee.co.id/verify/ivs", wait_until="domcontentloaded",
            timeout=90000)
    pg.wait_for_timeout(10000)
    print("   URL:", pg.url[:80])
    print("   TEXT:", repr(pg.inner_text("body")[:140]))

    # gerakan mouse manusiawi
    for x, y in [(400, 300), (700, 420), (900, 380), (650, 500)]:
        pg.mouse.move(x, y)
        pg.wait_for_timeout(320)

    sig_ok = None
    for m in methods:
        body = {"method_name": m["type"], "event": 2,
                "u_token": u_token, "r_token": r_token,
                "v_token": m["v_token"],
                "shopee_df": {"security_device_fingerprint": ""},
                "misc": {"seed": None, "operation": 0}}
        res = pg.evaluate(JS, {"body": body})
        v = res.get("verify") or {}
        e, sig = v.get("error"), v.get("signature")
        print(f"\n   type={m['type']}: error={e} sig={bool(sig)}")
        if e == 0 and sig:
            print("   ✅ SIGNATURE:", sig[:70], "…")
            sig_ok = {"type": m["type"], "signature": sig}
            break

    if sig_ok:
        # lanjut precheck + channels dari konteks halaman juga
        print("\n>> precheck_v2 + otp settings")
        nxt = pg.evaluate("""async (a) => {
          const post = async (p,b)=>{const r=await fetch(p,{method:'POST',credentials:'include',
            headers:{'Content-Type':'application/json','x-api-source':'pc',
              'x-requested-with':'XMLHttpRequest'},body:JSON.stringify(b)});
            const t=await r.text(); try{return JSON.parse(t);}catch(e){return {raw:t.slice(0,300)};}};
          const out={};
          out.pre = await post('/api/v4/account/management/change_phone_precheck_v2',
                               {new_phone:a.phone, change_phone_token:a.cp});
          out.otp = await post('/api/v4/otp/get_settings_v2',
                               {operation:0, phone:a.phone});
          return out;
        }""", {"phone": PHONE, "cp": f.cp_token})
        print("   precheck:", json.dumps(nxt.get("pre"), ensure_ascii=False)[:220])
        print("   channels:", json.dumps(nxt.get("otp"), ensure_ascii=False)[:220])

        json.dump({"u_token": u_token, "r_token": r_token,
                   "cp_token": f.cp_token, "v_token": m["v_token"],
                   "method": sig_ok["type"], "ivs_sig": sig_ok["signature"],
                   "phone": PHONE},
                  open(OUT, "w"), ensure_ascii=False, indent=1)
        print(f"\n✅ disimpan {OUT}")
    else:
        print("\n❌ signature belum dapat walau headed")

    br.close()
