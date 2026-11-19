# AGENTS.md — konteks untuk AI agent

Kamu melanjutkan proyek bot Telegram yang mengganti nomor Shopee lewat HTTP murni. Baca ini sebelum menyentuh kode.

## Aturan yang tidak boleh dilanggar

**1. Sumber kebenaran adalah bundle JS di `project/reference/`, bukan tebakan.**
Kalau sebuah request gagal, jangan coba-coba ubah body sampai berhasil. Cari pemanggilnya di bundle dulu: `grep -rn 'nama/endpoint' project/reference/ivs_js/`. Bundle itu berisi kode asli Shopee — urutan parameter, header, dan enum di sana adalah kebenaran.

**2. Jangan kirim header anti-fraud palsu.**
`af-ac-enc-dat`, `x-sap-ri`, `x-sap-sec`, `af-ac-enc-sz-token` harus berupa hasil enkripsi/signature yang valid. Mengirim nilai acak membuat **semua** akun dibalas `90309999` — dan itu terlihat persis seperti "akun kena flag", padahal bukan. Request yang benar tidak mengirim header itu sama sekali.

**3. `get_settings_v2` menaikkan counter anti-abuse.**
Jangan panggil untuk sekadar cek status akun. Setiap panggilan menambah counter per akun; beberapa kali dalam satu jam dan akun itu akan membalas `23500158` untuk semua nomor, termasuk nomor yang belum pernah dipakai. Untuk cek status, cukup `get_account_info` + `change_phone_init_v2`.

**4. `90309999` di `order_list` / `cart` bukan indikator flag.**
Endpoint itu membalas `90309999` untuk hampir semua request web-PC. Memakainya sebagai sinyal kesehatan menghasilkan false positive di setiap akun. Satu-satunya sinyal valid adalah `get_settings_v2` (dan hanya kalau kamu memang siap memakai counter-nya).

**5. Proxy wajib dipakai, dan wajib benar-benar tersambung.**
`Api.__init__` harus men-set `self.s.proxies`. Kalau proxy gagal, tandai error (`-997`) — jangan diam-diam jatuh ke koneksi langsung. Request langsung dari IP datacenter akan ditolak, dan kegagalannya terlihat seperti masalah akun.

**6. `operation` untuk change-phone adalah `0`.**
Bukan 23, bukan 18. Angka 23/18 adalah operation OTP yang berbeda dan punya perilaku counter yang lebih ketat.

## Di mana harus melihat

| Pertanyaan | Lihat |
|---|---|
| Endpoint apa yang dipakai? | `project/changenumfast.py`, `project/ivs_engine.py` |
| Urutan langkah lengkap? | `docs/DEEP-DIVE.md` |
| Enum, kode error, body | `docs/REFERENCE.md` |
| Kenapa kode ini begitu? | `docs/LESSONS.md` |
| Apa yang belum selesai? | `docs/ROADMAP.md` |

## Cara mengubah dengan aman

```bash
# 1. patch idempotent — selalu cek MARK sebelum menulis
grep -c 'NAMA_PATCH' project/shopee_bot.py   # kalau > 0, sudah terpasang
# 2. backup sebelum menulis
cp project/shopee_bot.py project/shopee_bot.py.bak$(date +%s)
# 3. verifikasi syntax setelah patch
python3 -c 'import ast;ast.parse(open("project/shopee_bot.py").read())'
# 4. jalankan regression — 59 cek
python3 project/regression.py
```

Jangan pernah men-deploy tanpa `regression.py` lulus. Skrip itu mengecek handler terdaftar, callback punya cabang, health check tidak memanggil endpoint terlarang, dan log bebas traceback.

## Jebakan yang sudah dibayar mahal

- `diag_bot.py` mengimpor `shopee_bot` sebagai modul terpisah → `NET_TMP` adalah instance berbeda dari bot yang berjalan → state selalu kosong → **tes tidak valid**, bukan bug.
- Tombol inline yang "tidak merespon" hampir selalu berarti `callback_data` cocok ke handler tapi tidak cocok ke satu pun `if act == ...`. Audit dengan `audit_callbacks.py`.
- `request_otp` mengembalikan `op` yang dipakai; `verify_vcode` **harus** memakai `op` yang sama. Kalau tidak, kode valid akan ditolak.
- Field verifikasi OTP bernama `vcode`, bukan `code`. Field token verifikasi bernama `vcode_token`, dan dikirim sebagai query param pada commit.
- Commit butuh service runtime webpack (`req.e(8167)`, `req.e(5358)`, `req.e(896)`, lalu `req(66199).K.changePhoneCommitV2`). Memanggil endpoint HTTP langsung menghasilkan `10002`.
