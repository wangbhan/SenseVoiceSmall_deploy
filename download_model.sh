#!/usr/bin/env bash
# 首次构建前执行；下载 SenseVoiceSmall int8 onnx 模型到 ./models/
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$DIR/models"
cd "$DIR/models"

BASE="https://hf-mirror.com/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/resolve/main"
[ -f model.int8.onnx ] || curl -L -o model.int8.onnx "$BASE/model.int8.onnx"
[ -f tokens.txt ]      || curl -L -o tokens.txt      "$BASE/tokens.txt"

ls -lh model.int8.onnx tokens.txt
echo "模型就绪，可以 docker compose build"
