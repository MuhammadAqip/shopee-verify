"""CART_GRAB.py — tangkap cart/mini response lengkap dari natural page load."""
import json, sys, time

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_zax.txt"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
T0 = time.time()
CART = {}


def log(*a):
    m = f"[{int(time.time()-T0):3d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/CG.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright


def onresp(r):
    if "cart/mini" not in r.url:
        return
    try:
        j = r.json()
    except Exception:
        return
    CART.update(j)
    log("=== cart/mini TERTANGKAP ===")
    log(f"  keys: {list(j.keys())}")
    for k, v in j.items():
        if k == "6" and isinstance(v, dict):
            log(f"  [6] keys={list(v.keys())}")
            for k2, v2 in v.items():
                log(f"      6[{k2}] = {str(v2)[:110]}  len={len(str(v2))}")
        elif not isinstance(v, (dict, list)):
            log(f"  [{k}] = {v}")
        else:
            log(f"  [{k}] = {str(v)[:100]}")


with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,900",
        "--disable-blink-features=AutomationControlled", "--lang=id-ID"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 900},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    ctx.add_cookies(cookies)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};")
    pg = ctx.new_page()
    pg.on("response", onresp)

    log("=== buka home ===")
    try:
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    pg.wait_for_timeout(15000)

    if not CART:
        log("belum tertangkap, buka /cart")
        try:
            pg.goto("https://shopee.co.id/cart", wait_until="domcontentloaded", timeout=50000)
        except Exception:
            pass
        pg.wait_for_timeout(12000)

    if CART:
        json.dump(CART, open("/root/shopee-verify/CART_FULL.json", "w"), indent=1)
        log("\n  → CART_FULL.json")
    else:
        log("\n  ❌ cart/mini tidak tertangkap")

    br.close()

log("\n=== SELESAI ===")
