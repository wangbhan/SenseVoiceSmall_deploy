FROM python:3.10-slim-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_ENDPOINT=https://hf-mirror.com

RUN pip install -i https://pypi.tuna.tsinghua.edu.cn/simple \
        sherpa-onnx==2.0.1 \
        fastapi==0.162.0 \
        "uvicorn[standard]==0.54.0" \
        python-multipart==0.0.32 \
        numpy==2.2.6

COPY models/model.int8.onnx /app/models/model.int8.onnx
COPY models/tokens.txt /app/models/tokens.txt
COPY app.py /app/app.py

ENV SV_PORT=9820 \
    SV_MODEL_DIR=/app/models \
    SV_NUM_THREADS=4 \
    SV_MAX_SECONDS=60 \
    SV_API_TOKEN=""

EXPOSE 9820

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:9820/health',timeout=3)" || exit 1

CMD ["python", "/app/app.py"]
