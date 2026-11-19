"""E2E18.py — end-to-end ganti nomor: verify(vcode) + finalisasi, SATU proses.

Kunci yang sudah terbukti:
  - get_settings_v2 op=18  -> need_captcha FALSE (scene phone_otp_account_set_phone)
  - send_vcode      op=18  -> OTP via WA (ch3)
  - verify_vcode    op=18  -> field 'vcode' (BUKAN 'code'), + m_token=change_phone_token
                              -> data.vcode_token

Mode:
  python3 E2E18.py ck.txt PHONE            -> kirim OTP, print tracking
  python3 E2E18.py ck.txt PHONE CODE       -> verify vcode + finalisasi + cek nomor
"""
import json, sys, time, os

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
    open("/root/shopee-verify/E2E.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright

NET = []


def onresp(r):
    u = r.url
    if "/api/v4/otp" in u or "/account/management" in u or "set_phone" in u:
        try:
            b = r.text()
        except Exception:
            b = ""
        NET.append({"u": u.split("shopee.co.id")[-1][:80], "s": r.status, "b": b[:600]})
        log(f"  NET {r.status} {u.split('shopee.co.id')[-1][:58]} :: {b[:160]}")


CONF = [  # endpoint finalisasi kandidat (urut paling mungkin)
    "/api/v4/account/management/change_phone_confirm_v2",
    "/api/v4/account/management/change_phone_v2",
    "/api/v4/account/management/set_phone",
    "/api/v4/account/basic/set_phone",
    "/api/v4/account/basic/change_phone",
    "/api/v4/otp/bind_phone",
    "/api/v4/otp/set_phone",
]

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
    pg.on("response", onresp)

    log(f"=== {PH} {'VERIFY' if CODE else 'SEND OTP'} ===")

    # warm
    try:
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    pg.wait_for_timeout(11000)

    a = pg.evaluate("""async()=>{try{
      const r=await fetch('/api/v4/account/basic/get_account_info',{credentials:'include'});
      const j=await r.json();return {err:j.error,user:(j.data||{}).username};
    }catch(e){return{ex:String(e).slice(0,50)}}}""")
    log(f"  sesi: {a}")
    if a.get("err") != 0:
        log("  ❌ cookie mati")
        br.close()
        sys.exit(1)

    # init_v2 + settings (opsional kalau sudah ada token dari file)
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
    log(f"  init: err={st.get('init_err')} cp={len(st.get('cp') or '')}B "
        f"set_err={st.get('set_err')} need_cap={st.get('need_cap')}")
    cp = st.get("cp") or ""

    if not CODE:
        # === mode kirim OTP ===
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
        }""", {"phone": PH, "seed": st.get("seed")})
        log(f"  send: {json.dumps(r)[:220]}")
        if r.get("win"):
            log(f"\n  ✅ OTP TERKIRIM ch={r['win']} trk={r.get('trk')}")
            json.dump({"phone": PH, "ch": r["win"], "seed": st.get("seed"),
                       "trk": r.get("trk"), "cp": cp},
                      open("/root/shopee-verify/E2E_OTP.json", "w"), indent=1)
        br.close()
        sys.exit(0)

    # === mode VERIFY + FINALISASI ===
    log(f"\n  verify dgn vcode={CODE}")
    vr = pg.evaluate("""async (a)=>{
      try{
        const r=await fetch('/api/v4/otp/verify_vcode',{method:'POST',
          credentials:'include',headers:{'Content-Type':'application/json'},
          body:JSON.stringify(a.b)});
        return {s:r.status,j:await r.json()};
      }catch(e){return {ex:String(e).slice(0,80)};}
    }""", {"b": {"phone": PH, "vcode": CODE, "operation": 18, "m_token": cp}})
    err = (vr.get("j") or {}).get("error")
    log(f"  verify err={err} {json.dumps(vr.get('j'))[:220]}")
    if err != 0:
        log("  ❌ verify gagal — kode salah/expired, resend")
        br.close()
        sys.exit(2)

    vt = ((vr.get("j") or {}).get("data") or {}).get("vcode_token") or ""
    log(f"  vcode_token {len(vt)}B")

    # finalisasi: coba tiap endpoint dengan beberapa bentuk body
    log("\n  === finalisasi ===")
    done = False
    for ep in CONF:
        for body in (
            {"phone": PH, "vcode_token": vt, "operation": 18},
            {"phone": PH, "vcode_token": vt},
            {"phone": PH, "otp_token": vt, "operation": 18},
        ):
            r = pg.evaluate("""async (a)=>{
              try{
                const r=await fetch(a.p,{method:'POST',credentials:'include',
                  headers:{'Content-Type':'application/json'},
                  body:JSON.stringify(a.b)});
                return {s:r.status,j:await r.json()};
              }catch(e){return {ex:String(e).slice(0,70)};}
            }""", {"p": ep, "b": body})
            e = (r.get("j") or {}).get("error")
            key = "vcode_token" if "vcode_token" in body else (
                "otp_token" if "otp_token" in body else "minimal")
            log(f"  {ep:52s} [{key:11s}] err={e} http={r.get('s')}")
            if e == 0:
                log(f"\n  🎉🎉🎉 SUKSES  {ep}  body={key}")
                log(f"  {json.dumps(r.get('j'))[:300]}")
                done = True
                break
        if done:
            break

    if not done:
        log("  ⚠️ semua endpoint finalisasi tolak — cek NET log di atas")

    log("\n  === cek nomor ===")
    fi = pg.evaluate("""async()=>{try{
      const r=await fetch('/api/v4/account/basic/get_account_info',{credentials:'include'});
      const j=await r.json();const d=j.data||{};
      return {err:j.error,user:d.username,phone:d.phone,
              masked:d.masked_phone,pkeys:Object.keys(d).filter(k=>/phone/i.test(k))};
    }catch(e){return{ex:String(e).slice(0,60)}}}""")
    log(f"  {json.dumps(fi)[:400]}")

    pg.screenshot(path="/root/shopee-verify/E2E.png", full_page=True)
    json.dump({"net": NET[-25:], "state": st, "verify": vr.get("j"),
               "final": fi, "done": done},
              open("/root/shopee-verify/E2E.json", "w"), indent=1)
    br.close()

log("\n=== SELESAI ===")
