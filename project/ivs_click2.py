# -*- coding: utf-8 -*-
"""ivs_click2.py — klik elemen 'Verifikasi dengan link email' via JS,
lalu tangkap r_token/signature + lanjut pasang nomor.
"""
import sys, json, time, ssl, urllib.request, urllib.error, urllib.parse

CK_FILE = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_1445_solved.txt"
NEWPHONE = sys.argv[2] if len(sys.argv) > 2 else "6285736070693"
CK = open(CK_FILE).read().strip()
CSRF = next((c.split("=", 1)[1] for c in CK.split(";")
             if c.strip().startswith("csrftoken=")), "")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"

_ct = ssl.create_default_context(); _ct.check_hostname = False
_ct.verify_mode = ssl.CERT_NONE
_OP = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}),
    urllib.request.HTTPSHandler(context=_ct))


def api(path, body=None, method="POST",
        ref="https://shopee.co.id/user/account/profile"):
    h = {"User-Agent": UA, "Cookie": CK, "Accept": "application/json",
         "x-api-source": "pc", "x-requested-with": "XMLHttpRequest",
         "x-shopee-language": "id", "Referer": ref, "x-csrftoken": CSRF,
         "Origin": "https://shopee.co.id", "x-app-type": "undefined"}
    d = None
    if body is not None:
        h["Content-Type"] = "application/json"
        d = json.dumps(body).encode()
    r = urllib.request.Request("https://shopee.co.id" + path, data=d,
                               method=method, headers=h)
    try:
        with _OP.open(r, timeout=35) as x: return json.loads(x.read())
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read())
        except Exception: return {"http": e.code}
    except Exception as e: return {"err": str(e)[:80]}


r1 = api("/api/v4/account/management/change_phone_init_v2", {})
d1 = r1.get("data") or {}
cp, ut = d1.get("change_phone_token"), d1.get("ivs_utoken")
print("init:", r1.get("error"), "cp:", bool(cp))

from playwright.sync_api import sync_playwright

cookies = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
           for k, _, v in (p.strip().partition("=") for p in CK.split(";"))
           if k and v]

IVS_URL = ("https://shopee.co.id/verify/ivs"
           + "?u_token=" + urllib.parse.quote(ut, safe="")
           + "&event_type=2&is_initial=true"
           + "&trigger_url=" + urllib.parse.quote("https://shopee.co.id/user/account/profile", safe="")
           + "&next=" + urllib.parse.quote("https://shopee.co.id/user/account/profile", safe="")
           + "&client_id=4&param_type=0")

LOG = []
with sync_playwright() as pw:
    br = pw.chromium.launch(headless=False, args=[
        "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--use-gl=swiftshader", "--window-size=1366,768"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 768},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    ctx.add_cookies(cookies)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};")
    pg = ctx.new_page()
    pg.on("response", lambda r: LOG.append(
        (r.request.method, r.url.split("/api/v4")[-1][:55], r.status,
         (r.text()[:400] if ("anti_fraud" in r.url or "management" in r.url) else "")))
        if "/api/v4" in r.url else None)

    print("\n>> buka IVS")
    pg.goto(IVS_URL, wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(11000)
    print("   body:", pg.evaluate("()=>document.body.innerText.slice(0,110)").replace("\n", " | ")[:100])

    print("\n>> klik elemen bertekst 'link email' via JS")
    res = pg.evaluate("""() => {
      const all = Array.from(document.querySelectorAll('*'));
      const hits = all.filter(e =>
        (e.innerText||'').trim().toLowerCase() === 'verifikasi dengan link email'
        || ((e.innerText||'').trim().toLowerCase().includes('link email')
            && (e.innerText||'').length < 60));
      if (!hits.length) return {found:0};
      const el = hits[hits.length-1];
      const out = {found:hits.length, tag:el.tagName, cls:(el.className||'').toString().slice(0,60)};
      el.scrollIntoView({block:'center'});
      // dispatch pointer + click + mouse
      for (const t of ['pointerdown','mousedown','pointerup','mouseup','click']) {
        try { el.dispatchEvent(new MouseEvent(t, {bubbles:true, cancelable:true, view:window})); } catch(e){}
      }
      try { el.click(); } catch(e){}
      out.clicked = true;
      return out;
    }""")
    print("   ->", res)

    pg.wait_for_timeout(9000)
    print("   URL:", pg.url[:80])
    print("   body:", pg.evaluate("()=>document.body.innerText.slice(0,260)").replace("\n", " | ")[:250])

    ss = pg.evaluate("""()=>{const o={};for(let i=0;i<sessionStorage.length;i++){
      const k=sessionStorage.key(i);o[k]=sessionStorage.getItem(k);}return o;}""")
    print("\n=== sessionStorage ===")
    for k, v in ss.items():
        print(f"   {k} = {str(v)[:85]}")

    print("\n=== request terakhir ===")
    for m, u, s, b in LOG[-8:]:
        print(f"   {m} {u} -> {s}")
        if b:
            print(f"      {b[:250]}")

    pg.screenshot(path="/root/shopee-verify/ivs_clicked.png")
    br.close()
