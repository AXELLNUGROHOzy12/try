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
| `DATA_DIR` | `/data` — wajib diisi setelah pasang Volume (lihat langkah 4) |

Railway otomatis kasih `PORT` sendiri, tidak perlu di-set manual.

## 3. Deploy
Railway bakal detect `Dockerfile` otomatis dan jalanin `start.sh`
(backend Python + bot WhatsApp jalan bareng dalam satu container).

## 4. Pasang Volume (wajib — biar data tidak reset tiap redeploy)
Railway filesystem ephemeral: `config.json` (termasuk semua API key),
`user.json`, `token.json`, sesi WhatsApp (`wa_auth/`), dan beberapa file
lain kereset tiap redeploy kalau tanpa Volume. Lihat panduan lengkap
step-by-step di [`README.md`](./README.md#️-penting-setup-railway-volume-wajib-sekali-di-awal)
— intinya: buat Volume dengan mount path `/data`, lalu set env var
`DATA_DIR=/data`.

## Catatan keamanan
Key Gemini & OpenAI yang lama sempat ketulis plain-text di `config.json`.
Push-nya sudah diblokir GitHub jadi kemungkinan besar belum bocor ke publik,
tapi kalau mau aman total, generate ulang key-nya di masing-masing provider.

## Proteksi API Key untuk /chat

Endpoint `/chat` (dipakai halaman `index.html`) dan `/global-ai` sekarang
wajib header `X-Api-Key` yang cocok, supaya orang lain yang cuma tahu URL
Railway kamu nggak bisa langsung pakai AI-nya (dan boros kuota Gemini/OpenAI).

- Kalau env var `API_KEY` diisi di Railway, itu jadi "master key" (nama
  tampilan `env-master`) — dipakai `wa.js` buat manggil `/chat`
  server-ke-server, dan tetap berlaku walau `config.json` ke-reset.
- Selain itu, tiap client (web widget, script Python, dll) bisa punya
  API key sendiri-sendiri, disimpan di `config.json["api_keys"]` dengan
  nama masing-masing + hitungan pemakaian. Kalau belum ada key sama
  sekali dan `API_KEY` juga tidak diset, server generate satu otomatis
  saat pertama kali jalan (cek **Logs** Railway).
- Halaman `static/index.html` akan minta "Kode Akses" sekali di awal,
  simpan di `localStorage` browser, dan otomatis dikirim di setiap chat.
  Kalau salah / dicabut, akan diminta ulang.
- Selain itu ada rate limit 20 request/menit per-IP di `/chat`, berlaku
  walau API key valid — jaga-jaga kalau key ke-share.

### Kelola API key

Dua cara: lewat **dashboard web** (`/admin`, lihat bagian di bawah) atau
lewat **chat** — kirim pesan berikut ke `/chat` (tidak perlu header
`X-Api-Key`, cukup `kode_akses`):

```
/apikey {kode_akses} list
/apikey {kode_akses} new {nama}
/apikey {kode_akses} revoke {nama}
```

- `list` → semua key aktif + berapa kali dipakai + terakhir dipakai kapan.
- `new {nama}` → bikin key baru buat client tertentu, misal
  `/apikey SXIELD1 new whatsapp-bot`.
- `revoke {nama}` → cabut satu key spesifik, tanpa ganggu key lain.

Contoh pakai curl (ganti `KODE_AKSES` dan URL Railway kamu):

```bash
curl -X POST https://nova-xxx.up.railway.app/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "/apikey KODE_AKSES list"}'
```

Ini juga jalur recovery kalau semua API key hilang tapi `kode_akses`
masih diingat.

## Dashboard Admin (`/admin`)

Buka `https://nova-xxx.up.railway.app/admin` di browser — halaman ini
minta `kode_akses` sekali (disimpan di sessionStorage, hilang kalau tab
ditutup), lalu nampilin:

- **Status** — nama AI, global AI aktif, total user, total API key.
- **API Keys** — daftar key + pemakaian, bisa bikin key baru per client
  atau cabut satu-satu, tanpa perlu ketik command chat.
- **Users** — daftar akun login (dari `/login`), bisa tambah/hapus.

Ini setara dengan command `/apikey`, `/admin/list`, `/admin/create`,
`/admin/delete` yang sudah ada, cuma lebih enak dipakai dari HP.
