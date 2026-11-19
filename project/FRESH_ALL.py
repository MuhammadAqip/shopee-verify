"""FRESH_ALL.py — SEMUA token diambil SEKALI, langsung dipakai (<180 detik).

Penemuan kunci dari ASSETS.json:
  SECURITY_REFRESH_INTERVAL = 180 detik
  -> encrypted_security_data + dfp_token expire 3 menit

Bug sebelumnya: SEC/DFP diambil dari browser, lalu requests dipanggil
lambat / retry -> token basi -> 31500200.

Fix: satu proses, satu sesi browser, tanpa jeda.
  1. buka shopee.co.id
  2. tunggu SDK ready, ambil getLongToken + getWebDeviceFingerprint
  3. SAAT ITU JUGA (dalam <5 detik) generate + solve + verify
  4. kalau captcha muncul di canvas, drag langsung
  5. OTP

Semua timing di-log supaya kelihatan jarak SEC -> verify.
"""
import json, sys, time, base64, os
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
    open("/root/shopee-verify/FA.log", "a").write(m + "\n")


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
    sh = u.split("shopee.co.id")[-1].split("?")[0][:64]
    if "captcha" in sh or "otp" in sh or "cart" in sh:
        try:
            b = r.text()
        except Exception:
            b = ""
        netlog.append({"u": sh, "s": r.status, "b": b[:1200]})
        log(f"  NET {r.status} {sh[:46]} :: {b[:120]}")


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

STATE = """()=>({
  url:location.href,
  n:[...document.querySelectorAll('canvas')].length,
  txt:(document.body.innerText||'').slice(0,220)
})"""

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
    pg.on("response", onresp)

    log("=== 1. buka shopee.co.id ===")
    try:
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    pg.wait_for_timeout(11000)

    log("\n=== 2. ambil SEC+DFP+DETAIL dari SDK ===")
    T_SEC = time.time()
    r = pg.evaluate(r"""
    (async () => {
      const out = {sec:null, dfp:null, meta:null, err:null};
      try {
        // ambil meta app details
        out.meta = window.__META_APP_DETAILS__ || null;

        const wc = window.webpackChunkshopee_pc;
        if(!wc){out.err='no_chunk';return out;}
        let req=null; wc.push([[('fa'+Date.now())],{},function(rr){req=rr;}]);
        if(!req){out.err='no_req';return out;}
        const m = req(16223);
        if(!m){out.err='no_16223';return out;}

        try{
          const v=await Promise.race([m.getLongToken(),
            new Promise((_,rj)=>setTimeout(()=>rj(new Error('to')),8000))]);
          if(typeof v==='string'&&v.length>100) out.sec=v;
        }catch(e){}

        try{
          const v=await Promise.race([m.getWebDeviceFingerprint(),
            new Promise((_,rj)=>setTimeout(()=>rj(new Error('to')),8000))]);
          const s=(typeof v==='string')?v:JSON.stringify(v);
          if(s&&s.length>4) out.dfp=s;
        }catch(e){}

        return out;
      } catch(e){ out.err=String(e).slice(0,180); return out; }
    })()
    """)
    SEC = r.get("sec") or ""
    DFP = r.get("dfp") or ""
    META = r.get("meta") or {}
    log(f"  SEC {len(SEC)}B | DFP {len(DFP)}B | meta keys={list(META.keys())[:4]}")
    log(f"  T+{time.time()-T_SEC:.1f}s ambil token")

    if len(SEC) < 100 or len(DFP) < 10:
        log("  ❌ token gagal")
        br.close()
        sys.exit(1)

    # simpan cookie terbaru (SDK mungkin set cookie baru)
    try:
        cs = ctx.cookies()
        s2 = "; ".join(f"{c['name']}={c['value']}"
                       for c in cs if c["domain"].endswith("shopee.co.id"))
        open("/root/shopee-verify/ck_fresh_after.txt", "w").write(s2)
    except Exception:
        pass

    # === 3. SEKARANG langsung request DARI DALAM PAGE (cookie + SEC fresh) ===
    log("\n=== 3. generate DARI PAGE (bukan requests) ===")
    r2 = pg.evaluate(r"""
    async (a) => {
      const out={};
      try{
        // init security sdk
        const wc = window.webpackChunkshopee_pc;
        let req=null; wc.push([[('fb'+Date.now())],{},function(rr){req=rr;}]);
        const m = req(16223);
        // generate captcha via helper SDK kalau ada
        const TRK = sessionStorage.getItem('@shopee-ac/tracking_id') || '';
        out.trk_len = TRK.length;

        // coba panggil generate lewat SDK
        const res = await fetch('/api/v4/anti_fraud/captcha/generate',{
          method:'POST', credentials:'include',
          headers:{'Content-Type':'application/json','af-ac-enc-dat':'0123456789abcdef'},
          body: JSON.stringify({})});
        out.gen_status = res.status;
        try{ out.gen = await res.json(); }catch(e){ out.gen_text = 'non-json'; }
        return out;
      }catch(e){ out.err=String(e).slice(0,150); return out; }
    }
    """, {})
    log(f"  {json.dumps(r2)[:400]}")

    # === 4. cek canvas ===
    st = pg.evaluate(STATE)
    log(f"\n  URL: {st['url'][:110]}")
    log(f"  canvas={st['n']} txt={st['txt'][:130].replace(chr(10),' | ')}")

    # === 5. kalau tidak render, coba ke /user/account/phone ===
    if st["n"] == 0:
        log("\n=== 5. coba /user/account/phone ===")
        try:
            pg.goto("https://shopee.co.id/user/account/phone",
                    wait_until="domcontentloaded", timeout=50000)
        except Exception:
            pass
        pg.wait_for_timeout(9000)
        st = pg.evaluate(STATE)
        log(f"  URL: {st['url'][:110]}")
        log(f"  canvas={st['n']} txt={st['txt'][:130].replace(chr(10),' | ')}")

    # === 6. kalau canvas ada -> solve ===
    if st["n"]:
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
                                         if g.get("pc") else ""}, timeout=60)
                log(f"    sad {rr.status_code} {rr.text[:80]}")
                if rr.status_code == 200:
                    prop = rr.json().get("slideXProportion")
            except Exception as e:
                log(f"    err {str(e)[:50]}")
            if prop is None:
                continue
            h = pg.evaluate(HANDLE)
            if not h:
                continue
            hx, hy = h[0]["x"], h[0]["y"]
            dist = prop * (g["rect"]["w"] or 280)
            log(f"    prop={prop} dist={dist:.0f}")
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
            pg.wait_for_timeout(9000)
            st2 = pg.evaluate(STATE)
            log(f"    -> canvas={st2['n']} url={st2['url'][:80]}")
            pg.screenshot(path=f"/root/shopee-verify/FA_s{att+1}.png")
            if st2["n"] == 0:
                break

    # === 7. send_vcode dari PAGE (cookie fresh) ===
    log("\n=== 7. send_vcode dari page ===")
    r3 = pg.evaluate("""async (a)=>{
      const {phone}=a; const out={tries:[]};
      const js=await (await fetch('/api/v4/otp/get_settings_v2',{method:'POST',
        credentials:'include',
        headers:{'Content-Type':'application/json','af-ac-enc-dat':'0123456789abcdef'},
        body:JSON.stringify({operation:8,phone})})).json();
      out.settings={err:js.error,seed:((js.data||{}).seed||'').slice(0,20),
                     ch:(js.data||{}).available_channels,
                     need_cap:(js.data||{}).need_captcha};
      const seed=(js.data||{}).seed;
      for(const ch of [3,2,1]){
        const j=await (await fetch('/api/v4/otp/send_vcode',{method:'POST',
          credentials:'include',
          headers:{'Content-Type':'application/json','af-ac-enc-dat':'0123456789abcdef'},
          body:JSON.stringify({phone,channel:ch,operation:8,seed})})).json();
        out.tries.push({ch,err:j.error,trk:(j.data||{}).otp_tracking_id});
        if(j.error===0){out.win=ch;out.tracking=(j.data||{}).otp_tracking_id;break;}
        if(j.error!==23500101) break;
      }
      return out;
    }""", {"phone": NEWPHONE})
    log(f"  settings: {r3.get('settings')}")
    for t in (r3.get("tries") or []):
        log(f"  ch={t.get('ch')} err={t.get('err')} trk={str(t.get('trk'))[:30]}")

    if r3.get("win"):
        log(f"\n  ✅✅✅ OTP TERKIRIM ch={r3['win']} tracking={r3.get('tracking')}")
        json.dump({"phone": NEWPHONE, "ch": r3["win"], "seed": (r3.get("settings") or {}).get("seed"),
                   "tracking": r3.get("tracking")},
                  open("/root/shopee-verify/OTP_SENT.json", "w"), indent=1)

    json.dump({"net": netlog[-40:], "meta_keys": list(META.keys()),
               "send": r3, "sec_len": len(SEC), "dfp_len": len(DFP)},
              open("/root/shopee-verify/FA.json", "w"), indent=1)
    pg.screenshot(path="/root/shopee-verify/FA_final.png", full_page=True)
    br.close()

log("\n=== SELESAI ===")
