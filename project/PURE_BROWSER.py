"""PURE_BROWSER.py — SEMUA dari page context. Zero requests ke Shopee API.

Kenapa: get_config butuh x-sap-sec (signature per-request).
Hanya SDK yang bisa generate. Jadi:
  1. buka /user/account/phone dengan cookie
  2. kalau redirect ke /verify/captcha -> tunggu canvas
  3. solve + drag DI CANVAS
  4. SDK kirim verify sendiri
  5. setelah lolos, send_vcode dari page

Semua fetch pakai credentials:'include' -> cookie + SAP hook otomatis.
"""
import json, sys, time, os
import requests

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_zax.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283829322571"
PROXY = os.environ.get("SHOPEE_PROXY", "http://127.0.0.1:18080")
SADKEY = open("/root/shopee-farm/bot_key.txt").read().strip()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/PB.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]
cmap = {c["name"]: c["value"] for c in cookies}

from playwright.sync_api import sync_playwright

NET = []


def onr(r):
    u = r.url
    if "/api/v4/" not in u:
        return
    sh = u.split("shopee.co.id")[-1].split("?")[0][:64]
    if "captcha" in sh or "otp" in sh:
        try:
            b = r.text()
        except Exception:
            b = ""
        NET.append({"u": sh, "s": r.status, "b": b[:1500]})
        log(f"  NET {r.status} {sh[:46]} :: {b[:140]}")


STATE = """()=>{
  const cs=[...document.querySelectorAll('canvas')].map(c=>{
    const r=c.getBoundingClientRect();
    return {w:Math.round(r.width),h:Math.round(r.height),
            x:Math.round(r.x),y:Math.round(r.y)};
  }).filter(o=>o.w>15&&o.h>8);
  return {n:cs.length, cs, url:location.href,
          txt:(document.body.innerText||'').slice(0,250)};
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
  out.n=all.length; out.ok=!!(out.puz&&out.puz.length>4000);
  return out;
}"""

HANDLE = """()=>{
  const out=[];
  for(const e of document.querySelectorAll('div,span,button,svg,img')){
    const r=e.getBoundingClientRect();
    if(r.width<20||r.width>110||r.height<20||r.height>110) continue;
    if(e.querySelector('canvas')) continue;
    if(r.y<15) continue;
    out.push({x:r.x+r.width/2,y:r.y+r.height/2,w:r.width,h:r.height});
  }
  out.sort((a,b)=>(b.y-a.y)||(a.x-b.x));
  return out.slice(0,10);
}"""

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,900",
        "--disable-blink-features=AutomationControlled", "--lang=id-ID"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 900},
                         timezone_id="Asia/Jakarta",
                         proxy={"server": PROXY} if PROXY else None)
    ctx.add_cookies(cookies)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{},loadTimes:function(){},csi:function(){}};"
        "Object.defineProperty(navigator,'languages',{get:()=>['id-ID','id','en']});"
        "Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4]});")
    pg = ctx.new_page()
    pg.on("response", onr)

    log("=== 1. buka home (SDK init, hook SAP) ===")
    try:
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    pg.wait_for_timeout(11000)

    a = pg.evaluate("""async()=>{try{
      const r=await fetch('/api/v4/account/basic/get_account_info',{credentials:'include'});
      const j=await r.json();return {err:j.error,user:(j.data||{}).username};
    }catch(e){return{ex:String(e).slice(0,50)}}}""")
    log(f"  sesi: {a}")

    # === 2. init change phone dari page (SDK hook header otomatis) ===
    log("\n=== 2. change_phone_init_v2 dari page ===")
    r2 = pg.evaluate("""async (phone)=>{
      const out={};
      try{
        const j2=await (await fetch('/api/v4/account/management/change_phone_init_v2',
          {method:'POST',credentials:'include',
           headers:{'Content-Type':'application/json'},
           body:JSON.stringify({phone,seq_no:null})})).json();
        out.init2=j2.error;
        out.ivs=(j2.data||{}).ivs_required;
        out.cp=((j2.data||{}).change_phone_token||'').length;
        const j3=await (await fetch('/api/v4/otp/get_settings_v2',
          {method:'POST',credentials:'include',
           headers:{'Content-Type':'application/json'},
           body:JSON.stringify({operation:8,phone})})).json();
        out.settings=j3.error;
        out.seed=((j3.data||{}).seed||'');
        out.ch=(j3.data||{}).available_channels;
        out.scene=(j3.data||{}).captcha_scene;
      }catch(e){out.err=String(e).slice(0,120);}
      return out;
    }""", NEWPHONE)
    log(f"  {json.dumps(r2)[:300]}")
    seed = r2.get("seed") or ""

    # === 3. navigasi ke /user/account/phone -> tunggu canvas ===
    log("\n=== 3. ke /user/account/phone, tunggu captcha render ===")
    try:
        pg.goto("https://shopee.co.id/user/account/phone",
                wait_until="domcontentloaded", timeout=55000)
    except Exception:
        pass

    # tunggu hingga 60s untuk canvas
    got = False
    for i in range(15):
        pg.wait_for_timeout(4000)
        st = pg.evaluate(STATE)
        log(f"  [{i*4+4:2d}s] canvas={st['n']} url={st['url'][:70]}")
        if st["n"]:
            got = True
            log(f"  ★ CAPTCHA RENDER! {st['cs']}")
            break
        if "Verifikasi gagal" in st["txt"]:
            log("  ⛔ Verifikasi gagal — desktop block")
            break

    # === 4. solve kalau canvas ada ===
    if got:
        for att in range(3):
            g = pg.evaluate(GRAB)
            if not g.get("ok"):
                pg.wait_for_timeout(3000)
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
            log(f"    prop={prop} dist={dist:.0f} handle=({hx:.0f},{hy:.0f})")
            try:
                pg.mouse.move(hx, hy)
                pg.wait_for_timeout(260)
                pg.mouse.down()
                pg.wait_for_timeout(360)
                for i in range(1, 26):
                    p = i / 26
                    e = p * p * (3 - 2 * p)
                    pg.mouse.move(hx + e * dist, hy - 2 * min(1, p), steps=1)
                    pg.wait_for_timeout(16 + (i % 4) * 10)
                pg.wait_for_timeout(450)
                pg.mouse.move(hx + dist + 2, hy - 2)
                pg.wait_for_timeout(380)
                pg.mouse.up()
                log("    ✅ released")
            except Exception as e:
                log(f"    drag err {str(e)[:50]}")
            pg.wait_for_timeout(10000)
            st2 = pg.evaluate(STATE)
            log(f"    -> canvas={st2['n']} url={st2['url'][:70]}")
            pg.screenshot(path=f"/root/shopee-verify/PB_s{att+1}.png")
            if st2["n"] == 0:
                log("    🎉 captcha hilang")
                break

    # === 5. send_vcode dari page ===
    log("\n=== 5. send_vcode dari page ===")
    r5 = pg.evaluate("""async (a)=>{
      const {phone, seed}=a; const out={tries:[]};
      for(const ch of [3,2,1]){
        const j=await (await fetch('/api/v4/otp/send_vcode',{method:'POST',
          credentials:'include',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({phone,channel:ch,operation:8,seed})})).json();
        out.tries.push({ch,err:j.error,trk:(j.data||{}).otp_tracking_id});
        if(j.error===0){out.win=ch;out.tracking=(j.data||{}).otp_tracking_id;break;}
        if(j.error!==23500101) break;
      }
      return out;
    }""", {"phone": NEWPHONE, "seed": seed})
    for t in (r5.get("tries") or []):
        log(f"  ch={t.get('ch')} err={t.get('err')}")

    if r5.get("win"):
        log(f"\n  ✅✅✅✅ OTP TERKIRIM ch={r5['win']} tracking={r5.get('tracking')}")
        json.dump({"phone": NEWPHONE, "ch": r5["win"], "seed": seed,
                   "tracking": r5.get("tracking")},
                  open("/root/shopee-verify/OTP_SENT.json", "w"), indent=1)

    json.dump({"net": NET[-40:], "init": r2, "send": r5},
              open("/root/shopee-verify/PB.json", "w"), indent=1)
    pg.screenshot(path="/root/shopee-verify/PB_final.png", full_page=True)
    br.close()

log("\n=== SELESAI ===")
