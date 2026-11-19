# -*- coding: utf-8 -*-
"""mitm_diff.py — BANDINGKAN request ANTIBOT yang LOLOS vs YANG GAGAL.

Tes A: browser headless/headed BUKAN dari cookie lama -> LoLoS
Tes B: request Python (dikit header) -> KENA

Yang dicatat: SEMUA header, urutan header, cookie yang dikirim, body,
HTTP version, dan response. Lalu diff.

Jalankan MITM: mitmdump di port 8081 menulis flow ke file .mitm
Lalu kita parse pakai mitmproxy API.
"""
import sys, json, ssl, urllib.request, urllib.error, time, os

CK_FILE = "/root/shopee-verify/ck_5th_solved.txt"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"

CK = open(CK_FILE).read().strip()
CSRF = next((c.split("=", 1)[1] for c in CK.split(";")
             if c.strip().startswith("csrftoken=")), "")

os.makedirs("/root/shopee-verify/dumps", exist_ok=True)

from playwright.sync_api import sync_playwright

HDRS = []
REQS = []

def run(label, headless):
    print(f"\n{'='*60}\n{label}\n{'='*60}")
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=headless, args=[
            "--no-sandbox", "--disable-dev-shm-usage",
            "--window-size=1366,768"])
        ctx = br.new_context(user_agent=UA, locale="id-ID",
                             viewport={"width": 1366, "height": 768},
                             timezone_id="Asia/Jakarta",
                             proxy={"server": PROXY})
        # cookie auth saja
        KEEP = {"csrftoken", "SPC_U", "SPC_ST", "SPC_R_T_ID", "SPC_R_T_IV",
                "SPC_T_ID", "SPC_T_IV", "SPC_CLIENTID", "REC_T_ID"}
        pairs = [(p.split("=", 1)[0].strip(), p.split("=", 1)[1].strip())
                 for p in CK.split(";") if "=" in p]
        ctx.add_cookies([{"name": k, "value": v, "domain": ".shopee.co.id",
                          "path": "/"} for k, v in pairs if k in KEEP])

        pg = ctx.new_page()

        def on_req(req):
            if "cart/mini" in req.url or "cart/get" in req.url:
                try:
                    hdrs = dict(req.headers)
                    hdr_order = list(req.headers.items())
                except Exception:
                    hdrs, hdr_order = {}, []
                try:
                    pd = req.post_data
                except Exception:
                    pd = None
                REQS.append({
                    "label": label, "url": req.url, "method": req.method,
                    "headers": hdrs, "hdr_order": hdr_order,
                    "body": pd,
                    "http": req.resource_type,
                })

        pg.on("request", on_req)

        try:
            pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print("  goto err:", str(e)[:60])
        pg.wait_for_timeout(7000)
        try:
            pg.goto("https://shopee.co.id/cart", wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print("  goto cart err:", str(e)[:60])
        pg.wait_for_timeout(7000)
        print("  url:", pg.url[:80])

        cks = {c["name"]: c["value"] for c in ctx.cookies()}
        out = f"/root/shopee-verify/dumps/ck_{label}.txt"
        open(out, "w").write("; ".join(f"{k}={v}" for k, v in cks.items()))
        print(f"  cookie -> {out} ({len(cks)})")
        br.close()


# Tes A: headed (bukan headless)
run("headed", False)
# Tes B: headless
run("headless", True)

print(f"\n\n{'='*60}\nTOTAL REQUEST ANTIBOT TERTANGKAP: {len(REQS)}\n{'='*60}")
json.dump(REQS, open("/root/shopee-verify/dumps/requests.json", "w"), indent=1)

for r in REQS:
    print(f"\n--- {r['label']} {r['method']} {r['url'].split('shopee.co.id')[-1][:50]}")
    print(f"    headers: {len(r['headers'])}")
    for k, v in r["hdr_order"]:
        vs = str(v)
        print(f"      {k}: {vs[:75]}")
    if r["body"]:
        print(f"    body: {r['body'][:200]}")
