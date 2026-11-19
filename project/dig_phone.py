# -*- coding: utf-8 -*-
"""
dig_phone.py — masuk profil, tutup modal, klik "Ubah" di baris Nomor Telepon,
lalu tangkap SEMUA request yang muncul di flow ganti nomor.

Juga probe jalur Email (Tambah/Ubah) karena endpoint-nya satu keluarga.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PROFILE = "https://shopee.co.id/user/account/profile"
HOME = "https://shopee.co.id/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

KEYS = ("account", "profile", "email", "phone", "otp", "vcode", "verify",
        "verification", "ivs", "sms", "security", "password", "unbind", "linked")


def parse_cookie(raw: str) -> dict[str, str]:
    out = {}
    for seg in raw.replace("\n", " ").split(";"):
        seg = seg.strip()
        if seg and "=" in seg:
            k, v = seg.split("=", 1)
            out[k.strip()] = v
    return out


def inject(ctx, page, jar):
    objs = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/",
             "secure": True, "sameSite": "None"} for k, v in jar.items()]
    try:
        ctx.add_cookies(objs)
    except Exception:
        pass
    cdp = ctx.new_cdp_session(page)
    cdp.send("Network.enable")
    for k, v in jar.items():
        try:
            cdp.send("Network.setCookie", {"name": k, "value": v,
                                           "domain": ".shopee.co.id", "path": "/",
                                           "secure": True, "httpOnly": False,
                                           "sameSite": "None"})
        except Exception:
            pass


def kill_modals(page):
    """Tutup modal bahasa / consent yang nutupin form."""
    tries = [
        "button:has-text('Bahasa Indonesia')",
        "button:has-text('Indonesia')",
        "button:has-text('Simpan')",
        "button:has-text('Konfirmasi')",
        "div[role=dialog] button[aria-label=Close]",
        "button.shopee-modal__close",
        ".shopee-modal__close",
        "button[class*=close]",
    ]
    for sel in tries:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click(timeout=2000)
                page.wait_for_timeout(800)
                print(f"    [modal] click {sel}")
        except Exception:
            pass
    for key in ("Escape", "Enter"):
        try:
            page.keyboard.press(key)
            page.wait_for_timeout(400)
        except Exception:
            pass


def main() -> None:
    jar = parse_cookie(open(sys.argv[1]).read().strip())
    out = Path("/root/shopee-verify/phone_flow.jsonl")
    fh = out.open("w")

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(user_agent=UA, locale="id-ID",
                            viewport={"width": 1366, "height": 900},
                            timezone_id="Asia/Jakarta")
        page = ctx.new_page()
        inject(ctx, page, jar)

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
            print(f"  >>> [{r.status}] {r.request.method} {u.split('?')[0][-70:]}")
            if pd:
                print(f"      REQ  {pd[:200]}")
            print(f"      RES  {body[:300]}")

        page.on("response", on_resp)

        print("[1] warm home")
        page.goto(HOME, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        print("[2] profile")
        page.goto(PROFILE, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        if "login" in page.url.lower():
            print("[!] cookie mati")
            return

        print("[3] tutup modal")
        kill_modals(page)
        page.wait_for_timeout(1500)
        page.screenshot(path="/root/shopee-verify/p1_clean.png", full_page=True)

        print("\n[4] cari baris 'Nomor Telepon' + tombol Ubah")
        # cari semua tombol yang bertuliskan Ubah, dan lihat konteks labelnya
        btns = page.query_selector_all("button, a, div[role=button]")
        target = None
        for el in btns:
            try:
                txt = (el.inner_text() or "").strip()
            except Exception:
                continue
            if txt not in ("Ubah", "Tambah", "Verifikasi", "Verif", "Ganti"):
                continue
            # naik ke parent dan lihat apakah ada label Nomor Telepon / Email
            try:
                ctx_txt = el.evaluate(
                    """(e)=>{let p=e;for(let i=0;i<6&&p;i++){p=p.parentElement;if(!p)break;
                       const t=(p.innerText||'').toLowerCase();
                       if(t.length<400&&(t.includes('telepon')||t.includes('email')))return t;}
                       return '';}""")
            except Exception:
                ctx_txt = ""
            print(f"    btn {txt!r} ctx={(ctx_txt[:70] if ctx_txt else '-')!r}")
            if "telepon" in ctx_txt and target is None:
                target = el

        if target is None:
            print("[!] tombol Ubah untuk Nomor Telepon tidak ketemu — coba semua tombol Ubah")
            for el in btns:
                try:
                    if (el.inner_text() or "").strip() == "Ubah":
                        target = el
                        break
                except Exception:
                    continue

        if target is None:
            print("[!] tidak ada tombol Ubah sama sekali")
            page.screenshot(path="/root/shopee-verify/p2_fail.png", full_page=True)
            return

        print("\n[5] klik Ubah (nomor telepon)")
        try:
            target.scroll_into_view_if_needed(timeout=5000)
        except Exception:
            pass
        target.click(timeout=8000)
        page.wait_for_timeout(6000)

        print(f"    URL: {page.url[:110]}")
        page.screenshot(path="/root/shopee-verify/p3_after_click.png", full_page=True)

        print("\n[6] isi halaman setelah klik:")
        try:
            print(page.inner_text("body")[:1200])
        except Exception:
            pass

        # klik tombol-tombol lanjutan yang muncul (Verifikasi / Lanjut / Kirim)
        for label in ("Verifikasi", "Lanjut", "Kirim Kode", "Kirim OTP", "Mulai", "Ya, lanjutkan"):
            try:
                el = page.query_selector(f"button:has-text('{label}')")
                if el and el.is_visible():
                    print(f"\n[7] klik lanjutan: {label}")
                    el.click(timeout=5000)
                    page.wait_for_timeout(5000)
                    page.screenshot(path=f"/root/shopee-verify/p4_{label.replace(' ','_')}.png",
                                    full_page=True)
                    break
            except Exception:
                pass

        page.wait_for_timeout(3000)
        b.close()

    fh.close()
    print(f"\n[+] capture -> {out}")


if __name__ == "__main__":
    main()
