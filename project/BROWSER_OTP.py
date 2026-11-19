"""BROWSER_OTP.py — captcha via browser, solve SadCaptcha, lalu OTP.

Kenapa browser: get_config butuh x-sap-* header yang hanya SDK generate.
Browser = SDK jalan sendiri = captcha render + encrypted_security_data siap.

Alur:
  1. Buka homepage dengan cookie ck_1659 (ivs_required=False)
  2. trigger cart/mini -> SDK redirect ke /verify/captcha
  3. Di halaman captcha: extract canvas, solve pakai SadCaptcha
     (deteksi tipe dulu: canvas/imgs), drag handle via page.mouse
  4. Setelah lolos -> cookie session punya captcha pass
  5. Buat change_phone_init dari page-context fetch (SDK sign)
  6. send_vcode dari page-context -> OTP
"""
import json, sys, time, base64

sys.path.insert(0, "/root/shopee-farm")

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1659.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283191104601"
BUDGET = int(sys.argv[3]) if len(sys.argv) > 3 else 600

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
SADKEY = open("/root/shopee-farm/bot_key.txt").read().strip()
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/BOTP.log", "a").write(m + "\n")


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
    if "/api/v4/" not in u:
        return
    short = u.split("shopee.co.id")[-1].split("?")[0][:80]
    try:
        b = r.text()
    except Exception:
        b = ""
    net.append({"u": short, "s": r.status, "b": b[:900]})
    if any(k in short for k in ("captcha", "otp/", "change_phone", "ivs/")):
        log(f"  NET {r.status} {short} :: {b[:110]}")


def modals(pg):
    for sel in ('button:has-text("Setuju")', 'text=Setuju',
                'text=Bahasa Indonesia'):
        try:
            l = pg.locator(sel)
            if l.count() and l.first.is_visible():
                l.first.click(timeout=2200, force=True)
                pg.wait_for_timeout(1500)
                return True
        except Exception:
            pass
    return False


SOLVE_JS = """()=>{
  const canv = [...document.querySelectorAll('canvas')].map(c=>{
    const r=c.getBoundingClientRect();
    return {w:c.width,h:c.height,x:r.x,y:r.y,drag:c.draggable,cls:c.className};
  });
  const btns = [...document.querySelectorAll('div,button')].filter(e=>{
    const r=e.getBoundingClientRect();
    return r.width>=30 && r.width<=70 && r.height>=30 && r.height<=70
      && e.querySelector('svg') && !e.querySelector('canvas');
  }).map(e=>{const r=e.getBoundingClientRect();
    return {x:r.x,y:r.y,w:r.width,h:r.height,cls:(e.className||'').slice(0,30)};});
  return {canv, btns: btns.slice(0,8),
          url: location.href.slice(0,80),
          txt: (document.body.innerText||'').slice(0,120)};
}"""


def grab_canvas(pg):
    """Ambil b64 puzzle + piece + posisi handle."""
    return pg.evaluate("""()=>{
      const out = {puzzle:null, piece:null, handle:null, ok:false};
      const all = [...document.querySelectorAll('canvas')].map(c=>{
        const r=c.getBoundingClientRect();
        return {el:c, w:r.width, h:r.height, x:r.x, y:r.y, drag:c.draggable};
      }).filter(o=>o.w>10&&o.h>10);
      if (!all.length) return out;
      // puzzle = terbesar (biasanya 280x150)
      all.sort((a,b)=>(b.w*b.h)-(a.w*a.h));
      const big = all[0];
      const small = all.slice(1).sort((a,b)=>(a.w*a.h)-(b.w*b.h))[0];
      try { out.puzzle = big.el.toDataURL('image/png'); } catch(e){}
      if (small) { try { out.piece = small.el.toDataURL('image/png'); } catch(e){} }
      if (out.puzzle) out.ok = out.puzzle.length > 5000;
      out.puzzleRect = {x:big.x,y:big.y,w:big.w,h:big.h};
      if (small) out.pieceRect = {x:small.x,y:small.y,w:small.w,h:small.h};
      out.count = all.length;
      return out;
    }""")


def find_handle(pg):
    return pg.evaluate("""()=>{
      const all=[...document.querySelectorAll('div,button')];
      const cands=[];
      for (const e of all){
        const r=e.getBoundingClientRect();
        if (r.width<28||r.width>80||r.height<28||r.height>80) continue;
        if (!e.querySelector('svg')) continue;
        if (e.querySelector('canvas')) continue;
        cands.push({x:r.x+r.width/2, y:r.y+r.height/2, w:r.width,
                    cls:(e.className||'').toString().slice(0,40)});
      }
      // urut kiri->kanan, ambil yang paling kanan-bawah (handle slider)
      cands.sort((a,b)=>(b.y-a.y)||(a.x-b.x));
      return cands.slice(0,6);
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

    log("=== 1. home ===")
    for a in range(4):
        try:
            pg.goto("https://shopee.co.id/", wait_until="domcontentloaded",
                    timeout=60000)
        except Exception:
            time.sleep(3)
            continue
        pg.wait_for_timeout(8000)
        modals(pg)
        log(f"  [{a+1}] {pg.url.split('shopee.co.id')[-1][:50]}")
        if "/verify/" not in pg.url:
            break

    log("\n=== 2. trigger -> /verify/captcha ===")
    for a in range(6):
        try:
            r = pg.evaluate("""async ()=>{
              try{
                const res=await fetch('/api/v4/cart/mini?need_buyer_dp_info=1',
                  {credentials:'include'});
                const j=await res.json();
                return {s:res.status, err:j.error};
              }catch(e){return {ex:String(e).slice(0,40)}}
            }""")
            log(f"  cart#{a+1} {r}")
        except Exception:
            pass
        pg.wait_for_timeout(5000)
        if "/verify/" in pg.url:
            log(f"  ★ {pg.url[:100]}")
            break

    if "/verify/" not in pg.url:
        log("  tidak redirect, paksa buka /verify/captcha")
        try:
            pg.goto("https://shopee.co.id/verify/captcha",
                    wait_until="domcontentloaded", timeout=50000)
        except Exception:
            pass
        pg.wait_for_timeout(7000)

    modals(pg)
    pg.wait_for_timeout(3000)

    st = pg.evaluate(SOLVE_JS)
    log(f"\n=== 3. state: canvas={len(st.get('canv', []))} btn={len(st.get('btns', []))} ===")
    log(f"  {st.get('txt', '')[:100]}")
    pg.screenshot(path="/root/shopee-verify/BOTP_before.png", full_page=False)

    # === 4. SOLVE LOOP ===
    for attempt in range(4):
        if time.time() - T0 > BUDGET - 200:
            log("  ⏰ waktu")
            break
        cv = pg.evaluate(SOLVE_JS)
        canv = cv.get("canv", [])
        if not canv:
            log(f"  [{attempt+1}] tidak ada canvas — tunggu")
            pg.wait_for_timeout(6000)
            modals(pg)
            continue

        log(f"  [{attempt+1}] canvas: {[(c['w'], c['h']) for c in canv]}")

        g = grab_canvas(pg)
        if not g.get("ok"):
            log("  puzzle belum paint, tunggu")
            pg.wait_for_timeout(5000)
            continue
        if not g.get("piece"):
            log("  piece tidak ada — coba drag handle saja")
        log(f"  puzzle b64 {len(g['puzzle'])}B piece {len(g.get('piece') or '')}B")

        # SadCaptcha
        pz_b64 = g["puzzle"].split(",", 1)[1]
        pc_b64 = (g.get("piece") or "").split(",", 1)[1] if g.get("piece") else ""
        prop = None
        try:
            r = requests.post("https://www.sadcaptcha.com/api/v1/puzzle",
                              params={"licenseKey": SADKEY},
                              json={"puzzleImageB64": pz_b64,
                                    "pieceImageB64": pc_b64}, timeout=60)
            log(f"  sad {r.status_code} {r.text[:90]}")
            if r.status_code == 200:
                prop = r.json().get("slideXProportion")
        except Exception as e:
            log(f"  sad err {str(e)[:60]}")

        if not prop:
            log("  ❌ tidak dapat prop, skip")
            pg.wait_for_timeout(4000)
            continue
        log(f"  ★ prop={prop}")

        # cari handle
        h = find_handle(pg)
        log(f"  handle kandidat: {[(round(x['x']),round(x['y'])) for x in h[:4]]}")
        if not h:
            log("  ❌ handle tidak ketemu")
            continue
        hx, hy = h[0]["x"], h[0]["y"]

        # drag handle: prop x puzzle width (280)
        pw_w = g["puzzleRect"]["w"] if g.get("puzzleRect") else 280
        dist = prop * pw_w
        log(f"  drag {hx:.0f},{hy:.0f} +{dist:.0f}px")

        try:
            pg.mouse.move(hx, hy)
            pg.wait_for_timeout(200)
            pg.mouse.down()
            pg.wait_for_timeout(300)
            steps = 22
            for i in range(1, steps + 1):
                p = i / steps
                e = p * p * (3 - 2 * p)
                pg.mouse.move(hx + e * dist, hy - 4 * min(1, p), steps=1)
                pg.wait_for_timeout(25 + (i % 5) * 8)
            pg.wait_for_timeout(400)
            pg.mouse.move(hx + dist + 2, hy - 4)
            pg.wait_for_timeout(300)
            pg.mouse.up()
            log("  ✅ drag released")
        except Exception as e:
            log(f"  drag err {str(e)[:60]}")

        pg.wait_for_timeout(8000)
        modals(pg)
        cur = pg.url
        log(f"  -> url {cur.split('shopee.co.id')[-1][:60]}")
        pg.screenshot(path=f"/root/shopee-verify/BOTP_try{attempt+1}.png",
                      full_page=False)
        if "/verify/" not in cur:
            log("  🎉🎉 LOLOS CAPTCHA")
            break

    # === 5. verifikasi sesi ===
    log("\n=== 5. cek sesi ===")
    try:
        r = pg.evaluate("""async ()=>{
          try{
            const res=await fetch('/api/v4/account/basic/get_account_info',
              {credentials:'include'});
            const j=await res.json();
            return {s:res.status, err:j.error,
                    user:(j.data||{}).username};
          }catch(e){return {ex:String(e).slice(0,40)}}
        }""")
        log(f"  account: {r}")
    except Exception as e:
        log(f"  {str(e)[:50]}")

    # === 6. change_phone via page-context ===
    log("\n=== 6. change_phone + send_vcode (page-context) ===")
    r = pg.evaluate("""async (phone)=>{
      const out = {};
      const P = async (path, body) => {
        try {
          const res = await fetch(path, {method:'POST', credentials:'include',
            headers:{'content-type':'application/json'},
            body: JSON.stringify(body||{})});
          return await res.json();
        } catch(e){ return {ex:String(e).slice(0,60)}; }
      };
      out.init = await P('/api/v4/account/management/change_phone_init');
      const seq = (out.init.data||{}).seq_no;
      out.init2 = await P('/api/v4/account/management/change_phone_init_v2',
                          {phone: phone, seq_no: seq});
      out.settings = await P('/api/v4/otp/get_settings_v2',
                             {operation: 8, phone: phone});
      const seed = (out.settings.data||{}).seed;
      out.sends = [];
      for (const ch of [3,2,1]) {
        const s = await P('/api/v4/otp/send_vcode',
          {phone: phone, channel: ch, operation: 8, seed: seed});
        out.sends.push({ch, err: s.error, data: s.data});
        if (s.error === 0) break;
      }
      out.seq = seq; out.seed = seed;
      return out;
    }""", NEWPHONE)

    log(f"  init: err={r.get('init',{}).get('error')} seq={(r.get('init',{}).get('data') or {}).get('seq_no','')[:24]}")
    log(f"  init2: err={r.get('init2',{}).get('error')} ivs={(r.get('init2',{}).get('data') or {}).get('ivs_required')}")
    log(f"  settings: err={r.get('settings',{}).get('error')} seed={(r.get('settings',{}).get('data') or {}).get('seed','')[:24]}")
    for x in r.get("sends", []):
        log(f"  send ch={x['ch']} err={x['err']}")
        if x["err"] == 0:
            dd = x.get("data") or {}
            log(f"  ✅✅ OTP TERKIRIM tracking={str(dd.get('otp_tracking_id',''))[:40]}")
            json.dump({"tracking": dd.get("otp_tracking_id"),
                       "ch": x["ch"], "seq": r.get("seq"),
                       "seed": r.get("seed")},
                      open("/root/shopee-verify/OTP_SENT.json", "w"), indent=1)
            break

    pg.screenshot(path="/root/shopee-verify/BOTP_final.png", full_page=True)
    cks = ctx.cookies()
    open("/root/shopee-verify/ck_botp.txt", "w").write(
        "; ".join(f"{c['name']}={c['value']}" for c in cks))
    json.dump({"net": net[-70:], "otp": r}, open("/root/shopee-verify/BOTP.json", "w"), indent=1)
    br.close()

log("\n=== SELESAI ===")
