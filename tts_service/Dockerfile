# Dialogbot TTS service – GPU image (CUDA 12.4 via torch 2.6.0 wheels from PyPI).
# Build:  docker build -f tts_service/Dockerfile -t dialogbot-tts .
# Run:    docker run --gpus all -p 8080:8080 -e TTS_SERVICE_TOKEN=... -e MODEL_REVISION=<40-hex commit> \
#                    -v tts-models:/models dialogbot-tts
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    HF_HOME=/models/hf PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends python3.11 python3.11-venv python3-pip git libsndfile1 ffmpeg \
    && rm -rf /var/lib/apt/lists/* && python3.11 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

WORKDIR /srv
COPY tts_service/requirements.lock /srv/requirements.lock
RUN pip install --upgrade pip && pip install --no-deps -r requirements.lock
COPY tts_service /srv/tts_service

# Model weights are NOT baked into the image: they are fetched at the pinned MODEL_REVISION on first start into the
# /models volume (reproducible, cached across restarts). The service refuses to start without a 40-hex revision.
ENV TTS_ENGINE=chatterbox MODEL_REPO=ResembleAI/chatterbox MODEL_T3=t3_mtl23ls_v3.safetensors TTS_DEVICE=cuda TTS_QUEUE_LIMIT=8
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=300s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')"
# One worker = one model instance on the GPU. Scale by adding replicas, not workers.
CMD ["uvicorn", "tts_service.app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
