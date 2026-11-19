# -*- coding: utf-8 -*-
"""ivs_real.py — jalankan IVS flow ASLI lewat halaman /verify/ivs.

Kunci: r_token EmailLink diambil dari sessionStorage ROBOT_TOKEN
       (@shopee-ivs/r_token) yang diisi halaman /verify/ivs, BUKAN API.
"""
import sys, json, time, ssl, urllib.request, urllib.error, urllib.parse

CK_FILE = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_1445_solved.txt"
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
print("init:", r1.get("error"), "cp:", bool(cp), "ut:", bool(ut))
if not cp:
    sys.exit(1)

from playwright.sync_api import sync_playwright

cookies = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
           for k, _, v in (p.strip().partition("=") for p in CK.split(";"))
           if k and v]

# Halaman IVS: parameter yang dipakai (dari bundle: u_token, event_type,
# r_token, is_initial, trigger_url, next, state, client_id, param_type)
IVS_URL = ("https://shopee.co.id/verify/ivs"
           "?u_token=" + urllib.parse.quote(ut, safe="")
           + "&event_type=2&is_initial=true"
           "&trigger_url=" + urllib.parse.quote("https://shopee.co.id/user/account/profile", safe="")
           + "&next=" + urllib.parse.quote("https://shopee.co.id/user/account/profile", safe="")
           + "&client_id=4&param_type=0")

JS_SS = """() => {
  const o = {};
  for (let i=0;i<sessionStorage.length;i++){
    const k = sessionStorage.key(i);
    o[k] = sessionStorage.getItem(k);
  }
  return o;
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
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};")
    pg = ctx.new_page()

    # tangkap request/response ivs
    seen = []
    pg.on("request", lambda r: seen.append(("REQ", r.method, r.url[:110],
                                            (r.post_data or "")[:400]))
          if "anti_fraud/ivs" in r.url else None)
    pg.on("response", lambda r: seen.append(("RES", r.status, r.url[:110], ""))
          if "anti_fraud/ivs" in r.url else None)

    print("\n>> buka halaman IVS")
    print("   ", IVS_URL[:150])
    try:
        pg.goto(IVS_URL, wait_until="domcontentloaded", timeout=90000)
    except Exception as e:
        print("   goto err:", str(e)[:70])
    for w in range(6):
        pg.wait_for_timeout(5000)
        u = pg.url
        t = pg.evaluate("()=>document.body.innerText.slice(0,150)")
        print(f"   [{w*5}s] {u[:70]} | {t.replace(chr(10),' | ')[:80]}")

    print("   URL:", pg.url[:110])
    txt = pg.evaluate("()=>document.body.innerText.slice(0,300)")
    print("   body:", txt.replace("\n", " | ")[:280])

    ss = pg.evaluate(JS_SS)
    print("\n=== sessionStorage ===")
    for k, v in ss.items():
        print(f"   {k} = {str(v)[:90]}")

    print("\n=== request IVS ===")
    for e in seen[:14]:
        print(f"   {e[0]} {e[1]} {e[2]}")
        if e[3]:
            print(f"        body: {e[3][:200]}")

    rt = None
    for k, v in ss.items():
        if "r_token" in k:
            rt = v
    print("\n   r_token dari sessionStorage:", (rt or "")[:80] if rt else "TIDAK ADA")

    if rt:
        print("\n>> retry token/verify dengan r_token sessionStorage")
        res = pg.evaluate("""async (a)=>{
          const r = await fetch('/api/v4/anti_fraud/ivs/token/verify',
            {method:'POST',credentials:'include',
             headers:{'Content-Type':'application/json',
               'x-api-source':'pc','x-requested-with':'XMLHttpRequest'},
             body: JSON.stringify(a)});
          const t = await r.text();
          try{return JSON.parse(t);}catch(e){return {raw:t.slice(0,200)};}
        }""", {"method_name": 8, "event": 2, "u_token": ut,
               "r_token": rt, "v_token": "",
               "shopee_df": {"security_device_fingerprint": ""},
               "misc": {"seed": None, "operation": 0}})
        print("   ->", json.dumps(res, ensure_ascii=False)[:200])

    pg.screenshot(path="/root/shopee-verify/ivs_page.png")
    br.close()
