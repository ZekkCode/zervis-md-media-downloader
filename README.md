# zervis-md-media-downloader

Bot Telegram buat auto-download media dari X/Twitter, TikTok, YouTube, Facebook, dan Instagram. Link yang dikirim ke grup/topik bakal dideteksi, didownload, lalu dikirim balik ke topik yang sama. Dilengkapi web control panel buat atur cookie & lihat status.

Dibuat oleh [zekkcode](https://github.com/zekkcode).

> [!IMPORTANT]
> **Tiga Hal Penting Sebelum Memulai:**
> 1. **Harus Membuat Bot Telegram:** Anda wajib membuat bot Telegram terlebih dahulu via [@BotFather](https://t.me/BotFather) untuk mendapatkan `TELEGRAM_BOT_TOKEN`. Tanpa token ini, program tidak akan berfungsi.
> 2. **Cookies HANYA Dibutuhkan untuk Media Privat:** Untuk mendownload media publik dari X, TikTok, dll., bot ini **langsung bekerja tanpa cookie**. Anda hanya perlu memasang cookie jika ingin mendownload konten privat, restricted, atau berbatas usia (age-gated).
> 3. **Cukup Jalankan Perintah Supervisor:** Untuk sehari-hari, Anda **hanya perlu menjalankan `supervisor.sh`** (atau Docker Compose jika menggunakan VPS). Supervisor akan otomatis menyalakan, memantau, dan menjaga agar proses Bot dan Worker tetap hidup secara bersamaan. Jangan menjalankan script bot atau worker secara terpisah secara manual.

---

## Daftar Isi

- [Arsitektur Singkat](#arsitektur-singkat)
- [Cara Menyalakan](#cara-menyalakan)
- [Command Bot di Telegram](#command-bot-di-telegram)
- [Cara Dapetin & Pasang Cookie](#cara-dapetin--pasang-cookie)
- [Web Control Panel](#web-control-panel)
- [Konfigurasi (.env)](#konfigurasi-env)
- [Troubleshooting](#troubleshooting)

---

## Arsitektur Singkat

Ada 3 proses utama:

| Proses | File | Fungsi |
|--------|------|--------|
| Worker | `scripts/worker.py` | FastAPI di port 3000. Download via yt-dlp + fallback, kirim ke Telegram, serve dashboard web. |
| Bot | `scripts/bot.py` | Listener Telegram. Deteksi link, terima command, hapus pesan, upload cookie. |
| Supervisor | `supervisor.sh` | Jaga worker + bot tetap hidup, restart otomatis kalau mati. |

Folder penting:

- `cookies/` — file cookie per platform (`x.txt`, `instagram.txt`, dst)
- `downloads/` — hasil download, dipisah per `Nama Grup/Nama Topik/`
- `logs/` — log worker, bot, supervisor, dan token dashboard

---

## Cara Install & Setup

### 1. Clone Repositori & Jalankan Installer Otomatis
Jalankan script `setup.sh` untuk menyiapkan virtual environment, menginstal dependensi, membuat folder yang diperlukan, dan menyiapkan konfigurasi `.env`.

```bash
git clone https://github.com/zekkcode/telegram-x-video-downloader.git
cd telegram-x-video-downloader
bash setup.sh
```

### 2. Isi Token Bot (.env)
Buka file `.env` yang baru dibuat dan masukkan token bot Telegram Anda dari BotFather:
```env
TELEGRAM_BOT_TOKEN=token_dari_botfather
```

---

## Cara Menyalakan

Ada dua cara untuk menyalakan bot ini: menggunakan **Local Environment (WSL/Linux)** atau **Docker Compose**.

### Metode A: Local Environment (WSL/Linux)

Jalanin supervisor. Dia otomatis nyalain worker + bot secara background, restart kalau mati, dan buka dashboard di browser.

```bash
bash supervisor.sh
```

Kalau mau tetap jalan walau terminal ditutup:
```bash
nohup bash supervisor.sh >> logs/supervisor-console.log 2>&1 &
```

Stop supervisor (sekalian worker + bot):
```bash
kill $(cat logs/supervisor.pid)
```

### Metode B: Docker Compose (Disarankan untuk VPS/Server)

Pastikan file konfigurasi `.env` sudah diisi, lalu jalankan:

```bash
docker-compose up --build -d
```

Command berguna untuk Docker:
*   Melihat status container: `docker-compose ps`
*   Melihat log realtime: `docker-compose logs -f`
*   Mematikan container: `docker-compose down`

### Metode C: Cara manual (tanpa auto-restart)

```bash
bash start.sh
```

`start.sh` cuma nyalain worker + bot sekali. Kalau salah satu mati, gak otomatis idup lagi. Buat sehari-hari, mending pakai `supervisor.sh` atau **Docker Compose**.

### Cek status jalan atau nggak

```bash
# lihat proses
ps aux | grep -E "worker.py|bot.py|supervisor" | grep -v grep

# cek worker hidup
curl -s http://127.0.0.1:3000/health
```

---

## Command Bot di Telegram

Semua command clean mode **cuma bisa dipakai admin grup**. Bot juga harus jadi admin dengan izin **Delete messages** biar bisa hapus pesan.

### Clean Mode (hapus pesan teks otomatis)

Kalau aktif, pesan teks biasa + pesan status/error bot bakal dihapus. **Media (foto/video/dokumen) dan pesan yang ada link tetap aman.**

| Command | Alias | Fungsi |
|---------|-------|--------|
| `/hapus_on` | `/clean_on`, `/bersih_on` | Aktifkan clean mode (berlaku se-grup) |
| `/hapus_off` | `/clean_off`, `/bersih_off` | Matikan clean mode |
| `/clean_status` | `/bersih_status` | Cek status clean mode + izin delete bot |

### Hapus Pesan Lama

| Command | Alias | Fungsi |
|---------|-------|--------|
| `/hapus_lama 50` | `/clean_old`, `/bersih_lama` | Hapus pesan teks lama yang udah tercatat (default 50, max 100) |
| `/hapus_bot_lama 100` | `/clean_bot_old`, `/bersih_bot_lama` | Hapus pesan lama dari bot di topik ini |
| `/hapus_bot_lama 100 all` | + `semua` / `global` | Hapus pesan bot lama di **semua topik** dalam grup |
| `/hapus_ini` | `/delete_this` | Reply ke pesan bot, lalu kirim ini buat hapus pesan itu |

> Catatan: Telegram gak ngasih bot akses ke history lama yang belum pernah dilihat. Jadi hapus-lama cuma jalan untuk pesan yang tercatat **setelah bot aktif**.

### Status & Info

| Command | Alias | Fungsi |
|---------|-------|--------|
| `/status` | `/cookies`, `/cookie_status` | Status worker, queue, cookie ke-load, izin delete, clean mode |
| `/where` | `/topic`, `/id` | Tampilkan chat_id + message_thread_id (buat debug topik) |

### Download media

Gak ada command khusus. Cukup **kirim/forward link** ke grup atau topik:

```
https://x.com/user/status/123456789
https://www.tiktok.com/@user/video/123
https://youtu.be/xxxx
```

Mau nambahin tag sendiri di caption? Tulis hashtag di pesan yang sama:

```
https://x.com/user/status/123  #asia #semok
```

Platform yang didukung: **X/Twitter, TikTok, YouTube, Facebook, Instagram**.

---

## Cara Dapetin & Pasang Cookie

Cookie dibutuhin buat konten yang perlu login (akun private, restricted, age-gated). **Pakai cookie dari akun lu sendiri.**

### Langkah 1 — Export cookie dari browser

1. Pasang extension export cookie format Netscape, misalnya **"Get cookies.txt LOCALLY"** (Chrome/Firefox).
2. Login ke platform target (X, Instagram, dll) di browser.
3. Buka situsnya, klik extension, **Export** → dapet file `.txt` format Netscape.

### Langkah 2 — Pasang cookie

Ada 3 cara, pilih yang paling enak:

**A. Lewat Web Dashboard (paling gampang)**
Buka dashboard → di tiap platform ada tombol **Upload**. Pilih file `.txt`-nya. Selesai. (Lihat [Web Control Panel](#web-control-panel))

**B. Lewat chat Telegram ke bot**
Kirim file cookie `.txt` ke bot, dengan **caption** sebut platformnya:

```
cookie x
cookie ig
cookie tiktok
cookie yt
cookie fb
```

Bot validasi, simpan ke `cookies/`, lalu **auto-hapus pesan upload** biar cookie gak ketinggalan di chat.
> Lebih aman lakuin ini di **chat private** ke bot, jangan di grup.

**C. Manual taruh file**
Copy file ke folder `cookies/` dengan nama sesuai platform:

| Platform | Nama file |
|----------|-----------|
| X / Twitter | `cookies/x.txt` |
| Instagram | `cookies/instagram.txt` |
| TikTok | `cookies/tiktok.txt` |
| YouTube | `cookies/youtube.txt` |
| Facebook | `cookies/facebook.txt` |

### Cek cookie udah ke-load

- Web dashboard: dot hijau + ukuran file
- Telegram: kirim `/status`
- Worker: `curl -s http://127.0.0.1:3000/health`

---

## Web Control Panel

Panel web buat lihat status real-time dan atur cookie tanpa nyentuh terminal.

### Akses

```
http://127.0.0.1:3000/dashboard
```

Akses cuma **lokal** (127.0.0.1) demi keamanan cookie. Default tanpa token, langsung kebuka.

### Token (opsional)

Kalau lu mau lapisan ekstra (misal mau akses dari device lain di jaringan yang sama), set token di `.env`:

```bash
DASHBOARD_TOKEN=isi_token_apa_aja_terserah
```

Kalau diset, dashboard butuh token. Akses lewat URL: `http://127.0.0.1:3000/dashboard?token=*** (kesimpen otomatis di browser).

Kalau dikosongin / dihapus dari `.env`, dashboard kebuka tanpa autentikasi.

### Fitur dashboard

- **Status real-time**: worker, bot, supervisor, tagger, queue, jumlah clean mode aktif (auto-refresh 10 detik).
- **Akun & Cookies**:
  *   **Drag & Drop File**: Taruh file cookie `.txt` ke platform terkait, atau jatuhkan ke mana saja pada dashboard (sistem akan otomatis mendeteksi platform berdasarkan nama file).
  *   **One-Click Paste Clipboard**: Cukup salin teks cookie Anda ke clipboard, lalu klik tombol *Paste Clipboard* untuk menyimpannya secara instan.
  *   **Paste Text (Manual Input)**: Tempel teks cookie secara manual lewat modal dialog jika Clipboard API tidak didukung.
- **Desain Premium**: Tampilan gelap (dark mode) dengan glassmorphism modern, font *Outfit*, micro-animations, dan panel pemantau status.
- **Pengaturan**: status token Telegram, toggle auto-refresh.

### Edit tampilan dashboard

UI dipisah dari logika:

- `scripts/dashboard.html` — struktur + style
- `scripts/dashboard.js` — logika + brand icon

Edit file-nya, refresh browser, langsung keganti. Gak perlu restart worker.

---

## Konfigurasi (.env)

Copy `.env.example` ke `.env`, lalu isi:

```bash
TELEGRAM_BOT_TOKEN=token_dari_botfather
OPENCLAW_WORKER_URL=http://127.0.0.1:3000/twitter-video

# opsional
X_BEARER_TOKEN=                 # buat fallback X API resmi
DASHBOARD_TOKEN=                # kosongin biar auto-generate
WORKER_HOST=127.0.0.1           # jangan diubah ke 0.0.0.0 kecuali paham risikonya
WORKER_PORT=3000

# cookie path (default udah ngarah ke folder cookies/)
COOKIES_FILE=/mnt/d/telegram-x-video-downloader/cookies.txt
X_COOKIES_FILE=/mnt/d/telegram-x-video-downloader/cookies/x.txt
INSTAGRAM_COOKIES_FILE=/mnt/d/telegram-x-video-downloader/cookies/instagram.txt
TIKTOK_COOKIES_FILE=/mnt/d/telegram-x-video-downloader/cookies/tiktok.txt
YOUTUBE_COOKIES_FILE=/mnt/d/telegram-x-video-downloader/cookies/youtube.txt
FACEBOOK_COOKIES_FILE=/mnt/d/telegram-x-video-downloader/cookies/facebook.txt

# Tagger (opsional). Path ke python venv yang punya open_clip_torch.
TAGGER_PYTHON=

# Dashboard token (opsional). Kosongin = tanpa auth.
DASHBOARD_TOKEN=

# Worker host/port
WORKER_HOST=127.0.0.1
WORKER_PORT=3000

# Auto cleanup download lama (opsional)
# MAX_DOWNLOAD_AGE_DAYS=7
# MAX_DOWNLOAD_SIZE_GB=10
```

> Jangan commit `.env`, folder `cookies/`, `downloads/`, dan `logs/` ke git. Itu berisi data sensitif akun.

---

## Troubleshooting

**Bot gak hapus pesan**
Pastikan bot jadi **admin grup** dengan izin **Delete messages**. Cek pakai `/clean_status` atau `/status`.

**Pesan "Conflict: terminated by other getUpdates"**
Ada 2 instance bot jalan barengan. Matiin semua, nyalain ulang via supervisor:
```bash
pkill -f "scripts/bot.py"; pkill -f "scripts/worker.py"
bash supervisor.sh
```

**Download gagal "No video could be found"**
Itu post gambar, bukan video — fallback otomatis bakal jalan. Kalau post private/protected, pastikan cookie platform itu udah ke-load.

**Dashboard 401**
Kalau lu set `DASHBOARD_TOKEN` di `.env` tapi gak masukin token waktu akses. Lepas token dari `.env` (kosongin) atau pakai URL `?token=*** lu.

**Worker mati terus**
Pakai `supervisor.sh`, bukan `start.sh`. Supervisor auto-restart tiap 15 detik.

**Lihat log**
```bash
tail -f logs/worker.log        # aktivitas download
tail -f logs/bot.log           # aktivitas bot
tail -f logs/supervisor.log    # restart events
```
