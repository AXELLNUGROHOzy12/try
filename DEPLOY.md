# Deploy ke Railway

## 1. Push ke GitHub
File `config.json`, `token.json`, `user.json`, dll sudah dibersihkan dari secret
dan di-`.gitignore`. Sekarang aman di-push.

## 2. Set Environment Variables di Railway
Buka project di Railway → tab **Variables** → tambahkan:

| Key | Value |
|-----|-------|
| `GEMINI_API_KEY` | API key Gemini kamu |
| `OPENAI_API_KEY` | API key OpenAI kamu (kalau pakai fitur ChatGPT) |
| `API_KEY` | Key rahasia buat proteksi `/chat` & `/global-ai` — lihat bagian di bawah |

Railway otomatis kasih `PORT` sendiri, tidak perlu di-set manual.

## 3. Deploy
Railway bakal detect `Dockerfile` otomatis dan jalanin `start.sh`
(backend Python + bot WhatsApp jalan bareng dalam satu container).

## 4. Scan ulang QR WhatsApp
Karena filesystem Railway ephemeral (kereset tiap redeploy kalau tanpa volume),
folder `wa_auth/` bakal hilang tiap redeploy → perlu scan QR ulang di `/qr`.
Kalau mau sesi WA persist antar redeploy, tambahkan **Volume** di Railway dan
mount ke `/app/wa_auth`.

## Catatan keamanan
Key Gemini & OpenAI yang lama sempat ketulis plain-text di `config.json`.
Push-nya sudah diblokir GitHub jadi kemungkinan besar belum bocor ke publik,
tapi kalau mau aman total, generate ulang key-nya di masing-masing provider.

## Proteksi API Key untuk /chat

Endpoint `/chat` (dipakai halaman `index.html`) dan `/global-ai` sekarang
wajib header `X-Api-Key` yang cocok, supaya orang lain yang cuma tahu URL
Railway kamu nggak bisa langsung pakai AI-nya (dan boros kuota Gemini/OpenAI).

- Kalau env var `API_KEY` diisi di Railway, itu yang dipakai.
- Kalau tidak diisi, server generate sendiri sekali saat pertama kali
  jalan, dan tampil di **Logs** Railway (`⚠️ API_KEY belum diset — key
  baru digenerate: ...`) serta tersimpan ke `config.json`.
- **Disarankan**: set manual `API_KEY` di tab Variables Railway dengan
  string acak sendiri, biar jelas dan tidak hilang kalau `config.json`
  ke-reset (tidak ada volume untuk file ini).
- Halaman `static/index.html` sekarang akan minta "Kode Akses" sekali di
  awal, simpan di `localStorage` browser, dan otomatis dikirim di setiap
  chat. Kalau salah / kadaluarsa, akan diminta ulang.
- Selain itu ada rate limit 20 request/menit per-IP di `/chat`, berlaku
  walau API key valid — jaga-jaga kalau key ke-share.

### Lihat / ganti API key lewat chat

Kirim pesan berikut ke `/chat` (bisa via halaman web, curl, atau Postman —
**tidak perlu** header `X-Api-Key` untuk command ini, cukup `kode_akses`):

```
/apikey {kode_akses} lihat
/apikey {kode_akses} rotate
```

- `lihat` → menampilkan API key yang aktif sekarang.
- `rotate` → generate API key baru, key lama langsung tidak berlaku.
  **Tidak bisa dipakai kalau env var `API_KEY` diset di Railway** — dalam
  kasus itu, ganti langsung di tab Variables Railway lalu redeploy.

Contoh pakai curl (ganti `KODE_AKSES` dengan isi `kode_akses` di config.json,
dan URL dengan domain Railway kamu):

```bash
curl -X POST https://nova-xxx.up.railway.app/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "/apikey KODE_AKSES rotate"}'
```

Ini juga jalur recovery kalau API key hilang/lupa tapi `kode_akses` masih
diingat.
