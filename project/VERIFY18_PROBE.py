"""VERIFY18_PROBE.py — cari body parameter yang benar untuk verify_vcode op=18.

Kode 23500000 = "code mismatch" — tapi kode benar. Kemungkinan:
  a) butuh m_token / cp_token / otp_token dari init_v2
  b) butuh seq_no / change_phone_token
  c) operation berbeda saat verify (op=8?)
  d) harus ada header khusus

Script ini brute kombinasi body yang masuk akal, dan juga coba verify
lewat page-context (SDK sign) supaya kalau butuh SAP header bisa lolos.

PENTING: kalau OTP sudah di-verify sekali dengan body SALAH, kode bisa
hangus. Jadi urutan dicoba dari yang paling mungkin dulu:
  1. page-context verify (SDK sign) - paling mirip browser asli
  2. requests + cp_token
  3. requests + operation 8
"""
import json, sys, time, os
import requests

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_zax.txt"
PH = sys.argv[2] if len(sys.argv) > 2 else "62895806564446"
CODE = sys.argv[3] if len(sys.argv) > 3 else "976878"
PROXY = os.environ.get("SHOPEE_PROXY", "")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
T0 = time.time()


def log(*a):
    m = f"[{int(time.time()-T0):4d}s] " + " ".join(str(x) for x in a)
    print(m, flush=True)
    open("/root/shopee-verify/V18P.log", "a").write(m + "\n")


ck = open(CK).read().strip()
cookies = {p.split("=", 1)[0].strip(): p.split("=", 1)[1].strip()
           for p in ck.split(";") if "=" in p}
cookies_pw = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
              for k, v in cookies.items()]

from playwright.sync_api import sync_playwright

NET = []


def onresp(r):
    u = r.url
    if "/api/v4/otp" in u or "/api/v4/account/management" in u:
        try:
            b = r.text()
        except Exception:
            b = ""
        NET.append({"u": u.split("shopee.co.id")[-1][:80], "s": r.status, "b": b[:600]})
        log(f"  NET {r.status} {u.split('shopee.co.id')[-1][:60]} :: {b[:180]}")


with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,900",
        "--disable-blink-features=AutomationControlled", "--lang=id-ID"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 900},
                         timezone_id="Asia/Jakarta",
                         proxy={"server": PROXY} if PROXY else None)
    ctx.add_cookies(cookies_pw)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};"
        "Object.defineProperty(navigator,'languages',{get:()=>['id-ID','id','en']});")
    pg = ctx.new_page()
    pg.on("response", onresp)

    # buka halaman ubah nomor supaya SDK + state siap
    log("=== warm: /user/account/phone ===")
    try:
        pg.goto("https://shopee.co.id/user/account/phone",
                wait_until="domcontentloaded", timeout=55000)
    except Exception:
        pass
    pg.wait_for_timeout(10000)
    cur = pg.evaluate("()=>location.href")
    log(f"  url: {cur[:100]}")

    # kalau di-redirect ke verify, balik ke home
    if "/verify/" in cur:
        log("  redirect — balik ke home")
        try:
            pg.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=55000)
        except Exception:
            pass
        pg.wait_for_timeout(9000)

    # === ambil state: init_v2 + settings op18 (fresh) ===
    log("\n=== init_v2 + settings op18 dari page ===")
    st = pg.evaluate("""async (phone)=>{
      const out={};
      try{
        const i=await (await fetch('/api/v4/account/management/change_phone_init_v2',
          {method:'POST',credentials:'include',
           headers:{'Content-Type':'application/json'},
           body:JSON.stringify({phone,seq_no:null})})).json();
        const id=i.data||{};
        out.init_err=i.error;
        out.ivs=id.ivs_required;
        out.cp_token=id.change_phone_token||'';
        out.init_keys=Object.keys(id);

        const g=await (await fetch('/api/v4/otp/get_settings_v2',
          {method:'POST',credentials:'include',
           headers:{'Content-Type':'application/json'},
           body:JSON.stringify({phone,operation:18})})).json();
        const gd=g.data||{};
        out.set_err=g.error;
        out.seed=gd.seed||'';
        out.need_cap=gd.need_captcha;
        out.set_keys=Object.keys(gd);
        return out;
      }catch(e){out.ex=String(e).slice(0,120);return out;}
    }""", PH)
    log(f"  {json.dumps(st)[:500]}")
    cptok = st.get("cp_token") or ""
    seed = st.get("seed") or ""

    # === brute verify body variants DARI PAGE (SDK sign otomatis) ===
    log("\n=== verify dari PAGE (SDK sign) — variant brute ===")
    variants = [
        {"name": "v1 phone+code+op18", "b": {"phone": PH, "code": CODE, "operation": 18}},
        {"name": "v2 +seed", "b": {"phone": PH, "code": CODE, "operation": 18, "seed": seed}},
        {"name": "v3 +m_token(cp)", "b": {"phone": PH, "code": CODE, "operation": 18, "m_token": cptok}},
        {"name": "v4 +force_channel", "b": {"phone": PH, "code": CODE, "operation": 18,
                                            "force_channel": False, "m_token": cptok}},
        {"name": "v5 op=8 +m_token", "b": {"phone": PH, "code": CODE, "operation": 8, "m_token": cptok}},
        {"name": "v6 op=8 +opttoken", "b": {"phone": PH, "code": CODE, "operation": 8,
                                            "m_token": cptok, "seed": seed}},
        {"name": "v7 vcode key", "b": {"phone": PH, "vcode": CODE, "operation": 18,
                                       "m_token": cptok}},
    ]

    for v in variants:
        r = pg.evaluate("""async (body)=>{
          try{
            const r=await fetch('/api/v4/otp/verify_vcode',{method:'POST',
              credentials:'include',headers:{'Content-Type':'application/json'},
              body:JSON.stringify(body)});
            return {s:r.status,j:await r.json()};
          }catch(e){return {ex:String(e).slice(0,80)};}
        }""", v["b"])
        err = (r.get("j") or {}).get("error")
        log(f"  {v['name']:22s} -> err={err} {(r.get('j') or {}) if err==0 else ''}")
        if err == 0:
            log(f"\n  🎉🎉🎉 VERIFY SUKSES dengan {v['name']}")
            log(f"  response: {json.dumps(r.get('j'))[:400]}")
            json.dump({"variant": v["name"], "body": v["b"], "resp": r.get("j")},
                      open("/root/shopee-verify/V18_OK.json", "w"), indent=1)
            break

    json.dump({"net": NET[-20:], "state": st},
              open("/root/shopee-verify/V18P.json", "w"), indent=1)
    pg.screenshot(path="/root/shopee-verify/V18P.png", full_page=True)
    br.close()

log("\n=== SELESAI ===")
