// Browser-Tests der Oberfläche mit falscher KI:  node --test tests/e2e.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { chromium, devices } = require('playwright');

const PORT = 8097;
const URL = `http://127.0.0.1:${PORT}/`;
let server, browser, daten;

test.before(async () => {
  daten = fs.mkdtempSync(path.join(os.tmpdir(), 'biko-helfer-'));
  server = spawn('python3', [path.join(__dirname, 'falscher_server.py'), String(PORT), daten], { stdio: 'ignore' });
  for (let i = 0; i < 50; i++) {
    try { await fetch(URL + 'api/status'); break; } catch (e) { await new Promise((r) => setTimeout(r, 100)); }
  }
  // Falsches Mikrofon des Browsers: Aufnahmen gelingen ohne Nachfrage und ohne echtes Gerät
  browser = await chromium.launch({ args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] });
});
test.after(async () => {
  await browser.close();
  server.kill();
  fs.rmSync(daten, { recursive: true, force: true });
});

// Falsche Spracherkennung: "hört" kurz zu und liefert dann einen Satz
const FALSCHES_MIKRO = () => {
  window.SpeechRecognition = class {
    start() {
      this.t = setTimeout(() => {
        this.onresult({ results: [[{ transcript: 'Hallo Biko' }]] });
        this.onend();
      }, 600);
    }
    stop() { clearTimeout(this.t); this.onend(); }
  };
  // Das Live-Zuhören erreicht den Sprachdienst im Test nicht: die Verbindung geht gleich wieder zu.
  // Die Tests fürs Reden wie am Telefon setzen stattdessen FALSCHES_TELEFON ein.
  window.WebSocket = class { constructor() { setTimeout(() => this.onclose && this.onclose(), 10); } send() {} close() {} };
};

// Die Uhr steht fest (Montag, 15 Uhr), damit keine Erinnerung von selbst in einen Test platzt.
// `ohneDienst`: so, als wäre am Server kein Sprachdienst eingerichtet (dann sprechen und hören die Browser selbst).
async function seite(t, { uhr = '2026-01-05T15:00:00', ohneDienst = false, vorher = null, ...optionen } = {}) {
  const kontext = await browser.newContext({ ...devices['iPhone 13'], ...optionen });
  t.after(() => kontext.close());
  const p = await kontext.newPage();
  p.setDefaultTimeout(4000);
  const fehler = [];
  p.on('pageerror', (e) => fehler.push(e.message));
  p.on('console', (m) => { if (m.type() === 'error') fehler.push(m.text()); });
  p.fehler = fehler;
  await p.addInitScript(FALSCHES_MIKRO);
  if (vorher) await p.addInitScript(vorher);
  if (ohneDienst) {
    await p.route('**/api/status', async (route) => {
      const antwort = await route.fetch();
      await route.fulfill({ response: antwort, json: { ...(await antwort.json()), sprachdienst: false } });
    });
  }
  await p.clock.setFixedTime(new Date(uhr));
  await p.goto(URL);
  return p;
}
async function angemeldet(t, optionen) {
  const p = await seite(t, optionen);
  await p.fill('#passwort', 'test');
  await p.click('#login-form button[type=submit]');
  await p.waitForSelector('#app:not([hidden])');
  return p;
}
const erinnerungenSetzen = (p, liste) => p.evaluate(async (l) => {
  await fetch('/api/erinnerungen', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ erinnerungen: l }) });
}, liste);
const erinnerungenHolen = (p) => p.evaluate(async () => (await fetch('/api/erinnerungen')).json());
const zu = (p, ziel) => p.click(`.leiste button[data-ziel=${ziel}]`);
const stimmung = (p) => p.getAttribute('#app .biko', 'data-mood');
const fragen = async (p, text) => {
  const bisher = await p.locator('.blase.biko-sagt').count();
  await p.fill('#chat-text', text);
  await p.click('#chat-knopf');
  await p.waitForFunction((n) => document.querySelectorAll('.blase.biko-sagt').length > n, bisher);
};

test('Anmelden zeigt die App und Biko begrüßt', async (t) => {
  const p = await seite(t);
  assert.equal(await p.isVisible('#login'), true);
  assert.equal(await p.getAttribute('#login .biko', 'data-mood'), 'winkt');
  await p.fill('#passwort', 'test');
  await p.click('#login-form button[type=submit]');
  await p.waitForSelector('#app:not([hidden])');
  assert.equal(await p.isVisible('#login'), false);
  assert.deepEqual(p.fehler, []);
});

test('Der große Knopf ist erst Mikrofon und wird beim Tippen zu Senden', async (t) => {
  const p = await angemeldet(t);
  assert.equal(await p.getAttribute('#chat-knopf', 'data-art'), 'mikro');
  await p.fill('#chat-text', 'Hallo');
  assert.equal(await p.getAttribute('#chat-knopf', 'data-art'), 'senden');
  assert.equal(await p.getAttribute('#chat-knopf', 'aria-label'), 'Senden');
  await p.fill('#chat-text', '');
  assert.equal(await p.getAttribute('#chat-knopf', 'data-art'), 'mikro');
});

test('Frage senden: Biko tippt beim Nachdenken und antwortet dann', async (t) => {
  const p = await angemeldet(t);
  await p.fill('#chat-text', 'Gibt es Angebote für Kaffee?');
  await p.click('#chat-knopf');
  await p.waitForSelector('.blase.ich');
  assert.equal(await stimmung(p), 'tippt');
  await p.waitForSelector('.blase.biko-sagt');
  assert.match(await p.textContent('.blase.biko-sagt'), /Billa/);
  assert.notEqual(await stimmung(p), 'tippt');
  assert.equal(await p.inputValue('#chat-text'), '');
  assert.deepEqual(p.fehler, []);
});

test('Sprechen ohne Sprachdienst: der Browser hört zu, der Satz wird von selbst gesendet', async (t) => {
  const p = await angemeldet(t, { ohneDienst: true });
  await p.click('#chat-knopf');
  assert.equal(await p.getAttribute('#chat-knopf', 'data-art'), 'stopp');
  assert.equal(await stimmung(p), 'hoert');
  await p.waitForSelector('.blase.ich');
  assert.equal(await p.textContent('.blase.ich'), 'Hallo Biko');
  await p.waitForSelector('.blase.biko-sagt');
});

test('Sprechen, wenn das Live-Zuhören nicht geht: die Aufnahme geht zum Server, der verstandene Satz wird gesendet', async (t) => {
  const p = await angemeldet(t);
  const aufnahme = p.waitForRequest((r) => r.url().endsWith('/api/zuhoeren'));
  await p.click('#chat-knopf');
  await p.waitForSelector('#chat-knopf[data-art=stopp]');
  assert.equal(await stimmung(p), 'hoert');
  await p.waitForTimeout(700);
  await p.click('#chat-knopf'); // fertig gesprochen
  const anfrage = await aufnahme;
  assert.match(anfrage.headers()['content-type'], /^audio\/(webm|mp4)/);
  await p.waitForSelector('.blase.ich');
  assert.equal(await p.textContent('.blase.ich'), 'Hallo Biko');
  await p.waitForSelector('.blase.biko-sagt');
  assert.equal(await p.getAttribute('#chat-knopf', 'data-art'), 'mikro');
  assert.deepEqual(p.fehler, []);
});

test('Sprechen: nichts verstanden oder Mikrofon nicht erlaubt sagt Biko freundlich', async (t) => {
  const p = await angemeldet(t);
  await p.route('**/api/zuhoeren', (route) => route.fulfill({ json: { text: '', sprache: '' } }));
  await p.click('#chat-knopf');
  await p.waitForSelector('#chat-knopf[data-art=stopp]');
  await p.waitForTimeout(400);
  await p.click('#chat-knopf');
  await p.waitForFunction(() => /nichts gehört/.test(document.querySelector('#chat-hinweis').textContent));
  assert.equal(await p.locator('.blase').count(), 0);
  assert.equal(await p.getAttribute('#chat-knopf', 'data-art'), 'mikro');

  const q = await angemeldet(t, { vorher: () => {
    navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException('nein', 'NotAllowedError'));
  } });
  await q.click('#chat-knopf');
  await q.waitForFunction(() => /Mikrofon/.test(document.querySelector('#chat-hinweis').textContent));
  assert.equal(await q.getAttribute('#chat-knopf', 'data-art'), 'mikro');
});

test('Sprechen: gleich wieder angetippt (ein Versehen) schickt nichts weg', async (t) => {
  const p = await angemeldet(t);
  let geschickt = 0;
  p.on('request', (r) => { if (r.url().endsWith('/api/zuhoeren')) geschickt++; });
  await p.click('#chat-knopf');
  await p.waitForSelector('#chat-knopf[data-art=stopp]');
  await p.click('#chat-knopf');
  await p.waitForFunction(() => /nichts gehört/.test(document.querySelector('#chat-hinweis').textContent));
  assert.equal(await p.getAttribute('#chat-knopf', 'data-art'), 'mikro');
  assert.equal(geschickt, 0);
  assert.equal(await p.locator('.blase').count(), 0);
});

// Falsches Mikrofon mit bestimmbarem Inhalt: `sekunden` lang ein Ton ("jemand spricht"), danach Stille
const MIKRO_MIT_TON = (sekunden) => {
  navigator.mediaDevices.getUserMedia = async () => {
    const ac = new AudioContext();
    const ziel = ac.createMediaStreamDestination();
    const o = ac.createOscillator(), g = ac.createGain();
    g.gain.value = sekunden ? 0.3 : 0;
    o.connect(g).connect(ziel);
    o.start();
    o.stop(ac.currentTime + (sekunden || 0.1));
    return ziel.stream;
  };
};

test('Sprechen: nach einer Pause hört Biko von selbst auf und schickt den Satz ab', async (t) => {
  const p = await angemeldet(t);
  await p.addInitScript(MIKRO_MIT_TON, 1);
  await p.reload();
  await p.waitForSelector('#app:not([hidden])');
  await p.click('#chat-knopf');
  await p.waitForSelector('#chat-knopf[data-art=stopp]');
  await p.waitForSelector('.blase.ich', { timeout: 8000 }); // kein zweites Antippen
  assert.equal(await p.textContent('.blase.ich'), 'Hallo Biko');
  assert.deepEqual(p.fehler, []);
});

test('Sprechen: wer nichts sagt, bekommt nach ein paar Sekunden von selbst einen freundlichen Hinweis', async (t) => {
  const p = await angemeldet(t);
  await p.addInitScript(MIKRO_MIT_TON, 0);
  await p.reload();
  await p.waitForSelector('#app:not([hidden])');
  // die stille Aufnahme geht trotzdem zum Verstehen (vielleicht war es nur sehr leise), dort kommt kein Wort heraus
  let geschickt = 0;
  await p.route('**/api/zuhoeren', (route) => { geschickt++; return route.fulfill({ json: { text: '', sprache: '' } }); });
  await p.click('#chat-knopf');
  await p.waitForSelector('#chat-knopf[data-art=stopp]');
  await p.waitForFunction(() => /nichts gehört/.test(document.querySelector('#chat-hinweis').textContent), null, { timeout: 12000 });
  assert.equal(await p.getAttribute('#chat-knopf', 'data-art'), 'mikro');
  assert.equal(geschickt, 1);
  assert.equal(await p.locator('.blase').count(), 0);
});

// Falsches Live-Zuhören: nimmt den Ton an wie der Sprachdienst, der Test sagt, was "gehört" wurde (window.liveSagt)
const FALSCHES_TELEFON = () => {
  window.live = { gesendet: 0, zu: false, adresse: '' };
  window.WebSocket = class {
    constructor(url) {
      this.readyState = 0;
      window.live.adresse = url;
      window.liveDienst = this;
      setTimeout(() => { this.readyState = 1; this.sag({ message_type: 'session_started', session_id: 's1', config: {} }); }, 30);
    }
    sag(m) { if (this.onmessage) this.onmessage({ data: JSON.stringify(m) }); }
    send(d) {
      const m = JSON.parse(d);
      if (m.message_type === 'input_audio_chunk' && m.sample_rate === 16000 && m.audio_base_64.length > 4000) window.live.gesendet++;
    }
    close() { this.readyState = 3; window.live.zu = true; }
  };
  window.liveSagt = (text, fertig) => window.liveDienst.sag({ message_type: fertig ? 'committed_transcript' : 'partial_transcript', text });
};
const hoertGeradeZu = (p) => p.waitForFunction(() => document.querySelector('#app .biko').dataset.mood === 'hoert');

test('Reden wie am Telefon: einmal tippen, Biko hört durchgehend zu und antwortet mit Stimme', async (t) => {
  const p = await angemeldet(t, { vorher: FALSCHES_TELEFON });
  const stimmen = [];
  p.on('request', (r) => { if (r.url().endsWith('/api/stimme')) stimmen.push(JSON.parse(r.postData()).text); });
  await p.click('#chat-knopf');
  await p.waitForSelector('#chat-knopf[data-art=stopp]');
  assert.equal(await p.getAttribute('#chat-knopf', 'aria-label'), 'Gespräch beenden');
  assert.match(await p.textContent('#chat-hinweis'), /Wir reden/);
  await hoertGeradeZu(p);
  // das Mikrofon geht laufend zum Live-Zuhören, mit Zugang vom Server, nie mit dem Schlüssel
  const adresse = await p.evaluate(() => window.live.adresse);
  assert.match(adresse, /^wss:\/\/api\.elevenlabs\.io\/v1\/speech-to-text\/realtime\?/);
  assert.match(adresse, /token=einmal-zugang/);
  assert.match(adresse, /commit_strategy=vad/);
  await p.waitForFunction(() => window.live.gesendet >= 3);

  // was gerade gesprochen wird, steht schon im Feld; ist der Satz fertig, geht er von selbst ab
  await p.evaluate(() => window.liveSagt('Gibt es', false));
  assert.equal(await p.inputValue('#chat-text'), 'Gibt es');
  await p.evaluate(() => window.liveSagt('Gibt es Angebote für Kaffee?', true));
  await p.waitForSelector('.blase.ich');
  assert.equal(await p.textContent('.blase.ich'), 'Gibt es Angebote für Kaffee?');
  await p.waitForSelector('.blase.biko-sagt');
  assert.match(await p.textContent('.blase.biko-sagt'), /Billa/);
  // Biko spricht Satz für Satz, kein Abspielen einer ganzen Datei
  await p.waitForFunction(() => document.querySelector('#app .biko').dataset.mood === 'da');
  assert.deepEqual(stimmen.slice(0, 1), ['Diese Woche gibt es bei Billa Kaffee um 30 % günstiger.']);
  await p.waitForFunction(() => document.querySelectorAll('.blase.ich').length === 1);
  // das Gespräch bleibt offen
  assert.equal(await p.getAttribute('#chat-knopf', 'data-art'), 'stopp');

  // hört das Mikrofon nur Bikos eigene Stimme, redet er einfach weiter
  await p.evaluate(() => window.liveSagt('bei Billa Kaffee günstiger', false));
  await p.waitForTimeout(150);
  assert.equal(await stimmung(p), 'da');
  // fällt man ihm ins Wort, hört er sofort auf und hört zu
  await p.evaluate(() => window.liveSagt('Moment mal', false));
  await hoertGeradeZu(p);
  await p.evaluate(() => window.liveSagt('Moment mal, und Tee?', true));
  await p.waitForFunction(() => document.querySelectorAll('.blase.ich').length === 2);
  assert.equal(await p.textContent('.blase.ich >> nth=1'), 'Moment mal, und Tee?');
  await p.waitForFunction(() => document.querySelectorAll('.blase.biko-sagt').length === 2);

  // der rote Knopf legt auf: das Mikrofon geht aus
  await p.click('#chat-knopf');
  assert.equal(await p.getAttribute('#chat-knopf', 'data-art'), 'mikro');
  assert.equal(await p.evaluate(() => window.live.zu), true);
  assert.equal(await p.textContent('#chat-hinweis'), '');
  assert.deepEqual(p.fehler, []);
});

test('In der Android-Blase (?mini): Biko redet ohne Fenster und meldet, was er gerade tut', async (t) => {
  const NATIV = () => {
    window.zustaende = [];
    window.kopiert = [];
    window.BikoNativ = { zustand: (z) => window.zustaende.push(z), hinweis: () => {}, kopieren: (x) => window.kopiert.push(x) };
  };
  const p = await angemeldet(t, { vorher: `(${FALSCHES_TELEFON})(); (${NATIV})();` });
  await p.goto(URL + '?mini');
  await p.waitForSelector('#app:not([hidden])');
  await p.evaluate(() => window.bikoReden());
  await p.waitForFunction(() => window.zustaende.includes('hoert'));
  // die Sprache ist vorgegeben, so versteht der Sprachdienst besser
  assert.match(await p.evaluate(() => window.live.adresse), /language_code=de/);
  await p.evaluate(() => window.liveSagt('Gibt es Angebote für Kaffee?', true));
  await p.waitForFunction(() => window.zustaende.includes('denkt') && window.zustaende.includes('spricht'));
  await p.evaluate(() => window.bikoAuflegen());
  assert.equal(await p.evaluate(() => window.zustaende[window.zustaende.length - 1]), 'aus');
  assert.equal(await p.evaluate(() => window.live.zu), true);
  assert.deepEqual(p.fehler, []);
});

test('Reden wie am Telefon: wer kurz absetzt und weiterredet, wird nicht abgeschnitten', async (t) => {
  const p = await angemeldet(t, { vorher: FALSCHES_TELEFON });
  await p.click('#chat-knopf');
  await hoertGeradeZu(p);
  await p.evaluate(() => window.liveSagt('Erinnere mich', true));
  await p.waitForTimeout(200);
  await p.evaluate(() => window.liveSagt('morgen um 8', false));
  await p.waitForTimeout(700);
  assert.equal(await p.locator('.blase.ich').count(), 0, 'noch nicht abgeschickt');
  await p.evaluate(() => window.liveSagt('morgen um 8 an die Tablette.', true));
  await p.waitForSelector('.blase.ich');
  assert.equal(await p.textContent('.blase.ich'), 'Erinnere mich morgen um 8 an die Tablette.');
  await p.waitForSelector('.notiz');
});

test('Reden wie am Telefon: weglegen legt auf, eine abgerissene Verbindung kommt still wieder', async (t) => {
  const p = await angemeldet(t, { vorher: FALSCHES_TELEFON });
  let zugaenge = 0;
  p.on('request', (r) => { if (r.url().endsWith('/api/live-zugang')) zugaenge++; });
  await p.click('#chat-knopf');
  await hoertGeradeZu(p);
  await p.evaluate(() => window.liveDienst.onclose());
  await p.waitForFunction(() => window.live.gesendet >= 1 && window.liveDienst.readyState === 1);
  assert.equal(zugaenge, 2);
  assert.equal(await p.getAttribute('#chat-knopf', 'data-art'), 'stopp');
  await p.evaluate(() => {
    Object.defineProperty(document, 'hidden', { value: true, configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  assert.equal(await p.getAttribute('#chat-knopf', 'data-art'), 'mikro');
  assert.deepEqual(p.fehler, []);
});

test('Vorlesen mit Sprachdienst: der Ton kommt vom Server, nochmal antippen stoppt', async (t) => {
  const p = await angemeldet(t);
  await fragen(p, 'Gibt es Angebote für Kaffee?');
  let geholt = 0;
  p.on('request', (r) => { if (r.url().endsWith('/api/vorlesen')) geholt++; });
  const anfrage = p.waitForRequest((r) => r.url().endsWith('/api/vorlesen'));
  await p.click('.blase .vorlesen');
  assert.match((await anfrage).postDataJSON().text, /Billa/);
  await p.waitForSelector('.blase .vorlesen[data-zustand=laeuft]');
  assert.equal((await p.textContent('.blase .vorlesen')).trim(), 'Stopp');
  // der Ton ist kurz: danach steht der Knopf von selbst wieder auf "Vorlesen"
  await p.waitForSelector('.blase .vorlesen[data-zustand=ruhe]');
  await p.click('.blase .vorlesen');
  await p.waitForSelector('.blase .vorlesen[data-zustand=laeuft]');
  await p.click('.blase .vorlesen');
  assert.equal(await p.getAttribute('.blase .vorlesen', 'data-zustand'), 'ruhe');
  assert.equal(geholt, 1, 'dieselbe Antwort nochmal anhören kostet nichts: der Ton ist noch da');
  assert.deepEqual(p.fehler, []);
});

test('Vorlesen: ohne Sprachdienst oder wenn er ausfällt, liest der Browser vor', async (t) => {
  const zaehlen = () => {
    window.gesprochen = [];
    speechSynthesis.speak = (u) => { window.gesprochen.push(u.text); };
  };
  const p = await angemeldet(t, { ohneDienst: true, vorher: zaehlen });
  let gefragt = 0;
  p.on('request', (r) => { if (r.url().endsWith('/api/vorlesen')) gefragt++; });
  await fragen(p, 'Gibt es Angebote für Kaffee?');
  await p.click('.blase .vorlesen');
  await p.waitForFunction(() => window.gesprochen.some((x) => /Billa/.test(x)));
  assert.equal(gefragt, 0, 'ohne Sprachdienst fragt die App den Server nicht');

  const q = await angemeldet(t, { vorher: zaehlen });
  await q.route('**/api/vorlesen', (route) => route.fulfill({ status: 503, json: { fehler: 'Die Stimme geht gerade nicht.' } }));
  await fragen(q, 'Gibt es Angebote für Kaffee?');
  await q.click('.blase .vorlesen');
  await q.waitForFunction(() => window.gesprochen.some((x) => /Billa/.test(x)));
});

test('Vorschlag antippen stellt die Frage', async (t) => {
  const p = await angemeldet(t);
  const text = await p.textContent('.vorschlag');
  await p.click('.vorschlag');
  await p.waitForSelector('.blase.ich');
  assert.equal(await p.textContent('.blase.ich'), text);
  assert.equal(await p.locator('.vorschlag').count(), 0);
});

test('Das Kissen in der Leiste wandert zum gewählten Bereich', async (t) => {
  const p = await angemeldet(t);
  await zu(p, 'einstellen');
  await p.waitForTimeout(500);
  const mitte = async (sel) => { const b = await p.locator(sel).boundingBox(); return b.x + b.width / 2; };
  const kissen = await mitte('.leiste-kissen');
  const knopf = await mitte('.leiste button[data-ziel=einstellen]');
  assert.ok(Math.abs(kissen - knopf) < 2, `Kissen ${kissen} liegt nicht unter dem Knopf ${knopf}`);
  assert.equal(await p.locator('.leiste-kissen').count(), 1, 'es gibt genau ein Kissen, das wandert');
  assert.equal(await p.isVisible('[data-ansicht=einstellen]'), true);
  assert.deepEqual(await p.locator('.leiste button').evaluateAll((l) => l.map((b) => b.dataset.ziel)), ['reden', 'gespraeche', 'einstellen'],
    'eigene Bereiche für Erinnerungen und Nachrichten gibt es nicht mehr');
  await p.waitForTimeout(300);
  assert.equal(await p.isVisible('[data-ansicht=reden]'), false);
});

test('Sprachmenü geht am Knopf auf und stellt auf Chinesisch um', async (t) => {
  const p = await angemeldet(t);
  assert.equal(await p.isVisible('#sprache-menue'), false);
  await p.click('#sprache-knopf');
  assert.equal(await p.isVisible('#sprache-menue'), true);
  assert.equal(await p.getAttribute('#sprache-knopf', 'aria-expanded'), 'true');
  await p.click('#sprache-menue [data-sprache=zh]');
  await p.waitForTimeout(300);
  assert.equal(await p.isVisible('#sprache-menue'), false);
  assert.equal((await p.textContent('.leiste button[data-ziel=reden]')).trim(), '聊天');
  assert.equal(await p.getAttribute('html', 'lang'), 'zh-CN');
});

test('Erinnerung geht groß auf, bei "Erledigt" freut sich Biko', async (t) => {
  const p = await angemeldet(t);
  await zu(p, 'einstellen');
  await p.click('#ton-test');
  await p.waitForSelector('#alarm:not([hidden])');
  assert.match(await p.textContent('#alarm-text'), /Erinnerung/);
  await p.click('#alarm-ok');
  assert.equal(await p.getAttribute('#alarm .biko', 'data-mood'), 'jubelt');
  await p.waitForSelector('#alarm', { state: 'hidden' });
});

const gespraecheHolen = (p) => p.evaluate(async () => (await fetch('/api/gespraeche')).json());

test('Nachricht für jemanden: Biko stellt sie ins Gespräch, Kopieren bestätigt mit "Kopiert"', async (t) => {
  const p = await angemeldet(t, { permissions: ['clipboard-read', 'clipboard-write'] });
  assert.equal(await p.locator('[data-ansicht=nachricht], #nachricht-form').count(), 0, 'kein eigener Bereich, kein Formular');
  await fragen(p, 'Schreib Anna danke für die Blumen');
  await p.waitForSelector('.entwurf');
  assert.match(await p.textContent('.entwurf .entwurf-an'), /Nachricht an Anna/);
  assert.match(await p.textContent('.entwurf .entwurf-text'), /^Liebe Anna, vielen Dank/);
  assert.doesNotMatch(await p.textContent('.blase.biko-sagt'), /Liebe Anna/, 'der Text steht nur einmal da');
  await p.click('.entwurf .kopieren');
  await p.waitForSelector('.entwurf .kopieren[data-zustand=ok]');
  assert.equal((await p.textContent('.entwurf .kopieren')).trim(), 'Kopiert');
  assert.match(await p.evaluate(() => navigator.clipboard.readText()), /^Liebe Anna, vielen Dank.*kommen\?$/);
  assert.match(await p.textContent('.entwurf .meldung'), /Einfügen/);
  assert.deepEqual(p.fehler, []);
});

test('Angebote: findet Biko nichts Genaues, steht der Prospekt als Knopf im Gespräch', async (t) => {
  const p = await angemeldet(t);
  await fragen(p, 'Gibt es Angebote für Tee?');
  const link = p.locator('.links a.link-knopf');
  assert.equal(await link.count(), 1);
  assert.equal(await link.getAttribute('href'), 'https://www.billa.at/flugblatt');
  assert.equal(await link.getAttribute('target'), '_blank');
  assert.match(await link.getAttribute('rel'), /noopener/);
  assert.match(await link.textContent(), /Billa Flugblatt.*billa\.at/s);
  const kasten = await link.boundingBox();
  assert.ok(kasten.height >= 56, `Knopf ist groß genug zum Antippen: ${kasten.height}`);
  assert.deepEqual(p.fehler, []);
});

test('Verlauf: frühere Gespräche stehen in der Liste und lassen sich zum Weiterreden öffnen', async (t) => {
  const p = await angemeldet(t, { permissions: ['clipboard-read', 'clipboard-write'] });
  await fragen(p, 'Schreib Anna einen Gruß vom Verlauf-Test');
  await fragen(p, 'Erzähl mir etwas vom Verlauf-Test');
  // "Neues Gespräch" steht im Gespräch selbst und führt zurück zum Startbild
  await p.click('#neu-im-kopf');
  await p.waitForSelector('#reden-kopf.gross');
  assert.equal(await p.locator('#verlauf > *').count(), 0);
  assert.ok(await p.locator('.vorschlag').count() > 0);
  await zu(p, 'gespraeche');
  const zeile = p.locator('li.gespraech', { hasText: 'Schreib Anna einen Gruß vom Verlauf-Test' });
  await zeile.waitFor();
  assert.equal(await zeile.count(), 1, 'beide Fragen gehören zu einem Gespräch');
  await zeile.locator('.oeffnen').click();
  await p.waitForSelector('[data-ansicht=reden]:not([hidden]) .blase.biko-sagt');
  assert.deepEqual(await p.locator('.blase.ich').allTextContents(),
    ['Schreib Anna einen Gruß vom Verlauf-Test', 'Erzähl mir etwas vom Verlauf-Test']);
  assert.equal(await p.locator('.blase.biko-sagt').count(), 2);
  assert.match(await p.textContent('.entwurf .entwurf-text'), /^Liebe Anna/, 'die geschriebene Nachricht ist wieder da');
  assert.equal(await p.locator('#reden-kopf.gross').count(), 0);
  // weiterreden landet im selben Gespräch
  await fragen(p, 'Und noch etwas');
  const liste = await gespraecheHolen(p);
  assert.deepEqual([liste[0].titel, liste[0].anzahl], ['Schreib Anna einen Gruß vom Verlauf-Test', 6]);
  assert.deepEqual(p.fehler, []);
});

test('Verlauf: "Neues Gespräch" beginnt von vorn, das alte bleibt in der Liste', async (t) => {
  const p = await angemeldet(t);
  await fragen(p, 'Erstes Gespräch vom Neu-Test');
  await zu(p, 'gespraeche');
  await p.click('#neues-gespraech');
  await p.waitForSelector('[data-ansicht=reden]:not([hidden]) #reden-kopf.gross');
  await fragen(p, 'Zweites Gespräch vom Neu-Test');
  const titel = (await gespraecheHolen(p)).map((g) => g.titel);
  assert.deepEqual(titel.slice(0, 2), ['Zweites Gespräch vom Neu-Test', 'Erstes Gespräch vom Neu-Test']);
});

test('Beim Öffnen am selben Tag steht das letzte Gespräch wieder da, an einem anderen Tag das Startbild', async (t) => {
  const p = await angemeldet(t, { uhr: new Date() });
  await zu(p, 'gespraeche');
  await p.click('#neues-gespraech'); // heute wurde in anderen Tests schon geredet
  await p.waitForSelector('[data-ansicht=reden]:not([hidden]) #reden-kopf.gross');
  await fragen(p, 'Frage vom Wiederkommen-Test');
  await p.reload();
  await p.waitForSelector('.blase.biko-sagt');
  assert.deepEqual(await p.locator('.blase.ich').allTextContents(), ['Frage vom Wiederkommen-Test']);
  assert.equal(await p.locator('#reden-kopf.gross').count(), 0);
  assert.equal(await p.locator('.vorschlag').count(), 0);
  // ein anderer Tag: Biko begrüßt wieder von vorn, das Gespräch steht im Verlauf
  await p.clock.setFixedTime(new Date(Date.now() + 2 * 86400000));
  await p.reload();
  await p.waitForSelector('#app:not([hidden])');
  await p.waitForSelector('.vorschlag');
  assert.equal(await p.locator('.blase').count(), 0);
  assert.equal(await p.locator('#reden-kopf.gross').count(), 1);
});

test('Gespräch löschen fragt zuerst nach, "Alle Gespräche vergessen" auch', async (t) => {
  const p = await angemeldet(t);
  await fragen(p, 'Frage vom Lösch-Test');
  await zu(p, 'gespraeche');
  const zeile = p.locator('li.gespraech', { hasText: 'Frage vom Lösch-Test' });
  await zeile.locator('.weg').click();
  assert.equal(await zeile.locator('.sicher').isVisible(), true);
  await zeile.locator('.sicher .nein').click();
  assert.equal(await zeile.count(), 1);
  await zeile.locator('.weg').click();
  await zeile.locator('.sicher .ja').click();
  await zeile.waitFor({ state: 'detached' });
  assert.ok(!(await gespraecheHolen(p)).some((g) => g.titel === 'Frage vom Lösch-Test'));
  // das gelöschte Gespräch war das offene: beim Reden steht wieder das Startbild
  await zu(p, 'reden');
  await p.waitForSelector('#reden-kopf.gross');
  await fragen(p, 'Noch eine Frage vom Lösch-Test');
  await zu(p, 'einstellen');
  await p.click('#verlauf-loeschen');
  assert.equal(await p.isVisible('#alle-sicher'), true);
  assert.ok((await gespraecheHolen(p)).length > 0, 'ein Tipp allein löscht noch nichts');
  await p.click('#alle-sicher .ja');
  await p.waitForFunction(() => /vergessen/.test(document.querySelector('#vergessen-info').textContent));
  assert.deepEqual(await gespraecheHolen(p), []);
  await zu(p, 'gespraeche');
  assert.match(await p.textContent('#gespraeche'), /Noch keine Gespräche/);
  await zu(p, 'reden');
  assert.equal(await p.locator('.blase').count(), 0);
});

test('Schalter "immer vorlesen" merkt sich seine Stellung', async (t) => {
  const p = await angemeldet(t);
  await zu(p, 'einstellen');
  assert.equal(await p.getAttribute('#vorlesen', 'aria-checked'), 'false');
  await p.click('#vorlesen');
  assert.equal(await p.getAttribute('#vorlesen', 'aria-checked'), 'true');
  await p.reload();
  await p.waitForSelector('#app:not([hidden])');
  assert.equal(await p.getAttribute('#vorlesen', 'aria-checked'), 'true');
});

test('Schriftgröße "Sehr groß" macht die Schrift größer', async (t) => {
  const p = await angemeldet(t);
  await zu(p, 'einstellen');
  const vorher = await p.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize));
  await p.click('#schrift button[data-wert="1.3"]');
  const nachher = await p.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize));
  assert.ok(nachher > vorher * 1.25, `${vorher} -> ${nachher}`);
  assert.equal(await p.getAttribute('#schrift button[data-wert="1.3"]', 'aria-pressed'), 'true');
});

test('Keine Emojis und keine Gedankenstriche in der Oberfläche', async (t) => {
  const p = await angemeldet(t);
  for (const ziel of ['reden', 'gespraeche', 'einstellen']) {
    await zu(p, ziel);
    await p.waitForTimeout(250);
    const text = await p.innerText('body');
    assert.doesNotMatch(text, /\p{Extended_Pictographic}/u, ziel);
    assert.doesNotMatch(text, /[—–]/, ziel);
  }
});

test('Dunkler Modus: Text bleibt gut lesbar (Kontrast mindestens 4,5 zu 1)', async (t) => {
  const p = await angemeldet(t, { colorScheme: 'dark' });
  const kontrast = await p.evaluate(() => {
    const rgb = (s) => s.match(/[\d.]+/g).slice(0, 3).map(Number);
    const hell = (c) => { const [r, g, b] = c.map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
    const hinter = rgb(getComputedStyle(document.body).backgroundColor);
    const paare = [['body', hinter], ['.leise', hinter]].map(([sel, bg]) => {
      const a = hell(rgb(getComputedStyle(document.querySelector(sel)).color)), b = hell(bg);
      return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    });
    return { paare, hintergrund: hell(hinter) };
  });
  assert.ok(kontrast.hintergrund < 0.1, 'Hintergrund ist dunkel');
  kontrast.paare.forEach((k) => assert.ok(k >= 4.5, `Kontrast ${k.toFixed(2)}`));
});

test('"Bewegung reduzieren": nichts fliegt oder wandert, es wird nur ein- und ausgeblendet', async (t) => {
  const p = await angemeldet(t, { reducedMotion: 'reduce' });
  await zu(p, 'gespraeche');
  await p.click('#sprache-knopf');
  await p.waitForSelector('#sprache-menue:not([hidden])');
  const bewegt = await p.evaluate(() => document.getAnimations()
    .filter((a) => !a.effect.target.closest('.biko'))
    .flatMap((a) => a.effect.getKeyframes())
    .some((k) => (k.transform && k.transform !== 'none') || k.translate || k.scale));
  assert.equal(bewegt, false);
});

test('Tippflächen sind groß genug (mindestens 48 px)', async (t) => {
  const p = await angemeldet(t);
  for (const ziel of ['reden', 'gespraeche', 'einstellen']) {
    await zu(p, ziel);
    await p.waitForTimeout(250);
    const zuKlein = await p.evaluate(() => [...document.querySelectorAll('#app button, #sprache-knopf')]
      .filter((b) => b.offsetParent !== null)
      .map((b) => ({ b, r: b.getBoundingClientRect() }))
      .filter(({ r }) => r.height < 48 || r.width < 48)
      .map(({ b }) => b.id || b.className || b.textContent.trim()));
    assert.deepEqual(zuKlein, [], ziel);
  }
});

test('Enter schickt die Frage ab', async (t) => {
  const p = await angemeldet(t);
  await p.fill('#chat-text', 'Wie geht es dir?');
  await p.press('#chat-text', 'Enter');
  await p.waitForSelector('.blase.ich');
  assert.equal(await p.textContent('.blase.ich'), 'Wie geht es dir?');
});

test('Fehler vom Server: Biko sagt es und der Text bleibt im Feld', async (t) => {
  const p = await angemeldet(t);
  await p.fill('#chat-text', 'a'.repeat(2100));
  await p.click('#chat-knopf');
  await p.waitForSelector('.blase.fehler-blase');
  assert.match(await p.textContent('.blase.fehler-blase'), /Kürzeres/);
  assert.equal(await stimmung(p), 'traurig');
  assert.equal((await p.inputValue('#chat-text')).length, 2100);
});

test('Fällige Erinnerung geht von selbst auf, "später" schließt sie und sie kommt nicht sofort wieder', async (t) => {
  const p = await angemeldet(t, { uhr: '2026-01-05T08:01:00' });
  const vorher = await erinnerungenHolen(p);
  try {
    await erinnerungenSetzen(p, [{ id: 'frueh', zeit: '08:00', text: 'Herztablette' }]);
    await p.reload();
    await p.waitForSelector('#alarm:not([hidden])');
    assert.equal(await p.textContent('#alarm-text'), 'Herztablette');
    await p.click('#alarm-spaeter');
    await p.waitForSelector('#alarm', { state: 'hidden' });
    await p.reload();
    await p.waitForSelector('#app:not([hidden])');
    await p.waitForTimeout(300);
    assert.equal(await p.isVisible('#alarm'), false);
  } finally {
    await erinnerungenSetzen(p, vorher);
  }
});

test('Löschen fragt zuerst nach', async (t) => {
  const p = await angemeldet(t);
  const vorher = await erinnerungenHolen(p);
  try {
    await erinnerungenSetzen(p, [{ id: 'x1', zeit: '09:30', text: 'Augentropfen' }]);
    await p.reload();
    await p.waitForSelector('#app:not([hidden])');
    await zu(p, 'einstellen');
    await p.click('li.erinnerung .weg');
    assert.equal(await p.isVisible('li.erinnerung .sicher'), true);
    await p.click('li.erinnerung .sicher .nein');
    assert.equal(await p.isVisible('li.erinnerung .sicher'), false);
    assert.equal(await p.locator('li.erinnerung').count(), 1);
    await p.click('li.erinnerung .weg');
    await p.click('li.erinnerung .sicher .ja');
    await p.waitForSelector('li.erinnerung', { state: 'detached' });
    assert.match(await p.textContent('#erinnerungen'), /Noch nichts gemerkt/);
  } finally {
    await erinnerungenSetzen(p, vorher);
  }
});

test('Erinnerung im Gespräch: Biko schreibt sie sich auf, zeigt "Gemerkt" und meldet sich zur Uhrzeit', async (t) => {
  const p = await angemeldet(t, { uhr: '2026-01-05T07:59:00' });
  const vorher = await erinnerungenHolen(p);
  try {
    await erinnerungenSetzen(p, []);
    await p.reload();
    await p.waitForSelector('#app:not([hidden])');
    await p.fill('#chat-text', 'Erinnere mich jeden Tag um 8 an die Herztablette');
    await p.click('#chat-knopf');
    await p.waitForSelector('.blase.biko-sagt');
    assert.match(await p.textContent('.notiz'), /Gemerkt.*Herztablette.*08:00/s);
    assert.equal(await p.isVisible('#alarm'), false);
    // ohne Neuladen und ohne Formular: die App kennt die Erinnerung sofort und meldet sich, sobald es 8 Uhr ist
    await p.clock.setFixedTime(new Date('2026-01-05T08:00:00'));
    await p.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await p.waitForSelector('#alarm:not([hidden])');
    assert.equal(await p.textContent('#alarm-text'), 'Herztablette');
    await p.click('#alarm-ok');
    await p.waitForSelector('#alarm', { state: 'hidden' });
    await zu(p, 'einstellen');
    assert.match(await p.textContent('#erinnerungen li.erinnerung'), /08:00.*Herztablette/s);
    assert.equal(await p.locator('#erinnerung-form, #erinnerung-neu').count(), 0, 'kein Formular mehr');
  } finally {
    await erinnerungenSetzen(p, vorher);
  }
});

test('Tägliche Erinnerung, deren Uhrzeit heute schon vorbei ist, platzt nicht sofort herein', async (t) => {
  const p = await angemeldet(t, { uhr: '2026-01-05T08:30:00' });
  const vorher = await erinnerungenHolen(p);
  try {
    await erinnerungenSetzen(p, []);
    await p.reload();
    await p.waitForSelector('#app:not([hidden])');
    await p.fill('#chat-text', 'Erinnere mich jeden Tag um 8 an die Herztablette');
    await p.click('#chat-knopf');
    await p.waitForSelector('.notiz');
    await p.waitForTimeout(400);
    assert.equal(await p.isVisible('#alarm'), false, 'heute ist 8 Uhr vorbei: Biko meldet sich erst morgen');
    await p.reload();
    await p.waitForSelector('#app:not([hidden])');
    await p.waitForTimeout(300);
    assert.equal(await p.isVisible('#alarm'), false, 'auch nach dem Neuladen nicht');
    // am nächsten Morgen meldet er sich
    await p.clock.setFixedTime(new Date('2026-01-06T08:00:00'));
    await p.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await p.waitForSelector('#alarm:not([hidden])');
  } finally {
    await erinnerungenSetzen(p, vorher);
  }
});

test('Biko streicht eine Erinnerung auf Zuruf und zeigt das an', async (t) => {
  const p = await angemeldet(t);
  const vorher = await erinnerungenHolen(p);
  try {
    await erinnerungenSetzen(p, [{ id: 'x1', zeit: '09:30', text: 'Augentropfen' }]);
    await p.reload();
    await p.waitForSelector('#app:not([hidden])');
    await p.fill('#chat-text', 'Vergiss die Augentropfen');
    await p.click('#chat-knopf');
    await p.waitForSelector('.blase.biko-sagt');
    assert.match(await p.textContent('.notiz'), /Gestrichen.*Augentropfen/s);
    await zu(p, 'einstellen');
    assert.equal(await p.locator('li.erinnerung').count(), 0);
  } finally {
    await erinnerungenSetzen(p, vorher);
  }
});

test('Schalter lässt sich ziehen: folgt dem Finger ohne Verzögerung und gibt am Rand nach', async (t) => {
  const p = await angemeldet(t);
  await zu(p, 'einstellen');
  await p.waitForTimeout(500);
  assert.equal(await p.getAttribute('#vorlesen', 'aria-checked'), 'false');
  await p.locator('#vorlesen').evaluate((el) => el.scrollIntoView({ block: 'center' }));
  const b = await p.locator('#vorlesen .knauf').boundingBox();
  const x = b.x + b.width / 2, y = b.y + b.height / 2;
  const versatz = () => p.evaluate(() => new DOMMatrix(getComputedStyle(document.querySelector('#vorlesen .knauf')).transform).m41);
  await p.mouse.move(x, y);
  await p.mouse.down();
  await p.mouse.move(x + 10, y);
  assert.equal(Math.round(await versatz()), 10, 'folgt sofort, ohne Übergang');
  await p.mouse.move(x + 120, y);
  const weit = await versatz();
  assert.ok(weit > 20 && weit < 30, `Gummiband am rechten Rand: ${weit}`);
  await p.mouse.up();
  assert.equal(await p.getAttribute('#vorlesen', 'aria-checked'), 'true');
  await p.waitForTimeout(300);
  assert.equal(Math.round(await versatz()), 20);
});

test('Biko merkt sich, was man über sich erzählt, und in den Einstellungen kann man es löschen', async (t) => {
  const p = await angemeldet(t);
  await zu(p, 'einstellen');
  assert.equal(await p.locator('#profil-diaet, #profil-notizen').count(), 0, 'keine Felder für Diät und Notizen mehr');
  assert.equal(await p.isVisible('#profil-name'), true);
  await zu(p, 'reden');
  await fragen(p, 'Ich hab Diabetes');
  await p.waitForSelector('.notiz.gelernt');
  assert.match(await p.textContent('.notiz.gelernt'), /Weiß ich jetzt.*Hat Diabetes/s);
  await zu(p, 'einstellen');
  const zeile = p.locator('#wissen li.wissen-zeile', { hasText: 'Hat Diabetes' });
  await zeile.waitFor();
  await zeile.locator('.weg').click();
  await zeile.locator('.sicher .ja').click();
  await p.waitForFunction(() => !document.querySelector('#wissen').textContent.includes('Hat Diabetes'));
  assert.deepEqual(await p.evaluate(async () => (await fetch('/api/wissen')).json()), []);
  assert.deepEqual(p.fehler, []);
});
