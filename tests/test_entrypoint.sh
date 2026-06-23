#!/usr/bin/env bash
# Smoke test for docker/entrypoint.sh device resolution + dry-run command render.
# Runs without WhisperLiveKit/GPU: STT_DRY_RUN=1 prints the command and exits.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() { echo "FAIL: $*" >&2; exit 1; }

# CPU override: device must resolve to cpu and command must pin faster-whisper.
out_cpu="$(STT_DRY_RUN=1 STT_DEVICE=cpu PYTHONPATH="$ROOT" bash docker/entrypoint.sh)"
echo "$out_cpu" | grep -q -- "--backend faster-whisper" || fail "cpu: backend not pinned"
echo "$out_cpu" | grep -q -- "--pcm-input" || fail "cpu: --pcm-input missing"
echo "$out_cpu" | grep -q -- "--language de" || fail "cpu: default language not de"

# CUDA override resolves cuda and still renders a command.
out_gpu="$(STT_DRY_RUN=1 STT_DEVICE=cuda PYTHONPATH="$ROOT" bash docker/entrypoint.sh)"
echo "$out_gpu" | grep -q -- "--backend-policy simulstreaming" || fail "gpu: policy missing"

# Subtitles mode tweaks the frame threshold.
out_sub="$(STT_DRY_RUN=1 STT_DEVICE=cpu STT_MODE=subtitles PYTHONPATH="$ROOT" bash docker/entrypoint.sh)"
echo "$out_sub" | grep -q -- "--frame-threshold 20" || fail "subtitles: frame-threshold not 20"

echo "PASS: entrypoint dry-run renders expected commands"
