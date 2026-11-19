# -*- coding: utf-8 -*-
"""gate_solver.py — buka shopee pakai cookie, KALAU redirect ke
/verify/captcha ATAU /verify/traffic -> SOLVE pakai SadCaptcha.

Loop: solve -> cek URL -> ulang sampai beranda. Simpan cookie hasil.
"""
import sys, json, time, re
sys.path.insert(0, "/root/shopee-farm")
from playwright.sync_api import sync_playwright
import shopee_v6 as V6

CK_FILE = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_1445.txt"
MAXTRY = int(sys.argv[2]) if len(sys.argv) > 2 else 6
OUT = CK_FILE.replace(".txt", "_solved.txt")

CK = open(CK_FILE).read().strip()
CK_RAW = CK
KEY = open("/root/shopee-farm/bot_key.txt").read().strip()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"


def cookies_from(ck):
    try: return json.loads(ck)
    except Exception:
        return [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
                for k, _, v in (p.strip().partition("=") for p in ck.split(";"))
                if k and v]


def dump(ck_list):
    return "; ".join(f"{c['name']}={c['value']}" for c in ck_list)


ck_list = cookies_from(CK_RAW)
print(f"cookie: {len(ck_list)} | max try: {MAXTRY}")

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=False, args=[
        "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--use-gl=swiftshader", "--window-size=1366,768",
        "--lang=id-ID"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 768},
                         timezone_id="Asia/Jakarta",
                         proxy={"server": PROXY})
    ctx.add_cookies(ck_list)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};"
        "Object.defineProperty(navigator,'languages',{get:()=>['id-ID','id','en']});"
        "Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});")
    pg = ctx.new_page()

    ok = False
    for attempt in range(1, MAXTRY + 1):
        print(f"\n===== ATTEMPT {attempt} =====")
        try:
            pg.goto("https://shopee.co.id/", wait_until="domcontentloaded",
                    timeout=90000)
        except Exception as e:
            print("  goto err:", str(e)[:70])
        pg.wait_for_timeout(7000)
        url = pg.url
        print("  URL:", url[:95])

        # sudah bersih?
        if "/verify/" not in url:
            st = pg.evaluate("()=>document.body.innerText.slice(0,120)")
            print("  body:", st.replace("\n", " | ")[:110])
            print("  >> TIDAK ADA GATE")
            ok = True
            break

        # state captcha
        stt = V6.state(pg)
        print("  state:", stt)
        if stt in ("ERROR", "?"):
            # halaman gagal / kosong -> cek elemen
            has = pg.evaluate(V6.JS_PRESENT, [V6.IC_PUZZLE, V6.IC_BUTTON,
                                              V6.ID_PUZZLE, V6.ID_PIECE,
                                              "#NEW_CAPTCHA", "aside"])
            print("  elemen ditemukan:", has)
            if not has:
                print("  >> tidak ada elemen captcha, reload")
                pg.reload(wait_until="domcontentloaded")
                pg.wait_for_timeout(6000)
                continue

        # coba solver berurutan
        for name, fn in (("image_crawl", V6.solve_image_crawl),
                         ("puzzle_slide", V6.solve_puzzle_slide),
                         ("image_drag", V6.solve_image_drag)):
            try:
                print(f"  coba {name}…")
                r = fn(pg, KEY)
                print(f"    -> {r}")
            except Exception as e:
                print(f"    -> EXC {str(e)[:90]}")
                continue
            pg.wait_for_timeout(6000)
            u2 = pg.url
            print("    URL:", u2[:95])
            if "/verify/" not in u2:
                ok = True
                break
            # captcha baru muncul lagi? ulangi solve
            if V6.state(pg) in ("CAPTCHA", "OTP_MODAL"):
                continue
        if ok:
            break
        pg.wait_for_timeout(2000)

    print("\n===== HASIL =====")
    print("URL akhir:", pg.url[:110])
    if ok:
        new_ck = ctx.cookies()
        open(OUT, "w").write(dump(new_ck))
        print(f">> LOLOS. {len(new_ck)} cookie -> {OUT}")
        print("   names:", [c["name"] for c in new_ck])
        r = pg.evaluate("""async()=>{const r=await fetch(
          '/api/v4/account/basic/get_account_info',{credentials:'include',
          headers:{'x-api-source':'pc','x-requested-with':'XMLHttpRequest'}});
          return await r.json();}""")
        print("   account:", json.dumps(r, ensure_ascii=False)[:250])
    else:
        pg.screenshot(path="/root/shopee-verify/gate_fail.png")
        print(">> GAGAL lolos", MAXTRY, "percobaan")
    br.close()
