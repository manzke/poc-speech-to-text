/**
 * Defensive parser for WhisperLiveKit `/asr` JSON messages.
 *
 * WhisperLiveKit is fast-moving community software (PRD risk register), so this
 * parser is intentionally tolerant: it recognizes the common message shapes and
 * always exposes the untouched payload as `raw`. The exact live schema is
 * pinned/validated against the running server during the Phase-0 spike; update
 * the recognized keys here if the upstream format shifts.
 */
import type { Transcript } from "./types.js";

export type ParsedMessage =
  | { kind: "ready" }
  | { kind: "transcript"; transcript: Transcript }
  | { kind: "unknown"; raw: unknown };

/** Join WhisperLiveKit's `lines` array (frontend format) into a single string. */
function textFromLines(lines: unknown): string | undefined {
  if (!Array.isArray(lines)) return undefined;
  const parts = lines
    .map((l) => (l && typeof l === "object" && "text" in l ? String((l as any).text) : ""))
    .filter(Boolean);
  return parts.length ? parts.join(" ") : undefined;
}

export function parseServerMessage(data: string): ParsedMessage {
  let msg: any;
  try {
    msg = JSON.parse(data);
  } catch {
    return { kind: "unknown", raw: data };
  }

  // The server signals end-of-stream readiness.
  if (msg?.type === "ready_to_stop" || msg?.status === "ready_to_stop") {
    return { kind: "ready" };
  }

  // Pull text from any of the known fields.
  const text =
    textFromLines(msg?.lines) ??
    (typeof msg?.text === "string" ? msg.text : undefined) ??
    (typeof msg?.transcript === "string" ? msg.transcript : undefined);

  if (text === undefined) {
    return { kind: "unknown", raw: msg };
  }

  // Determine finality across the conventions WLK has used.
  const isFinal =
    msg?.is_final === true ||
    msg?.isFinal === true ||
    msg?.type === "final" ||
    msg?.status === "final";

  return {
    kind: "transcript",
    transcript: { isFinal: Boolean(isFinal), text, raw: msg },
  };
}
