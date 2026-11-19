# Reference — endpoint, enum, kode error, konfigurasi

## Endpoint

| Method | Path | Body | Balasan penting |
|---|---|---|---|
| GET | `/api/v4/account/basic/get_account_info` | — | `username`, `phone`, `verified`, `uid` |
| POST | `/api/v4/account/management/change_phone_init_v2` | `{phone, seq_no}` | `change_phone_token`, `ivs_required`, `ivs_utoken` |
| POST | `/api/v4/otp/get_settings_v2` | `{operation, phone, supported_channels, support_session}` | `available_channels`, `need_captcha` |
| POST | `/api/v4/otp/send_vcode` | `{phone, channel, operation, force_channel, supported_channels, seed}` | `otp_tracking_id`, `delivery_channel` |
| POST | `/api/v4/otp/verify_vcode` | `{phone, vcode, operation, m_token}` | `vcode_token` |
| POST | `/api/v4/account/management/change_phone_commit_v2` | `{phone, changePhoneToken, vcodeToken}` | `{"error":0}` — **via webpack only** |
| POST | `/api/v4/anti_fraud/ivs/methods` | `{event, u_token}` | `[{type, v_token}]` |
| POST | `/api/v4/anti_fraud/ivs/method/select` | `{event, u_token, method, v_token}` | `{masked_username, operation_code}` |
| POST | `/api/v4/account/management/verify_password` | `{password, scene}` | `rc_token` |
| POST | `/api/v4/account/management/verify_payment` | `{pin, scene}` | `rc_token` |
| POST | `/api/v4/anti_fraud/ivs/token/verify` | `{method_name, event, u_token, r_token, v_token, misc, security_device_fingerprint}` | `ivs_signature` |

Base: `https://shopee.co.id`

## Header

Request yang berhasil **hanya** memakai ini:

```
User-Agent: <UA mobile Shopee asli>
Accept: application/json
Content-Type: application/json
Accept-Language: id-ID,id;q=0.9,en;q=0.8
Origin: https://shopee.co.id
Referer: https://shopee.co.id/user/account/phone
x-requested-with: XMLHttpRequest
x-api-source: pc
x-shopee-language: id
x-csrftoken: <dari cookie csrftoken>
Cookie: <cookie penuh>
```

**Jangan kirim** `af-ac-enc-dat`, `x-sap-ri`, `x-sap-sec`, `af-ac-enc-sz-token`, `x-sz-sdk-version` kecuali kamu benar-benar menghitungnya. Nilai acak pada header itu membuat server membalas `90309999` untuk semua akun.

## Enum

### Operation

```
0   General / change-phone (DIPAKAI)
1   AccountRegister
2   AccountLogin
8   AccountRegisterWithPhone
18  AccountSetPhone
20  AccountVerifyPhoneReminder
23  AccountChangePhone
24  AccountChangeEmail
25  AccountUpdateBankAccount
29  AccountSetPassword
34  AccountAddEmail
502 IvsChangePhone
```

`operation: 0` adalah nilai asli pada alur change-phone. 23 dan 18 punya counter yang lebih ketat.

### Channel OTP

```
1  SMS
2  Voice
3  WhatsApp   ← paling cepat
```

### IVS method type

```
1   OTP                    8   EMAIL_LINK
2   PASSWORD               10  NEW_SHOPEEPAY_PIN
3   SHOPEEPAY              11  WHATSAPP_LINK
5   AUTH_LINK              14  SECURITY_QUESTIONS
6   EMAIL                  15  SECURITY_EMAIL
7   QR                     20  DEVICE_TOKEN
                           100  SKIP
```

### IVS event

```
2   change-phone (DIPAKAI)
```

String seperti `"AccountChangePhone"` dibalas `211`.

### Captcha

```
ActionType      { Block: 2, Challenge: 3 }
ChallengeType   { Captcha: 1, ForceLogin: 2, Redirect: 5,
                  FORCE_DOWNLOAD_APP: 8, FORCE_BIND_PHONE: 9, VERIFY_PHONE: 10 }
captcha_type    { Animated: 2, Slider: 1|3 }
```

## Kode error

| Kode | Arti | Yang harus dilakukan |
|---|---|---|
| `0` | OK | lanjut |
| `10002` | required param / route salah | cek body; commit harus via webpack |
| `10013` | state tidak sesuai | ulangi dari `init_v2` |
| `19` | Failed to authenticate | cookie mati — ambil baru |
| `211` | event IVS tidak valid | pakai `2`, bukan string |
| `23500000` | kode/nomor tidak cocok | kode salah |
| `23500101` | NEED_CAPTCHA saat send | selesaikan captcha |
| `23500002` | kode dibatalkan (resend) | kirim ulang |
| `23500152` | rate limit | tunggu |
| `23500158` | anti-abuse per akun | tunggu 1–6 jam, atau akun lain |
| `31500000` | token expired / already used | ulangi dari `init_v2` |
| `31500200` | captcha payload kurang | lengkapi payload |
| `31600000` | butuh header x-sap | header SAP wajib untuk endpoint ini |
| `49900000` | param tidak dikenal | cek nama field (`u_token` bukan `ivs_utoken`) |
| `90309999` | TRIGGER_ANTI_CRAWLER | **bukan indikator akun** untuk `order_list`/`cart`; header palsu juga memicunya |
| `12301116` | akun/nomor di-restrict | akun bermasalah |
| `-997` | proxy gagal (internal) | cek relay |

## Konfigurasi

`project/bot.env.example`:

```ini
SHOPEE_BOT_TOKEN=          # token BotFather
ADMIN_ID=                  # telegram user id admin
SHOPEE_MITM=http://127.0.0.1:18080   # proxy keluar — WAJIB
PRICE_PER_CHECK=100
```

Kalau `SHOPEE_MITM` kosong, request keluar dari IP VPS dan akan ditolak.

## Data model

`project/bot_db.json`:

```json
{
  "users": {
    "<telegram_uid>": {
      "saldo": 0,
      "username": "",
      "first_seen": 0,
      "credit_log": [{"ts": 0, "delta": 0, "by": 0, "note": ""}]
    }
  }
}
```

## Bundle JS — peta modul webpack

| ID | Isi |
|---|---|
| `66199` | service module `K` — 19 method, termasuk `changePhoneCommitV2` |
| `7231` | AccountChangePhoneNumberV3 (circular dep, jangan dipakai langsung) |
| `16223` | fraud SDK |
| `66264` | antifraud |
| `68094` | APMS |

Chunk yang harus di-warm sebelum commit: `req.e(8167)`, `req.e(5358)`, `req.e(896)`.

## Timing terukur

| Langkah | Waktu |
|---|---|
| `check_account` | 0.06–0.15 s |
| `check_number` | 0.21–0.29 s |
| `send_vcode` | 0.20 s |
| `verify_vcode` | 0.20 s |
| `commit` | ~13 s (wajib webpack) |
| **total HTTP** | **0.67 s** (tanpa commit) |
| total Playwright | 13.0 s |
