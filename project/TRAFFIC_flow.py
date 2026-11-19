"""TRAFFIC_flow.py — /verify/traffic (BUKAN /verify/captcha).

Temuan: setelah cart/mini 90309999, SDK redirect ke
  /verify/traffic/error?home_url=...&is_logged_in=...

Yang benar: /verify/traffic?<params> -> render captcha
  (dari ivs_js/078.js: S="/verify/traffic", X="/verify/traffic/error")

Param dari es():
  tracking_id, is_logged_in, home_url, type(error_type),
  app_key, scene, client_id, redirect_type, next,
  should_replace_history, anti_bot_tracking_id

Strategi: trigger cart/mini -> tangkap redirect URL SDK ->
ganti /traffic/error jadi /traffic -> buka -> captcha render.
"""
import json, sys, time, urllib.parse

sys.path.insert(0, "/root/shopee-farm")

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1553.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283191104601"
BUDGET = int(sys.argv[3]) if len(sys.argv) > 3 else 900

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    try:
        open("/root/shopee-verify/TRAFFIC.log", "a").write(m + "\n")
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
    V6 = None
    KEY = ""
    SOLVER = False

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
    net.append({"u": short, "s": r.status, "b": b[:1200]})
    if "captcha/generate" in short:
        log(f"  gen: {b[:120]}")
    if "captcha/verify" in short:
        log(f"  VERIFY: {r.status} {b[:160]}")
    if "ivs/" in short or "change_phone" in short or "otp/" in short:
        log(f"  NET {r.status} {short} :: {b[:110]}")


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
    for fn in ("solve_image_crawl", "solve_image_drag", "solve_puzzle_slide"):
        try:
            f = getattr(V6, fn, None)
            if not f:
                continue
            r = f(pg, KEY)
            log(f"  {fn} -> {r}")
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

    log("=== 1. buka home ===")
    for a in range(5):
        try:
            pg.goto("https://shopee.co.id/", wait_until="domcontentloaded",
                    timeout=60000)
        except Exception:
            time.sleep(3)
            continue
        pg.wait_for_timeout(7000)
        modals(pg)
        log(f"  [{a+1}] {pg.url.split('shopee.co.id')[-1][:55]}")
        if "/verify/" not in pg.url:
            break
        pg.wait_for_timeout(3000)

    # === 2. trigger cart/mini, tangkap redirect ===
    log("\n=== 2. trigger + tangkap redirect ===")
    captured = None
    for a in range(6):
        try:
            r = pg.evaluate("""async ()=>{
              try {
                const res = await fetch('/api/v4/cart/mini?need_buyer_dp_info=1',
                  {credentials:'include'});
                const j = await res.json();
                return {s:res.status, err:j.error};
              } catch(e){ return {ex:String(e).slice(0,40)}; }
            }""")
            log(f"  cart #{a+1}: {r}")
        except Exception as e:
            log(f"  err {str(e)[:40]}")
        pg.wait_for_timeout(6000)
        if "/verify/traffic" in pg.url:
            captured = pg.url
            log(f"  ★ REDIRECT: {pg.url[:140]}")
            break
        if "/verify/" in pg.url:
            captured = pg.url
            log(f"  ★ verify: {pg.url[:140]}")
            break

    # === 3. BUKA /verify/traffic dengan param lengkap ===
    log("\n=== 3. buka /verify/traffic ===")
    ck_map = {c["name"]: c["value"] for c in cookies}
    cid = ck_map.get("SPC_CLIENTID", "")
    trk = ""
    if captured:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(captured).query)
        trk = (q.get("tracking_id") or q.get("anti_bot_tracking_id") or [""])[0]
    log(f"  tracking dari redirect: {len(trk)}B")

    params = {
        "is_initial": "true",
        "app_key": "f9ffc83459897a13dd14c537e84b1753",
        "scene": "crawler_item",
        "client_id": cid,
        "redirect_type": "1",
        "next": "https://shopee.co.id/",
        "should_replace_history": "true",
        "is_logged_in": "true",
        "home_url": "https://shopee.co.id",
    }
    if trk:
        params["anti_bot_tracking_id"] = trk
        params["tracking_id"] = trk

    url = "https://shopee.co.id/verify/traffic?" + urllib.parse.urlencode(params)
    log(f"  url len {len(url)}")
    try:
        pg.goto(url, wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        log(f"  goto err {str(e)[:50]}")
    pg.wait_for_timeout(9000)
    modals(pg)

    st = pg.evaluate("""()=>({
      canv: document.querySelectorAll('canvas').length,
      nc: !!document.querySelector('#NEW_CAPTCHA'),
      txt: (document.body.innerText||'').slice(0,200)
    })""")
    log(f"  state: {st}")
    pg.screenshot(path="/root/shopee-verify/TR_now.png", full_page=False)

    # === 4. solve kalau captcha ada ===
    if st.get("canv", 0) > 0 or "captcha" in pg.url:
        log("\n=== 4. SOLVE ===")
        for i in range(5):
            if time.time() - T0 > BUDGET - 200:
                break
            ok = solve(pg)
            pg.wait_for_timeout(7000)
            cur = pg.url
            log(f"  [{i+1}] url={cur.split('shopee.co.id')[-1][:55]}")
            if "/verify/" not in cur:
                log("  ✅ LOLOS!")
                break
    else:
        # coba route traffic/error -> traffic langsung
        log("  tidak ada canvas. coba /verify/traffic tanpa error path")
        try:
            u2 = "https://shopee.co.id/verify/traffic?" + urllib.parse.urlencode(
                {k: v for k, v in params.items() if k != "anti_bot_tracking_id"})
            pg.goto(u2, wait_until="domcontentloaded", timeout=50000)
            pg.wait_for_timeout(8000)
            st2 = pg.evaluate("()=>({canv:document.querySelectorAll('canvas').length, txt:(document.body.innerText||'').slice(0,150)})")
            log(f"  state2: {st2}")
            if st2.get("canv", 0) > 0:
                solve(pg)
                pg.wait_for_timeout(6000)
        except Exception as e:
            log(f"  err {str(e)[:50]}")

    pg.screenshot(path="/root/shopee-verify/TR_after.png", full_page=True)
    log(f"\n  url akhir: {pg.url[:100]}")
    log(f"  cookie -> simpan")
    cks = ctx.cookies()
    open("/root/shopee-verify/ck_traffic.txt", "w").write(
        "; ".join(f"{c['name']}={c['value']}" for c in cks))

    json.dump({"url": pg.url, "net": net[-80:], "captured": captured},
              open("/root/shopee-verify/TR.json", "w"), indent=1)
    br.close()

log("\n=== SELESAI ===")
