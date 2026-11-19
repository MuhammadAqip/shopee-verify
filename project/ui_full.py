# -*- coding: utf-8 -*-
"""ui_full.py — jalankan SELURUH flow change-phone di UI Shopee asli.
MITM capture semua request. Tujuannya: tahu endpoint + body persis
yang dipakai saat OTP dikirim via WhatsApp.

Tidak ada panggilan API manual. Semua lewat UI.
"""
import sys, json, ssl, urllib.request, urllib.error, urllib.parse, time

CK_FILE = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_5th_solved.txt"
PW = sys.argv[2] if len(sys.argv) > 2 else "qwertyui123"
NEWPHONE = sys.argv[3] if len(sys.argv) > 3 else "83191106499"  # tanpa 62

CK = open(CK_FILE).read().strip()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"

cookies = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
           for k, _, v in (p.strip().partition("=") for p in CK.split(";"))
           if k and v]

CAP = []
CAPR = []


def on_req(req):
    if "/api/v4" in req.url:
        try: b = req.post_data or ""
        except Exception: b = ""
        CAP.append({"m": req.method, "u": req.url.split("shopee.co.id")[-1],
                    "b": b[:1200]})


def on_resp(resp):
    if "/api/v4" in resp.url:
        try: t = resp.text()
        except Exception: t = ""
        CAPR.append({"u": resp.url.split("shopee.co.id")[-1],
                     "s": resp.status, "t": t[:600]})


from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=False, args=[
        "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--use-gl=swiftshader", "--window-size=1366,900"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 900},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    ctx.add_cookies(cookies)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};")
    pg = ctx.new_page()
    pg.on("request", on_req)
    pg.on("response", on_resp)

    def dump(tag, n=99):
        print(f"\n--- CAPTURE {tag} ({len(CAP)} req) ---")
        for c in CAP[-n:]:
            if "login" in c["u"] or "static" in c["u"] or "assets" in c["u"]:
                continue
            print(f"  {c['m']} {c['u'][:75]}")
            if c["b"]:
                print(f"     >> {c['b'][:260]}")

    print("=== 1. buka halaman keamanan ===")
    pg.goto("https://shopee.co.id/user/account/security",
            wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(8000)
    print("   url:", pg.url[:90])
    print("   body:", pg.evaluate("()=>document.body.innerText.slice(0,350)").replace("\n", " | ")[:300])
    dump("security", 15)

    # klik menu nomor telepon / ganti nomor
    print("\n=== 2. cari menu nomor ===")
    found = pg.evaluate("""()=>{
      const all=Array.from(document.querySelectorAll('*'));
      const hits=[];
      for(const e of all){
        const t=(e.innerText||'').trim();
        if(!t||t.length>45) continue;
        if(/nomor|telepon|phone|hp|ubah|ganti/i.test(t) && e.offsetParent!==null)
          hits.push({tag:e.tagName, t:t.slice(0,40)});
      }
      return hits.slice(0,15);
    }""")
    print("   kandidat:", json.dumps(found, ensure_ascii=False)[:500])

    # klik kandidat pertama yang mengandung nomor/telepon
    for kw in ("Nomor Telepon", "nomor telepon", "Nomor HP", "Ubah", "Ganti"):
        try:
            loc = pg.get_by_text(kw)
            if loc.count() > 0:
                loc.first.click(timeout=6000)
                print(f"   klik '{kw}'")
                pg.wait_for_timeout(6000)
                print("   url:", pg.url[:90])
                break
        except Exception as e:
            continue

    print("   body skrg:", pg.evaluate("()=>document.body.innerText.slice(0,400)").replace("\n", " | ")[:350])
    dump("after-click", 15)

    pg.screenshot(path="/root/shopee-verify/ui_security.png", full_page=True)
    br.close()

print("\n\n========== RINGKASAN ENDPOINT ==========")
seen = set()
for c in CAP:
    k = c["m"] + " " + c["u"].split("?")[0]
    if k in seen: continue
    seen.add(k)
    if any(x in c["u"] for x in ("login", "static", "assets", "live")):
        continue
    print(f"\n{k}")
    if c["b"]:
        print(f"  BODY: {c['b'][:400]}")
    for r in CAPR:
        if r["u"].split("?")[0] == c["u"].split("?")[0]:
            print(f"  RESP[{r['s']}]: {r['t'][:250]}")
            break
