# -*- coding: utf-8 -*-
"""one_flow2.py — IVS + redirect callback yang BENAR.

Perbaikan: next harus path relatif (/user/account/profile), bukan URL absolut.
Lalu setelah redirect, server mencatat IVS completion -> precheck 0.
"""
import sys, json, ssl, urllib.request, urllib.error, urllib.parse, time

CK_FILE = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_5th_solved.txt"
PW = sys.argv[2] if len(sys.argv) > 2 else "qwertyui123"
NEWPHONE = sys.argv[3] if len(sys.argv) > 3 else "6285736070693"

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
print(f"error={r1.get('error')} cp={bool(cp)} ut={bool(ut)}")
if not cp: sys.exit("init gagal")

from playwright.sync_api import sync_playwright

cookies = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
           for k, _, v in (p.strip().partition("=") for p in CK.split(";"))
           if k and v]

# next = PATH RELATIF, bukan URL absolut
URL = ("https://shopee.co.id/verify/ivs?u_token=" + urllib.parse.quote(ut, safe="")
       + "&event_type=2&is_initial=true&client_id=4&param_type=0"
       + "&trigger_url=" + urllib.parse.quote("/user/account/profile", safe="")
       + "&next=" + urllib.parse.quote("/user/account/profile", safe=""))

LOG = []
with sync_playwright() as pw:
    br = pw.chromium.launch(headless=False, args=[
        "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--use-gl=swiftshader", "--window-size=1366,768"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 768},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    ctx.add_cookies(cookies)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};")
    pg = ctx.new_page()
    pg.on("response", lambda r: LOG.append(
        (r.request.method, r.url.split("/api/v4")[-1][:48], r.status,
         (r.text()[:320] if "/api/v4" in r.url else "")))
        if "/api/v4" in r.url else None)

    print("\n=== 2. buka IVS ===")
    pg.goto(URL, wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(10000)
    for txt in ("Bahasa Indonesia", "English"):
        try:
            loc = pg.get_by_text(txt, exact=True)
            if loc.count() > 0:
                loc.first.click(timeout=5000, force=True); break
        except Exception: continue
    pg.wait_for_timeout(3500)

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

    # tunggu redirect selesai
    for _ in range(8):
        pg.wait_for_timeout(3000)
        u = pg.url
        if "/verify/ivs" not in u and "/verify/password" not in u:
            break
    print("=== 5. URL akhir:", pg.url[:110])

    fin = pg.evaluate("""()=>{const o={};for(let i=0;i<sessionStorage.length;i++){
      const k=sessionStorage.key(i);o[k]=sessionStorage.getItem(k);}return o;}""")
    sig = (fin.get("@shopee-ivs/signature") or "").strip().strip('"')
    print("   signature:", bool(sig), "len:", len(sig))
    print("   completed:", fin.get("@shopee-ivs/verification_completed_success"))

    print("\n=== API terakhir ===")
    for m, u, s, b in LOG[-8:]:
        print(f"   {m} {u} -> {s}")
        if b and ("management" in u or "ivs" in u):
            print(f"      {b[:250]}")

    br.close()

if not sig:
    sys.exit(">> signature gagal")

json.dump({"signature": sig, "cp": cp, "ut": ut, "type": 2},
          open("/root/shopee-verify/READY_FULL.json", "w"))

print("\n=== 6. precheck ===")
r5 = api("/api/v4/account/management/change_phone_precheck_v2",
         {"new_phone": NEWPHONE, "change_phone_token": cp,
          "ivs_signature": sig, "ivs_method": 2})
print(f"   error={r5.get('error')} {json.dumps(r5, ensure_ascii=False)[:200]}")

if r5.get("error") == 0:
    print("\n=== 7. otp settings ===")
    r6 = api("/api/v4/account/management/otp/get_settings_v2",
             {"operation": 0, "phone": NEWPHONE, "change_phone_token": cp})
    print(f"   error={r6.get('error')} {json.dumps(r6.get('data'), ensure_ascii=False)[:200]}")
    print("\n=== 8. send_vcode ===")
    r7 = api("/api/v4/account/management/otp/send_vcode",
             {"phone": NEWPHONE, "operation": 0, "change_phone_token": cp})
    print(f"   error={r7.get('error')} {json.dumps(r7, ensure_ascii=False)[:250]}")
