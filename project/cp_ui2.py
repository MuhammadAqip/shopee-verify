"""cp_ui2.py — klik bahasa DULU, baru captcha, baru flow.

Kesalahan sebelumnya: modal "Pilih bahasa Anda" menutupi halaman,
sehingga captcha tidak render dan solver ambil tombol yang salah.

Urutan benar:
  1. Buka settings
  2. Kalau ada modal bahasa -> klik "Bahasa Indonesia"
  3. Tunggu captcha render -> solve dengan key
  4. Settings render -> klik Nomor HP
  5. Ikuti UI sampai OTP
"""
import json, sys, time

sys.path.insert(0, "/root/shopee-farm")

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1553.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283191104601"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
OUT = "/root/shopee-verify/cp_ui2.json"


def log(*a):
    print(*a, flush=True)


ck = open(CK).read().strip()
cookies = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p
           for k, v in [p.strip().split("=", 1)]]

try:
    import shopee_v6 as V6
    KEY = open("/root/shopee-farm/bot_key.txt").read().strip()
    SOLVER = True
except Exception:
    SOLVER = False
    KEY = ""

from playwright.sync_api import sync_playwright

net = []


def onresp(r):
    u = r.url
    if "/api/v4/" in u and any(k in u for k in
                               ("ivs", "change_phone", "otp", "captcha", "verify")):
        try:
            b = r.text()[:1200]
        except Exception:
            b = ""
        net.append({"u": u.split("shopee.co.id")[-1][:90], "s": r.status, "b": b})


def pick_language(pg):
    """Klik modal bahasa kalau muncul."""
    for sel in ('text=Bahasa Indonesia', 'button:has-text("Bahasa Indonesia")',
                'text=English'):
        try:
            loc = pg.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click(timeout=4000, force=True)
                log(f"  ✅ klik bahasa: {sel}")
                pg.wait_for_timeout(4000)
                return True
        except Exception:
            pass
    return False


with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,1000",
        "--disable-blink-features=AutomationControlled",
        "--use-gl=swiftshader", "--lang=id-ID"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 1000},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    ctx.add_cookies(cookies)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};"
        "Object.defineProperty(navigator,'languages',{get:()=>['id-ID','id','en']});")
    pg = ctx.new_page()
    pg.on("response", onresp)

    log("=== 1. buka settings ===")
    for attempt in range(1, 10):
        try:
            pg.goto("https://shopee.co.id/user/account/settings",
                    wait_until="domcontentloaded", timeout=70000)
        except Exception as e:
            log(f"  try{attempt} err: {str(e)[:50]}")
            time.sleep(4)
            continue
        pg.wait_for_timeout(6000)

        # KLIK BAHASA DULU
        pick_language(pg)

        cur = pg.url
        body = pg.evaluate("()=>document.body.innerText.slice(0,200)")
        log(f"  [{attempt}] {cur.split('shopee.co.id')[-1][:60]} | {body[:90].replace(chr(10),'|')}")

        if "/user/account/settings" in cur and len(body.strip()) > 80:
            log("  ✅ SETTINGS RENDER!")
            break

        if "/verify/captcha" in cur:
            # pastikan modal bahasa sudah hilang
            pick_language(pg)
            pg.wait_for_timeout(2000)
            # cek apakah canvas captcha ada
            has_canvas = pg.evaluate(
                "()=>!!document.querySelector('#NEW_CAPTCHA canvas, aside canvas')")
            log(f"  captcha page, canvas={has_canvas}")
            if has_canvas and SOLVER:
                log("  solve...")
                try:
                    r = V6.solve_image_crawl(pg, KEY)
                    log(f"  result: {r}")
                except Exception as e:
                    log(f"  err: {str(e)[:80]}")
                pg.wait_for_timeout(7000)
            elif not has_canvas:
                log("  canvas belum render — tunggu")
                pg.wait_for_timeout(5000)
            continue

        pg.wait_for_timeout(4000)

    pg.screenshot(path="/root/shopee-verify/ui2_settings.png", full_page=False)
    body = pg.evaluate("()=>document.body.innerText.slice(0,600)")
    log(f"\n  body: {body[:350].replace(chr(10),' | ')}")

    # === 2. cari Nomor HP ===
    log("\n=== 2. cari Nomor HP ===")
    if "/user/account/settings" in pg.url:
        els = pg.evaluate("""()=>Array.from(document.querySelectorAll('a,button,div,span'))
          .map(e=>({t:(e.innerText||'').trim().slice(0,40),h:e.getAttribute('href')||''}))
          .filter(x=>x.t&&x.t.length<50).slice(0,80)""")
        hits = [e for e in els if any(k in e["t"].lower()
                                      for k in ("nomor", "phone", "hp", "ubah"))]
        for e in hits[:10]:
            log(f"  ★ {e['t']!r} -> {e['h'][:40]}")

        for sel in ('text=Nomor HP', 'text=Nomor Telepon',
                    'a[href*="phone"]', 'text=Ubah'):
            try:
                loc = pg.locator(sel)
                if loc.count() > 0:
                    loc.first.click(timeout=5000, force=True)
                    log(f"  klik {sel!r}")
                    pg.wait_for_timeout(8000)
                    break
            except Exception:
                pass

    log(f"\n  url akhir: {pg.url[:90]}")
    pg.screenshot(path="/root/shopee-verify/ui2_after.png", full_page=True)
    body2 = pg.evaluate("()=>document.body.innerText.slice(0,800)")
    log(f"  body: {body2[:380].replace(chr(10),' | ')}")

    # === 3. cari signature ===
    sig = None
    for n in net:
        if "token/verify" in n["u"] and '"signature"' in n["b"]:
            try:
                j = json.loads(n["b"])
                sig = (j.get("data") or {}).get("signature")
            except Exception:
                pass
    log(f"\n=== network {len(net)} rec, signature={'✅' if sig else '❌'} ===")
    for n in net[-12:]:
        log(f"  {n['s']} {n['u']}")

    json.dump({"url": pg.url, "net": net, "sig": sig,
               "body": body2[:1500]}, open(OUT, "w"), indent=1)
    log(f"-> {OUT}")
    br.close()

log("\n=== SELESAI ===")
