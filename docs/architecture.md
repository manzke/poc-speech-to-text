# Architecture

```
 Browser (web app)                         Kubernetes cluster
┌───────────────────────┐         ┌──────────────────────────────────────┐
│ getUserMedia          │         │  Ingress (WSS, OIDC/bearer, WS upgrade)│
│ AudioWorklet (PCM)    │  wss    │            │                          │
│  16 kHz mono     ─────────────────────────▶  ▼                          │
│ partial/final render ◀────────────────────  WhisperLiveKit (Deployment) │
└───────────────────────┘  JSON   │   ┌──────────────────────────────┐   │
   @manzke/stt-web-sdk            │   │ FastAPI WS server (/asr)     │   │
                                    │   │ Silero VAD + VAC             │   │
                                    │   │ SimulStreaming (AlignAtt)    │   │
                                    │   │ faster-whisper (CTranslate2) │   │
                                    │   │ German Whisper — BAKED IN    │   │
                                    │   └──────────────────────────────┘   │
                                    │      ▲ nvidia.com/gpu (prod)          │
                                    │      │ CPU fallback (dev / no-GPU)    │
                                    └──────────────────────────────────────┘
```

## Data flow

1. The browser SDK (`clients/web-sdk`) calls `getUserMedia`, runs an
   `AudioWorklet` that downsamples to **16 kHz mono PCM16** and posts chunks to
   the main thread (`pcm-worklet.ts` + `resample.ts`).
2. `SttClient` streams those chunks as binary frames over **WSS** to
   `…/asr` (WhisperLiveKit's `--pcm-input` path, ADR-006).
3. The server runs **Silero VAD** then **SimulStreaming/AlignAtt** over the
   **faster-whisper** backend with the **baked German model**, pushing JSON
   partial/final messages back.
4. `SttClient` parses those messages (`parse.ts`, tolerant to WLK format drift)
   and emits typed `partial`/`final`/`ready` events to the app.

## Configuration is the only thing that varies (ADR-004)

The image, dependency lockfile, WhisperLiveKit version, API surface and baked
model are identical everywhere. `docker/entrypoint.sh` resolves the device
(`STT_DEVICE` override → `nvidia-smi`/torch detect → cpu), then `server/config.py`
turns the `STT_*` environment into the exact `wlk` argument vector. The backend
is pinned to `faster-whisper` so macOS does not silently switch to MLX.

| Env var | Meaning | Default |
|---|---|---|
| `STT_DEVICE` | `cuda` / `cpu` (else auto-detected) | auto |
| `STT_MODE` | `dictation` / `subtitles` (FR-2) | `dictation` |
| `STT_LANGUAGE` | Whisper language code (FR-4) | `de` |
| `STT_MODEL_PATH` | baked CT2 model dir | `/models/de-default` |
| `STT_FRAME_THRESHOLD` | SimulStreaming latency/accuracy knob (ADR-003) | 25 (dictation) / 20 (subtitles) |
| `STT_BEAMS` | beam size (1 = greedy) | 1 |
| `STT_FORWARDED_ALLOW_IPS` | trusted proxy IPs behind ingress | unset |
| `STT_EXTRA_ARGS` | extra `wlk` flags, shlex-split | unset |

## Why these choices

- **faster-whisper / CTranslate2** runs both CPU and CUDA from one install,
  which is what makes a single baked image viable across dev and prod.
- **SimulStreaming** emits fast partials and refines them — ideal for captions
  and snappy for dictation; `--frame-threshold` is the single latency/accuracy
  knob (ADR-003). LocalAgreement is the conservative fallback.
- **Translation and diarization are never built in** (ADR-008/010); the CI
  license gate (`scripts/check_licenses.py`) fails if their packages appear.
