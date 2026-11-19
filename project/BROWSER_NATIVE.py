"""BROWSER_NATIVE.py — change phone SEPENUHNYA dari browser, satu sesi.

Kenapa 31500000 terus di jalur requests:
  - captcha_token + tracking_id + SEC punya BINDING ke sesi browser
  - requests = sesi baru tiap kali -> server tolak (window terkunci)
  - browser langsung (user bilang) = aman, tanpa max window

Jadi: JANGAN pakai requests untuk captcha. Semua dari dalam page:
  1. buka https://shopee.co.id/verify/captcha (SDK render sendiri)
  2. tunggu canvas muncul
  3. solve via SadCaptcha
  4. drag di canvas -> SDK kirim verify sendiri (SEC + DFP + tracking valid)
  5. setelah captcha lolos, SDK kasih token -> LANGSUNG send_vcode dari page
  6. isi OTP -> change_phone complete

Semua fetch pakai credentials:'include' di dalam page = cookie + sesi sama.
"""
import json, sys, time, base64, os
import requests

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_new234.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6282323737822"
MODE = sys.argv[3] if len(sys.argv) > 3 else "change"   # change|verify
BUDGET = int(sys.argv[4]) if len(sys.argv) > 4 else 600

PROXY = "http://127.0.0.1:18080"
SADKEY = open("/root/shopee-farm/bot_key.txt").read().strip()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/BN.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright

netlog = []


def onresp(r):
    u = r.url
    if "/api/v4/" not in u:
        return
    short = u.split("shopee.co.id")[-1].split("?")[0][:72]
    if "captcha" in short or "otp" in short or "change_phone" in short:
        try:
            b = r.text()
        except Exception:
            b = ""
        netlog.append({"u": short, "s": r.status, "b": b[:2500]})
        log(f"  NET {r.status} {short[:50]} :: {b[:130]}")


STATE = """()=>{
  const cs=[...document.querySelectorAll('canvas')].map(c=>{
    const r=c.getBoundingClientRect();
    return {w:Math.round(r.width),h:Math.round(r.height),
            x:Math.round(r.x),y:Math.round(r.y)};
  }).filter(o=>o.w>15&&o.h>8);
  return {n:cs.length, cs,
          txt:(document.body.innerText||'').slice(0,250),
          url:location.href};
}"""

GRAB = """()=>{
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
  out.n=all.length;
  out.ok=!!(out.puz&&out.puz.length>4000);
  return out;
}"""

HANDLE = """()=>{
  const out=[];
  for(const e of document.querySelectorAll('div,span,button,svg,img')){
    const r=e.getBoundingClientRect();
    if(r.width<20||r.width>110||r.height<20||r.height>110) continue;
    if(e.querySelector('canvas')) continue;
    if(r.y<20) continue;
    out.push({x:r.x+r.width/2,y:r.y+r.height/2,w:r.width,h:r.height});
  }
  out.sort((a,b)=>(b.y-a.y)||(a.x-b.x));
  return out.slice(0,10);
}"""


def drag(pg, prop, rect):
    h = pg.evaluate(HANDLE)
    if not h:
        return False, "no_handle"
    hx, hy = h[0]["x"], h[0]["y"]
    dist = prop * (rect.get("w") or 280)
    try:
        pg.mouse.move(hx, hy)
        pg.wait_for_timeout(280)
        pg.mouse.down()
        pg.wait_for_timeout(380)
        for i in range(1, 26):
            p = i / 26
            e = p * p * (3 - 2 * p)
            pg.mouse.move(hx + e * dist, hy - 2 * min(1, p), steps=1)
            pg.wait_for_timeout(18 + (i % 4) * 11)
        pg.wait_for_timeout(480)
        pg.mouse.move(hx + dist + 2, hy - 2)
        pg.wait_for_timeout(400)
        pg.mouse.up()
        return True, f"drag {dist:.0f}px from ({hx:.0f},{hy:.0f})"
    except Exception as e:
        return False, str(e)[:60]


def solve(pg, path_png):
    g = pg.evaluate(GRAB)
    if not g.get("ok"):
        return None, None
    log(f"  canvas: puz={len(g['puz'])}B pc={len(g.get('pc') or '')}B rect={g['rect']}")
    prop = None
    try:
        rr = requests.post("https://www.sadcaptcha.com/api/v1/puzzle",
                           params={"licenseKey": SADKEY},
                           json={"puzzleImageB64": g["puz"].split(",", 1)[1],
                                 "pieceImageB64": (g.get("pc") or "").split(",", 1)[1]
                                 if g.get("pc") else ""}, timeout=70)
        log(f"  sad {rr.status_code} {rr.text[:90]}")
        if rr.status_code == 200:
            prop = rr.json().get("slideXProportion")
    except Exception as e:
        log(f"  sad err {str(e)[:50]}")
    return prop, g.get("rect")


with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,900",
        "--disable-blink-features=AutomationControlled", "--lang=id-ID",
        "--disable-features=IsolateOrigins,site-per-process"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 900},
                         timezone_id="Asia/Jakarta",
                         proxy={"server": PROXY},
                         extra_http_headers={"Accept-Language": "id-ID,id;q=0.9,en;q=0.8"})
    ctx.add_cookies(cookies)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{},loadTimes:function(){},csi:function(){}};"
        "Object.defineProperty(navigator,'languages',{get:()=>['id-ID','id','en']});"
        "Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});")
    pg = ctx.new_page()
    pg.on("response", onresp)

    log("=== 1. home ===")
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
                pg.wait_for_timeout(1500)
        except Exception:
            pass

    # === cek sesi ===
    acc = pg.evaluate("""async()=>{
      try{const r=await fetch('/api/v4/account/basic/get_account_info',{credentials:'include'});
        const j=await r.json();return {err:j.error,user:(j.data||{}).username};}
      catch(e){return {ex:String(e).slice(0,50)}}
    }""")
    log(f"  sesi: err={acc.get('err')} user={acc.get('user')}")
    if acc.get("err") != 0:
        log("  ❌ cookie mati")
        br.close()
        sys.exit(1)

    # === 2. buka halaman change phone NATIVE (bukan /verify/captcha) ===
    log("\n=== 2. halaman native change phone ===")
    for url in ("https://shopee.co.id/user/account/phone",
                "https://shopee.co.id/buyer/settings/phone",
                "https://shopee.co.id/user/account/settings"):
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=45000)
            pg.wait_for_timeout(6000)
            st = pg.evaluate(STATE)
            log(f"  {url.split('.id')[-1]} -> n={st['n']} url={st['url'][:60]}")
            if "phone" in url:
                break
        except Exception as e:
            log(f"  {url.split('.id')[-1]} err {str(e)[:40]}")

    # === 3. trigger change phone via page JS (SDK aktif di page ini) ===
    log("\n=== 3. trigger change phone dari page ===")
    r = pg.evaluate("""async (phone)=>{
      const out={steps:[]};
      try{
        const j=(await (await fetch('/api/v4/account/management/change_phone_init',
          {credentials:'include',headers:{'af-ac-enc-dat':'0123456789abcdef'}})).json());
        out.steps.push({init:j.error, seq:(j.data||{}).seq_no});
        const seq=(j.data||{}).seq_no;
        const j2=(await (await fetch('/api/v4/account/management/change_phone_init_v2',
          {method:'POST',credentials:'include',
           headers:{'Content-Type':'application/json','af-ac-enc-dat':'0123456789abcdef'},
           body:JSON.stringify({phone:phone, seq_no:seq})})).json());
        out.steps.push({init2:j2.error, ivs:(j2.data||{}).ivs_required,
                        cp:((j2.data||{}).change_phone_token||'').length});
        if ((j2.data||{}).change_phone_token) out.cp_token=j2.data.change_phone_token;

        const j3=(await (await fetch('/api/v4/otp/get_settings_v2',
          {method:'POST',credentials:'include',
           headers:{'Content-Type':'application/json','af-ac-enc-dat':'0123456789abcdef'},
           body:JSON.stringify({operation:8, phone:phone})})).json());
        const d3=j3.data||{};
        out.steps.push({settings:j3.error, seed:(d3.seed||'').slice(0,20),
                        ch:d3.available_channels, pref:d3.preferred_channel,
                        need_cap:d3.need_captcha, scene:d3.captcha_scene});
        if (d3.seed) out.seed=d3.seed;
        if (d3.captcha_scene) out.scene=d3.captcha_scene;
      }catch(e){ out.err=String(e).slice(0,120); }
      return out;
    }""", NEWPHONE)
    for s in (r.get("steps") or []):
        log(f"  {s}")
    log(f"  err={r.get('err')}")
    seed = r.get("seed") or ""
    scene = r.get("scene") or "signup"
    log(f"  seed={seed[:20]} scene={scene}")

    if (r.get("steps") and r["steps"][-1].get("settings") not in (0, None)):
        log(f"  ⛔ settings gagal ({r['steps'][-1].get('settings')})")
        br.close()
        sys.exit(2)

    # === 4. send_vcode WA dari page (SDK yang inject captcha kalau perlu) ===
    log("\n=== 4. send_vcode WA dari page ===")
    r2 = pg.evaluate("""async (a)=>{
      const {phone, seed} = a;
      const out={tries:[]};
      for (const ch of [3,2,1]){
        try{
          const rr=await fetch('/api/v4/otp/send_vcode',{
            method:'POST', credentials:'include',
            headers:{'Content-Type':'application/json','af-ac-enc-dat':'0123456789abcdef'},
            body:JSON.stringify({phone, channel:ch, operation:8, seed})});
          const j=await rr.json();
          out.tries.push({ch, err:j.error, data:j.data});
          if (j.error===0){ out.win=ch; out.tracking=(j.data||{}).otp_tracking_id; break; }
          if (j.error!==23500101) break;
        }catch(e){ out.tries.push({ch, ex:String(e).slice(0,60)}); }
      }
      return out;
    }""", {"phone": NEWPHONE, "seed": seed})
    for t in (r2.get("tries") or []):
        log(f"  ch={t.get('ch')} err={t.get('err')} {str(t.get('data'))[:80]}")

    if r2.get("win"):
        log(f"\n  ✅✅✅ OTP TERKIRIM ch={r2['win']} tracking={r2.get('tracking')}")
        json.dump({"phone": NEWPHONE, "ch": r2["win"], "seed": seed,
                   "tracking": r2.get("tracking")}, open("/root/shopee-verify/OTP_SENT.json", "w"), indent=1)
        br.close()
        sys.exit(0)

    # === 5. kalau butuh captcha -> render SDK DI PAGE INI (sesi sama) ===
    log("\n=== 5. captcha perlu token — render SDK di page ini ===")
    trk = pg.evaluate("""()=>{try{return sessionStorage.getItem('@shopee-ac/tracking_id')||''}catch(e){return ''}}""")
    log(f"  tracking sessionStorage {len(trk)}B")
    if not trk:
        r3 = pg.evaluate("""async()=>{try{const j=await(await fetch('/api/v4/cart/mini?need_buyer_dp_info=1',{credentials:'include'})).json();return (j['6']||{})['0']||'';}catch(e){return ''}}""")
        trk = r3
        log(f"  tracking cart {len(trk)}B")

    rr = pg.evaluate("""(a)=>{
      try{
        if(typeof window.renderCaptchaPopupDesktop!=='function' &&
           typeof window.renderCaptchaDesktop!=='function') return {err:'no_fn'};
        let box=document.getElementById('__bnbox');
        if(!box){box=document.createElement('div');box.id='__bnbox';
          box.style.cssText='position:fixed;top:60px;left:50%;transform:translateX(-50%);z-index:2147483647;background:#fff;padding:6px;border-radius:6px;';
          document.body.appendChild(box);}
        window.__BN={ok:null,fail:null,load:null};
        const props={appKey:'FlashSale.PC',scene:'crawler_item',
          antiBotTrackingId:a.trk,captchaId:'',phone:a.phone,showTitle:true,
          onVerifySuccess:r=>{window.__BN.ok=(typeof r==='string')?r:JSON.stringify(r).slice(0,2500);},
          onVerifyFailed:e=>{window.__BN.fail=(typeof e==='string')?e:JSON.stringify(e).slice(0,600);},
          onLoadCaptchaSuccess:()=>{window.__BN.load=true;},
          loadCaptchaSdkAsync:async(s)=>{window.__BN.sig=String(s).slice(0,100);return s;}};
        const fn=window.renderCaptchaPopupDesktop||window.renderCaptchaDesktop;
        fn(box,props);
        return {ok:true};
      }catch(e){return {err:String(e).slice(0,150)};}
    }""", {"trk": trk, "phone": NEWPHONE})
    log(f"  render: {rr}")

    for i in range(10):
        pg.wait_for_timeout(4000)
        st = pg.evaluate(STATE)
        cb = pg.evaluate("()=>window.__BN||{}")
        log(f"  [{i*4+4}s] canvas={st['n']} load={cb.get('load')} fail={str(cb.get('fail'))[:50]}")
        if st["n"] or cb.get("fail"):
            break

    # solve loop
    for att in range(3):
        prop, rect = solve(pg, None)
        if prop is None:
            pg.wait_for_timeout(3500)
            continue
        log(f"  prop={prop}")
        ok, msg = drag(pg, prop, rect or {})
        log(f"  {msg}")
        pg.wait_for_timeout(9000)
        cb = pg.evaluate("()=>window.__BN||{}")
        log(f"  cb ok={str(cb.get('ok'))[:100]} fail={str(cb.get('fail'))[:60]}")
        pg.screenshot(path=f"/root/shopee-verify/BN_s{att+1}.png")
        if cb.get("fail"):
            break
        st = pg.evaluate(STATE)
        if st["n"] == 0:
            break

    tok = ""
    cb = pg.evaluate("()=>window.__BN||{}")
    if cb.get("ok"):
        try:
            tok = json.loads(cb["ok"]).get("token", "") if cb["ok"].startswith("{") else cb["ok"]
        except Exception:
            tok = cb["ok"]

    # === 6. kalau token didapat, send vcode lagi DARI PAGE ===
    if tok:
        log(f"\n=== 6. token {len(str(tok))}B -> send_vcode ulang ===")
        r4 = pg.evaluate("""async (a)=>{
          const {phone, seed, tok}=a;
          for(const ch of [3,2,1]){
            const j=await (await fetch('/api/v4/otp/send_vcode',{method:'POST',
              credentials:'include',
              headers:{'Content-Type':'application/json','af-ac-enc-dat':'0123456789abcdef'},
              body:JSON.stringify({phone,channel:ch,operation:8,seed,captcha_token:tok})})).json();
            if(j.error===0) return {ch, err:0, tracking:(j.data||{}).otp_tracking_id};
          }
          return {err:'all_failed'};
        }""", {"phone": NEWPHONE, "seed": seed, "tok": tok})
        log(f"  {r4}")

    json.dump({"net": netlog[-40:], "cb": cb, "token": str(tok)[:200]},
              open("/root/shopee-verify/BN.json", "w"), indent=1)
    pg.screenshot(path="/root/shopee-verify/BN_final.png", full_page=True)
    br.close()

log("\n=== SELESAI ===")
