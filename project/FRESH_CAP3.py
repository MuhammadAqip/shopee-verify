"""FRESH_CAP3.py — URL verify PAKAI anti_bot_tracking_id dari cart/mini field "6".

Bukti:
  cart/mini -> {"0":3 (Challenge), "2":true, "3":90309999,
                "6":{"0":"gqRjZGVr...", "1":"mfreyJidX..."}}
  field 6.0 = anti_bot_tracking_id
  URL: /verify/captcha?anti_bot_tracking_id=<6.0>&scene=crawler_item&is_logged_in=true

Juga coba /verify/traffic?tracking_id=<6.0>... (redirect pertama)

Flow:
  1. trigger cart/mini -> tangkap body lengkap, ambil 6.0
  2. buka URL verify dengan tracking
  3. tunggu canvas -> solve -> drag
  4. page-context change_phone + send_vcode
"""
import json, sys, time

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_fresh_1659.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6285796160652"
BUDGET = int(sys.argv[3]) if len(sys.argv) > 3 else 600

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
SADKEY = open("/root/shopee-farm/bot_key.txt").read().strip()
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):3d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/FRS3.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright
import requests

TID = {"v": ""}


def state(pg):
    return pg.evaluate("""()=>{
      const cs=[...document.querySelectorAll('canvas')].map(c=>{
        const r=c.getBoundingClientRect();
        return {w:Math.round(r.width),h:Math.round(r.height),x:Math.round(r.x),y:Math.round(r.y)};
      }).filter(o=>o.w>20&&o.h>10);
      return {canvas: cs,
              txt:(document.body.innerText||'').slice(0,260),
              url: location.href.slice(0,150)};
    }""")


def grab(pg):
    return pg.evaluate("""()=>{
      const out={ok:false};
      const all=[...document.querySelectorAll('canvas')].map(c=>{
        const r=c.getBoundingClientRect();
        return {el:c,w:r.width,h:r.height,x:r.x,y:r.y};
      }).filter(o=>o.w>20&&o.h>10);
      if(!all.length) return out;
      all.sort((a,b)=>(b.w*b.h)-(a.w*a.h));
      const big=all[0];
      const small=all.slice(1).sort((a,b)=>(a.w*a.h)-(b.w*b.h))[0];
      try{ out.puz=big.el.toDataURL('image/png'); }catch(e){}
      if(small){ try{ out.pc=small.el.toDataURL('image/png'); }catch(e){} }
      out.rect={x:big.x,y:big.y,w:big.w,h:big.h};
      out.n=all.length;
      out.ok=!!(out.puz&&out.puz.length>5000);
      return out;
    }""")


def click_any(pg, sels, wait=1800):
    for sel in sels:
        try:
            l = pg.locator(sel)
            if l.count() and l.first.is_visible():
                l.first.click(timeout=2400, force=True)
                pg.wait_for_timeout(wait)
                return sel
        except Exception:
            pass
    return None


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

    log("=== 1. home ===")
    try:
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    pg.wait_for_timeout(9000)
    click_any(pg, ['button:has-text("Setuju")', 'text=Bahasa Indonesia'])

    # === 2. cart/mini -> ambil field 6 ===
    log("\n=== 2. cart/mini -> field 6 ===")
    payload = {}
    for a in range(4):
        try:
            r = pg.evaluate("""async ()=>{
              const res=await fetch('/api/v4/cart/mini?need_buyer_dp_info=1',
                {credentials:'include'});
              return await res.json();
            }""")
            payload = r
            log(f"  [{a+1}] keys={list(r.keys())} err={r.get('error')} type={r.get('0')}")
            six = r.get("6")
            if isinstance(six, dict):
                for k, v in six.items():
                    log(f"   6[{k}] = {str(v)[:70]}")
                if six.get("0"):
                    TID["v"] = six["0"]
                    log(f"  ★ anti_bot_tracking_id {len(TID['v'])}B")
                    break
            elif isinstance(six, str) and len(six) > 40:
                TID["v"] = six
                log(f"  ★ tracking str {len(six)}B")
                break
        except Exception as e:
            log(f"  err {str(e)[:50]}")
        pg.wait_for_timeout(4000)

    if not TID["v"]:
        # fallback URL dari redirect
        cur = pg.url
        log(f"  fallback url: {cur[:130]}")
        if "tracking_id=" in cur:
            TID["v"] = cur.split("tracking_id=")[1].split("&")[0]
            log(f"  ★ tracking dari URL {len(TID['v'])}B")

    # === 3. buka URL verify dengan tracking ===
    url = None
    if TID["v"]:
        from urllib.parse import quote
        tid = quote(TID["v"], safe="")
        cands = [
            f"https://shopee.co.id/verify/captcha?anti_bot_tracking_id={tid}"
            f"&is_logged_in=true&redirect_type=2&should_replace_history=false"
            f"&app_key=TSS.PC&scene=crawler_item",
            f"https://shopee.co.id/verify/captcha?anti_bot_tracking_id={tid}",
            f"https://shopee.co.id/verify/traffic?tracking_id={tid}"
            f"&is_logged_in=true&app_key=TSS.PC&scene=crawler_item",
        ]
        log(f"\n=== 3. coba {len(cands)} URL verify ===")
        for i, u in enumerate(cands):
            try:
                pg.goto(u, wait_until="domcontentloaded", timeout=55000)
            except Exception as e:
                log(f"  [{i+1}] goto err {str(e)[:40]}")
                continue
            pg.wait_for_timeout(9000)
            click_any(pg, ['button:has-text("Setuju")'])
            st = state(pg)
            n = len(st.get("canvas", []))
            log(f"  [{i+1}] canvas={n} url={st.get('url', '')[-44:]}")
            log(f"      txt: {st.get('txt', '')[:110].replace(chr(10), ' | ')}")
            if n:
                url = u
                log(f"  ★ CANVAS di percobaan {i+1}")
                pg.screenshot(path=f"/root/shopee-verify/FRS3_u{i+1}.png", full_page=False)
                break

    # === 4. tunggu & solve ===
    if not url:
        log("\n=== 4. tunggu canvas tambahan ===")
        for i in range(12):
            pg.wait_for_timeout(5000)
            st = state(pg)
            if st.get("canvas"):
                log(f"  ★ canvas muncul di {i*5+5}s")
                break
            if i % 3 == 2:
                click_any(pg, ['text=Coba Lagi', 'button:has-text("Verifikasi")',
                               'button:has-text("Mulai")'])

    st = state(pg)
    log(f"\n  canvas={len(st.get('canvas', []))} url={st.get('url', '')[-55:]}")
    log(f"  txt: {st.get('txt', '')[:150].replace(chr(10), ' | ')}")
    pg.screenshot(path="/root/shopee-verify/FRS3_now.png", full_page=False)

    if st.get("canvas"):
        for att in range(3):
            g = grab(pg)
            if not g.get("ok"):
                pg.wait_for_timeout(4000)
                continue
            log(f"\n=== solve#{att+1} puz={len(g['puz'])}B pc={len(g.get('pc') or '')}B rect={g.get('rect')} ===")
            pz = g["puz"].split(",", 1)[1]
            pc = (g.get("pc") or "").split(",", 1)[1] if g.get("pc") else ""
            prop = None
            try:
                r = requests.post("https://www.sadcaptcha.com/api/v1/puzzle",
                                  params={"licenseKey": SADKEY},
                                  json={"puzzleImageB64": pz, "pieceImageB64": pc},
                                  timeout=60)
                log(f"  sad {r.status_code} {r.text[:90]}")
                if r.status_code == 200:
                    prop = r.json().get("slideXProportion")
            except Exception as e:
                log(f"  sad err {str(e)[:50]}")
            if prop is None:
                continue
            log(f"  ★ prop={prop}")
            h = pg.evaluate("""()=>{
              const out=[];
              for(const e of document.querySelectorAll('div,button,span,svg,img')){
                const r=e.getBoundingClientRect();
                if(r.width<24||r.width>90||r.height<24||r.height>90) continue;
                if(e.querySelector('canvas')) continue;
                out.push({x:r.x+r.width/2,y:r.y+r.height/2,w:r.width,
                          cls:(e.className||'').toString().slice(0,26)});
              }
              out.sort((a,b)=>(b.y-a.y)||(a.x-b.x));
              return out.slice(0,8);
            }""")
            log(f"  handle kandidat: {[(round(x['x']),round(x['y']),round(x['w'])) for x in h[:5]]}")
            if not h:
                continue
            hx, hy = h[0]["x"], h[0]["y"]
            w = g["rect"]["w"] or 280
            dist = prop * w
            log(f"  drag ({hx:.0f},{hy:.0f}) +{dist:.0f}")
            try:
                pg.mouse.move(hx, hy)
                pg.wait_for_timeout(240)
                pg.mouse.down()
                pg.wait_for_timeout(340)
                for i in range(1, 24):
                    p = i / 24
                    e = p * p * (3 - 2 * p)
                    pg.mouse.move(hx + e * dist, hy - 3 * min(1, p), steps=1)
                    pg.wait_for_timeout(22 + (i % 4) * 9)
                pg.wait_for_timeout(450)
                pg.mouse.move(hx + dist + 2, hy - 3)
                pg.wait_for_timeout(340)
                pg.mouse.up()
                log("  ✅ released")
            except Exception as e:
                log(f"  drag err {str(e)[:50]}")
            pg.wait_for_timeout(9000)
            st2 = state(pg)
            log(f"  -> canvas={len(st2.get('canvas', []))} url={st2.get('url', '')[-44:]}")
            pg.screenshot(path=f"/root/shopee-verify/FRS3_s{att+1}.png", full_page=False)
            if not st2.get("canvas"):
                log("  🎉 captcha hilang")
                break

    # === 5. change_phone + OTP ===
    log("\n=== 5. change_phone + send_vcode WA ===")
    r = pg.evaluate("""async (phone)=>{
      const P=async(p,b)=>{try{const res=await fetch(p,{method:'POST',
        credentials:'include',headers:{'content-type':'application/json'},
        body:JSON.stringify(b||{})});return await res.json();}catch(e){return{ex:String(e).slice(0,50)}}};
      const out={};
      out.init = await P('/api/v4/account/management/change_phone_init');
      const seq=(out.init.data||{}).seq_no;
      out.init2 = await P('/api/v4/account/management/change_phone_init_v2',
                          {phone:phone, seq_no:seq});
      out.settings = await P('/api/v4/otp/get_settings_v2',{operation:8, phone:phone});
      const seed=(out.settings.data||{}).seed;
      out.sends=[];
      for(const ch of [3,2,1]){
        const s=await P('/api/v4/otp/send_vcode',
          {phone:phone, channel:ch, operation:8, seed:seed});
        out.sends.push({ch, err:s.error, data:s.data});
        if(s.error===0) break;
      }
      out.seq=seq; out.seed=seed;
      return out;
    }""", NEWPHONE)

    log(f"  init err={r.get('init',{}).get('error')}")
    log(f"  init2 err={r.get('init2',{}).get('error')} ivs={(r.get('init2',{}).get('data') or {}).get('ivs_required')}")
    log(f"  settings err={r.get('settings',{}).get('error')} seed={str((r.get('settings',{}).get('data') or {}).get('seed'))[:22]}")
    for x in r.get("sends", []):
        log(f"  ch={x['ch']} err={x['err']}")
        if x["err"] == 0:
            dd = x.get("data") or {}
            log(f"  ✅✅✅ OTP TERKIRIM WA ch={x['ch']} tracking={str(dd.get('otp_tracking_id',''))[:46]}")
            json.dump({"tracking": dd.get("otp_tracking_id"), "ch": x["ch"],
                       "seed": r.get("seed"), "seq": r.get("seq")},
                      open("/root/shopee-verify/OTP_SENT.json", "w"), indent=1)
            break

    pg.screenshot(path="/root/shopee-verify/FRS3_final.png", full_page=True)
    json.dump({"tid": TID["v"][:200], "otp": r},
              open("/root/shopee-verify/FRS3.json", "w"), indent=1)
    cks = ctx.cookies()
    open("/root/shopee-verify/ck_frs3.txt", "w").write(
        "; ".join(f"{c['name']}={c['value']}" for c in cks))
    br.close()

log("\n=== SELESAI ===")
