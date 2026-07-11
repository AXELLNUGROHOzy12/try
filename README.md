# Nova AI

Backend chatbot AI (`back.py`, Python) + bot WhatsApp (`wa.js`, Node.js/Baileys)
yang jalan bareng dalam satu container. Ada juga halaman chat web
(`static/index.html`) dan dashboard admin (`static/admin.html`).

Untuk panduan deploy lengkap ke Railway (env vars, Dockerfile, dll), lihat
[`DEPLOY.md`](./DEPLOY.md). Dokumen ini fokus ke satu hal yang **wajib**
dibereskan setelah deploy: **Railway Volume**, biar data nggak hilang
tiap kali kamu redeploy.

---

## ⚠️ PENTING: Setup Railway Volume (wajib, sekali di awal)

### Kenapa ini penting

Railway itu **ephemeral filesystem** — tiap kali kamu redeploy (push kode
baru, restart manual, dll), semua file yang ditulis di dalam container
**dihapus** dan container mulai dari image bersih lagi.

Masalahnya, Nova AI nulis beberapa hal penting langsung ke file lokal:

| File / Folder | Isinya | Kalau hilang... |
|---|---|---|
| `config.json` | Nama AI, kepribadian, `kode_akses`, **semua API key** | Semua API key yang udah dibuat lewat `/apikey` atau dashboard ke-reset — server generate key baru & lupa yang lama |
| `user.json` | Akun login (dashboard/admin) | Semua akun yang dibuat lewat `/admin/create` hilang |
| `token.json` | Token sesi admin yang lagi login | Kamu ke-logout paksa |
| `wa_auth/` | Sesi login WhatsApp (Baileys) | **Harus scan ulang QR code** tiap redeploy |
| `seen_users.json` | Daftar nomor yang udah pernah di-chat (buat pesan sambutan) | Semua orang dianggap "baru" lagi, dapet pesan sambutan berulang |
| `self_mode.txt`, `ds_mode.txt` | Setting mode bot | Balik ke default |

Volume di Railway itu **disk permanen** yang nempel ke service kamu dan
**tidak ikut kereset** saat redeploy — solusinya tinggal pasang sekali.

### Langkah-langkah

**1. Tambah Volume di Railway**

- Buka service Nova AI kamu di Railway.
- Tab **Settings** → scroll ke bagian **Volumes** → klik **New Volume**.
- Isi **Mount Path**: `/data`
- Klik **Add**.

**2. Set environment variable `DATA_DIR`**

- Masih di service yang sama, buka tab **Variables**.
- Tambah:
  ```
  DATA_DIR=/data
  ```
- Kode `back.py` dan `wa.js` sudah dibuat baca env var ini — begitu diset,
  semua file di tabel atas otomatis pindah nulis & baca dari `/data`
  (folder yang nempel ke Volume), bukan lagi dari folder project.

**3. Redeploy**

- Railway otomatis redeploy begitu kamu nambah/ubah variable.
- Saat pertama kali jalan dengan `DATA_DIR` baru, `back.py` bakal nyalin
  `config.json` bawaan project ke `/data/config.json` (kalau di `/data`
  belum ada), jadi setting awal kamu (nama AI, kepribadian, dll) tetap
  kebawa, cuma sekarang lokasinya di Volume.

**4. Scan ulang QR WhatsApp (sekali terakhir)**

- Karena ini migrasi pertama kali, sesi WA lama (kalau ada) tetap perlu
  di-scan ulang satu kali di `https://<url-railway-kamu>/qr`.
- **Setelah ini**, redeploy berikutnya-berikutnya **tidak perlu** scan
  ulang lagi, karena `wa_auth/` sudah permanen di Volume.

### Cara mastiin udah bener

1. Buka **Logs** di Railway, cari baris:
   ```
   Backend jalan di port ...
   ```
   Kalau ada baris `⚠️ Belum ada API key — key baru digenerate`, artinya
   `config.json` lama belum ketemu (biasanya normal di migrasi pertama).
2. Bikin API key baru lewat dashboard (`/admin`) atau command `/apikey`.
3. **Redeploy sekali lagi** (misal: ubah 1 variable lain lalu save, atau
   klik **Redeploy** manual dari tab Deployments).
4. Cek lagi — kalau API key yang tadi dibikin masih ada (nggak perlu
   generate baru), berarti Volume-nya udah kerja dengan benar. ✅

### Kalau lupa/skip langkah ini

Nova AI tetap jalan normal sehari-hari — Volume cuma soal *persistence*
antar redeploy. Tapi tiap kali kamu push kode baru atau restart service,
bersiap untuk: scan ulang QR WhatsApp, API key yang lama nggak berlaku
lagi, dan akun dashboard yang dibuat manual hilang.

---

## Fitur lain

- **Proteksi API key per-client** + dashboard admin (`/admin`) — lihat
  detail di [`DEPLOY.md`](./DEPLOY.md#proteksi-api-key-untuk-chat).
- **Command chat admin**: `/ai`, `/add`, `/delete`, `/change`, `/apikey`
  — semua butuh `kode_akses` dari `config.json`.
