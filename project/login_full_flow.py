# -*- coding: utf-8 -*-
"""login_full_flow.py — LOGIN LENGKAP dari VPS, satu rantai konsisten.

Berdasarkan capture MITM:
  1. login_by_password  -> error=98 {ivs_flow_no, ivs_token}
  2. ivs/methods        -> [{type, v_token}]
  3. ivs/method/select  -> pilih v_token
  4. device-token/verify (type 20) atau langkah sesuai type
  5. ivs/token/verify   -> signature   <-- YANG HILANG DI BROWSER MAKER
  6. login_by_password LAGI -> error=0 + SPC_ST

Semua request DIKIRIM DARI BROWSER (SDK generate x-sap-sec/ri otomatis),
bukan dari Python — supaya header + DFP konsisten satu device.
"""
import sys, json, time, re

USER = sys.argv[1] if len(sys.argv) > 1 else "yq7uwh456q"
PASSW = sys.argv[2] if len(sys.argv) > 2 else "qwertyui123"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
OUT = "/root/shopee-verify/flow_result.json"


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

    LOG = []

    def onresp(r):
        if "/api/v4/" in r.url:
            try:
                t = r.text()
            except Exception:
                return
            short = r.url.split("shopee.co.id")[-1][:70]
            if any(k in short for k in ("login", "ivs", "anti_fraud", "device-token")):
                LOG.append({"url": short, "status": r.status, "body": t[:1500]})
                log(f"  ← {r.status} {short}")
                try:
                    j = json.loads(t)
                    e = j.get("error")
                    log(f"     error={e} data={str(j.get('data'))[:180]}")
                except Exception:
                    pass

    pg.on("response", onresp)

    # === 1. buka login page (SDK init, DFP generate) ===
    log("\n=== 1. buka /buyer/login ===")
    pg.goto("https://shopee.co.id/buyer/login", wait_until="domcontentloaded", timeout=90000)
    for _ in range(15):
        if pg.locator('input[name="loginKey"]').count() > 0:
            break
        pg.wait_for_timeout(2000)
    pg.wait_for_timeout(4000)
    log("  form siap")

    # === 2. login attempt #1 ===
    log("\n=== 2. LOGIN #1 (harap error=98) ===")
    el = pg.locator('input[name="loginKey"]').first
    el.click(force=True)
    el.type(USER, delay=45)
    pg.wait_for_timeout(800)
    el.press("Enter")
    pg.wait_for_timeout(4000)

    pwi = pg.locator('input[type="password"]').first
    if pwi.count() == 0:
        log("  ❌ password form tidak muncul")
        br.close()
        sys.exit(1)
    pwi.click(force=True)
    pwi.type(PASSW, delay=50)
    pg.wait_for_timeout(700)
    pwi.press("Enter")
    pg.wait_for_timeout(9000)

    log(f"  url: {pg.url[:80]}")

    # === 3. IVS flow otomatis — tunggu browser selesaikan ===
    log("\n=== 3. tunggu IVS otomatis (browser handle sendiri) ===")
    for i in range(20):
        pg.wait_for_timeout(2000)
        cks = {c["name"] for c in ctx.cookies()}
        if "SPC_ST" in cks:
            log("  🟢 SPC_ST MUNCUL!")
            break
        if i % 3 == 0:
            log(f"  [{i*2}s] url={pg.url[:60]} ST={'Y' if 'SPC_ST' in cks else 'N'}")

    # === 4. cek apakah perlu klik ulang / lanjut ===
    body = pg.evaluate("()=>document.body.innerText.slice(0,400)").replace("\n", " | ")
    log(f"\n  body: {body[:250]}")

    cks = {c["name"]: c["value"] for c in ctx.cookies()}
    if "SPC_ST" not in cks:
        log("\n=== 4. LOGIN #2 (setelah device token) ===")
        # kembali ke login
        try:
            pg.goto("https://shopee.co.id/buyer/login", wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(5000)
            if pg.locator('input[name="loginKey"]').count() > 0:
                el = pg.locator('input[name="loginKey"]').first
                el.click(force=True)
                el.type(USER, delay=45)
                pg.wait_for_timeout(700)
                el.press("Enter")
                pg.wait_for_timeout(3500)
                pwi = pg.locator('input[type="password"]').first
                if pwi.count() > 0:
                    pwi.click(force=True)
                    pwi.type(PASSW, delay=50)
                    pg.wait_for_timeout(700)
                    pwi.press("Enter")
                    pg.wait_for_timeout(12000)
        except Exception as e:
            log("  err:", str(e)[:70])

    # === 5. cek akhir ===
    log("\n=== 5. STATUS AKHIR ===")
    for i in range(10):
        pg.wait_for_timeout(2000)
        cks = {c["name"]: c["value"] for c in ctx.cookies()}
        if "SPC_ST" in cks:
            break

    cks = {c["name"]: c["value"] for c in ctx.cookies()}
    has = "SPC_ST" in cks
    log(f"  SPC_ST: {'✅ ADA' if has else '❌ TIDAK'}")
    log(f"  cookie: {len(cks)}")
    log(f"  url: {pg.url[:80]}")

    if has:
        open("/root/shopee-verify/ck_flow_ok.txt", "w").write(
            "; ".join(f"{k}={v}" for k, v in cks.items()))
        log("  -> ck_flow_ok.txt")

        # cek 90309999
        log("\n=== 6. TES cart/mini ===")
        r = pg.evaluate("""async ()=>{
          const res=await fetch('/api/v4/cart/mini',{method:'POST',credentials:'include',
            headers:{'Accept':'application/json','X-Requested-With':'XMLHttpRequest',
                     'X-API-SOURCE':'pc','X-Shopee-Language':'id','Content-Type':'application/json'},
            body:JSON.stringify({version_list:[3145728,65]})});
          let j=null; try{j=await res.json();}catch(e){}
          return {s:res.status, e:j&&j.error};
        }""")
        log("  ", json.dumps(r))

    json.dump({"log": LOG, "has_st": has, "url": pg.url},
              open(OUT, "w"), indent=1)
    log(f"\n  -> {OUT}")

    br.close()

log("\n=== SELESAI ===")
