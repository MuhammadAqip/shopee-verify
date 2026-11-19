"""HEADFUL.py — Chromium headful di DISPLAY :99, biarkan user lihat & klik.

VNC aktif di :99 (port 5900 -> websockify 6081).
Script ini:
  1. buka chromium HEADFUL (bukan headless) di :99
  2. set cookie ck_zax
  3. buka shopee.co.id
  4. tunggu user klik manual (atau auto-klik "Ubah Nomor" kalau ketemu)
  5. TIDAK menutup browser — biar user bisa lihat dan interaksi
"""
import json, sys, time, os

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_zax.txt"
DURATION = int(sys.argv[2]) if len(sys.argv) > 2 else 3600
TARGET_URL = sys.argv[3] if len(sys.argv) > 3 else "https://shopee.co.id/"
PROXY = os.environ.get("SHOPEE_PROXY", "")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/HF.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

USERDIR = "/root/shopee-verify/chrome_profile"
os.makedirs(USERDIR, exist_ok=True)

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    # HEADFUL dengan persistent context supaya sesi tersimpan
    ctx = pw.chromium.launch_persistent_context(
        USERDIR,
        headless=False,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--window-size=1366,900",
            "--window-position=0,0",
            "--disable-blink-features=AutomationControlled",
            "--lang=id-ID",
            "--start-maximized",
            "--no-first-run",
            "--no-default-browser-check",
        ],
        user_agent=UA,
        locale="id-ID",
        viewport={"width": 1366, "height": 900},
        timezone_id="Asia/Jakarta",
        proxy={"server": PROXY} if PROXY else None,
    )
    ctx.add_cookies(cookies)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{},loadTimes:function(){},csi:function(){}};"
        "Object.defineProperty(navigator,'languages',{get:()=>['id-ID','id','en']});"
        "Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});"
        "Object.defineProperty(navigator,'hardwareConcurrency',{get:()=>8});"
        "Object.defineProperty(navigator,'deviceMemory',{get:()=>8});")

    pg = ctx.pages[0] if ctx.pages else ctx.new_page()

    NET = []

    def onresp(r):
        u = r.url
        if "/api/v4/" not in u:
            return
        sh = u.split("shopee.co.id")[-1].split("?")[0][:66]
        if "captcha" in sh or "otp" in sh or "change_phone" in sh or "cart" in sh:
            try:
                b = r.text()
            except Exception:
                b = ""
            NET.append({"u": sh, "s": r.status, "b": b[:1500]})
            log(f"  NET {r.status} {sh[:48]} :: {b[:130]}")

    pg.on("response", onresp)

    log(f"=== headful chromium di DISPLAY={os.environ.get('DISPLAY')} ===")
    log(f"    profile: {USERDIR}")
    log(f"    proxy: {PROXY}")

    log(f"\n=== buka {TARGET_URL} ===")
    try:
        pg.goto(TARGET_URL, wait_until="domcontentloaded", timeout=70000)
    except Exception as e:
        log(f"  goto err: {str(e)[:80]}")

    pg.wait_for_timeout(12000)

    st = pg.evaluate("""()=>({
      url:location.href,
      n:[...document.querySelectorAll('canvas')].length,
      txt:(document.body.innerText||'').slice(0,300)
    })""")
    log(f"  url: {st['url'][:110]}")
    log(f"  canvas={st['n']}")
    log(f"  txt: {st['txt'][:200].replace(chr(10),' | ')}")

    # cek sesi
    a = pg.evaluate("""async()=>{try{
      const r=await fetch('/api/v4/account/basic/get_account_info',{credentials:'include'});
      const j=await r.json();return {err:j.error,user:(j.data||{}).username};
    }catch(e){return{ex:String(e).slice(0,50)}}}""")
    log(f"  sesi: {a}")

    log("\n" + "=" * 50)
    log("BROWSER SEKARANG TERBUKA DI VNC")
    log("Silakan lihat dan klik manual.")
    log("Script TIDAK menutup browser.")
    log("=" * 50)

    # loop monitor — biarkan user interaksi, catat apa yang terjadi
    last_url = ""
    for i in range(DURATION // 10):
        pg.wait_for_timeout(10000)
        try:
            cur = pg.evaluate("""()=>({
              url:location.href,
              n:[...document.querySelectorAll('canvas')].length,
              txt:(document.body.innerText||'').slice(0,200)
            })""")
        except Exception:
            continue

        if cur["url"] != last_url:
            last_url = cur["url"]
            log(f"  [URL BERUBAH] {cur['url'][:110]}")
            log(f"    canvas={cur['n']} txt={cur['txt'][:130].replace(chr(10),' | ')}")

        if cur["n"] and i % 3 == 0:
            log(f"  ★ CAPTCHA TERLIHAT! canvas={cur['n']}")

        # simpan screenshot periodik
        if i % 6 == 0:
            try:
                pg.screenshot(path="/root/shopee-verify/HF_live.png", full_page=False)
            except Exception:
                pass

        # kalau cookie baru muncul (user login), simpan
        if i % 12 == 0:
            try:
                cs = ctx.cookies()
                if cs:
                    s = "; ".join(f"{c['name']}={c['value']}"
                                  for c in cs if c["domain"].endswith("shopee.co.id"))
                    open("/root/shopee-verify/ck_live.txt", "w").write(s)
            except Exception:
                pass

    json.dump({"net": NET[-50:], "final_url": last_url},
              open("/root/shopee-verify/HF.json", "w"), indent=1)
    log("\n=== waktu habis, browser ditutup ===")
    ctx.close()
