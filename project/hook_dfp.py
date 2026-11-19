# -*- coding: utf-8 -*-
"""hook_dfp.py — HOOK window.fetch di halaman live, picu request yang lewat
interceptor SDK, tangkap security_device_fingerprint yang SDK sisipkan.

Lalu pakai DFP itu untuk token/verify.
"""
import sys, json, hashlib, urllib.request, urllib.error, ssl

CK_FILE = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_1553.txt"
CK = open(CK_FILE).read().strip()
CSRF = next((c.split("=", 1)[1] for c in CK.split(";")
             if c.strip().startswith("csrftoken=")), "")
PW, PHONE = "qwertyui123", "6285736070693"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"

_ct = ssl.create_default_context()
_ct.check_hostname = False
_ct.verify_mode = ssl.CERT_NONE
_OP = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}),
    urllib.request.HTTPSHandler(context=_ct))


def api(path, body=None, method="POST",
        ref="https://shopee.co.id/user/account/profile"):
    h = {"User-Agent": UA, "Cookie": CK, "Accept": "application/json",
         "x-api-source": "pc", "x-requested-with": "XMLHttpRequest",
         "x-shopee-language": "id", "Referer": ref, "x-csrftoken": CSRF}
    data = None
    if body is not None:
        h["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    r = urllib.request.Request("https://shopee.co.id" + path, data=data,
                               method=method, headers=h)
    try:
        with _OP.open(r, timeout=35) as x:
            return json.loads(x.read())
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read())
        except Exception: return {"http": e.code}
    except Exception as e:
        return {"err": str(e)[:90]}


a = api("/api/v4/account/basic/get_account_info", None, "GET",
        ref="https://shopee.co.id/")
print("account:", a.get("error"))
r1 = api("/api/v4/account/management/change_phone_init_v2", {})
d1 = r1.get("data") or {}
cp, ut = d1.get("change_phone_token"), d1.get("ivs_utoken")
r2 = api("/api/v4/anti_fraud/ivs/methods", {"event": 2, "u_token": ut})
ms = r2.get("data") or []
ph = hashlib.sha256(hashlib.md5(PW.encode()).hexdigest().encode()).hexdigest()
r4 = api("/api/v4/account/management/verify_password", {"password": ph})
rt = (r4.get("data") or {}).get("rc_token")
print("init:", r1.get("error"), "methods:", len(ms), "password:", bool(rt))
if not (ut and ms and rt):
    sys.exit("token gagal")
pick = next((x for x in ms if x["type"] == 2), ms[0])

from playwright.sync_api import sync_playwright

cookies = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
           for k, _, v in (p.strip().partition("=") for p in CK.split(";"))
           if k and v]

HOOK = r"""
(function(){
  if (window.__DFP_HOOKED) return;
  window.__DFP_HOOKED = true;
  window.__DFP__ = null;
  const orig = window.fetch;
  window.fetch = function(input, init){
    try {
      const b = init && init.body;
      if (typeof b === 'string' && b.indexOf('security_device_fingerprint') >= 0) {
        const j = JSON.parse(b);
        const f = j.security_device_fingerprint
               || (j.shopee_df && j.shopee_df.security_device_fingerprint);
        if (f) window.__DFP__ = f;
      }
      const h = init && init.headers;
      if (h) {
        const keys = h instanceof Headers ? Array.from(h.keys()) : Object.keys(h);
        window.__HDRS__ = (window.__HDRS__ || []).concat([keys]);
      }
    } catch(e){}
    return orig.apply(this, arguments);
  };
  // hook XHR juga
  const oo = XMLHttpRequest.prototype.open,
        os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(m,u){ this.__u=u; return oo.apply(this,arguments); };
  XMLHttpRequest.prototype.send = function(b){
    try {
      if (typeof b === 'string' && b.indexOf('security_device_fingerprint') >= 0) {
        const j = JSON.parse(b);
        const f = j.security_device_fingerprint
               || (j.shopee_df && j.shopee_df.security_device_fingerprint);
        if (f) window.__DFP__ = f;
      }
    } catch(e){}
    return os.apply(this, arguments);
  };
})();
"""

# picu request yang lewat interceptor -> SDK hitung DFP
TRIGGER = r"""async () => {
  const out = {};
  try {
    const r = await fetch('/api/v4/account/basic/get_account_info',
      {credentials:'include', headers:{'x-api-source':'pc',
       'x-requested-with':'XMLHttpRequest'}});
    out.info = r.status;
    await r.text();
  } catch(e){ out.err = String(e); }
  return out;
}"""

JS_VERIFY = r"""async (a) => {
  const post = async (p,b)=>{
    const r = await fetch(p, {method:'POST', credentials:'include',
      headers:{'Content-Type':'application/json','Accept':'application/json',
        'x-api-source':'pc','x-requested-with':'XMLHttpRequest'},
      body: JSON.stringify(b)});
    const t = await r.text();
    try { return JSON.parse(t); } catch(e){ return {raw:t.slice(0,250),http:r.status}; }
  };
  return {verify: await post('/api/v4/anti_fraud/ivs/token/verify', a.body)};
}"""

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=False, args=[
        "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--use-gl=swiftshader", "--window-size=1366,768"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 768},
                         timezone_id="Asia/Jakarta",
                         proxy={"server": PROXY})
    ctx.add_cookies(cookies)
    ctx.add_init_script(HOOK)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};")
    pg = ctx.new_page()
    print("\n>> beranda (proxy)")
    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(11000)
    print("   URL:", pg.url[:60])

    print(">> picu interceptor SDK")
    trig = pg.evaluate(TRIGGER)
    print("   trigger:", trig)
    pg.wait_for_timeout(4000)
    dfp = pg.evaluate("() => window.__DFP__")
    print("   DFP tertangkap:", str(dfp)[:100] if dfp else "TIDAK ADA")

    cand = dfp or ""
    for m in ([pick] + [x for x in ms if x is not pick]):
        for lbl, dfpv in ([("hook", cand), ("cookie", None)]):
            if dfpv is None:
                dfpv = pg.evaluate(
                    "()=>{const m=document.cookie.match(/(?:^|;\\s*)shopee_webUnique_ccd=([^;]+)/);"
                    "return m?decodeURIComponent(m[1]):'';}")
            if not dfpv:
                continue
            body = {"method_name": m["type"], "event": 2, "u_token": ut,
                    "r_token": rt, "v_token": m["v_token"],
                    "shopee_df": {"security_device_fingerprint": dfpv},
                    "misc": {"seed": None, "operation": 0}}
            res = pg.evaluate(JS_VERIFY, {"body": body})
            v = res.get("verify") or {}
            print(f"   type={m['type']} dfp={lbl}: error={v.get('error')} "
                  f"sig={bool(v.get('signature'))}")
            if v.get("error") == 0 and v.get("signature"):
                print("   ✅ SIGNATURE:", v["signature"][:70], "…")
                json.dump({"type": m["type"], "signature": v["signature"],
                           "cp": cp, "ut": ut, "rt": rt,
                           "v_token": m["v_token"]},
                          open("/root/shopee-verify/READY.json", "w"))
                br.close()
                sys.exit(0)
    br.close()
    print("\n>> gagal semua")
