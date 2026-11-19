"""tv_final.py — token/verify dengan x-app-type:"" (KOSONG).

Temuan kunci dari ivs_js/027.js:
  tobAppType = (event && m_(event)) ? tobAppType : undefined
  m_(e) = Se.includes(e)   // Se = daftar ToB event
  event=2 (ChangePhone) TIDAK ada di Se -> x-app-type = "" (kosong)

Gue selama ini kirim "3" -> 211 (method_name tidak valid untuk app-type itu).

Flow tepat:
  1. init -> seq_no
  2. init_v2 -> ivs_utoken, change_phone_token
  3. ivs/methods {event:2, u_token} + header x-app-type:""
  4. ivs/method/select {v_token, method, event:2, u_token} + x-app-type:""
     -> response mungkin bawa r_token
  5. ivs/token/verify {method_name, event:2, u_token, r_token, v_token,
                       shopee_df, misc:{seed,operation:0}} + x-app-type:""
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


JS = r"""
async () => {
  const M='/api/v4/account/management', IVS='/api/v4/anti_fraud/ivs';
  const o = {steps: []};
  const post = async (p, b, appType) => {
    const h = {'Content-Type':'application/json','X-API-SOURCE':'pc',
               'X-Requested-With':'XMLHttpRequest','Accept':'application/json',
               'X-Shopee-Language':'id'};
    if (appType !== undefined) h['x-app-type'] = appType;
    const r = await fetch(p, {method:'POST', credentials:'include',
      headers: h, body: JSON.stringify(b||{})});
    let j=null; try { j = await r.json(); } catch(e){}
    return {s:r.status, e:j&&j.error, d:j&&j.data, raw:j};
  };

  // 1
  let r = await post(M+'/change_phone_init', {});
  o.steps.push({n:'init', e:r.e, auth:(r.d||{}).auth_required});

  // 2
  r = await post(M+'/change_phone_init_v2', {});
  const UT = (r.d||{}).ivs_utoken||'', CPT = (r.d||{}).change_phone_token||'';
  o.ut = UT; o.cpt = CPT;
  o.steps.push({n:'init_v2', e:r.e, ut:UT.length, cpt:CPT.length});

  // 3 methods — x-app-type KOSONG
  r = await post(IVS+'/methods', {event:2, u_token:UT}, '');
  const ms = Array.isArray(r.d) ? r.d : ((r.d||{}).methods||[]);
  o.methods = ms.map(x=>({t:x.type, vt:(x.v_token||'').length}));
  o.steps.push({n:'methods', e:r.e, list:o.methods});

  o.tv = [];
  for (const m of ms) {
    const mt = m.type, VT = m.v_token || '';

    // 4 select — x-app-type KOSONG
    const sel = await post(IVS+'/method/select',
      {v_token:VT, method:mt, event:2, u_token:UT}, '');
    o.steps.push({n:'select_'+mt, e:sel.e, d:sel.d,
                  r_token: sel.raw && sel.raw.r_token ? String(sel.raw.r_token).length : 0});

    // r_token: dari select kalau ada, else v_token
    const RT = (sel.raw && (sel.raw.r_token || (sel.d&&sel.d.r_token))) || VT;

    const NAMES = {2:'Password', 10:'NewShopeePayPin', 1:'OTP', 20:'DEVICE_TOKEN'};
    const MN = NAMES[mt] || String(mt);

    // 5 token/verify — x-app-type KOSONG
    const tv = await post(IVS+'/token/verify', {
      method_name: MN, event: 2, u_token: UT,
      r_token: RT, v_token: VT, shopee_df: '',
      misc: {seed: '', operation: 0}
    }, '');
    const sigLen = tv.d && tv.d.signature ? tv.d.signature.length : 0;
    o.tv.push({t:mt, mn:MN, e:tv.e, sig:sigLen, rt: (typeof RT==='string'?RT.length:0)});
    if (tv.e === 0 && sigLen) {
      o.HIT = {mn:MN, mt:mt, sig:tv.d.signature};
      break;
    }
  }
  return o;
}
"""

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,1000",
        "--disable-blink-features=AutomationControlled"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 1000},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    ctx.add_cookies(cookies)
    pg = ctx.new_page()
    log("=== buka shopee ===")
    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(15000)

    log("=== flow dengan x-app-type KOSONG ===")
    try:
        o = pg.evaluate(JS)
    except Exception as e:
        log(f"ERR {str(e)[:130]}")
        o = {}

    for s in o.get("steps", []):
        line = f"  {s['n']:14s} err={s.get('e')}"
        if "auth" in s:
            line += f" auth={s['auth']}"
        if "ut" in s:
            line += f" ut={s['ut']}B cpt={s['cpt']}B"
        if "list" in s:
            line += f" {s['list']}"
        if "r_token" in s:
            line += f" rt={s['r_token']}"
        if s.get("d") is not None and str(s["n"]).startswith("select"):
            line += f" d={str(s['d'])[:70]}"
        log(line)

    log("\n=== token/verify ===")
    for t in o.get("tv", []):
        log(f"  type={t['t']:3d} {t['mn']:18s} err={t['e']} sig={t['sig']} rt={t['rt']}")

    if o.get("HIT"):
        log(f"\n🟢🟢🟢🟢 SIGNATURE DAPAT! {len(o['HIT']['sig'])}B  method={o['HIT']['mn']}")
        json.dump(o["HIT"], open("tv_final_hit.json", "w"))
    else:
        log("\n❌ belum dapat signature")

    json.dump(o, open("tv_final.json", "w"), indent=1)
    br.close()
    log("\n=== SELESAI ===")
