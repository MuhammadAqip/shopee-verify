"""FASE2.py — verify kode + KLIK semua, MITM aktif, dump chunk finalisasi.

Fase 2 dari REA_MITM. Butuh kode OTP yang baru dikirim (RM_otp.json).

  1. warm
  2. init_v2 + settings op18
  3. verify_vcode {vcode, m_token} -> vcode_token
  4. buka /user/account/phone  (semua varian)
  5. KLIK semua tombol di setiap halaman
  6. tunggu chunk 58331/93679/93651
  7. dump performance resource + semua endpoint
  8. TULIS body finalisasi persis kalau ketemu
"""
import json, sys, os, time, re

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_zax.txt"
CODE = sys.argv[2] if len(sys.argv) > 2 else ""
PROXY = os.environ.get("SHOPEE_PROXY", "http://127.0.0.1:18080")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
T0 = time.time()
JSONL = "/root/shopee-verify/MITM2.jsonl"


def log(*a):
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/F2.log", "a").write(m + "\n")


if not CODE:
    log("❌ butuh kode OTP")
    sys.exit(1)

otp = {}
try:
    otp = json.load(open("/root/shopee-verify/RM_otp.json"))
except Exception:
    pass
PH = otp.get("phone") or "62895806564446"

ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright


def rec(kind, obj):
    with open(JSONL, "a") as f:
        f.write(json.dumps({**obj, "kind": kind, "t": round(time.time() - T0, 2)},
                           ensure_ascii=False) + "\n")


with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,900",
        "--disable-blink-features=AutomationControlled", "--lang=id-ID",
        "--use-gl=swiftshader", "--enable-webgl"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 900},
                         timezone_id="Asia/Jakarta",
                         proxy={"server": PROXY} if PROXY else None)
    ctx.add_cookies(cookies)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{},loadTimes:function(){},csi:function(){}};"
        "Object.defineProperty(navigator,'languages',{get:()=>['id-ID','id','en']});"
        "Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});")
    pg = ctx.new_page()

    def onreq(r):
        if "/api/v" not in r.url:
            return
        try:
            h = dict(r.headers)
        except Exception:
            h = {}
        rec("REQ", {"url": r.url[:300], "method": r.method,
                    "body": (r.post_data or "")[:4000] if r.post_data else None,
                    "sap": {k: v for k, v in h.items()
                            if k.lower().startswith(("x-sap", "af-", "x-sz"))}})
        sh = r.url.split("shopee.co.id")[-1][:80]
        if any(x in r.url for x in ("phone", "otp", "management", "verify")):
            log(f"  → {r.method} {sh}")
            if r.post_data:
                log(f"      body: {r.post_data[:220]}")

    def onresp(r):
        if "/api/v" not in r.url:
            return
        try:
            b = r.text()
        except Exception:
            b = ""
        rec("RSP", {"url": r.url.split("shopee.co.id")[-1][:100],
                    "status": r.status, "body": b[:3000]})
        if any(x in r.url for x in ("phone", "otp", "management", "verify")):
            log(f"  ← {r.status} {r.url.split('shopee.co.id')[-1][:55]} :: {b[:160]}")

    pg.on("request", onreq)
    pg.on("response", onresp)

    log("=== 1. warm ===")
    try:
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    pg.wait_for_timeout(12000)

    # === 2. init + settings ===
    log("\n=== 2. init_v2 + settings op18 ===")
    st = pg.evaluate("""async (phone)=>{
      const out={};
      try{
        const i=await (await fetch('/api/v4/account/management/change_phone_init_v2',
          {method:'POST',credentials:'include',
           headers:{'Content-Type':'application/json'},
           body:JSON.stringify({phone,seq_no:null})})).json();
        const id=i.data||{};
        out.init=i.error; out.cp=id.change_phone_token||'';
        const g=await (await fetch('/api/v4/otp/get_settings_v2',
          {method:'POST',credentials:'include',
           headers:{'Content-Type':'application/json'},
           body:JSON.stringify({phone,operation:18})})).json();
        const gd=g.data||{};
        out.set=g.error; out.seed=gd.seed||''; out.cap=gd.need_captcha;
        return out;
      }catch(e){out.ex=String(e).slice(0,100);return out;}
    }""", PH)
    cp = st.get("cp") or ""
    seed = st.get("seed") or ""
    log(f"  init={st.get('init')} cp={len(cp)}B seed={seed[:18]} cap={st.get('cap')}")

    # === 3. verify ===
    log(f"\n=== 3. verify {CODE} ===")
    vr = pg.evaluate("""async (a)=>{
      try{
        const r=await fetch('/api/v4/otp/verify_vcode',{method:'POST',
          credentials:'include',headers:{'Content-Type':'application/json'},
          body:JSON.stringify(a.b)});
        return {s:r.status,j:await r.json()};
      }catch(e){return {ex:String(e).slice(0,70)};}
    }""", {"b": {"phone": PH, "vcode": CODE, "operation": 18, "m_token": cp}})
    err = (vr.get("j") or {}).get("error")
    log(f"  err={err}")
    vt = ""
    if err == 0:
        vt = ((vr.get("j") or {}).get("data") or {}).get("vcode_token") or ""
        log(f"  ✅ vcode_token {len(vt)}B")
        json.dump({"phone": PH, "cp": cp, "seed": seed, "vcode_token": vt},
                  open("/root/shopee-verify/F2_ok.json", "w"), indent=1)
    else:
        log("  ❌ verify gagal — stop")
        br.close()
        sys.exit(2)

    # === 4. buka + klik tiap halaman ===
    log("\n=== 4. halaman finalisasi + klik ===")
    pages = [
        ("phone-basic", "https://shopee.co.id/user/account/phone"),
        ("phone-vtok", f"https://shopee.co.id/user/account/phone?vcode_token={vt}&seed={seed}&operation=18"),
        ("settings", "https://shopee.co.id/user/account/settings"),
        ("security", "https://shopee.co.id/user/account/security"),
    ]
    for tag, u in pages:
        log(f"\n  --- {tag}")
        try:
            pg.goto(u, wait_until="domcontentloaded", timeout=50000)
        except Exception:
            pass
        pg.wait_for_timeout(11000)
        cur = pg.evaluate("()=>location.href")
        canv = pg.evaluate("()=>document.querySelectorAll('canvas').length")
        body_txt = pg.evaluate("()=>(document.body.innerText||'').slice(0,180)")
        log(f"      {cur[:90]}")
        log(f"      canvas={canv} txt={body_txt[:110].replace(chr(10),' | ')}")

        # cek apakah ada input telepon (= form render)
        form = pg.evaluate("""()=>({
          inputs:[...document.querySelectorAll('input')].map(i=>({t:i.type,n:i.name||'',ph:i.placeholder||''})).slice(0,8),
          btns:[...document.querySelectorAll('button')].map(b=>(b.innerText||'').trim().slice(0,28)).filter(Boolean).slice(0,8)
        })""")
        if form.get("inputs") or form.get("btns"):
            log(f"      form: {json.dumps(form)[:280]}")

        # klik semua tombol
        clicked = pg.evaluate("""()=>{
          const out=[];
          const els=[...document.querySelectorAll('button,a,div[role=button]')];
          let n=0;
          for(const e of els){
            const r=e.getBoundingClientRect();
            if(r.width<24||r.height<18) continue;
            if(r.y<0||r.y>1500) continue;
            const t=(e.innerText||'').trim().slice(0,36);
            if(!t) continue;
            if(/hapus|logout|keluar|delete|batal|cancel|bahasa|english|indonesia/i.test(t)) continue;
            try{ e.click(); out.push(t); n++; }catch(err){}
            if(n>=5) break;
          }
          return out;
        }""")
        if clicked:
            log(f"      klik: {clicked}")
            pg.wait_for_timeout(8000)

    # === 5. resource list + chunk ===
    log("\n=== 5. resource ===")
    res = pg.evaluate("""()=>performance.getEntriesByType('resource').map(e=>e.name)""")
    js = [u for u in res if ".js" in u]
    log(f"  {len(js)} JS")
    want = ("58331", "93679", "93651", "5427", "8963", "9308", "853", "2735", "8167", "5358", "1250")
    found = [u for u in js if any(w in u for w in want)]
    log(f"  chunk match: {len(found)}")
    for u in found[:12]:
        log(f"    {u.split('/')[-1][:70]}")
    json.dump(js, open("/root/shopee-verify/F2_js.json", "w"), indent=1)

    # === 6. endpoint baru ===
    log("\n=== 6. ENDPOINT dari MITM2 ===")
    seen = set()
    for line in open(JSONL):
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("kind") != "REQ":
            continue
        u = d.get("url", "")
        if "/api/v" in u:
            sh = u.split("shopee.co.id")[-1].split("?")[0]
            k = f"{d['method']} {sh}"
            if k not in seen:
                seen.add(k)
                if any(x in sh for x in ("phone", "otp", "management", "verify", "captcha")):
                    log(f"  {k}")
                    if d.get("body"):
                        log(f"       {d['body'][:180]}")

    pg.screenshot(path="/root/shopee-verify/F2.png", full_page=True)
    br.close()

log("\n=== SELESAI ===")
