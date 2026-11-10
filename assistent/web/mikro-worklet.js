// Läuft im Tonwerk des Browsers: macht aus dem Mikrofon Ton mit 16 kHz und 16 Bit, in Stücken von 0,1 Sekunden.
// So will ihn das Live-Zuhören des Sprachdienstes haben (siehe telefon.js).
class BikoMikro extends AudioWorkletProcessor {
  constructor() {
    super();
    this.schritt = sampleRate / 16000; // so viele Werte des Mikrofons werden zu einem
    this.pos = 0;
    this.summe = 0;
    this.zahl = 0;
    this.neuesStueck();
  }

  neuesStueck() {
    this.stueck = new Int16Array(1600);
    this.n = 0;
  }

  process(inputs) {
    const ein = inputs[0] && inputs[0][0];
    if (!ein) return true;
    for (let i = 0; i < ein.length; i++) {
      this.summe += ein[i];
      this.zahl++;
      if (++this.pos < this.schritt) continue;
      this.pos -= this.schritt;
      const v = Math.max(-1, Math.min(1, this.summe / this.zahl));
      this.summe = 0;
      this.zahl = 0;
      this.stueck[this.n++] = v < 0 ? v * 0x8000 : v * 0x7fff;
      if (this.n === this.stueck.length) {
        this.port.postMessage(this.stueck.buffer, [this.stueck.buffer]);
        this.neuesStueck();
      }
    }
    return true;
  }
}

registerProcessor('biko-mikro', BikoMikro);
