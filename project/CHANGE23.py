"""CHANGE23.py — ganti nomor asli pakai operation:23 (AccountChangePhone).

Alur dari bundle AccountChangePhoneNumberV2 (module 66199 = service):
  1. initChangePhoneNumberV2  -> changePhoneToken
  2. get_settings_v2 op=23    -> need_captcha FALSE     (VERIFIED)
  3. send_vcode op=23 ch=3    -> otp_tracking_id
  4. verify_vcode op=23 {vcode} -> vcode_token
  5. unbindPhoneByVcode {phone, vcodeToken, operation:23}
  6. changePhoneCommitV2      -> FINAL

Usage:
  python3 CHANGE23.py <cookie> <phone>            # kirim OTP (op=23)
  python3 CHANGE23.py <cookie> <phone> <kode>     # verify + unbind + commit
"""
import json, sys, os, time

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_zax.txt"
PH = sys.argv[2] if len(sys.argv) > 2 else "62895806564446"
CODE = sys.argv[3] if len(sys.argv) > 3 else ""
PROXY = os.environ.get("SHOPEE_PROXY", "http://127.0.0.1:18080")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
OP = 23          # AccountChangePhone
T0 = time.time()
STATE = "/root/shopee-verify/C23_state.json"


def log(*a):
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/C23.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled",
        "--lang=id-ID", "--use-gl=swiftshader"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 900},
                         timezone_id="Asia/Jakarta",
                         proxy={"server": PROXY} if PROXY else None)
    ctx.add_cookies(cookies)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};")
    pg = ctx.new_page()

    pg.on("response", lambda r: log(
        f"  ← {r.status} {r.url.split('shopee.co.id')[-1][:58]} :: {r.text()[:170]}")
        if "/api/v4/" in r.url and any(x in r.url for x in ("phone", "otp", "management", "vcode"))
        else None)

    log("=== warm ===")
    try:
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    pg.wait_for_timeout(11000)

    # === SEND MODE ===
    if not CODE:
        log(f"\n=== SEND OTP op={OP} ===")
        st = pg.evaluate("""async (a)=>{
          const {phone,op}=a; const out={};
          try{
            const i=await (await fetch('/api/v4/account/management/change_phone_init_v2',
              {method:'POST',credentials:'include',
               headers:{'Content-Type':'application/json'},
               body:JSON.stringify({phone,seq_no:null})})).json();
            const id=i.data||{};
            out.init=i.error; out.cp=id.change_phone_token||'';
            out.ivs=id.ivs_required; out.ivs_utoken=id.ivs_utoken||'';
            out.ongoing=id.ongoing_request_phone||null; out.delayed=id.is_delayed||false;
            const g=await (await fetch('/api/v4/otp/get_settings_v2',
              {method:'POST',credentials:'include',
               headers:{'Content-Type':'application/json'},
               body:JSON.stringify({phone,operation:op})})).json();
            const gd=g.data||{};
            out.set=g.error; out.seed=gd.seed||''; out.cap=gd.need_captcha;
            out.scene=gd.captcha_scene;
            return out;
          }catch(e){out.ex=String(e).slice(0,110);return out;}
        }""", {"phone": PH, "op": OP})
        log(f"  init={st.get('init')} cp={len(st.get('cp') or '')}B ivs={st.get('ivs')} "
            f"ongoing={st.get('ongoing')} cap={st.get('cap')} scene={st.get('scene')}")
        if st.get("init") != 0:
            log("  ❌ init gagal")
            br.close()
            sys.exit(2)

        seed = st.get("seed") or ""
        r = pg.evaluate("""async (a)=>{
          const {phone,seed,op}=a; const out={tries:[]};
          for(const ch of [3,2,1]){
            const j=await (await fetch('/api/v4/otp/send_vcode',{method:'POST',
              credentials:'include',headers:{'Content-Type':'application/json'},
              body:JSON.stringify({phone,channel:ch,operation:op,seed})})).json();
            out.tries.push({ch,err:j.error,trk:(j.data||{}).otp_tracking_id});
            if(j.error===0){out.win=ch;out.trk=(j.data||{}).otp_tracking_id;break;}
            if(j.error!==23500101) break;
          }
          return out;
        }""", {"phone": PH, "seed": seed, "op": OP})
        log(f"  send: {json.dumps(r)[:240]}")
        if r.get("win"):
            log(f"\n  ✅ OTP TERKIRIM ch={r['win']} trk={r.get('trk')}")
            json.dump({"phone": PH, "op": OP, "cp": st.get("cp"), "seed": seed,
                       "ch": r["win"], "trk": r.get("trk")},
                      open(STATE, "w"), indent=1)
        else:
            log("  ❌ send gagal")
        br.close()
        sys.exit(0)

    # === VERIFY + COMMIT MODE ===
    st = {}
    try:
        st = json.load(open(STATE))
    except Exception:
        log("❌ state hilang — kirim OTP dulu")
        br.close()
        sys.exit(1)

    cp = st.get("cp") or ""
    log(f"\n=== VERIFY {CODE} op={OP} ===")
    vr = pg.evaluate("""async (a)=>{
      try{
        const r=await fetch('/api/v4/otp/verify_vcode',{method:'POST',
          credentials:'include',headers:{'Content-Type':'application/json'},
          body:JSON.stringify(a.b)});
        return {s:r.status,j:await r.json()};
      }catch(e){return {ex:String(e).slice(0,80)};}
    }""", {"b": {"phone": PH, "vcode": CODE, "operation": OP, "m_token": cp}})
    err = (vr.get("j") or {}).get("error")
    log(f"  verify err={err}")
    if err != 0:
        log("  ❌ verify gagal")
        br.close()
        sys.exit(2)
    vt = ((vr.get("j") or {}).get("data") or {}).get("vcode_token") or ""
    log(f"  ✅ vcode_token {len(vt)}B")

    # === unbind phone by vcode ===
    log(f"\n=== unbind_phone_by_vcode op={OP} ===")
    ub = pg.evaluate("""async (a)=>{
      try{
        const r=await fetch('/api/v4/account/management/unbind_phone_by_vcode',
          {method:'POST',credentials:'include',
           headers:{'Content-Type':'application/json'},
           body:JSON.stringify(a.b)});
        return {s:r.status,j:await r.json()};
      }catch(e){return {ex:String(e).slice(0,80)};}
    }""", {"b": {"phone": PH, "vcode_token": vt, "operation": OP}})
    log(f"  unbind err={(ub.get('j') or {}).get('error')} :: {json.dumps(ub.get('j'))[:180]}")

    # === change phone commit ===
    log("\n=== change_phone_commit_v2 ===")
    for ep in ("change_phone_commit_v2", "change_phone_commit"):
        cm = pg.evaluate("""async (a)=>{
          try{
            const r=await fetch('/api/v4/account/management/'+a.ep,
              {method:'POST',credentials:'include',
               headers:{'Content-Type':'application/json'},
               body:JSON.stringify(a.b)});
            return {s:r.status,j:await r.json()};
          }catch(e){return {ex:String(e).slice(0,80)};}
        }""", {"ep": ep, "b": {"phone": PH, "change_phone_token": cp,
                              "vcode_token": vt, "operation": OP}})
        e2 = (cm.get("j") or {}).get("error")
        log(f"  {ep} err={e2} :: {json.dumps(cm.get('j'))[:200]}")
        if e2 == 0:
            log("  🎉 COMMIT SUKSES")
            break

    # === verifikasi nomor ===
    log("\n=== cek nomor akhir ===")
    fi = pg.evaluate("""async()=>{try{
      const r=await fetch('/api/v4/account/basic/get_account_info',{credentials:'include'});
      const j=await r.json();const d=j.data||{};
      return {err:j.error,user:d.username,phone:d.phone,verified:d.phone_verified};
    }catch(e){return{ex:String(e).slice(0,60)}}}""")
    log(f"  {fi}")
    json.dump({"verify": vr, "unbind": ub, "info": fi},
              open("/root/shopee-verify/C23_result.json", "w"), indent=1)
    br.close()

log("\n=== SELESAI ===")
