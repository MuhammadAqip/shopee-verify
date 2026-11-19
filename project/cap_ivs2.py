# -*- coding: utf-8 -*-
"""cap_ivs2.py — telusuri halaman /verify/ivs: baca state, cari tombol,
panggil ivs/methods dari konteks halaman (page.evaluate fetch)."""
import sys, json
sys.path.insert(0, "/root/shopee-verify")
from full_flow import Flow
from playwright.sync_api import sync_playwright

COOKIE = open("/root/shopee-verify/ck_1553.txt").read().strip()
CSRF = "3929567fdad6e3608eb25fd137f69955"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

f = Flow(cookie=COOKIE)
f.csrf = CSRF
r1 = f.step1_init()
r4 = f.step4_password("qwertyui123")
print("init:", r1["ok"], "password:", r4["ok"])
u_token, r_token, cp_token = f.u_token, f.r_token, f.cp_token
json.dump({"u_token": u_token, "r_token": r_token, "cp_token": cp_token},
          open("/root/shopee-verify/ivs_tokens_1553.json", "w"))

cookies = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
           for k, _, v in (p.strip().partition("=") for p in COOKIE.split(";"))
           if k and v]

JS_CALL = """async (args) => {
  const csrf = (document.cookie.match(/(?:^|;\\s*)csrftoken=([^;]+)/) || [])[1] || '';
  const out = {};
  const post = async (path, body) => {
    const r = await fetch(path, {method:'POST', credentials:'include',
      headers:{'Content-Type':'application/json','Accept':'application/json',
        'x-api-source':'pc','x-requested-with':'XMLHttpRequest',
        'x-csrftoken':csrf,'x-shopee-language':'id'},
      body: JSON.stringify(body)});
    let t = await r.text();
    try { return JSON.parse(t); } catch(e) { return {raw:t.slice(0,300)}; }
  };
  out.methods = await post('/api/v4/anti_fraud/ivs/methods',
                           {u_token: args.u_token});
  return out;
}"""

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1420, "height": 900},
                         timezone_id="Asia/Jakarta", ignore_https_errors=True,
                         proxy={"server": "http://127.0.0.1:18080"})
    ctx.add_cookies(cookies)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
    pg = ctx.new_page()
    pg.goto("https://shopee.co.id/verify/ivs",
            wait_until="domcontentloaded", timeout=70000)
    pg.wait_for_timeout(9000)
    print("URL:", pg.url[:70])
    print("TEXT:", repr(pg.inner_text("body")[:250]))
    print("\n=== panggil ivs/methods dari konteks halaman ===")
    r = pg.evaluate(JS_CALL, {"u_token": u_token})
    print(json.dumps(r, ensure_ascii=False)[:700])

    print("\n=== coba juga token verify dari konteks halaman ===")
    JS_VERIFY = """async (a) => {
      const csrf = (document.cookie.match(/(?:^|;\\s*)csrftoken=([^;]+)/) || [])[1] || '';
      const r = await fetch('/api/v4/anti_fraud/ivs/token/verify', {
        method:'POST', credentials:'include',
        headers:{'Content-Type':'application/json','Accept':'application/json',
          'x-api-source':'pc','x-requested-with':'XMLHttpRequest',
          'x-csrftoken':csrf,'x-shopee-language':'id'},
        body: JSON.stringify(a)});
      return await r.text();
    }"""
    body = {"method_name": 2, "event": 2, "u_token": u_token,
            "r_token": r_token, "misc": {"operation": 0}}
    out = pg.evaluate(JS_VERIFY, body)
    print(str(out)[:500])
    br.close()
