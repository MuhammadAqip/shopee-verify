"""SAP_flow.py — request dengan header x-sap-* ASLI dari browser.

hdr_test.py membuktikan: header lengkap -> HTTP 200 (gate lolos).
Tapi body tetap 90309999 -> itu ANTI-CRAWLER, bukan header.

Yang perlu: header di-generate FRESH setiap request oleh SDK.
Maka: lakukan SEMUA dari dalam browser (page-context fetch) supaya
SDK sign otomatis - JANGAN kirim header manual dari Python.

Ini yang belum dicoba: page.evaluate(fetch) ke endpoint commerce,
lalu ikuti redirect yang SDK berikan.
"""
import json, sys, time

sys.path.insert(0, "/root/shopee-farm")

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1425.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283191104601"
BUDGET = int(sys.argv[3]) if len(sys.argv) > 3 else 800

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    try:
        open("/root/shopee-verify/SAP.log", "a").write(m + "\n")
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
except Exception:
    V6, KEY, SOLVER = None, "", False

from playwright.sync_api import sync_playwright

net = []


def onresp(r):
    u = r.url
    if "/api/v4/" not in u:
        return
    short = u.split("shopee.co.id")[-1].split("?")[0][:80]
    try:
        b = r.text()
    except Exception:
        b = ""
    net.append({"u": short, "s": r.status, "b": b[:1000]})
    if any(k in short for k in ("captcha", "ivs/", "change_phone", "otp/")):
        log(f"  NET {r.status} {short} :: {b[:120]}")


def modals(pg):
    for sel in ('button:has-text("Setuju")', 'text=Setuju',
                'text=Bahasa Indonesia'):
        try:
            l = pg.locator(sel)
            if l.count() and l.first.is_visible():
                l.first.click(timeout=2200, force=True)
                pg.wait_for_timeout(1800)
                return True
        except Exception:
            pass
    return False


def solve(pg):
    if not SOLVER:
        return False
    for fn in ("solve_image_crawl", "solve_image_drag"):
        try:
            f = getattr(V6, fn, None)
            if not f:
                continue
            r = f(pg, KEY)
            log(f"  {fn} -> {str(r)[:80]}")
            if r and not (isinstance(r, dict) and r.get("err")):
                return True
        except Exception as e:
            log(f"  {fn} err {str(e)[:60]}")
    return False


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

    log("=== 1. home + biarkan SDK load ===")
    for a in range(4):
        try:
            pg.goto("https://shopee.co.id/", wait_until="domcontentloaded",
                    timeout=60000)
        except Exception:
            time.sleep(3)
            continue
        pg.wait_for_timeout(9000)
        modals(pg)
        log(f"  [{a+1}] {pg.url.split('shopee.co.id')[-1][:50]}")
        if "/verify/" not in pg.url:
            break

    # === 2. page-context fetch: SDK yang sign ===
    log("\n=== 2. page-context fetch ke endpoint account ===")
    probes = [
        "/api/v4/account/basic/get_account_info",
        "/api/v4/account/subaccount",
        "/api/v4/cart/mini?need_buyer_dp_info=1",
        "/api/v4/account/check_tos_consent",
    ]
    results = {}
    for p in probes:
        try:
            r = pg.evaluate("""async (path)=>{
              try {
                const res = await fetch(path, {credentials:'include'});
                const txt = await res.text();
                let j = null;
                try { j = JSON.parse(txt); } catch(e){}
                return {s: res.status, err: j ? j.error : null,
                        txt: txt.slice(0,200)};
              } catch(e){ return {ex:String(e).slice(0,60)}; }
            }""", p)
            results[p] = r
            log(f"  {p.split('/')[-1][:32]:34s} s={r.get('s')} err={r.get('err')}")
            if r.get("txt"):
                log(f"      {r['txt'][:120]}")
        except Exception as e:
            log(f"  {p} ERR {str(e)[:50]}")

    # === 3. kalau ada 90309999, ikuti redirect ===
    log("\n=== 3. cek redirect ===")
    pg.wait_for_timeout(5000)
    log(f"  url: {pg.url[:120]}")
    if "/verify/" in pg.url:
        log("  ⚠ kena verify page")

    # === 4. langsung coba settings via SPA ===
    log("\n=== 4. settings via page-context fetch ===")
    try:
        r = pg.evaluate("""async ()=>{
          try {
            const res = await fetch('/api/v4/account/basic/get_account_info',
              {credentials:'include'});
            const j = await res.json();
            return {s:res.status, err:j.error, keys:Object.keys(j).slice(0,8)};
          } catch(e){ return {ex:String(e).slice(0,50)}; }
        }""")
        log(f"  account_info: {r}")
    except Exception as e:
        log(f"  err {str(e)[:50]}")

    # === 5. navigasi UI ke settings ===
    log("\n=== 5. navigasi UI ke settings ===")
    for a in range(6):
        try:
            pg.goto("https://shopee.co.id/user/account/settings",
                    wait_until="domcontentloaded", timeout=55000)
        except Exception:
            continue
        pg.wait_for_timeout(8000)
        modals(pg)
        if "captcha" in pg.url:
            log(f"  [{a+1}] captcha -> solve")
            solve(pg)
            pg.wait_for_timeout(6000)
            continue
        body = pg.evaluate("()=>document.body.innerText")
        ok = len(body.strip()) > 150 and "Verifikasi gagal" not in body
        log(f"  [{a+1}] {pg.url.split('shopee.co.id')[-1][:42]} len={len(body)} ok={ok}")
        if ok:
            break
        pg.wait_for_timeout(3000)

    pg.screenshot(path="/root/shopee-verify/SAP_settings.png", full_page=True)
    body = pg.evaluate("()=>document.body.innerText.slice(0,600)")
    log(f"  body: {body[:350].replace(chr(10),' | ')}")

    # === 6. klik nomor HP ===
    log("\n=== 6. klik Nomor HP ===")
    for sel in ('text=Nomor HP', 'text=Nomor Telepon', 'text=Ubah Nomor',
                'a[href*="phone"]', 'text=Ubah', 'text=Ganti'):
        try:
            l = pg.locator(sel)
            if l.count() and l.first.is_visible():
                l.first.click(timeout=4500, force=True)
                log(f"  ✅ {sel}")
                pg.wait_for_timeout(9000)
                modals(pg)
                break
        except Exception:
            pass

    pg.wait_for_timeout(4000)
    log(f"  url: {pg.url[:90]}")
    b2 = pg.evaluate("()=>document.body.innerText.slice(0,700)")
    log(f"  body: {b2[:400].replace(chr(10),' | ')}")
    pg.screenshot(path="/root/shopee-verify/SAP_phone.png", full_page=True)

    # === 7. isi nomor ===
    log("\n=== 7. isi nomor baru ===")
    for sel in ('input[type="tel"]', 'input[name*="phone"]',
                'input[placeholder*="omor"]'):
        try:
            l = pg.locator(sel)
            if l.count() and l.first.is_visible():
                l.first.click(force=True)
                l.first.fill("")
                for ch in NEWPHONE:
                    l.first.type(ch, delay=55)
                log(f"  ✅ {NEWPHONE} -> {sel}")
                pg.wait_for_timeout(2500)
                for btn in ('button:has-text("Lanjut")', 'button:has-text("Kirim")',
                            'button:has-text("Selanjutnya")', 'button:has-text("Konfirmasi")'):
                    try:
                        b = pg.locator(btn)
                        if b.count() and b.first.is_visible():
                            b.first.click(timeout=4500, force=True)
                            log(f"  ✅ klik {btn}")
                            pg.wait_for_timeout(9000)
                            modals(pg)
                            break
                    except Exception:
                        pass
                break
        except Exception:
            pass

    pg.wait_for_timeout(5000)
    log(f"\n  url akhir: {pg.url[:90]}")
    b3 = pg.evaluate("()=>document.body.innerText.slice(0,900)")
    log(f"  body: {b3[:500].replace(chr(10),' | ')}")
    pg.screenshot(path="/root/shopee-verify/SAP_final.png", full_page=True)

    cks = ctx.cookies()
    open("/root/shopee-verify/ck_sap.txt", "w").write(
        "; ".join(f"{c['name']}={c['value']}" for c in cks))

    json.dump({"url": pg.url, "net": net[-90:], "probes": results,
               "body": b3[:1500]},
              open("/root/shopee-verify/SAP.json", "w"), indent=1)
    br.close()

log("\n=== SELESAI ===")
