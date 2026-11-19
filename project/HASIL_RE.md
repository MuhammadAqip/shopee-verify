# Flow Ganti Nomor Shopee by Cookie — Status RE

Update terakhir: dari DevTools Maker + tes live dari IP VPS (tanpa proxy).

## Flow lengkap (10 langkah)

| # | Endpoint | Status dari Python |
|---|---|---|
| 1 | `POST /api/v4/account/management/change_phone_init_v2` | ✅ `error:0` |
| 2 | `POST /api/v4/anti_fraud/ivs/methods` | ❌ `49900000` |
| 3 | `POST /api/v4/anti_fraud/ivs/method/select` | ❌ `49900000` |
| 4 | `POST /api/v4/account/management/verify_password` | ✅ `error:0` → `rc_token` |
| 5 | `POST /api/v4/anti_fraud/ivs/token/verify` | ❌ `403 / 90309999` |
| 6 | `POST /api/v4/account/management/change_phone_precheck_v2` | ❌ `10002` (butuh ivs) |
| 7 | `POST /api/v4/otp/get_settings_v2` | ❌ `23500158` (rate limit) |
| 8 | `POST /api/v4/otp/send_vcode` | — |
| 9 | `POST /api/v4/otp/verify_vcode` | — |
| 10 | `POST /api/v4/account/management/change_phone_commit_v2` | butuh `ivs_signature` |

## Bukti pemisahan (sesi sama, IP sama, cookie sama)

```
change_phone_init_v2    -> error 0        ✅ JALAN
verify_password         -> error 10003    (password uji salah — endpoint hidup)
ivs/methods             -> 49900000       ❌ DITOLAK
ivs/token/verify        -> 403 / 90309999 ❌ DITOLAK
otp/get_settings_v2     -> 23500158        (rate limit akun)
```

Kesimpulan: **hanya `/api/v4/anti_fraud/*` yang mewajibkan `x-sap-sec`.**

## Penyebab

`x-sap-sec` (19 byte signature) + kunci `af-ac` di-generate oleh sz-sdk
di dalam bytecode VM (~443 opcode, binary-search dispatch, prefix `vmp_`).
Tidak ada WASM, WebCrypto kosong. Tidak bisa direplikasi dari Python.

Jalan pintas yang terbukti: page-context `fetch()` di halaman Shopee live —
sz-sdk tanda tangan otomatis karena jalan di konteks halaman.

## Yang sudah ada di repo

- `ivs_flow.py` — 10 langkah, semua endpoint terdefinisi
- `sad_client.py` — SadCaptcha client (puzzle solver)
- `captcha_solver.py` — solver berbasis shopee_v6 (terbukti di /root/shopee-farm)
- `api_only_test.py`, `dump_init.py`, `v2_flow.py`, `probe_ivs*.py` — probe

## Pool SadCaptcha

20 key, total 327 kredit. Key terbaik: `6a65a6faee08ae961f05b57bd5789959` (25).
Catatan: solver HANYA menyelesaikan puzzle. Tidak menghasilkan `x-sap-sec`.

## Yang tersisa

Butuh salah satu:
- A. Proxy untuk request halaman saja (API tetap direct)
- B. IP/host lain yang tidak kena flag
- C. Jalankan flow di browser Maker lewat console script
