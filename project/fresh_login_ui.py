"""fresh_login_ui.py — login UI fresh, device token baru, lalu buka settings.

Hipotesis: tracking_id sticky karena SPC_T_ID (device token) lama.
Login ulang dari browser bersih -> SPC_T_ID baru -> tracking_id baru
-> captcha/generate terbit -> flow bisa jalan.

Akun: ck_1553 = uh4mfv6x92 / qwertyui123
"""
import json, sys, time

sys.path.insert(0, "/root/shopee-farm")

USER = sys.argv[1] if len(sys.argv) > 1 else "uh4mfv6x92"
PASS = sys.argv[2] if len(sys.argv) > 2 else "qwertyui123"
OUT = "/root/shopee-verify/fresh_login.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"


def log(*a):
    print(*a, flush=True)


try:
    import shopee_v6 as V6
    KEY = open("/root/shopee-farm/bot_key.txt").read().strip()
except Exception:
    V6 = None
    KEY = ""

from playwright.sync_api import sync_playwright

net = []


def onresp(r):
    if "/api/v4/" in r.url:
        u = r.url.split("shopee.co.id")[-1][:80]
        if any(k in u for k in ("captcha", "login", "ivs", "account", "tos")):
            try:
                b = r.text()[:900]
            except Exception:
                b = ""
            net.append({"u": u, "s": r.status, "b": b})


with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,1000",
        "--disable-blink-features=AutomationControlled",
        "--use-gl=swiftshader", "--lang=id-ID"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 1000},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    # TANPA cookie lama
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};"
        "Object.defineProperty(navigator,'languages',{get:()=>['id-ID','id','en']});")
    pg = ctx.new_page()
    pg.on("response", onresp)

    def modals():
        for sel in ('button:has-text("Setuju")', 'text=Setuju'):
            try:
                loc = pg.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    loc.first.click(timeout=3000, force=True)
                    log("  ✅ Setuju")
                    pg.wait_for_timeout(2500)
                    break
            except Exception:
                pass
        for sel in ('text=Bahasa Indonesia', 'text=English'):
            try:
                loc = pg.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    loc.first.click(timeout=3000, force=True)
                    log("  ✅ bahasa")
                    pg.wait_for_timeout(2500)
                    break
            except Exception:
                pass

    log("=== buka home (session BARU) ===")
    for a in range(6):
        try:
            pg.goto("https://shopee.co.id/", wait_until="domcontentloaded",
                    timeout=60000)
        except Exception as e:
            log(f"  err {str(e)[:40]}")
            time.sleep(3)
            continue
        pg.wait_for_timeout(8000)
        modals()
        if "captcha" not in pg.url:
            log(f"  ✅ home: {pg.url[:60]}")
            break
        if V6 and KEY:
            try:
                V6.solve_image_crawl(pg, KEY)
            except Exception:
                pass
        pg.wait_for_timeout(5000)

    # === login ===
    log("\n=== login ===")
    try:
        pg.goto("https://shopee.co.id/buyer/login", wait_until="domcontentloaded",
                timeout=60000)
    except Exception as e:
        log(f"  goto err {str(e)[:50]}")
    pg.wait_for_timeout(7000)
    modals()
    log(f"  url: {pg.url[:70]}")

    try:
        el = pg.locator('input[name="loginKey"]').first
        el.wait_for(state="visible", timeout=25000)
        el.click(force=True)
        el.type(USER, delay=45)
        pg.wait_for_timeout(600)
        el.press("Enter")
        pg.wait_for_timeout(4000)
        log("  username OK")

        pwi = pg.locator('input[type="password"]').first
        pwi.wait_for(state="visible", timeout=25000)
        pwi.click(force=True)
        pwi.type(PASS, delay=45)
        pg.wait_for_timeout(600)
        pwi.press("Enter")
        pg.wait_for_timeout(14000)
        log(f"  setelah password: {pg.url[:70]}")
    except Exception as e:
        log(f"  login err {str(e)[:100]}")

    body = pg.evaluate("()=>document.body.innerText.slice(0,400)")
    log(f"  body: {body[:250].replace(chr(10),' | ')}")

    # handle IVS kalau muncul
    if "/verify/ivs" in pg.url:
        log("\n=== IVS muncul — tunggu SDK ===")
        pg.wait_for_timeout(10000)
        mtoks = pg.evaluate("""()=>{
          const m=location.search.match(/u_token=([^&]+)/);
          return {ut: m?decodeURIComponent(m[1]).length:0,
                  url: location.pathname};
        }""")
        log(f"  {mtoks}")
        pg.wait_for_timeout(8000)

    pg.screenshot(path="/root/shopee-verify/fresh_after_login.png", full_page=True)

    # === cookie baru ===
    cks = ctx.cookies()
    names = {c["name"]: c["value"] for c in cks}
    log(f"\n=== cookie baru ({len(cks)}) ===")
    for k, v in names.items():
        log(f"  {k:18s} len={len(v)}")
    ckstr = "; ".join(f"{c['name']}={c['value']}" for c in cks)
    open("/root/shopee-verify/ck_fresh2.txt", "w").write(ckstr)
    log("  -> ck_fresh2.txt")

    # === cek tracking_id BARU ===
    tids = set()
    for n in net:
        if "captcha/get_config" in n["u"]:
            i = n["b"].find('"tracking_id":"')
            if i > 0:
                tids.add(n["b"][i+15:i+50])
    log(f"\n=== tracking_id ({len(tids)}) ===")
    for t in tids:
        log(f"  {t}...")

    # === coba settings ===
    log("\n=== coba settings dengan cookie baru ===")
    try:
        pg.goto("https://shopee.co.id/user/account/settings",
                wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(8000)
        modals()
        log(f"  url: {pg.url[:80]}")
        b2 = pg.evaluate("()=>document.body.innerText.slice(0,400)")
        log(f"  body: {b2[:280].replace(chr(10),' | ')}")
        pg.screenshot(path="/root/shopee-verify/fresh_settings.png", full_page=True)
    except Exception as e:
        log(f"  err {str(e)[:60]}")

    # captcha/generate terakhir
    gen = [n for n in net if "captcha/generate" in n["u"]]
    log(f"\n=== captcha/generate ({len(gen)}) ===")
    for g in gen[-4:]:
        log(f"  {g['b'][:180]}")

    json.dump({"net": net, "tids": list(tids), "cookies": names},
              open(OUT, "w"), indent=1)
    log(f"-> {OUT}")
    br.close()

log("\n=== SELESAI ===")
