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
  browser = await chromium.launch();
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
};

// Die Uhr steht fest (Montag, 15 Uhr), damit keine Erinnerung von selbst in einen Test platzt
async function seite(t, { uhr = '2026-01-05T15:00:00', ...optionen } = {}) {
  const kontext = await browser.newContext({ ...devices['iPhone 13'], ...optionen });
  t.after(() => kontext.close());
  const p = await kontext.newPage();
  p.setDefaultTimeout(4000);
  const fehler = [];
  p.on('pageerror', (e) => fehler.push(e.message));
  p.on('console', (m) => { if (m.type() === 'error') fehler.push(m.text()); });
  p.fehler = fehler;
  await p.addInitScript(FALSCHES_MIKRO);
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

test('Sprechen: Biko hört zu, der Satz wird von selbst gesendet', async (t) => {
  const p = await angemeldet(t);
  await p.click('#chat-knopf');
  assert.equal(await p.getAttribute('#chat-knopf', 'data-art'), 'stopp');
  assert.equal(await stimmung(p), 'hoert');
  await p.waitForSelector('.blase.ich');
  assert.equal(await p.textContent('.blase.ich'), 'Hallo Biko');
  await p.waitForSelector('.blase.biko-sagt');
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
  assert.deepEqual(await p.locator('.leiste button').evaluateAll((l) => l.map((b) => b.dataset.ziel)), ['reden', 'nachricht', 'einstellen'],
    'einen eigenen Bereich für Erinnerungen gibt es nicht mehr');
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

test('Nachricht schreiben und kopieren bestätigt mit "Kopiert"', async (t) => {
  const p = await angemeldet(t, { permissions: ['clipboard-read', 'clipboard-write'] });
  await zu(p, 'nachricht');
  await p.fill('#nachricht-an', 'Anna');
  await p.fill('#nachricht-was', 'danke für die Blumen');
  await p.click('#nachricht-form button[type=submit]');
  await p.waitForSelector('#nachricht-ergebnis:not([hidden])');
  assert.match(await p.textContent('#nachricht-text'), /Liebe Anna/);
  await p.click('#nachricht-kopieren');
  await p.waitForSelector('#nachricht-kopieren[data-zustand=ok]');
  assert.equal((await p.textContent('#nachricht-kopieren')).trim(), 'Kopiert');
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
  for (const ziel of ['reden', 'nachricht', 'einstellen']) {
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
  await zu(p, 'nachricht');
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
  for (const ziel of ['reden', 'nachricht', 'einstellen']) {
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
