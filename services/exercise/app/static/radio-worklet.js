/* Low-latency mono PCM bridge. No microphone data leaves this worklet while unkeyed. */
class RadioCapture extends AudioWorkletProcessor {
  constructor() {
    super(); this.enabled = false; this.previous = 0; this.position = 0;
    this.frame = new Int16Array(960); this.used = 0;
    this.port.onmessage = ({data}) => {
      this.enabled = data.active === true;
      this.used = 0; this.position = 0; this.previous = 0;
    };
  }
  process(inputs, outputs) {
    for (const output of outputs) for (const channel of output) channel.fill(0);
    const input = inputs[0]?.[0];
    if (!this.enabled || !input) return true;
    const source = new Float32Array(input.length + 1);
    source[0] = this.previous; source.set(input, 1);
    const step = sampleRate / 48000;
    while (this.position < source.length - 1) {
      const i = Math.floor(this.position), t = this.position - i;
      const value = Math.max(-1, Math.min(1, source[i] * (1-t) + source[i+1] * t));
      this.frame[this.used++] = Math.round(value * (value < 0 ? 32768 : 32767));
      if (this.used === 960) {
        // Protocol bytes are explicitly little-endian, independent of host order.
        const bytes = new ArrayBuffer(1920), view = new DataView(bytes);
        for (let j=0; j<960; j++) view.setInt16(j*2, this.frame[j], true);
        this.port.postMessage(bytes, [bytes]); this.used = 0;
      }
      this.position += step;
    }
    this.position -= source.length - 1;
    this.previous = source[source.length-1];
    return true;
  }
}

class RadioPlayback extends AudioWorkletProcessor {
  constructor() {
    super(); this.voices = new Map();
    this.port.onmessage = ({data}) => {
      if (data.clear) { this.voices.clear(); return; }
      const {speaker, pcm} = data;
      if (!(pcm instanceof ArrayBuffer) || pcm.byteLength % 2) return;
      const view = new DataView(pcm), count = pcm.byteLength/2;
      let voice = this.voices.get(speaker);
      if (!voice) {
        if (this.voices.size >= 16) this.voices.delete(this.voices.keys().next().value);
        voice = {samples: [], at: 0, started: false, receivedAt: currentTime}; this.voices.set(speaker, voice);
      }
      if (currentTime-voice.receivedAt > .25) { voice.samples=[]; voice.at=0; voice.started=false; }
      voice.receivedAt=currentTime;
      // Compact consumed samples; cap jitter storage at 200 ms. Never replay a backlog.
      const consumed = Math.floor(voice.at);
      if (consumed) { voice.samples.splice(0, consumed); voice.at -= consumed; }
      for (let i=0; i<count; i++) voice.samples.push(view.getInt16(i*2, true)/32768);
      if (voice.samples.length > 9600) {
        voice.samples.splice(0, voice.samples.length-1920); voice.at = 0; voice.started = false;
      }
      if (voice.samples.length >= 1920) voice.started = true;
    };
  }
  process(inputs, outputs) {
    const out = outputs[0]?.[0]; if (!out) return true;
    out.fill(0); const step = 48000/sampleRate;
    for (const [id, voice] of this.voices) {
      if (!voice.started && currentTime-voice.receivedAt > .06) voice.started=true;
      if (!voice.started) continue;
      for (let i=0; i<out.length; i++) {
        const j = Math.floor(voice.at), t = voice.at-j;
        if (j >= voice.samples.length) { this.voices.delete(id); break; }
        const a = voice.samples[j], b = voice.samples[j+1] ?? a;
        out[i] += a*(1-t)+b*t; voice.at += step;
      }
    }
    for (let i=0; i<out.length; i++) out[i] = Math.max(-1, Math.min(1, out[i]));
    // Copy mono to every output channel when the headset presents stereo output.
    for (let i=1; i<outputs[0].length; i++) outputs[0][i].set(out);
    return true;
  }
}
registerProcessor('radio-capture', RadioCapture);
registerProcessor('radio-playback', RadioPlayback);
