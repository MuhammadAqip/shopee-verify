# -*- coding: utf-8 -*-
"""auto_login.py — login OTOMATIS tanpa VNC.

Strategi:
 1. Fresh browser, no cookie
 2. Isi nomor -> LOG IN
 3. Deteksi: password form / captcha / OTP
 4. Password: auto isi
 5. Captcha: auto solve via SadCaptcha
 6. OTP: tulis ke OTP_NEEDED.txt, tunggu Maker isi OTP_CODE.txt
 7. Setelah login: cek 90309999
"""
import sys, json, time, os, hashlib

PHONE = sys.argv[1] if len(sys.argv) > 1 else "6285736070693"
PASSW = sys.argv[2] if len(sys.argv) > 2 else "qwertyui123"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"

OTP_NEEDED = "/root/shopee-verify/OTP_NEEDED.txt"
OTP_CODE = "/root/shopee-verify/OTP_CODE.txt"
STATE = "/root/shopee-verify/AUTO_LOGIN_STATE.json"

for f in (OTP_NEEDED, OTP_CODE):
    if os.path.exists(f):
        os.remove(f)


def st(stage, **kw):
    json.dump({"stage": stage, **kw}, open(STATE, "w"))
    print(f"  [STATE] {stage} {kw}", flush=True)


sys.path.insert(0, "/root/shopee-farm")
SOLVER = None
try:
    import shopee_v6 as V6
    if hasattr(V6, "solve_image_crawl"):
        SOLVER = V6
        print("  solver: OK", flush=True)
except Exception as e:
    print("  solver err:", str(e)[:60], flush=True)

from playwright.sync_api import sync_playwright

GATE = []

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,900"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 900},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    pg = ctx.new_page()

    def on_resp(r):
        if "/api/v4" in r.url:
            try: t = r.text()
            except Exception: return
            if "90309999" in t:
                GATE.append(time.strftime("%H:%M:%S"))

    pg.on("response", on_resp)

    print("=== 1. buka login ===", flush=True)
    pg.goto("https://shopee.co.id/buyer/login", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(7000)
    st("login_page", url=pg.url[:70])

    # ---------------------------------------------------------------
    def visible_inputs():
        return pg.evaluate("""()=>Array.from(document.querySelectorAll('input')).map((e,i)=>{
          const r=e.getBoundingClientRect();
          return {i, type:e.type, ph:(e.placeholder||'').slice(0,50),
                  name:(e.name||'').slice(0,30),
                  vis: r.width>0&&r.height>0&&e.offsetParent!==null};
        }).filter(x=>x.vis)""")

    def shoot(name):
        try: pg.screenshot(path=f"/root/shopee-verify/{name}.png", full_page=False)
        except Exception: pass

    def click_text(txt):
        try:
            loc = pg.get_by_text(txt, exact=True)
            if loc.count() > 0:
                loc.last.click(timeout=6000, force=True)
                return True
        except Exception:
            pass
        try:
            pg.evaluate("""(t)=>{
              const all=Array.from(document.querySelectorAll('button,div[role=button],span,a'));
              const h=all.filter(e=>(e.innerText||'').trim()===t);
              if(h.length){const el=h[h.length-1];
                for(const ev of ['pointerdown','mousedown','pointerup','mouseup','click'])
                  try{el.dispatchEvent(new MouseEvent(ev,{bubbles:true,cancelable:true,view:window}));}catch(e){}
                try{el.click();}catch(e){}
              }}""", txt)
            return True
        except Exception:
            return False

    def body_text():
        try: return pg.evaluate("()=>document.body.innerText.slice(0,600)")
        except Exception: return ""

    # ---------------------------------------------------------------
    print("=== 2. isi nomor ===", flush=True)
    # tunggu form render
    ok = False
    for try_i in range(12):
        try:
            pg.wait_for_selector('input[name="loginKey"]', state="visible", timeout=8000)
            ok = True
            break
        except Exception:
            pg.wait_for_timeout(2500)
            if try_i % 3 == 0:
                print(f"  tunggu form... {try_i*2.5:.0f}s", flush=True)
                print(f"    inputs: {visible_inputs()}", flush=True)
    if not ok:
        print("  form tidak muncul, reload", flush=True)
        pg.reload(wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(8000)
        try:
            pg.wait_for_selector('input[name="loginKey"]', state="visible", timeout=15000)
            ok = True
        except Exception:
            pass

    print("  inputs:", visible_inputs(), flush=True)
    ok2 = False
    for sel in ('input[name="loginKey"]', 'input[type="text"]',
                'input[type="tel"]', 'input'):
        try:
            el = pg.locator(sel).first
            if el.count() > 0 and el.is_visible():
                el.click(force=True)
                el.fill("")
                el.type(PHONE, delay=50)
                print(f"  isi ke {sel} -> {len(el.input_value())} char", flush=True)
                ok2 = True
                break
        except Exception as e:
            continue

    if not ok2:
        print("  GAGAL isi nomor", flush=True)
        shoot("login_fail")
        print("  body:", body_text().replace("\n", " | ")[:300], flush=True)
        br.close()
        sys.exit(1)

    pg.wait_for_timeout(1500)
    st("phone_filled")
    print("=== 3. klik LOG IN ===", flush=True)
    clicked = False
    for t in ("LOG IN", "Log In", "Login", "Lanjut", "Selanjutnya", "Next"):
        if click_text(t):
            print(f"  klik '{t}'", flush=True)
            clicked = True
            break
    pg.wait_for_timeout(7000)
    print("  url:", pg.url[:80], flush=True)
    print("  body:", body_text().replace("\n", " | ")[:280], flush=True)
    shoot("after_phone")

    # ---------------------------------------------------------------
    # deteksi captcha
    cap = pg.evaluate("""()=>({
      canvas: document.querySelectorAll('canvas').length,
      drag: document.querySelectorAll('canvas[draggable]').length,
      nc: !!document.getElementById('NEW_CAPTCHA'),
      url: location.href
    })""")
    print("  captcha state:", cap, flush=True)

    if cap["canvas"] > 0 or "captcha" in cap["url"]:
        st("captcha")
        print("=== 4. SOLVE CAPTCHA ===", flush=True)
        if SOLVER:
            for fn in ("solve_image_crawl", "solve_puzzle", "solve_image_drag"):
                if hasattr(SOLVER, fn):
                    try:
                        res = getattr(SOLVER, fn)(pg)
                        print(f"  {fn}: {str(res)[:150]}", flush=True)
                        if res and (isinstance(res, dict) and res.get("err") is None):
                            break
                    except Exception as e:
                        print(f"  {fn} err: {str(e)[:80]}", flush=True)
            pg.wait_for_timeout(8000)
            print("  url:", pg.url[:80], flush=True)
            print("  body:", body_text().replace("\n", " | ")[:250], flush=True)
            shoot("after_captcha")

    # ---------------------------------------------------------------
    print("=== 5. cari form password ===", flush=True)
    pw_in = pg.locator('input[type="password"]')
    if pw_in.count() > 0:
        st("password_form")
        try:
            el = pw_in.first
            el.wait_for(state="visible", timeout=15000)
            el.click(force=True)
            el.type(PASSW, delay=55)
            print(f"  password terisi: {len(el.input_value())} char", flush=True)
            pg.wait_for_timeout(1200)
            for t in ("LOG IN", "Log In", "Login", "Masuk", "KONFIRMASI"):
                if click_text(t):
                    print(f"  klik '{t}'", flush=True)
                    break
            pg.wait_for_timeout(10000)
        except Exception as e:
            print("  password err:", str(e)[:80], flush=True)
    else:
        print("  tidak ada form password", flush=True)

    print("  url:", pg.url[:90], flush=True)
    print("  body:", body_text().replace("\n", " | ")[:300], flush=True)
    shoot("after_password")

    # ---------------------------------------------------------------
    # captcha lagi?
    cap2 = pg.evaluate("""()=>({c:document.querySelectorAll('canvas').length,
                               u:location.href})""")
    if cap2["c"] > 0 or "captcha" in cap2["u"]:
        print("=== 6. captcha lagi — solve ===", flush=True)
        st("captcha2")
        if SOLVER and hasattr(SOLVER, "solve_image_crawl"):
            try:
                print("  res:", str(SOLVER.solve_image_crawl(pg))[:150], flush=True)
            except Exception as e:
                print("  err:", str(e)[:80], flush=True)
        pg.wait_for_timeout(8000)
        shoot("after_captcha2")

    # ---------------------------------------------------------------
    # OTP?
    txt = body_text()
    need_otp = any(k in txt.lower() for k in
                   ("verifikasi", "kode", "otp", "sms", "whatsapp", "kirim"))
    cks = {c["name"]: c["value"] for c in ctx.cookies()}
    has_st = bool(cks.get("SPC_ST"))
    print(f"\n  SPC_ST: {'ADA' if has_st else 'belum'}", flush=True)
    print(f"  body OTP hint: {need_otp}", flush=True)

    if not has_st and need_otp:
        st("otp_needed")
        open(OTP_NEEDED, "w").write(
            f"OTP diperlukan\nurl: {pg.url}\nwaktu: {time.strftime('%H:%M:%S')}\n")
        print("\n>>> TULIS KODE OTP KE OTP_CODE.txt <<<", flush=True)
        for i in range(120):  # 10 menit
            pg.wait_for_timeout(5000)
            if os.path.exists(OTP_CODE):
                code = open(OTP_CODE).read().strip()
                if code and len(code) >= 4:
                    print(f">>> OTP diterima: {code}", flush=True)
                    break
            if i % 6 == 0:
                print(f"  menunggu OTP... {i*5}s", flush=True)

        if os.path.exists(OTP_CODE):
            code = open(OTP_CODE).read().strip()
            for sel in ('input[type="tel"]', 'input[type="text"]', 'input'):
                try:
                    el = pg.locator(sel).first
                    if el.count() > 0 and el.is_visible():
                        el.click(force=True)
                        el.type(code, delay=90)
                        print(f"  OTP diisi ke {sel}", flush=True)
                        break
                except Exception:
                    continue
            pg.wait_for_timeout(2000)
            for t in ("LOG IN", "Konfirmasi", "Verifikasi", "Lanjut", "Submit"):
                if click_text(t):
                    print(f"  klik '{t}'", flush=True)
                    break
            pg.wait_for_timeout(10000)

    # ---------------------------------------------------------------
    print("\n=== 7. status akhir ===", flush=True)
    print("  url:", pg.url[:90], flush=True)
    print("  body:", body_text().replace("\n", " | ")[:250], flush=True)
    cks = {c["name"]: c["value"] for c in ctx.cookies()}
    print(f"  SPC_ST: {'ADA' if cks.get('SPC_ST') else 'TIDAK'}", flush=True)
    print(f"  90309999 events: {len(GATE)}", flush=True)

    # tes gate
    try:
        pg.goto("https://shopee.co.id/cart", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(8000)
        print(f"  cart url: {pg.url[:80]}", flush=True)
        print(f"  gate events: {len(GATE)}", flush=True)

        clean = len(GATE) == 0
        print(f"  ✅ GATE CLEAN: {clean}", flush=True)
        st("done", gate_clean=clean, gate_events=len(GATE))
    except Exception as e:
        print("  cart test err:", str(e)[:60], flush=True)

    cks = {c["name"]: c["value"] for c in ctx.cookies()}
    open("/root/shopee-verify/ck_autologin.txt", "w").write(
        "; ".join(f"{k}={v}" for k, v in cks.items()))
    print(f"  cookie -> ck_autologin.txt ({len(cks)})", flush=True)

    shoot("final")
    br.close()

print("=== SELESAI ===", flush=True)
