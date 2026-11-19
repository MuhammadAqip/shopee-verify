# -*- coding: utf-8 -*-
"""real_schema.py — pakai SKEMA ASLI dari bundle 027.js.

Dari RE ivs_js/027.js:
  ivs/methods   : {event, u_token}                 + header x-app-type
  method/select : {v_token, method, event, u_token} + header x-app-type
  token/verify  : {method_name, event, u_token, r_token, v_token,
                   shopee_df, misc:{seed, operation}}
                  + header x-app-type
                  + antiFraudConfig.deviceFingerPrint -> security_device_fingerprint

r_token berasal dari verify_password / flow sebelumnya.
Kalau tidak ada r_token, kirim null (SDK juga kirim null bila tak ada).

Uji 2 fase:
  Fase A: type 7 (QR) — tanpa r_token
  Fase B: cari r_token dari response lain; kalau ada, pakai.
"""
import sys, json, time

USER = sys.argv[1] if len(sys.argv) > 1 else "yq7uwh456q"
PASSW = sys.argv[2] if len(sys.argv) > 2 else "qwertyui123"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
OUT = "/root/shopee-verify/real_schema.json"


def log(*a):
    print(*a, flush=True)


from playwright.sync_api import sync_playwright

res = {"tests": []}

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
        if "/api/v4/" in r.url:
            try:
                b = r.text()
            except Exception:
                return
            if any(k in r.url for k in ("ivs", "login", "anticrawl", "captcha")):
                seen.append({"url": r.url.split("shopee.co.id")[-1][:80], "body": b[:3000]})

    pg.on("response", onresp)

    log("=== 1. login ===")
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

    u_token = None
    flow_no = None
    methods = []
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

    log(f"  u_token: {len(u_token or '')}B  flow: {flow_no}")
    log(f"  methods: {[(m.get('type'), len(m.get('v_token') or '')) for m in methods]}")

    if not u_token or not methods:
        log("  ❌ token/methods kosong")
        json.dump(res, open(OUT, "w"), indent=1)
        br.close()
        sys.exit(1)

    mtype = methods[0]["type"]
    vtok = methods[0]["v_token"]

    # === ambil device fingerprint dari SDK ===
    log("\n=== 2. ambil device fingerprint ===")
    dfp = pg.evaluate("""()=>{
      try{
        if (window.__SHOPEE_DFP__) return String(window.__SHOPEE_DFP__);
        if (window.__shopee_df) return String(window.__shopee_df);
        if (window.ShopeeDFP && window.ShopeeDFP.get) return String(window.ShopeeDFP.get());
      }catch(e){}
      return null;
    }""")
    log(f"  dfp: {(str(dfp)[:60] if dfp else 'null')}")
    res["dfp"] = (str(dfp)[:100] if dfp else None)

    # === 3. method/select skema asli ===
    log("\n=== 3. method/select (skema asli) ===")
    sel = pg.evaluate("""async (args)=>{
      const [b]=args;
      const r=await fetch('/api/v4/anti_fraud/ivs/method/select',{
        method:'POST',credentials:'include',
        headers:{'Accept':'application/json','Content-Type':'application/json',
                 'X-API-SOURCE':'pc','X-Requested-With':'XMLHttpRequest',
                 'X-Shopee-Language':'id'},
        body:JSON.stringify(b)});
      let j=null;try{j=await r.json();}catch(e){}
      return {s:r.status,j};
    }""", [{"v_token": vtok, "method": mtype, "event": 1, "u_token": u_token}])
    log(f"  select -> {sel.get('s')} err={(sel.get('j') or {}).get('error')} "
        f"data={str((sel.get('j') or {}).get('data'))[:160]}")
    res["select"] = sel
    pg.wait_for_timeout(2000)

    # cari r_token dari semua response
    r_token = None
    for it in seen:
        try:
            j = json.loads(it["body"])
        except Exception:
            continue
        for k in ("r_token", "rToken"):
            if isinstance(j.get("data"), dict) and j["data"].get(k):
                r_token = j["data"][k]
    log(f"  r_token: {(r_token[:20]+'...') if r_token else 'null'}")

    # === 4. token/verify SKEMA ASLI ===
    log("\n=== 4. token/verify (skema asli) ===")
    payloads = [
        ("full", {"method_name": mtype, "event": 1, "u_token": u_token,
                  "r_token": r_token, "v_token": vtok, "shopee_df": dfp,
                  "misc": {"seed": None, "operation": 0}}),
        ("no_df", {"method_name": mtype, "event": 1, "u_token": u_token,
                   "r_token": r_token, "v_token": vtok, "shopee_df": None,
                   "misc": {"seed": None, "operation": 0}}),
        ("str_method", {"method_name": str(mtype), "event": 1, "u_token": u_token,
                        "r_token": r_token, "v_token": vtok, "shopee_df": dfp,
                        "misc": {"seed": None, "operation": 0}}),
        ("ev2", {"method_name": mtype, "event": 2, "u_token": u_token,
                 "r_token": r_token, "v_token": vtok, "shopee_df": dfp,
                 "misc": {"seed": None, "operation": 0}}),
        ("ev0", {"method_name": mtype, "event": 0, "u_token": u_token,
                 "r_token": r_token, "v_token": vtok, "shopee_df": dfp,
                 "misc": {"seed": None, "operation": 0}}),
        ("no_misc", {"method_name": mtype, "event": 1, "u_token": u_token,
                     "r_token": r_token, "v_token": vtok, "shopee_df": dfp}),
    ]

    for name, b in payloads:
        r = pg.evaluate("""async (args)=>{
          const [body]=args;
          const r=await fetch('/api/v4/anti_fraud/ivs/token/verify',{
            method:'POST',credentials:'include',
            headers:{'Accept':'application/json','Content-Type':'application/json',
                     'X-API-SOURCE':'pc','X-Requested-With':'XMLHttpRequest',
                     'X-Shopee-Language':'id'},
            body:JSON.stringify(body)});
          let j=null;try{j=await r.json();}catch(e){}
          return {s:r.status,j};
        }""", [b])
        e = (r.get("j") or {}).get("error")
        dd = (r.get("j") or {}).get("data")
        sig = (dd or {}).get("signature") if isinstance(dd, dict) else None
        mark = "★★ SIG!" if sig else ("  " if e == 49900000 else "★ ")
        log(f" {mark}[{name:12s}] err={e} sig={'Y('+str(len(sig))+'B)' if sig else 'N'}")
        res["tests"].append({"name": name, "err": e,
                             "sig_len": len(sig) if sig else 0,
                             "data": str(dd)[:150]})
        if sig:
            res["signature"] = sig
            log(f"     🟢 SIGNATURE: {sig[:60]}...")
        pg.wait_for_timeout(1200)

    json.dump(res, open(OUT, "w"), indent=1)
    log(f"\n  -> {OUT}")
    br.close()

log("\n=== SELESAI ===")
