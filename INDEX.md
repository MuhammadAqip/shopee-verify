# INDEX — semua dokumen

| Dokumen | Isi |
|---|---|
| [README.md](README.md) | Apa proyek ini, cara pasang, struktur |
| [AGENTS.md](AGENTS.md) | Aturan untuk AI agent yang melanjutkan proyek |
| [docs/DEEP-DIVE.md](docs/DEEP-DIVE.md) | Alur enam langkah, percabangan IVS, state machine |
| [docs/REFERENCE.md](docs/REFERENCE.md) | Endpoint, header, enum, kode error, konfigurasi, timing |
| [docs/STRENGTHS-WEAKNESSES.md](docs/STRENGTHS-WEAKNESSES.md) | Apa yang kuat, apa yang rapuh, dan kenapa |
| [docs/ROADMAP.md](docs/ROADMAP.md) | P0 sampai P3 dengan estimasi |
| [docs/LESSONS.md](docs/LESSONS.md) | Tujuh pelajaran dari debugging yang mahal |
| [docs/ADVICE.md](docs/ADVICE.md) | Skor, tiga penghalang, anti-goals |

## Mulai dari mana

**Kalau kamu baru:** README → DEEP-DIVE → ADVICE.
**Kalau kamu mau mengubah kode:** AGENTS → REFERENCE → LESSONS.
**Kalau kamu mau memutuskan apakah proyek ini layak dilanjutkan:** ADVICE saja.

## Kode

| File | Baris | Isi |
|---|---|---|
| `project/shopee_bot.py` | 2381 | Bot Telegram, state machine, panel admin |
| `project/changenumfast.py` | 542 | Engine HTTP: akun, nomor, OTP, commit |
| `project/ivs_engine.py` | 210 | IVS: methods, select, verify, signature |
| `project/worker.py` | 518 | Worker latar |
| `project/regression.py` | — | 59 cek sebelum deploy |
| `project/reference/` | — | Bundle JS hasil reverse-engineering |
