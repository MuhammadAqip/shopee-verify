"""FINAL_change_phone.py — SATU RUN, SEMUA DARI BROWSER.

Tujuan: change_phone 6283191104601 selesai.

Kunci yang sudah ditemukan:
  - 90309999 = TRIGGER_ANTI_CRAWLER, dipicu dari endpoint commerce
  - SDK redirect ke /verify/captcha?anti_bot_tracking_id=<fresh>
  - captcha scene "crawler_item", appkey "TSS.PC"
  - SadCaptcha /puzzle -> slideXProportion
  - verify butuh encrypted_security_data + dfp_token (SDK generate)
  - user_action = {slider_start_ts, slider_end_ts, mouse_events:[[x,y,ts,type]]}

Strategi:
  1. Buka homepage (dapat sesi + SDK loaded)
  2. Picu cart/mini berulang sampai SDK redirect ke /verify/captcha
  3. Di /verify/captcha: deteksi tipe, solve pakai SadCaptcha
     (shopee_v6.solve_image_crawl = drag handle, method yang TERBUKTI)
  4. Setelah lolos -> buka /user/account/settings
  5. Klik Nomor HP -> isi nomor baru -> OTP
"""
import json, sys, time, os

sys.path.insert(0, "/root/shopee-farm")

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1553.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283191104601"
BUDGET = int(sys.argv[3]) if len(sys.argv) > 3 else 3600

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
OUT = "/root/shopee-verify/FINAL_CP.json"
T0 = time.time()
STATUS = "/root/shopee-verify/FINAL_STATUS.txt"


def log(*a):
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    try:
        with open("/root/shopee-verify/FINAL.log", "a") as f:
            f.write(m + "\n")
    except Exception:
        pass


def set_status(s):
    try:
        open(STATUS, "w").write(s)
    except Exception:
        pass


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

try:
    import shopee_v6 as V6
    KEY = open("/root/shopee-farm/bot_key.txt").read().strip()
    SOLVER = True
    log(f"SadCaptcha key: {KEY[:8]}...")
except Exception as e:
    V6 = None
    KEY = ""
    SOLVER = False
    log(f"solver OFF: {e}")

from playwright.sync_api import sync_playwright

net = []
sig_box = {}
flag_seen = {"captcha_page": False, "generated": 0, "verified": 0}


def onresp(r):
    u = r.url
    if "/api/v4/" not in u:
        return
    short = u.split("shopee.co.id")[-1].split("?")[0][:80]
    try:
        b = r.text()
    except Exception:
        b = ""
    net.append({"u": short, "s": r.status, "b": b[:1200]})
    if "token/verify" in short and '"signature"' in b:
        try:
            sg = (json.loads(b).get("data") or {}).get("signature")
            if sg:
                sig_box["sig"] = sg
                open("/root/shopee-verify/IVS_SIGNATURE.txt", "w").write(sg)
                log(f"🎉 SIGNATURE {len(sg)}B")
        except Exception:
            pass
    if "captcha/generate" in short:
        flag_seen["generated"] += 1
        log(f"  gen #{flag_seen['generated']}: {b[:110]}")
    if "captcha/verify" in short:
        flag_seen["verified"] += 1
        log(f"  verify #{flag_seen['verified']}: {r.status} {b[:130]}")
    if "change_phone" in short or "otp/" in short or "ivs/" in short:
        log(f"  NET {r.status} {short} :: {b[:110]}")


def handle_modals(pg):
    for sel in ('button:has-text("Setuju")', 'text=Setuju',
                'text=Bahasa Indonesia'):
        try:
            l = pg.locator(sel)
            if l.count() and l.first.is_visible():
                l.first.click(timeout=2500, force=True)
                log(f"  modal: {sel[:26]}")
                pg.wait_for_timeout(2000)
                return True
        except Exception:
            pass
    return False


def captcha_present(pg):
    try:
        return pg.evaluate("""()=>{
          const q = s => document.querySelector(s);
          return {
            canvas: document.querySelectorAll('canvas').length,
            aside: !!q('aside'),
            nc: !!q('#NEW_CAPTCHA'),
            mask: !!q('#captchaMask'),
            txt: (document.body.innerText||'').slice(0,120)
          };
        }""")
    except Exception:
        return {"canvas": 0}


def solve_captcha(pg):
    """Solve pakai shopee_v6 (deteksi tipe + SadCaptcha + drag handle)."""
    if not SOLVER:
        return False
    try:
        r = V6.solve_image_crawl(pg, KEY)
        log(f"  solver -> {r}")
        return bool(r)
    except Exception as e:
        log(f"  solver err: {str(e)[:100]}")
        try:
            r = V6.solve_image_drag(pg, KEY)
            log(f"  drag solver -> {r}")
            return bool(r)
        except Exception as e2:
            log(f"  drag err: {str(e2)[:80]}")
    return False


with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,900",
        "--disable-blink-features=AutomationControlled",
        "--lang=id-ID"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 900},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    ctx.add_cookies(cookies)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};"
        "Object.defineProperty(navigator,'languages',{get:()=>['id-ID','id','en']});")
    pg = ctx.new_page()
    pg.on("response", onresp)

    # ============ 1. HOME ============
    log("=== 1. homepage ===")
    home_ok = False
    for a in range(6):
        try:
            pg.goto("https://shopee.co.id/", wait_until="domcontentloaded",
                    timeout=60000)
        except Exception as e:
            log(f"  err {str(e)[:45]}")
            time.sleep(3)
            continue
        pg.wait_for_timeout(8000)
        handle_modals(pg)
        pg.wait_for_timeout(2000)
        if "captcha" in pg.url:
            log(f"  kena captcha di home, coba solve")
            if solve_captcha(pg):
                pg.wait_for_timeout(6000)
        body = pg.evaluate("()=>document.body.innerText.slice(0,100)")
        log(f"  [{a+1}] {pg.url.split('shopee.co.id')[-1][:40]} | {body[:60].replace(chr(10),' ')}")
        if "captcha" not in pg.url and len(body.strip()) > 30:
            home_ok = True
            break
    if not home_ok:
        log("  ⚠ home tidak bersih, lanjut saja")

    # ============ 2. TRIGGER 90309999 -> redirect => captcha asli ============
    log("\n=== 2. trigger anti-crawler via commerce ===")
    for a in range(10):
        if time.time() - T0 > BUDGET - 900:
            break
        try:
            r = pg.evaluate("""async ()=>{
              try {
                const res = await fetch('/api/v4/cart/mini?need_buyer_dp_info=1',
                  {credentials:'include'});
                const j = await res.json();
                return {status: res.status, err: j.error, keys: Object.keys(j).slice(0,6)};
              } catch(e){ return {ex: String(e).slice(0,50)}; }
            }""")
            log(f"  cart/mini #{a+1}: {r}")
            if r.get("err") == 90309999:
                log("  ✅ ANTI-CRAWLER TRIGGERED")
                break
        except Exception as e:
            log(f"  err {str(e)[:50]}")
        pg.wait_for_timeout(4000)

    pg.wait_for_timeout(6000)
    log(f"  url sekarang: {pg.url[:90]}")
    ci = captcha_present(pg)
    log(f"  captcha state: {ci}")

    # ============ 3. JIKA di /verify/captcha: SOLVE ============
    if "captcha" in pg.url or ci.get("canvas", 0) > 0:
        set_status("CAPTCHA_PAGE")
        log("\n=== 3. halaman captcha — SOLVE ===")
        for attempt in range(6):
            if time.time() - T0 > BUDGET - 600:
                log("  ⏰ timeout solve")
                break
            pg.wait_for_timeout(3000)
            handle_modals(pg)
            ci = captcha_present(pg)
            log(f"  [{attempt+1}] canvas={ci.get('canvas')} apart={ci.get('aside')}")

            if "captcha" not in pg.url and ci.get("canvas", 0) == 0:
                log("  ✅ captcha lolos! keluar dari halaman verify")
                set_status("CAPTCHA_CLEARED")
                break

            ok = solve_captcha(pg)
            pg.wait_for_timeout(7000)
            if ok:
                log("  solver jalan, cek status...")

    # ============ 4. SETTINGS ============
    log("\n=== 4. buka settings ===")
    for a in range(8):
        if time.time() - T0 > BUDGET - 420:
            break
        try:
            pg.goto("https://shopee.co.id/user/account/settings",
                    wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            log(f"  err {str(e)[:45]}")
            time.sleep(3)
            continue
        pg.wait_for_timeout(7000)
        handle_modals(pg)
        if "captcha" in pg.url:
            log(f"  [{a+1}] captcha lagi -> solve")
            solve_captcha(pg)
            pg.wait_for_timeout(6000)
            continue
        body = pg.evaluate("()=>document.body.innerText")
        ok = len(body.strip()) > 150 and "Verifikasi gagal" not in body
        log(f"  [{a+1}] {pg.url.split('shopee.co.id')[-1][:45]} len={len(body)} ok={ok}")
        if ok:
            break

    pg.screenshot(path="/root/shopee-verify/FIN_settings.png", full_page=True)
    body = pg.evaluate("()=>document.body.innerText.slice(0,600)")
    log(f"  body: {body[:350].replace(chr(10),' | ')}")

    # ============ 5. KLIK NOMOR HP ============
    log("\n=== 5. cari Nomor HP ===")
    els = pg.evaluate("""()=>Array.from(document.querySelectorAll('a,button,div,span,li'))
      .map(e=>({t:(e.innerText||'').trim().slice(0,45),h:e.getAttribute('href')||''}))
      .filter(x=>x.t&&x.t.length<55).slice(0,150)""")
    hits = [e for e in els if any(k in e["t"].lower()
                                  for k in ("nomor", "phone", "hp", "ubah", "ganti"))]
    for e in hits[:12]:
        log(f"  ★ {e['t']!r} -> {e['h'][:40]}")

    clicked = False
    for sel in ('text=Nomor HP', 'text=Nomor Telepon', 'text=Ubah Nomor',
                'a[href*="phone"]', 'text=Ubah', 'text=Ganti'):
        try:
            l = pg.locator(sel)
            if l.count() and l.first.is_visible():
                l.first.click(timeout=5000, force=True)
                log(f"  ✅ klik {sel!r}")
                clicked = True
                pg.wait_for_timeout(9000)
                handle_modals(pg)
                if "captcha" in pg.url:
                    log("  captcha setelah klik -> solve")
                    solve_captcha(pg)
                    pg.wait_for_timeout(6000)
                break
        except Exception:
            pass

    pg.wait_for_timeout(4000)
    log(f"  url: {pg.url[:90]}")
    b2 = pg.evaluate("()=>document.body.innerText.slice(0,700)")
    log(f"  body: {b2[:400].replace(chr(10),' | ')}")
    pg.screenshot(path="/root/shopee-verify/FIN_phone.png", full_page=True)

    # ============ 6. ISI NOMOR BARU ============
    log("\n=== 6. isi nomor baru ===")
    fill_selectors = [
        'input[type="tel"]',
        'input[name*="phone"]',
        'input[name*="hone"]',
        'input[placeholder*="omor"]',
        'input[placeholder*="08"]',
    ]
    for sel in fill_selectors:
        try:
            l = pg.locator(sel)
            if l.count() > 0 and l.first.is_visible():
                l.first.click(force=True)
                pg.wait_for_timeout(500)
                l.first.fill("")
                for ch in NEWPHONE:
                    l.first.type(ch, delay=60)
                log(f"  ✅ isi {NEWPHONE} di {sel}")
                pg.wait_for_timeout(2500)
                pg.screenshot(path="/root/shopee-verify/FIN_filled.png", full_page=True)
                # klik lanjut/kirim
                for btn in ('button:has-text("Lanjut")', 'button:has-text("Kirim")',
                            'button:has-text("Selanjutnya")', 'button:has-text("Konfirmasi")',
                            'button:has-text("Simpan")'):
                    try:
                        b = pg.locator(btn)
                        if b.count() and b.first.is_visible():
                            b.first.click(timeout=5000, force=True)
                            log(f"  ✅ klik {btn}")
                            pg.wait_for_timeout(9000)
                            handle_modals(pg)
                            if "captcha" in pg.url:
                                log("  captcha -> solve")
                                solve_captcha(pg)
                                pg.wait_for_timeout(6000)
                            break
                    except Exception:
                        pass
                break
        except Exception as e:
            log(f"  {sel}: {str(e)[:40]}")

    pg.wait_for_timeout(5000)
    set_status("OTP_STAGE")
    log(f"\n  url akhir: {pg.url[:90]}")
    b3 = pg.evaluate("()=>document.body.innerText.slice(0,900)")
    log(f"  body: {b3[:500].replace(chr(10),' | ')}")
    pg.screenshot(path="/root/shopee-verify/FIN_final.png", full_page=True)

    # cookie baru
    cks = ctx.cookies()
    ckstr = "; ".join(f"{c['name']}={c['value']}" for c in cks)
    open("/root/shopee-verify/ck_final.txt", "w").write(ckstr)
    log(f"  cookie baru -> ck_final.txt ({len(cks)} item)")

    log(f"\n=== summary gen={flag_seen['generated']} verify={flag_seen['verified']} sig={'YES' if sig_box.get('sig') else 'NO'} ===")
    json.dump({"url": pg.url, "net": net[-120:], "sig": sig_box.get("sig"),
               "flags": flag_seen, "body": b3[:1500]},
              open(OUT, "w"), indent=1)
    log(f"-> {OUT}")
    br.close()

log("\n=== SELESAI ===")
