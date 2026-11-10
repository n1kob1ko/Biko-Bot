// Reden mit Biko wie am Telefon: durchgehend zuhören und Satz für Satz sprechen.
// Hier steckt nur die Technik (Mikrofon, Live-Zuhören, Ton abspielen). Was dabei in der App passiert, steht in app.js.
(function () {
  'use strict';
  const L = window.BikoLogik;

  const LIVE = 'wss://api.elevenlabs.io/v1/speech-to-text/realtime';
  // Der Sprachdienst merkt selbst, wann ein Satz fertig ist: nach einer Sekunde Pause. Die Sprache wird nicht
  // vorgegeben, er erkennt Deutsch und Chinesisch selbst.
  const LIVE_EINSTELLUNG = { audio_format: 'pcm_16000', commit_strategy: 'vad', vad_silence_threshold_secs: '1.0' };
  const STIMME_HZ = 24000; // so kommt der Ton von /api/stimme

  const FEHLER = ['error', 'auth_error', 'quota_exceeded', 'unaccepted_terms', 'rate_limited', 'queue_overflow',
    'resource_exhausted', 'session_time_limit_exceeded', 'input_error', 'invalid_request', 'transcriber_error'];

  function base64(puffer) {
    const b = new Uint8Array(puffer);
    let s = '';
    for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
    return btoa(s);
  }

  let werkGeladen = null;

  // Mikrofon auf und live zuhören lassen. `zugang`: {token, modell} von /api/live-zugang.
  // beimTeil(text): was gerade gesprochen wird (kann sich noch ändern), beimSatz(text): ein fertiger Satz,
  // beimEnde(art): die Verbindung ist ohne Auflegen zu Ende.
  // Wirft {art: 'mikro'}, wenn das Mikrofon nicht erlaubt ist, sonst {art: 'live'}.
  async function hoeren({ ac, zugang, beimTeil, beimSatz, beimEnde }) {
    if (!ac || !ac.audioWorklet || !window.AudioWorkletNode || !window.WebSocket) throw { art: 'live' };
    try { if (navigator.audioSession) navigator.audioSession.type = 'play-and-record'; } catch (e) { /* älteres iPhone */ }
    let strom;
    try {
      strom = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
    } catch (e) { throw { art: 'mikro' }; }
    let ws, quelle, knoten, gestoppt = false;
    const aufraeumen = () => {
      gestoppt = true;
      strom.getTracks().forEach((s) => s.stop());
      try { quelle && quelle.disconnect(); knoten && knoten.disconnect(); } catch (e) { /* schon weg */ }
      if (knoten) knoten.port.onmessage = null;
      if (ws) { ws.onclose = ws.onmessage = ws.onerror = null; try { ws.close(); } catch (e) { /* schon zu */ } }
    };
    try {
      werkGeladen = werkGeladen || ac.audioWorklet.addModule('mikro-worklet.js');
      await werkGeladen;
      const q = new URLSearchParams({ model_id: zugang.modell, token: zugang.token, ...LIVE_EINSTELLUNG });
      ws = new WebSocket(`${LIVE}?${q}`);
      await new Promise((gut, schlecht) => {
        const uhr = setTimeout(() => schlecht(new Error('zu langsam')), 8000);
        ws.onmessage = (e) => {
          let m = {};
          try { m = JSON.parse(e.data); } catch (err) { /* kein JSON */ }
          if (m.message_type === 'session_started') { clearTimeout(uhr); gut(); } else if (FEHLER.includes(m.message_type)) { clearTimeout(uhr); schlecht(new Error(m.message_type)); }
        };
        ws.onerror = ws.onclose = () => { clearTimeout(uhr); schlecht(new Error('zu')); };
      });
    } catch (e) {
      aufraeumen();
      throw { art: 'live', grund: e && e.message };
    }
    ws.onmessage = (e) => {
      let m = {};
      try { m = JSON.parse(e.data); } catch (err) { return; }
      if (m.message_type === 'partial_transcript') beimTeil(String(m.text || ''));
      else if (m.message_type === 'committed_transcript') beimSatz(String(m.text || ''));
      else if (FEHLER.includes(m.message_type)) { aufraeumen(); beimEnde(m.message_type); }
    };
    ws.onerror = ws.onclose = () => { if (!gestoppt) { aufraeumen(); beimEnde('zu'); } };

    quelle = ac.createMediaStreamSource(strom);
    knoten = new AudioWorkletNode(ac, 'biko-mikro');
    const leise = ac.createGain(); // das Tonwerk läuft nur, wenn es irgendwo hinführt: ins Stille
    leise.gain.value = 0;
    quelle.connect(knoten).connect(leise).connect(ac.destination);
    knoten.port.onmessage = (e) => {
      if (ws.readyState !== 1) return;
      ws.send(JSON.stringify({ message_type: 'input_audio_chunk', audio_base_64: base64(e.data), commit: false, sample_rate: 16000 }));
    };
    return { stop: aufraeumen };
  }

  // Spricht Sätze nacheinander. Jeder Satz kommt als roher Ton in Stücken und spielt sofort, lückenlos hinter dem
  // vorigen. `holen(text, vorher, signal)` liefert die Antwort von /api/stimme.
  function sprecher({ ac, holen, beimStart, beimEnde, beimFehler }) {
    let schlange = [], lauf = 0, bis = 0, holt = false, aktiv = false, vorher = '', abbruch = null;
    const quellen = new Set();

    function planen(werte) {
      if (!werte.length) return;
      const buf = ac.createBuffer(1, werte.length, STIMME_HZ);
      if (buf.copyToChannel) buf.copyToChannel(werte, 0); else buf.getChannelData(0).set(werte);
      const src = ac.createBufferSource();
      src.buffer = buf;
      src.connect(ac.destination);
      const jetzt = ac.currentTime;
      if (bis < jetzt + 0.03) bis = jetzt + 0.08; // kleiner Vorlauf, damit nichts ruckelt
      src.start(bis);
      bis += buf.duration;
      quellen.add(src);
      src.onended = () => quellen.delete(src);
      if (!aktiv) { aktiv = true; beimStart(); }
    }

    async function spielen(text, hier) {
      abbruch = window.AbortController ? new AbortController() : null;
      const r = await holen(text, vorher, abbruch && abbruch.signal);
      if (!r.ok || !r.body) throw new Error('kein Ton');
      const leser = r.body.getReader();
      let rest = null;
      for (;;) {
        const { done, value } = await leser.read();
        if (hier !== lauf) { try { leser.cancel(); } catch (e) { /* egal */ } return; }
        if (done) break;
        const p = L.pcmLesen(rest, value);
        rest = p.rest;
        planen(p.werte);
      }
      vorher = (vorher + ' ' + text).slice(-500);
    }

    function endeAbwarten(hier) {
      if (hier !== lauf || holt || schlange.length) return;
      const offen = bis - ac.currentTime;
      if (offen > 0.02) { setTimeout(() => endeAbwarten(hier), offen * 1000 + 30); return; }
      if (aktiv) { aktiv = false; beimEnde(); }
    }

    async function weiter() {
      holt = true;
      const hier = lauf;
      while (schlange.length && hier === lauf) {
        const text = schlange.shift();
        try { await spielen(text, hier); } catch (e) { if (hier === lauf) beimFehler(e); }
      }
      if (hier !== lauf) return;
      holt = false;
      endeAbwarten(hier);
    }

    return {
      sagen(text) {
        if (!String(text || '').trim()) return;
        schlange.push(text);
        if (!holt) weiter();
      },
      // Spricht Biko gerade, oder kommt gleich noch etwas?
      spricht: () => aktiv || holt || schlange.length > 0,
      stopp() {
        lauf++;
        schlange = [];
        holt = false;
        if (abbruch) try { abbruch.abort(); } catch (e) { /* egal */ }
        quellen.forEach((s) => { try { s.stop(); } catch (e) { /* lief noch nicht */ } });
        quellen.clear();
        bis = 0;
        const war = aktiv;
        aktiv = false;
        if (war) beimEnde();
      },
      neueAntwort() { vorher = ''; },
    };
  }

  window.BikoTelefon = { hoeren, sprecher };
})();
