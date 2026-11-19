"""RENDER_FIX.py — panggil SDK dengan signature BENAR.

Dari bundle:
  function(n,t){ (0,O1.XX)(O1.n(m0,t), n) }
    n = container (DOM element / string selector)
    t = config object (options)

Jadi: renderCaptchaPopupDesktop(container, config)

Config kemungkinan: {appKey, scene, antiBotTrackingId, clientId, onSuccess, ...}
"""
import json, sys, time

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_fresh_1659.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6285796160652"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
SADKEY = open("/root/shopee-farm/bot_key.txt").read().strip()
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):3d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/RF.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright
import requests

net = []
TID = {"v": ""}


def onresp(r):
    u = r.url
    if "/api/v4/" not in u:
        return
    short = u.split("shopee.co.id")[-1].split("?")[0][:70]
    try:
        b = r.text()
    except Exception:
        b = ""
    net.append({"u": short, "s": r.status, "b": b[:1800]})
    if "captcha" in short or "otp" in short:
        log(f"  NET {r.status} {short[:46]} :: {b[:100]}")


def state(pg):
    return pg.evaluate("""()=>{
      const cs=[...document.querySelectorAll('canvas')].map(c=>{
        const r=c.getBoundingClientRect();
        return {w:Math.round(r.width),h:Math.round(r.height),
                x:Math.round(r.x),y:Math.round(r.y)};
      }).filter(o=>o.w>15&&o.h>8);
      return {n:cs.length, cs, txt:(document.body.innerText||'').slice(0,200)};
    }""")


def grab(pg):
    return pg.evaluate("""()=>{
      const out={ok:false};
      const all=[...document.querySelectorAll('canvas')].map(c=>{
        const r=c.getBoundingClientRect();
        return {el:c,w:r.width,h:r.height,x:r.x,y:r.y};
      }).filter(o=>o.w>15&&o.h>8);
      if(!all.length) return out;
      all.sort((a,b)=>(b.w*b.h)-(a.w*a.h));
      const big=all[0], small=all.slice(1).sort((a,b)=>(a.w*a.h)-(b.w*b.h))[0];
      try{out.puz=big.el.toDataURL('image/png');}catch(e){}
      if(small){try{out.pc=small.el.toDataURL('image/png');}catch(e){}}
      out.rect={x:big.x,y:big.y,w:big.w,h:big.h};
      out.n=all.length; out.ok=!!(out.puz&&out.puz.length>4000);
      return out;
    }""")


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

    log("=== 1. home -> tracking ===")
    try:
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    pg.wait_for_timeout(9000)
    for sel in ('button:has-text("Setuju")', 'text=Bahasa Indonesia'):
        try:
            l = pg.locator(sel)
            if l.count() and l.first.is_visible():
                l.first.click(timeout=2000, force=True)
                pg.wait_for_timeout(1200)
        except Exception:
            pass

    for a in range(3):
        try:
            r = pg.evaluate("""async ()=>{
              try{const res=await fetch('/api/v4/cart/mini?need_buyer_dp_info=1',
                {credentials:'include'});const j=await res.json();
                return {err:j.error, six:j['6']};}catch(e){return {ex:String(e).slice(0,40)}}
            }""")
            six = r.get("six") or {}
            if isinstance(six, dict) and six.get("0"):
                TID["v"] = six["0"]
                log(f"  ★ tracking {len(TID['v'])}B")
                break
        except Exception:
            pass
        pg.wait_for_timeout(4000)

    log("\n=== 2. /verify/captcha -> siapkan container ===")
    try:
        pg.goto("https://shopee.co.id/verify/captcha", wait_until="domcontentloaded",
                timeout=55000)
    except Exception:
        pass
    pg.wait_for_timeout(12000)

    client_id = next((c["value"] for c in cookies if c["name"] == "SPC_CLIENTID"), "")

    # buat container + panggil SDK dengan signature benar (container, config)
    log("\n=== 3. renderCaptchaPopupDesktop(container, config) ===")
    r = pg.evaluate("""(args)=>{
      const {tid, clientId} = args;
      try{
        if (typeof window.renderCaptchaPopupDesktop !== 'function')
          return {err:'no_fn'};
        // buat container overlay
        let box = document.getElementById('__capbox');
        if (!box){
          box = document.createElement('div');
          box.id='__capbox';
          box.style.cssText='position:fixed;top:80px;left:50%;transform:translateX(-50%);'
            +'z-index:2147483647;background:#fff;padding:8px;border-radius:8px;'
            +'box-shadow:0 4px 24px rgba(0,0,0,.25);';
          document.body.appendChild(box);
        }
        const cfg = {
          appKey: 'TSS.PC',
          scene: 'crawler_item',
          antiBotTrackingId: tid,
          anti_bot_tracking_id: tid,
          clientId: clientId,
          client_id: clientId,
          shouldReplaceHistory: false,
          verificationPageHost: location.origin,
          onSuccess: function(res){ window.__capOK = res ? JSON.stringify(res).slice(0,900) : 'ok'; },
          onFail: function(e){ window.__capFail = String(e).slice(0,300); },
          onClose: function(){ window.__capClose = true; }
        };
        window.renderCaptchaPopupDesktop(box, cfg);
        return {ok:true, boxId: box.id};
      }catch(e){ return {err:String(e).slice(0,160)}; }
    }""", {"tid": TID["v"], "clientId": client_id})
    log(f"  {r}")

    for i in range(12):
        pg.wait_for_timeout(4000)
        st = state(pg)
        cb = pg.evaluate("()=>({ok:window.__capOK, fail:window.__capFail, close:window.__capClose})")
        log(f"  [{i*4+4:2d}s] canvas={st['n']} cb={cb}")
        if st["n"] or cb.get("fail"):
            break

    st = state(pg)
    log(f"\n  canvas={st['n']} {st['cs']}")
    log(f"  txt: {st.get('txt', '')[:130].replace(chr(10), ' | ')}")
    pg.screenshot(path="/root/shopee-verify/RF_box.png", full_page=False)

    # === 4. SOLVE ===
    if st["n"]:
        for att in range(3):
            g = grab(pg)
            if not g.get("ok"):
                pg.wait_for_timeout(3000)
                continue
            log(f"\n=== solve#{att+1} puz={len(g['puz'])}B pc={len(g.get('pc') or '')}B ===")
            prop = None
            try:
                r2 = requests.post("https://www.sadcaptcha.com/api/v1/puzzle",
                                   params={"licenseKey": SADKEY},
                                   json={"puzzleImageB64": g["puz"].split(",", 1)[1],
                                         "pieceImageB64": (g.get("pc") or "").split(",", 1)[1]
                                         if g.get("pc") else ""}, timeout=60)
                log(f"  sad {r2.status_code} {r2.text[:80]}")
                if r2.status_code == 200:
                    prop = r2.json().get("slideXProportion")
            except Exception as e:
                log(f"  err {str(e)[:50]}")
            if prop is None:
                continue
            log(f"  ★ prop={prop}")
            h = pg.evaluate("""()=>{
              const out=[];
              for(const e of document.querySelectorAll('div,span,button,svg')){
                const r=e.getBoundingClientRect();
                if(r.width<22||r.width>95||r.height<22||r.height>95) continue;
                if(e.querySelector('canvas')) continue;
                out.push({x:r.x+r.width/2,y:r.y+r.height/2,w:r.width});
              }
              out.sort((a,b)=>(b.y-a.y)||(a.x-b.x));
              return out.slice(0,6);
            }""")
            log(f"  handle: {[(round(x['x']),round(x['y'])) for x in h[:4]]}")
            if not h:
                continue
            hx, hy = h[0]["x"], h[0]["y"]
            dist = prop * (g["rect"]["w"] or 280)
            try:
                pg.mouse.move(hx, hy)
                pg.wait_for_timeout(250)
                pg.mouse.down()
                pg.wait_for_timeout(350)
                for i in range(1, 24):
                    p = i / 24
                    e = p * p * (3 - 2 * p)
                    pg.mouse.move(hx + e * dist, hy - 3 * min(1, p), steps=1)
                    pg.wait_for_timeout(22 + (i % 4) * 9)
                pg.wait_for_timeout(450)
                pg.mouse.move(hx + dist + 2, hy - 3)
                pg.wait_for_timeout(350)
                pg.mouse.up()
                log("  ✅ released")
            except Exception as e:
                log(f"  drag err {str(e)[:50]}")
            pg.wait_for_timeout(10000)
            cb = pg.evaluate("()=>({ok:window.__capOK, fail:window.__capFail})")
            log(f"  callback: {cb}")
            st2 = state(pg)
            log(f"  -> canvas={st2['n']}")
            pg.screenshot(path=f"/root/shopee-verify/RF_s{att+1}.png", full_page=False)
            if cb.get("ok") or st2["n"] == 0:
                log("  🎉🎉 CAPTCHA LOLOS")
                break

    pg.screenshot(path="/root/shopee-verify/RF_final.png", full_page=True)
    json.dump({"net": net[-40:], "tid": TID["v"][:120]},
              open("/root/shopee-verify/RF.json", "w"), indent=1)
    br.close()

log("\n=== SELESAI ===")
