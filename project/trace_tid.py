# -*- coding: utf-8 -*-
"""trace_tid.py — MITM: hook fetch+XHR, lacak ASAL anti_bot_tracking_id.

Fokus: siapa yang pertama kali menetapkan gqRjZGVr... dan dari mana.
Juga dump localStorage + IndexedDB + cookie untuk cari sumbernya.
"""
import sys, json, ssl, urllib.request, urllib.error, urllib.parse

CK_FILE = sys.argv[1] if len(sys.argv) > 1 else "/root/shopee-verify/ck_5th_solved.txt"
PW = sys.argv[2] if len(sys.argv) > 2 else "qwertyui123"

CK = open(CK_FILE).read().strip()
CSRF = next((c.split("=", 1)[1] for c in CK.split(";")
             if c.strip().startswith("csrftoken=")), "")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
PROXY = "http://127.0.0.1:18080"

_ct = ssl.create_default_context(); _ct.check_hostname = False
_ct.verify_mode = ssl.CERT_NONE
_OP = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}),
    urllib.request.HTTPSHandler(context=_ct))


def api(path, body=None, method="POST",
        ref="https://shopee.co.id/user/account/profile"):
    h = {"User-Agent": UA, "Cookie": CK, "Accept": "application/json",
         "x-api-source": "pc", "x-requested-with": "XMLHttpRequest",
         "x-shopee-language": "id", "Referer": ref, "x-csrftoken": CSRF}
    d = None
    if body is not None:
        h["Content-Type"] = "application/json"; d = json.dumps(body).encode()
    r = urllib.request.Request("https://shopee.co.id" + path, data=d,
                               method=method, headers=h)
    try:
        with _OP.open(r, timeout=35) as x: return json.loads(x.read())
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read())
        except Exception: return {"http": e.code}
    except Exception as e: return {"err": str(e)[:80]}


r1 = api("/api/v4/account/management/change_phone_init_v2", {})
d1 = r1.get("data") or {}
cp, ut = d1.get("change_phone_token"), d1.get("ivs_utoken")
print("init:", r1.get("error"), "cp:", bool(cp))

from playwright.sync_api import sync_playwright

cookies = [{"name": k, "value": v, "domain": ".shopee.co.id", "path": "/"}
           for k, _, v in (p.strip().partition("=") for p in CK.split(";"))
           if k and v]

HOOK = r"""
(() => {
  window.__TID = [];
  const push = (src, u, v) => {
    if (!v) return;
    const s = String(v);
    if (s.includes('gqRjZGVr') || (s.length > 60 && s.startsWith('gq'))) {
      window.__TID.push({src, u: String(u).slice(0,120), v: s.slice(0,80),
                         st: new Error().stack.split('\n').slice(1,5).join(' | ').slice(0,400)});
    }
  };
  const _fetch = window.fetch;
  window.fetch = function(...a) {
    try {
      const u = a[0] && (a[0].url || a[0]);
      const b = a[1] && a[1].body;
      if (b) push('fetch-body', u, typeof b === 'string' ? b : '');
      if (u) push('fetch-url', u, u);
    } catch(e) {}
    return _fetch.apply(this, a);
  };
  const _open = XMLHttpRequest.prototype.open;
  const _send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(m, u) {
    this.__u = u; push('xhr-open', u, u); return _open.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function(b) {
    try { if (b) push('xhr-body', this.__u, typeof b === 'string' ? b : ''); } catch(e) {}
    return _send.apply(this, arguments);
  };
  const _setItem = Storage.prototype.setItem;
  Storage.prototype.setItem = function(k, v) {
    push('storage-set:' + k, '', v);
    return _setItem.apply(this, arguments);
  };
})();
"""

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=False, args=[
        "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--use-gl=swiftshader", "--window-size=1366,768"])
    ctx = br.new_context(user_agent=UA, locale="id-ID",
                         viewport={"width": 1366, "height": 768},
                         timezone_id="Asia/Jakarta", proxy={"server": PROXY})
    ctx.add_cookies(cookies)
    ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome={runtime:{}};")
    ctx.add_init_script(HOOK)
    pg = ctx.new_page()

    print("\n=== buka /mall (hook aktif) ===")
    pg.goto("https://shopee.co.id/mall", wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(9000)

    hits = pg.evaluate("()=>window.__TID||[]")
    print(f"hit tracking id di /mall: {len(hits)}")
    for h in hits[:6]:
        print(f"   [{h['src']}] {h['u'][:60]}")
        print(f"      v={h['v'][:60]}")
        if h.get("st"): print(f"      stack={h['st'][:220]}")

    print("\n=== localStorage / sessionStorage / cookie scan ===")
    scan = pg.evaluate("""()=>{
      const out={ls:{},ss:{},ck:{}};
      for(let i=0;i<localStorage.length;i++){const k=localStorage.key(i);
        const v=localStorage.getItem(k)||'';
        if(v.includes('gqRj')||k.toLowerCase().includes('bot')||k.toLowerCase().includes('track'))
          out.ls[k]=v.slice(0,80);}
      for(let i=0;i<sessionStorage.length;i++){const k=sessionStorage.key(i);
        const v=sessionStorage.getItem(k)||'';
        if(v.includes('gqRj')||k.toLowerCase().includes('bot')||k.toLowerCase().includes('track'))
          out.ss[k]=v.slice(0,80);}
      document.cookie.split(';').forEach(c=>{
        const [k,...r]=c.trim().split('=');const v=r.join('=');
        if(v.includes('gqRj')||k.toLowerCase().includes('bot')||k.toLowerCase().includes('farl'))
          out.ck[k]=v.slice(0,80);});
      return out;
    }""")
    print("  localStorage:", json.dumps(scan["ls"], indent=1)[:500])
    print("  sessionStorage:", json.dumps(scan["ss"], indent=1)[:600])
    print("  cookie:", json.dumps(scan["ck"], indent=1)[:400])

    print("\n=== IndexedDB databases ===")
    idb = pg.evaluate("""async()=>{
      try{
        if(!indexedDB.databases) return ['unsupported'];
        const dbs = await indexedDB.databases();
        return dbs.map(d=>d.name);
      }catch(e){return ['err:'+e.message];}
    }""")
    print("  ", idb)

    print("\n=== buka /user/account/profile ===")
    pg.goto("https://shopee.co.id/user/account/profile",
            wait_until="domcontentloaded", timeout=90000)
    pg.wait_for_timeout(7000)
    print("  url:", pg.url[:80])
    hits2 = pg.evaluate("()=>window.__TID||[]")
    print(f"  hit baru: {len(hits2)}")
    for h in hits2[-5:]:
        print(f"   [{h['src']}] {h['u'][:60]} v={h['v'][:50]}")

    br.close()

json.dump({"cp": cp, "ut": ut}, open("/root/shopee-verify/TID_CTX.json", "w"))
