# -*- coding: utf-8 -*-
"""token_verify_probe.py — cari tahu KENAPA browser tidak panggil ivs/token/verify.

Fakta dari MITM:
  - login_by_password -> error=98 {ivs_flow_no, ivs_token}
  - ivs/methods       -> [{type:7, v_token}]  atau  [{type:20, v_token}]
  - method/select     -> error=0, data SEMUA null
  - device-token/verify -> error=0 status:2
  - ivs/token/verify  -> TIDAK PERNAH DIPANGGIL
  - SPC_ST            -> TIDAK PERNAH muncul

Hipotesis:
  A. method/select data null = select GAGAL diam-diam -> token/verify tidak dijadwalkan
  B. type:20 butuh langkah tambahan (credit_liveness_check / operation_code)
  C. token/verify hanya untuk type lain (password/OTP), bukan QR/device

Uji: panggil token/verify LANGSUNG dengan kombinasi param berbeda,
dari dalam browser (header SDK asli), pakai sesi login yang baru dibuat.
"""
import sys, json, time

USER = sys.argv[1] if len(sys.argv) > 1 else "yq7uwh456q"
PASSW = sys.argv[2] if len(sys.argv) > 2 else "qwertyui123"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"
OUT = "/root/shopee-verify/tv_probe.json"


def log(*a):
    print(*a, flush=True)


from playwright.sync_api import sync_playwright

results = []

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,1000"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 1000},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    pg = ctx.new_page()

    ivs_seen = []

    def onresp(r):
        if "/api/v4/" in r.url and any(k in r.url for k in ("ivs", "login", "anti_fraud")):
            try:
                t = r.text()
            except Exception:
                return
            ivs_seen.append({"url": r.url.split("shopee.co.id")[-1][:80],
                             "status": r.status, "body": t[:3000]})
            log(f"  ← {r.status} {r.url.split('shopee.co.id')[-1][:65]}")

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
    pg.wait_for_timeout(10000)

    # Ambil ivs_token + flow_no dari response login
    login_data = {}
    for it in ivs_seen:
        if "login_by_password" in it["url"]:
            try:
                j = json.loads(it["body"])
                d = j.get("data") or {}
                if d.get("ivs_token"):
                    login_data = d
            except Exception:
                pass

    log(f"  url: {pg.url[:75]}")
    log(f"  captured: {len(ivs_seen)} api resp")
    for it in ivs_seen:
        log(f"    {it['url'][:55]} ({len(it['body'])}B)")
    log(f"  ivs_flow_no: {login_data.get('ivs_flow_no')}")
    log(f"  ivs_token len: {len(login_data.get('ivs_token') or '')}")

    # fallback: ambil dari URL /verify/ivs
    if not login_data.get("ivs_token"):
        import urllib.parse as up
        q = up.parse_qs(up.urlparse(pg.url).query)
        ut = (q.get("u_token") or [""])[0]
        if ut:
            login_data = {"ivs_token": ut, "ivs_flow_no": None, "_from_url": True}
            log(f"  ✓ ivs_token dari URL (len={len(ut)})")

    ivs_token = login_data.get("ivs_token")
    flow_no = login_data.get("ivs_flow_no")

    if not ivs_token:
        log("  ❌ tidak ada ivs_token, berhenti")
        json.dump({"error": "no ivs_token", "seen": ivs_seen}, open(OUT, "w"), indent=1)
        br.close()
        sys.exit(1)

    # === FASE 2: panggil token/verify dengan berbagai param ===
    log("\n=== 2. probe ivs/token/verify ===")

    variants = [
        ("baseline", {"u_token": ivs_token}),
        ("flow_no", {"u_token": ivs_token, "ivs_flow_no": flow_no}),
        ("event2", {"u_token": ivs_token, "event": 2}),
        ("event1", {"u_token": ivs_token, "event": 1}),
        ("flow_event2", {"u_token": ivs_token, "ivs_flow_no": flow_no, "event": 2}),
        ("token_field", {"token": ivs_token}),
        ("utoken_flow", {"utoken": ivs_token, "flow_no": flow_no}),
    ]

    for name, body in variants:
        r = pg.evaluate("""async (args)=>{
          const [body] = args;
          try{
            const res = await fetch('/api/v4/anti_fraud/ivs/token/verify', {
              method:'POST', credentials:'include',
              headers:{'Accept':'application/json','Content-Type':'application/json',
                       'X-API-SOURCE':'pc','X-Requested-With':'XMLHttpRequest',
                       'X-Shopee-Language':'id','Affiliate-Id':''},
              body: JSON.stringify(body)
            });
            let j=null; try{ j = await res.json(); }catch(e){}
            return {s:res.status, j};
          }catch(e){ return {s:0, err:String(e).slice(0,100)}; }
        }""", [body])
        log(f"  [{name}] -> {r.get('s')} err={((r.get('j') or {}).get('error'))}")
        results.append({"variant": name, "body_sent": list(body.keys()), "result": r})
        pg.wait_for_timeout(1200)

    # === FASE 3: cek method/select detail (kenapa null) ===
    log("\n=== 3. cek ulang method/select ===")
    for it in ivs_seen:
        if "method/select" in it["url"]:
            log(f"  select resp: {it['body'][:300]}")
        if "ivs/methods" in it["url"]:
            log(f"  methods resp: {it['body'][:400]}")

    json.dump({"login": login_data, "results": results, "seen": ivs_seen},
              open(OUT, "w"), indent=1)
    log(f"\n  -> {OUT}")
    br.close()

log("\n=== SELESAI ===")
