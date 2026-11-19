# ADVICE — baca ini sebelum melanjutkan

## Skor

| Aspek | Nilai | Alasan |
|---|---|---|
| Pengetahuan terdokumentasi | 9 | Bundle JS tersimpan, peta modul lengkap, tiap endpoint punya sumber |
| Kualitas kode engine | 7 | `changenumfast.py` dan `ivs_engine.py` bersih dan terpisah dari UI |
| Ketahanan operasional | 4 | Satu relay mati = seluruh bot gagal; tidak ada health check otomatis |
| Kelengkapan fitur | 6 | 5 dari 6 langkah tanpa browser; commit masih butuh Chromium; IVS belum terbukti |
| Kualitas UI bot | 7 | Satu pesan diedit sepanjang alur, tombol inline lengkap, pesan error spesifik |
| Test coverage | 4 | 59 cek regresi, tapi nol untuk IVS dan commit |
| Keamanan kredensial | 5 | Sudah di-scrub, tapi `bot_db.json` plaintext dan tidak ada enkripsi state |
| **Rata-rata** | **6.0** | |

Jujur: ini proyek dengan pengetahuan yang bagus dan infrastruktur yang rapuh.

## Tiga penghalang utama

**1. Commit masih butuh browser.**
Seluruh nilai "HTTP murni" hilang di langkah terakhir. Enam langkah pertama selesai dalam 0.67 detik, lalu commit memakan 13 detik dan satu instance Chromium. Artinya throughput bot dibatasi Chromium, bukan oleh jaringan.
Konsekuensi konkret: pada VPS 4 GB, maksimal 3–4 commit paralel sebelum kehabisan memori. Kalau targetnya lebih dari itu, arsitekturnya harus berubah.
Estimasi: 2 hari untuk mencoba mereplikasi `x-sap-sec` dari `sdkjs/`.

**2. Relay proxy adalah single point of failure.**
`socks-relay` mati → semua request keluar dari IP VPS → semua akun ditolak → bot melaporkan "akun bermasalah" → user mencoba akun lain → counter naik di akun-akun itu juga. Satu proses mati berubah menjadi kerusakan data yang tidak bisa dibatalkan.
Konsekuensi konkret: kegagalan 30 detik pada relay bisa membuat tiga akun pengguna terkunci selama berjam-jam.
Estimasi: 3 jam untuk watchdog + notifikasi admin.

**3. IVS belum pernah berhasil end-to-end.**
Seluruh `ivs_engine.py` — `verify_password`, `verify_payment`, `token_verify` — ditulis berdasarkan pembacaan bundle, bukan dari eksekusi yang berhasil. Belum ada satu pun akun uji yang menawarkan metode PASSWORD atau PIN.
Konsekuensi konkret: kalau ada pengguna dengan akun berpassword, alur ini akan gagal dan tidak ada yang tahu di langkah mana sampai ada yang mencoba.
Estimasi: 1 hari, tapi **butuh akun dengan password Shopee atau ShopeePay aktif**. Tanpa akun itu, pekerjaan ini tidak bisa dimulai.

## Prioritas

**P0 — lakukan sekarang**
1. Watchdog relay (3 jam). Ini melindungi data pengguna secara langsung.
2. Uji IVS dengan akun berpassword (1 hari, butuh akun).
3. Commit tanpa browser (2 hari).

**P1 — minggu ini**
4. Rate limit per user (3 jam).
5. State ke SQLite (4 jam).
6. SadCaptcha terhubung (4 jam).

**P2 — bulan ini**
7. `bot_db.json` → SQLite.
8. Log terstruktur JSON.
9. Antrean job per akun.

**P3 — kalau sempat**
10. Dashboard.
11. Metrik timing.
12. Ekstraksi enum otomatis dari bundle.

## Anti-goals — jangan lakukan ini

**Jangan menambah fitur baru sebelum watchdog relay ada.**
Menambah fitur di atas infrastruktur yang bisa mati diam-diam berarti menambah permukaan kerusakan. Setiap fitur baru adalah satu cara lagi untuk merusak akun pengguna ketika relay mati.

**Jangan mengganti `requests` dengan `httpx` atau `aiohttp`.**
Terlihat seperti modernisasi, sebenarnya risiko. `requests` dengan `Session` sudah memberi connection pooling, dan TLS fingerprint-nya sudah terbukti diterima. Mengganti library HTTP berarti mengubah fingerprint TLS, yang bisa memicu penolakan baru di endpoint yang saat ini bekerja. Ini bukan optimasi; ini mengganti satu variabel yang sudah stabil.

**Jangan menambah retry otomatis pada `get_settings_v2`.**
Endpoint itu punya counter. Retry otomatis mengubah satu kegagalan sementara menjadi tiga panggilan, dan tiga panggilan bisa mengunci akun. Kalau gagal, laporkan.

**Jangan memecah `changenumfast.py` menjadi banyak modul.**
441 baris, satu tanggung jawab, semua fungsi saling berkaitan lewat konstanta bersama (`OP`, `OP_CHAIN`, `CHANNEL_NAME`). Memecahnya akan membuat konstanta itu perlu diimpor silang dan menambah jalur impor melingkar. Ukurannya bukan masalah; keterkaitannya adalah alasan modul ini koheren.

**Jangan menambahkan framework web atau database ORM.**
Bot ini satu proses, satu file database, belasan pengguna. Setiap lapisan tambahan adalah tempat bug baru bersembunyi, dan tidak ada masalah yang sedang dipecahkan oleh lapisan itu.

**Jangan menyimpan cookie di log, bahkan terpotong.**
Cookie Shopee adalah kredensial penuh. Potongan 8 karakter pertama sudah cukup untuk mengidentifikasi akun di log yang mungkin dibagikan saat debugging. Log hanya boleh menyebut username, bukan cookie.

## Satu kalimat

Proyek ini tahu lebih banyak daripada yang bisa ia lakukan dengan andal — perbaiki relay dan buktikan IVS sebelum menambah apa pun yang baru.
