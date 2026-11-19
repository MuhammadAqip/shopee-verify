# -*- coding: utf-8 -*-
"""cp_inbrowser.py — JALANKAN SELURUH FLOW change_phone DARI DALAM BROWSER.

Kenapa: SDK generate x-sap-sec BERBEDA per-endpoint (2916B untuk cart,
3576B untuk change_phone_init). Header itu hanya valid untuk endpoint
yang sama. Jadi token/verify HARUS dipanggil dari dalam page context
supaya SDK yang generates header-nya.

Langkah:
  1. Buka shopee dengan cookie akun
  2. Dari page.evaluate, jalankan fetch chain:
     init -> init_v2 -> ivs/methods -> method/select -> token/verify
  3. Tangkap response token/verify (signature)
  4. Lanjut precheck -> send_vcode
  5. Coba selesaikan sampai commit kalau dapat signature
"""
import json, sys, time

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1553.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6283191104601"
OUT = "/root/shopee-verify/inbrowser_result.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"


def log(*a):
    print(*a, flush=True)


from playwright.sync_api import sync_playwright

ck = open(CK).read().strip()
cookies = []
for p in ck.split(";"):
    if "=" in p:
        k, v = p.strip().split("=", 1)
        cookies.append({"name": k, "value": v,
                        "domain": ".shopee.co.id", "path": "/"})

JS_FLOW = r"""
async (newPhone) => {
  const M = '/api/v4/account/management';
  const IVS = '/api/v4/anti_fraud/ivs';
  const out = {steps: []};

  async function post(path, body, useAntibot) {
    const t0 = performance.now();
    const res = await fetch(path, {
      method: 'POST', credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-API-SOURCE': 'pc',
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'application/json',
        'X-Shopee-Language': 'id'
      },
      body: JSON.stringify(body || {})
    });
    const ms = Math.round(performance.now() - t0);
    let j = null;
    try { j = await res.json(); } catch(e) {}
    return {s: res.status, e: j && j.error, d: j && j.data, ms: ms};
  }

  // 1 init
  let r = await post(M + '/change_phone_init', {});
  out.steps.push({n:'init', e:r.e, d:r.d, ms:r.ms});
  const authReq = (r.d||{}).auth_required;

  // 2 init_v2
  r = await post(M + '/change_phone_init_v2', {});
  out.steps.push({n:'init_v2', e:r.e,
    keys: r.d ? Object.keys(r.d) : null,
    ut_len: r.d && r.d.ivs_utoken ? r.d.ivs_utoken.length : 0,
    cp_len: r.d && r.d.change_phone_token ? r.d.change_phone_token.length : 0,
    ivs_req: r.d && r.d.ivs_required, ms:r.ms});
  const UT = (r.d||{}).ivs_utoken || '';
  const CPT = (r.d||{}).change_phone_token || '';
  out.ut = UT; out.cpt = CPT;

  // 3 methods
  r = await post(IVS + '/methods', {event: 2, u_token: UT});
  const ms = Array.isArray(r.d) ? r.d : ((r.d||{}).methods || []);
  out.steps.push({n:'methods', e:r.e,
    list: ms.map(x=>({t:x.type, vtlen:(x.v_token||'').length})), ms:r.ms});
  out.methods = ms;

  const NAMES = {1:'OTP',2:'Password',3:'ShopeePay',5:'AuthenticationLink',
    6:'Email',7:'Qr',8:'EmailLink',10:'NewShopeePayPin',11:'WhatsAppLink',
    14:'SecurityQuestions',15:'SecurityEmail',17:'SecurityDeviceToken',
    20:'DEVICE_TOKEN',100:'SkipVerification'};

  // 4-6 per method
  for (const m of ms) {
    const mt = m.type, VT = m.v_token || '', MN = NAMES[mt];
    if (!MN) continue;

    r = await post(IVS + '/method/select',
      {v_token: VT, method: mt, event: 2, u_token: UT});
    out.steps.push({n:'select_'+mt, e:r.e, d:r.d, ms:r.ms});

    // token/verify — SKEMA ASLI: method_name STRING + shopee_df
    const body = {
      method_name: MN, event: 2, u_token: UT,
      r_token: VT, v_token: VT, shopee_df: '',
      misc: {seed: '', operation: 0}
    };
    r = await post(IVS + '/token/verify', body);
    out.steps.push({n:'token_verify_'+mt, e:r.e,
      sig_len: r.d && r.d.signature ? r.d.signature.length : 0,
      d_keys: r.d ? Object.keys(r.d) : null, ms:r.ms});

    if (r.e === 0 && r.d && r.d.signature) {
      out.sig = r.d.signature;
      out.sig_method = MN;
      out.sig_type = mt;
      break;
    }
  }

  return out;
}
"""

res = {}

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,1000",
        "--disable-blink-features=AutomationControlled"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 1000},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    ctx.add_cookies(cookies)
    pg = ctx.new_page()

    # rekam request token/verify
    rec = []

    def onreq(r):
        if "token/verify" in r.url:
            rec.append({"req": True, "b": (r.post_data or "")[:800],
                        "hdr": {k: v for k, v in r.headers.items()
                                if k.lower().startswith(("x-sap", "af-ac", "x-sz"))}})

    def onresp(r):
        if "token/verify" in r.url:
            try:
                rec.append({"resp": True, "s": r.status, "b": r.text()[:600]})
            except Exception:
                pass

    pg.on("request", onreq)
    pg.on("response", onresp)

    log("=== buka shopee (SDK init) ===")
    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(14000)

    log("=== jalankan flow dari dalam browser ===")
    try:
        res = pg.evaluate(JS_FLOW, NEWPHONE)
    except Exception as e:
        log(f"  ERR: {str(e)[:120]}")
        res = {}

    log("\n=== STEPS ===")
    for s in res.get("steps", []):
        line = f"  {s['n']:22s} err={s.get('e')}"
        if "ut_len" in s:
            line += f" ut={s['ut_len']}B cp={s['cp_len']}B ivsreq={s.get('ivs_req')}"
        if "list" in s:
            line += f" {s['list']}"
        if "sig_len" in s:
            line += f" SIG={'✅ %dB' % s['sig_len'] if s['sig_len'] else 'N'}"
        if s.get("d") is not None and s["n"].startswith("select"):
            line += f" {str(s['d'])[:70]}"
        log(line)

    log(f"\n=== token/verify request/response ({len(rec)}) ===")
    for r in rec:
        if r.get("req"):
            log(f"  REQ body: {r['b'][:280]}")
            log(f"      hdr: {list(r['hdr'].keys())}")
        else:
            log(f"  RESP {r.get('s')}: {r.get('b','')[:200]}")

    if res.get("sig"):
        log(f"\n🟢🟢 SIGNATURE DAPAT! {len(res['sig'])}B method={res.get('sig_method')}")
    else:
        log("\n❌ signature tidak didapat")

    json.dump({"res": res, "net": rec}, open(OUT, "w"), indent=1)
    log(f"-> {OUT}")
    br.close()
