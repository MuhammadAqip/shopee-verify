# -*- coding: utf-8 -*-
"""get_vtoken.py — suntik cookie akun, jalanin UI ganti nomor sendiri,
klik sampai ivs/methods ke-trigger, tangkap v_token.

Bukan API murni. Ini browser asli via relay residensial ID.
"""
import sys, json, time
sys.path.insert(0, "/root/shopee-verify")
from playwright.sync_api import sync_playwright

COOKIE_FILE = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_1553.txt"
CSRF = sys.argv[2] if len(sys.argv) > 2 else "3929567fdad6e3608eb25fd137f69955"
OUT = "/root/shopee-verify/vtoken.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

COOKIE = open(COOKIE_FILE).read().strip()
cookies = []
for part in COOKIE.split(";"):
    k, _, v = part.strip().partition("=")
    if k and v and k not in ("", "csrftoken"):
        cookies.append({"name": k, "value": v,
                        "domain": ".shopee.co.id", "path": "/"})
cookies.append({"name": "csrftoken", "value": CSRF,
                "domain": ".shopee.co.id", "path": "/"})

cap = {"v_token": None, "methods_raw": None, "uid": None}


def on_resp(resp):
    u = resp.url
    if "ivs/methods" in u:
        try:
            b = resp.text()
        except Exception:
            return
        cap["methods_raw"] = b
        try:
            d = json.loads(b)
            if d.get("error") == 0 and d.get("data"):
                cap["v_token"] = d["data"]
                print(f"  ✅ v_token DAPAT: {len(d['data'])} metode")
                for m in d["data"]:
                    print(f"     type={m.get('type')} vtok={str(m.get('v_token'))[:45]}…")
        except Exception:
            pass


with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--disable-web-security"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1420, "height": 950},
                         timezone_id="Asia/Jakarta", ignore_https_errors=True,
                         proxy={"server": "http://127.0.0.1:18080"})
    ctx.add_cookies(cookies)
    ctx.add_init_script("""
        Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
        Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
        Object.defineProperty(navigator,'languages',{get:()=>['id-ID','id','en-US','en']});
        window.chrome = {runtime:{}};
    """)
    pg = ctx.new_page()
    pg.on("response", on_resp)

    print(">> buka homepage (set sesi)")
    pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=70000)
    pg.wait_for_timeout(7000)
    print("   URL:", pg.url[:60])

    # verifikasi login
    me = pg.evaluate("""async()=>{const r=await fetch('/api/v4/account/basic/get_account_info',
        {credentials:'include',headers:{'x-api-source':'pc','x-requested-with':'XMLHttpRequest'}});
        return await r.text();}""")
    print("   account:", me[:150])
    try:
        d = json.loads(me)
        if d.get("error") == 0:
            cap["uid"] = (d.get("data") or {}).get("userid")
            print("   LOGIN OK userid:", cap["uid"])
        else:
            print("   LOGIN GAGAL error:", d.get("error"))
            print("   >> cookie expired, gue stop")
            br.close(); sys.exit(1)
    except Exception:
        pass

    print("\n>> buka /verify/ivs (halaman IVS langsung)")
    pg.goto("https://shopee.co.id/verify/ivs", wait_until="domcontentloaded",
            timeout=70000)
    pg.wait_for_timeout(8000)
    print("   URL:", pg.url[:70])
    print("   TEXT:", repr(pg.inner_text("body")[:180]))

    # klik semua kandidat tombol
    for sel in ("text=Coba lagi", "text=Coba Lagi", "text=Ulangi",
                "button:has-text('Lanjut')", "button:has-text('Verifikasi')"):
        try:
            el = pg.locator(sel).first
            if el.is_visible(timeout=1500):
                el.click()
                print(f"   klik: {sel}")
                pg.wait_for_timeout(5000)
        except Exception:
            pass

    if not cap["v_token"]:
        print("\n>> coba lewat halaman profil + klik Ubah Nomor")
        pg.goto("https://shopee.co.id/user/account/profile",
                wait_until="domcontentloaded", timeout=70000)
        pg.wait_for_timeout(9000)
        print("   URL:", pg.url[:70])
        txt = pg.inner_text("body")[:200]
        print("   TEXT:", repr(txt))
        # kalau kena captcha halaman, jangan menyerah — coba endpoint ivs langsung
        # dari konteks halaman profil (origin sama)
        if "/verify/captcha" in pg.url:
            print("   (captcha halaman — tetap coba fetch ivs dari origin)")

    if not cap["v_token"]:
        print("\n>> panggil ivs/methods dari ORIGIN SHOPEE (page.evaluate)")
        res = pg.evaluate("""async()=>{
          const csrf=(document.cookie.match(/(?:^|;\\s*)csrftoken=([^;]+)/)||[])[1]||'';
          const out={};
          // ambil u_token via init_v2 dari origin
          const p=await fetch('/api/v4/account/management/change_phone_init_v2',
            {method:'POST',credentials:'include',headers:{'Content-Type':'application/json',
             'x-api-source':'pc','x-requested-with':'XMLHttpRequest','x-csrftoken':csrf},
             body:'{}'});
          out.init=await p.text();
          let u='';
          try{ u=JSON.parse(out.init).data.ivs_utoken||''; }catch(e){}
          const m=await fetch('/api/v4/anti_fraud/ivs/methods',
            {method:'POST',credentials:'include',headers:{'Content-Type':'application/json',
             'x-api-source':'pc','x-requested-with':'XMLHttpRequest','x-csrftoken':csrf},
             body:JSON.stringify({u_token:u})});
          out.methods=await m.text();
          return out;
        }""")
        print("   init:", str(res.get("init"))[:120])
        print("   methods:", str(res.get("methods"))[:400])
        try:
            d = json.loads(res.get("methods"))
            if d.get("error") == 0 and d.get("data"):
                cap["v_token"] = d["data"]
                cap["methods_raw"] = res["methods"]
        except Exception:
            pass

    br.close()

if cap["v_token"]:
    json.dump(cap, open(OUT, "w"), ensure_ascii=False, indent=1)
    print(f"\n✅ DISIMPAN ke {OUT}")
    for m in cap["v_token"]:
        print(f"   type={m['type']} v_token_len={len(str(m.get('v_token')))}")
else:
    print("\n❌ v_token belum dapat.")
    if cap.get("methods_raw"):
        print("   raw:", cap["methods_raw"][:250])
