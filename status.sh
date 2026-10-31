#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/config.sh"

if [ -f "$SV_PID" ] && kill -0 "$(cat $SV_PID)" 2>/dev/null; then
  PID=$(cat "$SV_PID")
  RSS=$(ps -o rss= -p "$PID" | awk '{printf "%.0f MB", $1/1024}')
  CPU=$(ps -o pcpu= -p "$PID")
  echo "RUNNING  pid=$PID  mem=$RSS  cpu=$CPU%"
else
  echo "STOPPED"
  exit 1
fi

curl -sf "http://127.0.0.1:$SV_PORT/health" && echo
ss -lntp 2>/dev/null | grep ":$SV_PORT " || true
