# -*- coding: utf-8 -*-
"""cp_multi.py — tes 10002 di SEMUA cookie yang hidup.

Kalau semua 10002 -> flag akun/server-side.
Kalau ada yang 0    -> bukan flag, tapi state cookie tertentu.

Juga uji: apakah 10002 muncul di akun yang punya phone verified vs tidak.
"""
import json, sys, urllib.request, urllib.error, time, os

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
M = "/api/v4/account/management"

FILES = [f for f in os.listdir(".") if f.startswith("ck_") and f.endswith(".txt")]
FILES.sort()
if len(sys.argv) > 1:
    FILES = sys.argv[1:]

results = []


def log(*a):
    print(*a, flush=True)


def mk(ckfile):
    ck = open(ckfile).read().strip()
    csrf = ""
    for p in ck.split(";"):
        if p.strip().startswith("csrftoken="):
            csrf = p.split("=", 1)[1].strip()
    return ck, csrf


def call(ck, csrf, path, body=None, method=None):
    h = {"Cookie": ck, "User-Agent": UA, "X-API-SOURCE": "pc",
         "X-Requested-With": "XMLHttpRequest",
         "Referer": "https://shopee.co.id/user/account/settings",
         "Content-Type": "application/json", "Accept": "application/json",
         "X-CSRFToken": csrf, "X-Shopee-Language": "id"}
    d = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request("https://shopee.co.id" + path, data=d, headers=h,
                                 method=method or ("POST" if body is not None else "GET"))
    try:
        r = urllib.request.urlopen(req, timeout=35)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}
    except Exception as ex:
        return 0, {"exc": str(ex)[:40]}


for f in FILES:
    if f.endswith("_solved.txt") and f.replace("_solved", "") in FILES:
        pass
    ck, csrf = mk(f)
    s, j = call(ck, csrf, "/api/v4/account/basic/get_account_info")
    d = j.get("data") or {}
    uid = d.get("userid")
    ph = d.get("phone") or ""
    err_acc = j.get("error")

    row = {"file": f, "uid": uid, "phone": ph, "acc_err": err_acc}

    if err_acc == 0:
        s, j2 = call(ck, csrf, f"{M}/change_phone_init", {})
        seq = (j2.get("data") or {}).get("seq_no")
        row["init"] = j2.get("error")
        row["seq"] = bool(seq)

        if seq:
            s, j3 = call(ck, csrf, f"{M}/get_password_verify_method?seq_no={seq}&scenario=1", None, "GET")
            row["verify_method"] = j3.get("error")
        else:
            row["verify_method"] = None

        s, j4 = call(ck, csrf, f"{M}/change_phone_init_v2", {})
        d4 = j4.get("data") or {}
        row["init_v2"] = j4.get("error")
        row["ivs_required"] = d4.get("ivs_required")
    results.append(row)
    log(f"{f:26s} uid={str(uid):12s} acc={err_acc} init={row.get('init')} "
        f"vm={row.get('verify_method')} ivs_req={row.get('ivs_required')}")
    time.sleep(1.2)

json.dump(results, open("cp_multi.json", "w"), indent=1)

ok = [r for r in results if r.get("verify_method") == 0]
log(f"\n=== {len(ok)}/{len(results)} akun lolos get_password_verify_method ===")
for r in ok:
    log(f"  ✅ {r['file']} uid={r['uid']} phone={r['phone']}")
