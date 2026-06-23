#!/usr/bin/env bash
# Supervisor: jaga worker + bot tetap hidup. Restart otomatis kalau mati.
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"
export PYTHONPATH="$PROJECT_DIR"

mkdir -p logs

if [[ ! -x ".venv/bin/python" ]]; then
  echo ".venv belum ada. Jalankan setup dependency dulu."
  exit 1
fi

if [[ ! -f ".env" ]]; then
  echo ".env belum ada. Copy .env.example ke .env lalu isi token."
  exit 1
fi

PYTHON="$PROJECT_DIR/.venv/bin/python"
CHECK_INTERVAL="${CHECK_INTERVAL:-15}"
SUPERVISOR_PID_FILE="logs/supervisor.pid"

# Cegah supervisor dobel
if [[ -f "$SUPERVISOR_PID_FILE" ]]; then
  old_pid="$(cat "$SUPERVISOR_PID_FILE" 2>/dev/null || true)"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
    if ps -p "$old_pid" -o cmd= 2>/dev/null | grep -Fq "supervisor.sh"; then
      echo "Supervisor sudah jalan (PID $old_pid). Keluar."
      exit 0
    fi
  fi
fi
echo "$$" > "$SUPERVISOR_PID_FILE"

worker_alive() {
  pgrep -f "scripts/worker.py" >/dev/null 2>&1
}

bot_alive() {
  pgrep -f "scripts/bot.py" >/dev/null 2>&1
}

start_worker() {
  echo "$(date '+%F %T') starting worker..." >> logs/supervisor.log
  setsid "$PYTHON" scripts/worker.py >> logs/worker-console.log 2>&1 < /dev/null &
  echo "$!" > logs/worker.pid
}

start_bot() {
  echo "$(date '+%F %T') starting bot..." >> logs/supervisor.log
  setsid "$PYTHON" scripts/bot.py >> logs/bot-console.log 2>&1 < /dev/null &
  echo "$!" > logs/bot.pid
}

stop_all() {
  echo "$(date '+%F %T') supervisor stopping, killing children..." >> logs/supervisor.log
  pkill -f "scripts/worker.py" 2>/dev/null || true
  pkill -f "scripts/bot.py" 2>/dev/null || true
  rm -f "$SUPERVISOR_PID_FILE"
  exit 0
}

trap stop_all INT TERM

echo "$(date '+%F %T') supervisor online (interval ${CHECK_INTERVAL}s, pid $$)" >> logs/supervisor.log
echo "Supervisor online. PID $$. Cek tiap ${CHECK_INTERVAL}s."
echo "Stop: kill \$(cat logs/supervisor.pid)"

DASH_PORT="${WORKER_PORT:-3000}"
DASH_URL="http://127.0.0.1:${DASH_PORT}/dashboard"

open_dashboard() {
  # Buka browser ke dashboard sekali, setelah worker siap.
  for _ in $(seq 1 20); do
    if curl -s -m 2 "http://127.0.0.1:${DASH_PORT}/health" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  if command -v wslview >/dev/null 2>&1; then
    wslview "$DASH_URL" >/dev/null 2>&1 || true
  elif command -v cmd.exe >/dev/null 2>&1; then
    cmd.exe /c start "" "$DASH_URL" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$DASH_URL" >/dev/null 2>&1 || true
  fi
  echo "Dashboard: $DASH_URL"
}

if [[ "${OPEN_DASHBOARD:-1}" == "1" ]]; then
  ( open_dashboard ) &
fi

# Bersihin stale lock bot sebelum mulai
rm -f logs/bot.lock 2>/dev/null || true

while true; do
  if ! worker_alive; then
    echo "$(date '+%F %T') worker mati, restart..." >> logs/supervisor.log
    start_worker
    sleep 3
  fi

  if ! bot_alive; then
    echo "$(date '+%F %T') bot mati, restart..." >> logs/supervisor.log
    rm -f logs/bot.lock 2>/dev/null || true
    start_bot
    sleep 3
  fi

  sleep "$CHECK_INTERVAL"
done
