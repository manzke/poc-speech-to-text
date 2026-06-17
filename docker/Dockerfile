# syntax=docker/dockerfile:1.7
#
# Single multi-arch image for the self-hosted STT service (ADR-004/005).
#
#   * linux/amd64 -> CUDA stack (WhisperLiveKit[cu129]); runs the GPU in prod,
#                    transparently falls back to CPU on a CPU-only Linux node.
#   * linux/arm64 -> CPU stack (WhisperLiveKit[cpu]); for Apple-Silicon dev.
#
# The German model is converted to CTranslate2 and BAKED IN at build time, so
# there is no Hugging Face egress at runtime (FR-6). Same image, lockfile,
# WhisperLiveKit version and API everywhere; only the arch variant, resolved
# device and per-arch model quantization differ.
#
# Build (multi-arch, from repo root):
#   docker buildx build -f docker/Dockerfile \
#     --platform linux/amd64,linux/arm64 \
#     --build-arg MODEL_ID=primeline/whisper-large-v3-turbo-german \
#     -t ghcr.io/manzke/poc-speech-to-text:dev .

ARG PYTHON_VERSION=3.11
ARG WHISPERLIVEKIT_VERSION=0.2.22

FROM python:${PYTHON_VERSION}-slim AS base
ARG WHISPERLIVEKIT_VERSION
# TARGETARCH is provided automatically by buildx (amd64 | arm64).
ARG TARGETARCH

# Default model is the Apache-2.0 German turbo fine-tune (ADR-001).
# Override with openai/whisper-large-v3 for the MIT base fallback.
ARG MODEL_ID=primeline/whisper-large-v3-turbo-german

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    PYTHONPATH=/app

# ffmpeg is a WhisperLiveKit runtime dep for the non-PCM path; curl for probes.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Dependency install: arch-specific WhisperLiveKit extra (ADR-004) ---------
# amd64 -> CUDA extra (cu129); arm64 -> CPU extra. We deliberately do NOT install
# the [translation] or [diarization-*] extras (ADR-008 / ADR-010 / license gate).
RUN if [ "$TARGETARCH" = "amd64" ]; then \
        pip install "whisperlivekit[cu129]==${WHISPERLIVEKIT_VERSION}" ctranslate2 ; \
    else \
        pip install "whisperlivekit[cpu]==${WHISPERLIVEKIT_VERSION}" ctranslate2 ; \
    fi

# --- Bake the model (ADR-005) -------------------------------------------------
# Per-arch quantization: float16 on the GPU build, int8 on the CPU build (§9).
COPY scripts/convert_model.py /app/scripts/convert_model.py
RUN MODEL_QUANTIZATION=$([ "$TARGETARCH" = "amd64" ] && echo float16 || echo int8) \
    && python /app/scripts/convert_model.py \
        --model-id "${MODEL_ID}" \
        --output /models/de-default \
        --quantization "${MODEL_QUANTIZATION}"

# --- Application code ---------------------------------------------------------
COPY server/ /app/server/
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Fail fast if the required warmup clip was not provided at build time.
RUN test -f /app/server/warmup/de_warmup.wav \
    || (echo "ERROR: server/warmup/de_warmup.wav missing — see server/warmup/README.md" && exit 1)

# Configuration is entirely environment-driven (§9). Sensible prod defaults:
ENV STT_MODE=dictation \
    STT_LANGUAGE=de \
    STT_MODEL_PATH=/models/de-default \
    STT_WARMUP_FILE=/app/server/warmup/de_warmup.wav \
    STT_HOST=0.0.0.0 \
    STT_PORT=8000

EXPOSE 8000

# No audio/transcripts persisted; no telemetry egress (NFR-8 / §13).
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD curl -fsS http://localhost:8000/ >/dev/null || exit 1

ENTRYPOINT ["/entrypoint.sh"]
