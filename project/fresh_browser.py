# -*- coding: utf-8 -*-
"""fresh_browser.py — FRESH CONTEXT MURNI.

Bedanya dengan semua percobaan sebelumnya:
  * context Playwright BARU, bukan reuse
  * TIDAK ada init_script fingerprint palsu (itu justru bikin anomali)
  * TIDAK ada cookie device (_sapid, SPC_F, SPC_SI, sense, _ga, dll)
  * HANYA cookie auth (csrftoken, SPC_U, SPC_ST, SPC_T_ID)
  * Buka homepage dulu -> Shopee generate _sapid/SPC_F/sense BARU
  * Baru masuk /cart -> lihat apakah 90309999 hilang
"""
import sys, json, ssl, urllib.request, urllib.error, urllib.parse

SRC = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_5th_solved.txt"
PW = sys.argv[2] if len(sys.argv) > 2 else "qwertyui123"
NEWPHONE = sys.argv[3] if len(sys.argv) > 3 else "6283191106499"

RAW = open(SRC).read().strip()
PAIRS = []
for p in RAW.split(";"):
    p = p.strip()
    if "=" not in p: continue
    k, v = p.split("=", 1)
    PAIRS.append((k.strip(), v.strip()))

KEEP = {"csrftoken", "SPC_U", "SPC_ST", "SPC_R_T_ID", "SPC_R_T_IV",
        "SPC_T_ID", "SPC_T_IV", "SPC_CLIENTID", "REC_T_ID"}
auth = {k: v for k, v in PAIRS if k in KEEP}
print(f"cookie auth: {len(auth)} -> " + ", ".join(auth))

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"

cookies = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
           for k, v in auth.items()]

GATE = []

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    # BROWSER BARU — tanpa argumen stealth apa pun
    br = pw.chromium.launch(headless=False, args=[
        "--no-sandbox", "--disable-dev-shm-usage",
        "--window-size=1366,768"])
    # CONTEXT BARU — tanpa init_script, tanpa header ekstra
    ctx = br.new_context(
        user_agent=UA,
        locale="id-ID",
        viewport={"width": 1366, "height": 768},
        timezone_id="Asia/Jakarta",
        proxy={"server": PROXY},
    )
    ctx.add_cookies(cookies)
    pg = ctx.new_page()

    def on_response(r):
        if "/api/v4" in r.url:
            try:
                t = r.text()
            except Exception:
                return
            if "90309999" in t:
                GATE.append((r.url.split("shopee.co.id")[-1][:50], t[:200]))

    pg.on("response", on_response)

    print("\n=== 1. homepage (Shopee generate device baru) ===")
    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(9000)
    print("   url:", pg.url[:70])
    cks = {c["name"]: c["value"] for c in ctx.cookies()}
    print("   cookie sekarang:", len(cks))
    for k in ("_sapid", "SPC_F", "SPC_SI", "sense_sa_r"):
        print(f"      {k} = {str(cks.get(k))[:45]}")
    print("   90309999 terdeteksi:", len(GATE))

    print("\n=== 2. /cart (uji gate) ===")
    pg.goto("https://shopee.co.id/cart", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(8000)
    print("   url:", pg.url[:90])
    print("   body:", pg.evaluate("()=>document.body.innerText.slice(0,150)").replace("\n", " | ")[:140])
    print("   90309999 total:", len(GATE))
    for u, t in GATE[:3]:
        print(f"      {u} -> {t[:120]}")

    # simpan cookie sesi baru
    cks2 = {c["name"]: c["value"] for c in ctx.cookies()}
    open("/root/shopee-verify/ck_freshbrowser.txt", "w").write(
        "; ".join(f"{k}={v}" for k, v in cks2.items()))
    print(f"\n   cookie baru disimpan: {len(cks2)} -> ck_freshbrowser.txt")

    pg.screenshot(path="/root/shopee-verify/freshbrowser.png", full_page=True)
    br.close()

print("\n=== 3. cek status dari Python (cookie browser baru) ===")
CK = open("/root/shopee-verify/ck_freshbrowser.txt").read().strip()
CSRF = next((c.split("=", 1)[1] for c in CK.split(";")
             if c.strip().startswith("csrftoken=")), "")
_ct = ssl.create_default_context(); _ct.check_hostname = False
_ct.verify_mode = ssl.CERT_NONE
_OP = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}),
    urllib.request.HTTPSHandler(context=_ct))


def api(path, body=None, method="POST", ref="https://shopee.co.id/cart"):
    h = {"User-Agent": UA, "Cookie": CK, "Accept": "application/json",
         "x-api-source": "pc", "x-requested-with": "XMLHttpRequest",
         "x-shopee-language": "id", "Referer": ref, "x-csrftoken": CSRF}
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


print("   cart/mini:", api("/api/v4/cart/mini", {"version_list": [3145728, 65]}).get("error"))
a = api("/api/v4/account/basic/get_account_info", None, "GET")
D = a.get("data") or {}
print(f"   account={a.get('error')} uid={D.get('userid')} user={D.get('username')}")
