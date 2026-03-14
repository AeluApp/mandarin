/* AudioWorklet processor for microphone recording.
   Replaces deprecated ScriptProcessorNode where available.
   Sends Float32Array copies of input audio to the main thread via port. */

class RecorderProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._stopped = false;
    this.port.onmessage = (e) => {
      if (e.data === 'stop') this._stopped = true;
    };
  }

  process(inputs) {
    if (this._stopped) return false;
    const input = inputs[0];
    if (input && input.length > 0 && input[0].length > 0) {
      this.port.postMessage(new Float32Array(input[0]));
    }
    return true;
  }
}

registerProcessor('recorder-processor', RecorderProcessor);
