# -*- coding: utf-8 -*-
"""ivs_pw2.py — tutup modal bahasa dulu, lalu klik Password & isi.

Output signature langsung dicetak.
"""
import sys, json, ssl, urllib.request, urllib.error, urllib.parse

CK_FILE = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_5th_solved.txt"
PW = sys.argv[2] if len(sys.argv) > 2 else "qwertyui123"
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
         "x-shopee-language": "id", "Referer": ref, "x-csrftoken": CSRF}
    d = None
    if body is not None:
        h["Content-Type"] = "application/json"; d = json.dumps(body).encode()
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
URL = ("https://shopee.co.id/verify/ivs?u_token=" + urllib.parse.quote(ut, safe="")
       + "&event_type=2&is_initial=true&client_id=4&param_type=0"
       + "&trigger_url=" + urllib.parse.quote("https://shopee.co.id/user/account/profile", safe="")
       + "&next=" + urllib.parse.quote("https://shopee.co.id/user/account/profile", safe=""))

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
        (r.request.method, r.url.split("/api/v4")[-1][:48], r.status,
         (r.text()[:350] if "/api/v4" in r.url else "")))
        if "/api/v4" in r.url else None)

    pg.goto(URL, wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(10000)

    # 1) tutup modal bahasa TANPA remove (react crash kalau di-remove)
    closed = False
    for txt in ("Bahasa Indonesia", "English"):
        try:
            loc = pg.get_by_text(txt, exact=True)
            if loc.count() > 0:
                loc.first.click(timeout=5000, force=True)
                print("klik bahasa ->", txt)
                closed = True
                break
        except Exception:
            continue
    pg.wait_for_timeout(3500)
    if not closed:
        pg.keyboard.press("Escape")
        print("Escape untuk tutup modal")
        pg.wait_for_timeout(2500)
    print("modal masih ada:", pg.evaluate("()=>!!document.getElementById('modal')"))
    print("body:", pg.evaluate("()=>document.body.innerText.slice(0,140)").replace("\n", " | ")[:130])

    # 2) klik Password
    try:
        pg.get_by_text("Verifikasi dengan Password", exact=True).last.click(timeout=12000)
        print("klik Password OK")
    except Exception as e:
        print("klik Password err:", str(e)[:80])
        pg.evaluate("""()=>{const all=Array.from(document.querySelectorAll('*'));
          const h=all.filter(e=>(e.innerText||'').trim()==='Verifikasi dengan Password');
          if(h.length){const el=h[h.length-1];
            for(const ev of ['pointerdown','mousedown','pointerup','mouseup','click'])
              try{el.dispatchEvent(new MouseEvent(ev,{bubbles:true,cancelable:true,view:window}));}catch(e){}}}""")
        print("fallback JS click")
    pg.wait_for_timeout(7000)
    print("URL:", pg.url[:70])
    print("body:", pg.evaluate("()=>document.body.innerText.slice(0,160)").replace("\n", " | ")[:150])

    # 3) isi password
    try:
        inp = pg.locator('input[type="password"]').first
        inp.wait_for(state="visible", timeout=15000)
        inp.click(force=True)
        inp.type(PW, delay=70)
        print("value_len:", len(inp.input_value()))
    except Exception as e:
        print("input err:", str(e)[:90])
        # fallback
        pg.evaluate("""(v)=>{const i=document.querySelector('input[type=password]');
          if(!i)return false;
          const s=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
          s.call(i,v); i.dispatchEvent(new Event('input',{bubbles:true}));
          i.dispatchEvent(new Event('change',{bubbles:true})); return true;}""", PW)
        print("fallback JS set value")

    pg.wait_for_timeout(1500)
    # 4) klik KONFIRMASI
    try:
        pg.get_by_text("KONFIRMASI", exact=True).last.click(timeout=10000, force=True)
        print("klik KONFIRMASI OK")
    except Exception as e:
        print("KONFIRMASI err:", str(e)[:70])
        pg.evaluate("""()=>{const all=Array.from(document.querySelectorAll('button,div,span'));
          const h=all.filter(e=>(e.innerText||'').trim().toUpperCase()==='KONFIRMASI');
          if(h.length){const el=h[h.length-1];
            for(const ev of ['pointerdown','mousedown','pointerup','mouseup','click'])
              try{el.dispatchEvent(new MouseEvent(ev,{bubbles:true,cancelable:true,view:window}));}catch(e){}}}""")

    pg.wait_for_timeout(12000)
    print("\nURL akhir:", pg.url[:80])
    print("body:", pg.evaluate("()=>document.body.innerText.slice(0,250)").replace("\n", " | ")[:240])

    # SIMPAN signature + token ke READY_PW.json
    fin = pg.evaluate("""()=>{const o={};for(let i=0;i<sessionStorage.length;i++){
      const k=sessionStorage.key(i);o[k]=sessionStorage.getItem(k);}return o;}""")
    sig = fin.get("@shopee-ivs/signature")
    rc = fin.get("@shopee-verify-password/rc_token")
    vt = fin.get("@shopee-ivs/v_token")
    mt = fin.get("@shopee-ivs/method_type")
    if sig:
        import json as _j
        _j.dump({"signature": sig, "rc_token": rc, "v_token": vt,
                 "type": int(mt or 2), "cp": cp, "ut": ut,
                 "completed": fin.get("@shopee-ivs/verification_completed_success")},
                open("/root/shopee-verify/READY_PW.json", "w"))
        print("\n✅ SIGNATURE TERSIMPAN:", sig[:60])
        print("   completed:", fin.get("@shopee-ivs/verification_completed_success"))

    print("\n=== API ===")
    for m, u, s, b in LOG[-12:]:
        print(f"   {m} {u} -> {s}")
        if b and ("verify" in u or "token" in u or "password" in u or "ivs" in u):
            print(f"      {b[:280]}")

    ss = pg.evaluate("""()=>{const o={};for(let i=0;i<sessionStorage.length;i++){
      const k=sessionStorage.key(i);o[k]=sessionStorage.getItem(k);}return o;}""")
    print("\n=== ivs sessionStorage ===")
    for k, v in ss.items():
        if "ivs" in k.lower() or "verify" in k.lower():
            print(f"   {k} = {str(v)[:85]}")
    pg.screenshot(path="/root/shopee-verify/pw_after.png")
    br.close()
