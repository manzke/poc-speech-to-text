# Deployment (Kubernetes)

The service ships as a Helm chart under `helm/stt`. The image is identical
across tiers (ADR-004); only env and GPU scheduling differ.

## GPU (production)

```bash
helm install stt ./helm/stt -f helm/stt/values-gpu.yaml \
  --set image.tag=v0.1.0 \
  --set ingress.enabled=true \
  --set ingress.host=stt.example.com
```

`values-gpu.yaml` sets `STT_DEVICE=cuda` and requests `nvidia.com/gpu: 1`
(rendered onto the container's resource limits by the deployment template). The
NVIDIA device plugin must be installed and a consumer/prosumer GPU node pool
(24–96 GB, PRD §11) available.

## CPU (no-GPU customers, ADR-007)

```bash
helm install stt ./helm/stt -f helm/stt/values-cpu.yaml
```

Large models are not real-time on CPU; document the smaller-model trade-off and,
if needed, build the image with a smaller `MODEL_ID`.

## Ingress / WebSocket

The chart's ingress template adds the nginx WebSocket annotations and long
proxy timeouts needed for streaming `/asr` connections (PRD §10). Terminate WSS
at the edge, enforce OIDC/bearer auth in front of `/asr`, and set
`config.forwardedAllowIps` to your proxy CIDR so WhisperLiveKit trusts the
`X-Forwarded-*` headers.

## Authentication (PRD §13)

WhisperLiveKit has no built-in auth, so the chart ships an optional **auth
gateway** (`server/auth_gateway.py`) that runs from the same image and is wired
to the ingress via an nginx `auth_request`. Every request — including the `/asr`
WebSocket upgrade — is sub-requested to the gateway, which returns 200/401; the
audio stream itself never passes through it (no added latency).

Token sources: `Authorization: Bearer <token>` or `?token=<token>` (the SDK uses
the query form because browsers can't set WS handshake headers).

Static shared token:

```bash
helm install stt ./helm/stt -f helm/stt/values-gpu.yaml \
  --set ingress.enabled=true --set auth.enabled=true \
  --set auth.mode=static --set auth.token=$(openssl rand -hex 24)
```

HS256 JWT (validate tokens minted by your IdP/app):

```bash
helm install stt ./helm/stt -f helm/stt/values-gpu.yaml \
  --set ingress.enabled=true --set auth.enabled=true \
  --set auth.mode=jwt --set auth.jwtSecret=<hs256-secret> \
  --set auth.jwtAudience=stt --set auth.jwtIssuer=https://idp.example
```

For production, prefer `auth.existingSecret` (a Secret you manage) over inline
values. Full OIDC (RS256/JWKS, login redirect) is best handled by fronting the
gateway with `oauth2-proxy`; the gateway covers static-token and HS256-JWT today.

## Air-gap verification (FR-6)

`scripts/verify_airgap.sh` runs the built image with **`--network none`** and
asserts it (a) reaches readiness with the baked model and (b) transcribes — i.e.
makes zero outbound calls. Because the container has no network, the checks run
inside it via `docker exec`.

```bash
BUILD=1 scripts/verify_airgap.sh stt:airgap-test   # build then verify
# or, against a prebuilt image:
scripts/verify_airgap.sh ghcr.io/manzke/poc-speech-to-text:<tag>
```

Wire it into CI as a job (workflow files must be added by a maintainer with the
`workflows` permission):

```yaml
  airgap:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: BUILD=1 IMAGE=stt:airgap-test bash scripts/verify_airgap.sh
```

## Readiness / warmup

Readiness and liveness probes hit the HTTP root. With `--warmup-file` set
(default), WhisperLiveKit loads the model and runs one decode before serving, so
the pod only becomes Ready once the slow first inference is done (PRD §10). The
probe `initialDelaySeconds`/`failureThreshold` in `values.yaml` allow for model
load time — increase them for the larger fallback model.

## Air-gap (FR-6)

- Weights are **baked into the image** — no runtime Hugging Face egress.
- Mirror the image and the Helm chart into the customer's internal registry.
- Verify in CI / staging with egress blocked: the pod must reach Ready and
  transcribe with no outbound connections.

## Scaling (Phase 2)

`autoscaling.enabled=true` renders an HPA. Today it targets CPU; Phase 2
replaces that with a custom concurrent-stream / queue-depth metric once load
testing sets NFR-6 (PRD §10/§15). VAD already suppresses idle compute.

## Observability (Phase 2)

Planned metrics (PRD §14): active streams, queue depth, RTF, partial/final
latency, GPU/CPU utilization, VAD speech ratio; structured logs/traces for the
session lifecycle with **no audio/PII**. Optional Langfuse/OTel hooks.
