#!/usr/bin/env bash
# Automated setup script for Telegram Media Downloader Bot
set -euo pipefail

# Print with styling
info() { echo -e "\e[34m[INFO]\e[0m $*"; }
success() { echo -e "\e[32m[SUCCESS]\e[0m $*"; }
error() { echo -e "\e[31m[ERROR]\e[0m $*"; exit 1; }

echo "=========================================="
echo "      Zervis Bot Setup Installer"
echo "=========================================="

# 1. Check Python 3
info "Memeriksa instalasi Python 3..."
if ! command -v python3 &>/dev/null; then
    error "Python 3 tidak ditemukan. Harap instal Python 3 terlebih dahulu."
fi
python3_ver=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
info "Ditemukan Python versi: $python3_ver"

# 2. Setup virtual environment
info "Mengecek virtual environment (.venv)..."
if [ ! -d ".venv" ]; then
    info "Membuat virtual environment baru..."
    python3 -m venv .venv || error "Gagal membuat venv. Coba instal python3-venv (sudo apt install python3-venv)."
    success "Virtual environment berhasil dibuat!"
else
    info "Virtual environment (.venv) sudah ada."
fi

# 3. Upgrade pip and install dependencies
info "Menginstal dependencies..."
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt || error "Gagal menginstal dependencies dari requirements.txt."
success "Semua dependencies berhasil diinstal!"

# 4. Create directory structure
info "Membuat struktur folder..."
mkdir -p cookies downloads logs
success "Folder cookies/, downloads/, dan logs/ telah dibuat!"

# 5. Create .env if not exists
info "Memeriksa file konfigurasi (.env)..."
if [ ! -f ".env" ]; then
    info "Meng-copy file .env.example menjadi .env..."
    cp .env.example .env
    
    # Auto fill random DASHBOARD_TOKEN
    dash_token=$(python3 -c "import secrets; print(secrets.token_hex(16))")
    sed -i "s/DASHBOARD_TOKEN=/DASHBOARD_TOKEN=$dash_token/g" .env || true
    
    success "File .env telah dibuat! Token dashboard otomatis di-generate."
    echo -e "\e[33m[PERINGATAN]\e[0m Harap edit file .env dan masukkan TELEGRAM_BOT_TOKEN Anda!"
else
    info "File .env sudah ada. Tidak menimpa konfigurasi yang sudah ada."
fi

# 6. Fix executable permissions for scripts
info "Mengatur izin eksekusi script bash..."
chmod +x supervisor.sh start.sh start-worker.sh start-bot.sh setup.sh
success "Izin eksekusi script diatur!"

echo "=========================================="
success "Setup selesai dengan sukses!"
echo "=========================================="
echo -e "\e[1mTIGA HAL PENTING UNTUK DIINGAT:\e[0m"
echo -e "1. \e[33mBot Telegram Wajib:\e[0m Anda wajib membuat bot terlebih dahulu di @BotFather"
echo -e "   untuk mendapatkan token, lalu masukkan token tersebut ke file '.env'."
echo -e "2. \e[32mCookies Hanya untuk Video Privat:\e[0m Bot langsung bekerja untuk video publik"
echo -e "   tanpa butuh cookie. Cookie hanya diunggah jika ingin mendownload konten privat."
echo -e "3. \e[36mCukup Jalankan Supervisor:\e[0m Jangan menyalakan bot dan worker manual terpisah."
echo -e "   Selalu gunakan perintah: \e[36mbash supervisor.sh\e[0m"
echo "=========================================="
echo "Langkah selanjutnya:"
echo "1. Edit file '.env' dan masukkan TELEGRAM_BOT_TOKEN Anda."
echo "2. Jalankan bot & worker dengan perintah: bash supervisor.sh"
echo "3. Buka dashboard di browser: http://127.0.0.1:3000/dashboard"
echo "=========================================="
