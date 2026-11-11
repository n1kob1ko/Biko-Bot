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

test('Die Wecker der Android-App: kommende Erinnerungen und die Morgenrunde, die nächste zuerst', () => {
  const arzt = { ...tablette, id: 'arzt', zeit: '15:00', text: 'Arzt', datum: '2026-11-10' };
  const turnen = { ...tablette, id: 'turnen', zeit: '10:00', text: 'Turnen', tage: ['mi'] };
  const aus = { ...tablette, id: 'aus', aktiv: false };
  const liste = L.naechsteMeldungen({ erinnerungen: [tablette, arzt, turnen, aus], morgenrunde: '07:30', jetzt: um('09:00'), stunden: 48 });
  const kurz = liste.map((m) => `${new Date(m.wann).getDate()}. ${new Date(m.wann).toTimeString().slice(0, 5)} ${m.art} ${m.id}`);
  assert.deepEqual(kurz, [
    '10. 07:30 morgenrunde morgenrunde',
    '10. 08:00 erinnerung a',
    '10. 15:00 erinnerung arzt',
    '11. 07:30 morgenrunde morgenrunde',
    '11. 08:00 erinnerung a',
  ]); // heute 8 Uhr ist vorbei, Turnen ist erst am Mittwoch um 10 (nach 48 Stunden)
  assert.equal(liste[1].text, 'Tablette');
  assert.deepEqual(L.naechsteMeldungen({ erinnerungen: [], morgenrunde: null, jetzt: um('09:00') }), []);
});

test('Geburtstage: am Tag um 9 Uhr, mit Morgenrunde sagt Biko es dort', () => {
  const peter = { id: 'p', name: 'Peter', tag: 10, monat: 11, jahr: 1986 };
  const rosa = { id: 'r', name: 'Rosa', tag: 29, monat: 2, jahr: null };
  const liste = L.naechsteMeldungen({ erinnerungen: [], geburtstage: [peter, rosa], jetzt: um('09:00') });
  assert.deepEqual(liste.map((m) => [new Date(m.wann).getDate(), m.art, m.id, m.name, m.alter]), [[10, 'geburtstag', 'gb-p', 'Peter', 40]]);
  assert.deepEqual(L.naechsteMeldungen({ erinnerungen: [], morgenrunde: '08:00', geburtstage: [peter], jetzt: um('09:00') }).map((m) => m.art), ['morgenrunde', 'morgenrunde']);
  // 29.2. in einem Jahr ohne Schalttag: am 28.2.
  const feb = L.naechsteMeldungen({ erinnerungen: [], geburtstage: [rosa], jetzt: um('10:00', '2027-02-27') });
  assert.deepEqual(feb.map((m) => [new Date(m.wann).getMonth() + 1, new Date(m.wann).getDate(), m.alter]), [[2, 28, null]]);
});

test('Check-in: jeden Tag zur Uhrzeit ein Wecker', () => {
  const liste = L.naechsteMeldungen({ erinnerungen: [], checkin: '10:00', jetzt: um('09:00') });
  assert.deepEqual(liste.map((m) => `${new Date(m.wann).getDate()}. ${new Date(m.wann).toTimeString().slice(0, 5)} ${m.art}`),
    ['9. 10:00 checkin', '10. 10:00 checkin']);
});

test('Anrufen, WhatsApp und SMS: Nummern werden zu Links, österreichische Nummern international', () => {
  assert.equal(L.telLink('0664 / 123 45-67'), 'tel:06641234567');
  assert.equal(L.telLink('144'), 'tel:144');
  assert.equal(L.telLink('ruf an'), '');
  assert.equal(L.waNummer('0664 1234567'), '436641234567');
  assert.equal(L.waNummer('+86 138 0013 8000'), '8613800138000');
  assert.equal(L.waNummer('0049 170 123'), '49170123');
  assert.equal(L.sendeLink({ ueber: 'whatsapp', nummer: '0664 1234567', text: 'Ich komme um 5!' }), 'https://wa.me/436641234567?text=Ich%20komme%20um%205!');
  assert.equal(L.sendeLink({ ueber: 'whatsapp', text: 'Hallo' }), 'https://wa.me/?text=Hallo');
  assert.equal(L.sendeLink({ ueber: 'sms', nummer: '0664 1234567', text: 'Hallo' }), 'sms:06641234567?body=Hallo');
  assert.equal(L.sendeLink({ ueber: 'wechat', text: 'Hallo' }), '');
  assert.equal(L.sendeLink({ text: 'Hallo' }), '');
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

test('Aufnahme: nach dem Sprechen beendet eine Pause die Aufnahme von selbst', () => {
  assert.equal(L.aufnahmeEnde({ dauer: 3000, gesprochen: true, stille: 500 }), 'weiter');
  assert.equal(L.aufnahmeEnde({ dauer: 3000, gesprochen: true, stille: 1800 }), 'fertig');
  // wer noch nichts gesagt hat, bekommt Zeit zum Überlegen
  assert.equal(L.aufnahmeEnde({ dauer: 5000, gesprochen: false, stille: 5000 }), 'weiter');
  // danach geht die Aufnahme trotzdem zum Verstehen: vielleicht hat jemand nur sehr leise gesprochen
  assert.equal(L.aufnahmeEnde({ dauer: 8000, gesprochen: false, stille: 8000 }), 'fertig');
  // nach einer Minute ist Schluss, auch wenn jemand ohne Pause weiterredet
  assert.equal(L.aufnahmeEnde({ dauer: 59000, gesprochen: true, stille: 0 }), 'weiter');
  assert.equal(L.aufnahmeEnde({ dauer: 60000, gesprochen: true, stille: 0 }), 'fertig');
});

test('Aufnahme: laut ist, was deutlich über dem Grundrauschen und nahe an der bisherigen Spitze liegt', () => {
  assert.equal(L.istLaut(0.005, 0), false, 'Rauschen');
  assert.equal(L.istLaut(0.05, 0), true, 'normale Stimme');
  assert.equal(L.istLaut(0.03, 0.2), false, 'leises Nachklingen nach lautem Sprechen zählt als Pause');
  assert.equal(L.istLaut(0.08, 0.2), true);
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

// ---------- Reden wie am Telefon ----------

test('Antwort in Sätze teilen: fertige Sätze gehen gleich zum Sprechen, der Rest wartet', () => {
  assert.deepEqual(L.saetzeTeilen('Hallo Anna! Wie geht es dir? Ich hab'), { saetze: ['Hallo Anna!', 'Wie geht es dir?'], rest: ' Ich hab' });
  assert.deepEqual(L.saetzeTeilen('Ein Satz.'), { saetze: [], rest: 'Ein Satz.' }, 'ohne Leerzeichen danach kann noch etwas kommen');
  assert.deepEqual(L.saetzeTeilen('Ein Satz.', true), { saetze: ['Ein Satz.'], rest: '' });
  // Der Anfang einer langen Antwort geht schon am ersten Komma an die Stimme, kurze Anfänge und Zahlen nicht
  assert.deepEqual(L.fruehStueck('Das ist eine wirklich gute Frage, und die Antwort'), { stueck: 'Das ist eine wirklich gute Frage,', rest: ' und die Antwort' });
  assert.equal(L.fruehStueck('Gerne, ich schau nach'), null);
  assert.equal(L.fruehStueck('Der Preis liegt heute bei 3,50 Euro und'), null);
  assert.deepEqual(L.fruehStueck('这个问题很好，我来解释'), { stueck: '这个问题很好，', rest: '我来解释' });
  assert.deepEqual(L.saetzeTeilen('Moment, ich schau nach.\nBei Billa'), { saetze: ['Moment, ich schau nach.'], rest: 'Bei Billa' });
});

test('Sätze teilen: Zahlen, Datum und Abkürzungen beenden keinen Satz', () => {
  assert.deepEqual(L.saetzeTeilen('Am 24. Dezember um 8.30 Uhr, z. B. mit Dr. Huber. Gut'),
    { saetze: ['Am 24. Dezember um 8.30 Uhr, z. B. mit Dr. Huber.'], rest: ' Gut' });
});

test('Sätze teilen: Chinesisch braucht kein Leerzeichen nach dem Satzzeichen', () => {
  assert.deepEqual(L.saetzeTeilen('你好！今天天气很好。我们'), { saetze: ['你好！', '今天天气很好。'], rest: '我们' });
  assert.deepEqual(L.saetzeTeilen('“好的。”然后'), { saetze: ['“好的。”'], rest: '然后' });
});

test('Echo: was Biko selbst gerade sagt, zählt nicht als Antwort der Person', () => {
  const gesagt = 'Diese Woche gibt es bei Billa Kaffee um 30 Prozent günstiger.';
  assert.equal(L.istEcho('bei Billa Kaffee günstiger', gesagt), true);
  assert.equal(L.istEcho('Warte, ich hab eine Frage', gesagt), false);
  assert.equal(L.istEcho('Hallo', ''), false);
  assert.equal(L.istEcho('今天天气', '今天天气很好。'), true);
  assert.equal(L.istEcho('等一下', '今天天气很好。'), false);
});

test('Ins Wort fallen: erst bei richtigen Worten, nicht bei einem Räuspern oder dem eigenen Echo', () => {
  const gesagt = 'Diese Woche gibt es bei Billa Kaffee günstiger.';
  assert.equal(L.istUnterbrechung('Moment mal', gesagt), true);
  assert.equal(L.istUnterbrechung('Stopp', gesagt), true);
  assert.equal(L.istUnterbrechung('mhm', gesagt), false);
  assert.equal(L.istUnterbrechung('  ', gesagt), false);
  assert.equal(L.istUnterbrechung('Billa Kaffee', gesagt), false);
  assert.equal(L.istUnterbrechung('等等', '今天天气很好。'), true);
  assert.equal(L.istUnterbrechung('嗯', '今天天气很好。'), false);
});

test('Server-Sent Events lesen, auch wenn ein Ereignis in zwei Stücken ankommt', () => {
  const a = L.sseLesen('data: {"text":"Hal"}\n\ndata: {"text":"lo"}\n\ndata: {"fer');
  assert.deepEqual(a.ereignisse, [{ text: 'Hal' }, { text: 'lo' }]);
  const b = L.sseLesen(a.rest + 'tig":{"antwort":"Hallo"}}\n\n');
  assert.deepEqual(b, { ereignisse: [{ fertig: { antwort: 'Hallo' } }], rest: '' });
});

test('Ton aus dem Netz: 16-Bit-Stücke werden zu Zahlen, ein halbes Byte wartet aufs nächste Stück', () => {
  const a = L.pcmLesen(null, new Uint8Array([0x00, 0x40, 0x00, 0xc0, 0xff]));
  assert.deepEqual(Array.from(a.werte), [0.5, -0.5]);
  assert.deepEqual(Array.from(a.rest), [0xff]);
  const b = L.pcmLesen(a.rest, new Uint8Array([0x7f]));
  assert.equal(b.werte.length, 1);
  assert.ok(Math.abs(b.werte[0] - 1) < 0.001);
  assert.equal(b.rest, null);
});
