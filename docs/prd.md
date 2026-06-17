# PRD — Self-Hosted Speech-to-Text Service for Web Applications

| | |
|---|---|
| **Status** | Draft for review |
| **Version** | 0.4 |
| **Owner** | Head of Engineering |
| **Last updated** | 17 June 2026 |
| **Reviewers** | Architecture, Product, Security/Compliance |
| **Related** | "Self-Hosted Permissively-Licensed German STT" evaluation report (2026) |

> **Changelog v0.4** — Translation removed from scope (handled by the consuming applications). Drops the NLLB/NLLW (CC-BY-NC) dependency from consideration entirely.
>
> **Changelog v0.3** — Inference engine fixed as **faster-whisper**; serving framework adopted as **WhisperLiveKit** (Apache-2.0) after review of the project and its capabilities. vLLM dropped. Model weights **baked into the image**. Single-image dev↔prod parity restored (faster-whisper runs CPU on Mac, CUDA in prod from one codebase).

---

## 1. Summary

We will build a self-hosted speech-to-text (STT) service that any of our web applications — and our customers' self-hosted deployments — can use for **dictation** and **real-time subtitles/captions**. It replaces the browser's native Chrome Web Speech API, whose fatal flaw for our market is that audio is sent to Google.

The service is **WhisperLiveKit** (Apache-2.0) configured with the **faster-whisper** backend, running a **German-fine-tuned Whisper model under a permissive license**, with the **model weights baked into a single container image** used unchanged across local development and production. The only difference between a developer's MacBook and a production GPU node is runtime configuration (CPU/INT8 vs. CUDA/FP16), selected automatically.

The whole point is data sovereignty: for public-sector, defense, financial-regulator, and large-industrial customers, audio must never leave the customer's infrastructure, and the stack must be air-gap deployable under a permissive (Apache/MIT) license.

---

## 2. Problem & context

Our web applications (e.g. iAssistant) increasingly need voice input and live captioning. The native browser API is fine for prototypes but disqualified in production: Chrome's Web Speech API streams microphone audio to Google. The existing on-prem alternative (an older Azure speech container) is subscription-locked and dated. Customers require **on-premise / air-gapped** capability and a license that lets us and them self-host and redistribute without per-seat cloud fees.

We completed an engine/model evaluation (see related report). This PRD turns that evaluation into a buildable product with explicit architecture decisions.

---

## 3. Goals & non-goals

### Goals
- A self-hostable STT service exposing a streaming WebSocket API consumable from the browser, replacing the Web Speech API drop-in.
- Strong **German** accuracy first; broad European-language coverage second.
- Near-real-time: a few seconds of latency acceptable; responsive for dictation and usable for live subtitles.
- Runs on **consumer/prosumer GPUs (24–96 GB)**; **CPU-only operation supported** (slower) as a deployment option.
- **Permissive license** (Apache-2.0 / MIT / BSD) across model weights and all framework code, safe for customer redistribution.
- **One container image for dev and prod** with weights baked in — identical artifact, environment-driven configuration.
- Kubernetes-native deployment with GPU scheduling and horizontal scaling.

### Non-goals (this version)
- Speaker diarization ("who spoke when") — available in WhisperLiveKit but deferred (see ADR-010).
- Custom acoustic/vocabulary fine-tuning on customer data (future; LoRA path noted in ADR-001).
- Sub-300 ms "voice-agent"-grade latency.
- A managed/multi-tenant SaaS offering.
- Wake-word / always-on hotword detection.
- **Translation of any kind** — handled by the consuming applications, not this service (see ADR-008).

---

## 4. Users & use cases

| Persona | Use case | Latency tolerance | Primary metric |
|---|---|---|---|
| Knowledge worker | **Dictation** into a text field (notes, search, chat) | Final text within ~2 s of pausing | German WER, responsiveness |
| Meeting/training participant | **Live subtitles** of a speaker | Rolling captions within ~1 s | Stream stability, partial accuracy |
| Platform operator (us / customer ops) | Deploy and scale on-prem/k8s | n/a | Ease of deploy, resource cost, air-gap |

---

## 5. Requirements

### 5.1 Functional
- **FR-1** Accept streaming microphone audio from a browser over a secure WebSocket and return incremental (partial) and finalized transcripts.
- **FR-2** Support a **dictation mode** (finalize on natural pause) and a **subtitles mode** (continuously rolling partials).
- **FR-3** Server-side **VAD** to segment speech, suppress silence, and reduce hallucination/compute (Silero VAD, built into WhisperLiveKit).
- **FR-4** Selectable recognition **language** per session, defaulting to German; support de, en, fr, it, es and other Whisper-supported languages.
- **FR-5** Expose a **REST batch endpoint** (OpenAI-compatible) for file/offline transcription and **SRT subtitle generation**.
- **FR-6** Operate **fully offline / air-gapped** — no outbound calls at runtime; model weights baked into the image.

### 5.2 Non-functional (targets — validate by benchmark)

| ID | Attribute | Target |
|---|---|---|
| NFR-1 | German accuracy | WER ≤ **3.5%** on our internal German eval set (stretch ≤ 3.0%) |
| NFR-2 | Partial latency | First interim result ≤ **1.0 s** p50 / ≤ 1.5 s p95 after speech onset |
| NFR-3 | Final latency | Final text ≤ **1.5 s** p50 / ≤ 2.5 s p95 after end-of-utterance |
| NFR-4 | GPU footprint | Default model runs in ≤ **8 GB VRAM**; fits a single 24 GB GPU with concurrency headroom |
| NFR-5 | CPU fallback | Runs on CPU with a supported (smaller) model; degraded but functional |
| NFR-6 | Concurrency | ≥ **5–10 concurrent dictation streams per 24 GB GPU** (planning assumption; load-tested in Phase 2) |
| NFR-7 | Licensing | All shipped components Apache-2.0 / MIT / BSD; no copyleft, no non-commercial, no CC by default |
| NFR-8 | Privacy | No audio or transcript persisted by default; no telemetry leaves the cluster |
| NFR-9 | Portability | Identical baked image runs on a developer Mac (CPU) and a prod GPU node (CUDA) |

---

## 6. Why WhisperLiveKit (build-vs-adopt)

WhisperLiveKit gives us, out of the box and under Apache-2.0, almost the entire non-model layer we would otherwise build and maintain:

- **FastAPI WebSocket server** (`ws://…/asr`) with the browser transport handled — including a bundled HTML/JS frontend and a Chrome extension for capturing tab audio.
- **faster-whisper backend** as a first-class option (`--backend faster-whisper`), exactly our chosen engine.
- **Intelligent streaming** via 2025 SOTA research: **SimulStreaming** (AlignAtt policy, ultra-low latency, default) and **LocalAgreement** (WhisperStreaming) as alternatives.
- **Silero VAD + Voice Activity Controller** built in.
- **Multi-user concurrent backend**, the basis for our concurrency target.
- **Drop-in API compatibility**: native WebSocket, **OpenAI-compatible** REST (`/v1/audio/transcriptions`), and **Deepgram-compatible** WebSocket.
- **Batch/CLI**: `wlk transcribe --format srt` for subtitle files (FR-5).
- **Ready Dockerfiles** for GPU and CPU and a docker-compose with profiles.

Our work becomes: pick/convert the German model, bake it in, build one hardened multi-arch image, add auth and observability, wire it into k8s, and write a thin client SDK. We do **not** write a streaming server.

---

## 7. Architecture overview

```
 Browser (web app)                         Kubernetes cluster
┌───────────────────────┐         ┌──────────────────────────────────────┐
│ getUserMedia          │         │  Ingress (WSS, OIDC/bearer, WS upgrade)│
│ AudioWorklet (PCM)    │  wss    │            │                          │
│  16 kHz mono     ─────────────────────────▶  ▼                          │
│ partial/final render ◀────────────────────  WhisperLiveKit (Deployment) │
└───────────────────────┘  JSON   │   ┌──────────────────────────────┐   │
   client SDK wraps ws://…/asr     │   │ FastAPI WS server (/asr)     │   │
                                    │   │ Silero VAD + VAC             │   │
                                    │   │ SimulStreaming (AlignAtt)    │   │
                                    │   │ faster-whisper (CTranslate2) │   │
                                    │   │ German Whisper — BAKED IN    │   │
                                    │   └──────────────────────────────┘   │
                                    │      ▲ nvidia.com/gpu (prod)          │
                                    │      │ CPU fallback (dev / no-GPU)    │
                                    └──────────────────────────────────────┘
```

A single image contains WhisperLiveKit, faster-whisper, and the baked German model. The browser captures 16 kHz mono PCM via an `AudioWorklet` (WhisperLiveKit's `--pcm-input` path) and streams it over WSS; the server runs VAD + SimulStreaming and pushes JSON partial/final transcripts back. The same image runs on a developer's Mac (CPU) and a prod GPU node (CUDA).

---

## 8. Architecture Decision Records

See `docs/adr-index.md` for a quick index. The full ADR text (ADR-001 … ADR-010)
is reproduced below.

### ADR-001 — Model: German-fine-tuned Whisper, permissive license, baked in
**Decision.** Default model = **`primeline/whisper-large-v3-turbo-german` (Apache-2.0)**, provided via `--model-path` and **baked into the image** (ADR-005). Ship base **`whisper-large-v3` (MIT)** as a configurable fallback. Keep **LoRA adapters** on the roadmap.

### ADR-002 — Serving framework: WhisperLiveKit (faster-whisper backend)
**Decision.** Adopt **WhisperLiveKit** with **`--backend faster-whisper`**. Use its native WebSocket API; keep OpenAI/Deepgram-compatible endpoints available. Harden (auth, observability, pinned version), wrap in our image and Helm chart rather than fork.

### ADR-003 — Streaming strategy: SimulStreaming (AlignAtt) default, LocalAgreement fallback
**Decision.** Default to **SimulStreaming** (`--backend-policy simulstreaming`), tuned via `--frame-threshold` and greedy decoding (`--beams 1`) for dictation. Expose policy as configuration.

### ADR-004 — One baked image for dev and prod *(parity)*
**Decision.** Build **one multi-arch image** (`linux/amd64` + `linux/arm64`). amd64 = CUDA stack (falls back to CPU); arm64 = CPU stack for Mac dev. Auto-detect device at startup with env override; pin `--backend faster-whisper` everywhere. Reject qemu emulation; MLX is dev-only opt-out.

### ADR-005 — Model weights baked into the image
**Decision.** **Bake the converted German model** into the image at build time. No runtime download; model version is part of the image version.

### ADR-006 — Client transport: WSS, browser-side 16 kHz PCM
**Decision.** Browser captures mic via `getUserMedia` + `AudioWorklet`, sends **16 kHz mono PCM** over **WSS** to `--pcm-input`. Server returns JSON partial/final. Ship a thin client SDK.

### ADR-007 — CPU-only deployment tier
**Decision.** Support a **CPU tier** from the same codebase with `small`/`medium` models for dictation; reserve large models for GPU.

### ADR-008 — Translation: out of scope (handled by consuming applications)
**Decision.** This service produces **transcripts only**. Translation is out of scope; WhisperLiveKit's NLLB-based translation (CC-BY-NC) is **disabled and not shipped**.

### ADR-009 — License posture: strict permissive by default
**Decision.** **Default build is strictly Apache/MIT/BSD.** Anything CC / non-commercial is excluded. A CI license gate enforces this.

### ADR-010 — Diarization deferred (available, not default)
**Decision.** **Diarization is a non-goal for v1.** If pursued later, prefer **Sortformer** and clear its license; keep gated pyannote models out of the permissive default.

---

## 9–18

Sections 9 (container parity), 10 (k8s deployment), 11 (hardware sizing),
12 (licensing matrix), 13 (security), 14 (observability), 15 (risks),
16 (phased delivery), 17 (success metrics), 18 (out of scope) of the source PRD
are realized by this repository. See `docs/architecture.md`,
`docs/deployment.md`, and `docs/development.md` for how each maps to the code.

### Appendix — references
- Internal: "Self-Hosted Permissively-Licensed German Speech-to-Text" evaluation report (2026).
- WhisperLiveKit (Apache-2.0): github.com/QuentinFuxa/WhisperLiveKit
- Engines/models: faster-whisper & CTranslate2 (MIT), Whisper (MIT), primeline German fine-tunes (Apache-2.0), Silero VAD (MIT).
