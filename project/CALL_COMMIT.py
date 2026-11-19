"""CALL_COMMIT.py — panggil changePhoneCommitV2 lewat runtime, TANGKAP endpoint aslinya.

Fix circular dep `Cannot access 'N'`:
  1. req(7231) dulu (modul AccountChangePhoneNumberV3) supaya `N` ter-init
  2. hook window.fetch + XHR untuk rekam endpoint PERSIS yang service pakai
  3. panggil K.changePhoneCommitV2({phone, changePhoneToken, vcodeToken, ivsSignature, ivsMethod})
  4. print request yg tertangkap
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
    open("/root/shopee-verify/CC.log", "a").write(m + "\n")


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
        f"  ← {r.status} {r.url.split('shopee.co.id')[-1][:62]} :: {r.text()[:180]}")
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
      const out={};
      try{
        const i=await (await fetch('/api/v4/account/management/change_phone_init_v2',
          {method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},
           body:JSON.stringify({phone:a.phone,seq_no:null})})).json();
        out.init=i.error; out.cp=(i.data||{}).change_phone_token||'';
        return out;
      }catch(e){out.ex=String(e).slice(0,100);return out;}
    }""", {"phone": PH})
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

    if not vt:
        log("❌ butuh vcode_token — kirim kode OTP")
        br.close()
        sys.exit(1)

    # === 3. hook fetch + load modul + panggil commit ===
    log("\n=== 3. hook fetch → load modul → panggil commit ===")
    r = pg.evaluate("""async (a)=>{
      const captured=[];
      // hook fetch
      const origFetch = window.fetch;
      window.fetch = async function(...args){
        const url = (typeof args[0]==='string')?args[0]:(args[0]&&args[0].url)||'';
        const opt = args[1]||{};
        const rec = {url, method: opt.method||'GET', body: opt.body||null};
        captured.push(rec);
        try { return await origFetch.apply(this, args); }
        catch(e){ rec.err=String(e).slice(0,100); throw e; }
      };

      const out={captured};
      const wp=window.webpackChunkshopee_pc;
      if(!wp){out.err='no wp'; return out;}
      let req=null;
      wp.push([[Math.random().toString(36).slice(2)],{},function(r){req=r;}]);
      if(!req){out.err='no require'; return out;}
      window.__WR=req;

      // muat chunk
      for(const c of [5427,8963,9308,1250,2735,8167,5358,896]){
        try{ await req.e(c);}catch(e){}
      }
      // init modul 7231 (V3) supaya 'N' terdefinisi
      try{ req(7231); }catch(e){ out.e7231=String(e).slice(0,80); }
      try{ req(66199); }catch(e){ out.e66199=String(e).slice(0,80); }

      // ambil service
      let svc=null;
      try{
        const m=req(66199);
        svc = m && m.K;
        out.svcKeys = svc? Object.keys(svc):null;
      }catch(e){ out.svcErr=String(e).slice(0,120); }

      if(!svc){ out.err='svc null'; return out; }

      // panggil commit
      try{
        const res = await svc.changePhoneCommitV2({
          phone: a.phone,
          changePhoneToken: a.cp,
          vcodeToken: a.vt,
          ivsSignature: "",
          ivsMethod: null
        });
        out.commit_res = JSON.parse(JSON.stringify(res||{}));
      }catch(e){ out.commit_err = String(e).slice(0,300); }

      window.fetch = origFetch;
      return out;
    }""", {"phone": PH, "cp": cp, "vt": vt})

    log(f"  svc: {r.get('svcKeys')}  err={r.get('err')} {r.get('svcErr') or ''}")
    log(f"  commit_res: {json.dumps(r.get('commit_res'))[:260]}")
    log(f"  commit_err: {r.get('commit_err')}")
    caps = r.get("captured") or []
    log(f"\n  REQUEST TERTANGKAP ({len(caps)}):")
    for c in caps:
        u = c.get("url", "")
        if "/api/" in u:
            log(f"    {c.get('method')} {u.split('shopee.co.id')[-1][:80]}")
            if c.get("body"):
                log(f"       {str(c['body'])[:220]}")
    json.dump(r, open("/root/shopee-verify/CC_capture.json", "w"), indent=1)

    log("\n=== 4. nomor ===")
    fi = pg.evaluate("""async()=>{try{
      const r=await fetch('/api/v4/account/basic/get_account_info',{credentials:'include'});
      const j=await r.json();const d=j.data||{};
      return {err:j.error,user:d.username,phone:d.phone};
    }catch(e){return{ex:String(e).slice(0,50)}}}""")
    log(f"  {fi}")
    br.close()

log("\n=== SELESAI ===")
