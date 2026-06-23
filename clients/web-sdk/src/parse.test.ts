import { describe, expect, it } from "vitest";
import { parseServerMessage } from "./parse.js";
import { downsampleTo, floatToPcm16 } from "./resample.js";

describe("parseServerMessage", () => {
  it("parses a partial transcript from `text`", () => {
    const r = parseServerMessage(JSON.stringify({ text: "guten tag", is_final: false }));
    expect(r.kind).toBe("transcript");
    if (r.kind === "transcript") {
      expect(r.transcript.text).toBe("guten tag");
      expect(r.transcript.isFinal).toBe(false);
    }
  });

  it("parses a final transcript", () => {
    const r = parseServerMessage(JSON.stringify({ text: "fertig", is_final: true }));
    expect(r.kind).toBe("transcript");
    if (r.kind === "transcript") expect(r.transcript.isFinal).toBe(true);
  });

  it("joins WhisperLiveKit `lines` format", () => {
    const r = parseServerMessage(
      JSON.stringify({ lines: [{ text: "hallo" }, { text: "welt" }] }),
    );
    expect(r.kind).toBe("transcript");
    if (r.kind === "transcript") expect(r.transcript.text).toBe("hallo welt");
  });

  it("recognizes ready_to_stop", () => {
    expect(parseServerMessage(JSON.stringify({ type: "ready_to_stop" })).kind).toBe("ready");
  });

  it("returns unknown for non-JSON", () => {
    expect(parseServerMessage("not json").kind).toBe("unknown");
  });

  it("returns unknown when no text field is present", () => {
    expect(parseServerMessage(JSON.stringify({ status: "buffering" })).kind).toBe("unknown");
  });
});

describe("audio helpers", () => {
  it("downsamples 48k -> 16k by ~3x", () => {
    const input = new Float32Array(48000).fill(0.5);
    const out = downsampleTo(input, 48000, 16000);
    expect(out.length).toBe(16000);
  });

  it("returns input unchanged when rates match", () => {
    const input = new Float32Array([0.1, 0.2]);
    expect(downsampleTo(input, 16000, 16000)).toBe(input);
  });

  it("encodes PCM16 little-endian with correct byte length", () => {
    const buf = floatToPcm16(new Float32Array([0, 1, -1]));
    expect(buf.byteLength).toBe(6);
    const view = new DataView(buf);
    expect(view.getInt16(0, true)).toBe(0);
    expect(view.getInt16(2, true)).toBe(32767); // +1 -> 0x7fff
    expect(view.getInt16(4, true)).toBe(-32768); // -1 -> -0x8000
  });
});
