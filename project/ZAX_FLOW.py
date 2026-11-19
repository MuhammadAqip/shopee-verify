"""ZAX_FLOW.py — buka /user/account/phone dengan UI click, tangkap semua network."""
import json, sys, time
CK = sys.argv[1] if len(sys.argv) > 1 else "ck_zax.txt"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):3d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/ZF.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright

NET = []


def onresp(r):
    u = r.url
    if "/api/v4/" not in u:
        return
    sh = u.split("shopee.co.id")[-1].split("?")[0][:66]
    try:
        b = r.text()
    except Exception:
        b = ""
    NET.append({"u": sh, "s": r.status, "b": b[:1200]})
    log(f"  {r.status} {sh} :: {b[:130]}")
    if "captcha" in sh:
        try:
            h = dict(r.request.headers)
            for k in [x for x in h if x.lower().startswith(("x-", "af-", "sec-"))][:8]:
                log(f"       H {k}: {str(h[k])[:60]}")
        except Exception:
            pass


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

    log("=== home ===")
    try:
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    pg.wait_for_timeout(8000)
    for sel in ('button:has-text("Setuju")', 'button:has-text("Bahasa Indonesia")'):
        try:
            l = pg.locator(sel)
            if l.count() and l.first.is_visible():
                l.first.click(timeout=2500, force=True)
                pg.wait_for_timeout(1500)
                break
        except Exception:
            pass
    pg.wait_for_timeout(4000)

    log("=== scroll + mouse natural ===")
    for i in range(5):
        pg.mouse.move(400 + i * 80, 300 + i * 60, steps=10)
        pg.wait_for_timeout(600)
        pg.mouse.wheel(0, 400)
        pg.wait_for_timeout(800)

    log("\n=== klik menu akun ===")
    clicked = pg.evaluate("""()=>{
      const cands=[...document.querySelectorAll('a,div,span')].filter(e=>{
        const t=(e.innerText||'').trim().toLowerCase();
        return (t==='akun saya'||t==='my account'||t==='pengaturan'||t==='profil') && t.length<20;
      });
      if(!cands.length) return null;
      cands[0].click();
      return cands[0].innerText.trim();
    }""")
    log(f"  clicked: {clicked}")
    pg.wait_for_timeout(9000)
    log(f"  url: {pg.url[:110]}")

    st = pg.evaluate("""()=>({
      url:location.href,
      n:[...document.querySelectorAll('canvas')].length,
      txt:(document.body.innerText||'').slice(0,300)
    })""")
    log(f"  canvas={st['n']}")
    log(f"  txt: {st['txt'][:200].replace(chr(10),' | ')}")

    log("\n=== cari tombol ubah nomor ===")
    cands = pg.evaluate("""()=>{
      const items=[...document.querySelectorAll('a,div,span,button')].filter(e=>{
        const t=(e.innerText||'').trim().toLowerCase();
        return /ubah|change|nomor|phone|telepon/.test(t) && t.length<40;
      }).slice(0,10);
      return items.map(e=>({t:(e.innerText||'').trim().slice(0,40),tag:e.tagName}));
    }""")
    log(f"  kandidat: {cands}")

    # kalau ada, klik
    if cands:
        r = pg.evaluate("""()=>{
          const items=[...document.querySelectorAll('a,div,span,button')].filter(e=>{
            const t=(e.innerText||'').trim().toLowerCase();
            return /ubah|change|nomor|phone|telepon/.test(t) && t.length<40;
          });
          if(items.length){items[0].click();return items[0].innerText.trim();}
          return null;
        }""")
        log(f"  clicked2: {r}")
        pg.wait_for_timeout(12000)
        st2 = pg.evaluate("""()=>({url:location.href,
          n:[...document.querySelectorAll('canvas')].length,
          txt:(document.body.innerText||'').slice(0,250)})""")
        log(f"  url2: {st2['url'][:110]}")
        log(f"  canvas2={st2['n']} txt2: {st2['txt'][:170].replace(chr(10),' | ')}")

    json.dump({"net": NET[-50:]}, open("/root/shopee-verify/ZF.json", "w"), indent=1)
    pg.screenshot(path="/root/shopee-verify/ZAX_flow.png", full_page=True)
    br.close()

log("\n=== SELESAI ===")
