# SenseVoiceSmall API 服务

多语言语音识别 HTTP API（中/英/日/韩/粤），SenseVoiceSmall int8 ONNX + sherpa-onnx + FastAPI，纯 CPU 推理，2-3 并发。

## 快速开始（Docker）
```bash
git clone https://github.com/wangbhan/SenseVoiceSmall_deploy.git
cd SenseVoiceSmall_deploy
./download_model.sh                                        # 首次下载模型 229MB 到 ./models/
echo "SV_API_TOKEN=$(openssl rand -hex 24)" > .env         # 生成 token
docker compose up -d --build                               # 构建并起容器，端口 9820
docker compose logs -f                                     # 观察日志
curl -s http://127.0.0.1:9820/health
```

## 裸机部署（不用 Docker）
```bash
./download_model.sh
./start.sh    # 启动 + 健康检查（依赖已装好 miniconda + sherpa-onnx + fastapi）
./status.sh   # 查看状态、PID、内存
./test.sh     # 冒烟测（默认用 test_zh.wav，可传自定义 wav）
./stop.sh
```

## 端口
- **9820/tcp**（HTTP，绑定 0.0.0.0）

## 配置
- 端口/线程等在 `config.sh`
- **API token 在 `.env`**（首次部署：`cp .env.example .env && echo "SV_API_TOKEN=$(openssl rand -hex 24)" > .env`；`.env` 已在 `.gitignore` 里）

| 变量 | 默认 | 说明 |
|---|---|---|
| `SV_PORT` | 9820 | HTTP 端口 |
| `SV_API_TOKEN` | — | 鉴权 token（放 `.env`，勿入库） |
| `SV_NUM_THREADS` | 4 | onnxruntime 推理线程数 |
| `SV_MAX_SECONDS` | 60 | 单次请求最长音频 |

## 接口

### `POST /asr`
Header: `Authorization: Bearer <SV_API_TOKEN>`

Body: `multipart/form-data`，字段名 `file`

支持格式：
- **WAV**（16/24/32-bit，任意采样率，任意声道，自动转 16k mono）
- **裸 PCM** 16-bit little-endian（需带 `?sample_rate=16000` 查询参数）

Query 参数：
- `sample_rate`（默认 16000，仅在无 WAV header 时使用）

成功响应 200（含诊断时间戳 headers）：
```json
{
  "text": "欢迎大家来体验达摩院推出的语音合成模型。",
  "language": "zh",
  "emotion": "NEUTRAL",
  "event": "Speech",
  "duration": 5.547,
  "upload_ms": 0.1,
  "decode_ms": 0.4,
  "infer_ms": 441.0,
  "total_ms": 442.0
}
```
Headers：
| Header | 说明 |
|---|---|
| `X-Upload-Ms` | 请求 body 上传耗时 |
| `X-Decode-Ms` | WAV 解析+重采样 |
| `X-Infer-Ms` | 模型推理 |
| `X-Total-Ms` | 服务端处理总时长 |
| `X-Request-Id` | 匹配服务端 log；客户端可通过同名请求头注入 |
| `Server-Timing` | 标准格式，供网关/监控采集 |
- `language`: zh / en / ja / ko / yue / auto
- `emotion`: NEUTRAL / HAPPY / SAD / ANGRY / FEARED / DISGUSTED / SURPRISED / EMO_UNKNOWN
- `event`: Speech / BGM / Applause / Laughter / Cry / Sneezle / Breathing / Coughing / Hum / Event_UNKNOWN
- `duration` 音频秒数；`infer_ms` 推理耗时

错误响应：
| HTTP | 场景 |
|---|---|
| 401 | 缺少 Authorization |
| 403 | token 错误 |
| 400 | body 为空 |
| 413 | 音频 > `SV_MAX_SECONDS` |
| 415 | WAV 采样位深不支持 |

### `GET /health`
无鉴权。返回 `{"ok":true,"model":"SenseVoiceSmall-int8","supports_stream":false}`。

### `GET /metrics/recent?limit=20`
无鉴权。返回最近 100 次 ASR 请求的 timing 汇总（infer_ms p50/p95/avg + 明细），用于诊断和压测。

## curl 示例
```bash
TOKEN=<从 .env 里读 SV_API_TOKEN>
HOST=<你的服务器 IP>

# WAV 上传
curl -X POST "http://$HOST:9820/asr" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@speech.wav"

# 裸 PCM（硬件直采，16kHz mono 16-bit）
curl -X POST "http://$HOST:9820/asr?sample_rate=16000" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@raw.pcm"
```

Python 端（`requests`）：
```python
import requests
r = requests.post(
    "http://HOST:9820/asr",
    headers={"Authorization": f"Bearer {TOKEN}"},
    files={"file": open("speech.wav", "rb")},
    timeout=10,
)
print(r.json()["text"])
```

## 性能实测（本机 8 核 Xeon 8173M，无 GPU）
| 音频长度 | 推理耗时 | 相对速度 |
|---|---|---|
| 5.5 s | ~360 ms | 15× 实时 |

- 内存：常驻 **~350 MB**（int8 onnx）
- 3 路并发（串行排队）：最坏 p99 ≈ 1.1 s，均能正常返回
- 建议单次说话 <15 s（超过会一次推理更久；硬件端配合 VAD 切句最理想）

## 目录结构
```
/root/sensevoice/
├── app.py              # FastAPI 服务
├── config.sh           # 环境变量
├── start.sh / stop.sh / status.sh / test.sh
├── models/
│   ├── model.int8.onnx # 229 MB
│   └── tokens.txt
├── logs/
│   ├── app.log
│   └── app.pid
└── test_zh.wav         # 冒烟测音频
```

## 开机自启（可选）
`/etc/systemd/system/sensevoice.service`：
```ini
[Unit]
Description=SenseVoiceSmall ASR API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/sensevoice
EnvironmentFile=/root/sensevoice/config.sh
ExecStart=/root/miniconda3/bin/python /root/sensevoice/app.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```
启用：
```bash
systemctl daemon-reload && systemctl enable --now sensevoice
# 之后用 systemctl start|stop|status sensevoice 代替本目录脚本
```

## 常见排错
- **端口占用**：`ss -lntp | grep 9820`
- **日志位置**：`tail -f /root/sensevoice/logs/app.log`
- **改了 token 不生效**：必须 `./stop.sh && ./start.sh`
- **防火墙**：确保云安全组放行 9820/tcp，或本机 `firewall-cmd --add-port=9820/tcp --permanent && firewall-cmd --reload`
- **安全提示**：token 是明文 header 传输，公网裸跑建议前置 Nginx 加 HTTPS；否则只在内网/VPN 暴露
