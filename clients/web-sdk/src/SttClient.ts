/**
 * SttClient — thin browser wrapper over WhisperLiveKit's `/asr` WebSocket.
 *
 * Replaces the Chrome Web Speech API as a drop-in: captures the mic via
 * getUserMedia + an AudioWorklet (16 kHz mono PCM16, ADR-006), streams binary
 * frames over WSS, and emits typed partial/final transcript events. Audio never
 * leaves the configured server — that is the whole point (data sovereignty, §1).
 */
import { parseServerMessage } from "./parse.js";
import type {
  SttClientOptions,
  SttEvent,
  SttEventListener,
} from "./types.js";

const DEFAULT_TARGET_RATE = 16000;

export class SttClient {
  private readonly opts: Required<Pick<SttClientOptions, "url" | "mode" | "targetSampleRate">> &
    SttClientOptions;
  private ws?: WebSocket;
  private audioContext?: AudioContext;
  private mediaStream?: MediaStream;
  private workletNode?: AudioWorkletNode;
  private sourceNode?: MediaStreamAudioSourceNode;
  private readonly listeners = new Set<SttEventListener>();

  constructor(options: SttClientOptions) {
    if (!options.url) throw new Error("SttClient: `url` is required");
    this.opts = {
      mode: "dictation",
      targetSampleRate: DEFAULT_TARGET_RATE,
      ...options,
    };
  }

  on(listener: SttEventListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private emit(event: SttEvent): void {
    for (const l of this.listeners) {
      try {
        l(event);
      } catch (err) {
        // A listener throwing must not break the audio pipeline.
        console.error("[stt] listener error", err);
      }
    }
  }

  private buildUrl(): string {
    const u = new URL(this.opts.url);
    if (this.opts.token) u.searchParams.set("token", this.opts.token);
    // Surface mode to the server where supported; harmless if ignored.
    u.searchParams.set("mode", this.opts.mode);
    return u.toString();
  }

  /** Connect, request mic access, and begin streaming. Resolves once the WS opens. */
  async start(): Promise<void> {
    if (this.ws) throw new Error("SttClient: already started");

    this.ws = new WebSocket(this.buildUrl());
    this.ws.binaryType = "arraybuffer";

    this.ws.onmessage = (ev: MessageEvent) => {
      if (typeof ev.data !== "string") return; // server sends JSON text
      const parsed = parseServerMessage(ev.data);
      if (parsed.kind === "ready") {
        this.emit({ type: "ready" });
      } else if (parsed.kind === "transcript") {
        this.emit({
          type: parsed.transcript.isFinal ? "final" : "partial",
          transcript: parsed.transcript,
        });
      }
    };
    this.ws.onerror = () =>
      this.emit({ type: "error", error: new Error("WebSocket error") });
    this.ws.onclose = (ev: CloseEvent) =>
      this.emit({ type: "close", code: ev.code, reason: ev.reason });

    await this.waitForOpen();
    this.emit({ type: "open" });

    await this.startAudio();
  }

  private waitForOpen(): Promise<void> {
    return new Promise((resolve, reject) => {
      const ws = this.ws!;
      if (ws.readyState === WebSocket.OPEN) return resolve();
      ws.addEventListener("open", () => resolve(), { once: true });
      ws.addEventListener(
        "error",
        () => reject(new Error("WebSocket failed to open")),
        { once: true },
      );
    });
  }

  private async startAudio(): Promise<void> {
    this.mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
    this.audioContext = new AudioContext();
    const workletUrl =
      this.opts.workletUrl ?? new URL("./pcm-worklet.js", import.meta.url).toString();
    await this.audioContext.audioWorklet.addModule(workletUrl);

    this.sourceNode = this.audioContext.createMediaStreamSource(this.mediaStream);
    this.workletNode = new AudioWorkletNode(this.audioContext, "stt-pcm-processor");
    this.workletNode.port.onmessage = (ev: MessageEvent) => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(ev.data as ArrayBuffer);
      }
    };
    this.sourceNode.connect(this.workletNode);
    // Do not connect to destination — we don't want to play the mic back.
  }

  /** Stop streaming, release the mic, and close the socket. */
  async stop(): Promise<void> {
    this.workletNode?.port.close();
    this.sourceNode?.disconnect();
    this.workletNode?.disconnect();
    this.mediaStream?.getTracks().forEach((t) => t.stop());
    await this.audioContext?.close().catch(() => undefined);
    if (this.ws && this.ws.readyState <= WebSocket.OPEN) this.ws.close(1000, "client stop");
    this.ws = undefined;
    this.audioContext = undefined;
    this.mediaStream = undefined;
    this.workletNode = undefined;
    this.sourceNode = undefined;
  }
}
