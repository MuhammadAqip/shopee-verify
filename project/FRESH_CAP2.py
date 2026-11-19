"""FRESH_CAP2.py — action_type=3 (Challenge) -> captcha HARUS render.

Bukti terakhir:
  cart/mini -> {"0":3, "2":true, "3":90309999}   <- 0:3 = Challenge!
  bundle captcha dimuat: security-captcha.cache.susercontent.com/api/v4/50017751/client

Berarti: challenge dipicu, halaman harus render captcha.
Yang kurang: tunggu cukup lama + klik tombol "Coba Lagi" kalau ada.

Flow:
  1. buka /verify/captcha, tunggu SAMPAI canvas muncul (max 90s)
  2. kalau "Coba Lagi" -> klik, tunggu lagi
  3. kalau canvas -> SadCaptcha solve + drag handle
  4. setelah lolos -> page-context change_phone + send_vcode
"""
import json, sys, time, base64

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
    open("/root/shopee-verify/FRS2.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright
import requests

net = []


def onresp(r):
    u = r.url
    if "/api/v4/" not in u and "security-captcha" not in u:
        return
    short = u.split("shopee.co.id")[-1].split("?")[0][:70]
    try:
        b = r.text()
    except Exception:
        b = ""
    net.append({"u": short, "s": r.status, "b": b[:1500]})
    if "captcha" in short and len(b) < 900:
        log(f"  NET {r.status} {short[:55]} :: {b[:130]}")


def click_any(pg, sels, wait=1800):
    for sel in sels:
        try:
            l = pg.locator(sel)
            if l.count() and l.first.is_visible():
                l.first.click(timeout=2500, force=True)
                pg.wait_for_timeout(wait)
                return sel
        except Exception:
            pass
    return None


def state(pg):
    return pg.evaluate("""()=>{
      const cs=[...document.querySelectorAll('canvas')].map(c=>{
        const r=c.getBoundingClientRect();
        return {w:Math.round(r.width),h:Math.round(r.height),
                bw:c.width,bh:c.height,x:Math.round(r.x),y:Math.round(r.y)};
      }).filter(o=>o.w>20&&o.h>10);
      const btns=[...document.querySelectorAll('div,button,span')]
        .map(e=>{
          const r=e.getBoundingClientRect();
          return {t:(e.innerText||'').trim().slice(0,22), x:Math.round(r.x),
                  y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)};
        })
        .filter(o=>o.w>40&&o.w<220&&o.h>20&&o.h<70&&o.t)
        .slice(0,14);
      return {canvas: cs, btns,
              txt:(document.body.innerText||'').slice(0,300),
              url: location.href.slice(0,110)};
    }""")


def grab(pg):
    return pg.evaluate("""()=>{
      const out={ok:false};
      const all=[...document.querySelectorAll('canvas')].map(c=>{
        const r=c.getBoundingClientRect();
        return {el:c, w:r.width, h:r.height, x:r.x, y:r.y};
      }).filter(o=>o.w>20&&o.h>10);
      if(!all.length) return out;
      all.sort((a,b)=>(b.w*b.h)-(a.w*a.h));
      const big=all[0];
      const small=all.slice(1).sort((a,b)=>(a.w*a.h)-(b.w*b.h))[0];
      try{ out.puz=big.el.toDataURL('image/png'); }catch(e){}
      if(small){ try{ out.pc=small.el.toDataURL('image/png'); }catch(e){} }
      out.rect={x:big.x,y:big.y,w:big.w,h:big.h};
      out.n=all.length;
      out.ok = !!(out.puz && out.puz.length>5000);
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

    log("=== 1. /verify/captcha ===")
    try:
        pg.goto("https://shopee.co.id/verify/captcha", wait_until="domcontentloaded",
                timeout=55000)
    except Exception as e:
        log(f"  goto err {str(e)[:50]}")
    pg.wait_for_timeout(9000)
    click_any(pg, ['button:has-text("Setuju")', 'text=Bahasa Indonesia'])

    # === 2. TUNGGU canvas / dialog ===
    log("\n=== 2. tunggu canvas (max 100s) ===")
    got = False
    for i in range(20):
        pg.wait_for_timeout(5000)
        st = state(pg)
        ncv = len(st.get("canvas", []))
        log(f"  [{i*5+5:3d}s] canvas={ncv} url={st.get('url', '')[-40:]}")
        if ncv >= 1:
            log(f"  ★ CANVAS MUNCUL: {st['canvas']}")
            got = True
            break
        # coba klik "Coba Lagi" / "Verifikasi"
        hit = click_any(pg, [
            'text=Coba Lagi', 'button:has-text("Coba Lagi")',
            'button:has-text("Verifikasi")', 'text=Verifikasi',
            'button:has-text("Mulai")', 'button:has-text("Lanjut")',
            'button:has-text("Setuju")'])
        if hit:
            log(f"  klik {hit}")
            pg.wait_for_timeout(6000)

    st = state(pg)
    log(f"\n  txt: {st.get('txt', '')[:180].replace(chr(10), ' | ')}")
    log(f"  btns: {[(b['t'], b['x'], b['y']) for b in st.get('btns', [])[:8]]}")
    pg.screenshot(path="/root/shopee-verify/FRS2_wait.png", full_page=False)

    # === 3. SOLVE kalau canvas ada ===
    if got:
        for att in range(3):
            g = grab(pg)
            if not g.get("ok"):
                log(f"  [{att+1}] grab gagal")
                pg.wait_for_timeout(4000)
                continue
            log(f"\n=== 3. solve#{att+1} puz={len(g['puz'])}B pc={len(g.get('pc') or '')}B ===")
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
                pg.wait_for_timeout(4000)
                continue
            log(f"  ★ prop={prop}")

            # cari handle slider
            h = pg.evaluate("""()=>{
              const out=[];
              for(const e of document.querySelectorAll('div,button,span,svg')){
                const r=e.getBoundingClientRect();
                if(r.width<25||r.width>85||r.height<25||r.height>85) continue;
                if(e.querySelector('canvas')) continue;
                const sty=getComputedStyle(e);
                if(sty.cursor && (sty.cursor.includes('grab')||sty.cursor.includes('pointer'))){
                  out.push({x:r.x+r.width/2,y:r.y+r.height/2,w:r.width,
                            cls:(e.className||'').toString().slice(0,30)});
                }
              }
              return out.slice(0,6);
            }""")
            log(f"  handle cursor: {[(round(x['x']),round(x['y'])) for x in h]}")
            if not h:
                # fallback: elemen paling kanan di baris bawah
                h = pg.evaluate("""()=>{
                  const out=[];
                  for(const e of document.querySelectorAll('div,span')){
                    const r=e.getBoundingClientRect();
                    if(r.width<25||r.width>75||r.height<25||r.height>75) continue;
                    if(r.y<200) continue;
                    out.push({x:r.x+r.width/2,y:r.y+r.height/2,w:r.width});
                  }
                  out.sort((a,b)=>(b.y-a.y)||(a.x-b.x));
                  return out.slice(0,5);
                }""")
            if not h:
                log("  ❌ handle tidak ketemu")
                continue

            hx, hy = h[0]["x"], h[0]["y"]
            w = g["rect"]["w"] or 280
            dist = prop * w
            log(f"  drag {hx:.0f},{hy:.0f} +{dist:.0f}px (w={w})")
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

            pg.wait_for_timeout(9000)
            cur = pg.url
            log(f"  -> {cur.split('shopee.co.id')[-1][:60]}")
            pg.screenshot(path=f"/root/shopee-verify/FRS2_s{att+1}.png", full_page=False)
            st2 = state(pg)
            if len(st2.get("canvas", [])) == 0 and "/verify/" not in cur:
                log("  🎉 LOLOS")
                break

    # === 4. page-context change_phone + send_vcode ===
    log("\n=== 4. change_phone + send_vcode (page-context, WA) ===")
    r = pg.evaluate("""async (phone)=>{
      const P=async(p,b)=>{try{const res=await fetch(p,{method:'POST',
        credentials:'include',headers:{'content-type':'application/json'},
        body:JSON.stringify(b||{})});return await res.json();}catch(e){return{ex:String(e).slice(0,50)}}};
      const out={};
      out.init = await P('/api/v4/account/management/change_phone_init');
      const seq=(out.init.data||{}).seq_no;
      out.init2 = await P('/api/v4/account/management/change_phone_init_v2',
                          {phone:phone, seq_no:seq});
      out.settings = await P('/api/v4/otp/get_settings_v2',
                             {operation:8, phone:phone});
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

    log(f"  init err={r.get('init',{}).get('error')} seq={str((r.get('init',{}).get('data') or {}).get('seq_no'))[:22]}")
    log(f"  init2 err={r.get('init2',{}).get('error')} ivs={(r.get('init2',{}).get('data') or {}).get('ivs_required')}")
    log(f"  settings err={r.get('settings',{}).get('error')} seed={str((r.get('settings',{}).get('data') or {}).get('seed'))[:22]}")
    sent = False
    for x in r.get("sends", []):
        log(f"  ch={x['ch']} err={x['err']}")
        if x["err"] == 0:
            dd = x.get("data") or {}
            log(f"  ✅✅✅ OTP TERKIRIM WA ch={x['ch']} tracking={str(dd.get('otp_tracking_id',''))[:40]}")
            json.dump({"tracking": dd.get("otp_tracking_id"), "ch": x["ch"],
                       "seed": r.get("seed"), "seq": r.get("seq")},
                      open("/root/shopee-verify/OTP_SENT.json", "w"), indent=1)
            sent = True
            break

    if not sent:
        log("  ❌ OTP belum terkirim")

    pg.screenshot(path="/root/shopee-verify/FRS2_final.png", full_page=True)
    json.dump({"net": net[-50:], "otp": r},
              open("/root/shopee-verify/FRS2.json", "w"), indent=1)
    cks = ctx.cookies()
    open("/root/shopee-verify/ck_frs2.txt", "w").write(
        "; ".join(f"{c['name']}={c['value']}" for c in cks))
    br.close()

log("\n=== SELESAI ===")
