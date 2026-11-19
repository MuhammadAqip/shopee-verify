"""FIND_FINAL.py — temukan endpoint finalisasi set_phone dari bundle Shopee.

vcode_token sudah didapat (verify err=0). Tinggal endpoint yang menukarnya
jadi nomor baru. Endpoint itu PASTI ada di bundle JS halaman
/user/account/phone.

Strategi:
  1. buka /user/account/phone, dump SEMUA script source via CDP
  2. grep 'vcode_token' / 'set_phone' / change_phone_* di tiap script
  3. cetak URL endpoint + body shape sekitar hit
"""
import json, re, sys, os, time

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_zax.txt"
PROXY = os.environ.get("SHOPEE_PROXY", "")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/FF.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright

SCRIPTS = {}


def on_script(src):
    """Simpan semua script source via CDP."""
    try:
        body = src["source"]
        url = src.get("url") or f"inline-{src['scriptId']}"
        if body and len(body) > 2000:  # skip stub kecil
            SCRIPTS[url] = body
    except Exception:
        pass


with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,900",
        "--disable-blink-features=AutomationControlled", "--lang=id-ID"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 900},
                         timezone_id="Asia/Jakarta",
                         proxy={"server": PROXY} if PROXY else None)
    ctx.add_cookies(cookies)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};")
    pg = ctx.new_page()

    # CDP untuk dump SEMUA script source
    cdp = ctx.new_cdp_session(pg)
    cdp.send("Debugger.enable")
    cdp.on("Debugger.scriptParsed", on_script)

    for url in ("https://shopee.co.id/user/account/phone",
                "https://shopee.co.id/user/account/settings"):
        log(f"=== buka {url} ===")
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=55000)
        except Exception:
            pass
        pg.wait_for_timeout(14000)

    log(f"\n  scripts tertangkap: {len(SCRIPTS)}")

    # grep pattern yang relevan
    PATS = ["vcode_token", "set_phone", "change_phone", "bind_phone",
            "update_phone", "phone_otp_account_set_phone", "verify_vcode"]
    HITS = {}
    for url, body in SCRIPTS.items():
        for p in PATS:
            if p in body:
                HITS.setdefault(p, []).append((url, body))

    for p in PATS:
        hs = HITS.get(p, [])
        log(f"\n=== {p}: {len(hs)} script ===")
        seen = set()
        for url, body in hs[:6]:
            for m in re.finditer(re.escape(p), body):
                i = m.start()
                ctx_s = body[max(0, i - 260):i + 260].replace("\n", " ")
                # ekstrak path api kalau ada
                paths = re.findall(r'/api/v[0-9]/[A-Za-z0-9_/\-]{4,70}', ctx_s)
                if paths:
                    for pp in set(paths):
                        if pp not in seen:
                            seen.add(pp)
                            log(f"  PATH {pp}")
                            log(f"       {ctx_s[:300]}")
                break

    # ekstrak SEMUA path api dari script yang punya vcode_token
    log("\n\n=== SEMUA PATH API dari script ber-'vcode_token' ===")
    allp = set()
    for url, body in HITS.get("vcode_token", []):
        for m in re.finditer(r'/api/v[0-9]/[A-Za-z0-9_/\-]{4,80}', body):
            allp.add(m.group(0))
    for pp in sorted(allp):
        log(f"  {pp}")

    # simpan semua script untuk grep manual
    os.makedirs("/root/shopee-verify/pscripts", exist_ok=True)
    for n, (url, body) in enumerate(SCRIPTS.items()):
        fn = f"/root/shopee-verify/pscripts/{n:03d}_{re.sub(r'[^A-Za-z0-9]', '_', url)[-60:]}.js"
        try:
            open(fn, "w").write(body)
        except Exception:
            pass
    log(f"\n  {len(SCRIPTS)} script disimpan di /root/shopee-verify/pscripts/")

    br.close()

log("\n=== SELESAI ===")
