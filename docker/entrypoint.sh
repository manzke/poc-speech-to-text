#!/usr/bin/env bash
# Container entrypoint: resolve the runtime device, then launch WhisperLiveKit.
#
# Dev/prod parity (ADR-004): the SAME image runs on a developer Mac (CPU) and a
# prod GPU node (CUDA). The only runtime difference is the auto-detected device
# and the resulting compute type. The backend is pinned to faster-whisper.
#
# Device resolution order:
#   1. STT_DEVICE env override (cuda | cpu)
#   2. nvidia-smi present and working          -> cuda
#   3. torch reports CUDA available            -> cuda
#   4. otherwise                               -> cpu
#
# Set STT_DRY_RUN=1 to print the resolved command and exit (used by tests/CI).
set -euo pipefail

log() { echo "[entrypoint] $*" >&2; }

resolve_device() {
    if [ -n "${STT_DEVICE:-}" ]; then
        echo "${STT_DEVICE}"
        return
    fi
    if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
        echo "cuda"
        return
    fi
    if python - <<'PY' >/dev/null 2>&1
import sys
try:
    import torch
    sys.exit(0 if torch.cuda.is_available() else 1)
except Exception:
    sys.exit(1)
PY
    then
        echo "cuda"
        return
    fi
    echo "cpu"
}

STT_DEVICE="$(resolve_device)"
export STT_DEVICE
log "resolved device: ${STT_DEVICE}"

# Render the wlk command (server/config.py logs the full config summary to stderr
# and prints the shell-quoted command on stdout).
CMD="$(python -m server.config)"
log "launching: ${CMD}"

if [ "${STT_DRY_RUN:-0}" = "1" ]; then
    echo "${CMD}"
    exit 0
fi

# exec so wlk becomes PID 1 and receives signals (clean k8s shutdown).
exec bash -c "exec ${CMD}"
