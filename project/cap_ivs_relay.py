# -*- coding: utf-8 -*-
"""cap_ivs_relay.py — buka /verify/ivs lewat RELAY residensial (:18080)
dan tangkap v_token langsung dari response Playwright.

Tanpa MITM (mitmproxy upstream bermasalah). Playwright sudah bisa
intercept response body — setara MITM untuk kebutuhan ini.
"""
import sys, json, time
sys.path.insert(0, "/root/shopee-verify")
from full_flow import Flow
from playwright.sync_api import sync_playwright

COOKIE = open("/root/shopee-verify/ck_1553.txt").read().strip()
CSRF = "3929567fdad6e3608eb25fd137f69955"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
OUT = "/root/shopee-verify/mitm_ivs.jsonl"

# 1) token segar dari Python
f = Flow(cookie=COOKIE)
f.csrf = CSRF
r1 = f.step1_init()
r4 = f.step4_password("qwertyui123")
print("init:", r1["ok"], "| password:", r4["ok"])
if not (r1["ok"] and r4["ok"]):
    sys.exit("init/password gagal")

captured = []


def on_resp(resp):
    u = resp.url
    if "/anti_fraud/ivs" in u or "/verify/ivs" in u:
        try:
            body = resp.text()[:6000]
        except Exception:
            body = ""
        rec = {"url": u.split("?")[0], "status": resp.status,
               "req": (resp.request.post_data or "")[:3000], "resp": body}
        captured.append(rec)
        with open(OUT, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"  [CAP] {resp.status} {u.split('?')[0][-55:]}")


cookies = []
for part in COOKIE.split(";"):
    k, _, v = part.strip().partition("=")
    if k and v:
        cookies.append({"name": k, "value": v,
                        "domain": ".shopee.co.id", "path": "/"})

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
    pg.on("response", on_resp)
    for target in ("https://shopee.co.id/verify/ivs",
                   "https://shopee.co.id/user/account/profile"):
        print(f"\n>> {target}")
        try:
            pg.goto(target, wait_until="domcontentloaded", timeout=70000)
            pg.wait_for_timeout(9000)
            print("   URL:", pg.url[:75])
            # klik elemen ganti nomor kalau ada
            for txt in ("Ubah", "Ganti", "Nomor HP", "Perbarui"):
                try:
                    el = pg.get_by_text(txt, exact=False).first
                    if el.is_visible(timeout=1200):
                        el.click()
                        print(f"   klik '{txt}'")
                        pg.wait_for_timeout(6000)
                        break
                except Exception:
                    pass
        except Exception as e:
            print("   ERR:", str(e)[:110])

    br.close()

print("\n=== HASIL CAPTURE ===")
for rec in captured:
    print(f"{rec['status']} {rec['url'][-50:]}")
    if "v_token" in rec["resp"]:
        try:
            d = json.loads(rec["resp"])
            for m in (d.get("data") or []):
                print(f"   type={m.get('type')} v_token={str(m.get('v_token'))[:60]}…")
        except Exception:
            print("   RESP:", rec["resp"][:300])
print(f"\ntotal captured: {len(captured)} -> {OUT}")
