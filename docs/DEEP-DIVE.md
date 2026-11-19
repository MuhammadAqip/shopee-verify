# Deep Dive — bagaimana bot ini benar-benar bekerja

## Masalah yang diselesaikan

Mengganti nomor HP di Shopee sebenarnya adalah alur enam langkah di web app mereka. Seseorang membuka halaman akun, klik "ganti nomor", memasukkan nomor baru, menunggu OTP, memasukkan kode, selesai. Di bawahnya, enam request HTTP berurutan dengan state yang saling bergantung.

Bot ini menjalankan keenam langkah itu tanpa membuka browser. Bukan dengan menyimulasikan klik, tapi dengan memanggil endpoint yang sama, dengan body yang sama, dengan header yang sama.

Hasil terukur: alur penuh **0.67 detik** lewat HTTP vs **13.0 detik** lewat Playwright. Sembilan belas kali lebih cepat, dan tidak butuh RAM untuk Chromium.

## Kenapa browser tidak dipakai

Playwright bekerja, tapi mahal: 13 detik per akun, ~400 MB RSS, dan setiap instance butuh profil terpisah. Untuk bot Telegram yang harus melayani banyak permintaan, itu tidak layak.

Yang lebih penting: browser menyembunyikan alur. Kalau ada yang gagal, kamu hanya melihat "timeout". Dengan HTTP langsung, kamu melihat `23500158` dan bisa tahu persis apa artinya.

## Alur lengkap

```
                    ┌──────────────────────────┐
   cookie masuk  →  │ 1. get_account_info      │  username, phone, verified
                    └──────────────────────────┘
                                 │
                    ┌──────────────────────────┐
                    │ 2. change_phone_init_v2  │  change_phone_token (236B)
                    └──────────────────────────┘  ivs_required? → cabang IVS
                                 │
                    ┌──────────────────────────┐
                    │ 3. get_settings_v2 op=0  │  channel OTP tersedia
                    └──────────────────────────┘  need_captcha?
                                 │
                    ┌──────────────────────────┐
                    │ 4. send_vcode            │  otp_tracking_id
                    └──────────────────────────┘  delivery_channel
                                 │
                    ┌──────────────────────────┐
                    │ 5. verify_vcode          │  vcode_token (~236B)
                    └──────────────────────────┘
                                 │
                    ┌──────────────────────────┐
                    │ 6. change_phone_commit_v2│  {"error":0}
                    └──────────────────────────┘  nomor berganti
```

### Langkah 1 — cek akun

`GET /api/v4/account/basic/get_account_info` dengan cookie. Membalas username, nomor terdaftar, dan status verifikasi. Ini satu-satunya panggilan yang aman diulang berkali-kali; tidak ada counter.

### Langkah 2 — init

`POST /api/v4/account/management/change_phone_init_v2` dengan `{phone, seq_no: null}`.

Membalas `change_phone_token` (236 byte normal). Kalau akun butuh verifikasi identitas, tokennya membesar ke 804 byte dan ada field `ivs_required: true` plus `ivs_utoken` 448 byte.

**Di sinilah percabangan IVS terjadi.**

### Langkah 3 — settings

`POST /api/v4/otp/get_settings_v2` dengan:

```json
{"operation": 0, "phone": "628xxx",
 "supported_channels": [1, 2, 3], "support_session": false}
```

Membalas `available_channels` (1=SMS, 2=Voice, 3=WhatsApp) dan `need_captcha`.

`operation: 0` adalah nilai asli untuk alur change-phone. Nilai 23 dan 18 adalah operasi OTP lain yang counter anti-abuse-nya jauh lebih ketat — memakai keduanya untuk change-phone membuat akun cepat terkunci.

### Langkah 4 — kirim OTP

`POST /api/v4/otp/send_vcode`:

```json
{"phone": "628xxx", "channel": 3, "operation": 0,
 "force_channel": false, "supported_channels": [1, 2, 3], "seed": "<dari langkah 3>"}
```

`channel` 3 = WhatsApp, yang paling cepat sampai. Membalas `otp_tracking_id`.

### Langkah 5 — verifikasi

`POST /api/v4/otp/verify_vcode`:

```json
{"phone": "628xxx", "vcode": "618344",
 "operation": 0, "m_token": "<change_phone_token>"}
```

Perhatikan: field kodenya **`vcode`**, bukan `code`. `operation` **harus sama** dengan yang dipakai di langkah 4, kalau tidak kode yang benar akan ditolak.

Membalas `vcode_token`.

### Langkah 6 — commit

Ini satu-satunya langkah yang tidak bisa lewat HTTP biasa. Commit harus dipanggil lewat service runtime webpack:

```javascript
// warm up
req.e(8167); req.e(5358); req.e(896);

// commit
req(66199).K.changePhoneCommitV2({
  phone: "628xxx",
  changePhoneToken: "<change_phone_token>",
  vcodeToken: "<vcode_token>"
});
// → {"error":0,"data":{"is_delayed":false}}
```

`ivsSignature`, `ivsMethod`, dan `operation` tidak wajib di body ini. Memanggil endpoint HTTP langsung menghasilkan `10002` (required param).

## Percabangan IVS

Kalau `ivs_required: true`, akun minta verifikasi identitas sebelum nomor bisa diganti. Metodenya **tidak bisa ditebak** — harus ditanyakan:

```
POST /api/v4/anti_fraud/ivs/methods
{"event": 2, "u_token": "<ivs_utoken>"}
→ [{"type": 8, "v_token": "..."}]
```

`event: 2` adalah enum untuk change-phone. Nilai string seperti `"AccountChangePhone"` dibalas `211`.

`type` yang mungkin muncul:

| type | nama | syarat muncul |
|---|---|---|
| 1 | OTP | selalu |
| 2 | PASSWORD | akun sudah set password Shopee |
| 3 | SHOPEEPAY | akun punya ShopeePay |
| 8 | EMAIL_LINK | akun punya email terverifikasi |
| 10 | NEW_SHOPEEPAY_PIN | akun punya PIN ShopeePay |
| 14 | SECURITY_QUESTIONS | akun set pertanyaan keamanan |

**Method yang muncul hanya yang benar-benar dimiliki akun.** Akun yang belum pernah set password tidak akan pernah menawarkan `PASSWORD`, sekuat apa pun kamu mencarinya.

Alur setelah pilih method:

```
POST /anti_fraud/ivs/method/select
{"event": 2, "u_token": U, "method": T, "v_token": V}     → err 0

POST /account/management/verify_password
{"password": "sha256(md5(pw).hexdigest())"}                → rc_token
   atau
POST /account/management/verify_payment
{"pin": "123456"}                                          → rc_token

POST /anti_fraud/ivs/token/verify
{"method_name": T, "event": 2, "u_token": U,
 "r_token": rc_token, "v_token": V,
 "misc": {"operation": 0},
 "security_device_fingerprint": FP}                        → ivs_signature
```

`ivs_signature` lalu dimasukkan ke commit.

## Proxy — komponen yang paling mudah salah

Bot berjalan di VPS datacenter. Shopee menolak request yang datang langsung dari IP seperti itu. Semua request harus keluar lewat proxy residensial Indonesia.

Dua kesalahan yang pernah terjadi dan akibatnya:

**1. Proxy tidak di-set di session.** `Api.__init__` membuat `requests.Session()` tapi tidak mengisi `self.s.proxies`. Hasilnya: semua request keluar dari IP VPS, dan setiap akun dibalas penolakan. Terlihat seperti masalah cookie.

**2. Proxy di-set tapi gagal, lalu diam-diam fallback.** Mitmproxy di `:8080` meng-intercept TLS dengan sertifikat sendiri; `requests` menolaknya dengan `SSLCertVerificationError`. Kalau error itu diabaikan, request jatuh ke koneksi langsung — sama hasilnya dengan kasus pertama, tapi lebih sulit didiagnosis.

Yang benar: pakai relay SOCKS (`:18080`) yang meneruskan koneksi tanpa membongkar TLS, dan **tandai error sebagai error** (`-997`) alih-alih fallback.

Verifikasi selalu dengan:

```python
print(api.get("https://api.ipify.org"))   # harus IP Indonesia, bukan IP VPS
```

## Health check — kenapa harus murah

Cek status akun secara naif berarti memanggil endpoint OTP. Itu mahal: setiap panggilan menambah counter anti-abuse per akun. Bot yang memanggil dua kali setiap cookie masuk akan membuat akun sehat terlihat terkunci setelah beberapa kali pemakaian.

`cn_health()` karena itu hanya memakai dua sinyal murah:

```
get_account_info           → cookie hidup atau mati
change_phone_init_v2       → ivs_required?
```

Nol panggilan ke `get_settings_v2`. Status `ok` / `ivs` / `dead` ditentukan dari dua panggilan itu. `limited` hanya dipakai kalau `init_v2` sendiri menolak.

## State machine bot

```
chg_cookie → chg_ivsm? → chg_ivs_pw / chg_ivs_pin / chg_ivs_code
                       → chg_phone → chg_chan → chg_otp → selesai
```

State disimpan di `NET_TMP[uid]` sebagai `{"step": ..., "chg": {...}, "msg": pesan}`. Satu pesan Telegram dipakai ulang sepanjang alur — setiap transisi meng-edit pesan itu, bukan mengirim yang baru. Hanya kartu akun awal yang dikirim sebagai pesan baru, karena pada titik itu alur belum dimulai.
