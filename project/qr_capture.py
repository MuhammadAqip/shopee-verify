# -*- coding: utf-8 -*-
"""qr_capture.py — login yq7uwh456q -> sampai halaman QR -> crop QR.

Lebih tahan error. QR di halaman /verify/ivs "Verifikasi dengan Scan Kode QR".
"""
import sys, json, time, os

USERNAME = sys.argv[1] if len(sys.argv) > 1 else "yq7uwh456q"
PASSW = sys.argv[2] if len(sys.argv) > 2 else "qwertyui123"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"


def log(*a):
    print(*a, flush=True)


from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,900"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 900},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    pg = ctx.new_page()
    pg.set_default_timeout(20000)

    log("=== 1. login page ===")
    ok = False
    for attempt in range(3):
        try:
            pg.goto("https://shopee.co.id/buyer/login", wait_until="domcontentloaded", timeout=90000)
            pg.wait_for_timeout(6000)
            if pg.locator('input[name="loginKey"]').count() > 0:
                ok = True
                break
            log(f"  [{attempt}] form belum, reload")
            pg.reload(wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(6000)
            if pg.locator('input[name="loginKey"]').count() > 0:
                ok = True
                break
        except Exception as e:
            log(f"  [{attempt}] err: {str(e)[:70]}")
            pg.wait_for_timeout(4000)

    if not ok:
        pg.wait_for_selector('input[name="loginKey"]', state="visible", timeout=45000)
    pg.wait_for_selector('input[name="loginKey"]', state="visible", timeout=30000)
    log("  form siap")

    el = pg.locator('input[name="loginKey"]').first
    el.click(force=True)
    el.type(USERNAME, delay=45)
    log(f"  username: {len(el.input_value())} char")
    pg.wait_for_timeout(1000)

    # submit via Enter (lebih andal dari klik)
    el.press("Enter")
    pg.wait_for_timeout(6000)
    log(f"  url: {pg.url[:75]}")

    # password form
    try:
        pwi = pg.locator('input[type="password"]').first
        pwi.wait_for(state="visible", timeout=20000)
        pwi.click(force=True)
        pwi.type(PASSW, delay=50)
        log(f"  password: {len(pwi.input_value())} char")
        pg.wait_for_timeout(800)
        pwi.press("Enter")
        pg.wait_for_timeout(12000)
    except Exception as e:
        log("  password err:", str(e)[:80])

    log(f"  url setelah login: {pg.url[:85]}")
    body = pg.evaluate("()=>document.body.innerText.slice(0,400)")
    log(f"  body: {body.replace(chr(10),' | ')[:350]}")

    # kalau sudah di IVS, cari QR
    if "ivs" in pg.url or "verify" in pg.url:
        log("\n=== 2. halaman verify — cari QR ===")

        # klik opsi QR kalau ada pilihan
        for t in ("Verifikasi dengan Scan Kode QR", "Scan Kode QR", "Kode QR"):
            try:
                loc = pg.get_by_text(t)
                if loc.count() > 0:
                    loc.last.click(timeout=7000, force=True)
                    log(f"  klik '{t}'")
                    pg.wait_for_timeout(7000)
                    break
            except Exception:
                pass

        log(f"  url: {pg.url[:85]}")
        b2 = pg.evaluate("()=>document.body.innerText.slice(0,350)")
        log(f"  body: {b2.replace(chr(10),' | ')[:300]}")

        # dump semua kemungkinan QR
        info = pg.evaluate("""()=>{
          const out={canvas:[],img:[],svg:[],qrdiv:[]};
          document.querySelectorAll('canvas').forEach((c,i)=>{
            const r=c.getBoundingClientRect();
            out.canvas.push({i,w:Math.round(r.width),h:Math.round(r.height),
                             vis:r.width>10&&r.height>10});
          });
          document.querySelectorAll('img').forEach((im,i)=>{
            const r=im.getBoundingClientRect();
            out.img.push({i,w:Math.round(r.width),h:Math.round(r.height),
                          src:(im.src||'').slice(0,70),vis:r.width>50});
          });
          out.svg=[...document.querySelectorAll('svg')].length;
          document.querySelectorAll('[class*=qr],[id*=qr],[class*=QR]').forEach(e=>{
            const r=e.getBoundingClientRect();
            if(r.width>50) out.qrdiv.push({cls:(e.className||'').toString().slice(0,30),
                                          w:Math.round(r.width)});
          });
          return out;
        }""")
        log(f"  elemen: {json.dumps(info)[:500]}")

        pg.screenshot(path="/root/shopee-verify/qr_page.png", full_page=True)
        log("  screenshot -> qr_page.png")

        # coba semua canvas & img besar
        saved = False
        for kind, lst in (("canvas", info["canvas"]), ("img", info["img"])):
            for it in lst:
                if not it.get("vis"):
                    continue
                try:
                    pg.locator(kind).nth(it["i"]).screenshot(
                        path="/root/shopee-verify/qr.png")
                    log(f"  ✅ QR dari {kind}#{it['i']} ({it['w']}x{it['h']}) -> qr.png")
                    saved = True
                    break
                except Exception as e:
                    log(f"  {kind}#{it['i']} err: {str(e)[:50]}")
            if saved:
                break

        if not saved:
            # fallback: crop area tengah halaman
            try:
                pg.screenshot(path="/root/shopee-verify/qr_page_full.png", full_page=True)
                log("  QR tidak spesifik, full screenshot -> qr_page_full.png")
            except Exception:
                pass

        # tunggu scan
        log("\n=== 3. menunggu scan QR (max 6 menit) ===")
        for i in range(72):
            pg.wait_for_timeout(5000)
            cur = pg.url
            cks = {c["name"]: c["value"] for c in ctx.cookies()}
            if i % 4 == 0:
                log(f"  [{i*5}s] {cur[:55]} ST={'Y' if cks.get('SPC_ST') else 'N'}")
            if "verify" not in cur and cks.get("SPC_ST"):
                log("  ✅ SCAN BERHASIL")
                break

        cks = {c["name"]: c["value"] for c in ctx.cookies()}
        open("/root/shopee-verify/ck_qr_verified.txt", "w").write(
            "; ".join(f"{k}={v}" for k, v in cks.items()))
        log(f"  cookie -> ck_qr_verified.txt ({len(cks)})")

    pg.screenshot(path="/root/shopee-verify/qr_final.png", full_page=True)
    br.close()

log("=== SELESAI ===")
