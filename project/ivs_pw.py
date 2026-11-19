# -*- coding: utf-8 -*-
"""ivs_pw.py — akun punya password: jalankan IVS di halaman, isi password,
tangkap signature, lalu lanjut pasang nomor.
"""
import sys, json, time, ssl, urllib.request, urllib.error, urllib.parse

CK_FILE = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_5th_solved.txt"
PW = sys.argv[2] if len(sys.argv) > 2 else "qwertyui123"
NEWPHONE = sys.argv[3] if len(sys.argv) > 3 else "6285736070693"

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
print("init:", r1.get("error"), "cp:", bool(cp), "ut:", bool(ut))

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
        (r.request.method, r.url.split("/api/v4")[-1][:50], r.status,
         (r.text()[:280] if "/api/v4" in r.url else "")))
        if "/api/v4" in r.url else None)

    print("\n>> buka IVS")
    pg.goto(IVS_URL, wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(11000)
    print("   URL:", pg.url[:75])
    print("   body:", pg.evaluate("()=>document.body.innerText.slice(0,200)").replace("\n", " | ")[:190])

    # klik method Password / ShopeePay
    for label in ("verifikasi dengan password", "password", "verifikasi dengan pin",
                  "shopeepay", "kata sandi"):
        try:
            r = pg.evaluate("""(txt)=>{
              const all=Array.from(document.querySelectorAll('*'));
              const h=all.filter(e=>{const t=(e.innerText||'').trim();
                return t && t.length<70 && t.toLowerCase().includes(txt);});
              if(!h.length) return null;
              const el=h[h.length-1];
              for(const ev of ['pointerdown','mousedown','pointerup','mouseup','click'])
                try{el.dispatchEvent(new MouseEvent(ev,{bubbles:true,cancelable:true,view:window}));}catch(e){}
              try{el.click();}catch(e){}
              return {tag:el.tagName, txt:(el.innerText||'').trim().slice(0,40)};
            }""", label.lower())
            if r:
                print(f"   klik '{label}': {r}")
                break
        except Exception:
            pass

    pg.wait_for_timeout(6000)
    print("   URL:", pg.url[:75])
    print("   body:", pg.evaluate("()=>document.body.innerText.slice(0,250)").replace("\n", " | ")[:240])

    # isi password lalu klik KONFIRMASI
    try:
        print("   >> isi via locator input[type=password]")
        el = pg.locator('input[type="password"]').first
        el.wait_for(state="visible", timeout=15000)
        el.click()
        el.fill("")
        el.press_sequentially(PW, delay=80)
        val = el.input_value()
        print(f"   value_len={len(val)} match={val == PW}")
        pg.wait_for_timeout(1500)

        btns = pg.evaluate("""()=>Array.from(document.querySelectorAll(
          'button,[role=button],div,span'))
          .filter(e=>{const t=(e.innerText||'').trim();
            return t && t.length<30 && e.offsetParent!==null &&
              /konfirmasi|confirm|lanjut|submit/i.test(t);})
          .map(e=>({tag:e.tagName, t:(e.innerText||'').trim()}))""")
        print("   kandidat tombol:", btns[:6])

        # klik via locator (real mouse)
        clicked = False
        for txt in ("KONFIRMASI", "Konfirmasi", "LANJUTKAN"):
            loc = pg.get_by_text(txt, exact=True)
            if loc.count() > 0:
                try:
                    loc.last.click(timeout=6000)
                    print("   klik locator:", txt)
                    clicked = True
                    break
                except Exception as e:
                    print("   locator err:", str(e)[:50])
        if not clicked:
            print("   >> fallback Enter")
            el.press("Enter")
    except Exception as e:
        print("   input/confirm err:", str(e)[:90])

    pg.wait_for_timeout(9000)
    print("   URL:", pg.url[:75])
    print("   body:", pg.evaluate("()=>document.body.innerText.slice(0,280)").replace("\n", " | ")[:270])

    print("\n=== API ===")
    for m, u, s, b in LOG[-10:]:
        print(f"   {m} {u} -> {s}")
        if b:
            print(f"      {b[:230]}")

    ss = pg.evaluate("""()=>{const o={};for(let i=0;i<sessionStorage.length;i++){
      const k=sessionStorage.key(i);o[k]=sessionStorage.getItem(k);}return o;}""")
    print("\n=== sessionStorage ===")
    for k, v in ss.items():
        if "ivs" in k.lower() or "verify" in k.lower():
            print(f"   {k} = {str(v)[:80]}")

    pg.screenshot(path="/root/shopee-verify/ivs_pw.png")
    br.close()
