# Kekuatan dan Kelemahan

## Kuat

**Kecepatan.** Alur penuh lewat HTTP 0.67 detik. Playwright 13 detik. Untuk bot yang melayani banyak permintaan, selisih ini menentukan apakah satu VPS 4 GB cukup atau tidak. HTTP murni juga menghapus seluruh beban Chromium dari memori.

**Setiap keputusan bisa ditelusuri ke kode Shopee.** Folder `project/reference/` menyimpan hasil ekstraksi bundle. Kalau ada yang bertanya "kenapa `event` harus 2?", jawabannya ada di `ivs_js/027.js`, bukan dalam dugaan. Ini membuat perbaikan berikutnya jauh lebih cepat: cari pemanggilnya di bundle, tiru persis.

**Pemisahan engine dari UI.** `changenumfast.py` dan `ivs_engine.py` tidak tahu apa-apa tentang Telegram. Keduanya bisa dipanggil dari CLI, dari skrip batch, atau dari bot lain. UI hanya mengatur state dan render. Ini terbukti berguna berkali-kali: bug yang sama bisa direproduksi di terminal tanpa mengetuk bot.

**Deteksi error spesifik.** Tiap kode error Shopee dipetakan ke pesan yang menjelaskan penyebab sebenarnya. `23500158` bukan "nomor diblokir" tapi "counter OTP akun penuh" — beda arti, beda tindakan.

**Health check gratis.** `cn_health()` tidak memakai endpoint OTP sama sekali, jadi memeriksa akun tidak memperburuk keadaannya. Ini penting karena alat diagnostik yang merusak objek yang didiagnosis adalah kegagalan desain, bukan bug kecil.

**Panel admin dengan audit.** Kredit bisa ditambah/dikurangi, termasuk nilai negatif yang di-clamp ke nol, dan setiap perubahan tercatat dengan pelaku dan waktu.

## Lemah

**Ketergantungan pada proxy yang sehat.** Tanpa proxy residensial Indonesia, semuanya gagal — dan gagalnya terlihat seperti masalah akun. Relay punya single point of failure: proses `socks-relay` mati berarti seluruh bot mati secara fungsional. Saat ini tidak ada health check otomatis yang me-restart atau mengalihkan ke rute cadangan.

**Commit masih butuh browser.** Langkah terakhir memerlukan service runtime webpack. Artinya enam langkah pertama bisa jalan tanpa Chromium, tapi langkah terakhir tidak. Ini membatasi throughput ke kecepatan satu instance browser, dan sampai saat ini belum ada yang berhasil memanggil `change_phone_commit_v2` lewat HTTP biasa (`10002`).

**Tidak ada batas laju di sisi bot.** Kalau satu user mengirim lima cookie dalam satu menit, bot memproses kelimanya. Counter anti-abuse Shopee per akun tidak akan terpengaruh (akun berbeda), tapi IP relay akan kena. Tidak ada queue, tidak ada backoff.

**State di memori.** `NET_TMP` hilang saat restart. User yang sedang di tengah alur harus mulai dari awal. Untuk bot yang di-restart untuk deploy, ini berarti semua sesi aktif putus.

**`bot_db.json` bukan database.** Ditulis penuh setiap perubahan. Dua thread yang menulis bersamaan bisa saling menimpa. Untuk belasan user ini tidak masalah; untuk ratusan, ini akan kehilangan data.

**Tidak ada test untuk IVS.** `regression.py` menguji 59 hal, tapi tidak satu pun menyentuh `verify_password` / `verify_payment` / `ivs_signature`, karena tidak ada akun uji yang menawarkan metode itu. Alur IVS saat ini **belum pernah berhasil end-to-end**.

**Deteksi IVS bergantung pada satu field.** `ivs_required` dibaca dari `init_v2`. Kalau Shopee mengubah cara menandai akun yang butuh verifikasi, bot akan menganggapnya akun normal dan gagal di langkah berikutnya dengan pesan yang menyesatkan.

**Tidak ada penanganan captcha.** SadCaptcha terpasang tapi tidak terhubung ke alur. Kalau `send_vcode` membalas `23500101`, bot hanya melaporkannya.

## Keseimbangan

Kekuatan terbesar proyek ini adalah **pengetahuan, bukan kode**. Pengetahuan itu terdokumentasi di `reference/` dan di dokumen ini. Kode bisa ditulis ulang dalam sehari oleh siapa pun yang punya dokumen itu; tanpa dokumen itu, kode ini tidak berarti apa-apa. Karena itu prioritas perbaikan berikutnya bukan menambah fitur, tapi memastikan pengetahuan itu tidak hilang dan memperbaiki tiga hal yang secara struktural rapuh: proxy, commit, dan IVS.
