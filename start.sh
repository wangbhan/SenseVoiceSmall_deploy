#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/config.sh"
mkdir -p "$(dirname "$SV_LOG")"

if [ -f "$SV_PID" ] && kill -0 "$(cat $SV_PID)" 2>/dev/null; then
  echo "already running, pid=$(cat $SV_PID)"
  exit 0
fi

export PATH="/root/miniconda3/bin:$PATH"
nohup python "$DIR/app.py" >> "$SV_LOG" 2>&1 &
echo $! > "$SV_PID"

for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:$SV_PORT/health" >/dev/null; then
    echo "SenseVoice API up  →  http://0.0.0.0:$SV_PORT/asr  (pid=$(cat $SV_PID))"
    exit 0
  fi
  sleep 1
done
echo "启动超时，查看日志: $SV_LOG"
tail -30 "$SV_LOG"
exit 1
