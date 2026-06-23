/**
 * AudioWorkletProcessor that downsamples mic audio to 16 kHz mono PCM16 and
 * posts each chunk to the main thread, which forwards it over the WebSocket.
 *
 * Registered as the "stt-pcm-processor" worklet. This file is loaded via
 * `audioWorklet.addModule()` and therefore runs in the AudioWorklet global
 * scope (not the window), so it cannot import DOM code — the resample helpers
 * are inlined to keep it a standalone module.
 *
 * NOTE: when bundling, this module must be emitted as its own file/URL and
 * passed via `SttClientOptions.workletUrl`. tsc emits it to dist/pcm-worklet.js.
 */

declare const sampleRate: number;
declare function registerProcessor(name: string, ctor: unknown): void;
declare class AudioWorkletProcessor {
  readonly port: MessagePort;
  constructor();
}

const TARGET_RATE = 16000;

function downsampleTo(input: Float32Array, inputRate: number, targetRate: number): Float32Array {
  if (targetRate >= inputRate) return input;
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

function floatToPcm16(input: Float32Array): ArrayBuffer {
  const buffer = new ArrayBuffer(input.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < input.length; i++) {
    let s = Math.max(-1, Math.min(1, input[i]));
    s = s < 0 ? s * 0x8000 : s * 0x7fff;
    view.setInt16(i * 2, s | 0, true);
  }
  return buffer;
}

class PcmProcessor extends AudioWorkletProcessor {
  process(inputs: Float32Array[][]): boolean {
    const channel = inputs[0]?.[0];
    if (channel && channel.length) {
      const down = downsampleTo(channel, sampleRate, TARGET_RATE);
      const pcm = floatToPcm16(down);
      // Transfer the buffer to avoid a copy.
      this.port.postMessage(pcm, [pcm]);
    }
    return true; // keep the processor alive
  }
}

registerProcessor("stt-pcm-processor", PcmProcessor);
