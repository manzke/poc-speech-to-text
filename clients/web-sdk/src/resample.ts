/**
 * Audio helpers shared by the AudioWorklet and unit tests.
 *
 * Kept DOM-free so they can be tested under Node/vitest. The browser captures
 * mic audio at the AudioContext's native rate (often 44.1/48 kHz, and Safari
 * has its own quirks — PRD risk register); we downsample to 16 kHz mono and
 * convert to little-endian PCM16, which is what WhisperLiveKit's `--pcm-input`
 * path expects (ADR-006).
 */

/** Linear-interpolation downsample of mono Float32 audio to `targetRate`. */
export function downsampleTo(
  input: Float32Array,
  inputRate: number,
  targetRate: number,
): Float32Array {
  if (targetRate === inputRate) return input;
  if (targetRate > inputRate) {
    throw new Error(`upsampling not supported (${inputRate} -> ${targetRate})`);
  }
  const ratio = inputRate / targetRate;
  const outLength = Math.floor(input.length / ratio);
  const out = new Float32Array(outLength);
  for (let i = 0; i < outLength; i++) {
    const pos = i * ratio;
    const lo = Math.floor(pos);
    const hi = Math.min(lo + 1, input.length - 1);
    const frac = pos - lo;
    out[i] = input[lo] * (1 - frac) + input[hi] * frac;
  }
  return out;
}

/** Convert Float32 samples in [-1, 1] to little-endian signed PCM16 bytes. */
export function floatToPcm16(input: Float32Array): ArrayBuffer {
  const buffer = new ArrayBuffer(input.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < input.length; i++) {
    let s = Math.max(-1, Math.min(1, input[i]));
    // Asymmetric scaling for full int16 range.
    s = s < 0 ? s * 0x8000 : s * 0x7fff;
    view.setInt16(i * 2, s | 0, true /* little-endian */);
  }
  return buffer;
}
