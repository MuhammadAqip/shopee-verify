# -*- coding: utf-8 -*-
"""schema_v2.py — pakai enum + skema PERSIS dari bundle.

Dari ivs_js/026.js (MethodNo):
  Qr=7, Password=2, DEVICE_TOKEN=20, SkipVerification=100 ...
Dari ivs_js/027.js:
  token/verify body: {method_name, event, u_token, r_token, v_token, shopee_df,
                      misc:{seed, operation}}
  method/select body: {v_token, method, event, u_token}

Temuan sebelumnya:
  method_name=int(7)   -> 49900000 (param kurang)
  method_name="7"      -> 211        (nilai tak valid)

=> method_name BUKAN int. Nama ENUM-nya? atau field lain yang kurang.

Uji: method_name sebagai NAMA ("Qr","QrCode"), atau tetap int + tambah field.
Juga coba skip: langsung token/verify tanpa select.
"""
import sys, json

USER = sys.argv[1] if len(sys.argv) > 1 else "yq7uwh456q"
PASSW = sys.argv[2] if len(sys.argv) > 2 else "qwertyui123"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
OUT = "/root/shopee-verify/schema_v2.json"


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
        if "/api/v4/" in r.url and any(k in r.url for k in ("ivs", "login")):
            try:
                seen.append({"url": r.url.split("shopee.co.id")[-1][:80],
                             "body": r.text()[:3000]})
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
    log(f"  u_token={len(u_token)}B type={mtype} v_token={len(vtok)}B")

    # method/select dulu (urutan benar)
    log("\n=== select ===")
    pg.evaluate("""async (b)=>{
      await fetch('/api/v4/anti_fraud/ivs/method/select',{method:'POST',
        credentials:'include',headers:{'Accept':'application/json',
        'Content-Type':'application/json','X-API-SOURCE':'pc',
        'X-Requested-With':'XMLHttpRequest','X-Shopee-Language':'id'},
        body:JSON.stringify(b)});
    }""", {"v_token": vtok, "method": mtype, "event": 1, "u_token": u_token})
    pg.wait_for_timeout(2000)

    # cari r_token
    r_token = None
    for it in seen:
        try:
            j = json.loads(it["body"])
        except Exception:
            continue
        d = j.get("data")
        if isinstance(d, dict):
            r_token = d.get("r_token") or d.get("rToken") or r_token
    log(f"  r_token: {'Y' if r_token else 'N'}")

    # Variasi method_name
    variants = []
    for mn_label, mn in [
        ("int7", 7), ("str7", "7"), ("name_Qr", "Qr"),
        ("name_QRCode", "QRCode"), ("name_qr", "qr"),
        ("no_mn", None),
    ]:
        body = {"event": 1, "u_token": u_token, "r_token": r_token,
                "v_token": vtok, "shopee_df": None,
                "misc": {"seed": None, "operation": 0}}
        if mn is not None:
            body["method_name"] = mn
        variants.append((mn_label, body))

    # Tambah varian dengan field 'method' (bukan method_name)
    variants.append(("field_method", {"method": mtype, "event": 1,
                                      "u_token": u_token, "r_token": r_token,
                                      "v_token": vtok, "shopee_df": None,
                                      "misc": {"seed": None, "operation": 0}}))
    # Event sebagai string
    variants.append(("ev_str", {"method_name": mtype, "event": "1",
                                "u_token": u_token, "r_token": r_token,
                                "v_token": vtok, "shopee_df": None,
                                "misc": {"seed": None, "operation": 0}}))

    log("\n=== token/verify variasi method_name ===")
    for name, b in variants:
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
        mark = "★★" if sig else ("  " if e == 49900000 else "★ ")
        log(f" {mark}[{name:14s}] err={e} sig={'Y' if sig else 'N'} data={str(dd)[:70]}")
        res["tests"].append({"name": name, "err": e,
                             "sig": bool(sig), "data": str(dd)[:120]})
        if sig:
            res["signature"] = sig
        pg.wait_for_timeout(1100)

    json.dump(res, open(OUT, "w"), indent=1)
    br.close()

log("\n=== SELESAI ===")
