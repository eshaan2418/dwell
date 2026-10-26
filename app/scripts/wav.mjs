// Minimal 16-bit mono PCM WAV writer (used only to make placeholder audio for the dev fixture).
/** @param {ArrayLike<number>} samples @param {number} [sampleRate] */
export function wavBytes(samples, sampleRate = 22050) {
  const n = samples.length;
  const buf = Buffer.alloc(44 + n * 2);
  buf.write('RIFF', 0); buf.writeUInt32LE(36 + n * 2, 4); buf.write('WAVE', 8);
  buf.write('fmt ', 12); buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); buf.writeUInt16LE(1, 22);
  buf.writeUInt32LE(sampleRate, 24); buf.writeUInt32LE(sampleRate * 2, 28); buf.writeUInt16LE(2, 32); buf.writeUInt16LE(16, 34);
  buf.write('data', 36); buf.writeUInt32LE(n * 2, 40);
  for (let i = 0; i < n; i++) buf.writeInt16LE(Math.max(-32767, Math.min(32767, Math.round(samples[i] * 32767))), 44 + i * 2);
  return buf;
}

/** Deterministic low rumble ("brown" noise) — a placeholder, clearly not a model output. */
/** @param {number} seconds @param {number} gain @param {number} [sampleRate] @param {number} [seed] */
export function placeholderNoise(seconds, gain, sampleRate = 22050, seed = 1) {
  let s = seed >>> 0;
  const rand = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32) * 2 - 1;
  const out = new Float32Array(Math.round(seconds * sampleRate));
  let y = 0;
  for (let i = 0; i < out.length; i++) { y = 0.98 * y + 0.02 * rand() * 4; out[i] = y * gain; }
  return out;
}
