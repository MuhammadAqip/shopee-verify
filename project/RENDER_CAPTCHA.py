"""RENDER_CAPTCHA.py — panggil window.renderCaptchaPopupDesktop langsung.

Temuan: SDK captcha 50017751 expose:
  window.renderCaptchaDesktop(n, t)
  window.renderCaptchaPopupDesktop(n, t)

Kalau dipanggil dengan antiBotTrackingId + clientId + appKey yang benar,
captcha render sendiri -- dan SDK yang handle verify_v2 (signature, encryption).

Alur:
  1. buka /verify/captcha
  2. tunggu window.renderCaptchaPopupDesktop ada
  3. panggil dengan argumen dari cart/mini field 6.0
  4. tunggu canvas muncul
  5. solve SadCaptcha + drag
  6. OTP
"""
import json, sys, time

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
    open("/root/shopee-verify/RC.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright
import requests

TID = {"v": ""}
net = []


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
    if "captcha" in short or "otp" in short:
        log(f"  NET {r.status} {short[:48]} :: {b[:100]}")


def state(pg):
    return pg.evaluate("""()=>{
      const cs=[...document.querySelectorAll('canvas')].map(c=>{
        const r=c.getBoundingClientRect();
        return {w:Math.round(r.width),h:Math.round(r.height),
                x:Math.round(r.x),y:Math.round(r.y)};
      }).filter(o=>o.w>15&&o.h>8);
      return {n:cs.length, cs,
              txt:(document.body.innerText||'').slice(0,200),
              hasRender: typeof window.renderCaptchaPopupDesktop==='function'};
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
      const big=all[0];
      const small=all.slice(1).sort((a,b)=>(a.w*a.h)-(b.w*b.h))[0];
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

    log("=== 1. home + cart/mini (ambil tracking) ===")
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

    TID["v"] = ""
    for a in range(3):
        try:
            r = pg.evaluate("""async ()=>{
              try{const res=await fetch('/api/v4/cart/mini?need_buyer_dp_info=1',
                {credentials:'include'});const j=await res.json();
                return {err:j.error, t:j['0'], six:j['6']};}
              catch(e){return {ex:String(e).slice(0,40)}}
            }""")
            six = r.get("six") or {}
            log(f"  cart#{a+1} err={r.get('err')} type={r.get('t')} six={list(six.keys()) if isinstance(six, dict) else six}")
            if isinstance(six, dict) and six.get("0"):
                TID["v"] = six["0"]
                log(f"  ★ tracking {len(TID['v'])}B")
                break
        except Exception:
            pass
        pg.wait_for_timeout(4000)

    # === 2. buka /verify/captcha, tunggu SDK ===
    log("\n=== 2. /verify/captcha + tunggu SDK ===")
    try:
        pg.goto("https://shopee.co.id/verify/captcha", wait_until="domcontentloaded",
                timeout=55000)
    except Exception:
        pass

    have = False
    for i in range(12):
        pg.wait_for_timeout(4000)
        st = state(pg)
        log(f"  [{i*4+4:2d}s] render={st.get('hasRender')} canvas={st['n']}")
        if st.get("hasRender"):
            have = True
            break

    if not have:
        log("  ❌ SDK renderCaptchaPopupDesktop tidak tersedia")
        pg.screenshot(path="/root/shopee-verify/RC_fail.png", full_page=False)
        br.close()
        sys.exit(1)

    # === 3. PANGGIL SDK ===
    log("\n=== 3. panggil renderCaptchaPopupDesktop ===")
    client_id = ""
    for c in cookies:
        if c["name"] == "SPC_CLIENTID":
            client_id = c["value"]

    variants = [
        {"antiBotTrackingId": TID["v"], "clientId": client_id,
         "appKey": "TSS.PC", "scene": "crawler_item",
         "shouldReplaceHistory": False},
        {"anti_bot_tracking_id": TID["v"], "client_id": client_id,
         "app_key": "TSS.PC", "scene": "crawler_item"},
        {"antiBotTrackingId": TID["v"]},
        {"anti_bot_tracking_id": TID["v"]},
        TID["v"],
    ]

    for vi, arg in enumerate(variants):
        r = pg.evaluate("""(arg)=>{
          try{
            if (typeof window.renderCaptchaPopupDesktop !== 'function')
              return {err:'no_fn'};
            window.renderCaptchaPopupDesktop(arg, '');
            return {ok:true, arg: JSON.stringify(arg).slice(0,120)};
          }catch(e){ return {err:String(e).slice(0,120)}; }
        }""", arg)
        log(f"  [{vi+1}] {r}")
        pg.wait_for_timeout(6000)
        st = state(pg)
        if st["n"]:
            log(f"  ★ CANVAS MUNCUL: {st['cs']}")
            break

    pg.wait_for_timeout(5000)
    st = state(pg)
    log(f"\n  canvas={st['n']} {st['cs']}")
    log(f"  txt: {st.get('txt', '')[:130].replace(chr(10), ' | ')}")
    pg.screenshot(path="/root/shopee-verify/RC_after.png", full_page=False)

    # === 4. SOLVE ===
    if st["n"]:
        for att in range(3):
            g = grab(pg)
            if not g.get("ok"):
                log("  grab gagal")
                pg.wait_for_timeout(3000)
                continue
            log(f"\n=== solve#{att+1} puz={len(g['puz'])}B pc={len(g.get('pc') or '')}B ===")
            try:
                r = requests.post("https://www.sadcaptcha.com/api/v1/puzzle",
                                  params={"licenseKey": SADKEY},
                                  json={"puzzleImageB64": g["puz"].split(",", 1)[1],
                                        "pieceImageB64": (g.get("pc") or "").split(",", 1)[1]
                                        if g.get("pc") else ""}, timeout=60)
                log(f"  sad {r.status_code} {r.text[:80]}")
                prop = r.json().get("slideXProportion") if r.status_code == 200 else None
            except Exception as e:
                log(f"  err {str(e)[:50]}")
                prop = None
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
            st2 = state(pg)
            log(f"  -> canvas={st2['n']}")
            pg.screenshot(path=f"/root/shopee-verify/RC_s{att+1}.png", full_page=False)
            if st2["n"] == 0:
                log("  🎉 captcha hilang — LOLOS")
                break

    # === 5. OTP ===
    log("\n=== 5. change_phone + send_vcode WA ===")
    r = pg.evaluate("""async (phone)=>{
      const P=async(p,b)=>{try{const res=await fetch(p,{method:'POST',
        credentials:'include',headers:{'content-type':'application/json'},
        body:JSON.stringify(b||{})});return await res.json();}
        catch(e){return{ex:String(e).slice(0,50)}}};
      const out={};
      out.init=await P('/api/v4/account/management/change_phone_init');
      const seq=(out.init.data||{}).seq_no;
      out.init2=await P('/api/v4/account/management/change_phone_init_v2',
                        {phone:phone,seq_no:seq});
      out.settings=await P('/api/v4/otp/get_settings_v2',{operation:8,phone:phone});
      const seed=(out.settings.data||{}).seed;
      out.sends=[];
      for(const ch of [3,2,1]){
        const s=await P('/api/v4/otp/send_vcode',
          {phone:phone,channel:ch,operation:8,seed:seed});
        out.sends.push({ch,err:s.error,data:s.data});
        if(s.error===0)break;
      }
      out.seed=seed; out.seq=seq;
      return out;
    }""", NEWPHONE)

    log(f"  init err={r.get('init',{}).get('error')}")
    log(f"  init2 err={r.get('init2',{}).get('error')} ivs={(r.get('init2',{}).get('data') or {}).get('ivs_required')}")
    log(f"  settings err={r.get('settings',{}).get('error')} seed={str(r.get('seed'))[:22]}")
    for x in r.get("sends", []):
        log(f"  ch={x['ch']} err={x['err']}")
        if x["err"] == 0:
            dd = x.get("data") or {}
            log(f"  ✅✅✅ OTP TERKIRIM WA ch={x['ch']} tracking={str(dd.get('otp_tracking_id', ''))[:44]}")
            json.dump({"tracking": dd.get("otp_tracking_id"), "ch": x["ch"],
                       "seed": r.get("seed"), "seq": r.get("seq")},
                      open("/root/shopee-verify/OTP_SENT.json", "w"), indent=1)
            break

    pg.screenshot(path="/root/shopee-verify/RC_final.png", full_page=True)
    json.dump({"net": net[-40:], "otp": r}, open("/root/shopee-verify/RC.json", "w"), indent=1)
    cks = ctx.cookies()
    open("/root/shopee-verify/ck_rc.txt", "w").write(
        "; ".join(f"{c['name']}={c['value']}" for c in cks))
    br.close()

log("\n=== SELESAI ===")
