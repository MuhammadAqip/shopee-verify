"""SDK_VERIFY.py — verify captcha LEWAT SDK browser (bukan requests).

Kenapa: verify via requests = 31500200 terus.
063.js: setelah captcha/verify -> dapat `signature` -> panggil
        loadCaptchaSdkAsync(signature) -> SDK lanjut proses.
Yang harus ada: encrypted_security_data = ARRAY (v[v.length-1]).
Jadi verify HARUS dari dalam SDK.

Alur:
  1. buka shopee.co.id, SDK load
  2. module 16223: getLongToken -> SEC (array buffer)
  3. module 16223: getWebDeviceFingerprint -> DFP
  4. trigger captcha via SDK: renderCaptchaPopupDesktop(box, props)
     props lengkap: appKey, scene, antiBotTrackingId, captchaId,
                    onVerifySuccess, onVerifyFailed, onLoadCaptchaSuccess
  5. kalau captcha render -> solve SadCaptcha -> drag di canvas
  6. SDK sendiri yang kirim verify (dengan SEC array + DFP)
  7. callback onVerifySuccess -> token

Output: SDK_VERIFY.json
"""
import json, sys, time, base64, os
import requests

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_new234.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6282323737822"
PROXY = "http://127.0.0.1:18080"
SADKEY = open("/root/shopee-farm/bot_key.txt").read().strip()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/SV.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]
cookie_map = {c["name"]: c["value"] for c in cookies}

from playwright.sync_api import sync_playwright

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
    net.append({"u": short, "s": r.status, "b": b[:2200]})
    if "captcha" in short:
        log(f"  NET {r.status} {short[:44]} :: {b[:150]}")


RENDER = r"""
(args) => {
  const { tid, captchaId, phone } = args;
  const out = {ok:false};
  try {
    if (typeof window.renderCaptchaPopupDesktop !== 'function'
     && typeof window.renderCaptchaDesktop !== 'function')
      return {err:'no_fn'};

    let box = document.getElementById('__cbx');
    if (!box){
      box = document.createElement('div');
      box.id = '__cbx';
      box.style.cssText = 'position:fixed;top:70px;left:50%;transform:translateX(-50%);'
        + 'z-index:2147483647;background:#fff;padding:6px;border-radius:6px;'
        + 'box-shadow:0 6px 30px rgba(0,0,0,.3);';
      document.body.appendChild(box);
    }

    window.__SVCB = {success:null, fail:null, loadOk:null, loadFail:null, events:[]};

    const props = {
      appKey: 'FlashSale.PC',
      scene: 'crawler_item',
      antiBotTrackingId: tid,
      captchaId: captchaId || '',
      phone: phone || '',
      showTitle: true,
      enableAudioCaptcha: false,
      enableAudioCaptchaKeyboardShortcuts: false,
      disableSlidablePuzzlePiece: false,
      onVerifySuccess: function(r){
        try{ window.__SVCB.success = (typeof r==='string')?r:JSON.stringify(r).slice(0,3000); }catch(e){}
      },
      onVerifyFailed: function(e){
        try{ window.__SVCB.fail = (typeof e==='string')?e:JSON.stringify(e).slice(0,800); }catch(e){}
      },
      onLoadCaptchaSuccess: function(){
        window.__SVCB.loadOk = true;
      },
      onLoadCaptchaFailed: function(e){
        try{ window.__SVCB.loadFail = (typeof e==='string')?e:JSON.stringify(e).slice(0,800); }catch(e){}
      },
      onComplete: function(){ window.__SVCB.events.push('complete'); },
      loadCaptchaSdkAsync: async function(signature){
        window.__SVCB.events.push('sdkAsync:'+String(signature).slice(0,40));
        return signature;
      }
    };

    const fn = window.renderCaptchaPopupDesktop || window.renderCaptchaDesktop;
    fn(box, props);
    out.ok = true;
    out.boxId = box.id;
    return out;
  } catch(e){ return {err:String(e).slice(0,200)}; }
}
"""

STATE = """()=>{
  const cs=[...document.querySelectorAll('canvas')].map(c=>{
    const r=c.getBoundingClientRect();
    return {w:Math.round(r.width),h:Math.round(r.height),
            x:Math.round(r.x),y:Math.round(r.y)};
  }).filter(o=>o.w>15&&o.h>8);
  return {n:cs.length, cs, txt:(document.body.innerText||'').slice(0,200),
          cb: window.__SVCB || null};
}"""

GRAB = """()=>{
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
}"""

HANDLE = """()=>{
  const out=[];
  for(const e of document.querySelectorAll('div,span,button,svg,img')){
    const r=e.getBoundingClientRect();
    if(r.width<20||r.width>100||r.height<20||r.height>100) continue;
    if(e.querySelector('canvas')) continue;
    out.push({x:r.x+r.width/2,y:r.y+r.height/2,w:r.width,h:r.height});
  }
  out.sort((a,b)=>(b.y-a.y)||(a.x-b.x));
  return out.slice(0,8);
}"""

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

    log("=== 1. shopee.co.id ===")
    try:
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    pg.wait_for_timeout(14000)
    for sel in ('button:has-text("Setuju")', 'text=Bahasa Indonesia'):
        try:
            l = pg.locator(sel)
            if l.count() and l.first.is_visible():
                l.first.click(timeout=2000, force=True)
                pg.wait_for_timeout(1200)
        except Exception:
            pass

    log("\n=== 2. cart/mini -> anti_bot_tracking_id ===")
    TRK = ""
    for a in range(3):
        try:
            r = pg.evaluate("""async ()=>{
              try{const res=await fetch('/api/v4/cart/mini?need_buyer_dp_info=1',
                {credentials:'include'});const j=await res.json();
                return {err:j.error, six:j['6'], action:j['0']};}catch(e){return {ex:String(e).slice(0,50)}}
            }""")
            log(f"  cart err={r.get('err')} action={r.get('action')}")
            six = r.get("six") or {}
            if isinstance(six, dict) and six.get("0"):
                TRK = six["0"]
                log(f"  ★ tracking {len(TRK)}B")
                break
        except Exception:
            pass
        pg.wait_for_timeout(4000)

    # fallback sessionStorage
    if not TRK:
        TRK = pg.evaluate("()=>{try{return sessionStorage.getItem('@shopee-ac/tracking_id')||'';}catch(e){return '';}}")
        log(f"  fallback tracking {len(TRK)}B")

    log("\n=== 3. renderCaptchaPopupDesktop dengan props lengkap ===")
    r = pg.evaluate(RENDER, {"tid": TRK, "captchaId": "", "phone": NEWPHONE})
    log(f"  {r}")

    for i in range(15):
        pg.wait_for_timeout(4000)
        st = pg.evaluate(STATE)
        cb = st.get("cb") or {}
        log(f"  [{i*4+4:2d}s] canvas={st['n']} loadOk={cb.get('loadOk')} "
            f"fail={str(cb.get('fail'))[:50]}")
        if st["n"] or cb.get("fail") or cb.get("loadFail"):
            break

    st = pg.evaluate(STATE)
    log(f"\n  canvas={st['n']} {st['cs']}")
    log(f"  txt: {str(st.get('txt',''))[:140].replace(chr(10),' | ')}")
    pg.screenshot(path="/root/shopee-verify/SV_box.png", full_page=False)

    token = ""

    # === 4. solve kalau canvas ada ===
    if st["n"]:
        for att in range(3):
            g = pg.evaluate(GRAB)
            if not g.get("ok"):
                pg.wait_for_timeout(3500)
                continue
            log(f"\n  solve#{att+1} puz={len(g['puz'])}B pc={len(g.get('pc') or '')}B")
            prop = None
            try:
                rr = requests.post("https://www.sadcaptcha.com/api/v1/puzzle",
                                   params={"licenseKey": SADKEY},
                                   json={"puzzleImageB64": g["puz"].split(",", 1)[1],
                                         "pieceImageB64": (g.get("pc") or "").split(",", 1)[1]
                                         if g.get("pc") else ""}, timeout=70)
                log(f"    sad {rr.status_code} {rr.text[:80]}")
                if rr.status_code == 200:
                    prop = rr.json().get("slideXProportion")
            except Exception as e:
                log(f"    err {str(e)[:50]}")
            if prop is None:
                continue

            h = pg.evaluate(HANDLE)
            if not h:
                log("    no handle")
                continue
            hx, hy = h[0]["x"], h[0]["y"]
            dist = prop * (g["rect"]["w"] or 280)
            log(f"    prop={prop} dist={dist:.1f} handle=({hx:.0f},{hy:.0f})")

            try:
                pg.mouse.move(hx, hy)
                pg.wait_for_timeout(250)
                pg.mouse.down()
                pg.wait_for_timeout(350)
                for i in range(1, 25):
                    p = i / 25
                    e = p * p * (3 - 2 * p)
                    pg.mouse.move(hx + e * dist, hy - 2 * min(1, p), steps=1)
                    pg.wait_for_timeout(20 + (i % 4) * 10)
                pg.wait_for_timeout(450)
                pg.mouse.move(hx + dist + 2, hy - 2)
                pg.wait_for_timeout(380)
                pg.mouse.up()
                log("    ✅ released")
            except Exception as e:
                log(f"    drag err {str(e)[:50]}")

            pg.wait_for_timeout(9000)
            cb = pg.evaluate("()=>window.__SVCB||{}")
            log(f"    cb: success={str(cb.get('success'))[:80]} fail={str(cb.get('fail'))[:60]}")
            log(f"    events: {cb.get('events')}")
            pg.screenshot(path=f"/root/shopee-verify/SV_s{att+1}.png", full_page=False)
            if cb.get("success"):
                token = cb["success"]
                log("    🎉🎉 SDK SUCCESS")
                break
            st2 = pg.evaluate(STATE)
            log(f"    -> canvas={st2['n']}")
            if st2["n"] == 0 and not cb.get("fail"):
                log("    canvas hilang (mungkin sukses)")
                break

    json.dump({"net": net[-45:], "trk": TRK[:120], "token": token,
               "cb": st.get("cb")},
              open("/root/shopee-verify/SDK_VERIFY.json", "w"), indent=1)

    pg.screenshot(path="/root/shopee-verify/SV_final.png", full_page=True)
    br.close()

log("\n=== SELESAI ===")
