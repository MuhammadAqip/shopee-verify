# -*- coding: utf-8 -*-
"""qr_grab.py — login -> tangkap QR code dari halaman /verify/ivs.

Output: qr.png (siap di-scan pakai app Shopee di HP)
Setelah Maker scan, sesi lanjut -> SPC_ST baru (BERSIH).
"""
import sys, json, time, os

USERNAME = sys.argv[1] if len(sys.argv) > 1 else "yq7uwh456q"
PASSW = sys.argv[2] if len(sys.argv) > 2 else "qwertyui123"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
STATE = "/root/shopee-verify/QR_STATE.json"


def st(s, **kw):
    json.dump({"stage": s, **kw}, open(STATE, "w"))
    print(f"  [STATE] {s} {kw}", flush=True)


from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,900"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 900},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    pg = ctx.new_page()

    print("=== 1. login ===", flush=True)
    pg.goto("https://shopee.co.id/buyer/login", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_selector('input[name="loginKey"]', state="visible", timeout=40000)
    el = pg.locator('input[name="loginKey"]').first
    el.click(force=True)
    el.type(USERNAME, delay=50)
    pg.wait_for_timeout(1200)
    pg.get_by_text("LOG IN", exact=True).last.click(timeout=8000, force=True)
    pg.wait_for_timeout(6000)

    pwi = pg.locator('input[type="password"]').first
    pwi.wait_for(state="visible", timeout=20000)
    pwi.click(force=True)
    pwi.type(PASSW, delay=55)
    pg.wait_for_timeout(1200)
    pg.get_by_text("LOG IN", exact=True).last.click(timeout=8000, force=True)
    pg.wait_for_timeout(10000)

    print("  url:", pg.url[:90], flush=True)
    st("after_login", url=pg.url[:100])

    # === tangkap QR ===
    print("\n=== 2. cari QR code ===", flush=True)
    for attempt in range(6):
        info = pg.evaluate("""()=>{
          const out = {canvas:0, img:[], svg:0, url:location.href};
          out.canvas = document.querySelectorAll('canvas').length;
          document.querySelectorAll('img').forEach(i=>{
            const r=i.getBoundingClientRect();
            if(r.width>80 && r.height>80)
              out.img.push({src:(i.src||'').slice(0,100), w:Math.round(r.width), h:Math.round(r.height)});
          });
          out.svg = document.querySelectorAll('svg').length;
          return out;
        }""")
        print(f"  [{attempt}] {json.dumps(info)[:250]}", flush=True)

        if "ivs" in info["url"] or info["canvas"] > 0 or info["img"]:
            break
        pg.wait_for_timeout(4000)

    # klik tombol QR kalau ada
    try:
        for t in ("Verifikasi dengan Scan Kode QR", "Scan Kode QR", "QR"):
            loc = pg.get_by_text(t)
            if loc.count() > 0:
                loc.last.click(timeout=6000, force=True)
                print(f"  klik '{t}'", flush=True)
                pg.wait_for_timeout(6000)
                break
    except Exception as e:
        print("  klik QR err:", str(e)[:60], flush=True)

    print("  url skrg:", pg.url[:90], flush=True)
    print("  body:", pg.evaluate("()=>document.body.innerText.slice(0,300)").replace("\n", " | ")[:280], flush=True)

    # dump semua elemen QR
    qr = pg.evaluate("""()=>{
      const out = {canvas:[], img:[], code:null};
      document.querySelectorAll('canvas').forEach((c,i)=>{
        const r=c.getBoundingClientRect();
        if(r.width>50 && r.height>50) out.canvas.push({i, w:Math.round(r.width), h:Math.round(r.height)});
      });
      document.querySelectorAll('img').forEach((im,i)=>{
        const r=im.getBoundingClientRect();
        if(r.width>80 && r.height>80) out.img.push({i, w:Math.round(r.width), h:Math.round(r.height), src:(im.src||'').slice(0,80)});
      });
      return out;
    }""")
    print("  QR elemen:", json.dumps(qr)[:400], flush=True)

    pg.screenshot(path="/root/shopee-verify/qr_full.png", full_page=False)
    print("  screenshot -> qr_full.png", flush=True)

    # crop QR dari canvas
    if qr["canvas"]:
        try:
            idx = qr["canvas"][0]["i"]
            pg.locator("canvas").nth(idx).screenshot(path="/root/shopee-verify/qr.png")
            print("  ✅ QR tersimpan -> qr.png", flush=True)
        except Exception as e:
            print("  crop canvas err:", str(e)[:60], flush=True)
    elif qr["img"]:
        try:
            idx = qr["img"][0]["i"]
            pg.locator("img").nth(idx).screenshot(path="/root/shopee-verify/qr.png")
            print("  ✅ QR tersimpan -> qr.png", flush=True)
        except Exception as e:
            print("  crop img err:", str(e)[:60], flush=True)

    st("qr_ready")
    print("\n>>> SCAN qr.png PAKAI APP SHOPEE DI HP <<<", flush=True)
    print(">>> Menunggu scan... (max 8 menit) <<<", flush=True)

    # tunggu scan
    for i in range(96):
        pg.wait_for_timeout(5000)
        cur = pg.url
        cks = {c["name"]: c["value"] for c in ctx.cookies()}
        has_st = bool(cks.get("SPC_ST"))
        if i % 6 == 0:
            print(f"  [{i*5}s] {cur[:60]} ST={'Y' if has_st else 'N'}", flush=True)
        if has_st and "verify" not in cur:
            print("\n  ✅ VERIFIKASI SELESAI!", flush=True)
            break

    print("\n=== status akhir ===", flush=True)
    print("  url:", pg.url[:90], flush=True)
    cks = {c["name"]: c["value"] for c in ctx.cookies()}
    print(f"  SPC_ST: {'ADA' if cks.get('SPC_ST') else 'TIDAK'}", flush=True)
    print(f"  cookie: {len(cks)}", flush=True)

    open("/root/shopee-verify/ck_verified.txt", "w").write(
        "; ".join(f"{k}={v}" for k, v in cks.items()))

    # tes gate
    print("\n=== tes cart/mini ===", flush=True)
    GATE = []
    pg.on("response", lambda r: GATE.append(1)
          if "/api/v4" in r.url and "90309999" in (r.text() if r.status==200 else "")
          else None)
    try:
        pg.goto("https://shopee.co.id/cart", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(8000)
        print("  cart url:", pg.url[:80], flush=True)
        print("  gate events:", len(GATE), flush=True)
        st("done", gate_clean=len(GATE) == 0)
    except Exception as e:
        print("  err:", str(e)[:60], flush=True)

    pg.screenshot(path="/root/shopee-verify/qr_final.png", full_page=False)
    br.close()

print("=== SELESAI ===", flush=True)
