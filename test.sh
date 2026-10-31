#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/config.sh"
FILE="${1:-$DIR/test_zh.wav}"

echo "POST /asr  file=$FILE"
time curl -sS -X POST "http://127.0.0.1:$SV_PORT/asr" \
  -H "Authorization: Bearer $SV_API_TOKEN" \
  -F "file=@$FILE"
echo
