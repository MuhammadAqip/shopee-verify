"""EXTRACT_SVC.py — setelah chunk 8167/5358/896 ter-load, panggil modul service
langsung dari runtime webpack dan temukan fungsi finalisasi + endpoint aslinya.

Chunk yang sudah bisa dimuat (terbukti): 5427, 8963, 9308, 1250, 2735, 8167, 5358, 896
  8167 = AccountChangePhoneNumberV2
  5358 = AccountChangePhoneNumberV3
  896  = AccountAddPhoneNumberV2

Strategi:
  1. warm + init_v2 + settings + verify (pakai kode)
  2. req.e() load 8 chunk
  3. telusuri semua modul yg ke-load -> cari export yg namanya mengandung
     changePhone/commit/unbind/phone + rekam source-nya
  4. panggil fungsi commit dgn state kita, LIAT endpoint yg muncul di MITM
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
    open("/root/shopee-verify/EX.log", "a").write(m + "\n")


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
        f"  ← {r.status} {r.url.split('shopee.co.id')[-1][:62]} :: {r.text()[:160]}")
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
        const id=i.data||{};
        out.init=i.error; out.cp=id.change_phone_token||'';
        const g=await (await fetch('/api/v4/otp/get_settings_v2',
          {method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},
           body:JSON.stringify({phone,operation:op})})).json();
        const gd=g.data||{};
        out.set=g.error; out.seed=gd.seed||'';
        return out;
      }catch(e){out.ex=String(e).slice(0,100);return out;}
    }""", {"phone": PH, "op": OP})
    cp = st.get("cp") or ""
    seed = st.get("seed") or ""
    log(f"  init={st.get('init')} cp={len(cp)}B set={st.get('set')} seed={seed[:18]}")

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

    # === 3. load chunk + telusuri modul ===
    log("\n=== 3. load chunk + bedah modul service ===")
    res = pg.evaluate("""async ()=>{
      const out={loaded:[],mods:[]};
      const wp=window.webpackChunkshopee_pc;
      if(!wp){out.err='no wp';return out;}
      let req=null;
      wp.push([[Math.random().toString(36).slice(2)],{},function(r){req=r;}]);
      if(!req){out.err='no require';return out;}
      const chunks=[5427,8963,9308,1250,2735,8167,5358,896];
      for(const c of chunks){ try{ await req.e(c); out.loaded.push(c);}catch(e){} }
      // telusuri cache modul
      const cache=req.c||{};
      out.cache_count = Object.keys(cache).length;
      for(const id of Object.keys(cache)){
        try{
          const m=cache[id];
          if(!m||!m.exports) continue;
          const ex=m.exports;
          const keys=Object.keys(ex).filter(k=>/^(K|default|svc|services|api)$/.test(k)||true);
          // cari objek service yg punya fungsi phone
          for(const k of keys){
            const v=ex[k];
            if(v&&typeof v==='object'){
              const fn=Object.keys(v).filter(n=>/phone|Phone|vcode|commit|unbind/i.test(n));
              if(fn.length) out.mods.push({id,k,fns:fn});
            }
            if(typeof v==='function' && /phone|vcode|commit|unbind/i.test(k)){
              out.mods.push({id,k,fn:true});
            }
          }
        }catch(e){}
      }
      return out;
    }""")
    log(f"  loaded: {res.get('loaded')}")
    log(f"  cache modul: {res.get('cache_count')}")
    mods = res.get("mods") or []
    log(f"  modul kandidat: {len(mods)}")
    for m in mods[:25]:
        log(f"    id={m.get('id')} key={m.get('k')} fns={m.get('fns') or 'function'}")

    json.dump(res, open("/root/shopee-verify/EX_mods.json", "w"), indent=1)

    # === 4. panggil service commit langsung ===
    if vt:
        log("\n=== 4. panggil service via runtime (cari endpoint) ===")
        r2 = pg.evaluate("""async (a)=>{
          const out=[];
          const wp=window.webpackChunkshopee_pc;
          let req=null;
          wp.push([[Math.random().toString(36).slice(2)],{},function(r){req=r;}]);
          const cache=req.c||{};
          // cari objek yg punya changePhoneCommitV2 / unbindPhoneByVcode
          for(const id of Object.keys(cache)){
            try{
              const ex=cache[id]&&cache[id].exports; if(!ex) continue;
              for(const k of Object.keys(ex)){
                const v=ex[k];
                if(!v||typeof v!=='object') continue;
                const hasCommit = typeof v.changePhoneCommitV2==='function';
                const hasUnbind = typeof v.unbindPhoneByVcode==='function';
                const hasInit = typeof v.initChangePhoneNumberV2==='function';
                if(hasCommit||hasUnbind||hasInit){
                  out.push({mod:id,key:k,hasCommit,hasUnbind,hasInit,
                            all:Object.keys(v).filter(n=>/phone|vcode|commit|unbind|precheck|avail/i.test(n))});
                }
              }
            }catch(e){}
          }
          return out;
        }""", {})
        log(f"  service object ditemukan: {len(r2)}")
        for x in r2[:10]:
            log(f"    mod={x['mod']} key={x['key']} commit={x['hasCommit']} unbind={x['hasUnbind']} init={x['hasInit']}")
            log(f"       methods: {x['all']}")
        json.dump(r2, open("/root/shopee-verify/EX_svc.json", "w"), indent=1)

        # kalau ada service, panggil commit
        if r2:
            log("\n  → memanggil changePhoneCommitV2 lewat service asli")
            r3 = pg.evaluate("""async (a)=>{
              const wp=window.webpackChunkshopee_pc;
              let req=null;
              wp.push([[Math.random().toString(36).slice(2)],{},function(r){req=r;}]);
              const cache=req.c||{};
              for(const id of Object.keys(cache)){
                try{
                  const ex=cache[id]&&cache[id].exports; if(!ex) continue;
                  for(const k of Object.keys(ex)){
                    const v=ex[k];
                    if(v&&typeof v==='object'&&typeof v.changePhoneCommitV2==='function'){
                      const res=await v.changePhoneCommitV2({
                        phone:a.phone, changePhoneToken:a.cp,
                        vcodeToken:a.vt, ivsSignature:"", ivsMethod:null});
                      return {mod:id,key:k,res:res};
                    }
                  }
                }catch(e){ return {err:String(e).slice(0,200)}; }
              }
              return {err:'service not found'};
            }""", {"phone": PH, "cp": cp, "vt": vt})
            log(f"  hasil commit: {json.dumps(r3)[:400]}")

    log("\n=== 5. nomor ===")
    fi = pg.evaluate("""async()=>{try{
      const r=await fetch('/api/v4/account/basic/get_account_info',{credentials:'include'});
      const j=await r.json();const d=j.data||{};
      return {err:j.error,user:d.username,phone:d.phone};
    }catch(e){return{ex:String(e).slice(0,50)}}}""")
    log(f"  {fi}")
    br.close()

log("\n=== SELESAI ===")
