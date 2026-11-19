"""EXTRACT_SVC2.py — akses modul service langsung via req(moduleId).

Fix dari EXTRACT_SVC.py: `req.c` kosong di production build. Tapi `req(id)`
mengembalikan exports modul apa pun yang sudah ke-load.

Target modul (dari REA bundle):
  66199  = service object Y.K (changePhoneCommitV2, unbindPhoneByVcode, ...)
  75405  = enum operation jU (AccountChangePhone=23) + channel UW
  9358   = helper $
  22725  = X (error enum)
"""
import json
import sys
import os
import time

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
    open("/root/shopee-verify/EX2.log", "a").write(m + "\n")


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
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 900},
                         timezone_id="Asia/Jakarta", proxy={"server": MITM},
                         ignore_https_errors=True)
    ctx.add_cookies(cookies)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};")
    pg = ctx.new_page()

    pg.on("response", lambda r: log(
        f"  ← {r.status} {r.url.split('shopee.co.id')[-1][:62]} :: {r.text()[:170]}")
        if "/api/" in r.url and any(x in r.url for x in ("phone", "otp", "vcode"))
        else None)

    log("=== 1. warm ===")
    try:
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=70000)
    except Exception:
        pass
    pg.wait_for_timeout(13000)

    log("\n=== 2. init + verify ===")
    st = pg.evaluate("""async (a)=>{
      const {phone,op}=a; const out={};
      try{
        const i=await (await fetch('/api/v4/account/management/change_phone_init_v2',
          {method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},
           body:JSON.stringify({phone,seq_no:null})})).json();
        out.init=i.error; out.cp=(i.data||{}).change_phone_token||'';
        return out;
      }catch(e){out.ex=String(e).slice(0,100);return out;}
    }""", {"phone": PH, "op": OP})
    cp = st.get("cp") or ""
    log(f"  init={st.get('init')} cp={len(cp)}B")

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

    # === 3. load chunk + akses modul via req(id) ===
    log("\n=== 3. req(id) langsung ===")
    r = pg.evaluate("""async ()=>{
      const out={loaded:[],mods:{},req:false};
      const wp=window.webpackChunkshopee_pc;
      if(!wp){out.err='no wp';return out;}
      let req=null;
      wp.push([[Math.random().toString(36).slice(2)],{},function(r){req=r;}]);
      if(!req){out.err='no require';return out;}
      window.__WR = req; out.req=true;
      for(const c of [5427,8963,9308,1250,2735,8167,5358,896]){
        try{ await req.e(c); out.loaded.push(c);}catch(e){}
      }
      // akses modul target langsung
      for(const id of [66199,75405,9358,22725]){
        try{
          const m = req(id);
          if(!m) continue;
          const keys = Object.keys(m);
          const svc = {};
          for(const k of keys){
            const v = m[k];
            if(v && typeof v === 'object'){
              const fns = Object.keys(v).filter(n=>typeof v[n]==='function');
              if(fns.length) svc[k] = fns;
            }
          }
          out.mods[id] = {keys, svc};
        }catch(e){ out.mods[id] = {err:String(e).slice(0,80)}; }
      }
      return out;
    }""")
    log(f"  req ada: {r.get('req')}  loaded: {r.get('loaded')}")
    for mid, info in (r.get("mods") or {}).items():
        if info.get("err"):
            log(f"  mod {mid}: ERR {info['err']}")
        else:
            log(f"  mod {mid}: keys={info.get('keys')}")
            for k, fns in (info.get("svc") or {}).items():
                log(f"     {k}: {fns}")
    json.dump(r, open("/root/shopee-verify/EX2_mods.json", "w"), indent=1)

    # === 4. cari service di SEMUA modul yang ke-load ===
    log("\n=== 4. sapu semua modul untuk changePhoneCommitV2 ===")
    r2 = pg.evaluate("""async ()=>{
      const req = window.__WR; if(!req) return {err:'no req'};
      const found=[];
      // id modul: coba range dari chunk yg di-load
      const ids=new Set();
      for(const c of [5427,8963,9308,1250,2735,8167,5358,896]){
        // module ids di chunk biasanya ribuan; coba beberapa range umum
      }
      // lebih tepat: enumerasi req.m (module factories)
      const m = req.m || {};
      const keys = Object.keys(m);
      found.push({total_modules: keys.length});
      for(const id of keys){
        try{
          const ex = req(id);
          if(!ex) continue;
          for(const k of Object.keys(ex)){
            const v=ex[k];
            if(v && typeof v==='object'){
              if(typeof v.changePhoneCommitV2==='function' ||
                 typeof v.unbindPhoneByVcode==='function' ||
                 typeof v.initChangePhoneNumberV2==='function'){
                found.push({id, key:k,
                  commit: typeof v.changePhoneCommitV2==='function',
                  unbind: typeof v.unbindPhoneByVcode==='function',
                  init: typeof v.initChangePhoneNumberV2==='function',
                  methods: Object.keys(v).filter(n=>typeof v[n]==='function')});
              }
            }
          }
        }catch(e){}
      }
      return {found};
    }""")
    f = (r2.get("found") or [])
    log(f"  total modul di req.m: {f[0].get('total_modules') if f else '?'}")
    hits = [x for x in f if isinstance(x, dict) and x.get("id")]
    log(f"  service ditemukan: {len(hits)}")
    for h in hits[:12]:
        log(f"    id={h['id']} key={h['key']} commit={h.get('commit')} unbind={h.get('unbind')} init={h.get('init')}")
        log(f"       {h.get('methods')}")
    json.dump(r2, open("/root/shopee-verify/EX2_found.json", "w"), indent=1)

    # === 5. panggil commit via service asli ===
    if hits and vt:
        log("\n=== 5. PANGGIL commit via service asli ===")
        r3 = pg.evaluate("""async (a)=>{
          const req=window.__WR;
          const m=req.m||{};
          for(const id of Object.keys(m)){
            try{
              const ex=req(id); if(!ex) continue;
              for(const k of Object.keys(ex)){
                const v=ex[k];
                if(v&&typeof v==='object'&&typeof v.changePhoneCommitV2==='function'){
                  const res=await v.changePhoneCommitV2({
                    phone:a.phone, changePhoneToken:a.cp,
                    vcodeToken:a.vt, ivsSignature:"", ivsMethod:null});
                  return {id,key:k,res:JSON.parse(JSON.stringify(res||{}))};
                }
              }
            }catch(e){ return {id,err:String(e).slice(0,200)}; }
          }
          return {err:'not found'};
        }""", {"phone": PH, "cp": cp, "vt": vt})
        log(f"  {json.dumps(r3)[:500]}")

    log("\n=== 6. nomor ===")
    fi = pg.evaluate("""async()=>{try{
      const r=await fetch('/api/v4/account/basic/get_account_info',{credentials:'include'});
      const j=await r.json();const d=j.data||{};
      return {err:j.error,user:d.username,phone:d.phone};
    }catch(e){return{ex:String(e).slice(0,50)}}}""")
    log(f"  {fi}")
    br.close()

log("\n=== SELESAI ===")
