// Reine Logik der Oberfläche, ohne Browser testbar (tests/logik.test.js).
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.BikoLogik = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const JS_TAG = ['so', 'mo', 'di', 'mi', 'do', 'fr', 'sa']; // Date.getDay()
  const NACHHOLEN_MIN = 120; // so lange wird eine verpasste Erinnerung noch gezeigt

  const zwei = (n) => String(n).padStart(2, '0');
  const datum = (d) => `${d.getFullYear()}-${zwei(d.getMonth() + 1)}-${zwei(d.getDate())}`;

  // Unter diesem Namen merkt sich das Handy, dass eine Erinnerung heute schon gezeigt wurde
  function gezeigtSchluessel(er, jetzt) {
    return `gezeigt-${er.id}-${datum(jetzt)}`;
  }

  // Welche Erinnerung soll jetzt aufgehen? `gezeigt`: Set der Schlüssel von heute,
  // `spaeter`: { id: Zeitpunkt in ms } für "In 10 Minuten nochmal".
  function faelligeErinnerung({ erinnerungen, jetzt, gezeigt = new Set(), spaeter = {} }) {
    const tag = JS_TAG[jetzt.getDay()];
    const minuten = jetzt.getHours() * 60 + jetzt.getMinutes();
    for (const er of erinnerungen) {
      if (!er.aktiv || !er.tage.includes(tag)) continue;
      if (er.datum && er.datum !== datum(jetzt)) continue; // einmalige Erinnerung: nur an ihrem Tag
      const [h, m] = er.zeit.split(':').map(Number);
      const seit = minuten - (h * 60 + m);
      if (seit < 0 || seit > NACHHOLEN_MIN) continue;
      const nochmal = spaeter[er.id] !== undefined;
      if (nochmal ? spaeter[er.id] <= jetzt.getTime() : !gezeigt.has(gezeigtSchluessel(er, jetzt))) return er;
    }
    return null;
  }

  // Wann sich Biko in den nächsten Stunden von selbst meldet, für die Wecker der Android-App (die meldet sich auch,
  // wenn Biko gerade nicht offen ist): [{ wann (ms), art: 'erinnerung' | 'morgenrunde', id, text }], die nächste zuerst
  function naechsteMeldungen({ erinnerungen, morgenrunde, jetzt, stunden = 48 }) {
    const ab = jetzt.getTime(), bis = ab + stunden * 3600 * 1000;
    const liste = [];
    for (let plus = 0; plus <= Math.ceil(stunden / 24); plus++) {
      const tag = new Date(jetzt.getFullYear(), jetzt.getMonth(), jetzt.getDate() + plus);
      const um = (zeit) => {
        const [h, m] = zeit.split(':').map(Number);
        return new Date(tag.getFullYear(), tag.getMonth(), tag.getDate(), h, m).getTime();
      };
      const dazu = (eintrag, wann) => { if (wann > ab && wann <= bis) liste.push({ wann, ...eintrag }); };
      for (const er of erinnerungen || []) {
        if (!er.aktiv || !er.tage.includes(JS_TAG[tag.getDay()])) continue;
        if (er.datum && er.datum !== datum(tag)) continue;
        dazu({ art: 'erinnerung', id: er.id, text: er.text }, um(er.zeit));
      }
      if (morgenrunde) dazu({ art: 'morgenrunde', id: 'morgenrunde', text: '' }, um(morgenrunde));
    }
    return liste.sort((a, b) => a.wann - b.wann).slice(0, 30);
  }

  // Wann kommt die Erinnerung? Kurz in Worten: "jeden Tag", "Mo, Mi", "heute", "morgen", "einmal am 24.12." (Vorlage mit {t} und {m})
  function wannText(er, texte, jetzt) {
    if (er.datum) {
      if (er.datum === datum(jetzt)) return texte.heute;
      const morgen = new Date(jetzt.getFullYear(), jetzt.getMonth(), jetzt.getDate() + 1);
      if (er.datum === datum(morgen)) return texte.morgen;
      const [, monat, tag] = er.datum.split('-').map(Number);
      return texte.einmal_am.replace('{t}', tag).replace('{m}', monat);
    }
    if (er.tage.length === 7) return texte.jeden_tag;
    return er.tage.map((x) => texte.tage[x]).join(texte.tage_trenner || ', ');
  }

  // Gespräche: am selben Tag redet man im letzten weiter, an einem neuen Tag beginnt von selbst ein neues
  function weiterreden(zuletzt, jetzt) {
    const d = new Date(zuletzt || NaN);
    return !isNaN(d) && datum(d) === datum(jetzt);
  }

  // Wann war ein Gespräch? "heute, 08:05", "gestern, 21:40", sonst der Tag (Vorlage mit {t} und {m})
  function wannWar(zuletzt, jetzt, texte) {
    const d = new Date(zuletzt || NaN);
    if (isNaN(d)) return '';
    const uhr = `${zwei(d.getHours())}:${zwei(d.getMinutes())}`;
    const trenner = texte.zeit_trenner || ', ';
    if (datum(d) === datum(jetzt)) return texte.heute + trenner + uhr;
    const gestern = new Date(jetzt.getFullYear(), jetzt.getMonth(), jetzt.getDate() - 1);
    if (datum(d) === datum(gestern)) return texte.gestern + trenner + uhr;
    return texte.tag_kurz.replace('{t}', d.getDate()).replace('{m}', d.getMonth() + 1);
  }

  // Ein Link wird nur zum Knopf, wenn er sicher ist (https). Liefert den Namen der Seite, sonst ''.
  function linkSeite(url) {
    const m = /^https:\/\/([a-z0-9.-]+\.[a-z]{2,})(?:[/?#]\S*)?$/i.exec(String(url || ''));
    return m ? m[1].toLowerCase().replace(/^www\./, '') : '';
  }

  // Was vorgelesen wird: die Antwort und danach die Nachrichten, die Biko für jemanden geschrieben hat
  function vorleseText(antwort, nachrichten) {
    return [antwort, ...(nachrichten || []).map((n) => n.text)].join('\n\n');
  }

  // Chinesische Schriftzeichen im Text -> chinesische Stimme, sonst deutsche
  function spracheVonText(text) {
    return /[一-鿿]/.test(text) ? 'zh-CN' : 'de-AT';
  }

  // Der große Knopf neben dem Textfeld
  function knopfArt(text, hoert) {
    if (hoert) return 'stopp';
    return text.trim() ? 'senden' : 'mikro';
  }

  // Aufnahme mit dem Mikrofon: laut ist, was deutlich über dem Grundrauschen liegt und nicht nur
  // das Nachklingen von lautem Sprechen ist. `rms`: Lautstärke jetzt, `spitze`: lauteste Stelle bisher (0 bis 1).
  function istLaut(rms, spitze) {
    return rms > Math.max(0.015, spitze * 0.25);
  }

  // Wann hört Biko von selbst auf zuzuhören? Zeiten in ms. Nach dem Sprechen reicht eine Pause. Wer noch nichts
  // gesagt hat, bekommt Zeit zum Überlegen. Danach geht die Aufnahme trotzdem zum Verstehen, falls nur sehr
  // leise gesprochen wurde. Nach einer Minute ist immer Schluss.
  function aufnahmeEnde({ dauer, gesprochen, stille }) {
    if (dauer >= 60000) return 'fertig';
    return (gesprochen ? stille >= 1800 : dauer >= 8000) ? 'fertig' : 'weiter';
  }

  // Ziehen über eine Grenze hinaus: folgt dem Finger immer weniger, nie weiter als `grenze`
  function gummiband(weg, grenze) {
    if (weg <= 0) return 0;
    return grenze * (1 - 1 / (weg / grenze + 1));
  }

  // Punkte für einen Flug von (dx, dy) nach (0, 0) auf einem Bogen:
  // waagrecht bremst die Bewegung, senkrecht beschleunigt sie, dadurch krümmt sich der Weg.
  function bogen(dx, dy, schritte) {
    const punkte = [];
    for (let i = 0; i <= schritte; i++) {
      const t = i / schritte;
      const x = dx * (1 - t) * (1 - t);
      const y = dy * (1 - t * t);
      punkte.push({ x: Math.round(x * 100) / 100 || 0, y: Math.round(y * 100) / 100 || 0 });
    }
    return punkte;
  }

  // Wandernder Knopf (Schalter, Kissen in der Leiste): unterwegs 12 % breiter
  function dehnung(von, nach) {
    return [
      { transform: `translateX(${von}px) scaleX(1)` },
      { transform: `translateX(${(von + nach) / 2}px) scaleX(1.12)` },
      { transform: `translateX(${nach}px) scaleX(1)` },
    ];
  }

  // Ausgänge laufen 20 % kürzer als Eingänge
  function ausgang(ms) {
    return Math.round(ms * 0.8);
  }

  // ---------- Reden wie am Telefon ----------

  const ZH_ENDE = '。！？；', ENDE = '.!?…', ZU = '”」』）"\'';
  const ABKUERZUNG = new Set(['ca', 'dr', 'nr', 'bzw', 'usw', 'evtl', 'ggf', 'inkl', 'st', 'hr', 'fr', 'mag', 'ing', 'prof', 'tel', 'vgl', 'ab']);
  // Biko spricht Satz für Satz, während die Antwort noch kommt. Liefert die fertigen Sätze und was noch wartet.
  // `ende`: die Antwort ist vollständig, der Rest wird auch gesprochen.
  function saetzeTeilen(puffer, ende = false) {
    const saetze = [];
    let start = 0;
    const nimm = (bis, weiter) => {
      const satz = puffer.slice(start, bis).trim();
      if (satz) saetze.push(satz);
      start = weiter;
    };
    for (let i = 0; i < puffer.length; i++) {
      const c = puffer[i];
      if (c === '\n') { nimm(i, i + 1); continue; }
      if (ZH_ENDE.includes(c)) {
        let j = i + 1;
        while (j < puffer.length && ZU.includes(puffer[j])) j++;
        nimm(j, j);
        i = j - 1;
        continue;
      }
      if (ENDE.includes(c) && i + 1 < puffer.length && /\s/.test(puffer[i + 1])) {
        if (c === '.') { // "24. Dezember", "z. B." oder "Dr." beenden keinen Satz
          const wort = (/([\p{L}\p{N}]+)$/u.exec(puffer.slice(start, i)) || [''])[0];
          if (/^\d+$/.test(wort) || wort.length === 1 || ABKUERZUNG.has(wort.toLowerCase())) continue;
        }
        nimm(i + 1, i + 1);
      }
    }
    if (ende) { nimm(puffer.length, puffer.length); return { saetze, rest: '' }; }
    return { saetze, rest: puffer.slice(start) };
  }

  const CJK = /[㐀-鿿]/u;
  const zeichen = (s) => Array.from(String(s || '')).filter((c) => CJK.test(c));
  const woerter = (s) => String(s || '').toLowerCase().replace(/[^\p{L}\p{N}\s]/gu, ' ').split(/\s+/).filter(Boolean);
  // Hört das Mikrofon gerade Bikos eigene Stimme? Dann stehen fast alle gehörten Wörter in dem, was er sagt.
  function istEcho(gehoert, gesagt) {
    if (!String(gesagt || '').trim()) return false;
    if (CJK.test(gehoert)) {
      const z = zeichen(gehoert);
      return z.filter((c) => gesagt.includes(c)).length / z.length >= 0.7;
    }
    const w = woerter(gehoert);
    if (!w.length) return false;
    const da = new Set(woerter(gesagt));
    return w.filter((x) => da.has(x)).length / w.length >= 0.6;
  }
  // Fällt die Person Biko ins Wort? Erst bei richtigen Worten, nicht bei "mhm" und nicht beim eigenen Echo.
  function istUnterbrechung(teil, gesagt) {
    const genug = CJK.test(teil) ? zeichen(teil).length >= 2 : ((w) => w.length >= 2 || (w.length === 1 && w[0].length >= 4))(woerter(teil));
    return genug && !istEcho(teil, gesagt);
  }

  // Server-Sent Events: "data: {...}" und eine Leerzeile. Ein angefangenes Ereignis bleibt als Rest für später.
  function sseLesen(text) {
    const teile = String(text).split('\n\n');
    const rest = teile.pop();
    const ereignisse = [];
    for (const teil of teile) {
      const daten = teil.split('\n').filter((z) => z.startsWith('data:')).map((z) => z.slice(5).trimStart()).join('\n');
      if (!daten) continue;
      try { ereignisse.push(JSON.parse(daten)); } catch (e) { /* kaputtes Ereignis überspringen */ }
    }
    return { ereignisse, rest };
  }

  // Roher Ton (16 Bit, little endian) als Zahlen von -1 bis 1. Ein übriges Byte wartet auf das nächste Stück.
  function pcmLesen(rest, bytes) {
    let b = bytes;
    if (rest && rest.length) { b = new Uint8Array(rest.length + bytes.length); b.set(rest); b.set(bytes, rest.length); }
    const n = b.length >> 1;
    const werte = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      let v = b[2 * i] | (b[2 * i + 1] << 8);
      if (v >= 0x8000) v -= 0x10000;
      werte[i] = v / 32768;
    }
    return { werte, rest: b.length % 2 ? b.slice(b.length - 1) : null };
  }

  return { saetzeTeilen, istEcho, naechsteMeldungen, istUnterbrechung, sseLesen, pcmLesen, faelligeErinnerung, gezeigtSchluessel, wannText, weiterreden, wannWar, linkSeite, vorleseText, spracheVonText, knopfArt, istLaut, aufnahmeEnde, gummiband, bogen, dehnung, ausgang };
});
