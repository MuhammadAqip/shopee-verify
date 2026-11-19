"""cp_ui3.py — kerja dari halaman yang RENDER, apapun path-nya.

Temuan: dengan IP baru, /user/account/profile render dengan username.
Script lama loop karena cek '/user/account/settings' exact.

Fix:
  - Terima /user/account/* yang bukan captcha & body > 100 char
  - Navigasi LANGSUNG ke /user/account/settings via SPA (bukan reload)
  - Kalau kena captcha, tunggu + retry
  - Cari & klik Nomor HP
"""
import json, sys, time

sys.path.insert(0, "/root/shopee-farm")

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1553.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283191104601"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
OUT = "/root/shopee-verify/cp_ui3.json"


def log(*a):
    print(*a, flush=True)


ck = open(CK).read().strip()
cookies = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p
           for k, v in [p.strip().split("=", 1)]]

try:
    import shopee_v6 as V6
    KEY = open("/root/shopee-farm/bot_key.txt").read().strip()
except Exception:
    V6 = None
    KEY = ""

from playwright.sync_api import sync_playwright

net = []


def onresp(r):
    u = r.url
    if "/api/v4/" in u and any(k in u for k in
                               ("ivs", "change_phone", "otp", "captcha",
                                "settings", "account")):
        try:
            b = r.text()[:1200]
        except Exception:
            b = ""
        net.append({"u": u.split("shopee.co.id")[-1][:90], "s": r.status, "b": b})


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

    def klik_bahasa():
        for sel in ('text=Bahasa Indonesia', 'text=English'):
            try:
                loc = pg.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    loc.first.click(timeout=3000, force=True)
                    pg.wait_for_timeout(3000)
                    return True
            except Exception:
                pass
        return False

    def ok_page():
        cur = pg.url
        if "captcha" in cur:
            return False
        body = pg.evaluate("()=>document.body.innerText")
        return len(body.strip()) > 100 and "Verifikasi gagal" not in body

    log("=== 1. buka shopee dulu (jangan langsung settings) ===")
    for a in range(8):
        try:
            pg.goto("https://shopee.co.id/", wait_until="domcontentloaded",
                    timeout=60000)
        except Exception as e:
            log(f"  err {str(e)[:45]}")
            time.sleep(3)
            continue
        pg.wait_for_timeout(9000)
        klik_bahasa()
        if ok_page():
            log(f"  ✅ homepage OK: {pg.url[:60]}")
            break
        log(f"  [{a+1}] {pg.url.split('shopee.co.id')[-1][:50]}")
        if "captcha" in pg.url and V6 and KEY:
            try:
                V6.solve_image_crawl(pg, KEY)
            except Exception:
                pass
        pg.wait_for_timeout(4000)

    # === 2. navigasi via SPA (client-side, tidak reload) ===
    log("\n=== 2. navigasi SPA ke settings ===")
    nav = pg.evaluate("""async () => {
      try {
        // coba history push + popstate
        history.pushState({}, '', '/user/account/settings');
        window.dispatchEvent(new PopStateEvent('popstate'));
        await new Promise(r=>setTimeout(r,2000));
        return {ok:true, url:location.pathname};
      } catch(e) { return {err:String(e).slice(0,60)}; }
    }""")
    log(f"  pushState: {nav}")
    pg.wait_for_timeout(6000)
    log(f"  url: {pg.url.split('shopee.co.id')[-1][:70]}")
    body = pg.evaluate("()=>document.body.innerText.slice(0,300)")
    log(f"  body: {body[:200].replace(chr(10),' | ')}")

    # === 3. kalau belum, klik menu akun ===
    if not ok_page() or "settings" not in pg.url:
        log("\n=== 3. klik menu akun via UI ===")
        for sel in ('text=Akun Saya', 'text=Pengaturan', 'text=Akun',
                    'a[href*="/user/account"]', 'text=uh4mfv6x92'):
            try:
                loc = pg.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    loc.first.click(timeout=4000, force=True)
                    log(f"  klik {sel!r}")
                    pg.wait_for_timeout(5000)
                    klik_bahasa()
                    if "settings" in pg.url:
                        break
            except Exception:
                pass

    log(f"\n  url: {pg.url[:80]}")
    body = pg.evaluate("()=>document.body.innerText.slice(0,700)")
    log(f"  body: {body[:350].replace(chr(10),' | ')}")
    pg.screenshot(path="/root/shopee-verify/ui3_now.png", full_page=True)

    # === 4. cari Nomor HP ===
    log("\n=== 4. cari elemen nomor HP ===")
    els = pg.evaluate("""()=>Array.from(document.querySelectorAll('a,button,div,span,li,tr'))
      .map(e=>({t:(e.innerText||'').trim().slice(0,45),
                h:e.getAttribute('href')||''}))
      .filter(x=>x.t && x.t.length<55).slice(0,100)""")
    hits = [e for e in els if any(k in e["t"].lower()
                                  for k in ("nomor", "phone", "hp", "ubah", "ganti"))]
    log(f"  {len(hits)} kandidat:")
    for e in hits[:15]:
        log(f"    {e['t']!r} -> {e['h'][:40]}")

    if hits:
        for sel in ('text=Nomor HP', 'text=Nomor Telepon', 'text=Ubah Nomor',
                    'a[href*="phone"]', 'text=Ubah', 'text=Ganti'):
            try:
                loc = pg.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    loc.first.click(timeout=5000, force=True)
                    log(f"  ✅ klik {sel!r}")
                    pg.wait_for_timeout(8000)
                    break
            except Exception:
                pass

    pg.wait_for_timeout(4000)
    log(f"\n  url akhir: {pg.url[:90]}")
    body2 = pg.evaluate("()=>document.body.innerText.slice(0,900)")
    log(f"  body: {body2[:400].replace(chr(10),' | ')}")
    pg.screenshot(path="/root/shopee-verify/ui3_final.png", full_page=True)

    # === 5. signature ===
    sig = None
    for n in net:
        if "token/verify" in n["u"] and '"signature"' in n["b"]:
            try:
                j = json.loads(n["b"])
                sig = (j.get("data") or {}).get("signature")
            except Exception:
                pass

    log(f"\n=== network {len(net)} rec | sig={'✅ %dB' % len(sig) if sig else '❌'} ===")
    for n in net[-15:]:
        log(f"  {n['s']} {n['u']}")

    json.dump({"url": pg.url, "net": net, "sig": sig,
               "body": body2[:1500], "hits": hits[:20]},
              open(OUT, "w"), indent=1)
    log(f"-> {OUT}")
    br.close()

log("\n=== SELESAI ===")
