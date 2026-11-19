"""cap_verify.py — submit captcha/verify dengan jawaban SadCaptcha.

Dari ivs_js/063.js:
  POST /api/v4/anti_fraud/captcha/verify
  body = {
    encrypted_data: AES({app_key, scene, captcha_type, captcha_answer,
                         user_action, phone, email, username,
                         captcha_extra_info:{tracking_id}}),
    encrypted_security_data: <dari SDK>,
    dfp_token: <dari SDK>
  }

user_action (dari capbundle.js) = JSON.stringify({
  slider_start_timestamp, slider_end_timestamp,
  mouse_events: [[x,y,ts,type],...],
  touch_events: [], device_orientation_events: [],
  captcha: {...}, audio: {}
})

captcha_answer = ? (cari format: proporsi atau pixel)
Tipe 10 = drag piece, jawaban = koordinat target.

Tes beberapa format captcha_answer.
"""
import json, sys, base64, hashlib, os, time, random
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

CK = sys.argv[1] if len(sys.argv) > 1 else "ck_1553.txt"
PROXY = "http://127.0.0.1:18080"
KEY = b"dRgUkXp2r5u8x/A?D(G+KbPeShVmYq3t"
APPKEY = "TSS.PC"
SCENE = "crawler_item"


def log(*a):
    print(*a, flush=True)


def evp(pw, salt):
    d, prev = b"", b""
    while len(d) < 48:
        prev = hashlib.md5(prev + pw + salt).digest()
        d += prev
    return d[:32], d[32:48]


def enc(obj):
    salt = os.urandom(8)
    k, iv = evp(KEY, salt)
    ct = AES.new(k, AES.MODE_CBC, iv).encrypt(
        pad(json.dumps(obj, separators=(",", ":")).encode(), 16))
    return base64.b64encode(b"Salted__" + salt + ct).decode()


def dec(b):
    try:
        raw = base64.b64decode(b)
        if not raw.startswith(b"Salted__"):
            return {"_nohdr": raw[:60]}
        k, iv = evp(KEY, raw[8:16])
        return json.loads(unpad(AES.new(k, AES.MODE_CBC, iv).decrypt(raw[16:]), 16))
    except Exception as e:
        return {"_err": str(e)[:60]}


ck = open(CK).read().strip()
cookies = {p.split("=", 1)[0].strip(): p.split("=", 1)[1].strip()
           for p in ck.split(";") if "=" in p}
tracking = open("TRACKING.txt").read().strip()
cap = json.load(open("CAPTCHA.json"))["data"]
solve = json.load(open("SOLVE.json"))
prop = solve["prop"]

s = requests.Session()
s.cookies.update(cookies)
s.proxies = {"http": PROXY, "https": PROXY}
s.headers.update({
    "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"),
    "x-api-source": "pc", "af-ac-enc-dat": "0123456789abcdef",
    "x-sz-sdk-version": "1.12.45", "x-requested-with": "XMLHttpRequest",
    "referer": "https://shopee.co.id/", "accept": "application/json",
    "content-type": "application/json"})

log(f"captcha_id: {cap['captcha_id']}")
log(f"captcha_type: {cap['captcha_type']}")
log(f"slideXProportion: {prop}")
log(f"tracking: {len(tracking)}B")

# bangun trajectory 20 sample manusiawi
PW = 280
target_px = prop * PW
log(f"target_px = {target_px:.1f}")


def trajectory(target, n=20):
    t0 = int(time.time() * 1000)
    ev = []
    # easing: lambat -> cepat -> lambat
    span = 900 + random.randint(0, 500)
    for i in range(n):
        p = (i + 1) / n
        ease = p * p * (3 - 2 * p)          # smoothstep
        x = round(ease * target + random.uniform(-0.7, 0.7), 1)
        y = round(0.4 * x + random.uniform(-0.5, 0.5), 1)
        ts = t0 + int(span * p) + random.randint(0, 25)
        ev.append([x, y, ts, 1])
    t1 = t0 + span + random.randint(40, 120)
    ev.append([round(target, 1), ev[-1][1], t1, 2])
    return t0, t1, ev


start, end, events = trajectory(target_px)
ua_obj = {"slider_start_timestamp": start,
          "slider_end_timestamp": end,
          "mouse_events": events,
          "touch_events": [],
          "device_orientation_events": [],
          "captcha": {},
          "audio": {}}
log(f"trajectory: {len(events)} events, {start}→{end} ({end-start}ms)")

# jawaban: coba beberapa format
FORMS = [
    ("int_px", int(round(target_px))),
    ("float_prop", round(prop, 6)),
    ("str_int", str(int(round(target_px)))),
    ("dict_prop", {"x": round(prop, 6), "y": 0}),
]

for name, ans in FORMS:
    p = {"app_key": APPKEY, "scene": SCENE,
         "captcha_type": cap["captcha_type"],
         "captcha_answer": ans,
         "user_action": json.dumps(ua_obj),
         "phone": "", "email": "", "username": "",
         "captcha_extra_info": {"tracking_id": tracking}}
    body = {
        "encrypted_data": enc(p),
        "encrypted_security_data": "",
        "dfp_token": "",
    }
    log(f"\n--- answer={name} ({str(ans)[:30]}) ---")
    try:
        r = s.post("https://shopee.co.id/api/v4/anti_fraud/captcha/verify",
                   json=body, timeout=45)
        j = r.json()
        log(f"  {r.status_code} err={j.get('error')}")
        if j.get("encrypted_data"):
            d = dec(j["encrypted_data"])
            log(f"  ✅ {json.dumps(d)[:400]}")
            if d.get("error") == 0 or d.get("captcha_token") or d.get("success"):
                log("  🎉🎉🎉 CAPTCHA LULUS!")
                json.dump({"form": name, "resp": d}, open("VERIFY_OK.json", "w"), indent=1)
                break
        else:
            log(f"  plain: {json.dumps(j)[:220]}")
    except Exception as e:
        log(f"  ERR {str(e)[:70]}")
