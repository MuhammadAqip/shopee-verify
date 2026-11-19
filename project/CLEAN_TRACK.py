"""CLEAN_TRACK.py — hapus tracking lama, paksa SDK terbitkan tracking FRESH.

Diagnosa:
  sessionStorage '@shopee-ac/tracking_id' menyimpan tracking LAMA (1422B/1184B)
  SDK generate pakai tracking itu -> 90309999 / 31500000
  get_config selalu kasih tracking BARU, tapi SDK pakai yang di storage

Fix:
  1. hapus semua key tracking di sessionStorage + localStorage
  2. buka /verify/captcha -> SDK panggil get_config -> tracking baru
  3. tangkap tracking BARU dari network
  4. verifikasi generate pakai tracking BARU itu
  5. kalau error=0 -> solve -> drag di canvas -> SDK verify sendiri
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
    open("/root/shopee-verify/CT.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright

TRK = {"new": "", "all": []}
GEN = {"r": None}


def onresp(r):
    u = r.url
    if "get_config" in u:
        try:
            j = r.json()
            t = j.get("tracking_id") or ""
            if t:
                TRK["new"] = t
                TRK["all"].append(t)
                log(f"  ★ get_config tracking BARU {len(t)}B :: {t[:40]}")
        except Exception:
            pass
    if "captcha/generate" in u:
        try:
            b = r.text()
        except Exception:
            b = ""
        GEN["r"] = {"s": r.status, "b": b[:1200]}
        log(f"  NET generate {r.status} :: {b[:220]}")


STATE = """()=>{
  const cs=[...document.querySelectorAll('canvas')].map(c=>{
    const r=c.getBoundingClientRect();
    return {w:Math.round(r.width),h:Math.round(r.height),
            x:Math.round(r.x),y:Math.round(r.y)};
  }).filter(o=>o.w>15&&o.h>8);
  return {n:cs.length, cs, txt:(document.body.innerText||'').slice(0,180)};
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
        "--disable-blink-features=AutomationControlled", "--lang=id-ID",
        "--disable-features=IsolateOrigins,site-per-process"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 900},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    ctx.add_cookies(cookies)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{},loadTimes:function(){},csi:function(){}};"
        "Object.defineProperty(navigator,'languages',{get:()=>['id-ID','id','en']});"
        "Object.defineProperty(navigator,'deviceMemory',{get:()=>8});"
        "Object.defineProperty(navigator,'hardwareConcurrency',{get:()=>8});")
    pg = ctx.new_page()
    pg.on("response", onresp)

    log("=== 1. buka home, lalu HAPUS tracking lama ===")
    try:
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    pg.wait_for_timeout(8000)
    for sel in ('button:has-text("Setuju")', 'text=Bahasa Indonesia'):
        try:
            l = pg.locator(sel)
            if l.count() and l.first.is_visible():
                l.first.click(timeout=2000, force=True)
                pg.wait_for_timeout(1200)
        except Exception:
            pass

    cleared = pg.evaluate("""()=>{
      const out={ss:[],ls:[]};
      try{
        const sks=[];
        for(let i=0;i<sessionStorage.length;i++) sks.push(sessionStorage.key(i));
        for(const k of sks){
          if(/tracking|antifraud|captcha|dfp|sapid/i.test(k)){
            out.ss.push(k+'='+String(sessionStorage.getItem(k)).slice(0,40));
            sessionStorage.removeItem(k);
          }
        }
      }catch(e){}
      try{
        const lks=[];
        for(let i=0;i<localStorage.length;i++) lks.push(localStorage.key(i));
        for(const k of lks){
          if(/tracking|antifraud|captcha|dfp/i.test(k)){
            out.ls.push(k+'='+String(localStorage.getItem(k)).slice(0,40));
            localStorage.removeItem(k);
          }
        }
      }catch(e){}
      return out;
    }""")
    log(f"  dihapus SS: {cleared.get('ss')}")
    log(f"  dihapus LS: {cleared.get('ls')}")

    log("\n=== 2. buka /verify/captcha -> SDK minta tracking FRESH ===")
    TRK["new"] = ""
    try:
        pg.goto("https://shopee.co.id/verify/captcha", wait_until="domcontentloaded",
                timeout=55000)
    except Exception:
        pass
    pg.wait_for_timeout(12000)

    if not TRK["new"]:
        log("  belum dapat tracking, trigger cart/mini")
        try:
            pg.evaluate("""async()=>{try{await fetch('/api/v4/cart/mini?need_buyer_dp_info=1',{credentials:'include'});}catch(e){}}""")
        except Exception:
            pass
        pg.wait_for_timeout(8000)

    log(f"  tracking final: {len(TRK['new'])}B")

    st = pg.evaluate(STATE)
    log(f"  canvas={st['n']} txt={str(st.get('txt',''))[:110].replace(chr(10),' | ')}")

    # === 3. kalau canvas ada, langsung solve ===
    tok = ""
    if st["n"]:
        for att in range(3):
            g = pg.evaluate(GRAB)
            if not g.get("ok"):
                pg.wait_for_timeout(3500)
                continue
            log(f"\n  solve#{att+1} puz={len(g['puz'])}B pc={len(g.get('pc') or '')}B rect={g['rect']}")
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
                log("    ✅ released")
            except Exception as e:
                log(f"    drag err {str(e)[:50]}")

            pg.wait_for_timeout(10000)
            st2 = pg.evaluate(STATE)
            log(f"    -> canvas={st2['n']} txt={str(st2.get('txt',''))[:90].replace(chr(10),' | ')}")
            pg.screenshot(path=f"/root/shopee-verify/CT_s{att+1}.png")
            if st2["n"] == 0:
                log("    🎉 canvas hilang — kemungkinan LOLOS")
                break

    # === 4. setelah captcha, coba send_vcode dari page ===
    log("\n=== 4. send_vcode dari page ===")
    r4 = pg.evaluate("""async (a)=>{
      const {phone} = a;
      const out={tries:[]};
      // settings dulu (seed fresh)
      const js=await (await fetch('/api/v4/otp/get_settings_v2',{method:'POST',
        credentials:'include',
        headers:{'Content-Type':'application/json','af-ac-enc-dat':'0123456789abcdef'},
        body:JSON.stringify({operation:8,phone})})).json();
      out.settings={err:js.error, seed:((js.data||{}).seed||'').slice(0,20),
                    ch:(js.data||{}).available_channels,
                    need_cap:(js.data||{}).need_captcha,
                    scene:(js.data||{}).captcha_scene};
      const seed=(js.data||{}).seed;
      for(const ch of [3,2,1]){
        const j=await (await fetch('/api/v4/otp/send_vcode',{method:'POST',
          credentials:'include',
          headers:{'Content-Type':'application/json','af-ac-enc-dat':'0123456789abcdef'},
          body:JSON.stringify({phone,channel:ch,operation:8,seed})})).json();
        out.tries.push({ch,err:j.error,trk:(j.data||{}).otp_tracking_id});
        if(j.error===0){out.win=ch;break;}
      }
      return out;
    }""", {"phone": NEWPHONE})
    log(f"  settings: {r4.get('settings')}")
    for t in (r4.get("tries") or []):
        log(f"  ch={t.get('ch')} err={t.get('err')}")

    if r4.get("win"):
        log(f"\n  🎉🎉🎉 OTP TERKIRIM ch={r4['win']}")
        json.dump({"phone": NEWPHONE, "ch": r4["win"],
                   "seed": (r4.get("settings") or {}).get("seed"),
                   "tries": r4.get("tries")},
                  open("/root/shopee-verify/OTP_SENT.json", "w"), indent=1)

    json.dump({"trk_all": [t[:60] for t in TRK["all"]], "gen": GEN["r"],
               "canvas": st["n"], "send": r4},
              open("/root/shopee-verify/CT.json", "w"), indent=1)

    pg.screenshot(path="/root/shopee-verify/CT_final.png", full_page=True)
    br.close()

log("\n=== SELESAI ===")
