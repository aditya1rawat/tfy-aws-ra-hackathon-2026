#!/usr/bin/env bash
# Restart the local dev bridge (uvicorn on :8000) after backend code changes.
# Kills whatever holds the port, relaunches detached from .venv, waits for /health.
# No --reload: the WatchFiles reloader fails to boot the worker on this box, so a
# clean kill+relaunch is the reliable path. Loads backend/.env via load_dotenv().
set -euo pipefail

PORT=8000
HOST=127.0.0.1
LOG=/tmp/lifeline-bridge.log
BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BACKEND_DIR"

echo "[restart_bridge] killing anything on :$PORT"
for p in $(lsof -ti :"$PORT" 2>/dev/null || true); do kill "$p" 2>/dev/null || true; done
pkill -f "uvicorn lifeline.bridge.app" 2>/dev/null || true
sleep 1

echo "[restart_bridge] launching uvicorn (log: $LOG)"
nohup .venv/bin/uvicorn lifeline.bridge.app:app --port "$PORT" --host "$HOST" > "$LOG" 2>&1 &
echo "[restart_bridge] pid $!"

for i in $(seq 1 15); do
  sleep 1
  if curl -s --max-time 2 "http://$HOST:$PORT/health" >/dev/null 2>&1; then
    echo "[restart_bridge] UP after ${i}s — $(curl -s http://$HOST:$PORT/health)"
    exit 0
  fi
done

echo "[restart_bridge] FAILED to come up in 15s. Last log lines:"
tail -20 "$LOG"
exit 1
