# -*- coding: utf-8 -*-
"""tv_params.py — bongkar parameter wajib ivs/token/verify.

Petunjuk dari probe:
  {u_token}                -> 49900000 (param kurang)
  {utoken, flow_no}        -> 90309999 (param CUKUP, sesi ditolak anti-bot)
  {token}                  -> 49900000

Artinya: nama field = utoken + flow_no (atau serupa).
49900000 = PARAMETER KURANG. Kita perlu temukan LENGKAPnya.

Pendekatan: brute-force kombinasi nama field yang mungkin,
deteksi transisi 49900000 (kurang param) -> bukan 49900000 (param cukup).
"""
import sys, json, time

USER = sys.argv[1] if len(sys.argv) > 1 else "yq7uwh456q"
PASSW = sys.argv[2] if len(sys.argv) > 2 else "qwertyui123"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
OUT = "/root/shopee-verify/tv_params.json"


def log(*a):
    print(*a, flush=True)


from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,1000"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 1000},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    pg = ctx.new_page()

    seen = []

    def onresp(r):
        if "/api/v4/" in r.url and any(k in r.url for k in ("ivs", "login")):
            try:
                seen.append({"url": r.url.split("shopee.co.id")[-1][:70],
                             "body": r.text()[:2000]})
            except Exception:
                pass

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
    pg.wait_for_timeout(9000)

    # === Kumpulkan semua token ===
    flow_no = None
    ivs_token = None
    methods = []
    select_resp = None
    for it in seen:
        try:
            j = json.loads(it["body"])
        except Exception:
            continue
        d = j.get("data")
        if "login_by_password" in it["url"] and isinstance(d, dict):
            flow_no = d.get("ivs_flow_no") or flow_no
            ivs_token = d.get("ivs_token") or ivs_token
        if "ivs/methods" in it["url"] and isinstance(d, list):
            methods = d
        if "method/select" in it["url"]:
            select_resp = j

    log(f"  flow_no: {flow_no}")
    log(f"  ivs_token: {len(ivs_token or '')}B")
    log(f"  methods: {[(m.get('type'),len(m.get('v_token') or '')) for m in methods]}")
    log(f"  select: {str(select_resp)[:200]}")

    if not ivs_token:
        import urllib.parse as up
        q = up.parse_qs(up.urlparse(pg.url).query)
        ivs_token = (q.get("u_token") or [""])[0]
        log(f"  ivs_token dari URL: {len(ivs_token)}B")

    v_token = methods[0].get("v_token") if methods else None
    mtype = methods[0].get("type") if methods else None

    # === FASE 2: brute param ===
    log("\n=== 2. brute kombinasi param token/verify ===")

    BASE = {"utoken": ivs_token, "flow_no": flow_no}

    cands = [
        ("base", dict(BASE)),
        ("+v_token", {**BASE, "v_token": v_token}),
        ("+event", {**BASE, "event": 2}),
        ("+event_type", {**BASE, "event_type": 2}),
        ("+method", {**BASE, "method_type": mtype}),
        ("+method_name", {**BASE, "method_name": mtype}),
        ("+type", {**BASE, "type": mtype}),
        ("+v+ev", {**BASE, "v_token": v_token, "event": 2}),
        ("+v+method", {**BASE, "v_token": v_token, "method_type": mtype}),
        ("+v+mname", {**BASE, "v_token": v_token, "method_name": mtype}),
        ("+v+t+ev", {**BASE, "v_token": v_token, "type": mtype, "event": 2}),
        ("+v+mn+ev", {**BASE, "v_token": v_token, "method_name": mtype, "event": 2}),
        ("+v+misc", {**BASE, "v_token": v_token,
                     "misc": {"operation": 0}}),
        ("+v+misc2", {**BASE, "v_token": v_token, "misc": {"operation": 2}}),
    ]

    results = []
    hitted = None

    for name, body in cands:
        body = {k: v for k, v in body.items() if v is not None}
        r = pg.evaluate("""async (args)=>{
          const [body] = args;
          try{
            const res = await fetch('/api/v4/anti_fraud/ivs/token/verify', {
              method:'POST', credentials:'include',
              headers:{'Accept':'application/json','Content-Type':'application/json',
                       'X-API-SOURCE':'pc','X-Requested-With':'XMLHttpRequest',
                       'X-Shopee-Language':'id'},
              body: JSON.stringify(body)
            });
            let j=null; try{ j = await res.json(); }catch(e){}
            return {s:res.status, j};
          }catch(e){ return {s:0, err:String(e).slice(0,100)}; }
        }""", [body])
        err = (r.get("j") or {}).get("error")
        mark = "  " if err == 49900000 else "★"
        log(f" {mark}[{name:14s}] err={err}")
        results.append({"variant": name, "fields": list(body.keys()), "err": err,
                        "resp": (r.get("j") or {}).get("data")})
        if err not in (49900000, None, 0) or (r.get("j") or {}).get("data"):
            hitted = (name, body, r)
        pg.wait_for_timeout(900)

    log("\n=== 3. kesimpulan ===")
    ok = [r for r in results if r["err"] != 49900000]
    if ok:
        log(f"  ★ {len(ok)} kombinasi MELEWATI error 49900000:")
        for r in ok:
            log(f"     {r['variant']}: err={r['err']} data={str(r['resp'])[:100]}")
    else:
        log("  semua 49900000 — nama field utoken/flow_no mungkin salah")

    json.dump({"flow_no": flow_no, "methods": methods,
               "select": select_resp, "results": results},
              open(OUT, "w"), indent=1)
    log(f"  -> {OUT}")
    br.close()

log("\n=== SELESAI ===")
