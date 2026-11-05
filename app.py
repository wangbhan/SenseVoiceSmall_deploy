import io
import os
import re
import time
import wave
import logging
import threading
from typing import Optional

log = logging.getLogger("sensevoice")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

import numpy as np
import sherpa_onnx
from fastapi import FastAPI, File, UploadFile, Header, HTTPException, Query
from fastapi.responses import JSONResponse

MODEL_DIR = os.environ.get("SV_MODEL_DIR", "/root/sensevoice/models")
API_TOKEN = os.environ.get("SV_API_TOKEN", "")
MAX_SECONDS = float(os.environ.get("SV_MAX_SECONDS", "60"))
NUM_THREADS = int(os.environ.get("SV_NUM_THREADS", "4"))

rec = sherpa_onnx.OfflineRecognizer.from_sense_voice(
    model=os.path.join(MODEL_DIR, "model.int8.onnx"),
    tokens=os.path.join(MODEL_DIR, "tokens.txt"),
    num_threads=NUM_THREADS,
    sample_rate=16000,
    feature_dim=80,
    use_itn=True,
    debug=False,
)
lock = threading.Lock()

_recent = []
_recent_lock = threading.Lock()


def _record(info: dict):
    with _recent_lock:
        _recent.append(info)
        if len(_recent) > 100:
            _recent.pop(0)


app = FastAPI(title="SenseVoiceSmall API", version="1.1")


def _auth(authorization: Optional[str]):
    if not API_TOKEN:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    if authorization[7:] != API_TOKEN:
        raise HTTPException(403, "invalid token")


def _decode(data: bytes, sample_rate: int) -> np.ndarray:
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            sr = w.getframerate()
            n_ch = w.getnchannels()
            sw = w.getsampwidth()
            n_fr = w.getnframes()
            raw = w.readframes(n_fr)
        if sw == 2:
            audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        elif sw == 4:
            audio = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
        elif sw == 1:
            audio = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        else:
            raise HTTPException(415, f"unsupported sample width: {sw}")
        if n_ch > 1:
            audio = audio.reshape(-1, n_ch).mean(axis=1).astype(np.float32)
    except wave.Error:
        audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        sr = sample_rate
    if sr != 16000:
        n_out = int(len(audio) * 16000 / sr)
        idx = np.linspace(0, len(audio) - 1, n_out)
        audio = np.interp(idx, np.arange(len(audio)), audio).astype(np.float32)
    return audio


@app.get("/health")
def health():
    return {"ok": True, "model": "SenseVoiceSmall-int8", "supports_stream": False}


@app.get("/metrics/recent")
def metrics_recent(limit: int = 20):
    with _recent_lock:
        items = list(_recent)
    if not items:
        summary = {}
    else:
        infer = [x["infer_ms"] for x in items]
        total = [x["total_ms"] for x in items]
        summary = {
            "n": len(items),
            "infer_ms_avg": round(sum(infer)/len(infer)),
            "infer_ms_p95": sorted(infer)[int(len(infer)*0.95)] if len(infer) > 1 else infer[0],
            "total_ms_avg": round(sum(total)/len(total)),
        }
    return {"summary": summary, "requests": items[-limit:][::-1]}


@app.post("/asr")
async def asr(
    file: UploadFile = File(...),
    sample_rate: int = Query(16000, description="raw PCM 时使用；WAV 会忽略"),
    authorization: Optional[str] = Header(None),
    x_request_id: Optional[str] = Header(None),
):
    req_t0 = time.perf_counter()
    req_id = x_request_id or f"r{int(req_t0*1000)%100000:x}"
    _auth(authorization)
    t_upload = time.perf_counter()
    data = await file.read()
    upload_ms = (time.perf_counter() - t_upload) * 1000
    if not data:
        raise HTTPException(400, "empty body")

    t_dec = time.perf_counter()
    audio = _decode(data, sample_rate)
    decode_ms = (time.perf_counter() - t_dec) * 1000
    duration = len(audio) / 16000.0
    if duration > MAX_SECONDS:
        raise HTTPException(413, f"audio too long: {duration:.1f}s > {MAX_SECONDS}s")

    t0 = time.perf_counter()
    with lock:
        stream = rec.create_stream()
        stream.accept_waveform(16000, audio)
        rec.decode_stream(stream)
        text = stream.result.text
        lang = stream.result.lang
        emo = stream.result.emotion
        evt = stream.result.event
    infer_ms = (time.perf_counter() - t0) * 1000
    total_ms = (time.perf_counter() - req_t0) * 1000

    def _clean(s):
        m = re.fullmatch(r"<\|([^|]*)\|>", (s or "").strip())
        return m.group(1) if m else (s or "")

    log.info(f"[{req_id}] upload={upload_ms:.0f}ms decode={decode_ms:.0f}ms infer={infer_ms:.0f}ms total={total_ms:.0f}ms dur={duration:.2f}s bytes={len(data)}")
    _record({
        "req_id": req_id, "upload_ms": round(upload_ms), "decode_ms": round(decode_ms),
        "infer_ms": round(infer_ms), "total_ms": round(total_ms),
        "audio_sec": round(duration, 3), "bytes": len(data),
    })

    headers = {
        "X-Upload-Ms": f"{upload_ms:.0f}",
        "X-Decode-Ms": f"{decode_ms:.0f}",
        "X-Infer-Ms": f"{infer_ms:.0f}",
        "X-Total-Ms": f"{total_ms:.0f}",
        "X-Request-Id": req_id,
        "Server-Timing": f"upload;dur={upload_ms:.0f}, decode;dur={decode_ms:.0f}, infer;dur={infer_ms:.0f}, total;dur={total_ms:.0f}",
    }
    return JSONResponse({
        "text": text,
        "language": _clean(lang),
        "emotion": _clean(emo),
        "event": _clean(evt),
        "duration": round(duration, 3),
        "infer_ms": round(infer_ms, 1),
        "upload_ms": round(upload_ms, 1),
        "decode_ms": round(decode_ms, 1),
        "total_ms": round(total_ms, 1),
    }, headers=headers)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("SV_PORT", "9820")), log_level="info")
