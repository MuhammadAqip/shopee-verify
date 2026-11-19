"""cp_ui4.py — KLIK "Setuju" (TOS) DULU, baru flow.

Akar masalah: modal "Simak Ketentuan Akun Shopee" menutupi halaman.
Tanpa klik "Setuju", Shopee redirect ke /verify/captcha terus,
captcha tidak render (karena modal TOS yang blokir), dan
token/verify tidak pernah jalan.

Urutan benar:
  1. Buka homepage
  2. Klik "Setuju" di modal TOS (kalau muncul)
  3. Klik bahasa (kalau muncul)
  4. Buka /user/account/settings
  5. Cari & klik Nomor HP
  6. Ikuti flow sampai OTP
"""
import json, sys, time

sys.path.insert(0, "/root/shopee-farm")

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1553.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283191104601"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
OUT = "/root/shopee-verify/cp_ui4.json"


def log(*a):
    print(*a, flush=True)


ck = open(CK).read().strip()
cookies = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p
           for k, v in [p.strip().split("=", 1)]]

try:
    import shopee_v6 as V6
    KEY = open("/root/shopee-farm/bot_key.txt").read().strip()
except Exception:
    V6 = None
    KEY = ""

from playwright.sync_api import sync_playwright

net = []


def onresp(r):
    u = r.url
    if "/api/v4/" in u and any(k in u for k in
                               ("ivs", "change_phone", "otp", "captcha",
                                "account", "tos")):
        try:
            b = r.text()[:1200]
        except Exception:
            b = ""
        net.append({"u": u.split("shopee.co.id")[-1][:90], "s": r.status, "b": b})


def handle_modals(pg):
    """Klik Setuju (TOS) + pilih bahasa. Return list aksi."""
    acts = []
    # TOS "Setuju" — oranye primary
    for sel in ('button:has-text("Setuju")', 'text=Setuju',
                'div:has-text("Simak Ketentuan Akun Shopee") >> text=Setuju'):
        try:
            loc = pg.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click(timeout=4000, force=True)
                acts.append("TOS_SETUJU")
                log("  ✅ klik Setuju (TOS)")
                pg.wait_for_timeout(4000)
                break
        except Exception:
            pass
    # bahasa
    for sel in ('text=Bahasa Indonesia', 'text=English'):
        try:
            loc = pg.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click(timeout=3000, force=True)
                acts.append("LANG")
                log("  ✅ klik Bahasa Indonesia")
                pg.wait_for_timeout(3000)
                break
        except Exception:
            pass
    return acts


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

    log("=== 1. buka homepage + handle TOS ===")
    for a in range(6):
        try:
            pg.goto("https://shopee.co.id/", wait_until="domcontentloaded",
                    timeout=60000)
        except Exception as e:
            log(f"  err {str(e)[:45]}")
            time.sleep(3)
            continue
        pg.wait_for_timeout(8000)
        acts = handle_modals(pg)
        pg.wait_for_timeout(3000)
        # handle sekali lagi (mungkin muncul bertahap)
        handle_modals(pg)
        cur = pg.url
        log(f"  [{a+1}] {cur.split('shopee.co.id')[-1][:60]} acts={acts}")
        if "captcha" not in cur and "traffic" not in cur:
            log("  ✅ homepage bersih")
            break
        pg.wait_for_timeout(4000)

    # === 2. buka settings ===
    log("\n=== 2. buka settings ===")
    for a in range(5):
        try:
            pg.goto("https://shopee.co.id/user/account/settings",
                    wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            log(f"  err {str(e)[:45]}")
            continue
        pg.wait_for_timeout(7000)
        handle_modals(pg)
        cur = pg.url
        body = pg.evaluate("()=>document.body.innerText")
        ok = "captcha" not in cur and len(body.strip()) > 150
        log(f"  [{a+1}] {cur.split('shopee.co.id')[-1][:60]} len={len(body)} ok={ok}")
        if ok:
            break
        if "captcha" in cur:
            has_canvas = pg.evaluate(
                "()=>!!document.querySelector('#NEW_CAPTCHA canvas, aside canvas')")
            log(f"    canvas={has_canvas}")
            if has_canvas and V6 and KEY:
                try:
                    r = V6.solve_image_crawl(pg, KEY)
                    log(f"    solve: {r}")
                except Exception as e:
                    log(f"    solve err {str(e)[:60]}")
                pg.wait_for_timeout(7000)
            else:
                pg.wait_for_timeout(6000)

    pg.screenshot(path="/root/shopee-verify/ui4_settings.png", full_page=True)
    body = pg.evaluate("()=>document.body.innerText.slice(0,900)")
    log(f"\n  url: {pg.url[:85]}")
    log(f"  body: {body[:400].replace(chr(10),' | ')}")

    # === 3. cari Nomor HP ===
    log("\n=== 3. cari Nomor HP ===")
    els = pg.evaluate("""()=>Array.from(document.querySelectorAll('a,button,div,span,li,tr'))
      .map(e=>({t:(e.innerText||'').trim().slice(0,45),h:e.getAttribute('href')||''}))
      .filter(x=>x.t&&x.t.length<55).slice(0,120)""")
    hits = [e for e in els if any(k in e["t"].lower()
                                  for k in ("nomor", "phone", "hp", "ubah", "ganti"))]
    for e in hits[:15]:
        log(f"  ★ {e['t']!r} -> {e['h'][:40]}")

    for sel in ('text=Nomor HP', 'text=Nomor Telepon', 'text=Ubah Nomor',
                'a[href*="phone"]', 'text=Ubah', 'text=Ganti'):
        try:
            loc = pg.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click(timeout=5000, force=True)
                log(f"  ✅ klik {sel!r}")
                pg.wait_for_timeout(8000)
                handle_modals(pg)
                break
        except Exception:
            pass

    pg.wait_for_timeout(4000)
    log(f"\n  url akhir: {pg.url[:90]}")
    body2 = pg.evaluate("()=>document.body.innerText.slice(0,900)")
    log(f"  body: {body2[:400].replace(chr(10),' | ')}")
    pg.screenshot(path="/root/shopee-verify/ui4_final.png", full_page=True)

    sig = None
    for n in net:
        if "token/verify" in n["u"] and '"signature"' in n["b"]:
            try:
                j = json.loads(n["b"])
                sig = (j.get("data") or {}).get("signature")
            except Exception:
                pass

    log(f"\n=== network {len(net)} | sig={'✅ %dB' % len(sig) if sig else '❌'} ===")
    for n in net[-12:]:
        log(f"  {n['s']} {n['u']}")
        if "ivs" in n["u"] or "change_phone" in n["u"]:
            log(f"       {n['b'][:120]}")

    json.dump({"url": pg.url, "net": net, "sig": sig,
               "body": body2[:2000], "hits": hits[:25]},
              open(OUT, "w"), indent=1)
    log(f"-> {OUT}")
    br.close()

log("\n=== SELESAI ===")
