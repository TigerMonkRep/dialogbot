# Dialogbot browser worker – Playwright + Chromium (headless), Python 3.12 (Ubuntu noble).
# Build (from the repository root):  docker build -f browser_worker/Dockerfile -t dialogbot-browser-worker .
# The image tag of the base MUST match the playwright version in browser_worker/requirements.lock.
FROM mcr.microsoft.com/playwright/python:v1.64.1-noble

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# ffmpeg: the evidence video is trimmed to BROWSER_MAX_SECONDS before upload.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-liberation && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.lock /srv/requirements.lock
COPY browser_worker/requirements.lock /srv/browser_worker/requirements.lock
# The base image ships playwright + the matching Chromium; pin everything else exactly as locked.
RUN pip install --no-deps -r requirements.lock -r browser_worker/requirements.lock
COPY app /srv/app
COPY browser_worker /srv/browser_worker

# One Playwright browser context per run, no shared state; the process runs as the unprivileged image user.
USER pwuser
CMD ["python", "-m", "browser_worker.runner"]
