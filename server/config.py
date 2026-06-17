"""Build the WhisperLiveKit (`wlk`) argument list from environment variables.

This module is intentionally dependency-free and side-effect-free so the flag
logic can be unit-tested without a GPU, the model, or WhisperLiveKit installed.
The container entrypoint (`docker/entrypoint.sh`) calls `python -m server.config`
to render the final command.

Design notes
------------
* WhisperLiveKit's CLI has **no** ``--device``/``--compute-type`` flag
  (verified against ``parse_args.py``). faster-whisper auto-detects CUDA via
  ``device="auto"``; we resolve the device ourselves only to (a) log it and
  (b) pick a sensible compute type and concurrency, surfaced through the env
  consumed by faster-whisper / CTranslate2.
* The backend is pinned to ``faster-whisper`` in every environment for dev/prod
  parity (ADR-004) — WhisperLiveKit would otherwise auto-select MLX on macOS.
* Translation and diarization flags are never emitted (ADR-008 / ADR-010).
"""

from __future__ import annotations

import os
import shlex
from typing import Mapping, Sequence

# Path the model is baked to inside the image (ADR-005). Overridable for the
# MIT fallback model or a mounted CT2 directory.
DEFAULT_MODEL_PATH = "/models/de-default"
DEFAULT_WARMUP_FILE = "/app/server/warmup/de_warmup.wav"

# Recognition modes map to WhisperLiveKit streaming policy + decoding choices.
#   dictation  -> snappy finalize-on-pause, greedy decoding
#   subtitles  -> continuously rolling partials (SimulStreaming, refine)
VALID_MODES = ("dictation", "subtitles")
VALID_DEVICES = ("cuda", "cpu")


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def resolve_compute_type(device: str, env: Mapping[str, str]) -> str:
    """Pick the CTranslate2 compute type for the resolved device.

    GPU -> float16 (NFR-4 fits the default model in <=8 GB VRAM).
    CPU -> int8 (the arm64/CPU dev build bakes the model quantized to int8).
    Overridable via ``STT_COMPUTE_TYPE`` for experimentation.
    """
    override = env.get("STT_COMPUTE_TYPE")
    if override:
        return override
    return "float16" if device == "cuda" else "int8"


def build_args(env: Mapping[str, str]) -> list[str]:
    """Return the ``wlk`` argument vector (excluding the ``wlk`` program name).

    Driven entirely by environment variables so deployment is configuration,
    never code (ADR-004 / §9). Recognized variables:

    ``STT_DEVICE``        cuda|cpu (resolved by the entrypoint; defaults cpu here)
    ``STT_MODE``          dictation|subtitles (default dictation)
    ``STT_LANGUAGE``      Whisper language code (default de; ADR-001/FR-4)
    ``STT_MODEL_PATH``    baked CT2 model dir (default /models/de-default)
    ``STT_WARMUP_FILE``   warmup wav for readiness gating (§10)
    ``STT_HOST``/``STT_PORT``
    ``STT_FRAME_THRESHOLD``  SimulStreaming latency/accuracy knob (ADR-003)
    ``STT_BEAMS``         beam size (default 1 = greedy, snappy dictation)
    ``STT_FORWARDED_ALLOW_IPS``  trusted proxy IPs behind the ingress (§10)
    ``STT_EXTRA_ARGS``    free-form extra flags appended verbatim (shlex-split)
    """
    device = (env.get("STT_DEVICE") or "cpu").strip().lower()
    if device not in VALID_DEVICES:
        raise ValueError(f"STT_DEVICE must be one of {VALID_DEVICES}, got {device!r}")

    mode = (env.get("STT_MODE") or "dictation").strip().lower()
    if mode not in VALID_MODES:
        raise ValueError(f"STT_MODE must be one of {VALID_MODES}, got {mode!r}")

    language = (env.get("STT_LANGUAGE") or "de").strip()
    model_path = env.get("STT_MODEL_PATH") or DEFAULT_MODEL_PATH
    warmup_file = env.get("STT_WARMUP_FILE") or DEFAULT_WARMUP_FILE
    host = env.get("STT_HOST") or "0.0.0.0"
    port = env.get("STT_PORT") or "8000"

    args: list[str] = [
        # Backend pinned for dev/prod parity (ADR-004).
        "--backend", "faster-whisper",
        # SimulStreaming/AlignAtt is the default policy (ADR-003).
        "--backend-policy", "simulstreaming",
        "--model-path", model_path,
        "--language", language,
        "--warmup-file", warmup_file,
        # Browser streams raw 16 kHz mono PCM, bypassing server-side ffmpeg (ADR-006).
        "--pcm-input",
        "--host", host,
        "--port", port,
    ]

    # Mode-specific tuning. Both modes use SimulStreaming; dictation favours a
    # snappy greedy decode, subtitles favour smoother rolling refinement.
    frame_threshold = env.get("STT_FRAME_THRESHOLD")
    beams = env.get("STT_BEAMS")
    if mode == "dictation":
        beams = beams or "1"
        frame_threshold = frame_threshold or "25"
    else:  # subtitles
        beams = beams or "1"
        # Slightly lower threshold => earlier partials for rolling captions.
        frame_threshold = frame_threshold or "20"
    args += ["--frame-threshold", frame_threshold, "--beams", beams]

    forwarded = env.get("STT_FORWARDED_ALLOW_IPS")
    if forwarded:
        args += ["--forwarded-allow-ips", forwarded]

    extra = env.get("STT_EXTRA_ARGS")
    if extra:
        args += shlex.split(extra)

    return args


def render_command(env: Mapping[str, str], program: str = "wlk") -> list[str]:
    """Full argv including the program name."""
    return [program, *build_args(env)]


def _summary(env: Mapping[str, str], device: str, compute_type: str) -> str:
    return (
        "[stt] resolved configuration: "
        f"device={device} compute_type={compute_type} "
        f"mode={env.get('STT_MODE', 'dictation')} "
        f"language={env.get('STT_LANGUAGE', 'de')} "
        f"model_path={env.get('STT_MODEL_PATH', DEFAULT_MODEL_PATH)}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Print the resolved ``wlk`` command as a shell-quoted line on stdout.

    The entrypoint captures stdout to build the command; diagnostics go to
    stderr so they never pollute the command line.
    """
    import sys

    env = os.environ
    device = (env.get("STT_DEVICE") or "cpu").strip().lower()
    compute_type = resolve_compute_type(device, env)
    print(_summary(env, device, compute_type), file=sys.stderr)

    cmd = render_command(env)
    # Shell-quoted so the entrypoint can `eval` it safely.
    print(" ".join(shlex.quote(part) for part in cmd))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
