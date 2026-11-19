"""tv_slow.py — SATU token/verify, jeda panjang, dari browser.

Hipotesis: 90309999 = rate limit / burst detection dari SDK.
Bukti: 16 request cepat → semua 90309999; 211 hanya saat schema salah.

Tes:
  1. Init flow
  2. select Password
  3. TUNGGU 8 detik (biar SDK settle)
  4. SATU token/verify
  5. Kalau 90309999, tunggu 20 detik, coba sekali lagi
"""
import json, sys, time
from playwright.sync_api import sync_playwright

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1553.txt"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"

ck = open(CK).read().strip()
cookies = []
for p in ck.split(";"):
    if "=" in p:
        k, v = p.strip().split("=", 1)
        cookies.append({"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"})


def log(*a):
    print(*a, flush=True)


with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,1000",
        "--disable-blink-features=AutomationControlled"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 1000},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    ctx.add_cookies(cookies)
    pg = ctx.new_page()

    log("=== buka shopee, tunggu SDK settle 18s ===")
    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(18000)

    # INIT FLOW
    o = pg.evaluate(r"""
    async () => {
      const M='/api/v4/account/management', IVS='/api/v4/anti_fraud/ivs';
      const post = async (p,b) => {
        const r = await fetch(p,{method:'POST',credentials:'include',
          headers:{'Content-Type':'application/json','X-API-SOURCE':'pc',
                   'X-Requested-With':'XMLHttpRequest','Accept':'application/json',
                   'X-Shopee-Language':'id'}, body:JSON.stringify(b||{})});
        let j=null; try{j=await r.json();}catch(e){}
        return {s:r.status,e:j&&j.error,d:j&&j.data};
      };
      const o={};
      await post(M+'/change_phone_init',{});
      const r2 = await post(M+'/change_phone_init_v2',{});
      o.ut=(r2.d||{}).ivs_utoken||''; o.cpt=(r2.d||{}).change_phone_token||'';
      const r3 = await post(IVS+'/methods',{event:2,u_token:o.ut});
      const ms = Array.isArray(r3.d)?r3.d:((r3.d||{}).methods||[]);
      o.methods = ms.map(x=>x.type);
      // pilih Password (2) kalau ada, else yang pertama
      const pick = ms.find(x=>x.type===2) || ms[0];
      o.pick = pick ? pick.type : null;
      o.vt = pick ? pick.v_token : '';
      if (pick) {
        const rs = await post(IVS+'/method/select',
          {v_token:o.vt, method:pick.type, event:2, u_token:o.ut});
        o.select = {e:rs.e, d:rs.d};
      }
      return o;
    }""")

    log(f"auth ut={len(o.get('ut',''))}B cpt={len(o.get('cpt',''))}B pick={o.get('pick')}")
    log(f"select={str(o.get('select'))[:120]}")

    if not o.get("vt"):
        log("❌ tidak ada method")
        br.close()
        sys.exit(1)

    NAMES = {2: "Password", 10: "NewShopeePayPin", 1: "OTP", 20: "DEVICE_TOKEN"}
    mt = o["pick"]
    MN = NAMES.get(mt, str(mt))

    for i, wait_s in enumerate((8, 20, 30), 1):
        log(f"\n--- attempt {i}: tunggu {wait_s}s lalu SATU request ---")
        pg.wait_for_timeout(wait_s * 1000)
        r = pg.evaluate("""async ([ut,vt,mn]) => {
          const r = await fetch('/api/v4/anti_fraud/ivs/token/verify', {
            method:'POST', credentials:'include',
            headers:{'Content-Type':'application/json','X-API-SOURCE':'pc',
                     'X-Requested-With':'XMLHttpRequest','Accept':'application/json',
                     'X-Shopee-Language':'id'},
            body: JSON.stringify({method_name:mn, event:2, u_token:ut,
              r_token:vt, v_token:vt, shopee_df:'', misc:{seed:'',operation:0}})
          });
          let j=null; try{j=await r.json();}catch(e){}
          return {s:r.status, e:j&&j.error, sig:j&&j.data&&j.data.signature?j.data.signature.length:0,
                  d:j&&j.data?Object.keys(j.data):null};
        }""", [o["ut"], o["vt"], MN])
        log(f"    {r}")
        if r.get("e") == 0 and r.get("sig"):
            log(f"\n🟢🟢🟢 SIGNATURE! {r['sig']}B")
            json.dump({"sig": "SEE_NETWORK", "len": r["sig"], "method": MN},
                      open("tv_slow_hit.json", "w"))
            break

    br.close()
    log("\n=== SELESAI ===")
