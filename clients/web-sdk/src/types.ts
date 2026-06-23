/** Public types for the STT web SDK. */

/** Recognition mode, mirroring the server's STT_MODE (FR-2). */
export type SttMode = "dictation" | "subtitles";

export interface SttClientOptions {
  /** Full WebSocket URL of the server's /asr endpoint, e.g. wss://stt.example/asr */
  url: string;
  /** dictation (finalize on pause) or subtitles (rolling partials). Default: "dictation". */
  mode?: SttMode;
  /**
   * Bearer token sent as a `?token=` query param on connect (ingress auth, §13).
   * Browsers cannot set WS headers, so the token rides on the URL over WSS.
   */
  token?: string;
  /** Target sample rate sent to the server. WhisperLiveKit expects 16 kHz (ADR-006). */
  targetSampleRate?: number;
  /** Override the AudioWorklet module URL (defaults to the bundled pcm-worklet). */
  workletUrl?: string;
}

/** A transcript update pushed by the server. */
export interface Transcript {
  /** true once the server has finalized this segment (dictation pause / end of utterance). */
  isFinal: boolean;
  /** Best-effort text for the current segment. */
  text: string;
  /** Raw server message, for consumers that need fields the SDK does not surface. */
  raw: unknown;
}

export type SttEvent =
  | { type: "open" }
  | { type: "ready" }
  | { type: "partial"; transcript: Transcript }
  | { type: "final"; transcript: Transcript }
  | { type: "error"; error: Error }
  | { type: "close"; code: number; reason: string };

export type SttEventListener = (event: SttEvent) => void;
