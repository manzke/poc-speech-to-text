# Development

## Prerequisites
- Docker (with buildx) for the image; Python 3.11 + Node 20 for the test suites.
- A 16 kHz mono German warmup clip at `server/warmup/de_warmup.wav` before
  building the image (see `server/warmup/README.md`).

## Fast inner loop (no image build)

The flag logic and SDK are testable without a GPU, the model, or WhisperLiveKit:

```bash
# Server-side arg builder + entrypoint device resolution
pip install pytest
python -m pytest tests/test_config.py -q
bash tests/test_entrypoint.sh          # prints the resolved `wlk` command

# Browser SDK
cd clients/web-sdk
npm install && npm run build && npm test
```

## Run the service locally (CPU)

```bash
# From repo root. Builds the arm64/CPU image with the model baked in.
docker compose -f docker/compose.yaml --profile cpu up --build
```

Then open `clients/web-sdk/examples/index.html` (served over http://localhost
or file://; mic needs a secure context for non-localhost) and point it at
`ws://localhost:8000/asr`. Speak German → partial then final transcripts.

## Dev/prod parity & the Apple-Silicon caveat (ADR-004)

- The **same image** runs on a Mac (arm64/CPU, INT8) and a prod GPU node
  (amd64/CUDA, FP16). Only the resolved device, compute type and per-arch model
  quantization differ — never code.
- **GPU acceleration does not light up inside containers on Apple Silicon.** You
  get *functional* parity locally (correctness, API, message format) at lower
  speed; do **performance** validation (NFR-1/2/3) on a shared GPU dev node.
- We deliberately **reject** running the amd64 image under qemu on a Mac (ML
  inference under emulation is unusably slow). MLX is an optional, documented
  dev-only accelerator for developers who opt out of parity for speed.

## Building the multi-arch image

```bash
docker buildx build -f docker/Dockerfile \
  --platform linux/amd64,linux/arm64 \
  --build-arg MODEL_ID=primeline/whisper-large-v3-turbo-german \
  -t ghcr.io/manzke/poc-speech-to-text:dev .
```

The build downloads the HF model once and bakes the converted CTranslate2
directory into the image (ADR-005). For the MIT base fallback, pass
`--build-arg MODEL_ID=openai/whisper-large-v3`.
