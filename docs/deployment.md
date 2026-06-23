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
