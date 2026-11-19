"""browser_flow.py — SEMUA dari browser: TOS, captcha SDK native, settings, change phone.

Strategi: JANGAN panggil API sendiri. Biarkan SDK Shopee yang:
  - generate captcha (encrypted_data + encrypted_security_data + dfp_token)
  - submit captcha (verify)
  - buka settings
  - jalanin change_phone flow
  - keluarkan ivs_signature

Kita cuma:
  1. Buka halaman
  2. Klik TOS + bahasa
  3. Kalau captcha render -> solve pakai SadCaptcha (isi jawaban ke input SDK)
  4. Pantau network: token/verify signature
  5. Klik "Nomor HP" -> isi nomor -> OTP
"""
import json, sys, time

sys.path.insert(0, "/root/shopee-farm")

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1553.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283191104601"
MAXT = int(sys.argv[3]) if len(sys.argv) > 3 else 280

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
OUT = "/root/shopee-verify/browser_flow.json"

T0 = time.time()


def log(*a):
    print(f"[{int(time.time()-T0):3d}s]", *a, flush=True)


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

try:
    import shopee_v6 as V6
    KEY = open("/root/shopee-farm/bot_key.txt").read().strip()
except Exception:
    V6 = None
    KEY = ""

from playwright.sync_api import sync_playwright

net = []
sig_box = {}


def onresp(r):
    u = r.url
    if "/api/v4/" not in u:
        return
    short = u.split("shopee.co.id")[-1].split("?")[0][:80]
    try:
        b = r.text()
    except Exception:
        b = ""
    net.append({"u": short, "s": r.status, "b": b[:1500]})
    # tangkap signature
    if "token/verify" in short and '"signature"' in b:
        try:
            j = json.loads(b)
            sg = (j.get("data") or {}).get("signature")
            if sg:
                sig_box["sig"] = sg
                log(f"🎉 SIGNATURE! {len(sg)}B")
                open("/root/shopee-verify/IVS_SIGNATURE.txt", "w").write(sg)
        except Exception:
            pass
    if any(k in short for k in ("captcha/generate", "captcha/verify",
                                "change_phone", "ivs/", "otp/")):
        log(f"  NET {r.status} {short}")
        if "captcha/generate" in short:
            log(f"      gen: {b[:160]}")


def modal(pg):
    did = False
    for sel in ('button:has-text("Setuju")', 'text=Setuju'):
        try:
            l = pg.locator(sel)
            if l.count() and l.first.is_visible():
                l.first.click(timeout=3000, force=True)
                log("  ✅ TOS Setuju")
                pg.wait_for_timeout(2500)
                did = True
                break
        except Exception:
            pass
    for sel in ('text=Bahasa Indonesia', 'text=English'):
        try:
            l = pg.locator(sel)
            if l.count() and l.first.is_visible():
                l.first.click(timeout=3000, force=True)
                log("  ✅ bahasa")
                pg.wait_for_timeout(2500)
                did = True
                break
        except Exception:
            pass
    return did


def try_captcha(pg):
    """Cek captcha render -> solve lewat SadCaptcha (SDK yang submit)."""
    has = pg.evaluate(
        "()=>!!document.querySelector('#NEW_CAPTCHA canvas, aside canvas')")
    if not has:
        return False
    log("  🧩 captcha canvas ADA — solve")
    if V6 and KEY:
        try:
            r = V6.solve_image_crawl(pg, KEY)
            log(f"  solver: {r}")
            return True
        except Exception as e:
            log(f"  solve err: {str(e)[:90]}")
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

    log("=== 1. homepage + TOS ===")
    for a in range(5):
        try:
            pg.goto("https://shopee.co.id/", wait_until="domcontentloaded",
                    timeout=60000)
        except Exception as e:
            log(f"  err {str(e)[:40]}")
            time.sleep(3)
            continue
        pg.wait_for_timeout(8000)
        modal(pg)
        pg.wait_for_timeout(2000)
        if "captcha" not in pg.url:
            log(f"  ✅ home OK")
            break
        try_captcha(pg)
        pg.wait_for_timeout(6000)

    log("\n=== 2. settings (loop sampai render / timeout) ===")
    settings_ok = False
    for a in range(8):
        if time.time() - T0 > MAXT - 60:
            log("  ⏰ waktu habis")
            break
        try:
            pg.goto("https://shopee.co.id/user/account/settings",
                    wait_until="domcontentloaded", timeout=60000)
        except Exception:
            continue
        pg.wait_for_timeout(7000)
        modal(pg)
        try_captcha(pg)
        pg.wait_for_timeout(3000)

        body = pg.evaluate("()=>document.body.innerText")
        ok = ("captcha" not in pg.url and "Verifikasi gagal" not in body
              and len(body.strip()) > 150)
        log(f"  [{a+1}] {pg.url.split('shopee.co.id')[-1][:50]} len={len(body)} ok={ok}")
        if ok:
            settings_ok = True
            break
        pg.wait_for_timeout(3000)

    pg.screenshot(path="/root/shopee-verify/bf_settings.png", full_page=True)

    if settings_ok:
        log("\n=== 3. klik Nomor HP ===")
        body = pg.evaluate("()=>document.body.innerText")
        log(f"  body: {body[:300].replace(chr(10),' | ')}")

        els = pg.evaluate("""()=>Array.from(document.querySelectorAll('a,button,div,span,li'))
          .map(e=>({t:(e.innerText||'').trim().slice(0,45),
                    h:e.getAttribute('href')||''}))
          .filter(x=>x.t&&x.t.length<55).slice(0,120)""")
        hits = [e for e in els if any(k in e["t"].lower()
                                      for k in ("nomor", "phone", "hp", "ubah"))]
        for e in hits[:12]:
            log(f"  ★ {e['t']!r} -> {e['h'][:40]}")

        for sel in ('text=Nomor HP', 'text=Nomor Telepon', 'text=Ubah Nomor',
                    'a[href*="phone"]', 'text=Ubah', 'text=Ganti'):
            try:
                l = pg.locator(sel)
                if l.count() and l.first.is_visible():
                    l.first.click(timeout=5000, force=True)
                    log(f"  ✅ klik {sel!r}")
                    pg.wait_for_timeout(9000)
                    modal(pg)
                    try_captcha(pg)
                    break
            except Exception:
                pass

        pg.wait_for_timeout(4000)
        log(f"  url: {pg.url[:85]}")
        b2 = pg.evaluate("()=>document.body.innerText.slice(0,600)")
        log(f"  body: {b2[:350].replace(chr(10),' | ')}")
        pg.screenshot(path="/root/shopee-verify/bf_phone.png", full_page=True)

        # isi nomor baru kalau ada input
        try:
            inp = pg.locator('input[type="tel"], input[name*="hone"], input[placeholder*="omor"]')
            if inp.count() > 0 and inp.first.is_visible():
                inp.first.click(force=True)
                inp.first.type(NEWPHONE, delay=50)
                log(f"  ✅ isi nomor {NEWPHONE}")
                pg.wait_for_timeout(2000)
                pg.screenshot(path="/root/shopee-verify/bf_filled.png", full_page=True)
        except Exception as e:
            log(f"  input nomor: {str(e)[:60]}")

    log(f"\n=== network {len(net)} | sig={'YES' if sig_box.get('sig') else 'NO'} ===")
    endpoints = {}
    for n in net:
        endpoints[n["u"]] = endpoints.get(n["u"], 0) + 1
    for u, c in list(endpoints.items())[:30]:
        log(f"  {c:2d}x {u}")

    json.dump({"url": pg.url, "net": net, "sig": sig_box.get("sig")},
              open(OUT, "w"), indent=1)
    log(f"-> {OUT}")
    br.close()

log("\n=== SELESAI ===")
