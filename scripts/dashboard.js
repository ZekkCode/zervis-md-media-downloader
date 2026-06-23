const PLATFORMS = {
  youtube: {
    name: "YouTube",
    svg: '<svg viewBox="0 0 24 24" fill="#ff0000"><path d="M23.5 6.2a3 3 0 0 0-2.1-2.1C19.5 3.5 12 3.5 12 3.5s-7.5 0-9.4.6A3 3 0 0 0 .5 6.2 31 31 0 0 0 0 12a31 31 0 0 0 .5 5.8 3 3 0 0 0 2.1 2.1c1.9.6 9.4.6 9.4.6s7.5 0 9.4-.6a3 3 0 0 0 2.1-2.1A31 31 0 0 0 24 12a31 31 0 0 0-.5-5.8zM9.5 15.5v-7l6.3 3.5z"/></svg>'
  },
  facebook: {
    name: "Facebook",
    svg: '<svg viewBox="0 0 24 24" fill="#1877f2"><path d="M24 12a12 12 0 1 0-13.9 11.9v-8.4H7v-3.5h3.1V9.4c0-3 1.8-4.7 4.5-4.7 1.3 0 2.7.2 2.7.2v3h-1.5c-1.5 0-2 .9-2 1.9v2.2h3.4l-.5 3.5h-2.9v8.4A12 12 0 0 0 24 12z"/></svg>'
  },
  x: {
    name: "X (Twitter)",
    svg: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M18.2 2.2h3.3l-7.2 8.3 8.5 11.3h-6.7l-5.2-6.9-6 6.9H1.6l7.7-8.9L1.2 2.2h6.8l4.7 6.3zM17 19.8h1.8L7.1 4.1H5.1z"/></svg>'
  },
  instagram: {
    name: "Instagram",
    svg: '<svg viewBox="0 0 24 24" fill="none" stroke="#e1306c" stroke-width="2"><rect x="2" y="2" width="20" height="20" rx="5.5"/><circle cx="12" cy="12" r="4.2"/><circle cx="17.5" cy="6.5" r="1.2" fill="#e1306c" stroke="none"/></svg>'
  },
  tiktok: {
    name: "TikTok",
    svg: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M16.5 2c.3 2.2 1.6 3.9 3.8 4.1v2.7c-1.3.1-2.5-.3-3.8-1v6.6c0 4-2.9 6.6-6.4 6.6A6.1 6.1 0 0 1 4 14.9c0-3.6 3.3-6.3 7-5.6v2.9c-.4-.1-.9-.2-1.4-.2-1.7 0-3 1.3-3 3a3 3 0 0 0 6 .1V2z"/></svg>'
  }
};
const ORDER = ["youtube", "facebook", "x", "instagram", "tiktok"];

let TOKEN = localStorage.getItem("zervis_token") || "";
(function initTokenFromUrl() {
  const q = new URLSearchParams(location.search).get("token");
  if (q) { TOKEN = q.trim(); localStorage.setItem("zervis_token", TOKEN); }
})();

function toast(m) {
  const t = document.getElementById("toast");
  t.textContent = m;
  t.classList.add("show");
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove("show"), 2300);
}
function hdr() { return { "X-Dashboard-Token": TOKEN }; }
function fmtSize(b) { return b >= 1024 ? Math.round(b / 1024) + " KB" : b + " B"; }
function fmtTime(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  return d.toLocaleDateString("id-ID", { day: "numeric", month: "short" }) + " " +
    d.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
}

function shell() {
  return `
  <!-- TAB: DASHBOARD -->
  <div id="tab-dashboard" class="tab-content active">
    <div class="grid" id="stats"></div>
    
    <section>
      <div class="h">Akun &amp; Cookies</div>
      <div class="panel" id="accounts"></div>
    </section>

    <section>
      <div class="h">Pengaturan</div>
      <div class="panel" id="settings"></div>
    </section>

    <section>
      <div class="h">Akses</div>
      <div class="panel" style="padding:16px">
        <div class="access">
          <button class="solid" onclick="refresh()">Refresh</button>
        </div>
        <div class="note">Panel ini cuma untuk akses lokal di laptop ini. Jangan ekspos worker ke jaringan publik.</div>
      </div>
    </section>
  </div>

  <!-- TAB: PANDUAN -->
  <div id="tab-guide" class="tab-content">
    <div class="guide-card" style="margin-top:0;">
      <div class="guide-toggle" style="cursor:default;display:flex;align-items:center;justify-content:flex-start;gap:8px;">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:16px;height:16px;flex-shrink:0;"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>
        <span>Dokumentasi Lengkap &amp; Setup Panduan</span>
      </div>
      <div class="guide-content" style="display:block;border-top:none;color:var(--txt);">
        
        <!-- Langkah 1: Persiapan Awal -->
        <h3 style="margin-top:0;font-weight:600;font-size:15px;border-bottom:1px solid var(--line);padding-bottom:6px;color:var(--accent);text-transform:uppercase;letter-spacing:0.3px;">Langkah 1: Persiapan Awal (Python &amp; FFmpeg)</h3>
        <p>Sebelum menjalankan aplikasi ini, sistem Anda membutuhkan dua prasyarat utama:</p>
        
        <div style="background:var(--bg);padding:12px;border-radius:8px;margin-bottom:16px;">
          <strong style="display:block;margin-bottom:6px;font-size:14px;color:var(--accent);">A. Python 3 (Versi 3.8 ke atas)</strong>
          <span style="font-size:13px;line-height:1.5;">
            • <strong>Windows:</strong> Unduh installer Python dari <a href="https://www.python.org/downloads/" target="_blank" rel="noopener">python.org</a>. <span style="color:var(--off);font-weight:600;">PERINGATAN KERAS:</span> Saat menginstal di Windows, pastikan Anda mencentang kotak <strong>"Add Python to PATH"</strong> di jendela pertama installer. Jika dilewati, perintah <code>python</code> tidak akan dikenali di CMD/PowerShell.<br>
            • <strong>Linux (Ubuntu/Debian):</strong> Jalankan perintah berikut di terminal Anda:<br>
            <code style="display:block;background:var(--panel);padding:6px;border-radius:4px;margin-top:6px;font-family:monospace;border:1px solid var(--line);">sudo apt update && sudo apt install python3 python3-pip python3-venv</code>
            • <strong>macOS:</strong> Download installer resmi dari website Python atau gunakan Homebrew: <code>brew install python</code>
          </span>
        </div>

        <div style="background:var(--bg);padding:12px;border-radius:8px;margin-bottom:16px;">
          <strong style="display:block;margin-bottom:6px;font-size:14px;color:var(--accent);">B. FFmpeg (Sangat Penting untuk yt-dlp)</strong>
          <p style="margin:0 0 8px 0;font-size:13px;line-height:1.5;">
            <code>FFmpeg</code> sangat dibutuhkan oleh <code>yt-dlp</code> untuk menyatukan trek video HD (1080p ke atas) dan trek audio yang di-download terpisah dari server platform. Tanpa FFmpeg, video hasil unduhan Anda hanya akan bersuara tanpa gambar, atau resolusinya terbatas pada 360p/720p.
          </p>
          <span style="font-size:13px;line-height:1.5;">
            • <strong>Windows:</strong> Buka PowerShell (Run as Administrator) lalu jalankan perintah otomatis:<br>
            <code style="display:block;background:var(--panel);padding:6px;border-radius:4px;margin-top:6px;font-family:monospace;border:1px solid var(--line);">winget install Gygax.FFmpeg</code>
            Setelah selesai instalasi, tutup dan buka kembali jendela PowerShell/CMD Anda agar PATH diperbarui.<br>
            • <strong>Linux (Ubuntu/Debian):</strong> Jalankan:<br>
            <code style="display:block;background:var(--panel);padding:6px;border-radius:4px;margin-top:6px;font-family:monospace;border:1px solid var(--line);">sudo apt update && sudo apt install ffmpeg</code>
            • <strong>macOS:</strong> Jalankan melalui Terminal: <code>brew install ffmpeg</code>
          </span>
        </div>

        <!-- Langkah 2: Membuat Bot -->
        <h3 style="margin-top:24px;font-weight:600;font-size:15px;border-bottom:1px solid var(--line);padding-bottom:6px;color:var(--accent);text-transform:uppercase;letter-spacing:0.3px;">Langkah 2: Registrasi Bot Telegram</h3>
        <ol style="margin:10px 0 0 16px;padding:0;line-height:1.6;font-size:13px;">
          <li>Buka aplikasi Telegram Anda, cari akun resmi <a href="https://t.me/BotFather" target="_blank" rel="noopener">@BotFather</a> dan tekan tombol start.</li>
          <li>Kirim perintah <code>/newbot</code>. Ikuti petunjuk untuk mengisi nama bot dan username (misal: <code>zervis_downloader_bot</code>). Username harus diakhiri dengan kata <i>bot</i>.</li>
          <li>Setelah berhasil, BotFather akan memberikan <code>TELEGRAM_BOT_TOKEN</code> (contoh: <code>8957699644:AAGM3wz5C2suNNf9z30lDn8IlNAgA1eX5lE</code>). Simpan token ini untuk langkah berikutnya.</li>
        </ol>

        <!-- Langkah 3: Setup Dependensi -->
        <h3 style="margin-top:24px;font-weight:600;font-size:15px;border-bottom:1px solid var(--line);padding-bottom:6px;color:var(--accent);text-transform:uppercase;letter-spacing:0.3px;">Langkah 3: Pembuatan Env &amp; Instalasi Library</h3>
        <p>Buka terminal atau command prompt pada folder proyek ini, lalu pilih metode setup di bawah sesuai lingkungan sistem Anda:</p>
        
        <div style="background:var(--bg);padding:12px;border-radius:8px;margin-bottom:16px;">
          <strong style="display:block;margin-bottom:6px;font-size:14px;color:var(--txt);">• Metode A: Menggunakan Script Bash (Linux / macOS / Git Bash Windows)</strong>
          <span style="font-size:13px;line-height:1.5;">
            Cukup jalankan satu baris perintah ini di terminal. Script akan otomatis membuat virtual environment, menginstal pip, menginstal library pendukung, dan membuat duplikasi berkas konfigurasi env:
            <pre style="background:var(--panel);padding:8px 10px;border-radius:6px;font-family:monospace;font-size:12px;margin:6px 0 0 0;color:var(--txt);border:1px solid var(--line);">bash setup.sh</pre>
          </span>
        </div>

        <div style="background:var(--bg);padding:12px;border-radius:8px;">
          <strong style="display:block;margin-bottom:6px;font-size:14px;color:var(--txt);">• Metode B: Instalasi Manual di PowerShell (Untuk Windows Murni Tanpa Bash)</strong>
          <span style="font-size:13px;line-height:1.5;">
            Jika Anda tidak menggunakan Git Bash, jalankan perintah ini baris demi baris di PowerShell Anda:
            <pre style="background:var(--panel);padding:8px 10px;border-radius:6px;font-family:monospace;font-size:12px;margin:6px 0;color:var(--txt);border:1px solid var(--line);"># 1. Membuat virtual environment
python -m venv .venv

# 2. Mengaktifkan virtual environment
.venv\\Scripts\\Activate.ps1

# 3. Menginstal pip dan semua dependensi
python -m pip install --upgrade pip
pip install -r requirements.txt

# 4. Membuat file konfigurasi .env dari template
copy .env.example .env</pre>
          </span>
        </div>

        <!-- Langkah 4: Konfigurasi .env -->
        <h3 style="margin-top:24px;font-weight:600;font-size:15px;border-bottom:1px solid var(--line);padding-bottom:6px;color:var(--accent);text-transform:uppercase;letter-spacing:0.3px;">Langkah 4: Konfigurasi File .env</h3>
        <ol style="margin:10px 0 0 16px;padding:0;line-height:1.6;font-size:13px;">
          <li>Buka file <code>.env</code> yang berada di root direktori proyek menggunakan editor teks seperti Notepad atau VS Code.</li>
          <li>Cari variabel <code>TELEGRAM_BOT_TOKEN=</code> lalu isi dengan token bot yang telah Anda dapatkan dari @BotFather di Langkah 2.</li>
          <li>(Opsional) Anda dapat menetapkan token keamanan akses dashboard pada variabel <code>DASHBOARD_TOKEN=</code> (misal: <code>DASHBOARD_TOKEN=admin123</code>). Jika dikosongkan, dashboard tidak akan memerlukan autentikasi token selama diakses lewat jaringan lokal.</li>
        </ol>

        <!-- Langkah 5: Cara Menjalankan -->
        <h3 style="margin-top:24px;font-weight:600;font-size:15px;border-bottom:1px solid var(--line);padding-bottom:6px;color:var(--accent);text-transform:uppercase;letter-spacing:0.3px;">Langkah 5: Cara Menjalankan Bot &amp; Panel Kontrol</h3>
        <p>Aplikasi ini memiliki 2 subsistem utama: **Bot Telegram** (untuk membalas dan menangkap link dari user) dan **FastAPI Worker** (untuk memproses download dan menyajikan dashboard kontrol ini).</p>
        
        <div style="background:var(--bg);padding:12px;border-radius:8px;margin-bottom:16px;">
          <strong style="display:block;margin-bottom:6px;font-size:14px;">• Metode A: Menggunakan Supervisor Script (Disarankan untuk Linux / macOS / Git Bash)</strong>
          <span style="font-size:13px;line-height:1.5;">
            Supervisor script akan menjalankan dan mengawasi kedua subsistem di latar belakang agar berjalan beriringan secara otomatis. Cukup ketik perintah berikut:
            <pre style="background:var(--panel);padding:8px 10px;border-radius:6px;font-family:monospace;font-size:12px;margin:6px 0 0 0;color:var(--txt);border:1px solid var(--line);">bash supervisor.sh</pre>
          </span>
        </div>

        <div style="background:var(--bg);padding:12px;border-radius:8px;">
          <strong style="display:block;margin-bottom:6px;font-size:14px;">• Metode B: Menjalankan Secara Terpisah (Windows PowerShell)</strong>
          <span style="font-size:13px;line-height:1.5;">
            Buka **dua** jendela PowerShell terpisah pada direktori proyek. Aktifkan virtual environment Anda di masing-masing jendela, lalu jalankan perintah berikut:
            <div style="display:flex;gap:12px;margin-top:8px;flex-wrap:wrap;">
              <div style="flex:1;min-width:220px;">
                <span style="font-weight:600;font-size:12.5px;color:var(--accent);display:block;margin-bottom:4px;">Jendela 1: Bot Listener</span>
                <pre style="background:var(--panel);padding:8px;border-radius:6px;font-family:monospace;font-size:11.5px;margin:0;color:var(--txt);border:1px solid var(--line);">.venv\\Scripts\\activate
python scripts/bot.py</pre>
              </div>
              <div style="flex:1;min-width:220px;">
                <span style="font-weight:600;font-size:12.5px;color:var(--accent);display:block;margin-bottom:4px;">Jendela 2: Worker &amp; Dashboard</span>
                <pre style="background:var(--panel);padding:8px;border-radius:6px;font-family:monospace;font-size:11.5px;margin:0;color:var(--txt);border:1px solid var(--line);">.venv\\Scripts\\activate
python scripts/worker.py</pre>
              </div>
            </div>
          </span>
        </div>

        <!-- Langkah 6: Setup Cookie -->
        <h3 style="margin-top:24px;font-weight:600;font-size:15px;border-bottom:1px solid var(--line);padding-bottom:6px;color:var(--accent);text-transform:uppercase;letter-spacing:0.3px;">Langkah 6: Ekspor &amp; Unggah Cookie (Hanya Jika Dibutuhkan)</h3>
        <p>Secara default, bot ini dapat langsung mengunduh semua media publik. Langkah ini hanya diperlukan jika Anda hendak mengunduh kiriman dari akun privat, konten yang dibatasi umur (restricted), atau postingan berbayar.</p>
        <ol style="margin:10px 0 0 16px;padding:0;line-height:1.6;font-size:13px;">
          <li>Pasang ekstensi browser Chrome: <a href="https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc" target="_blank" rel="noopener">Get cookies.txt LOCALLY</a>.</li>
          <li>Masuk ke situs media sosial tujuan (seperti <code>x.com</code> atau <code>instagram.com</code>) menggunakan akun Anda.</li>
          <li>Buka ekstensi tersebut di browser, pilih format ekspor Netscape lalu klik **Export** (file akan terunduh ke komputer Anda, contoh: <code>x.txt</code>).</li>
          <li>Kembali ke Dashboard Utama di panel ini, lalu seret dan lepas (Drag &amp; Drop) file <code>.txt</code> cookie tersebut ke baris platform masing-masing. Anda juga bisa menggunakan tombol **Paste Clipboard** atau **Paste Text** untuk menempel cookie secara manual.</li>
        </ol>

      </div>
    </div>
  </div>

  <!-- TAB: TENTANG (ABOUT) -->
  <div id="tab-about" class="tab-content">
    <div class="guide-card" style="margin-top:0;">
      <div class="guide-toggle" style="cursor:default;display:flex;align-items:center;justify-content:flex-start;gap:8px;">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:16px;height:16px;flex-shrink:0;"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
        <span>Tentang Zervis Bot Control</span>
      </div>
      <div class="guide-content" style="display:block;border-top:none;line-height:1.6;">
        <p><strong>Zervis Bot Control</strong> adalah aplikasi panel kontrol lokal yang dirancang untuk mengelola status bot Telegram media downloader secara efisien.</p>
        <p>Dengan panel ini, Anda dapat mengunggah, memperbarui, atau menghapus cookie sesi untuk berbagai platform media sosial utama, guna memastikan bot selalu dapat mengunduh konten restricted atau privat.</p>
        
        <h4 style="margin:16px 0 8px 0;font-weight:600;color:var(--txt);">Informasi Proyek:</h4>
        <table style="width:100%;border-collapse:collapse;margin-top:10px;font-size:13px;">
          <tr style="border-bottom:1px solid var(--line);">
            <td style="padding:8px 0;font-weight:600;width:140px;">Pengembang</td>
            <td style="padding:8px 0;"><a href="https://github.com/zekkcode" target="_blank" rel="noopener">zekkcode</a></td>
          </tr>
          <tr style="border-bottom:1px solid var(--line);">
            <td style="padding:8px 0;font-weight:600;">Lisensi</td>
            <td style="padding:8px 0;">MIT License</td>
          </tr>
          <tr style="border-bottom:1px solid var(--line);">
            <td style="padding:8px 0;font-weight:600;">Teknologi</td>
            <td style="padding:8px 0;">Python (FastAPI, Pyrogram, yt-dlp) &amp; Vanilla JS</td>
          </tr>
          <tr style="border-bottom:1px solid var(--line);">
            <td style="padding:8px 0;font-weight:600;">Kemampuan</td>
            <td style="padding:8px 0;">Mengunduh media (video, foto/gambar, audio, gif, dll.) dari berbagai platform sosial.</td>
          </tr>
          <tr>
            <td style="padding:8px 0;font-weight:600;">Repository</td>
            <td style="padding:8px 0;"><a href="https://github.com/zekkcode/zervis-md-media-downloader" target="_blank" rel="noopener">github.com/zekkcode/zervis-md-media-downloader</a></td>
          </tr>
        </table>
      </div>
    </div>
  </div>`;
}

function statItem(k, on, label) {
  return `<div class="stat"><div class="k">${k}</div><div class="v"><span class="dot ${on ? "on" : "off"}"></span>${label}</div></div>`;
}

function render(d) {
  const stats = document.getElementById("stats");
  stats.innerHTML =
    statItem("Worker", d.worker, d.worker ? "Aktif" : "Mati") +
    statItem("Bot Telegram", d.bot, d.bot ? "Aktif" : "Mati") +
    statItem("Auto-restart", d.supervisor, d.supervisor ? "Aktif" : "Mati") +
    statItem("Tagger", d.tagger, d.tagger ? "Siap" : "Hilang") +
    `<div class="stat"><div class="k">Queue</div><div class="v">${d.queue_size} antrian</div></div>` +
    `<div class="stat"><div class="k">Clean mode</div><div class="v">${d.cleanup_active} grup/topik</div></div>`;

  const cmap = {};
  (d.cookies || []).forEach(c => cmap[c.platform] = c);
  const box = document.getElementById("accounts");
  box.innerHTML = ORDER.map(p => {
    const meta = PLATFORMS[p];
    const c = cmap[p] || { loaded: false, size: 0, updated: 0 };
    const status = c.loaded
      ? `<span class="dot on"></span>Cookie aktif &middot; ${fmtSize(c.size)}${c.updated ? " &middot; " + fmtTime(c.updated) : ""}`
      : `<span class="dot off"></span>Belum ada cookie`;
    return `
      <div class="acct" data-platform="${p}">
        <div class="ico">${meta.svg}</div>
        <div class="meta">
          <div class="name">${meta.name}</div>
          <div class="st">${status}</div>
        </div>
        <div class="act">
          <label class="btn filebtn" title="Upload file cookie .txt">${c.loaded ? "Ganti" : "Upload"}
            <input type="file" accept=".txt" onchange="uploadCookie('${p}', this)">
          </label>
          <button class="btn" onclick="pasteFromClipboard('${p}')" title="Tempel langsung dari clipboard">Paste Clipboard</button>
          <button class="btn" onclick="openPasteModal('${p}')" title="Tempel teks secara manual">Paste Text</button>
          ${c.loaded ? `<button class="danger" onclick="delCookie('${p}')" title="Hapus cookie">Hapus</button>` : ""}
        </div>
      </div>`;
  }).join("");

  setupDragAndDrop();

  const set = document.getElementById("settings");
  set.innerHTML = `
    <div class="opt">
      <div class="lbl">Status Telegram token<small>Token bot dari konfigurasi .env</small></div>
      <div><span class="dot ${d.telegram_token_set ? "on" : "off"}"></span></div>
    </div>
    <div class="opt">
      <div class="lbl">Auto-refresh panel<small>Perbarui status tiap 10 detik</small></div>
      <div><button id="autobtn" onclick="toggleAuto()">${AUTO ? "Aktif" : "Mati"}</button></div>
    </div>`;
}

let AUTO = true;
let AUTO_TIMER = null;
function toggleAuto() {
  AUTO = !AUTO;
  document.getElementById("autobtn").textContent = AUTO ? "Aktif" : "Mati";
  setupAuto();
}
function setupAuto() {
  if (AUTO_TIMER) clearInterval(AUTO_TIMER);
  if (AUTO) AUTO_TIMER = setInterval(refresh, 10000);
}

function saveToken() {}

async function refresh() {
  try {
    const r = await fetch("/api/status", { headers: hdr() });
    if (r.status === 401) { toast("Token salah atau kosong"); return; }
    const d = await r.json();
    render(d);
  } catch (e) {
    toast("Gagal konek ke worker");
  }
}

async function uploadCookie(platform, inp) {
  if (!inp.files.length) return;
  const fd = new FormData();
  fd.append("file", inp.files[0]);
  const r = await fetch("/api/cookies/" + platform, { method: "POST", headers: hdr(), body: fd });
  const d = await r.json().catch(() => ({}));
  if (r.ok) { toast(PLATFORMS[platform].name + " cookie tersimpan"); refresh(); }
  else { toast("Gagal: " + (d.detail || r.status)); }
  inp.value = "";
}

async function delCookie(platform) {
  if (!confirm("Hapus cookie " + PLATFORMS[platform].name + "?")) return;
  const r = await fetch("/api/cookies/" + platform, { method: "DELETE", headers: hdr() });
  if (r.ok) { toast(PLATFORMS[platform].name + " cookie dihapus"); refresh(); }
  else { toast("Gagal hapus cookie"); }
}

// Modal cookie paste logic
let currentPlatformForModal = "";
function openPasteModal(platform) {
  currentPlatformForModal = platform;
  document.getElementById("modalTitle").textContent = "Paste Cookie " + PLATFORMS[platform].name;
  document.getElementById("cookieText").value = "";
  document.getElementById("cookieModal").classList.add("open");
  document.getElementById("modalSaveBtn").onclick = () => savePastedCookie(platform);
}

function closeModal() {
  document.getElementById("cookieModal").classList.remove("open");
  currentPlatformForModal = "";
}

async function savePastedCookie(platform) {
  const text = document.getElementById("cookieText").value.trim();
  if (!text) {
    toast("Teks cookie tidak boleh kosong.");
    return;
  }
  const file = new File([text], PLATFORMS[platform].name.toLowerCase() + "_cookie.txt", { type: "text/plain" });
  const fd = new FormData();
  fd.append("file", file);
  try {
    const r = await fetch("/api/cookies/" + platform, { method: "POST", headers: hdr(), body: fd });
    const d = await r.json().catch(() => ({}));
    if (r.ok) {
      toast(PLATFORMS[platform].name + " cookie berhasil disimpan");
      closeModal();
      refresh();
    } else {
      toast("Gagal: " + (d.detail || r.status));
    }
  } catch (e) {
    toast("Gagal menyimpan cookie");
  }
}

let CURRENT_TAB = localStorage.getItem("current_tab") || "dashboard";

window.switchTab = function(tabId) {
  CURRENT_TAB = tabId;
  localStorage.setItem("current_tab", tabId);
  
  document.querySelectorAll(".nav-tab").forEach(el => {
    el.classList.toggle("active", el.dataset.tab === tabId);
  });
  
  document.querySelectorAll(".tab-content").forEach(el => {
    el.classList.toggle("active", el.id === `tab-${tabId}`);
  });
};

function renderHeader() {
  const headerRoot = document.getElementById("header-root");
  if (!headerRoot) return;
  headerRoot.innerHTML = `
  <div class="top-banner">
    <div class="top-banner-inner">
      <div class="brand-logo" onclick="switchTab('dashboard')">
        <div class="logo-avatar">Z</div>
        <span>Zervis</span>
      </div>
      <div class="nav-tabs">
        <div class="nav-tab" data-tab="dashboard" onclick="switchTab('dashboard')">Dashboard</div>
        <div class="nav-tab" data-tab="guide" onclick="switchTab('guide')">Panduan</div>
        <div class="nav-tab" data-tab="about" onclick="switchTab('about')">Tentang</div>
      </div>
      <div class="top-banner-right">
        <button id="themeToggle" class="btn" onclick="toggleTheme()" title="Ganti Tema" style="padding:6px;border-radius:50%;width:34px;height:34px;cursor:pointer;display:flex;align-items:center;justify-content:center;border:none;background:rgba(255,255,255,0.15);color:#ffffff;">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:16px;height:16px;"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>
        </button>
        <a class="dev" href="https://github.com/zekkcode" target="_blank" rel="noopener">github.com/zekkcode</a>
      </div>
    </div>
  </div>`;
}

function renderFooter() {
  const footerRoot = document.getElementById("footer-root");
  if (!footerRoot) return;
  footerRoot.innerHTML = `
  <footer class="footer-banner">
    <div class="footer-banner-inner">
      <span>Zervis &middot; Zekk Service</span>
      <span>dibuat oleh <a href="https://github.com/zekkcode" target="_blank" rel="noopener">zekkcode</a></span>
    </div>
  </footer>`;
}

document.getElementById("app").innerHTML = shell();
renderHeader();
renderFooter();

window.toggleTheme = function() {
  const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
  const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', newTheme);
  localStorage.setItem('theme', newTheme);
  updateThemeButton();
};

function updateThemeButton() {
  const btn = document.getElementById("themeToggle");
  if (!btn) return;
  const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
  if (currentTheme === 'dark') {
    btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:16px;height:16px;"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>`;
  } else {
    btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:16px;height:16px;"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>`;
  }
}

updateThemeButton();
switchTab(CURRENT_TAB);

// Drag & Drop event wire-up
function setupDragAndDrop() {
  const cards = document.querySelectorAll(".acct");
  cards.forEach(card => {
    const platform = card.dataset.platform;

    card.addEventListener("dragenter", (e) => {
      e.preventDefault();
      card.classList.add("drag-over");
    });

    card.addEventListener("dragover", (e) => {
      e.preventDefault();
      card.classList.add("drag-over");
    });

    card.addEventListener("dragleave", (e) => {
      e.preventDefault();
      card.classList.remove("drag-over");
    });

    card.addEventListener("drop", async (e) => {
      e.preventDefault();
      card.classList.remove("drag-over");
      const files = e.dataTransfer.files;
      if (files.length) {
        await handleCookieFileDrop(platform, files[0]);
      }
    });
  });

  // Global Drag-and-Drop Overlay Logic
  const overlay = document.getElementById("dropOverlay");
  if (!overlay) return;
  
  let dragCounter = 0;

  window.addEventListener("dragenter", (e) => {
    e.preventDefault();
    dragCounter++;
    if (dragCounter === 1) {
      overlay.classList.add("active");
    }
  });

  window.addEventListener("dragover", (e) => {
    e.preventDefault();
  });

  window.addEventListener("dragleave", (e) => {
    e.preventDefault();
    dragCounter--;
    if (dragCounter === 0) {
      overlay.classList.remove("active");
    }
  });

  window.addEventListener("drop", async (e) => {
    e.preventDefault();
    dragCounter = 0;
    overlay.classList.remove("active");

    const files = e.dataTransfer.files;
    if (files.length) {
      // Find the card being dropped onto if any
      let targetCard = null;
      let el = e.target;
      while (el && el !== window) {
        if (el.classList && el.classList.contains("acct")) {
          targetCard = el;
          break;
        }
        el = el.parentNode;
      }

      if (targetCard) {
        const platform = targetCard.dataset.platform;
        await handleCookieFileDrop(platform, files[0]);
      } else {
        // Global drop - process all dropped files and try to detect platform by name
        let processedCount = 0;
        for (let i = 0; i < files.length; i++) {
          const file = files[i];
          const platform = detectPlatformFromFilename(file.name);
          if (platform) {
            await handleCookieFileDrop(platform, file);
            processedCount++;
          }
        }
        if (processedCount === 0) {
          toast("Gagal mendeteksi platform dari nama file. Seret file langsung ke baris platform.");
        }
      }
    }
  });
}

function detectPlatformFromFilename(filename) {
  const name = filename.toLowerCase();
  if (name.includes("youtube") || name.includes("yt")) return "youtube";
  if (name.includes("facebook") || name.includes("fb")) return "facebook";
  if (name.includes("instagram") || name.includes("ig")) return "instagram";
  if (name.includes("tiktok")) return "tiktok";
  if (name.includes("twitter") || name.includes("x.txt") || name.includes("x_") || name.includes("_x.") || name === "x") return "x";
  return null;
}

async function handleCookieFileDrop(platform, file) {
  const reader = new FileReader();
  reader.onload = async (e) => {
    const text = e.target.result;
    const isNetscape = text.toLowerCase().includes("# netscape http cookie file") || text.includes("\t");
    const isHeader = text.includes("=") && text.includes(";");
    
    if (!isNetscape && !isHeader && !text.includes("\n")) {
      toast("Format cookie tidak valid. Pakai Netscape (cookies.txt) atau raw header.");
      return;
    }
    
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await fetch("/api/cookies/" + platform, { method: "POST", headers: hdr(), body: fd });
      const d = await r.json().catch(() => ({}));
      if (r.ok) {
        toast(PLATFORMS[platform].name + " cookie berhasil disimpan!");
        refresh();
      } else {
        toast("Gagal: " + (d.detail || r.status));
      }
    } catch (err) {
      toast("Gagal menyimpan cookie.");
    }
  };
  reader.readAsText(file);
}

// Clipboard Paste Logic
async function pasteFromClipboard(platform) {
  try {
    if (!navigator.clipboard || !navigator.clipboard.readText) {
      toast("Clipboard API tidak didukung browser ini. Gunakan manual Paste Text.");
      openPasteModal(platform);
      return;
    }

    const text = await navigator.clipboard.readText();
    if (!text || !text.trim()) {
      toast("Clipboard kosong. Salin cookie terlebih dahulu.");
      return;
    }

    const isNetscape = text.toLowerCase().includes("# netscape http cookie file") || text.includes("\t");
    const isHeader = text.includes("=") && text.includes(";");
    if (!isNetscape && !isHeader && !text.includes("\n")) {
      toast("Format cookie di clipboard tidak dikenali.");
      return;
    }

    const file = new File([text], platform + "_cookie.txt", { type: "text/plain" });
    const fd = new FormData();
    fd.append("file", file);

    const r = await fetch("/api/cookies/" + platform, { method: "POST", headers: hdr(), body: fd });
    const d = await r.json().catch(() => ({}));
    if (r.ok) {
      toast(PLATFORMS[platform].name + " cookie berhasil disimpan dari clipboard!");
      refresh();
    } else {
      toast("Gagal: " + (d.detail || r.status));
    }
  } catch (err) {
    console.warn("Clipboard API read failed, opening modal fallback:", err);
    toast("Akses clipboard ditolak. Silakan tempel secara manual.");
    openPasteModal(platform);
  }
}

refresh();
setupAuto();
