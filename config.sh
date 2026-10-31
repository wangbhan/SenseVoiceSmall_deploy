# SenseVoice API 配置
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 端口/资源
export SV_PORT=9820
export SV_NUM_THREADS=4
export SV_MAX_SECONDS=60
export SV_MODEL_DIR="$DIR/models"
export SV_LOG="$DIR/logs/app.log"
export SV_PID="$DIR/logs/app.pid"

# Token 从 .env 加载（.env 不入库）
if [ -f "$DIR/.env" ]; then
  set -a; source "$DIR/.env"; set +a
fi
: "${SV_API_TOKEN:?SV_API_TOKEN 未设置，请在 $DIR/.env 中填入，或用 openssl rand -hex 24 生成}"
