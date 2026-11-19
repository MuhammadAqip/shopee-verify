# -*- coding: utf-8 -*-
"""qr_full.py — QR FLOW LENGKAP dari VPS.

type:7 = Scan Kode QR. Flow:
  1. login_by_password -> error=98
  2. ivs/methods -> type:7 v_token
  3. method/select -> pilih type 7
  4. Browser render QR di /verify/ivs
  5. Maker scan pakai app Shopee (akun yq7uwh456q)
  6. Browser polling -> SPC_ST muncul
  7. Selesai

Script ini TIDAK nutup browser sampai QR scanned.
QR di-crop dari screenshot dan disimpan ke qr_live.png.
"""
import sys, json, time, os

USER = sys.argv[1] if len(sys.argv) > 1 else "yq7uwh456q"
PASSW = sys.argv[2] if len(sys.argv) > 2 else "qwertyui123"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"


def log(*a):
    print(*a, flush=True)


from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,1000"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 1000},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    pg = ctx.new_page()

    log("=== 1. login page ===")
    pg.goto("https://shopee.co.id/buyer/login", wait_until="domcontentloaded", timeout=90000)
    for _ in range(15):
        if pg.locator('input[name="loginKey"]').count() > 0:
            break
        pg.wait_for_timeout(2000)
    pg.wait_for_timeout(3000)
    log("  form siap")

    log("\n=== 2. login ===")
    el = pg.locator('input[name="loginKey"]').first
    el.click(force=True)
    el.type(USER, delay=45)
    pg.wait_for_timeout(700)
    el.press("Enter")
    pg.wait_for_timeout(4000)

    pwi = pg.locator('input[type="password"]').first
    pwi.wait_for(state="visible", timeout=25000)
    pwi.click(force=True)
    pwi.type(PASSW, delay=50)
    pg.wait_for_timeout(700)
    pwi.press("Enter")
    pg.wait_for_timeout(10000)

    log(f"  url: {pg.url[:80]}")

    # === QR page ===
    if "/verify/ivs" in pg.url or "/verify/qr" in pg.url:
        log("\n=== 3. halaman IVS ===")
        body = pg.evaluate("()=>document.body.innerText.slice(0,300)").replace("\n", " | ")
        log(f"  {body[:200]}")

        # klik tombol QR
        for t in ("Verifikasi dengan Scan Kode QR", "Scan Kode QR", "Kode QR"):
            try:
                loc = pg.get_by_text(t)
                if loc.count() > 0:
                    loc.last.click(timeout=7000, force=True)
                    log(f"  klik '{t}'")
                    pg.wait_for_timeout(8000)
                    break
            except Exception:
                pass

        log(f"  url: {pg.url[:80]}")
        pg.screenshot(path="/root/shopee-verify/qr_live_full.png", full_page=False)

        # crop QR
        try:
            from PIL import Image
            im = Image.open("/root/shopee-verify/qr_live_full.png")
            w, h = im.size
            # QR biasanya di tengah kartu
            box = (int(w*0.42), int(h*0.33), int(w*0.58), int(h*0.62))
            qr = im.crop(box)
            qr = qr.resize((qr.width*3, qr.height*3), Image.LANCZOS)
            qr.save("/root/shopee-verify/qr_live.png")
            log(f"  ✅ qr_live.png {qr.size}")
        except Exception as e:
            log("  crop err:", str(e)[:60])

        log("\n=== 4. MENUNGGU SCAN (10 menit) ===")
        for i in range(120):
            pg.wait_for_timeout(5000)
            cks = {c["name"]: c["value"] for c in ctx.cookies()}
            if "SPC_ST" in cks:
                log("  🟢🟢 SPC_ST DIDAPAT — SCAN BERHASIL!")
                break
            if i % 6 == 0:
                log(f"  [{i*5}s] {pg.url[:55]} ST={'Y' if 'SPC_ST' in cks else 'N'}")

        cks = {c["name"]: c["value"] for c in ctx.cookies()}
        if "SPC_ST" in cks:
            open("/root/shopee-verify/ck_qr_ok.txt", "w").write(
                "; ".join(f"{k}={v}" for k, v in cks.items()))
            log("  -> ck_qr_ok.txt")
            # tes cart
            r = pg.evaluate("""async ()=>{
              const res=await fetch('/api/v4/cart/mini',{method:'POST',credentials:'include',
                headers:{'Accept':'application/json','X-Shopee-Language':'id',
                         'X-API-SOURCE':'pc','X-Requested-With':'XMLHttpRequest',
                         'Content-Type':'application/json'},
                body:JSON.stringify({version_list:[3145728,65]})});
              let j=null;try{j=await res.json();}catch(e){}
              return {s:res.status,e:j&&j.error};
            }""")
            log(f"  cart/mini: {json.dumps(r)}")
    else:
        log("  ⚠️ tidak di halaman IVS")

    br.close()

log("\n=== SELESAI ===")
