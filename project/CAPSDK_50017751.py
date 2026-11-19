"""CAPSDK_50017751.py — tangkap SDK captcha BARU (app 50017751) + endpoint API-nya.

Temuan: halaman shopee.co.id memuat SDK captcha dari
  https://security-captcha.cache.susercontent.com/api/v4/50017751/client
APP ID BARU = 50017751 (bukan f9ffc83459897a13dd14c537e84b1753)

Tugas:
  1. buka shopee.co.id dengan cookie, tangkap semua request ke 50017751/*
  2. simpan source SDK
  3. cari endpoint API (generate/verify/get_config) di dalam SDK
  4. cari app_key / scene / AES key baru
"""
import json, sys, time, re

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_fresh_1659.txt"
BUDGET = int(sys.argv[2]) if len(sys.argv) > 2 else 220

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):3d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/CSDK.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright

assets = []
apis = []


def onresp(r):
    u = r.url
    if "50017751" in u:
        try:
            b = r.text()
        except Exception:
            b = ""
        assets.append({"u": u, "s": r.status, "len": len(b)})
        log(f"  ASSET {r.status} {u[-50:]} {len(b)}B")
        # simpan JS
        if len(b) > 5000 and (".js" in u or "client" in u):
            nm = "cap5001_" + re.sub(r"[^a-zA-Z0-9]", "_", u.split("/")[-1])[:40] + ".js"
            open(f"/root/shopee-verify/{nm}", "w", encoding="utf-8").write(b)
            log(f"    → {nm}")
        elif len(b) > 5000:
            nm = "cap5001_" + re.sub(r"[^a-zA-Z0-9]", "_", u.split("/")[-1])[:40] + ".js"
            open(f"/root/shopee-verify/{nm}", "w", encoding="utf-8").write(b)
            log(f"    → {nm}")
    if "/api/v4/" in u and "captcha" in u.lower():
        try:
            b = r.text()
        except Exception:
            b = ""
        apis.append({"u": u.split("shopee.co.id")[-1][:100], "s": r.status, "b": b[:1500]})
        log(f"  API {r.status} {u.split('shopee.co.id')[-1][:70]} :: {b[:110]}")


with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,900",
        "--disable-blink-features=AutomationControlled", "--lang=id-ID"])
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

    log("=== 1. shopee.co.id (SDK 50017751 harus load) ===")
    try:
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    pg.wait_for_timeout(12000)

    # klik modal kalau ada
    for sel in ('button:has-text("Setuju")', 'text=Bahasa Indonesia'):
        try:
            l = pg.locator(sel)
            if l.count() and l.first.is_visible():
                l.first.click(timeout=2000, force=True)
                pg.wait_for_timeout(1500)
        except Exception:
            pass

    # trigger captcha
    log("\n=== 2. trigger captcha ===")
    for a in range(3):
        try:
            r = pg.evaluate("""async ()=>{
              try{const res=await fetch('/api/v4/cart/mini?need_buyer_dp_info=1',
                {credentials:'include'});const j=await res.json();
                return {err:j.error, t:j['0'], six:j['6']?Object.keys(j['6']):null};}
              catch(e){return {ex:String(e).slice(0,40)}}
            }""")
            log(f"  cart#{a+1}: {r}")
        except Exception:
            pass
        pg.wait_for_timeout(5000)

    # buka /verify/captcha untuk picu SDK baru
    try:
        pg.goto("https://shopee.co.id/verify/captcha", wait_until="domcontentloaded",
                timeout=50000)
    except Exception:
        pass
    pg.wait_for_timeout(20000)

    log(f"\n=== 3. url: {pg.url[:100]} ===")
    log(f"  assets: {len(assets)}  apis: {len(apis)}")
    pg.screenshot(path="/root/shopee-verify/CSDK.png", full_page=False)

    json.dump({"assets": assets, "apis": apis, "url": pg.url},
              open("/root/shopee-verify/CSDK.json", "w"), indent=1)
    br.close()

# === 4. grep endpoint di SDK yang tersimpan ===
log("\n=== 4. grep SDK ===")
import glob
for f in glob.glob("/root/shopee-verify/cap5001_*.js"):
    try:
        s = open(f, encoding="utf-8", errors="ignore").read()
    except Exception:
        continue
    log(f"  {f.split('/')[-1]} {len(s)}B")
    for pat in (r"/api/v[0-9]+/[a-z_/]*captcha[a-z_/]*",
                r"app_?key[\"']?\s*[:=]\s*[\"'][a-f0-9]{20,}",
                r"scene[\"']?\s*[:=]\s*[\"'][a-z_]{3,20}",
                r"50017751"):
        hits = sorted(set(re.findall(pat, s, re.I)))[:6]
        if hits:
            log(f"    {pat[:35]} -> {hits}")

log("\n=== SELESAI ===")
