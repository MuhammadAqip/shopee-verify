"""BOT_CHANGE.py — pipeline ganti nomor Shopee full-auto (op=23, no captcha).

Alur terbukti:
  1. warm   -> ambil webpack require
  2. init_v2 -> change_phone_token
  3. get_settings_v2 op=23 -> need_captcha FALSE
  4. send_vcode op=23 ch=3 (WA) -> seed/trk
  5. verify_vcode {vcode, operation:23, m_token} -> vcode_token
  6. req(7231) init, req(66199).K.changePhoneCommitV2(...) -> {"error":0}
  7. cek get_account_info -> nomor baru

Usage:
  python3 BOT_CHANGE.py <cookie.txt> <nomor_baru>              # kirim OTP
  python3 BOT_CHANGE.py <cookie.txt> <nomor_baru> <kode_otp>   # verify + commit
"""
import json
import sys
import os
import time

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_zax.txt"
PH = sys.argv[2] if len(sys.argv) > 2 else ""
CODE = sys.argv[3] if len(sys.argv) > 3 else ""
MITM = os.environ.get("MITM_PROXY", "http://127.0.0.1:8080")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
OP = 23
T0 = time.time()
STATE = f"/root/shopee-verify/BOT_state_{os.path.basename(CK).replace('.txt','')}.json"


def log(*a):
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)


if not PH:
    log("❌ usage: BOT_CHANGE.py <cookie> <nomor> [kode]")
    sys.exit(1)

ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright

# script JS: ambil require webpack dari mana pun (dipakai berkali-kali)
JS_GET_REQ = """
() => {
  if (window.__WR) return true;
  const wp = window.webpackChunkshopee_pc;
  if (!wp) return false;
  wp.push([[Math.random().toString(36).slice(2)], {}, function(r){ window.__WR = r; }]);
  return !!window.__WR;
}
"""

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,900",
        "--disable-blink-features=AutomationControlled", "--lang=id-ID",
        "--ignore-certificate-errors"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 900},
                         timezone_id="Asia/Jakarta",
                         proxy={"server": MITM} if MITM else None,
                         ignore_https_errors=True)
    ctx.add_cookies(cookies)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};")
    pg = ctx.new_page()

    pg.on("response", lambda r: log(
        f"  ← {r.status} {r.url.split('shopee.co.id')[-1][:60]} :: {r.text()[:150]}")
        if "/api/" in r.url and any(x in r.url for x in ("phone", "otp", "vcode"))
        else None)

    log("=== 1. warm ===")
    try:
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=70000)
    except Exception:
        pass
    pg.wait_for_timeout(13000)
    log(f"  webpack require: {pg.evaluate(JS_GET_REQ)}")

    # === SEND MODE ===
    if not CODE:
        log("\n=== 2. send OTP op=23 ch3 (WA) ===")
        r = pg.evaluate("""async (a)=>{
          const out={};
          try{
            const i=await (await fetch('/api/v4/account/management/change_phone_init_v2',
              {method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},
               body:JSON.stringify({phone:a.phone,seq_no:null})})).json();
            const id=i.data||{};
            out.init=i.error; out.cp=id.change_phone_token||'';
            out.ivs=id.ivs_required;
            if(i.error!==0) return out;
            const g=await (await fetch('/api/v4/otp/get_settings_v2',
              {method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},
               body:JSON.stringify({phone:a.phone,operation:23})})).json();
            const gd=g.data||{};
            out.set=g.error; out.seed=gd.seed||''; out.cap=gd.need_captcha;
            out.scene=gd.captcha_scene;
            if(g.error!==0) return out;
            const s=await (await fetch('/api/v4/otp/send_vcode',
              {method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},
               body:JSON.stringify({phone:a.phone,channel:3,operation:23,seed:out.seed})})).json();
            out.send=s.error; out.trk=(s.data||{}).otp_tracking_id;
            return out;
          }catch(e){out.ex=String(e).slice(0,110);return out;}
        }""", {"phone": PH})
        log(f"  init={r.get('init')} cp={len(r.get('cp') or '')}B ivs={r.get('ivs')}")
        log(f"  set={r.get('set')} cap={r.get('cap')} scene={r.get('scene')}")
        log(f"  send={r.get('send')} trk={r.get('trk')}")
        if r.get("send") == 0:
            log(f"\n  ✅ OTP TERKIRIM via WA ke {PH}")
            log(f"     trk = {r.get('trk')}")
            json.dump(r, open(STATE, "w"), indent=1)
        else:
            log(f"  ❌ gagal: {json.dumps(r)[:200]}")
        br.close()
        sys.exit(0)

    # === VERIFY + COMMIT MODE ===
    st = {}
    try:
        st = json.load(open(STATE))
    except Exception:
        log("⚠️ state hilang — ambil ulang cp_token")
        st = pg.evaluate("""async (a)=>{try{
          const i=await (await fetch('/api/v4/account/management/change_phone_init_v2',
            {method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},
             body:JSON.stringify({phone:a.phone,seq_no:null})})).json();
          return {cp:(i.data||{}).change_phone_token||''};
        }catch(e){return{cp:''}}}""", {"phone": PH})
    cp = st.get("cp") or ""
    log(f"\n=== 2. verify_vcode op=23 (vcode={CODE}) ===")
    v = pg.evaluate("""async (b)=>{try{
      const r=await fetch('/api/v4/otp/verify_vcode',{method:'POST',credentials:'include',
        headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
      return {s:r.status,j:await r.json()};
    }catch(e){return{ex:String(e).slice(0,70)}}}""",
        {"phone": PH, "vcode": CODE, "operation": OP, "m_token": cp})
    e = (v.get("j") or {}).get("error")
    log(f"  err={e}")
    if e != 0:
        log("  ❌ verify gagal")
        br.close()
        sys.exit(2)
    vt = ((v.get("j") or {}).get("data") or {}).get("vcode_token") or ""
    log(f"  ✅ vcode_token {len(vt)}B")

    # === COMMIT via service asli ===
    log("\n=== 3. changePhoneCommitV2 (service runtime) ===")
    res = pg.evaluate("""async (a)=>{
      const req = window.__WR;
      if(!req) return {err:'no webpack require'};
      const out={};
      // pastikan chunk finalisasi + modul V3 ter-init (fix circular 'N')
      for(const c of [5427,8963,9308,1250,2735,8167,5358,896]){
        try{ await req.e(c); }catch(e){}
      }
      for(const mid of [7231, 66199]){
        try{ req(mid); }catch(e){ out['e'+mid]=String(e).slice(0,80); }
      }
      let svc=null;
      try{ svc = req(66199).K; }catch(e){ out.svcErr=String(e).slice(0,120); }
      if(!svc) return {...out, err:'svc null'};
      try{
        const r = await svc.changePhoneCommitV2({
          phone: a.phone,
          changePhoneToken: a.cp,
          vcodeToken: a.vt,
          ivsSignature: "",
          ivsMethod: null
        });
        out.commit_raw = JSON.parse(JSON.stringify(r||{}));
      }catch(e){ out.commit_err = String(e).slice(0,300); }
      return out;
    }""", {"phone": PH, "cp": cp, "vt": vt})
    log(f"  {json.dumps(res)[:400]}")

    log("\n=== 4. cek nomor ===")
    fi = pg.evaluate("""async()=>{try{
      const r=await fetch('/api/v4/account/basic/get_account_info',{credentials:'include'});
      const j=await r.json();const d=j.data||{};
      return {err:j.error,user:d.username,phone:d.phone,verified:d.phone_verified};
    }catch(e){return{ex:String(e).slice(0,50)}}}""")
    log(f"  {fi}")

    ok = (res.get("commit_raw") or {}).get("error") == 0
    if ok:
        log(f"\n  🎉 SUKSES — nomor sekarang: {fi.get('phone')}")
    else:
        log("\n  ⚠️ commit belum sukses — lihat log di atas")
    json.dump({"verify": v, "commit": res, "info": fi},
              open(f"/root/shopee-verify/BOT_result_{os.path.basename(CK).replace('.txt','')}.json", "w"),
              indent=1)
    br.close()

log("=== SELESAI ===")
