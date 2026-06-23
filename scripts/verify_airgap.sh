#!/usr/bin/env bash
# Air-gap verification (FR-6 / PRD §17 acceptance criterion).
#
# Runs the built image with NO network at all (`--network none`) and proves it
# (a) reaches readiness with the model baked in and (b) transcribes audio — i.e.
# it makes zero outbound calls at runtime. Because the container has no network,
# the checks run *inside* it via `docker exec` (no host port mapping needed).
#
# Usage:
#   scripts/verify_airgap.sh [IMAGE]
#
# Env:
#   IMAGE          image to test (default: stt:airgap-test; arg overrides)
#   BUILD          if "1", build the image first (CPU variant) before testing
#   READY_TIMEOUT  seconds to wait for readiness (default 240; CPU model warmup)
#   AUDIO_FILE     in-container path to a wav (default: baked warmup clip)
set -euo pipefail

IMAGE="${1:-${IMAGE:-stt:airgap-test}}"
READY_TIMEOUT="${READY_TIMEOUT:-240}"
AUDIO_FILE="${AUDIO_FILE:-/app/server/warmup/de_warmup.wav}"
NAME="stt-airgap-$$"

log() { echo "[airgap] $*"; }
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

if [ "${BUILD:-0}" = "1" ]; then
    log "building $IMAGE (CPU variant)"
    docker build -f docker/Dockerfile --build-arg STT_BUILD_VARIANT=cpu -t "$IMAGE" .
fi

# --network none => the container cannot make ANY outbound (or inbound) calls.
log "starting container with --network none from $IMAGE"
docker run -d --network none --name "$NAME" "$IMAGE" >/dev/null

# Belt-and-suspenders: assert the container truly has no usable network.
if docker exec "$NAME" sh -c 'getent hosts huggingface.co' >/dev/null 2>&1; then
    log "FAIL: DNS resolved inside the container — network is not isolated"
    docker logs "$NAME" 2>&1 | tail -30 || true
    exit 1
fi
log "confirmed: no DNS / no egress inside the container"

# Wait for readiness: the HTTP root responds only after model load + warmup.
log "waiting up to ${READY_TIMEOUT}s for readiness (model warmup)…"
deadline=$(( $(date +%s) + READY_TIMEOUT ))
ready=0
while [ "$(date +%s)" -lt "$deadline" ]; do
    if docker exec "$NAME" sh -c 'curl -fsS http://localhost:8000/ >/dev/null 2>&1'; then
        ready=1
        break
    fi
    if [ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" != "true" ]; then
        log "FAIL: container exited during warmup"
        docker logs "$NAME" 2>&1 | tail -40 || true
        exit 1
    fi
    sleep 5
done
if [ "$ready" != "1" ]; then
    log "FAIL: not ready within ${READY_TIMEOUT}s"
    docker logs "$NAME" 2>&1 | tail -40 || true
    exit 1
fi
log "ready ✓ (model loaded with no network)"

# Functional check: transcribe via the OpenAI-compatible REST endpoint.
log "transcribing baked clip via /v1/audio/transcriptions…"
resp="$(docker exec "$NAME" sh -c \
    "curl -fsS -F file=@${AUDIO_FILE} http://localhost:8000/v1/audio/transcriptions")" || {
    log "FAIL: transcription request errored"
    docker logs "$NAME" 2>&1 | tail -40 || true
    exit 1
}
log "response: ${resp}"

# Accept any 200 JSON that carries a "text" field (may be empty for a silent clip).
echo "$resp" | docker exec -i "$NAME" python -c \
    'import sys,json; d=json.load(sys.stdin); assert "text" in d, d; print("[airgap] transcript field present ✓")' || {
    log "FAIL: response did not contain a JSON transcript"
    exit 1
}

log "PASS: air-gapped image reached readiness and transcribed with zero egress"
