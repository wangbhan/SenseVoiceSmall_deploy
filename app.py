import io
import os
import re
import time
import wave
import threading
from typing import Optional

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

app = FastAPI(title="SenseVoiceSmall API", version="1.0")


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
    return {"ok": True, "model": "SenseVoiceSmall-int8"}


@app.post("/asr")
async def asr(
    file: UploadFile = File(...),
    sample_rate: int = Query(16000, description="raw PCM 时使用；WAV 会忽略"),
    authorization: Optional[str] = Header(None),
):
    _auth(authorization)
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty body")

    audio = _decode(data, sample_rate)
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

    def _clean(s):
        m = re.fullmatch(r"<\|([^|]*)\|>", (s or "").strip())
        return m.group(1) if m else (s or "")
    return JSONResponse({
        "text": text,
        "language": _clean(lang),
        "emotion": _clean(emo),
        "event": _clean(evt),
        "duration": round(duration, 3),
        "infer_ms": round(infer_ms, 1),
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("SV_PORT", "9820")), log_level="info")
