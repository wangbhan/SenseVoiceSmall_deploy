#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/config.sh"

if [ ! -f "$SV_PID" ]; then
  echo "not running (no pidfile)"
  exit 0
fi
PID=$(cat "$SV_PID")
if ! kill -0 "$PID" 2>/dev/null; then
  echo "stale pidfile, cleaning"
  rm -f "$SV_PID"; exit 0
fi

kill "$PID"
for i in $(seq 1 10); do
  kill -0 "$PID" 2>/dev/null || { rm -f "$SV_PID"; echo "stopped (pid=$PID)"; exit 0; }
  sleep 1
done
kill -9 "$PID" 2>/dev/null
rm -f "$SV_PID"
echo "force-killed (pid=$PID)"
