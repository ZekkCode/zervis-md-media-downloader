---
name: telegram-x-video-downloader
description: Deteksi link X/Twitter, TikTok, YouTube, Facebook, dan Instagram dari grup Telegram, download media publik dengan yt-dlp, simpan sesuai folder nama grup dan topic, lalu kirim kembali ke topic Telegram yang sama.
---

# Telegram X Video Downloader Skill

Gunakan skill ini ketika user meminta bot Telegram untuk:
- membaca link X/Twitter, TikTok, YouTube, Facebook, dan Instagram dari grup Telegram
- mengecek apakah postingan memiliki media
- mendownload media publik menggunakan yt-dlp
- menyimpan video ke folder sesuai nama grup dan nama topic Telegram
- mengirim video, gambar, atau dokumen kembali ke topic yang sama

## Prinsip Aman

- Jangan melakukan scraping agresif.
- Gunakan cookie hanya dari akun milik user sendiri ketika konten membutuhkan login.
- Proses hanya postingan yang memang dapat diakses oleh akun/user tersebut.
- Pakai cache agar link yang sama tidak didownload berkali-kali.
- Batasi request per user dan per grup.
- Jangan hapus watermark/kredit.
- Selalu cantumkan link sumber asli di caption Telegram.
- Jangan bypass private/protected/paywalled/locked content.

## File Penting

- scripts/bot.py: listener Telegram.
- scripts/worker.py: worker FastAPI untuk download via yt-dlp, simpan file, dan upload balik ke Telegram.
- scripts/topics.json: mapping chat_id + message_thread_id ke nama topic.
- downloads/: folder output video.
- logs/: folder log bot, worker, dan output console.
- .env.example: template konfigurasi tanpa token asli.
- start.sh: menjalankan worker dan bot sekaligus.

## Cara Menjalankan

1. Pastikan `.env` berisi:
   - TELEGRAM_BOT_TOKEN
   - OPENCLAW_WORKER_URL
   - COOKIES_FILE (opsional)
   - X_COOKIES_FILE, INSTAGRAM_COOKIES_FILE, TIKTOK_COOKIES_FILE, YOUTUBE_COOKIES_FILE, FACEBOOK_COOKIES_FILE (opsional)

2. Jalankan worker:
   ```bash
   python3 scripts/worker.py
   ```

3. Jalankan bot:
   ```bash
   python3 scripts/bot.py
   ```

Atau jalankan keduanya:
```bash
./start.sh
```

## Workflow

Saat ada link:
1. Bot Telegram membaca link x.com/twitter.com, TikTok, YouTube, Facebook, atau Instagram.
2. Bot mengambil chat_id, group_name, message_thread_id, media_id, dan original_url.
3. Bot mengirim payload ke worker.
4. Worker memasukkan link ke queue agar request diproses satu per satu.
5. Worker mendownload media publik dengan yt-dlp.
6. Jika cookie platform tersedia, worker memakai cookie untuk konten yang butuh login.
7. Worker menyimpan file ke:
   ```text
   downloads/Nama Grup/Nama Topic/Nama Topic-1.mp4
   ```
8. Worker mengirim video/gambar/dokumen balik ke Telegram menggunakan message_thread_id.
9. Worker menyimpan cache media_id agar tidak download ulang.
10. Bot dan worker menulis log ke folder logs/.
