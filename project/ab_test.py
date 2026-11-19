# -*- coding: utf-8 -*-
"""ab_test.py — cari variabel yang BIKIN 90309999 hilang.

Fakta:
  - param minimal: utoken + flow_no + type  (8 kombinasi lolos 49900000)
  - SEMUA kena 90309999 = sesi belum trusted

Pertanyaan: APA yang bikin sesi trusted?
Yang sudah diuji negatif (dari sesi sebelum): cookie, IP, TLS, header, fresh ctx.

Yang BELUM diuji dengan endpoint token/verify:
  A. Device fingerprint dari browser ASLI vs headless
  B. Urutan request: init_v2 -> methods -> select -> token/verify (jangan skip select)
  C. Jalankan select DULU baru token/verify
  D. Kirim dari halaman /verify/ivs (context benar), bukan /buyer/login
  E. sec-ch-ua headless vs headed

Fokus: A + C + D.
"""
import sys, json, time

USER = sys.argv[1] if len(sys.argv) > 1 else "yq7uwh456q"
PASSW = sys.argv[2] if len(sys.argv) > 2 else "qwertyui123"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
OUT = "/root/shopee-verify/ab_test.json"


def log(*a):
    print(*a, flush=True)


from playwright.sync_api import sync_playwright

res = {}

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage",
        "--window-size=1366,1000",
        # coba hilangkan jejak headless di level flag
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
    ])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 1000},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY},
                         extra_http_headers={"Accept-Language": "id-ID,id;q=0.9,en;q=0.8"})
    ctx.add_init_script("""
      Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
      Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
      Object.defineProperty(navigator,'languages',{get:()=>['id-ID','id','en']});
      window.chrome={runtime:{}};
    """)
    pg = ctx.new_page()

    seen = []

    def onresp(r):
        if "/api/v4/" in r.url and any(k in r.url for k in ("ivs", "login")):
            try:
                seen.append({"url": r.url.split("shopee.co.id")[-1][:70],
                             "body": r.text()[:2500]})
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
    pg.wait_for_timeout(11000)

    flow_no = ivs_token = None
    methods = []
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

    log(f"  url: {pg.url[:70]}")
    log(f"  flow_no: {flow_no}  methods: {[(m.get('type')) for m in methods]}")
    log(f"  ivs_token: {len(ivs_token or '')}B")

    if not ivs_token:
        log("  ❌ no token")
        br.close()
        sys.exit(1)

    vtok = methods[0]["v_token"] if methods else None
    mtype = methods[0]["type"] if methods else 7
    res["flow_no"] = flow_no
    res["methods"] = [{"type": m.get("type"), "len": len(m.get("v_token") or "")} for m in methods]

    # === 2. jalankan method/select DULU ===
    log("\n=== 2. method/select (urut benar) ===")
    sel = pg.evaluate("""async (args)=>{
      const [b] = args;
      const r = await fetch('/api/v4/anti_fraud/ivs/method/select',{
        method:'POST',credentials:'include',
        headers:{'Accept':'application/json','Content-Type':'application/json',
                 'X-API-SOURCE':'pc','X-Requested-With':'XMLHttpRequest',
                 'X-Shopee-Language':'id'},
        body:JSON.stringify(b)});
      let j=null;try{j=await r.json();}catch(e){}
      return {s:r.status,j};
    }""", [{"method_name": mtype, "event": 1, "u_token": ivs_token,
            "v_token": vtok, "misc": {"operation": 0}}])
    log(f"  select -> {sel.get('s')} err={(sel.get('j') or {}).get('error')} "
        f"data={str((sel.get('j') or {}).get('data'))[:140]}")
    res["select"] = sel
    pg.wait_for_timeout(1500)

    # === 3. token/verify dari HALAMAN IVS ===
    log("\n=== 3. token/verify dari /verify/ivs ===")
    try:
        if "/verify/ivs" not in pg.url:
            import urllib.parse as up
            q = up.parse_qs(up.urlparse(pg.url).query)
            log(f"  url sekarang: {pg.url[:60]}")
    except Exception:
        pass

    tests = [
        ("nvp1", {"utoken": ivs_token, "flow_no": flow_no, "type": mtype}),
        ("nvp2", {"utoken": ivs_token, "flow_no": flow_no, "type": mtype,
                  "event": 1}),
        ("nvp3", {"utoken": ivs_token, "flow_no": flow_no, "type": mtype,
                  "v_token": vtok}),
        ("nvp4", {"utoken": ivs_token, "flow_no": flow_no, "type": mtype,
                  "v_token": vtok, "event": 1}),
    ]
    res["token_verify"] = []
    for name, b in tests:
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
        log(f"  [{name}] err={e} data={str((r.get('j') or {}).get('data'))[:90]}")
        res["token_verify"].append({"name": name, "err": e,
                                    "resp": (r.get("j") or {}).get("data")})
        pg.wait_for_timeout(1000)

    # === 4. cek sec-ch-ua ===
    log("\n=== 4. fingerprint check ===")
    fp = pg.evaluate("""()=>({
      ua:navigator.userAgent.slice(0,80),
      webdriver:navigator.webdriver,
      plugins:navigator.plugins.length,
      langs:navigator.languages,
      canvas: (()=>{try{const c=document.createElement('canvas');
        const x=c.getContext('2d');x.textBaseline='top';x.font='14px Arial';
        x.fillText('fp',2,2);return c.toDataURL().slice(-30);}catch(e){return 'err'}})(),
      tz:Intl.DateTimeFormat().resolvedOptions().timeZone,
      memory:navigator.deviceMemory,
    })""")
    log(f"  {json.dumps(fp)}")
    res["fingerprint"] = fp

    json.dump(res, open(OUT, "w"), indent=1)
    log(f"\n  -> {OUT}")
    br.close()

log("\n=== SELESAI ===")
