"""tv_skip.py — coba paksa SkipVerification (100) & cari r_token asli.

Teori:
  - method/select untuk Password: r_token WAJIB beda dari v_token
  - method/select untuk SkipVerification: r_token = v_token (valid!)
  - Server hanya tawarkan [10, 2], tapi mungkin select(100) tetap diterima

Juga: cari endpoint apapun yang mengembalikan r_token.
"""
import json, sys, time
from playwright.sync_api import sync_playwright

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1553.txt"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"

ck = open(CK).read().strip()
cookies = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p
           for k, v in [p.strip().split("=", 1)]]


def log(*a):
    print(*a, flush=True)


JS = r"""
async () => {
  const M='/api/v4/account/management', IVS='/api/v4/anti_fraud/ivs';
  const o = {};
  const post = async (p, b, at) => {
    const h = {'Content-Type':'application/json','X-API-SOURCE':'pc',
               'X-Requested-With':'XMLHttpRequest','Accept':'application/json',
               'X-Shopee-Language':'id'};
    if (at !== undefined) h['x-app-type'] = at;
    const r = await fetch(p, {method:'POST', credentials:'include', headers:h,
                              body: JSON.stringify(b||{})});
    let j=null; try{j=await r.json();}catch(e){}
    return {s:r.status, e:j&&j.error, d:j&&j.data, raw:j};
  };

  await post(M+'/change_phone_init', {});
  const r2 = await post(M+'/change_phone_init_v2', {});
  const UT=(r2.d||{}).ivs_utoken||'', CPT=(r2.d||{}).change_phone_token||'';
  o.ut=UT.length; o.cpt=CPT.length;
  o.raw_init_v2 = r2.d ? Object.keys(r2.d) : null;

  const r3 = await post(IVS+'/methods', {event:2, u_token:UT}, '');
  const ms = Array.isArray(r3.d)?r3.d:((r3.d||{}).methods||[]);
  o.offered = ms.map(x=>x.type);

  // ambil SATU v_token (dari t=2)
  const pick = ms.find(x=>x.type===2) || ms[0];
  const VT = pick ? pick.v_token : '';
  o.vt = VT.length;
  o.pick = pick ? pick.type : null;

  // === A: select(100) SkipVerification ===
  const s100 = await post(IVS+'/method/select',
    {v_token:VT, method:100, event:2, u_token:UT}, '');
  o.select100 = {e:s100.e, d:s100.d, rt:s100.raw&&s100.raw.r_token};

  // === B: token/verify SkipVerification ===
  const tv100 = await post(IVS+'/token/verify', {
    method_name:'SkipVerification', event:2, u_token:UT,
    r_token:VT, v_token:VT, shopee_df:'', misc:{seed:'',operation:0}}, '');
  o.tv100 = {e:tv100.e, sig: tv100.d&&tv100.d.signature ? tv100.d.signature.length : 0};

  // === C: select(2) lalu token/verify Password ===
  const s2 = await post(IVS+'/method/select',
    {v_token:VT, method:2, event:2, u_token:UT}, '');
  o.select2 = {e:s2.e, d:s2.d, rt:s2.raw&&s2.raw.r_token};
  const tv2 = await post(IVS+'/token/verify', {
    method_name:'Password', event:2, u_token:UT,
    r_token:VT, v_token:VT, shopee_df:'', misc:{seed:'',operation:0}}, '');
  o.tv2 = {e:tv2.e, sig: tv2.d&&tv2.d.signature ? tv2.d.signature.length : 0};

  // === D: token/verify TANPA r_token ===
  const tvNo = await post(IVS+'/token/verify', {
    method_name:'Password', event:2, u_token:UT,
    v_token:VT, shopee_df:'', misc:{seed:'',operation:0}}, '');
  o.tv_no_r = {e:tvNo.e};

  // === E: token/verify r_token = CPT (change_phone_token) ===
  const tvCpt = await post(IVS+'/token/verify', {
    method_name:'Password', event:2, u_token:UT,
    r_token:CPT, v_token:VT, shopee_df:'', misc:{seed:'',operation:0}}, '');
  o.tv_cpt = {e:tvCpt.e, sig: tvCpt.d&&tvCpt.d.signature ? tvCpt.d.signature.length : 0};

  // === F: cari endpoint yang balas r_token ===
  o.rt_probe = [];
  for (const p of ['/api/v4/account/basic/get_account_info',
                   '/api/v4/account/management/get_change_phone_info',
                   '/api/v4/account/management/get_ivs_info',
                   '/api/v4/anti_fraud/ivs/get_token',
                   M+'/change_phone_precheck_v2']) {
    try {
      const rr = await post(p, {change_phone_token:CPT, new_phone:'6283191104601',
                                event:2, u_token:UT, method:2});
      o.rt_probe.push({p:p.split('/').pop(), e:rr.e,
        rt: rr.raw && rr.raw.r_token ? String(rr.raw.r_token).length : 0,
        keys: rr.raw ? Object.keys(rr.raw).slice(0,6) : null});
    } catch(e) { o.rt_probe.push({p:p.split('/').pop(), err:1}); }
    await new Promise(r=>setTimeout(r,400));
  }

  o.UT = UT; o.CPT = CPT; o.VTval = VT;
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

    log("=== probe SkipVerification + r_token hunt ===")
    try:
        o = pg.evaluate(JS)
    except Exception as e:
        log(f"ERR {str(e)[:150]}")
        o = {}

    log(f"  offered={o.get('offered')} vt={o.get('vt')}B cpt={o.get('cpt')}B")
    log(f"  init_v2 keys={o.get('raw_init_v2')}")
    log(f"\n  A select(100)     err={o.get('select100',{}).get('e')} rt={o.get('select100',{}).get('rt')}")
    log(f"  B tv SkipVerif    err={o.get('tv100',{}).get('e')} sig={o.get('tv100',{}).get('sig')}")
    log(f"  C select(2)       err={o.get('select2',{}).get('e')} rt={o.get('select2',{}).get('rt')}")
    log(f"    tv Password     err={o.get('tv2',{}).get('e')} sig={o.get('tv2',{}).get('sig')}")
    log(f"  D tv tanpa r      err={o.get('tv_no_r',{}).get('e')}")
    log(f"  E tv r=cpt        err={o.get('tv_cpt',{}).get('e')} sig={o.get('tv_cpt',{}).get('sig')}")
    log("\n  F probe endpoint yang balas r_token:")
    for p in o.get("rt_probe", []):
        log(f"    {p.get('p','?'):28s} err={p.get('e')} rt={p.get('rt')} keys={p.get('keys')}")

    json.dump(o, open("tv_skip.json", "w"), indent=1)
    br.close()
    log("\n=== SELESAI ===")
