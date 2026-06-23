// AudioWorklet served as a static file (referenced via SttClientOptions.workletUrl).
// Plain JS copy of clients/web-sdk/src/pcm-worklet.ts: downsample mic audio to
// 16 kHz mono PCM16 and post each chunk to the main thread. AudioWorklet modules
// must be plain JS, so this is committed alongside the example app.
const TARGET_RATE = 16000;

function downsampleTo(input, inputRate, targetRate) {
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

function floatToPcm16(input) {
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
  process(inputs) {
    const channel = inputs[0]?.[0];
    if (channel && channel.length) {
      const down = downsampleTo(channel, sampleRate, TARGET_RATE);
      const pcm = floatToPcm16(down);
      this.port.postMessage(pcm, [pcm]);
    }
    return true;
  }
}

registerProcessor("stt-pcm-processor", PcmProcessor);
