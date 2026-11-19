"""FULL_E2E18.py — satu run: verify(vcode) -> redirect vcode_token -> dump chunk finalisasi -> submit.

Kunci yang terbukti:
  verify_vcode {phone, vcode, operation:18, m_token:<cp_token>} -> data.vcode_token
  PageUserPhone: successCallback({vcodeToken,seed}) -> location.href = D2(search,{vcode_token,seed})

Langkah:
  1. warm + init_v2 + settings op18
  2. verify_vcode -> vcode_token
  3. buka /user/account/phone?vcode_token=X&seed=Y  (harusnya TANPA redirect)
  4. tunggu chunk 58331/93679/93651 ter-load, dump semua resource JS baru
  5. grep endpoint finalisasi dari chunk itu
  6. submit kalau ketemu
"""
import json, re, sys, os, time

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_zax.txt"
PH = sys.argv[2] if len(sys.argv) > 2 else "62895806564446"
CODE = sys.argv[3] if len(sys.argv) > 3 else ""
PROXY = os.environ.get("SHOPEE_PROXY", "")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/FE.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright

if not CODE:
    log("❌ butuh kode OTP")
    sys.exit(1)

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
        "window.chrome={runtime:{}};"
        "Object.defineProperty(navigator,'languages',{get:()=>['id-ID','id','en']});")
    pg = ctx.new_page()

    # intercept semua response API untuk deteksi endpoint finalisasi
    NET = []

    def onresp(r):
        u = r.url
        if "/api/v4/" in u and ("phone" in u or "otp" in u or "management" in u):
            try:
                b = r.text()
            except Exception:
                b = ""
            NET.append({"u": u.split("shopee.co.id")[-1][:90], "s": r.status, "b": b[:600]})
            log(f"  NET {r.status} {u.split('shopee.co.id')[-1][:60]} :: {b[:150]}")

    pg.on("response", onresp)

    log("=== 1. warm ===")
    try:
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    pg.wait_for_timeout(11000)

    # === 2. init_v2 + settings ===
    log("\n=== 2. init_v2 + settings op18 ===")
    st = pg.evaluate("""async (phone)=>{
      const out={};
      try{
        const i=await (await fetch('/api/v4/account/management/change_phone_init_v2',
          {method:'POST',credentials:'include',
           headers:{'Content-Type':'application/json'},
           body:JSON.stringify({phone,seq_no:null})})).json();
        const id=i.data||{};
        out.init_err=i.error; out.cp=id.change_phone_token||'';
        const g=await (await fetch('/api/v4/otp/get_settings_v2',
          {method:'POST',credentials:'include',
           headers:{'Content-Type':'application/json'},
           body:JSON.stringify({phone,operation:18})})).json();
        const gd=g.data||{};
        out.set_err=g.error; out.seed=gd.seed||''; out.need_cap=gd.need_captcha;
        return out;
      }catch(e){out.ex=String(e).slice(0,120);return out;}
    }""", PH)
    cp = st.get("cp") or ""
    seed = st.get("seed") or ""
    log(f"  init err={st.get('init_err')} cp={len(cp)}B seed={seed[:20]}")

    # === 3. verify ===
    log(f"\n=== 3. verify_vcode {CODE} ===")
    vr = pg.evaluate("""async (a)=>{
      try{
        const r=await fetch('/api/v4/otp/verify_vcode',{method:'POST',
          credentials:'include',headers:{'Content-Type':'application/json'},
          body:JSON.stringify(a.b)});
        return {s:r.status,j:await r.json()};
      }catch(e){return {ex:String(e).slice(0,80)};}
    }""", {"b": {"phone": PH, "vcode": CODE, "operation": 18, "m_token": cp}})
    err = (vr.get("j") or {}).get("error")
    log(f"  err={err} {json.dumps(vr.get('j'))[:200]}")
    if err != 0:
        log("  ❌ verify gagal")
        br.close()
        sys.exit(2)
    vt = ((vr.get("j") or {}).get("data") or {}).get("vcode_token") or ""
    log(f"  ✅ vcode_token {len(vt)}B")

    # simpan token
    json.dump({"phone": PH, "cp": cp, "seed": seed, "vcode_token": vt},
              open("/root/shopee-verify/FE_ok.json", "w"), indent=1)

    # === 4. buka /user/account/phone DENGAN vcode_token sebagai query ===
    log("\n=== 4. buka /user/account/phone + vcode_token ===")
    urls = [
        f"https://shopee.co.id/user/account/phone?step=confirm&vcode_token={vt}&seed={seed}&operation=18",
        f"https://shopee.co.id/user/account/phone/confirm?vcode_token={vt}&seed={seed}&operation=18",
        f"https://shopee.co.id/user/account/phone?vcode_token={vt}&seed={seed}",
    ]
    for u in urls:
        log(f"  goto {u[:110]}")
        try:
            pg.goto(u, wait_until="domcontentloaded", timeout=50000)
        except Exception:
            pass
        pg.wait_for_timeout(12000)
        cur = pg.evaluate("()=>location.href")
        canv = pg.evaluate("()=>document.querySelectorAll('canvas').length")
        txt = pg.evaluate("()=>(document.body.innerText||'').slice(0,200)")
        log(f"    -> {cur[:100]}")
        log(f"       canvas={canv} txt={txt[:130].replace(chr(10),' | ')}")
        if "/verify/" not in cur:
            log("  ★ TIDAK redirect — halaman render!")
            break

    # === 5. dump chunk terbaru ===
    log("\n=== 5. resource JS baru ===")
    res = pg.evaluate("""()=>performance.getEntriesByType('resource')
      .map(e=>e.name).filter(n=>n.includes('.js'))""")
    log(f"  {len(res)} resource")

    # search chunk ids
    want = ("58331", "93679", "93651", "5427", "8963", "9308", "853", "2735", "8167", "1250", "5358")
    found = [u for u in res if any(w in u for w in want)]
    log(f"  chunk diminta: {len(found)}")
    for u in found[:10]:
        log(f"    {os.path.basename(u)[:70]}")

    # tag: bundle dengan nama Profile / Phone
    if "58331" not in str(found):
        log("  ⚠️ chunk 58331 tidak ke-load (halaman tidak render form)")
        # kalau halaman berisi input, coba submit manual
        form = pg.evaluate("""()=>({
          inputs:[...document.querySelectorAll('input')].map(i=>({t:i.type,n:i.name,p:i.placeholder})),
          buttons:[...document.querySelectorAll('button')].map(b=>(b.innerText||'').slice(0,30))
        })""")
        log(f"  form: {json.dumps(form)[:300]}")

    pg.screenshot(path="/root/shopee-verify/FE.png", full_page=True)
    json.dump({"net": NET[-30:], "res": res[:300], "found": found},
              open("/root/shopee-verify/FE.json", "w"), indent=1)
    br.close()

log("\n=== SELESAI ===")
