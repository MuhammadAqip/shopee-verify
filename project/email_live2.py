# -*- coding: utf-8 -*-
"""email_live2.py — cari halaman shopee.co.id yang TIDAK redirect,
lalu jalankan token/verify dari asal yang bersih itu.
"""
import sys, json, urllib.request, urllib.error, ssl

CK_FILE = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_1445.txt"
CK = open(CK_FILE).read().strip()
CSRF = next((c.split("=", 1)[1] for c in CK.split(";")
             if c.strip().startswith("csrftoken=")), "")
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
         "x-shopee-language": "id", "Referer": ref, "x-csrftoken": CSRF,
         "Origin": "https://shopee.co.id", "x-app-type": "undefined"}
    d = None
    if body is not None:
        h["Content-Type"] = "application/json"
        d = json.dumps(body).encode()
    r = urllib.request.Request("https://shopee.co.id" + path, data=d,
                               method=method, headers=h)
    try:
        with _OP.open(r, timeout=35) as x:
            return json.loads(x.read())
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read())
        except Exception: return {"http": e.code}
    except Exception as e:
        return {"err": str(e)[:80]}


r1 = api("/api/v4/account/management/change_phone_init_v2", {})
d1 = r1.get("data") or {}
cp, ut = d1.get("change_phone_token"), d1.get("ivs_utoken")
r2 = api("/api/v4/anti_fraud/ivs/methods", {"event": 2, "u_token": ut})
ms = r2.get("data") or []
m = ms[0]
api("/api/v4/anti_fraud/ivs/method/select",
    {"method_name": m["type"], "event": 2, "u_token": ut,
     "v_token": m["v_token"], "misc": {"operation": 0}})
print("init ok:", bool(cp), "| type:", m["type"], "len:", len(m["v_token"]))

from playwright.sync_api import sync_playwright

cookies = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
           for k, _, v in (p.strip().partition("=") for p in CK.split(";"))
           if k and v]

PAGES = ["https://shopee.co.id/",
         "https://shopee.co.id/buyer/login",
         "https://shopee.co.id/help/",
         "https://shopee.co.id/shop/1",
         "https://mall.shopee.co.id/"]

JS = r"""async (a) => {
  const post = async (p,b)=>{
    const r = await fetch(p, {method:'POST', credentials:'include',
      headers:{'Content-Type':'application/json','Accept':'application/json',
        'x-api-source':'pc','x-requested-with':'XMLHttpRequest'},
      body: JSON.stringify(b)});
    const t = await r.text();
    try { return JSON.parse(t); } catch(e){ return {raw:t.slice(0,200),http:r.status}; }
  };
  const out = {dfp:null};
  // picu SDK dengan request ringan
  try {
    await fetch('/api/v4/account/basic/get_account_info',
      {credentials:'include',headers:{'x-api-source':'pc','x-requested-with':'XMLHttpRequest'}});
    await new Promise(s=>setTimeout(s,2500));
  } catch(e){}
  const m = document.cookie.match(/(?:^|;\s*)shopee_webUnique_ccd=([^;]+)/);
  out.dfp = m ? decodeURIComponent(m[1]) : null;
  out.verify = await post('/api/v4/anti_fraud/ivs/token/verify', a.body);
  return out;
}"""

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=False, args=[
        "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--use-gl=swiftshader", "--window-size=1366,768"])
    for url in PAGES:
        ctx = br.new_context(user_agent=UA, locale="id-ID",
                             viewport={"width": 1366, "height": 768},
                             timezone_id="Asia/Jakarta",
                             proxy={"server": PROXY})
        try:
            ctx.add_cookies(cookies)
            ctx.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
                "window.chrome={runtime:{}};")
            pg = ctx.new_page()
            pg.goto(url, wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(9000)
            cur = pg.url
            gated = "/verify/" in cur
            print(f"\n[{url}]")
            print(f"   -> {cur[:80]}  gated={gated}")
            if gated:
                ctx.close()
                continue
            body = {"method_name": m["type"], "event": 2, "u_token": ut,
                    "r_token": "", "v_token": m["v_token"],
                    "shopee_df": {"security_device_fingerprint": ""},
                    "misc": {"seed": None, "operation": 0}}
            res = pg.evaluate(JS, {"body": body})
            v = res.get("verify") or {}
            print(f"   dfp: {str(res.get('dfp'))[:70]}")
            print(f"   verify: error={v.get('error')} sig={bool(v.get('signature'))}")
            if v.get("error") == 0 and v.get("signature"):
                print("   ✅ SIGNATURE:", v["signature"][:70])
                json.dump({"type": m["type"], "signature": v["signature"],
                           "cp": cp, "ut": ut, "v_token": m["v_token"], "url": url},
                          open("/root/shopee-verify/READY_EMAIL.json", "w"))
                br.close()
                sys.exit(0)
        except Exception as e:
            print(f"\n[{url}] err: {str(e)[:80]}")
        finally:
            try: ctx.close()
            except Exception: pass
    br.close()
    print("\n>> semua halaman gagal")
