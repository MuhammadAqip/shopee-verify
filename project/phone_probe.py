# -*- coding: utf-8 -*-
"""
phone_probe.py — probe endpoint change_phone Shopee langsung (read-only dulu).

Recon-only. Tidak mengubah nomor. Hanya memanggil precheck/init untuk melihat
shape respons, kode error, dan header yang diperlukan.
"""
import json
import sys

import requests

SHOPEE = "https://shopee.co.id"

UA = ("Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36")


def build_session(cookie: str) -> requests.Session:
    s = requests.Session()
    s.verify = False
    s.headers.update({
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
        "Origin": SHOPEE,
        "Referer": SHOPEE + "/user/account/phone",
        "x-api-source": "pc",
        "x-requested-with": "XMLHttpRequest",
        "x-shopee-language": "id",
        "Content-Type": "application/json",
        "af-ac-enc-dat": "null",
    })
    # cookie harus domain .shopee.co.id
    jar = {}
    for seg in cookie.split(";"):
        seg = seg.strip()
        if not seg or "=" not in seg:
            continue
        k, v = seg.split("=", 1)
        jar[k.strip()] = v
    s.cookies.update(jar)
    csrf = jar.get("csrftoken")
    if csrf:
        s.headers["x-csrftoken"] = csrf
    return s


def post(s: requests.Session, path: str, body: dict, label: str) -> dict:
    url = SHOPEE + path
    try:
        r = s.post(url, json=body, timeout=30)
    except Exception as e:
        print(f"  [{label}] EXC {e.__class__.__name__}: {e}")
        return {"_exc": str(e)}
    ct = r.headers.get("content-type", "")
    print(f"  [{label}] HTTP {r.status_code} len={len(r.content)} ct={ct[:40]}")
    if not r.content:
        print("        -> BODY KOSONG = soft-block / signature missing")
        return {"_empty": True, "status": r.status_code}
    try:
        j = r.json()
    except Exception:
        print(f"        -> non-json: {r.text[:200]}")
        return {"_raw": r.text[:400]}
    print("        " + json.dumps(j, ensure_ascii=False)[:400])
    return j


def get(s: requests.Session, path: str, label: str) -> dict:
    url = SHOPEE + path
    try:
        r = s.get(url, timeout=30)
    except Exception as e:
        print(f"  [{label}] EXC {e}")
        return {"_exc": str(e)}
    print(f"  [{label}] HTTP {r.status_code} len={len(r.content)}")
    if not r.content:
        print("        -> BODY KOSONG")
        return {"_empty": True, "status": r.status_code}
    try:
        j = r.json()
    except Exception:
        print(f"        -> non-json: {r.text[:200]}")
        return {}
    print("        " + json.dumps(j, ensure_ascii=False)[:400])
    return j


def main() -> None:
    cookie_file = sys.argv[1] if len(sys.argv) > 1 else "/root/.ck_probe"
    with open(cookie_file) as f:
        cookie = f.read().strip()
    new_phone = sys.argv[2] if len(sys.argv) > 2 else "6281234567890"

    s = build_session(cookie)
    print(f"cookie keys: {sorted(s.cookies.keys())[:12]}")

    # 0. warmup + validity
    print("\n[0] warmup")
    try:
        r = s.get(SHOPEE, timeout=30)
        print(f"  home HTTP {r.status_code} len={len(r.content)}")
    except Exception as e:
        print(f"  home EXC {e}")

    print("\n[1] get_account_info (validity)")
    get(s, "/api/v4/account/basic/get_account_info", "account_info")

    print("\n[2] get_phone_validation_list")
    get(s, "/api/v4/account/basic/get_phone_validation_list", "phone_validation")

    print("\n[3] change_phone_init_v2 (ambil token)")
    init = post(s, "/api/v4/account/management/change_phone_init_v2", {}, "change_init_v2")
    token = None
    if isinstance(init, dict):
        data = init.get("data") if isinstance(init.get("data"), dict) else init
        token = data.get("change_phone_token") or data.get("token")
    print(f"  change_phone_token: {str(token)[:40] if token else None}")

    print("\n[4] check_phone_exist (read-only, nomor baru)")
    post(s, "/api/v4/account/basic/check_phone_exist",
         {"phone": new_phone}, "check_exist")

    print("\n[5] change_phone_precheck_v2")
    post(s, "/api/v4/account/management/change_phone_precheck_v2",
         {"phone": new_phone}, "precheck_v2")

    print("\n[6] get_linked_accounts")
    get(s, "/api/v4/account/get_linked_accounts", "linked")

    print("\n[7] check_unbind_phone")
    post(s, "/api/v4/account/management/check_unbind_phone",
         {"phone": new_phone}, "unbind_check")


if __name__ == "__main__":
    main()
