# -*- coding: utf-8 -*-
"""ivs_live.py — semua di dalam browser (proxy), SDK asli.

Flow:
  Python: init_v2, ivs_methods, verify_password -> token
  Browser: token/verify via page.evaluate -> SDK bikin shopee_df + sign
  Python: precheck, otp settings (langsung, tanpa SDK)
"""
import sys, json, hashlib, urllib.request, urllib.error, ssl

CK_FILE = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_1553.txt"
CK = open(CK_FILE).read().strip()
CSRF = next((c.split("=", 1)[1] for c in CK.split(";")
             if c.strip().startswith("csrftoken=")), "")
PW = "qwertyui123"
PHONE = "6285736070693"
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
         "x-shopee-language": "id", "Referer": ref,
         "Origin": "https://shopee.co.id", "x-csrftoken": CSRF}
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


print("=== PYTHON (proxy) ===")
a = api("/api/v4/account/basic/get_account_info", None, "GET",
        ref="https://shopee.co.id/")
print("account:", a.get("error"))
if a.get("error") != 0:
    sys.exit("cookie mati")

r1 = api("/api/v4/account/management/change_phone_init_v2", {})
d1 = r1.get("data") or {}
cp, ut = d1.get("change_phone_token"), d1.get("ivs_utoken")
print("init:", r1.get("error"), "u_token:", bool(ut))

r2 = api("/api/v4/anti_fraud/ivs/methods", {"event": 2, "u_token": ut})
ms = r2.get("data") or []
print("methods:", [(m["type"], len(m["v_token"])) for m in ms])
if not (ut and ms):
    sys.exit("token gagal")

ph = hashlib.sha256(hashlib.md5(PW.encode()).hexdigest().encode()).hexdigest()
r4 = api("/api/v4/account/management/verify_password", {"password": ph})
rt = (r4.get("data") or {}).get("rc_token")
print("password:", r4.get("error"), "r_token:", bool(rt))
if not rt:
    sys.exit("password gagal")

pick = next((x for x in ms if x["type"] == 2), ms[0])

# ===== BROWSER (proxy) =====
from playwright.sync_api import sync_playwright

cookies = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
           for k, _, v in (p.strip().partition("=") for p in CK.split(";"))
           if k and v]

JS = """async (a) => {
  const post = async (path, body) => {
    const r = await fetch(path, {method:'POST', credentials:'include',
      headers:{'Content-Type':'application/json','Accept':'application/json',
        'x-api-source':'pc','x-requested-with':'XMLHttpRequest'},
      body: JSON.stringify(body)});
    const t = await r.text();
    try { return JSON.parse(t); } catch(e){ return {raw:t.slice(0,300),http:r.status}; }
  };
  const out = {};
  // minta SDK bikin dfp lewat request dummy (SDK sign otomatis semua fetch)
  out.verify = await post('/api/v4/anti_fraud/ivs/token/verify', a.body);
  return out;
}"""

sig = None
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
    print("\n=== BROWSER (proxy) ===")
    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(11000)
    print("beranda:", pg.url[:70])

    for m in ([pick] + [x for x in ms if x is not pick]):
        body = {"method_name": m["type"], "event": 2, "u_token": ut,
                "r_token": rt, "v_token": m["v_token"],
                "shopee_df": {"security_device_fingerprint": ""},
                "misc": {"seed": None, "operation": 0}}
        res = pg.evaluate(JS, {"body": body})
        v = res.get("verify") or {}
        print(f"  type={m['type']}: error={v.get('error')} sig={bool(v.get('signature'))}")
        if v.get("raw"):
            print("     raw:", v["raw"][:160])
        if v.get("error") == 0 and v.get("signature"):
            sig = v["signature"]
            print("  ✅ SIGNATURE:", sig[:70], "…")
            break
    br.close()

if not sig:
    print("\n>> token/verify gagal juga di browser")
    sys.exit(1)

json.dump({"type": pick["type"], "signature": sig, "cp": cp, "ut": ut,
           "rt": rt, "v_token": pick["v_token"]},
          open("/root/shopee-verify/READY.json", "w"))

print("\n=== PYTHON: precheck + channels ===")
r6 = api("/api/v4/account/management/change_phone_precheck_v2",
         {"new_phone": PHONE, "change_phone_token": cp})
print("precheck:", json.dumps(r6, ensure_ascii=False)[:200])
r7 = api("/api/v4/otp/get_settings_v2", {"operation": 0, "phone": PHONE})
print("channels:", json.dumps(r7, ensure_ascii=False)[:200])
