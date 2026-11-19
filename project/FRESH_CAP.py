"""FRESH_CAP.py — ambil tracking FRESH di browser, generate captcha, solve, OTP.

Kenapa: get_config dari Python = 31600000 (butuh x-sap). Di browser = error 0.
Maka: browser buka /verify/captcha, hook ambil tracking_id dari response get_config,
lalu SIMULASI generate dari page-context (SDK sign otomatis).

Kalau generate tetap Block, fallback: solve captcha yang SDK render (kalau ada canvas),
lalu submit lewat page-context (SDK yang kirim verify + security_data).
"""
import json, sys, time, base64, os

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_fresh_1659.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6285796160652"
BUDGET = int(sys.argv[3]) if len(sys.argv) > 3 else 480

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
SADKEY = open("/root/shopee-farm/bot_key.txt").read().strip()
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):3d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/FRESH.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright
import requests

net = []
TRK = {"v": ""}


def onresp(r):
    u = r.url
    if "/api/v4/" not in u:
        return
    short = u.split("shopee.co.id")[-1].split("?")[0][:70]
    try:
        b = r.text()
    except Exception:
        b = ""
    net.append({"u": short, "s": r.status, "b": b[:1500]})
    if "get_config" in short and b:
        try:
            j = json.loads(b)
            if j.get("tracking_id"):
                TRK["v"] = j["tracking_id"]
                log(f"  ★ TRACKING FRESH {len(TRK['v'])}B")
                open("/root/shopee-verify/TRK_FRESH.txt", "w").write(TRK["v"])
        except Exception:
            pass
    if "captcha" in short or "otp" in short:
        log(f"  NET {r.status} {short} :: {b[:120]}")


def modals(pg):
    for sel in ('button:has-text("Setuju")', 'text=Setuju',
                'text=Bahasa Indonesia'):
        try:
            l = pg.locator(sel)
            if l.count() and l.first.is_visible():
                l.first.click(timeout=2000, force=True)
                pg.wait_for_timeout(1500)
                return True
        except Exception:
            pass
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

    log("=== 1. buka /verify/captcha -> ambil tracking fresh ===")
    for a in range(3):
        try:
            pg.goto("https://shopee.co.id/verify/captcha",
                    wait_until="domcontentloaded", timeout=55000)
        except Exception:
            time.sleep(3)
            continue
        pg.wait_for_timeout(10000)
        modals(pg)
        log(f"  [{a+1}] {pg.url.split('shopee.co.id')[-1][:55]}")
        if TRK["v"]:
            break

    if not TRK["v"]:
        log("  ⚠ get_config belum muncul, trigger cart/mini")
        try:
            pg.evaluate("""async ()=>{try{await fetch('/api/v4/cart/mini?need_buyer_dp_info=1',
                {credentials:'include'});}catch(e){}}""")
        except Exception:
            pass
        pg.wait_for_timeout(9000)

    log(f"\n=== tracking: {len(TRK['v'])}B ===")
    if not TRK["v"]:
        log("  ❌ tidak dapat tracking")
        json.dump({"net": net[-40:]}, open("/root/shopee-verify/FRESH.json", "w"), indent=1)
        br.close()
        sys.exit(1)

    # === 2. GENERATE dari page-context (SDK sign otomatis) ===
    log("\n=== 2. generate dari page-context ===")
    gen = pg.evaluate("""async (args)=>{
      const {trk, phone} = args;
      const body = {app_key:'TSS.PC', scene:'signup', captcha_type:1,
                    image_version:'', client_id:'',
                    captcha_extra_info:{tracking_id: trk}, captcha_id:''};
      const out = {attempts: []};
      // coba langsung plain (mungkin SDK auto-encrypt via interceptor)
      for (const path of ['/api/v4/anti_fraud/captcha/generate']) {
        try {
          const res = await fetch(path, {method:'POST', credentials:'include',
            headers:{'content-type':'application/json'},
            body: JSON.stringify(body)});
          const t = await res.text();
          out.attempts.push({path, s:res.status, b:t.slice(0,600)});
        } catch(e){ out.attempts.push({path, ex:String(e).slice(0,60)}); }
      }
      return out;
    }""", {"trk": TRK["v"], "phone": NEWPHONE})
    for x in gen.get("attempts", []):
        log(f"  {x.get('path')} s={x.get('s')} {x.get('b', '')[:220]}")

    # === 3. cek canvas ===
    pg.wait_for_timeout(6000)
    st = pg.evaluate("""()=>{
      const cs=[...document.querySelectorAll('canvas')].map(c=>{
        const r=c.getBoundingClientRect(); return {w:r.width,h:r.height,x:r.x,y:r.y};
      }).filter(o=>o.w>20&&o.h>10);
      return {n:cs.length, cs:cs.slice(0,5),
              txt:(document.body.innerText||'').slice(0,180)};
    }""")
    log(f"\n=== 3. canvas={st.get('n')} ===")
    log(f"  {st.get('cs')}")
    log(f"  txt: {st.get('txt', '')[:140].replace(chr(10), ' | ')}")
    pg.screenshot(path="/root/shopee-verify/FRESH_page.png", full_page=False)

    json.dump({"net": net[-60:], "trk": TRK["v"][:200],
               "gen": gen, "canvas": st},
              open("/root/shopee-verify/FRESH.json", "w"), indent=1)
    cks = ctx.cookies()
    open("/root/shopee-verify/ck_fresh_out.txt", "w").write(
        "; ".join(f"{c['name']}={c['value']}" for c in cks))
    br.close()

log("\n=== SELESAI ===")
