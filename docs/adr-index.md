# ADR index

Architecture Decision Records from the PRD (`docs/prd.md` §8) and where each is
realized in this repository.

| ADR | Decision | Realized in |
|---|---|---|
| ADR-001 | German fine-tune (`primeline/whisper-large-v3-turbo-german`, Apache-2.0) default; `whisper-large-v3` (MIT) fallback; baked in | `scripts/convert_model.py`, `docker/Dockerfile` (`MODEL_ID`) |
| ADR-002 | WhisperLiveKit + `--backend faster-whisper` as the serving layer | `server/config.py`, `docker/Dockerfile` (pinned `0.2.22`) |
| ADR-003 | SimulStreaming (AlignAtt) default; `--frame-threshold`/`--beams` knobs; LocalAgreement fallback | `server/config.py` (`build_args`) |
| ADR-004 | One multi-arch image, device auto-detect, backend pinned for parity | `docker/Dockerfile`, `docker/entrypoint.sh` |
| ADR-005 | Model weights baked at build time, no runtime egress | `docker/Dockerfile` (convert step), `scripts/convert_model.py` |
| ADR-006 | WSS transport, browser-side 16 kHz mono PCM, `--pcm-input` | `clients/web-sdk` (`pcm-worklet.ts`, `SttClient.ts`) |
| ADR-007 | CPU-only tier from the same codebase | `helm/stt/values-cpu.yaml`, `docker/compose.yaml` (cpu profile) |
| ADR-008 | Translation out of scope; NLLB extra not installed | `docker/Dockerfile` (no `[translation]`), `scripts/check_licenses.py` |
| ADR-009 | Strict-permissive dependency posture, CI gate | `.github/workflows/license-gate.yml`, `scripts/check_licenses.py` |
| ADR-010 | Diarization deferred; gated pyannote excluded | `docker/Dockerfile` (no `[diarization-*]`), `scripts/check_licenses.py` (forbidden list) |

## Notable spike item (PRD §15 risk register)

WhisperLiveKit's CLI exposes **no `--device`/`--compute-type` flag** (verified
against `parse_args.py` on `0.2.22`). faster-whisper auto-detects CUDA via
`device="auto"`; our `entrypoint.sh` resolves and logs the device and picks the
compute type. Confirm during the Phase-0 spike that the faster-whisper backend
honors the resolved device and that the SimulStreaming alignment-head packaging
works with the baked CT2 model — fall back to `--backend-policy localagreement`
if SimulStreaming packaging proves troublesome (ADR-003).
