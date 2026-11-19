# -*- coding: utf-8 -*-
"""mitm_flow.py — REA + MITM: tangkap SEMUA request saat UI asli Shopee
kirim OTP ke nomor baru. Ini yang mengungkap endpoint + channel WA yang benar.

Strategi: jangan nebak endpoint. Jalanin UI asli Shopee sampai layar OTP,
tiru network-nya persis.
"""
import sys, json, ssl, urllib.request, urllib.error, urllib.parse, time

CK_FILE = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_5th_solved.txt"
PW = sys.argv[2] if len(sys.argv) > 2 else "qwertyui123"
NEWPHONE = sys.argv[3] if len(sys.argv) > 3 else "6283191106499"

CK = open(CK_FILE).read().strip()
CSRF = next((c.split("=", 1)[1] for c in CK.split(";")
             if c.strip().startswith("csrftoken=")), "")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"

_ct = ssl.create_default_context(); _ct.check_hostname = False
_ct.verify_mode = ssl.CERT_NONE
_OP = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}),
    urllib.request.HTTPSHandler(context=_ct))


def api(path, body=None, method="POST",
        ref="https://shopee.co.id/user/account/profile"):
    h = {"User-Agent": UA, "Cookie": CK, "Accept": "application/json",
         "x-api-source": "pc", "x-requested-with": "XMLHttpRequest",
         "x-shopee-language": "id", "Referer": ref, "x-csrftoken": CSRF,
         "Origin": "https://shopee.co.id"}
    d = None
    if body is not None:
        h["Content-Type"] = "application/json"; d = json.dumps(body).encode()
    r = urllib.request.Request("https://shopee.co.id" + path, data=d,
                               method=method, headers=h)
    try:
        with _OP.open(r, timeout=35) as x: return json.loads(x.read())
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read())
        except Exception: return {"http": e.code}
    except Exception as e: return {"err": str(e)[:80]}


print("=== 1. init_v2 ===")
r1 = api("/api/v4/account/management/change_phone_init_v2", {})
d1 = r1.get("data") or {}
cp, ut = d1.get("change_phone_token"), d1.get("ivs_utoken")
print(f"error={r1.get('error')} cp={bool(cp)}")
if not cp: sys.exit("init gagal")

from playwright.sync_api import sync_playwright

cookies = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
           for k, _, v in (p.strip().partition("=") for p in CK.split(";"))
           if k and v]

CAP = []          # semua request /api/v4
CAP_JSON = []     # yang body-nya JSON

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=False, args=[
        "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--use-gl=swiftshader", "--window-size=1366,768"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 768},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY},
                         extra_http_headers={"Accept-Language":
                                             "id-ID,id;q=0.9,en;q=0.8"})
    ctx.add_cookies(cookies)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};")

    def on_req(req):
        if "/api/v4" in req.url:
            try: body = req.post_data or ""
            except Exception: body = ""
            CAP.append({"m": req.method, "u": req.url, "b": body[:900]})

    def on_resp(resp):
        if "/api/v4" in resp.url:
            try: t = resp.text()
            except Exception: t = ""
            CAP_JSON.append({"u": resp.url, "s": resp.status, "t": t[:700]})

    pg = ctx.new_page()
    pg.on("request", on_req)
    pg.on("response", on_resp)

    IVS_URL = ("https://shopee.co.id/verify/ivs?u_token="
               + urllib.parse.quote(ut, safe="")
               + "&event_type=2&is_initial=true&client_id=4&param_type=0"
               + "&trigger_url=" + urllib.parse.quote("/user/account/profile", safe="")
               + "&next=" + urllib.parse.quote("/user/account/profile", safe=""))

    print("\n=== 2. buka IVS ===")
    pg.goto(IVS_URL, wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(10000)
    for t in ("Bahasa Indonesia", "English"):
        try:
            loc = pg.get_by_text(t, exact=True)
            if loc.count() > 0:
                loc.first.click(timeout=5000, force=True); break
        except Exception: continue
    pg.wait_for_timeout(3000)

    print("=== 3. klik Password ===")
    pg.get_by_text("Verifikasi dengan Password", exact=True).last.click(timeout=12000)
    pg.wait_for_timeout(7000)

    print("=== 4. password + KONFIRMASI ===")
    inp = pg.locator('input[type="password"]').first
    inp.wait_for(state="visible", timeout=15000)
    inp.click(force=True)
    inp.type(PW, delay=70)
    pg.wait_for_timeout(1500)
    pg.get_by_text("KONFIRMASI", exact=True).last.click(timeout=10000, force=True)

    for _ in range(10):
        pg.wait_for_timeout(3000)
        if "/verify/" not in pg.url: break
    print("=== 5. URL setelah IVS:", pg.url[:100])

    fin = pg.evaluate("""()=>{const o={};for(let i=0;i<sessionStorage.length;i++){
      const k=sessionStorage.key(i);o[k]=sessionStorage.getItem(k);}return o;}""")
    sig = (fin.get("@shopee-ivs/signature") or "").strip().strip('"')
    print("   signature:", bool(sig), "len:", len(sig))

    # === 6. LANJUT DI UI: buka halaman keamanan -> ganti nomor ===
    print("\n=== 6. buka halaman keamanan akun ===")
    CAP.clear(); CAP_JSON.clear()
    for url in ("https://shopee.co.id/user/account/security",
                "https://shopee.co.id/user/account/settings"):
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(6000)
            print(f"   {url} -> {pg.url[:60]}")
            body = pg.evaluate("()=>document.body.innerText.slice(0,250)")
            print("   body:", body.replace("\n", " | ")[:200])
            if "om" in body.lower() or "telepon" in body.lower() or "security" in pg.url:
                break
        except Exception as e:
            print(f"   {url} err: {str(e)[:50]}")

    print("\n=== CAPTURE: request /api/v4 saat buka halaman ===")
    for c in CAP[:20]:
        print(f"   {c['m']} {c['u'].split('shopee.co.id')[-1][:70]}")
        if c["b"]:
            print(f"      BODY: {c['b'][:200]}")

    br.close()

json.dump({"signature": sig, "cp": cp, "ut": ut, "type": 2},
          open("/root/shopee-verify/READY_MITM.json", "w"))
print("\n✅ signature disimpan READY_MITM.json")
