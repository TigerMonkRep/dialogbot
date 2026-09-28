#!/usr/bin/env bash
# Start the TTS service on a bare GPU pod (e.g. RunPod) from a git checkout, for measurements.
# Same steps as tts_service/Dockerfile, without building an image. Expects TTS_SERVICE_TOKEN and MODEL_REVISION in the
# environment. The model's own built-in voice (conds.pt at the pinned revision) is placed in local voice storage as
#   platform/voices/default/conds.pt   (designed_blend) so the service can be benchmarked without private voices.
set -euo pipefail
cd "$(dirname "$0")/.."
export DEBIAN_FRONTEND=noninteractive PIP_NO_CACHE_DIR=1 HF_HOME=${HF_HOME:-/models/hf}
apt-get update -q && apt-get install -y -q --no-install-recommends python3.11 python3.11-venv python3-pip git \
  libsndfile1 ffmpeg >/dev/null
python3.11 -m venv /opt/venv && . /opt/venv/bin/activate
pip install -q --upgrade pip && pip install -q --no-deps -r tts_service/requirements.lock
export VOICE_STORAGE=local VOICE_STORAGE_DIR=/srv/voice-store
python - <<'PY'
import os, shutil
from huggingface_hub import hf_hub_download
p = hf_hub_download("CoRal-project/roest-v3-chatterbox-500m", "conds.pt", revision=os.environ["MODEL_REVISION"])
d = "/srv/voice-store/platform/voices/default"
os.makedirs(d, exist_ok=True)
shutil.copy(p, f"{d}/conds.pt")
PY
export TTS_ENGINE=chatterbox MODEL_REPO=CoRal-project/roest-v3-chatterbox-500m MODEL_T3=t3_mtl23ls_v2.safetensors \
  TTS_DEVICE=cuda TTS_QUEUE_LIMIT=${TTS_QUEUE_LIMIT:-8}
exec uvicorn tts_service.app:app --host 0.0.0.0 --port 8080 --workers 1
