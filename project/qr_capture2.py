# -*- coding: utf-8 -*-
"""qr_capture2.py — login -> QR capture. Robust: poll input, Enter submit.
"""
import sys, json, time, os

USERNAME = sys.argv[1] if len(sys.argv) > 1 else "yq7uwh456q"
PASSW = sys.argv[2] if len(sys.argv) > 2 else "qwertyui123"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"


def log(*a):
    print(*a, flush=True)


def wait_form(pg, sel, max_s=45):
    for i in range(max_s // 3):
        if pg.locator(sel).count() > 0:
            return True
        pg.wait_for_timeout(3000)
    return False


log("UA:", UA[:60])

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,900",
        "--disable-blink-features=AutomationControlled"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 900},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    ctx.add_init_script("""
      Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
      Object.defineProperty(navigator,'languages',{get:()=>['id-ID','id','en-US','en']});
      Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
    """)
    pg = ctx.new_page()

    # ============ 1. LOGIN PAGE ============
    log("\n=== 1. login page ===")
    pg.goto("https://shopee.co.id/buyer/login", wait_until="domcontentloaded", timeout=90000)
    if not wait_form(pg, 'input[name="loginKey"]', 45):
        log("  RELOAD")
        pg.reload(wait_until="domcontentloaded", timeout=60000)
        if not wait_form(pg, 'input[name="loginKey"]', 45):
            log("  ❌ form tidak muncul")
            log("  body:", pg.evaluate("()=>document.body.innerText.slice(0,200)"))
            br.close()
            sys.exit(1)
    log("  ✅ form siap")

    # ============ 2. ISI USERNAME ============
    log("\n=== 2. isi username ===")
    el = pg.locator('input[name="loginKey"]').first
    el.click(force=True)
    el.type(USERNAME, delay=45)
    log(f"  {USERNAME} -> {len(el.input_value())} char")
    pg.wait_for_timeout(1000)

    # ============ 3. SUBMIT ============
    log("\n=== 3. submit login ===")
    el.press("Enter")
    pg.wait_for_timeout(5000)
    if pg.locator('input[type="password"]').count() == 0:
        # fallback klik
        log("  password form belum, klik LOG IN")
        try:
            pg.get_by_text("LOG IN", exact=True).last.click(timeout=6000, force=True)
        except Exception:
            pass
        pg.wait_for_timeout(5000)

    # ============ 4. PASSWORD ============
    log("\n=== 4. password ===")
    if not wait_form(pg, 'input[type="password"]', 25):
        log("  ❌ password form tidak muncul")
        log("  url:", pg.url[:80])
        log("  body:", pg.evaluate("()=>document.body.innerText.slice(0,300)").replace("\n", " | ")[:280])
        pg.screenshot(path="/root/shopee-verify/qr_fail1.png", full_page=True)
        br.close()
        sys.exit(1)

    pwi = pg.locator('input[type="password"]').first
    pwi.click(force=True)
    pwi.type(PASSW, delay=50)
    log(f"  pw: {len(pwi.input_value())} char")
    pg.wait_for_timeout(800)
    pwi.press("Enter")
    pg.wait_for_timeout(12000)

    log(f"  url: {pg.url[:90]}")
    body = pg.evaluate("()=>document.body.innerText.slice(0,400)")
    log(f"  body: {body.replace(chr(10),' | ')[:350]}")

    # ============ 5. CARI QR ============
    log("\n=== 5. cari QR ===")
    if "ivs" in pg.url or "verify" in pg.url:
        # klik opsi QR
        for t in ("Verifikasi dengan Scan Kode QR", "Scan Kode QR", "Kode QR",
                  "Verifikasi dengan Scan"):
            try:
                loc = pg.get_by_text(t)
                if loc.count() > 0:
                    loc.last.click(timeout=7000, force=True)
                    log(f"  klik '{t}'")
                    pg.wait_for_timeout(7000)
                    break
            except Exception:
                pass

        log(f"  url: {pg.url[:90]}")
        b2 = pg.evaluate("()=>document.body.innerText.slice(0,400)")
        log(f"  body: {b2.replace(chr(10),' | ')[:350]}")

        pg.screenshot(path="/root/shopee-verify/qr_page.png", full_page=True)
        log("  📸 qr_page.png")

        # dump element
        info = pg.evaluate("""()=>{
          const out={canvas:[],img:[],n:0};
          document.querySelectorAll('canvas').forEach((c,i)=>{
            const r=c.getBoundingClientRect();
            out.canvas.push({i,w:Math.round(r.width),h:Math.round(r.height)});
          });
          document.querySelectorAll('img').forEach((im,i)=>{
            const r=im.getBoundingClientRect();
            if(r.width>60&&r.height>60)
              out.img.push({i,w:Math.round(r.width),h:Math.round(r.height),
                            src:(im.src||'').slice(0,60)});
          });
          return out;
        }""")
        log(f"  elemen: {json.dumps(info)[:400]}")

        # crop
        saved = False
        cands = [("canvas", c) for c in info["canvas"]] + [("img", i) for i in info["img"]]
        cands.sort(key=lambda x: -x[1].get("w", 0))
        for kind, it in cands:
            if it.get("w", 0) < 100:
                continue
            try:
                pg.locator(kind).nth(it["i"]).screenshot(
                    path="/root/shopee-verify/qr.png")
                log(f"  ✅ qr.png dari {kind}#{it['i']} {it['w']}x{it['h']}")
                saved = True
                break
            except Exception as e:
                log(f"  {kind}#{it['i']} err {str(e)[:40]}")
        if not saved:
            log("  ⚠️ tidak ada canvas/img QR, screenshot full")

        # tunggu scan
        log("\n=== 6. tunggu scan (6 menit) ===")
        for i in range(72):
            pg.wait_for_timeout(5000)
            cur = pg.url
            cks = {c["name"]: c["value"] for c in ctx.cookies()}
            if i % 4 == 0:
                log(f"  [{i*5}s] {cur[:55]} ST={'Y' if cks.get('SPC_ST') else 'N'}")
            if "verify" not in cur and cks.get("SPC_ST"):
                log("  ✅✅ SCAN BERHASIL — SPC_ST BARU!")
                break

        cks = {c["name"]: c["value"] for c in ctx.cookies()}
        open("/root/shopee-verify/ck_qr_verified.txt", "w").write(
            "; ".join(f"{k}={v}" for k, v in cks.items()))
        log(f"  cookie -> ck_qr_verified.txt ({len(cks)})")

        # cek gate
        log("\n=== 7. cek 90309999 ===")
        GATE = []
        pg.on("response", lambda r: GATE.append(1)
              if "/api/v4" in r.url and "90309999" in (r.text() if r.status else "")
              else None)
        try:
            pg.goto("https://shopee.co.id/cart", wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(9000)
            log("  cart:", pg.url[:80], "gate:", len(GATE))
        except Exception as e:
            log("  err:", str(e)[:50])
    else:
        log("  ⚠️ tidak masuk halaman verify")

    pg.screenshot(path="/root/shopee-verify/qr_final.png", full_page=True)
    br.close()

log("\n=== SELESAI ===")
