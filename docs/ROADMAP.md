# Roadmap — yang masih bisa diperbaiki

## P0 — sebelum dipakai serius

**1. Commit tanpa browser** (~2 hari)
Satu-satunya langkah yang masih butuh Chromium. Dugaan: `change_phone_commit_v2` butuh `x-sap-sec` yang valid, dan header itu dihasilkan SDK antifraud yang butuh runtime penuh. Kalau signature-nya bisa direplikasi (`sdkjs/` sudah diekstrak), commit bisa jadi HTTP murni dan throughput naik sepuluh kali.

**2. Health check proxy otomatis** (~3 jam)
Timer yang memanggil `https://api.ipify.org` lewat relay setiap 60 detik. Kalau gagal: restart `socks-relay`, dan kalau tetap gagal setelah 2 menit, kirim notifikasi ke admin. Tanpa ini, satu relay mati membuat bot tampak "semua akun bermasalah".

**3. Uji IVS end-to-end** (~1 hari)
Alur IVS belum pernah berhasil penuh. Butuh akun dengan password Shopee atau ShopeePay aktif. Tanpa tes ini, kode IVS adalah tebakan yang terstruktur.

## P1 — dalam minggu pertama

**4. Rate limit per user** (~3 jam)
Maksimal N cookie per menit per user, dengan backoff. Melindungi IP relay, yang jauh lebih mahal diganti daripada akun.

**5. State persisten** (~4 jam)
Pindahkan `NET_TMP` ke SQLite. Restart tidak memutus sesi, dan bot bisa di-deploy tanpa menunggu semua user selesai.

**6. SadCaptcha terhubung** (~4 jam)
`send_vcode` → `23500101` → selesaikan captcha → ulangi. Saat ini kode error dilaporkan tapi tidak ditindaklanjuti.

## P2 — perbaikan struktural

**7. `bot_db.json` → SQLite** (~4 jam)
Tulis penuh setiap perubahan tidak akan bertahan pada skala. Skema sudah jelas; migrasinya kecil.

**8. Log terstruktur** (~2 jam)
Saat ini log berupa teks bebas. JSON per baris membuat pencarian (`jq 'select(.code==23500158)'`) dan agregasi jauh lebih mudah.

**9. Antrean job** (~1 hari)
Satu worker per akun, bukan thread per request. Membatasi paralelisme secara alami dan membuat pembatalan mungkin.

## P3 — kalau sempat

**10. Dashboard pemakaian** — berapa akun diproses, tingkat keberhasilan, kode error terbanyak.
**11. Metrik timing per langkah** — untuk mendeteksi regresi performa lebih awal.
**12. Dokumentasi enum otomatis** — skrip yang mengekstrak enum dari bundle dan membandingkannya dengan `REFERENCE.md`, sehingga dokumen tidak basi saat Shopee memperbarui kode.
