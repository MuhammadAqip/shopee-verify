# -*- coding: utf-8 -*-
"""solve_gate_full.py — buka Shopee, DETEKSI 90309999, solve captcha
via SadCaptcha sampai sesi bersih, LALU jalankan IVS + change phone.

Kunci: setelah cart/mini balas 90309999, paksa buka /verify/captcha dan
solve. Setelah lolos, tracking_id di-refresh server dan sesi jadi trusted.
"""
import sys, json, ssl, urllib.request, urllib.error, urllib.parse, time, os

CK_FILE = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_5th_solved.txt"
PW = sys.argv[2] if len(sys.argv) > 2 else "qwertyui123"
NEWPHONE = sys.argv[3] if len(sys.argv) > 3 else "6283191106499"

CK = open(CK_FILE).read().strip()
CSRF = next((c.split("=", 1)[1] for c in CK.split(";")
             if c.strip().startswith("csrftoken=")), "")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"

sys.path.insert(0, "/root/shopee-farm")
sys.path.insert(0, "/root/shopee-verify")

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


# ---- cek sesi trusted via cart/mini ----
def session_status():
    r = api("/api/v4/cart/mini", {"version_list": [3145728, 65]})
    err = r.get("error")
    tid = ((r.get("6") or {}).get("0") if isinstance(r.get("6"), dict) else None)
    return err, tid, r


print("=== 0. status sesi ===")
err, tid, raw = session_status()
print(f"   error={err}  tid={str(tid)[:45]}")
if err == 90309999:
    print("   ⚠️  SESI BELUM TRUSTED — captcha wajib diselesaikan")
else:
    print("   ✅ sesi OK")

# ---- cari solver ----
SOLVER = None
try:
    import shopee_v6 as V6
    if hasattr(V6, "solve_image_crawl"):
        SOLVER = V6
        print("   solver: shopee_v6.solve_image_crawl")
except Exception as e:
    print("   solver load err:", str(e)[:70])

from playwright.sync_api import sync_playwright

cookies = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
           for k, _, v in (p.strip().partition("=") for p in CK.split(";"))
           if k and v]

CAPLOG = []

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

    def on_resp(r):
        if "/api/v4" in r.url:
            try: t = r.text()
            except Exception: t = ""
            if "90309999" in t:
                CAPLOG.append((r.url.split("shopee.co.id")[-1][:55], t[:180]))

    pg.on("response", on_resp)

    print("\n=== 1. buka /cart (pemicu cart/mini) ===")
    pg.goto("https://shopee.co.id/cart", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(9000)
    print("   url:", pg.url[:90])
    print("   body:", pg.evaluate("()=>document.body.innerText.slice(0,200)").replace("\n", " | ")[:180])

    trig = [c for c in CAPLOG if "90309999" in c[1]]
    print(f"   request dengan 90309999: {len(trig)}")
    for u, t in trig[:3]:
        print(f"     {u} -> {t[:120]}")

    # ---- kalau ada captcha, solve ----
    captcha_state = pg.evaluate("""()=>{
      return {
        hasCanvas: !!document.querySelector('#NEW_CAPTCHA canvas, canvas[draggable]'),
        hasMask: !!document.getElementById('captchaMask'),
        hasImg: document.querySelectorAll('img').length,
        url: location.href
      };
    }""")
    print("\n=== 2. keadaan captcha ===")
    print("  ", captcha_state)

    if not captcha_state["hasCanvas"] and "captcha" not in pg.url:
        print("\n=== 3. paksa buka /verify/captcha ===")
        pg.goto("https://shopee.co.id/verify/captcha",
                wait_until="domcontentloaded", timeout=90000)
        pg.wait_for_timeout(8000)
        print("   url:", pg.url[:90])
        st2 = pg.evaluate("""()=>({
          canvas: document.querySelectorAll('canvas').length,
          drag: document.querySelectorAll('canvas[draggable]').length,
          img: document.querySelectorAll('img').length,
          body: document.body.innerText.slice(0,140)
        })""")
        print("   ", st2)

        if st2["canvas"] > 0 and SOLVER:
            print("\n=== 4. SOLVE captcha ===")
            try:
                res = SOLVER.solve_image_crawl(pg)
                print("   solver result:", json.dumps(res, ensure_ascii=False)[:250] if res else "None")
            except Exception as e:
                print("   solver err:", str(e)[:120])
                # coba metode lain
                for fn in ("solve_puzzle", "solve_image_drag"):
                    if hasattr(SOLVER, fn):
                        try:
                            res = getattr(SOLVER, fn)(pg)
                            print(f"   {fn}:", json.dumps(res, ensure_ascii=False)[:180] if res else "None")
                            break
                        except Exception as e2:
                            print(f"   {fn} err:", str(e2)[:80])
            pg.wait_for_timeout(6000)

    print("\n=== 5. cek sesi setelah solve ===")
    pg.goto("https://shopee.co.id/user/account/profile",
            wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(6000)
    print("   url:", pg.url[:90])

    cks = ctx.cookies()
    newck = {c["name"]: c["value"] for c in cks}
    open("/root/shopee-verify/ck_after_solve.txt", "w").write(
        "; ".join(f"{k}={v}" for k, v in newck.items()))
    print("   cookie baru:", len(newck), "-> ck_after_solve.txt")

    pg.screenshot(path="/root/shopee-verify/after_solve.png", full_page=True)
    br.close()

print("\n=== 6. tes sesi via Python (cookie baru) ===")
CK = open("/root/shopee-verify/ck_after_solve.txt").read().strip()
CSRF = next((c.split("=", 1)[1] for c in CK.split(";")
             if c.strip().startswith("csrftoken=")), "")
err2, tid2, _ = session_status()
print(f"   cart/mini error={err2}")
print(f"   tid={str(tid2)[:50]}")
if err2 != 90309999:
    print("   ✅ SESI TRUSTED — lanjut IVS")
else:
    print("   ❌ masih 90309999")
