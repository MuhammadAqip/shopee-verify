"""FIND_FINAL2.py — cari endpoint finalisasi lewat intercept fetch/XHR page.

Strategi baru (CDP scriptParsed terbukti 0 di headless):
  1. hook window.fetch + XMLHttpRequest SETELAH page load
  2. KLIK tombol "Ubah Nomor" asli di UI -> Shopee sendiri yang panggil
     endpoint finalisasi saat lo submit form
  3. TAPI kita tidak punya OTP valid untuk submit

  -> Alternatif: dump semua bundle URL yang di-load, download pakai requests,
     grep 'vcode_token' / 'set_phone'.

Cara ini lebih pasti: bundle list dari performance.getEntriesByType('resource').
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
    open("/root/shopee-verify/FF2.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = [{"name": p.split("=", 1)[0].strip(),
            "value": p.split("=", 1)[1].strip(),
            "domain": ".shopee.co.id", "path": "/"}
           for p in ck.split(";") if "=" in p]

from playwright.sync_api import sync_playwright

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

    log("=== buka home + /user/account/phone (paksa load bundle akun) ===")
    for url in ("https://shopee.co.id/",
                "https://shopee.co.id/user/account/phone"):
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=55000)
        except Exception:
            pass
        pg.wait_for_timeout(13000)

    # ambil semua resource JS yang di-load
    res = pg.evaluate("""()=>performance.getEntriesByType('resource')
      .map(e=>e.name).filter(n=>n.includes('.js'))""")
    log(f"  {len(res)} JS resource")

    # filter kandidat: bundle utama (hashed)
    cands = [u for u in res if "deo.shopeemobile.com/shopee/" in u
             or "/assets/" in u]
    log(f"  {len(cands)} kandidat bundle")

    # download semua via requests (pakai cookie + proxy)
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Referer": "https://shopee.co.id/"})
    ckstr = {"Cookie": "; ".join(f"{c['name']}={c['value']}" for c in cookies)}
    px = {"http": PROXY, "https": PROXY} if PROXY else None

    os.makedirs("/root/shopee-verify/pb", exist_ok=True)
    got = 0
    HITS = []
    for u in cands:
        try:
            r = s.get(u, headers=ckstr, proxies=px, timeout=40)
            if r.status_code != 200 or len(r.content) < 5000:
                continue
            body = r.text
            fn = f"/root/shopee-verify/pb/{got:03d}.js"
            open(fn, "w").write(body)
            got += 1
            hit = [p for p in ("vcode_token", "set_phone", "change_phone",
                               "phone_otp_account_set_phone")
                   if p in body]
            if hit:
                HITS.append((u, fn, hit, body))
                log(f"  ★ {os.path.basename(u)[:50]} -> {hit}")
        except Exception:
            pass

    log(f"\n  {got} bundle tersimpan, {len(HITS)} punya keyword")

    # grep endpoint
    log("\n=== ENDPOINT dari bundle ber-hit ===")
    seen = set()
    for u, fn, hit, body in HITS:
        log(f"\n--- {os.path.basename(u)[:60]} [{hit}] ---")
        for pat in ("vcode_token", "set_phone", "change_phone"):
            for m in re.finditer(pat, body):
                i = m.start()
                seg = body[max(0, i - 400):i + 400]
                for pp in set(re.findall(r'/api/v[0-9]/[A-Za-z0-9_/\-]{4,80}', seg)):
                    if pp not in seen:
                        seen.add(pp)
                        log(f"  PATH {pp}")
    for p in sorted(seen):
        log(f"  {p}")

    json.dump({"res": res[:200], "hits": [h[2] for h in HITS]},
              open("/root/shopee-verify/FF2.json", "w"), indent=1)
    br.close()

log("\n=== SELESAI ===")
