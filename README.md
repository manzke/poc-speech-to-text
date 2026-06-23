# poc-speech-to-text

Self-hosted **speech-to-text** service for web applications — **dictation** and
**real-time subtitles** — that keeps audio on your own infrastructure. It
replaces the Chrome Web Speech API (which streams mic audio to Google) with a
drop-in WebSocket API you host yourself, air-gap deployable under permissive
component licenses.

Built on **[WhisperLiveKit](https://github.com/QuentinFuxa/WhisperLiveKit)**
(Apache-2.0) with the **faster-whisper** backend and a **German-fine-tuned
Whisper model baked into a single container image** that runs unchanged on a
developer's Mac (CPU) and a production GPU node (CUDA).

> Status: **Phase-0 foundation** (see `docs/prd.md` §16). The repository scaffolding,
> baked-image build, device-autodetect entrypoint, browser SDK, Helm chart and CI
> are in place. GPU performance validation, autoscaling, observability and a pilot
> integration are later phases.

## What's here

| Path | What |
|---|---|
| `docker/Dockerfile` | One multi-arch image (amd64/CUDA, arm64/CPU), model **baked in** (ADR-004/005) |
| `docker/entrypoint.sh` | Resolves device (cuda/cpu) and launches WhisperLiveKit |
| `server/config.py` | Pure, tested builder of the `wlk` argument vector from `STT_*` env |
| `scripts/convert_model.py` | HF → CTranslate2 model conversion (int8 CPU / float16 GPU) |
| `scripts/check_licenses.py` | CI gate: shipped deps must be Apache/MIT/BSD (NFR-7/ADR-009) |
| `scripts/verify_airgap.sh` | Runs the image with egress blocked and asserts readiness + transcription (FR-6) |
| `server/auth_gateway.py` | Ingress `auth_request` validator (static bearer / HS256 JWT) in front of `/asr` (§13) |
| `clients/web-sdk/` | TypeScript browser SDK: mic → 16 kHz PCM → WSS, typed partial/final events |
| `examples/web-app/` | React + Vite reference app: dictation & live captions via the SDK |
| `helm/stt/` | Helm chart with CPU/GPU presets and optional auth gateway |
| `docs/` | PRD, ADR index, architecture, development, deployment |

## Quickstart (local CPU)

```bash
# 1. Provide a warmup clip (see server/warmup/README.md)
# 2. Run the service (builds the image with the German model baked in)
docker compose -f docker/compose.yaml --profile cpu up --build

# 3. Open clients/web-sdk/examples/index.html, point it at ws://localhost:8000/asr,
#    and speak German.
```

## Develop & test (no image build needed)

```bash
pip install pytest && python -m pytest tests/test_config.py -q && bash tests/test_entrypoint.sh
cd clients/web-sdk && npm install && npm run build && npm test
helm lint helm/stt
```

See **`docs/development.md`** for the dev/prod parity model and the Apple-Silicon
GPU caveat, and **`docs/deployment.md`** for Kubernetes/Helm and air-gap notes.

## Licensing

This repository's own wrapper code is **AGPL-3.0** (see `LICENSE`). The PRD's
"strict permissive" requirement (NFR-7/ADR-009) applies to the **third-party
components we redistribute** — WhisperLiveKit (Apache-2.0), faster-whisper/
CTranslate2 (MIT), Whisper (MIT), the primeline German model (Apache-2.0),
Silero VAD (MIT). The CI license gate (`scripts/check_licenses.py`) enforces
that the *dependency tree* stays permissive and that translation/diarization
extras (CC-BY-NC / gated) never enter the build.
