"""cp_ui.py — jalankan flow change phone LEWAT UI WEB ASLI di browser.

Bukan API panggilan sendiri — klik-klik UI Shopee seperti manusia:
  1. Buka /user/account/settings (solve captcha kalau kena)
  2. Klik "Nomor HP" / "Ubah"
  3. Tunggu halaman IVS render — biar SDK yang handle token/verify
  4. Tangkap SEMUA request yang browser sendiri kirim
  5. Kalau browser sampai ke step OTP, isi nomor target + submit

Output: cp_ui.json + screenshot tiap langkah
"""
import json, sys, time, re

sys.path.insert(0, "/root/shopee-farm")

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1553.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283191104601"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
OUT = "/root/shopee-verify/cp_ui.json"


def log(*a):
    print(*a, flush=True)


ck = open(CK).read().strip()
cookies = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p
           for k, v in [p.strip().split("=", 1)]]

try:
    import shopee_v6 as V6
    SOLVER = True
    KEY = open("/root/shopee-farm/bot_key.txt").read().strip()
except Exception:
    SOLVER = False
    KEY = ""

from playwright.sync_api import sync_playwright

net = []


def onresp(r):
    u = r.url
    if "/api/v4/" in u and any(k in u for k in
                               ("ivs", "change_phone", "otp", "captcha",
                                "password", "verify", "account")):
        try:
            b = r.text()[:1500]
        except Exception:
            b = ""
        net.append({"u": u.split("shopee.co.id")[-1][:100], "s": r.status, "b": b})


with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,1000",
        "--disable-blink-features=AutomationControlled",
        "--use-gl=swiftshader", "--lang=id-ID",
        "--disable-features=IsolateOrigins,site-per-process"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 1000},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    ctx.add_cookies(cookies)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};"
        "Object.defineProperty(navigator,'languages',{get:()=>['id-ID','id','en']});"
        "Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});")
    pg = ctx.new_page()
    pg.on("response", onresp)

    def shot(name):
        try:
            pg.screenshot(path=f"/root/shopee-verify/ui_{name}.png",
                          full_page=False)
        except Exception:
            pass

    # ============ 1. buka settings ============
    log("=== 1. buka /user/account/settings ===")
    for attempt in range(1, 8):
        try:
            pg.goto("https://shopee.co.id/user/account/settings",
                    wait_until="domcontentloaded", timeout=70000)
        except Exception as e:
            log(f"  try{attempt}: {str(e)[:60]}")
            time.sleep(4)
            continue
        pg.wait_for_timeout(7000)
        cur = pg.url
        log(f"  [{attempt}] {cur[:80]}")

        if "/verify/captcha" in cur:
            log("  captcha → solve")
            if SOLVER:
                try:
                    V6.solve_image_crawl(pg, KEY)
                except Exception as e:
                    log(f"    err {str(e)[:50]}")
                pg.wait_for_timeout(6000)
            continue
        if "/user/account/settings" in cur:
            body = pg.evaluate("()=>document.body.innerText.slice(0,300)")
            if len(body.strip()) > 40:
                log(f"  ✅ settings RENDER ({len(body)} char)")
                break
            log("  halaman kosong, ulang")
            pg.wait_for_timeout(6000)
            continue

    shot("settings")
    txt = pg.evaluate("()=>document.body.innerText.slice(0,900)")
    log(f"  body: {txt[:280].replace(chr(10),' | ')}")

    # ============ 2. cari & klik Nomor HP ============
    log("\n=== 2. cari elemen Nomor HP ===")
    els = pg.evaluate("""()=>Array.from(document.querySelectorAll('a,button,div[role=button],span,li'))
      .map(e=>({t:(e.innerText||'').trim().slice(0,45),
                h:e.getAttribute('href')||'',
                cls:(e.className||'').toString().slice(0,40)}))
      .filter(x=>x.t && (x.t.length<60)).slice(0,60)""")
    for e in els:
        if any(k in e["t"].lower() for k in
               ("nomor", "phone", "hp", "ubah", "edit", "change")):
            log(f"  ★ {e['t']!r} -> {e['h'][:40]}")

    clicked = False
    for sel in ('text=Nomor HP', 'text=Nomor Telepon', 'text=Nomor',
                'text=Ubah Nomor', 'text=Ubah', 'text=Change',
                'a[href*="phone"]', 'a[href*="settings"]'):
        try:
            loc = pg.locator(sel)
            if loc.count() > 0:
                loc.first.click(timeout=5000, force=True)
                log(f"  klik {sel!r}")
                clicked = True
                pg.wait_for_timeout(7000)
                break
        except Exception:
            pass

    log(f"  url: {pg.url[:85]}")
    shot("after_click")

    # ============ 3. tunggu IVS / form ============
    log("\n=== 3. tunggu halaman berikutnya ===")
    for i in range(15):
        pg.wait_for_timeout(2000)
        cur = pg.url
        body = pg.evaluate("()=>document.body.innerText.slice(0,200)")
        if "/verify/ivs" in cur:
            log(f"  ✅ IVS: {cur[:70]}")
            break
        if "captcha" in cur:
            log("  captcha di sini")
            if SOLVER:
                try:
                    V6.solve_image_crawl(pg, KEY)
                except Exception:
                    pass
            continue
    shot("ivs_page")

    # ============ 4. dump state ============
    log("\n=== 4. halaman sekarang ===")
    cur = pg.url
    body = pg.evaluate("()=>document.body.innerText.slice(0,1200)")
    log(f"  url: {cur[:90]}")
    log(f"  body: {body[:400].replace(chr(10),' | ')}")

    pg.screenshot(path="/root/shopee-verify/ui_final.png", full_page=True)

    # ============ 5. ringkas network ============
    log(f"\n=== 5. network ({len(net)}) ===")
    for n in net[-25:]:
        log(f"  {n['s']} {n['u']}")
        if "error" in n["b"] and n["b"][:80].find('"error":0') == -1:
            log(f"       {n['b'][:140]}")

    # cari signature di network
    sig = None
    for n in net:
        if "token/verify" in n["u"] and '"signature"' in n["b"]:
            try:
                j = json.loads(n["b"])
                sig = (j.get("data") or {}).get("signature")
            except Exception:
                pass
    if sig:
        log(f"\n🟢🟢 SIGNATURE DARI BROWSER: {len(sig)}B")

    json.dump({"url": cur, "net": net, "sig": sig,
               "body": body[:2000]}, open(OUT, "w"), indent=1)
    log(f"-> {OUT}")
    br.close()

log("\n=== SELESAI ===")
