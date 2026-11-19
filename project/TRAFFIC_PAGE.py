"""TRAFFIC_PAGE.py — fokus halaman /verify/traffic.

Temuan: Shopee redirect ke /verify/traffic DULU (bukan langsung /verify/captcha).
Halaman /verify/traffic kemungkinan mount captcha dengan config proper.

Script ini:
  1. buka /user/account/phone -> biarkan redirect sendiri
  2. tangkap URL final, cek apakah /verify/traffic atau /verify/captcha
  3. di halaman itu, tunggu canvas sampai 90 detik
  4. kalau canvas muncul, solve + drag
  5. kalau tidak, enumerate DOM untuk cari iframe/shadow/wrapper
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
    open("/root/shopee-verify/TP.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright

NET = []


def onr(r):
    u = r.url
    if "/api/v4/" not in u:
        return
    sh = u.split("shopee.co.id")[-1].split("?")[0][:60]
    if "captcha" in sh or "traffic" in sh or "otp" in sh:
        try:
            b = r.text()
        except Exception:
            b = ""
        NET.append({"u": sh, "s": r.status, "b": b[:1200]})
        log(f"  NET {r.status} {sh[:44]} :: {b[:150]}")


DEEP = """()=>{
  const out={canvases:[],url:location.href,
             txt:(document.body.innerText||'').slice(0,300),deep:[]};
  // semua canvas termasuk shadow DOM
  function walk(root,depth){
    if(!root||depth>6) return;
    let els=[];
    try{els=[...root.querySelectorAll('*')];}catch(e){}
    for(const e of els){
      if(e.tagName==='CANVAS'){
        const r=e.getBoundingClientRect();
        out.canvases.push({w:Math.round(r.width),h:Math.round(r.height),
                           x:Math.round(r.x),y:Math.round(r.y)});
      }
      if(e.shadowRoot) walk(e.shadowRoot,depth+1);
      if(e.tagName==='IFRAME'){
        try{
          const d=e.contentDocument;
          if(d) walk(d,depth+1);
        }catch(err){ out.deep.push('iframe-xorigin'); }
      }
    }
  }
  walk(document,0);
  out.iframes=[...document.querySelectorAll('iframe')].map(f=>({src:(f.src||'').slice(0,90),
    w:Math.round(f.getBoundingClientRect().width)}));
  out.n=out.canvases.length;
  return out;
}"""

GRAB = """()=>{
  const out={ok:false};
  function allCanvas(root,acc,depth){
    if(!root||depth>6) return;
    let els=[]; try{els=[...root.querySelectorAll('*')];}catch(e){}
    for(const e of els){
      if(e.tagName==='CANVAS'){const r=e.getBoundingClientRect();
        if(r.width>15&&r.height>8) acc.push({el:e,w:r.width,h:r.height,x:r.x,y:r.y});}
      if(e.shadowRoot) allCanvas(e.shadowRoot,acc,depth+1);
    }
  }
  const all=[]; allCanvas(document,all,0);
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
        "Object.defineProperty(navigator,'languages',{get:()=>['id-ID','id','en']});")
    pg = ctx.new_page()
    pg.on("response", onr)

    log("=== 1. init dari home ===")
    try:
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    pg.wait_for_timeout(11000)

    log("\n=== 2. /user/account/phone -> biarkan redirect ===")
    try:
        pg.goto("https://shopee.co.id/user/account/phone",
                wait_until="domcontentloaded", timeout=55000)
    except Exception:
        pass

    # tunggu 90 detik, cek canvas tiap 5 detik
    for i in range(18):
        pg.wait_for_timeout(5000)
        d = pg.evaluate(DEEP)
        log(f"[{(i+1)*5:2d}s] url={d['url'][:65]} canvas={d['n']} "
            f"iframes={len(d.get('iframes') or [])}")
        if d["n"]:
            log(f"  ★ CANVAS: {d['canvases']}")
            break
        # kalau sudah halaman error final, break
        if "Verifikasi gagal" in d["txt"] and "Coba Lagi" in d["txt"]:
            log("  ⛔ Verifikasi gagal — stage 2 block")
            log(f"  txt: {d['txt'][:180]}")
            break

    d = pg.evaluate(DEEP)
    if d["iframes"]:
        log(f"\n  iframes: {json.dumps(d['iframes'])[:400]}")

    # === 3. kalau canvas ada -> solve ===
    if d["n"]:
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
            d2 = pg.evaluate(DEEP)
            log(f"    -> canvas={d2['n']} url={d2['url'][:70]}")
            pg.screenshot(path=f"/root/shopee-verify/TP_s{att+1}.png")
            if d2["n"] == 0:
                log("    🎉 captcha hilang")
                break

    # === 4. send_vcode ===
    log("\n=== 4. send_vcode ===")
    r5 = pg.evaluate("""async (a)=>{
      const {phone}=a; const out={tries:[]};
      const js=await (await fetch('/api/v4/otp/get_settings_v2',{method:'POST',
        credentials:'include',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({operation:8,phone})})).json();
      out.settings={err:js.error,seed:((js.data||{}).seed||'')};
      const seed=(js.data||{}).seed;
      for(const ch of [3,2,1]){
        const j=await (await fetch('/api/v4/otp/send_vcode',{method:'POST',
          credentials:'include',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({phone,channel:ch,operation:8,seed})})).json();
        out.tries.push({ch,err:j.error,trk:(j.data||{}).otp_tracking_id});
        if(j.error===0){out.win=ch;out.tracking=(j.data||{}).otp_tracking_id;break;}
        if(j.error!==23500101) break;
      }
      return out;
    }""", {"phone": NEWPHONE})
    log(f"  {json.dumps(r5)[:250]}")
    if r5.get("win"):
        log(f"\n  ✅✅✅✅ OTP TERKIRIM ch={r5['win']}")
        json.dump(r5, open("/root/shopee-verify/OTP_SENT.json", "w"), indent=1)

    pg.screenshot(path="/root/shopee-verify/TP_final.png", full_page=True)
    json.dump({"net": NET[-40:], "send": r5},
              open("/root/shopee-verify/TP.json", "w"), indent=1)
    br.close()

log("\n=== SELESAI ===")
