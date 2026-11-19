# Lessons — pelajaran dari debugging yang mahal

## Header anti-fraud palsu lebih merusak daripada tidak ada header

Kode mengirim `af-ac-enc-dat` (8 byte random hex), `x-sap-ri` (MAC acak), `af-ac-enc-sz-token` (16 byte random), dan `x-sz-sdk-version`. Semuanya dihasilkan acak dengan komentar seolah-olah itu signature.

**Akibatnya:** setiap akun, tanpa kecuali, dibalas `90309999` selama berjam-jam.

**Yang menyesatkan:** `90309999` adalah kode yang sama dengan TRIGGER_ANTI_CRAWLER. Jadi kesimpulannya terlihat jelas — "akun kena flag". Tiga akun berbeda semuanya gagal, yang makin memperkuat kesimpulan salah itu.

**Yang akhirnya membongkar:** membandingkan dengan skrip lama yang **berhasil**. `full_flow.py` tidak mengirim header itu sama sekali. Perbandingan langsung antara dua implementasi lebih cepat daripada sepuluh hipotesis.

**Aturan:** kalau ada dua implementasi dari hal yang sama, dan satu berhasil sementara yang lain gagal, diff keduanya sebelum menyusun teori apa pun.

## Alat diagnostik yang merusak objeknya

`account_health()` memanggil `order_list`, `cart/get`, dan `unbind_check` untuk menentukan apakah akun sehat. `order_list` dan `cart` **selalu** membalas `90309999` untuk request web-PC. Jadi fungsinya melaporkan "limited" untuk setiap akun.

Lebih buruk: versi berikutnya memanggil `get_settings_v2` dua kali per akun. Endpoint itu menaikkan counter anti-abuse. Memeriksa status akun 3 kali berarti 6 request OTP — cukup untuk mengunci akun sehat.

**Aturan:** alat diagnostik tidak boleh memakai endpoint yang punya efek samping tulis atau counter. Kalau memang harus, sebutkan biayanya di nama fungsi.

## Sinyal yang terlihat benar tapi bukan

`90309999` di `order_list` terlihat persis seperti "akun diblok". Kode yang sama, endpoint berat, akun yang sama.

Yang membongkar: akun yang **berhasil** di `get_settings_v2 op23 → 0` tetap dapat `90309999` di `order_list`. Satu endpoint bilang sehat, satu bilang mati. Berarti `order_list` bukan indikator.

**Aturan:** sebelum memakai sebuah sinyal sebagai indikator, buktikan bahwa sinyal itu **berbeda** antara kasus sehat dan kasus gagal. Kalau sama di keduanya, itu bukan indikator.

## Proxy yang gagal diam-diam

Ada tiga lapis kegagalan yang semuanya terlihat sama dari luar:

1. `self.s.proxies` tidak pernah di-set → keluar dari IP VPS → ditolak
2. Proxy di-set ke `:8080` (mitmproxy) → `SSLCertVerificationError` → jatuh ke koneksi langsung → ditolak
3. Env var di-`export` di shell untuk tes, tapi kode tidak membacanya → tes "berhasil" padahal bot produksi tidak

Ketiganya menghasilkan gejala identik: "akun bermasalah".

**Aturan:** verifikasi jalur keluar dengan `api.ipify.org` setiap kali proxy disentuh. Jangan percaya bahwa proxy "sudah dikonfigurasi" hanya karena variabelnya ada.

## Tes dengan modul terpisah bukan tes

`diag_bot.py` mengimpor `shopee_bot` sebagai modul. `NET_TMP` adalah dict di level modul — jadi impor kedua membuat dict **baru dan kosong**. Tes melaporkan "state kosong", padahal bot yang berjalan baik-baik saja.

Menghabiskan satu siklus debug untuk bug yang tidak ada.

**Aturan:** tes state harus berjalan di proses yang sama dengan bot, atau menggunakan representasi state yang eksplisit (kirim state sebagai argumen, jangan baca global).

## Tombol yang tidak merespon hampir selalu soal cabang, bukan handler

`callback_data="adm_cred"` → handler `on_admin` terpanggil → `act = "cred"` → tidak ada satu pun `if act == "cred"` → fungsi selesai tanpa melakukan apa pun.

Tidak ada error. Tidak ada log. Hanya diam.

**Aturan:** setiap `callback_data` baru harus ditambahkan ke cabang handler **dan** ke audit. `audit_callbacks.py` mengecek bahwa setiap string `callback_data` punya handler; itu tidak cukup — perlu juga mengecek bahwa handler punya cabang untuk nilai itu.

## `operation` bukan konstanta yang bisa ditebak

`operation: 23` adalah AccountChangePhone menurut enum. Terlihat benar. Tapi alur change-phone yang sebenarnya memakai `operation: 0`.

23 dan 18 punya counter yang jauh lebih ketat — beberapa panggilan saja dan akun terkunci untuk semua nomor.

**Aturan:** enum yang namanya "terlihat cocok" belum tentu yang dipakai. Cari nilainya di bundle pada pemanggil endpoint yang bersangkutan.

## Health check yang mahal membunuh produk

Rangkaian kejadian: health check memanggil endpoint OTP → counter naik → akun "diblokir" → bot melaporkan diblokir → user mencoba akun lain → counter akun itu naik juga → tiga akun terkunci dalam satu sesi.

Pengguna menyimpulkan "semua cookie saya jelek". Padahal cookie tidak pernah bermasalah; alatnya yang merusak.

**Aturan:** operasi yang dipanggil otomatis (health, pre-check, warm-up) harus nol biaya terhadap kuota. Kalau tidak bisa nol, jangan otomatis.

## Yang paling cepat membongkar bug: membandingkan dengan yang berhasil

Tiga kali dalam proyek ini, jalan keluar datang dari membandingkan kode yang gagal dengan kode yang berhasil — bukan dari membaca dokumentasi, bukan dari menambah hipotesis.

`full_flow.py` berhasil dua kali. `changenumfast.py` gagal terus. Diff keduanya menunjukkan: header berbeda, `operation` berbeda, body berbeda.

**Aturan:** simpan skrip yang berhasil. Jangan hapus. Itu adalah referensi termurah yang akan kamu punya.
