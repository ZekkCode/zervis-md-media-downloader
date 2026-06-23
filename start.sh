#!/usr/bin/env bash
set -euo pipefail

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

source .venv/bin/activate

pid_is_running() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

pid_has_cmd() {
  local pid="${1:-}"
  local needle="${2:-}"
  [[ -n "$pid" ]] && ps -p "$pid" -o cmd= 2>/dev/null | grep -Fq "$needle"
}

worker_pid_from_port() {
  ss -ltnp 2>/dev/null \
    | sed -n 's/.*:3000 .*pid=\([0-9]\+\).*/\1/p' \
    | head -n 1
}

bot_pid_from_process() {
  pgrep -f "scripts/bot.py" 2>/dev/null | while read -r pid; do
    if pid_has_cmd "$pid" "scripts/bot.py"; then
      echo "$pid"
      break
    fi
  done
}

WORKER_PID="$(worker_pid_from_port || true)"
BOT_PID="$(bot_pid_from_process || true)"
STARTED_WORKER=0
STARTED_BOT=0

if pid_is_running "$WORKER_PID" && pid_has_cmd "$WORKER_PID" "scripts/worker.py"; then
  echo "Worker already running. PID: $WORKER_PID"
else
  echo "Starting worker..."
  python scripts/worker.py >> logs/worker-console.log 2>&1 &
  WORKER_PID=$!
  STARTED_WORKER=1
fi

if pid_is_running "$BOT_PID" && pid_has_cmd "$BOT_PID" "scripts/bot.py"; then
  echo "Bot already running. PID: $BOT_PID"
else
  echo "Starting bot..."
  python scripts/bot.py >> logs/bot-console.log 2>&1 &
  BOT_PID=$!
  STARTED_BOT=1
fi

echo "$WORKER_PID" > logs/worker.pid
echo "$BOT_PID" > logs/bot.pid

DASH_URL="http://127.0.0.1:${WORKER_PORT:-3000}/dashboard"

echo "Worker PID: $WORKER_PID"
echo "Bot PID: $BOT_PID"
echo "Dashboard: $DASH_URL"
echo "Logs:"
echo "- $PROJECT_DIR/logs/worker.log"
echo "- $PROJECT_DIR/logs/bot.log"
echo "- $PROJECT_DIR/logs/worker-console.log"
echo "- $PROJECT_DIR/logs/bot-console.log"
echo
if [[ "$STARTED_WORKER" -eq 0 && "$STARTED_BOT" -eq 0 ]]; then
  echo "Worker dan bot sudah jalan. Tidak perlu start ulang."
  exit 0
fi

echo "Tekan CTRL+C untuk stop proses yang baru start dari terminal ini."

cleanup() {
  echo "Stopping..."
  if [[ "$STARTED_WORKER" -eq 1 ]]; then
    kill "$WORKER_PID" 2>/dev/null || true
  fi
  if [[ "$STARTED_BOT" -eq 1 ]]; then
    kill "$BOT_PID" 2>/dev/null || true
  fi
}
trap cleanup INT TERM EXIT

WAIT_PIDS=()
if [[ "$STARTED_WORKER" -eq 1 ]]; then
  WAIT_PIDS+=("$WORKER_PID")
fi
if [[ "$STARTED_BOT" -eq 1 ]]; then
  WAIT_PIDS+=("$BOT_PID")
fi

wait "${WAIT_PIDS[@]}"
