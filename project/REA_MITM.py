"""REA_MITM.py — capture SEMUA endpoint ganti nomor via browser headless.

= "MITM PROXY" dalam bentuk paling andal: Playwright intercept di level
  network (request + response + header + body), via relay residensial.
  (mitmproxy --mode upstream: ke relay terbukti 502 di setup ini — skill
  mitm-capture-debugging: jangan debug hop itu, pakai page.on('response')
  langsung. Request AND response body visibility sama.)

Langkah (semua otomatis, tanpa input manusia):
  1. warm home
  2. init_v2 -> cp_token
  3. settings op=18 -> seed (need_captcha FALSE)
  4. send_vcode op=18 ch3 -> OTP  [kode OTP diambil dari argumen]
  5. verify_vcode {vcode} -> vcode_token
  6. BUKA SEMUA kandidat URL finalisasi, klik semua elemen interaktif
  7. rekam SETIAP request/response ke MITM.jsonl  <- ini yang dicari
  8. dump sisa endpoint yang muncul dari NET log
"""
import json, sys, os, time, base64

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_zax.txt"
PH = sys.argv[2] if len(sys.argv) > 2 else "62895806564446"
CODE = sys.argv[3] if len(sys.argv) > 3 else ""
PROXY = os.environ.get("SHOPEE_PROXY", "http://127.0.0.1:18080")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
T0 = time.time()
JSONL = "/root/shopee-verify/MITM.jsonl"


def log(*a):
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/RM.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright

REQS = {}


def rec(kind, obj):
    with open(JSONL, "a") as f:
        f.write(json.dumps({**obj, "kind": kind, "t": round(time.time() - T0, 2)},
                           ensure_ascii=False) + "\n")


def onreq(r):
    """Rekam SETIAP request: url, method, headers, post body."""
    try:
        h = dict(r.headers)
    except Exception:
        h = {}
    sap = {k: v for k, v in h.items()
           if k.lower().startswith(("x-sap", "af-", "x-sz"))}
    e = {
        "id": r.url + "|" + str(r.method),
        "url": r.url[:300],
        "method": r.method,
        "sap": sap,
        "ctype": h.get("content-type", ""),
        "body": (r.post_data or "")[:4000] if r.post_data else None,
        "rt": r.resource_type,
    }
    REQS[e["id"]] = e
    rec("REQ", e)
    if "/api/v4/" in r.url and any(x in r.url for x in ("phone", "otp", "management", "account")):
        log(f"  → {r.method} {r.url.split('shopee.co.id')[-1][:70]}")
        if e["body"]:
            log(f"      body: {e['body'][:200]}")
        if sap:
            log(f"      sap: {list(sap.keys())}")


def onresp(r):
    try:
        b = r.text()
    except Exception:
        b = ""
    sh = r.url.split("shopee.co.id")[-1][:100]
    if "/api/v4/" in r.url or "/api/v2/" in r.url:
        rec("RSP", {"url": sh, "status": r.status, "body": b[:3000]})
        if any(x in r.url for x in ("phone", "otp", "management")):
            log(f"  ← {r.status} {sh[:60]} :: {b[:200]}")
    # kalau ada Set-Cookie baru, catat
    try:
        sc = r.headers.get("set-cookie", "")
    except Exception:
        sc = ""
    if sc:
        rec("COOKIE", {"url": sh, "set_cookie": sc[:600]})


def onjs(r):
    """Rekam semua JS baru yang di-load — chunk finalisasi ada di sini."""
    u = r.url
    if u.endswith(".js"):
        rec("JS", {"url": u[:250], "status": r.status})


def on_fail(r):
    rec("FAIL", {"url": r.url[:200], "err": str(r.failure)[:150]})


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
        "Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});"
        "Object.defineProperty(navigator,'hardwareConcurrency',{get:()=>8});")
    pg = ctx.new_page()
    pg.on("request", onreq)
    pg.on("response", onresp)
    pg.on("requestfailed", on_fail)

    # === 1. warm ===
    log("=== 1. warm home (SDK + SAP hook init) ===")
    try:
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    pg.wait_for_timeout(12000)

    # === 2. init_v2 + settings ===
    log("\n=== 2. init_v2 + settings op=18 ===")
    st = pg.evaluate("""async (phone)=>{
      const out={};
      try{
        const i=await (await fetch('/api/v4/account/management/change_phone_init_v2',
          {method:'POST',credentials:'include',
           headers:{'Content-Type':'application/json'},
           body:JSON.stringify({phone,seq_no:null})})).json();
        const id=i.data||{};
        out.init_err=i.error; out.cp=id.change_phone_token||'';
        out.ivs=id.ivs_required;
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
    log(f"  init={st.get('init_err')} cp={len(cp)}B seed={seed[:18]} cap={st.get('need_cap')}")

    vt = ""

    if CODE:
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
        log(f"  err={err}")
        if err == 0:
            vt = ((vr.get("j") or {}).get("data") or {}).get("vcode_token") or ""
            log(f"  ✅ vcode_token {len(vt)}B")
            json.dump({"phone": PH, "cp": cp, "seed": seed, "vcode_token": vt},
                      open("/root/shopee-verify/RM_ok.json", "w"), indent=1)
    else:
        # === 3b. kirim OTP ===
        log("\n=== 3. send_vcode op=18 ===")
        r = pg.evaluate("""async (a)=>{
          const {phone,seed}=a; const out={tries:[]};
          for(const ch of [3,2,1]){
            const j=await (await fetch('/api/v4/otp/send_vcode',{method:'POST',
              credentials:'include',headers:{'Content-Type':'application/json'},
              body:JSON.stringify({phone,channel:ch,operation:18,seed})})).json();
            out.tries.push({ch,err:j.error,trk:(j.data||{}).otp_tracking_id});
            if(j.error===0){out.win=ch;out.trk=(j.data||{}).otp_tracking_id;break;}
            if(j.error!==23500101) break;
          }
          return out;
        }""", {"phone": PH, "seed": seed})
        log(f"  {json.dumps(r)[:200]}")
        if r.get("win"):
            log(f"  ✅ OTP terkirim ch={r['win']} trk={r.get('trk')}")
            json.dump({"phone": PH, "seed": seed, "cp": cp,
                       "ch": r["win"], "trk": r.get("trk")},
                      open("/root/shopee-verify/RM_otp.json", "w"), indent=1)
        br.close()
        sys.exit(0)

    # === 4. BUKA SEMUA kandidat URL finalisasi, KLIK semuanya ===
    log("\n=== 4. buka halaman finalisasi + klik semua ===")
    cand = [
        "https://shopee.co.id/user/account/phone",
        f"https://shopee.co.id/user/account/phone?operation=18&vcode_token={vt}&seed={seed}",
        f"https://shopee.co.id/user/account/phone?step=confirm&operation=18&vcode_token={vt}&seed={seed}",
        "https://shopee.co.id/user/account/settings",
        "https://shopee.co.id/user/account/security",
        "https://shopee.co.id/user/account/phone/verify",
    ]
    for u in cand:
        log(f"\n  --- goto {u[:100]}")
        try:
            pg.goto(u, wait_until="domcontentloaded", timeout=50000)
        except Exception:
            pass
        pg.wait_for_timeout(11000)
        cur = pg.evaluate("()=>location.href")
        canv = pg.evaluate("()=>document.querySelectorAll('canvas').length")
        log(f"      url={cur[:90]} canvas={canv}")

        # klik semua elemen interaktif (biar SDK trigger endpoint)
        clicked = pg.evaluate("""()=>{
          const out=[];
          const els=[...document.querySelectorAll('button,a,div[role=button],[class*=btn]')];
          let n=0;
          for(const e of els){
            const r=e.getBoundingClientRect();
            if(r.width<20||r.height<16) continue;
            if(r.y<0||r.y>1400) continue;
            const t=(e.innerText||'').trim().slice(0,40);
            if(!t) continue;
            if(/hapus|logout|keluar|delete|batal|cancel/i.test(t)) continue;
            try{ e.click(); out.push(t); n++; }catch(err){}
            if(n>=6) break;
          }
          return out;
        }""")
        if clicked:
            log(f"      klik: {clicked}")
            pg.wait_for_timeout(9000)

    # === 5. ringkas endpoint yang muncul ===
    log("\n\n=== 5. SEMUA ENDPOINT phone/otp/management ===")
    seen = set()
    try:
        for line in open(JSONL):
            d = json.loads(line)
            if d.get("kind") != "REQ":
                continue
            u = d.get("url", "")
            if "/api/v" in u and any(x in u for x in ("phone", "otp", "management", "account")):
                sh = u.split("shopee.co.id")[-1].split("?")[0]
                key = f"{d['method']} {sh}"
                if key not in seen:
                    seen.add(key)
                    log(f"  {key}")
                    if d.get("body"):
                        log(f"       body={d['body'][:160]}")
    except Exception as e:
        log(f"  err {e}")

    pg.screenshot(path="/root/shopee-verify/RM.png", full_page=True)
    br.close()

log("\n=== SELESAI — MITM.jsonl ===")
