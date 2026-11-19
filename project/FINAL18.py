"""FINAL18.py — verify (vcode) + finalisasi ganti nomor, semua dari page.

Alur:
  1. init_v2 -> change_phone_token
  2. get_settings_v2 op=18 -> need_captcha FALSE
  3. send_vcode op=18 ch3 WA -> OTP
  4. verify_vcode {phone, vcode, operation:18, m_token:<cp_token>} -> vcode_token
  5. finalisasi: brute endpoint confirm dengan vcode_token
  6. cek get_account_info -> nomor berubah?
"""
import json, sys, time, os

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_zax.txt"
PH = sys.argv[2] if len(sys.argv) > 2 else "62895806564446"
VTOKEN = sys.argv[3] if len(sys.argv) > 3 else ""
PROXY = os.environ.get("SHOPEE_PROXY", "")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/F18.log", "a").write(m + "\n")


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
        NET.append({"u": u.split("shopee.co.id")[-1][:80], "s": r.status, "b": b[:500]})
        log(f"  NET {r.status} {u.split('shopee.co.id')[-1][:58]} :: {b[:150]}")


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

    log("=== 1. warm home ===")
    try:
        pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    pg.wait_for_timeout(11000)

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
    log(f"  {json.dumps(st)[:250]}")
    cp = st.get("cp") or ""

    VCODE_TOK = VTOKEN

    # kalau vtoken belum ada, minta verify (butuh kode baru)
    if not VCODE_TOK:
        log("\n  ⚠️ vcode_token belum ada — perlu OTP baru dulu")
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
        log(f"  send: {json.dumps(r)[:200]}")
        if r.get("win"):
            log(f"  ✅ OTP terkirim ch={r['win']} trk={r.get('trk')}")
        br.close()
        sys.exit(0)

    # === finalisasi: brute endpoint ===
    log(f"\n=== 3. finalisasi dengan vcode_token {len(VCODE_TOK)}B ===")
    cands = [
        ("/api/v4/account/management/change_phone_confirm_v2",
         {"phone": PH, "vcode_token": VCODE_TOK, "operation": 18}),
        ("/api/v4/account/management/change_phone_confirm_v2",
         {"phone": PH, "vcode_token": VCODE_TOK}),
        ("/api/v4/otp/bind_phone",
         {"phone": PH, "vcode_token": VCODE_TOK, "operation": 18}),
        ("/api/v4/account/basic/set_phone",
         {"phone": PH, "vcode_token": VCODE_TOK, "operation": 18}),
        ("/api/v4/account/management/set_phone",
         {"phone": PH, "vcode_token": VCODE_TOK}),
        ("/api/v4/otp/set_phone",
         {"phone": PH, "vcode_token": VCODE_TOK, "operation": 18}),
        ("/api/v4/account/management/change_phone_v2",
         {"phone": PH, "vcode_token": VCODE_TOK, "operation": 18}),
        ("/api/v4/account/basic/change_phone",
         {"phone": PH, "vcode_token": VCODE_TOK, "operation": 18}),
    ]
    for p, b in cands:
        r = pg.evaluate("""async (a)=>{
          try{
            const r=await fetch(a.p,{method:'POST',credentials:'include',
              headers:{'Content-Type':'application/json'},
              body:JSON.stringify(a.b)});
            return {s:r.status,j:await r.json()};
          }catch(e){return {ex:String(e).slice(0,70)};}
        }""", {"p": p, "b": b})
        err = (r.get("j") or {}).get("error")
        log(f"  {p:58s} err={err}")
        if err == 0:
            log(f"\n  🎉🎉🎉 SUKSES via {p}")
            log(f"  {json.dumps(r.get('j'))[:300]}")
            break

    log("\n=== 4. cek nomor ===")
    a = pg.evaluate("""async()=>{try{
      const r=await fetch('/api/v4/account/basic/get_account_info',{credentials:'include'});
      const j=await r.json();const d=j.data||{};
      return {err:j.error,user:d.username,phone:d.phone,
              masked:d.masked_phone,mkeys:Object.keys(d).filter(k=>/phone/i.test(k))};
    }catch(e){return{ex:String(e).slice(0,60)}}}""")
    log(f"  {json.dumps(a)[:400]}")

    pg.screenshot(path="/root/shopee-verify/F18.png", full_page=True)
    json.dump({"net": NET[-25:], "state": st, "final": a},
              open("/root/shopee-verify/F18.json", "w"), indent=1)
    br.close()

log("\n=== SELESAI ===")
