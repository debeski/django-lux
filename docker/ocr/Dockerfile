# DjangoLux OCR service (debeski/dlux-ocr): Indra OCR behind a small internal HTTP API.
# Build context is this folder: docker build -t debeski/dlux-ocr docker/ocr
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    INDRA_OCR_MODEL_DIR=/opt/indra/models \
    INDRA_OCR_MODEL_REVISION=v1.1.0

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY fetch_models.py .
RUN python fetch_models.py

# Models are baked in; the container must never reach Hugging Face at runtime.
ENV HF_HUB_OFFLINE=1 \
    OCR_PORT=8080

COPY engines.py server.py NOTICE ./
RUN useradd --system --uid 10001 --home-dir /srv ocr
USER ocr

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=5).read()"]

CMD ["python", "server.py"]
