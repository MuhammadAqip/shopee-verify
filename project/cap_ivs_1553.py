# -*- coding: utf-8 -*-
"""cap_ivs_1553.py — buka halaman ivs lewat MITM, tangkap v_token akun 15539296185."""
import sys, json, time
sys.path.insert(0, "/root/shopee-verify")
from full_flow import Flow
from playwright.sync_api import sync_playwright

COOKIE = open("/root/shopee-verify/ck_1553.txt").read().strip()
CSRF = "3929567fdad6e3608eb25fd137f69955"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

# 1) dari Python: init + password -> u_token, r_token
f = Flow(cookie=COOKIE)
f.csrf = CSRF
print("=== init_v2 ===")
r1 = f.step1_init()
print(json.dumps(r1, ensure_ascii=False))
print("=== verify_password ===")
r4 = f.step4_password("qwertyui123")
print(json.dumps(r4, ensure_ascii=False))
if not (r1["ok"] and r4["ok"]):
    sys.exit("init/password gagal")

json.dump({"cp_token": f.cp_token, "u_token": f.u_token,
           "r_token": f.r_token},
          open("/root/shopee-verify/ivs_tokens_1553.json", "w"))
print("\n[token disimpan ivs_tokens_1553.json]")

# 2) browser via MITM: buka /verify/ivs, capture request ivs/methods
print("\n=== buka halaman /verify/ivs lewat MITM :8099 ===")
with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1420, "height": 900},
                         timezone_id="Asia/Jakarta",
                         ignore_https_errors=True,
                         proxy={"server": "http://127.0.0.1:8099"})
    ctx.add_cookies([
        {"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
        for k, _, v in (p.partition("=") for p in
                        [x.strip() for x in COOKIE.split(";")])
        if k and v
    ])
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
    pg = ctx.new_page()
    hits = []
    pg.on("request", lambda r: hits.append((r.method, r.url))
          if "/anti_fraud/ivs" in r.url else None)
    try:
        pg.goto("https://shopee.co.id/verify/ivs",
                wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        print("goto:", str(e)[:120])
    pg.wait_for_timeout(12000)
    print("URL:", pg.url[:80])
    for m, u in hits:
        print("  HIT", m, u.split("?")[0][-60:])
    br.close()

time.sleep(2)
print("\n=== isi mitm_ivs.jsonl ===")
try:
    for line in open("/root/shopee-verify/mitm_ivs.jsonl"):
        rec = json.loads(line)
        print(rec["tag"], rec["method"], rec["url"].split("?")[0][-60:],
              "status", rec["status"])
        if rec.get("resp_body") and "v_token" in str(rec["resp_body"]):
            print("  RESP:", str(rec["resp_body"])[:500])
        if rec.get("req_body"):
            print("  REQ :", str(rec["req_body"])[:300])
except FileNotFoundError:
    print("(kosong)")
