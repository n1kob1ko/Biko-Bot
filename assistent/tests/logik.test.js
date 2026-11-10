// Tests für die reine Logik der Oberfläche (ohne Browser):  node --test tests/logik.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const L = require('../web/logik.js');
const T = require('../web/texte.js');

const um = (hhmm, tag = '2026-11-09') => new Date(`${tag}T${hhmm}:00`); // 9.11.2026 ist ein Montag
const tablette = { id: 'a', zeit: '08:00', text: 'Tablette', tage: ['mo', 'di', 'mi', 'do', 'fr', 'sa', 'so'], aktiv: true };

test('Erinnerung ist fällig, sobald ihre Uhrzeit erreicht ist', () => {
  assert.equal(L.faelligeErinnerung({ erinnerungen: [tablette], jetzt: um('08:00') }).id, 'a');
});

test('Einmalige Erinnerung ist nur an ihrem Tag fällig', () => {
  const arzt = { ...tablette, id: 'arzt', datum: '2026-11-10' };
  assert.equal(L.faelligeErinnerung({ erinnerungen: [arzt], jetzt: um('08:00', '2026-11-09') }), null);
  assert.equal(L.faelligeErinnerung({ erinnerungen: [arzt], jetzt: um('08:00', '2026-11-10') }).id, 'arzt');
  assert.equal(L.faelligeErinnerung({ erinnerungen: [arzt], jetzt: um('08:00', '2026-11-11') }), null);
});

test('Wann eine Erinnerung kommt, steht kurz und klar da', () => {
  const texte = { jeden_tag: 'jeden Tag', einmal_am: 'einmal am {t}.{m}.', heute: 'heute', morgen: 'morgen', tage: { mo: 'Mo', mi: 'Mi' } };
  const jetzt = um('12:00', '2026-11-09');
  assert.equal(L.wannText(tablette, texte, jetzt), 'jeden Tag');
  assert.equal(L.wannText({ ...tablette, tage: ['mo', 'mi'] }, texte, jetzt), 'Mo, Mi');
  assert.equal(L.wannText({ ...tablette, tage: ['mo', 'mi'] }, { ...texte, tage: { mo: '周一', mi: '周三' }, tage_trenner: '、' }, jetzt), '周一、周三');
  assert.equal(L.wannText({ ...tablette, datum: '2026-11-09' }, texte, jetzt), 'heute');
  assert.equal(L.wannText({ ...tablette, datum: '2026-11-10' }, texte, jetzt), 'morgen');
  assert.equal(L.wannText({ ...tablette, datum: '2026-12-24' }, texte, jetzt), 'einmal am 24.12.');
  assert.equal(L.wannText({ ...tablette, datum: '2026-12-24' }, { ...texte, einmal_am: '{m}月{t}日' }, jetzt), '12月24日');
});

test('Erinnerung ist vor ihrer Uhrzeit nicht fällig', () => {
  assert.equal(L.faelligeErinnerung({ erinnerungen: [tablette], jetzt: um('07:59') }), null);
});

test('Erinnerung kommt heute nicht noch einmal, wenn sie schon gezeigt wurde', () => {
  const gezeigt = new Set([L.gezeigtSchluessel(tablette, um('08:05'))]);
  assert.equal(L.faelligeErinnerung({ erinnerungen: [tablette], jetzt: um('08:05'), gezeigt }), null);
});

test('Erinnerung wird höchstens zwei Stunden lang nachgeholt', () => {
  assert.equal(L.faelligeErinnerung({ erinnerungen: [tablette], jetzt: um('10:00') }).id, 'a');
  assert.equal(L.faelligeErinnerung({ erinnerungen: [tablette], jetzt: um('10:01') }), null);
});

test('Erinnerung gilt nur an ihren Wochentagen', () => {
  const nurDienstag = { ...tablette, tage: ['di'] };
  assert.equal(L.faelligeErinnerung({ erinnerungen: [nurDienstag], jetzt: um('08:00') }), null);
  assert.equal(L.faelligeErinnerung({ erinnerungen: [nurDienstag], jetzt: um('08:00', '2026-11-10') }).id, 'a');
});

test('Ausgeschaltete Erinnerung ist nie fällig', () => {
  assert.equal(L.faelligeErinnerung({ erinnerungen: [{ ...tablette, aktiv: false }], jetzt: um('08:00') }), null);
});

test('"In 10 Minuten nochmal" bringt die Erinnerung zurück, obwohl sie schon gezeigt wurde', () => {
  const jetzt = um('08:15');
  const gezeigt = new Set([L.gezeigtSchluessel(tablette, jetzt)]);
  const spaeter = { a: jetzt.getTime() - 1000 };
  assert.equal(L.faelligeErinnerung({ erinnerungen: [tablette], jetzt, gezeigt, spaeter }).id, 'a');
  const nochNicht = { a: jetzt.getTime() + 60000 };
  assert.equal(L.faelligeErinnerung({ erinnerungen: [tablette], jetzt, gezeigt, spaeter: nochNicht }), null);
});

test('Vorlese-Sprache richtet sich nach dem Text', () => {
  assert.equal(L.spracheVonText('Guten Morgen, Biko'), 'de-AT');
  assert.equal(L.spracheVonText('这周 Billa 的咖啡打七折'), 'zh-CN');
});

test('Der große Knopf ist Mikrofon, Senden oder Stopp', () => {
  assert.equal(L.knopfArt('', false), 'mikro');
  assert.equal(L.knopfArt('   ', false), 'mikro');
  assert.equal(L.knopfArt('Hallo', false), 'senden');
  assert.equal(L.knopfArt('Hallo', true), 'stopp');
  assert.equal(L.knopfArt('', true), 'stopp');
});

test('Gummiband: Ziehen über die Grenze wird immer schwerer und bleibt begrenzt', () => {
  assert.equal(L.gummiband(0, 120), 0);
  const a = L.gummiband(50, 120), b = L.gummiband(100, 120), c = L.gummiband(5000, 120);
  assert.ok(a > 0 && a < 50, 'weniger als der Finger');
  assert.ok(b > a, 'wächst weiter');
  assert.ok(b - a < a, 'aber langsamer');
  assert.ok(c < 120, 'nie über die Grenze');
});

test('Bogen: der Weg von A nach B verläuft gekrümmt, nicht auf einer Geraden', () => {
  const k = L.bogen(200, -100, 5);
  assert.deepEqual(k[0], { x: 200, y: -100 });
  assert.deepEqual(k[k.length - 1], { x: 0, y: 0 });
  const mitte = k[Math.floor(k.length / 2)];
  const aufGerade = mitte.x * -100 - mitte.y * 200; // Kreuzprodukt mit der Geraden = 0, wenn der Punkt darauf liegt
  assert.ok(Math.abs(aufGerade) > 1000, 'Mittelpunkt liegt neben der Geraden');
});

test('Dehnung: ein wandernder Knopf ist unterwegs 12 % breiter, am Anfang und Ende normal', () => {
  const k = L.dehnung(0, 80);
  assert.equal(k[0].transform, 'translateX(0px) scaleX(1)');
  assert.equal(k[1].transform, 'translateX(40px) scaleX(1.12)');
  assert.equal(k[2].transform, 'translateX(80px) scaleX(1)');
});

test('Ausgänge sind 20 % kürzer als Eingänge', () => {
  assert.equal(L.ausgang(200), 160);
  assert.equal(L.ausgang(320), 256);
});

test('Am selben Tag redet man im letzten Gespräch weiter, an einem neuen Tag beginnt ein neues', () => {
  const jetzt = um('15:00', '2026-11-10');
  assert.equal(L.weiterreden('2026-11-10T08:30:00+01:00', jetzt), true);
  assert.equal(L.weiterreden(um('00:05', '2026-11-10').toISOString(), jetzt), true);
  assert.equal(L.weiterreden(um('23:55', '2026-11-09').toISOString(), jetzt), false);
  assert.equal(L.weiterreden('', jetzt), false);
  assert.equal(L.weiterreden(undefined, jetzt), false);
  assert.equal(L.weiterreden('kein Datum', jetzt), false);
});

test('Wann ein Gespräch war, steht kurz da: heute und gestern mit Uhrzeit, sonst der Tag', () => {
  const texte = { heute: 'heute', gestern: 'gestern', tag_kurz: '{t}.{m}.', zeit_trenner: ', ' };
  const jetzt = um('15:00', '2026-11-10');
  assert.equal(L.wannWar(um('08:05', '2026-11-10').toISOString(), jetzt, texte), 'heute, 08:05');
  assert.equal(L.wannWar(um('21:40', '2026-11-09').toISOString(), jetzt, texte), 'gestern, 21:40');
  assert.equal(L.wannWar(um('21:40', '2026-11-03').toISOString(), jetzt, texte), '3.11.');
  assert.equal(L.wannWar(um('21:40', '2026-11-03').toISOString(), jetzt, { ...texte, tag_kurz: '{m}月{t}日' }), '11月3日');
  assert.equal(L.wannWar(um('08:05', '2026-11-10').toISOString(), jetzt, { ...texte, heute: '今天', zeit_trenner: ' ' }), '今天 08:05');
  assert.equal(L.wannWar('kein Datum', jetzt, texte), '');
});

test('Links: nur sichere Adressen werden zu einem Knopf, gezeigt wird der Name der Seite', () => {
  assert.equal(L.linkSeite('https://www.billa.at/flugblatt'), 'billa.at');
  assert.equal(L.linkSeite('https://flugblatt.hofer.at/woche?x=1'), 'flugblatt.hofer.at');
  assert.equal(L.linkSeite('http://www.billa.at/flugblatt'), '');
  assert.equal(L.linkSeite('javascript:alert(1)'), '');
  assert.equal(L.linkSeite('billa.at'), '');
  assert.equal(L.linkSeite(undefined), '');
});

test('Vorgelesen wird Bikos Antwort und danach die Nachricht, die er geschrieben hat', () => {
  assert.equal(L.vorleseText('Hier ist die Nachricht.', [{ an: 'Anna', text: 'Liebe Anna, danke!' }]), 'Hier ist die Nachricht.\n\nLiebe Anna, danke!');
  assert.equal(L.vorleseText('Nur die Antwort.', []), 'Nur die Antwort.');
  assert.equal(L.vorleseText('Nur die Antwort.'), 'Nur die Antwort.');
});

test('Jeder deutsche Text hat eine chinesische Fassung und umgekehrt', () => {
  assert.deepEqual(Object.keys(T.zh).sort(), Object.keys(T.de).sort());
});

test('Texte enthalten keine Emojis und keine Gedankenstriche', () => {
  const alle = (o) => Object.values(o).flatMap((v) => (typeof v === 'string' ? [v] : alle(v)));
  for (const s of [...alle(T.de), ...alle(T.zh)]) {
    assert.doesNotMatch(s, /\p{Extended_Pictographic}/u, s);
    assert.doesNotMatch(s, /[—–]/, s);
  }
});
