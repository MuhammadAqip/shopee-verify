# -*- coding: utf-8 -*-
"""
dig2.py — versi tahan modal. Strategi:
  1. inject cookie
  2. warm di homepage sampai lolos (bukan profile)
  3. reload profile beberapa kali dengan jeda
  4. tutup modal via JS (paksa hapus node), bukan klik
  5. baru cari tombol Ubah
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HOME = "https://shopee.co.id/"
PROFILE = "https://shopee.co.id/user/account/profile"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
KEYS = ("account", "profile", "email", "phone", "otp", "vcode", "verify",
        "verification", "ivs", "sms", "security", "password", "unbind", "linked")


def parse_cookie(raw):
    out = {}
    for seg in raw.replace("\n", " ").split(";"):
        seg = seg.strip()
        if seg and "=" in seg:
            k, v = seg.split("=", 1)
            out[k.strip()] = v
    return out


FORCE_CLOSE_JS = r"""
() => {
  let n = 0;
  document.querySelectorAll('[class*="modal"],[class*="popup"],[class*="Popup"],[role="dialog"],[class*="overlay"],[class*="Overlay"]').forEach(el => {
    const cs = getComputedStyle(el);
    if (cs.position === 'fixed' || cs.position === 'absolute' || el.getAttribute('role') === 'dialog') {
      el.remove(); n++;
    }
  });
  document.body.style.overflow = 'auto';
  document.documentElement.style.overflow = 'auto';
  return n;
}
"""


def main():
    jar = parse_cookie(open(sys.argv[1]).read().strip())
    out = Path("/root/shopee-verify/phone_flow.jsonl")
    fh = out.open("w")

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(user_agent=UA, locale="id-ID",
                            viewport={"width": 1366, "height": 900},
                            timezone_id="Asia/Jakarta",
                            extra_http_headers={"Accept-Language": "id-ID,id;q=0.9"})
        page = ctx.new_page()

        objs = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/",
                 "secure": True, "sameSite": "None"} for k, v in jar.items()]
        try:
            ctx.add_cookies(objs)
        except Exception as e:
            print("add_cookies:", e)
        cdp = ctx.new_cdp_session(page)
        cdp.send("Network.enable")
        for k, v in jar.items():
            try:
                cdp.send("Network.setCookie", {"name": k, "value": v,
                                               "domain": ".shopee.co.id", "path": "/",
                                               "secure": True, "httpOnly": False})
            except Exception:
                pass

        def on_resp(r):
            u = r.url
            if "shopee.co.id/api/" not in u:
                return
            if not any(k in u.lower() for k in KEYS):
                return
            try:
                body = r.text()[:5000]
            except Exception:
                body = ""
            try:
                pd = r.request.post_data
            except Exception:
                pd = None
            fh.write(json.dumps({"ts": time.time(), "status": r.status,
                                 "method": r.request.method, "url": u,
                                 "req_body": pd[:1500] if pd else None,
                                 "resp_body": body}, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"  >>> [{r.status}] {r.request.method} {u.split('?')[0][-68:]}")
            if pd:
                print(f"      REQ  {pd[:220]}")
            print(f"      RES  {body[:260]}")

        page.on("response", on_resp)

        # --- warm berkali-kali sampai tidak ada modal / redirect ---
        for attempt in range(4):
            print(f"\n[warm {attempt+1}/4] home")
            try:
                page.goto(HOME, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print("  goto:", e)
            page.wait_for_timeout(5000)
            url = page.url
            if "verify" in url or "login" in url:
                print(f"  blocked: {url[:100]}")
                page.wait_for_timeout(12000)
                continue
            print(f"  ok: {url[:80]}")
            break

        print("\n[profile] load")
        page.goto(PROFILE, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)
        print(f"  url={page.url[:100]}")

        # paksa hapus modal
        removed = page.evaluate(FORCE_CLOSE_JS)
        print(f"[modal] node dihapus paksa: {removed}")
        page.wait_for_timeout(2500)
        page.screenshot(path="/root/shopee-verify/d1_forced.png", full_page=True)

        txt = page.inner_text("body")
        print("\n[isi halaman 900 char]")
        print(txt[:900])

        # dump semua tombol
        print("\n[daftar tombol]")
        btns = page.query_selector_all("button, a[role=button], div[role=button]")
        for i, el in enumerate(btns[:40]):
            try:
                t = (el.inner_text() or "").strip().replace("\n", " ")
            except Exception:
                continue
            if not t or len(t) > 40:
                continue
            print(f"  [{i}] {t!r}")

        # klik tombol yang menandakan ubah nomor
        clicked = False
        for label in ("Ubah", "Verifikasi", "Tambah"):
            for el in btns:
                try:
                    t = (el.inner_text() or "").strip()
                    if t != label or not el.is_visible():
                        continue
                    ctx_t = el.evaluate(
                        """(e)=>{let p=e;for(let i=0;i<7&&p;i++){p=p.parentElement;if(!p)break;
                           const t=(p.innerText||'').toLowerCase();
                           if(t.length<500&&(t.includes('telepon')||t.includes('email')))return t;}
                           return '';}""")
                    if "telepon" in ctx_t:
                        print(f"\n[CLICK] {label} pada baris: {ctx_t[:60]!r}")
                        el.scroll_into_view_if_needed()
                        el.click(timeout=8000)
                        clicked = True
                        break
                except Exception as e:
                    continue
            if clicked:
                break

        if not clicked:
            print("\n[!] tidak ada tombol ubah nomor yang terdeteksi")
        else:
            page.wait_for_timeout(6000)
            page.screenshot(path="/root/shopee-verify/d2_clicked.png", full_page=True)
            print(f"  url={page.url[:100]}")
            print("  isi:")
            print(page.inner_text("body")[:800])

        b.close()
    fh.close()
    print(f"\n[capture] {out}")


if __name__ == "__main__":
    main()
