// Biko Helfer: Verhalten der Oberfläche, ohne externe Abhängigkeiten.
// Texte stehen in texte.js, die reine Logik in logik.js (getestet), die Bewegungen in bewegung.js.
(function () {
  'use strict';
  const T = window.BikoTexte, L = window.BikoLogik, B = window.BikoBewegung, M = window.Maskottchen;
  const STIMME = { de: 'de-AT', zh: 'zh-CN' };

  const $ = (s, wo = document) => wo.querySelector(s);
  const $$ = (s, wo = document) => Array.from(wo.querySelectorAll(s));
  const merken = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* privates Fenster */ } };
  const holen = (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } };
  const neu = (tag, klasse, text) => {
    const el = document.createElement(tag);
    if (klasse) el.className = klasse;
    if (text !== undefined) el.textContent = text;
    return el;
  };
  const icon = (name, klasse = '') => `<svg class="icon ${klasse}" aria-hidden="true"><use href="#i-${name}"/></svg>`;

  // Sprache der Oberfläche: gemerkte Wahl, sonst die Sprache des Handys
  let sprache = holen('sprache') || ((navigator.language || '').toLowerCase().startsWith('zh') ? 'zh' : 'de');
  if (!T[sprache]) sprache = 'de';
  const t = (k) => T[sprache][k] ?? T.de[k] ?? k;

  let profil = {};
  let erinnerungen = [];
  let morgenrunde = null; // Uhrzeit der Morgenrunde ("08:00") oder null
  let geburtstage = []; // [{id, name, tag, monat, jahr}] für die Wecker der Android-App
  let checkin = null; // Uhrzeit des täglichen Check-ins ("10:00") oder null
  let wissen = [];      // was Biko über die Person weiß; merkt er sich im Gespräch selbst
  let gespraeche = [];  // Übersicht aller Gespräche, das zuletzt benutzte zuerst
  let gespraechNr = ''; // das offene Gespräch; leer heißt: mit der nächsten Frage beginnt ein neues
  let sitzung = 0;      // zählt hoch, sobald ein anderes Gespräch gezeigt wird: eine späte Antwort gehört dann nicht mehr hierher
  let angemeldet = false;
  let aktiv = 'reden'; // der gezeigte Bereich
  const spracheKnopf = $('#sprache-knopf'), spracheMenue = $('#sprache-menue');
  // Neben einem Titel ist für den ausgeschriebenen Sprachknopf kein Platz: dann zeigt er nur sein Symbol
  const kopfRichten = () => document.body.classList.toggle('kompakt',
    angemeldet && (aktiv !== 'reden' || !$('#reden-kopf').classList.contains('gross')));

  // ---------- Biko zeigt, was gerade passiert ----------
  $$('[data-biko]').forEach((el) => M.mount(el, { decorative: el.dataset.biko !== 'haupt' }));
  let ruheUhr;
  // In der Android-App läuft Biko auch ganz klein in der Blase (?mini): sie zeigt, ob er zuhört, nachdenkt oder spricht
  const nativ = window.BikoNativ || null;
  // Die Android-App stellt Wecker: so meldet sich Biko zur Erinnerung und zur Morgenrunde, auch wenn er zu ist
  const wecker = window.BikoWecker || null;
  const mini = !!nativ && new URLSearchParams(location.search).has('mini');
  function nativMelden(art) {
    if (!nativ) return;
    try {
      const z = !telefon ? 'aus' : telefon.sprecher.spricht() ? 'spricht' : art === 'tippt' ? 'denkt' : 'hoert';
      nativ.zustand(z);
    } catch (e) { /* noch beim Laden oder ältere App */ }
  }
  function stimmung(art, zurueckNach) {
    clearTimeout(ruheUhr);
    M.setMood(art);
    nativMelden(art);
    if (zurueckNach) ruheUhr = setTimeout(() => M.setMood('da'), zurueckNach);
  }
  $('#biko-reden').addEventListener('click', () => M.fidget('boop'));

  // ---------- Texte ----------
  function texteSetzen() {
    document.documentElement.lang = sprache === 'zh' ? 'zh-CN' : 'de';
    $$('[data-t]').forEach((el) => { el.textContent = t(el.dataset.t); });
    $$('[data-t-ph]').forEach((el) => { el.placeholder = t(el.dataset.tPh); });
    $$('[data-t-label]').forEach((el) => el.setAttribute('aria-label', t(el.dataset.tLabel)));
    $('#sprache-name').textContent = t('sprache_' + sprache);
    spracheKnopf.setAttribute('aria-label', `${t('sprache')}: ${t('sprache_' + sprache)}`);
    $$('#sprache-menue [data-sprache]').forEach((b) => b.setAttribute('aria-checked', String(b.dataset.sprache === sprache)));
    $('#gruss').textContent = profil.name ? t('hallo_name').replace('{name}', profil.name) : t('hallo');
    $$('.blase .vorlesen').forEach((k) => { k.lastElementChild.textContent = t(k.dataset.zustand === 'laeuft' ? 'stopp' : 'vorlesen'); });
    $$('.blase.denkt .nur-vorlesen').forEach((el) => { el.textContent = t('denkt'); });
    $$('.notiz').forEach(notizFuellen);
    $$('.entwurf').filter((el) => el._n).forEach(entwurfTexte); // Listen und Tagebuch sind auch Blätter, aber keine Nachrichten
    $$('.liste-karte').forEach(listeTexte);
    $$('.tagebuch-karte').forEach(tagebuchTexte);
    $$('.warnung-karte').forEach(warnungTexte);
    zustand($('#profil-speichern'), 'ruhe', 'speichern');
    knopfZeigen();
    vorschlaegeZeigen();
    erinnerungenZeigen();
    wissenZeigen();
    gespraecheZeigen();
  }
  // Knopf mit Zustand: Symbol und Beschriftung wechseln zusammen
  function zustand(knopf, art, textSchluessel) {
    knopf.dataset.zustand = art;
    knopf.lastElementChild.textContent = t(textSchluessel);
  }
  function bestaetigen(knopf, okText, ruheText) {
    zustand(knopf, 'ok', okText);
    B.puls(knopf);
    clearTimeout(knopf._zurueck);
    knopf._zurueck = setTimeout(() => zustand(knopf, 'ruhe', ruheText), 2600);
  }

  // ---------- Sprachmenü (geht am Knopf auf) ----------
  function menueZu(fokus) {
    if (spracheKnopf.getAttribute('aria-expanded') !== 'true') return;
    spracheKnopf.setAttribute('aria-expanded', 'false');
    B.zuklappen(spracheMenue);
    if (fokus) spracheKnopf.focus();
  }
  spracheKnopf.addEventListener('click', () => {
    if (spracheKnopf.getAttribute('aria-expanded') === 'true') return menueZu();
    spracheKnopf.setAttribute('aria-expanded', 'true');
    B.aufklappen(spracheMenue);
  });
  spracheMenue.addEventListener('click', (e) => {
    const b = e.target.closest('[data-sprache]');
    if (!b) return;
    if (b.dataset.sprache !== sprache) {
      sprache = b.dataset.sprache;
      merken('sprache', sprache);
      texteSetzen();
      if (angemeldet) { // Biko antwortet im Zweifel in dieser Sprache
        profil.sprache = STIMME[sprache];
        api('/api/profil', profil).catch(() => {});
      }
    }
    menueZu(true);
  });
  document.addEventListener('click', (e) => { if (!e.target.closest('.sprache')) menueZu(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') menueZu(true); });

  // ---------- Server ----------
  // `daten`: nichts (lesen), ein Objekt (als JSON) oder eine Tonaufnahme (Blob, geht so wie sie ist)
  const anfrage = (pfad, daten) => {
    const roh = daten instanceof Blob;
    return fetch(pfad, {
      method: daten === undefined ? 'GET' : 'POST',
      headers: { 'Content-Type': roh ? daten.type : 'application/json', 'X-Sprache': STIMME[sprache] },
      body: daten === undefined || roh ? daten : JSON.stringify(daten),
      credentials: 'same-origin',
    });
  };
  async function api(pfad, daten) {
    let r;
    try { r = await anfrage(pfad, daten); } catch (e) { throw new Error(t('keine_verbindung')); }
    let j = {};
    try { j = await r.json(); } catch (e) { /* leer */ }
    if (r.status === 401 && pfad !== '/api/login') loginZeigen();
    if (!r.ok) throw new Error(j.fehler || t('fehler'));
    return j;
  }

  // ---------- Anmelden ----------
  function loginZeigen() {
    angemeldet = false;
    $('#app').hidden = true;
    $('#login').hidden = false;
    kopfRichten();
    stimmung('winkt');
  }
  $('#login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const knopf = $('#login-form button[type=submit]');
    $('#login-fehler').textContent = '';
    knopf.disabled = true;
    try {
      const j = await api('/api/login', { passwort: $('#passwort').value });
      $('#passwort').value = '';
      if (j.rolle === 'familie') { location.replace('/familie.html'); return; }
      await starten();
    } catch (err) { $('#login-fehler').textContent = err.message; }
    knopf.disabled = false;
  });

  async function starten() {
    texteSetzen();
    let s;
    try { s = await api('/api/status'); } catch (err) {
      loginZeigen();
      stimmung('offline');
      $('#login-fehler').textContent = err.message;
      return;
    }
    // Mit einem Link aus der Einladung (/?code=...) meldet sich das Handy gleich selbst an
    const code = new URLSearchParams(location.search).get('code');
    if (code && !s.angemeldet) {
      try {
        const j = await api('/api/login', { code });
        if (j.rolle === 'familie') { location.replace('/familie.html'); return; }
        s = await api('/api/status');
      } catch (err) { loginZeigen(); $('#passwort').value = code; $('#login-fehler').textContent = err.message; return; }
    }
    if (!s.angemeldet) { loginZeigen(); return; }
    if (s.rolle === 'familie') { location.replace('/familie.html'); return; }
    $('#zur-familie').hidden = s.rolle !== 'verwalter';
    sprachdienst = !!s.sprachdienst;
    let mr;
    let ci;
    [profil, erinnerungen, gespraeche, wissen, mr, geburtstage, ci] = await Promise.all([api('/api/profil'), api('/api/erinnerungen'), api('/api/gespraeche'), api('/api/wissen'), api('/api/morgenrunde'), api('/api/geburtstage'), api('/api/checkin')]);
    morgenrunde = mr.zeit;
    checkin = ci.zeit;
    lebenszeichen();
    api('/api/dolmetscher').then((d) => dolmetscherZeigen(d.dolmetscher), () => {});
    angemeldet = true;
    $('#login').hidden = true;
    $('#app').hidden = false;
    profilInsFormular();
    texteSetzen();
    // Am selben Tag steht das letzte Gespräch wieder da. An einem neuen Tag begrüßt Biko von vorn,
    // das alte Gespräch steht dann im Verlauf.
    const letztes = gespraeche[0];
    if (letztes && L.weiterreden(letztes.zuletzt, new Date())) {
      try { gespraechZeigen(await api('/api/gespraech?id=' + encodeURIComponent(letztes.id))); } catch (err) { startbild(); }
    } else startbild();
    kopfRichten();
    kissenRichten(false);
    stimmung('winkt', 2600); // Biko grüßt kurz und ist dann einfach da
    alteMerkerLoeschen();
    clearInterval(starten.uhr);
    starten.uhr = setInterval(erinnerungPruefen, 15000);
    erinnerungPruefen();
    // Die Android-App öffnet Biko mit ?reden, wenn man auf die Blase tippt: dann geht das Gespräch gleich los
    const seite = new URLSearchParams(location.search);
    if (seite.has('reden')) {
      history.replaceState(null, '', location.pathname);
      if (kannTelefonieren()) telefonieren();
    }
    // Aus der Mitteilung "Guten Morgen!": Biko erzählt die Morgenrunde
    if (seite.has('morgenrunde')) {
      history.replaceState(null, '', location.pathname);
      morgenrundeHoeren();
    }
    // In der Blase holt Biko alle 5 Minuten die Erinnerungen neu (vielleicht kam am Handy eine dazu) und stellt die Wecker
    if (mini) {
      clearInterval(starten.auffrischen);
      starten.auffrischen = setInterval(async () => {
        try {
          const [liste, m, gb, ci] = await Promise.all([api('/api/erinnerungen'), api('/api/morgenrunde'), api('/api/geburtstage'), api('/api/checkin')]);
          erinnerungen = liste;
          morgenrunde = m.zeit;
          geburtstage = gb;
          checkin = ci.zeit;
          erinnerungenZeigen();
        } catch (e) { /* kein Netz: beim nächsten Mal */ }
      }, 5 * 60 * 1000);
    }
  }

  // ---------- Bereiche wechseln ----------
  const leiste = $('.leiste'), kissen = $('.leiste-kissen');
  const ansicht = (name) => $(`.ansicht[data-ansicht="${name}"]`);
  const kissenRichten = (animiert) => B.kissenSetzen(kissen, $(`.leiste button[data-ziel="${aktiv}"]`), animiert);
  if (window.ResizeObserver) new ResizeObserver(() => kissenRichten(false)).observe(leiste);

  // Zeilen kommen der Reihe nach (je 30 ms später), Hilfetexte setzen sich danach
  function reihenZaehlen(wo) {
    $$('.reihe', wo).forEach((el, i) => {
      el.style.setProperty('--i', Math.min(i, 8));
      $$('.detail', el).forEach((d) => d.style.setProperty('--i', Math.min(i, 8)));
    });
    $$(':scope > .detail', wo).forEach((d) => d.style.setProperty('--i', 8));
  }
  function wechseln(ziel) {
    if (ziel === aktiv) return;
    const alt = ansicht(aktiv), neuA = ansicht(ziel);
    aktiv = ziel;
    kopfRichten();
    $$('.leiste button').forEach((b) => {
      if (b.dataset.ziel === ziel) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    });
    kissenRichten(true);
    // Alte und neue Ansicht liegen kurz übereinander: die alte blendet aus, während die neue schon kommt
    clearTimeout(neuA._uhr);
    clearTimeout(alt._uhr);
    reihenZaehlen(neuA);
    neuA.classList.remove('geht');
    neuA.hidden = false;
    neuA.classList.add('kommt');
    alt.classList.remove('kommt');
    alt.classList.add('geht');
    alt._uhr = setTimeout(() => { alt.hidden = true; alt.classList.remove('geht'); }, L.ausgang(220));
    neuA._uhr = setTimeout(() => neuA.classList.remove('kommt'), 900);
    window.scrollTo(0, 0);
  }
  leiste.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-ziel]');
    if (!b) return;
    if (b.dataset.ziel === 'gespraeche') gespraecheLaden(); // die Liste ist sofort da und wird im Hintergrund aufgefrischt
    wechseln(b.dataset.ziel);
  });

  // Löschen fragt immer erst nach: ein falscher Tipp soll keine Erinnerung und kein Gespräch kosten.
  // `sicher` enthält die Frage (p) und die Knöpfe .nein und .ja, `tun` löscht wirklich.
  function sicherVerdrahten(sicher, ausloeser, frage, tun) {
    const text = $('p', sicher), ja = $('.ja', sicher), nein = $('.nein', sicher);
    const zu = () => { sicher.hidden = true; ausloeser.setAttribute('aria-expanded', 'false'); };
    ausloeser.setAttribute('aria-expanded', 'false');
    ausloeser.addEventListener('click', () => {
      sicher.hidden = !sicher.hidden;
      ausloeser.setAttribute('aria-expanded', String(!sicher.hidden));
      if (sicher.hidden) return;
      text.textContent = frage();
      B.spiele(sicher, [{ opacity: 0 }, { opacity: 1 }], { duration: 200, easing: 'ease' });
      nein.focus({ preventScroll: true });
    });
    nein.addEventListener('click', () => { zu(); ausloeser.focus(); });
    ja.addEventListener('click', async () => {
      ja.disabled = true;
      try { await tun(); zu(); } catch (err) { text.textContent = err.message; }
      ja.disabled = false;
    });
    return sicher;
  }
  // Eine Zeile in einer Liste bekommt ihren Löschen-Knopf und die Nachfrage dazu
  function loeschKnopf(name, frage, tun) {
    const weg = neu('button', 'weg druck');
    weg.type = 'button';
    weg.innerHTML = icon('loeschen');
    weg.setAttribute('aria-label', `${t('loeschen')}: ${name}`);
    const sicher = neu('div', 'sicher');
    const ja = neu('button', 'knopf druck ja', t('loeschen')), nein = neu('button', 'knopf druck nein', t('behalten'));
    ja.type = nein.type = 'button';
    sicher.append(neu('p'), nein, ja);
    sicher.hidden = true;
    return [weg, sicherVerdrahten(sicher, weg, () => t(frage), tun)];
  }
  const verschwinden = (el) => B.spiele(el, [{ opacity: 1, transform: 'scale(1)' }, { opacity: 0, transform: 'scale(0.97)' }],
    { duration: L.ausgang(220), easing: 'ease', fill: 'forwards' });

  // ---------- Vorlesen ----------
  // Mit Sprachdienst am Server (siehe README) kommt eine natürliche Stimme als Ton. Ohne ihn, oder wenn er
  // gerade ausfällt, liest die Stimme des Browsers vor.
  let sprachdienst = false; // sagt der Server in /api/status
  const browserStimme = 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;
  const kannVorlesen = () => sprachdienst || browserStimme;
  const vorlesenAn = () => holen('vorlesen') === '1';
  const spieler = new Audio(); // immer derselbe: ein iPhone erlaubt Ton nur dem Spieler, der einmal angetippt wurde
  const tonSpeicher = new Map(); // Text -> fertiger Ton: nochmal anhören kostet nichts
  let liest = null; // der Knopf der Blase, die gerade vorgelesen wird
  let lauf = 0;     // zählt jedes Vorlesen und jedes Stopp: ein Ton, der zu spät ankommt, spielt nicht mehr
  function vorlesenStopp() {
    lauf++;
    spieler.onended = spieler.onerror = null;
    spieler.pause();
    if (browserStimme) speechSynthesis.cancel();
    if (liest) zustand(liest, 'ruhe', 'vorlesen');
    liest = null;
  }
  function vorlesenFertig(knopf) {
    if (!knopf || liest !== knopf) return;
    zustand(knopf, 'ruhe', 'vorlesen');
    liest = null;
  }
  function browserLiest(text, knopf) {
    if (!browserStimme) return vorlesenFertig(knopf);
    const u = new SpeechSynthesisUtterance(text);
    u.lang = L.spracheVonText(text);
    u.rate = 0.92;
    u.onend = u.onerror = () => vorlesenFertig(knopf);
    speechSynthesis.speak(u);
  }
  async function tonHolen(text) {
    if (tonSpeicher.has(text)) return tonSpeicher.get(text);
    const r = await anfrage('/api/vorlesen', { text });
    if (!r.ok) throw new Error('kein Ton');
    const url = URL.createObjectURL(await r.blob());
    tonSpeicher.set(text, url);
    if (tonSpeicher.size > 8) { // nur die letzten Antworten bleiben im Speicher
      const [alt, altUrl] = tonSpeicher.entries().next().value;
      tonSpeicher.delete(alt);
      URL.revokeObjectURL(altUrl);
    }
    return url;
  }
  async function vorlesen(text, knopf) {
    if (!kannVorlesen()) return;
    const war = liest;
    vorlesenStopp();
    if (knopf && war === knopf) return; // nochmal antippen heißt Stopp
    if (knopf) {
      liest = knopf;
      zustand(knopf, 'laeuft', 'stopp');
    }
    if (!sprachdienst) return browserLiest(text, knopf);
    stimmeWecken();
    const hier = lauf;
    try {
      const url = await tonHolen(text);
      if (hier !== lauf) return;
      spieler.src = url;
      // `ended`: das Ende des stillen Weck-Tons von eben zählt nicht
      spieler.onended = () => { if (hier === lauf && spieler.ended) vorlesenFertig(knopf); };
      spieler.onerror = () => { if (hier === lauf) vorlesenFertig(knopf); };
      await spieler.play();
    } catch (err) {
      if (hier === lauf) browserLiest(text, knopf); // lieber die Stimme des Browsers als Stille
    }
  }
  // iPhones spielen Ton nur, wenn er einmal durch ein Antippen begonnen wurde. Deshalb beim ersten
  // Antippen (senden, sprechen, vorlesen) kurz etwas Stilles abspielen, danach darf Biko von selbst reden.
  let stimmeWach = false;
  function stimmeWecken() {
    if (stimmeWach) return;
    if (sprachdienst) {
      if (!spieler.paused) return;
      spieler.src = 'stille.mp3';
      spieler.play().then(() => { stimmeWach = true; }).catch(() => { /* beim nächsten Antippen nochmal */ });
    } else if (browserStimme && vorlesenAn()) {
      stimmeWach = true;
      speechSynthesis.speak(new SpeechSynthesisUtterance(''));
    }
  }

  // ---------- 1. Reden ----------
  const feld = $('#chat-text'), chatKnopf = $('#chat-knopf'), verlauf = $('#verlauf');
  let sendet = false;
  let hoert = null;      // Biko hört gerade zu: Aufnahme oder Spracherkennung, mit stop()
  let versteht = false;  // die Aufnahme ist beim Sprachdienst, der Satz kommt gleich
  let telefon = null;     // läuft gerade ein Gespräch wie am Telefon (siehe unten)?

  function knopfZeigen() {
    const art = L.knopfArt(feld.value, !!hoert);
    chatKnopf.dataset.art = art;
    chatKnopf.setAttribute('aria-label', t(telefon ? 'knopf_auflegen' : 'knopf_' + art));
    chatKnopf.disabled = (sendet || versteht) && art !== 'stopp';
    feld.placeholder = t(hoert ? 'eingabe_hoert' : versteht ? 'eingabe_versteht' : 'eingabe');
  }
  function feldAnpassen() {
    feld.style.height = 'auto';
    feld.style.height = feld.scrollHeight + 'px';
    knopfZeigen();
  }
  let still = false; // ein ganzes Gespräch wird auf einmal aufgebaut: nicht bei jeder Blase rollen
  const nachUnten = () => { if (!still) window.scrollTo({ top: document.documentElement.scrollHeight, behavior: B.reduziert() ? 'auto' : 'smooth' }); };
  const ganzNachUnten = () => window.scrollTo(0, document.documentElement.scrollHeight);

  // `lesetext`: was der Vorlesen-Knopf vorliest, wenn es mehr ist als der Text der Blase
  function blase(text, art, lesetext) {
    const d = neu('div', 'blase ' + art);
    d.appendChild(neu('span', '', text));
    if (art === 'biko-sagt' && kannVorlesen()) {
      const k = neu('button', 'vorlesen druck');
      k.type = 'button';
      k.dataset.zustand = 'ruhe';
      k.innerHTML = `<span class="wechsel">${icon('vorlesen', 'i-ruhe')}${icon('stopp', 'i-laeuft')}</span><span></span>`;
      k.lastElementChild.textContent = t('vorlesen');
      k.addEventListener('click', () => vorlesen(lesetext || text, k));
      d.appendChild(k);
    }
    verlauf.appendChild(d);
    nachUnten(); // ganz nach unten, damit die neue Blase über dem Eingabefeld zu sehen ist
    return d;
  }
  // Kleine Zeile unter Bikos Antwort: was er sich gerade aufgeschrieben ("Gemerkt") oder gestrichen hat,
  // und was er jetzt über die Person weiß ("Weiß ich jetzt")
  function notizFuellen(n) {
    const er = n._er, art = n.classList.contains('gestrichen') ? 'gestrichen' : n.classList.contains('gelernt') ? 'gelernt' : 'gemerkt';
    n.innerHTML = icon(art === 'gestrichen' ? 'loeschen' : art === 'gelernt' ? 'ok' : 'erinnern');
    const zeile = neu('span');
    zeile.append(neu('strong', '', t(art + '_notiz')), er.text);
    n.appendChild(zeile);
    if (art === 'gemerkt') n.appendChild(neu('span', 'wann', `${L.wannText(er, T[sprache], new Date())}, ${er.zeit}`));
  }
  function notiz(er, art) {
    const n = neu('div', 'notiz' + (art === 'gemerkt' ? '' : ' ' + art));
    n._er = er;
    notizFuellen(n);
    verlauf.appendChild(n);
    nachUnten();
  }

  // Eine Nachricht, die Biko für jemanden geschrieben hat: steht unter seiner Antwort, zum Kopieren und Einfügen
  // in WeChat, WhatsApp oder SMS. Verschicken kann Biko selbst nichts.
  async function kopiere(el) {
    try {
      await navigator.clipboard.writeText(el.textContent);
      return true;
    } catch (e) { // ohne https gibt es die Zwischenablage nur auf dem alten Weg
      const wahl = getSelection(), bereich = document.createRange();
      bereich.selectNodeContents(el);
      wahl.removeAllRanges();
      wahl.addRange(bereich);
      let ok = false;
      try { ok = document.execCommand('copy'); } catch (e2) { /* geht nicht */ }
      wahl.removeAllRanges();
      return ok;
    }
  }
  function entwurfTexte(el) {
    const n = el._n, kop = $('.kopieren', el), teil = $('.teilen', el), mit = $('.senden-mit', el);
    $('.entwurf-an span', el).textContent = n.an ? t('nachricht_an').replace('{name}', n.an) : t('nachricht_ohne');
    kop.lastElementChild.textContent = t(kop.dataset.zustand === 'ok' ? 'kopiert' : 'kopieren');
    if (teil) teil.lastElementChild.textContent = t('teilen');
    if (mit) mit.lastElementChild.textContent = t(n.ueber === 'sms' ? 'mit_sms' : 'mit_whatsapp');
    $('.meldung', el).textContent = '';
  }
  function entwurf(n) {
    const el = neu('div', 'entwurf');
    el._n = n;
    const an = neu('p', 'entwurf-an');
    an.innerHTML = icon('nachricht') + '<span></span>';
    const text = neu('p', 'entwurf-text', n.text);
    const knoepfe = neu('div', 'zwei');
    const link = L.sendeLink(n); // WhatsApp oder SMS: gleich dort öffnen, Kopieren bleibt als zweiter Weg
    if (link) {
      const mit = neu('a', 'knopf haupt druck senden-mit');
      mit.href = link;
      mit.rel = 'noopener noreferrer';
      if (link.startsWith('https:')) mit.target = '_blank';
      mit.innerHTML = icon('senden') + '<span></span>';
      knoepfe.appendChild(mit);
    }
    const kop = neu('button', link ? 'knopf druck kopieren' : 'knopf haupt druck kopieren');
    kop.type = 'button';
    kop.dataset.zustand = 'ruhe';
    kop.innerHTML = `<span class="wechsel">${icon('kopieren', 'i-ruhe')}${icon('ok', 'i-ok')}</span><span></span>`;
    const info = neu('p', 'meldung');
    info.setAttribute('role', 'status');
    kop.addEventListener('click', async () => {
      if (await kopiere(text)) {
        bestaetigen(kop, 'kopiert', 'kopieren');
        info.textContent = t('kopiert_hilfe');
        M.fidget('hop');
      } else info.textContent = t('kopieren_geht_nicht');
      info.scrollIntoView({ block: 'nearest', behavior: B.reduziert() ? 'auto' : 'smooth' });
    });
    knoepfe.appendChild(kop);
    if (navigator.share && !link) {
      const teil = neu('button', 'knopf druck teilen');
      teil.type = 'button';
      teil.innerHTML = icon('teilen') + '<span></span>';
      teil.addEventListener('click', () => { navigator.share({ text: n.text }).catch(() => {}); });
      knoepfe.appendChild(teil);
    }
    el.append(an, text, knoepfe, info);
    entwurfTexte(el);
    verlauf.appendChild(el);
    if (!still) B.aufdecken(el); // frisch geschrieben: das Blatt wird von oben nach unten aufgedeckt
    nachUnten();
  }

  // Links, die Biko gefunden hat (Quelle eines Angebots, aktueller Prospekt): große Knöpfe unter der Antwort
  function linksZeigen(liste) {
    const gut = liste.filter((l) => L.linkSeite(l.url));
    if (!gut.length) return;
    const box = neu('div', 'links');
    gut.forEach((l) => {
      const a = neu('a', 'link-knopf druck');
      a.href = l.url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.innerHTML = icon('link');
      const zeilen = neu('span');
      zeilen.append(neu('strong', '', l.titel || L.linkSeite(l.url)), neu('span', 'seite', L.linkSeite(l.url)));
      a.appendChild(zeilen);
      box.appendChild(a);
    });
    verlauf.appendChild(box);
    nachUnten();
  }

  // Eine Liste (Einkaufen, Notizen) als Karte: Gekauftes tippt man weg, Kopieren gibt sie als Text mit
  function listeTexte(el) {
    $('.meldung', el).textContent = el._offen ? t('liste_hilfe') : t('liste_fertig');
    const kop = $('.kopieren', el);
    kop.lastElementChild.textContent = t(kop.dataset.zustand === 'ok' ? 'kopiert' : 'kopieren');
  }
  function listeKarte(k) {
    const el = neu('div', 'entwurf liste-karte');
    el._offen = k.eintraege.length;
    const kopf = neu('p', 'entwurf-an');
    kopf.innerHTML = icon('liste') + '<span></span>';
    kopf.lastElementChild.textContent = k.name;
    const ul = neu('ul', 'liste-eintraege');
    k.eintraege.forEach((e) => {
      const li = neu('li');
      const b = neu('button', 'eintrag druck');
      b.type = 'button';
      b.innerHTML = `<span class="haken">${icon('ok')}</span><span></span>`;
      b.lastElementChild.textContent = e.text;
      b.setAttribute('aria-pressed', 'false');
      b.addEventListener('click', async () => {
        if (b.classList.contains('erledigt')) return;
        b.classList.add('erledigt');
        b.setAttribute('aria-pressed', 'true');
        el._offen--;
        listeTexte(el);
        if (!el._offen) M.fidget('hop');
        try { await api('/api/liste/weg', { liste: k.name, id: e.id }); } catch (err) { // nicht angekommen: wieder offen
          b.classList.remove('erledigt');
          b.setAttribute('aria-pressed', 'false');
          el._offen++;
          listeTexte(el);
        }
      });
      li.appendChild(b);
      ul.appendChild(li);
    });
    const info = neu('p', 'meldung');
    info.setAttribute('role', 'status');
    const kop = neu('button', 'knopf druck kopieren');
    kop.type = 'button';
    kop.dataset.zustand = 'ruhe';
    kop.innerHTML = `<span class="wechsel">${icon('kopieren', 'i-ruhe')}${icon('ok', 'i-ok')}</span><span></span>`;
    const text = neu('span', '', k.name + ':\n' + k.eintraege.map((e) => '- ' + e.text).join('\n'));
    kop.addEventListener('click', async () => { if (await kopiere(text)) bestaetigen(kop, 'kopiert', 'kopieren'); });
    el.append(kopf, ul, info, kop);
    listeTexte(el);
    verlauf.appendChild(el);
    if (!still) B.aufdecken(el);
    nachUnten();
  }

  // Gesundheitstagebuch als Karte: zum Vorzeigen beim Arzt oder zum Kopieren
  const tagebuchWann = (zeit) => {
    const d = new Date(zeit);
    return `${d.getDate()}.${d.getMonth() + 1}. ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  };
  function tagebuchTexte(el) {
    const arten = t('tagebuch_arten');
    $('.entwurf-an span', el).textContent = t('tagebuch_titel');
    $$('.tagebuch-zeilen li', el).forEach((li, i) => {
      const z = el._k.zeilen[i];
      $('.art', li).textContent = (arten[z.art] || z.art) + ': ';
    });
    const kop = $('.kopieren', el);
    kop.lastElementChild.textContent = t(kop.dataset.zustand === 'ok' ? 'kopiert' : 'kopieren');
  }
  function tagebuchKarte(k) {
    const el = neu('div', 'entwurf tagebuch-karte');
    el._k = k;
    const kopf = neu('p', 'entwurf-an');
    kopf.innerHTML = icon('liste') + '<span></span>';
    const ul = neu('ul', 'tagebuch-zeilen');
    k.zeilen.forEach((z) => {
      const li = neu('li');
      const was = neu('span', 'was');
      was.append(neu('span', 'art'), neu('strong', '', z.wert));
      if (z.notiz) was.append(' (' + z.notiz + ')');
      li.append(neu('span', 'wann', tagebuchWann(z.zeit)), was);
      ul.appendChild(li);
    });
    const kop = neu('button', 'knopf druck kopieren');
    kop.type = 'button';
    kop.dataset.zustand = 'ruhe';
    kop.innerHTML = `<span class="wechsel">${icon('kopieren', 'i-ruhe')}${icon('ok', 'i-ok')}</span><span></span>`;
    kop.addEventListener('click', async () => {
      const arten = t('tagebuch_arten');
      const text = neu('span', '', [t('tagebuch_titel'), ...k.zeilen.map((z) =>
        `${tagebuchWann(z.zeit)}  ${arten[z.art] || z.art}: ${z.wert}${z.notiz ? ' (' + z.notiz + ')' : ''}`)].join('\n'));
      if (await kopiere(text)) bestaetigen(kop, 'kopiert', 'kopieren');
    });
    el.append(kopf, ul, kop);
    tagebuchTexte(el);
    verlauf.appendChild(el);
    if (!still) B.aufdecken(el);
    nachUnten();
  }

  // Warnkarte bei Betrug: groß und rot (oder orange, wenn man nur nachprüfen soll), woran man es erkennt, was jetzt hilft.
  // Die Sätze schreibt Biko in der Sprache der Person, nur die Überschriften kommen von der App.
  function warnungTexte(el) {
    $('.warnung-kopf span', el).textContent = t(el.dataset.stufe === 'betrug' ? 'warnung_betrug' : 'warnung_vorsicht');
    $$('.warnung-teil', el).forEach((h) => { h.textContent = t(h.dataset.k); });
  }
  function warnungKarte(w) {
    const el = neu('div', 'entwurf warnung-karte');
    el.dataset.stufe = w.stufe === 'betrug' ? 'betrug' : 'vorsicht';
    if (!still) el.setAttribute('role', 'alert');
    const kopf = neu('p', 'warnung-kopf');
    kopf.innerHTML = icon('warnung') + '<span></span>';
    el.append(kopf, neu('p', 'warnung-titel', w.titel));
    [['warnung_anzeichen', w.anzeichen], ['warnung_tun', w.tun]].forEach(([k, punkte]) => {
      if (!punkte || !punkte.length) return;
      const h = neu('p', 'warnung-teil');
      h.dataset.k = k;
      const ul = neu(k === 'warnung_tun' ? 'ol' : 'ul', 'warnung-punkte');
      punkte.forEach((p) => ul.appendChild(neu('li', '', p)));
      el.append(h, ul);
    });
    warnungTexte(el);
    verlauf.appendChild(el);
    if (!still) B.aufdecken(el);
    nachUnten();
  }

  // Anrufen: ein großer Knopf, der das Telefon mit der Nummer öffnet. Anrufen muss die Person selbst.
  function anrufeZeigen(liste) {
    const gut = liste.filter((a) => L.telLink(a.nummer));
    if (!gut.length) return;
    const box = neu('div', 'links');
    gut.forEach((a) => {
      const k = neu('a', 'link-knopf anruf druck');
      k.href = L.telLink(a.nummer);
      k.innerHTML = icon('telefon');
      const zeilen = neu('span');
      zeilen.append(neu('strong', '', t('anrufen').replace('{name}', a.name || a.nummer)), neu('span', 'seite', a.nummer));
      k.appendChild(zeilen);
      box.appendChild(k);
    });
    verlauf.appendChild(box);
    nachUnten();
  }

  // Bikos Antwort mit allem, was er dabei getan hat: gemerkt, gestrichen, eine Nachricht geschrieben, Links gefunden
  function bikoSagt(m) {
    const d = blase(m.text, 'biko-sagt', L.vorleseText(m.text, m.nachrichten));
    (m.vergessen || []).forEach((er) => notiz(er, 'gestrichen'));
    (m.gemerkt || []).forEach((er) => notiz(er, 'gemerkt'));
    (m.gelernt || []).forEach((w) => notiz(w, 'gelernt'));
    (m.warnungen || []).forEach(warnungKarte);
    (m.nachrichten || []).forEach(entwurf);
    linksZeigen(m.links || []);
    anrufeZeigen(m.anrufe || []);
    (m.listen || []).forEach(listeKarte);
    (m.tagebuch || []).forEach(tagebuchKarte);
    return d;
  }
  function denkBlase() {
    const d = neu('div', 'blase denkt');
    d.innerHTML = '<i></i><i></i><i></i>';
    d.appendChild(neu('span', 'nur-vorlesen', t('denkt')));
    verlauf.appendChild(d);
    nachUnten();
    return d;
  }

  function vorschlaegeZeigen() {
    const box = $('#vorschlaege');
    box.replaceChildren();
    box.hidden = verlauf.children.length > 0;
    if (box.hidden) return;
    t('vorschlaege').forEach((v, i) => {
      const b = neu('button', 'vorschlag druck reihe', v);
      b.type = 'button';
      b.style.setProperty('--i', i + 1);
      b.addEventListener('click', () => senden(v, b.getBoundingClientRect()));
      box.appendChild(b);
    });
  }
  // Vom Startbild ins Gespräch: Biko wird klein und rückt nach oben, die Vorschläge blenden aus
  function gespraechBeginnen() {
    const box = $('#vorschlaege'), kopf = $('#reden-kopf');
    if (!box.hidden) { B.geist(box); box.replaceChildren(); box.hidden = true; }
    if (!kopf.classList.contains('gross')) return;
    const platz = $('#biko-reden'), vorher = platz.getBoundingClientRect();
    kopf.classList.remove('gross');
    kopfRichten();
    B.umzug(platz, vorher);
    B.spiele($('#neu-im-kopf'), [{ opacity: 0 }, { opacity: 1 }], { duration: 220, delay: 140, fill: 'backwards', easing: 'ease' });
  }
  // Leeres Startbild: mit der nächsten Frage beginnt ein neues Gespräch. Das alte bleibt im Verlauf.
  function startbild() {
    sitzung++;
    gespraechNr = '';
    vorlesenStopp();
    verlauf.replaceChildren();
    $('#reden-kopf').classList.add('gross');
    kopfRichten();
    vorschlaegeZeigen();
    gespraecheZeigen();
  }
  // Ein gespeichertes Gespräch steht wieder da, zum Nachlesen und Weiterreden
  function gespraechZeigen(g) {
    sitzung++;
    gespraechNr = g.id;
    vorlesenStopp();
    still = true;
    verlauf.replaceChildren();
    g.nachrichten.forEach((m) => (m.von === 'ich' ? blase(m.text, 'ich') : bikoSagt(m)));
    still = false;
    $('#reden-kopf').classList.toggle('gross', !g.nachrichten.length);
    kopfRichten();
    vorschlaegeZeigen();
    gespraecheZeigen();
    ganzNachUnten();
  }

  // Die Antwort kommt stückweise (Server-Sent Events): `beimText` bekommt jedes neue Stück, am Ende kommt alles,
  // was Biko dabei getan hat (gemerkt, Nachrichten, Links).
  async function chatStrom(daten, beimText) {
    let r;
    try { r = await anfrage('/api/chat', { ...daten, strom: true }); } catch (e) { throw new Error(t('keine_verbindung')); }
    if (!r.ok || !r.body) {
      let j = {};
      try { j = await r.json(); } catch (e) { /* leer */ }
      if (r.status === 401) loginZeigen();
      throw new Error(j.fehler || t('fehler'));
    }
    const leser = r.body.getReader(), dekoder = new TextDecoder();
    let rest = '';
    for (;;) {
      let teil;
      try { teil = await leser.read(); } catch (e) { throw new Error(t('keine_verbindung')); }
      if (teil.done) break;
      const s = L.sseLesen(rest + dekoder.decode(teil.value, { stream: true }));
      rest = s.rest;
      for (const e of s.ereignisse) {
        if (e.fehler) throw new Error(e.fehler);
        if (e.fertig) return e.fertig;
        if (typeof e.text === 'string') beimText(e.text);
      }
    }
    throw new Error(t('keine_verbindung')); // die Verbindung ging vor dem Ende zu
  }

  // `von`: Stelle, von der die Frage losfliegt (Vorschlag oder Eingabefeld)
  // `bild`: Adresse eines Fotos, das mit der Frage mitgeht (klein in der eigenen Blase zu sehen)
  async function senden(text, von, bild) {
    text = text.trim();
    if (!text || sendet || versteht) return;
    sendet = true;
    const start = von || feld.getBoundingClientRect();
    if (!von) feld.value = '';
    feldAnpassen();
    vorlesenStopp();
    stimmeWecken();
    gespraechBeginnen();
    stimmung('tippt');
    const meine = blase(text, 'ich');
    if (bild) {
      const img = neu('img', 'foto-klein');
      img.src = bild;
      img.alt = '';
      meine.prepend(img);
    }
    B.flug(meine, start);
    const warte = denkBlase();
    const hier = sitzung;
    const tel = telefon; // am Telefon spricht Biko schon, während die Antwort noch kommt
    if (tel) antwortBeginnt(tel);
    let live = null;     // Bikos Antwort, solange sie noch kommt: sie wächst Stück für Stück
    const stueck = (s) => {
      if (hier !== sitzung) return;
      if (!live) { warte.remove(); live = blase('', 'biko-sagt-live'); }
      live.firstChild.textContent += s;
      nachUnten();
      if (tel && telefon === tel) antwortStueck(tel, s);
    };
    try {
      const j = await chatStrom({ text, gespraech: gespraechNr, gesprochen: !!tel }, stueck);
      gespraeche = [j.gespraech, ...gespraeche.filter((g) => g.id !== j.gespraech.id)];
      if (hier === sitzung) { // sonst wurde inzwischen ein anderes Gespräch geöffnet: die Antwort steht dann im Verlauf
        warte.remove();
        if (live) live.remove();
        gespraechNr = j.gespraech.id;
        const d = bikoSagt({ ...j, text: j.antwort });
        if (live) d.classList.add('gleich-da');
        if (tel && telefon === tel) antwortFertig(tel, j);
        else {
          stimmung('da');
          if (vorlesenAn()) vorlesen(L.vorleseText(j.antwort, j.nachrichten), d.querySelector('.vorlesen'));
        }
      }
      gespraecheZeigen();
      if (j.morgenrunde !== undefined) morgenrunde = j.morgenrunde;
      if (j.geburtstage) geburtstage = j.geburtstage;
      if (j.checkin !== undefined) checkin = j.checkin;
      if (j.dolmetscher !== undefined) dolmetscherZeigen(j.dolmetscher);
      if (j.erinnerungen) erinnerungenUebernehmen(j.erinnerungen, j.gemerkt || []);
      if (j.wissen) { wissen = j.wissen; wissenZeigen(); }
    } catch (err) {
      if (hier === sitzung) {
        warte.remove();
        if (live) live.remove();
        stimmung('traurig', 5000);
        blase(err.message, 'fehler-blase');
        if (tel && telefon === tel) { antwortBeginnt(tel); tel.sprecher.sagen(err.message); }
        else if (!feld.value) feld.value = text; // nichts geht verloren
      }
    }
    sendet = false;
    feldAnpassen();
  }

  // ---------- 2. Gespräche: frühere Sitzungen ----------
  // Jede Sitzung ist am Server ein eigenes Gespräch. Hier stehen sie zum Wiederöffnen, das zuletzt benutzte oben.
  function gespraecheZeigen() {
    const ul = $('#gespraeche');
    if (!gespraeche.length) { ul.replaceChildren(neu('li', 'leer-zeile reihe', t('keine_gespraeche'))); return; }
    ul.replaceChildren(...gespraeche.map((g) => {
      const li = neu('li', 'gespraech reihe');
      const auf = neu('button', 'oeffnen druck');
      auf.type = 'button';
      auf.append(neu('span', 'titel', g.titel), neu('span', 'wann', L.wannWar(g.zuletzt, new Date(), T[sprache])));
      if (g.id === gespraechNr) auf.setAttribute('aria-current', 'true');
      auf.addEventListener('click', () => gespraechOeffnen(g.id));
      const [weg, sicher] = loeschKnopf(g.titel, 'gespraech_loeschen_frage', async () => {
        const liste = await api('/api/gespraech/loeschen', { id: g.id });
        await verschwinden(li);
        gespraeche = liste;
        if (g.id === gespraechNr) startbild(); else gespraecheZeigen();
      });
      li.append(auf, weg, sicher);
      return li;
    }));
  }
  async function gespraecheLaden() {
    try {
      gespraeche = await api('/api/gespraeche');
      gespraecheZeigen();
    } catch (err) { /* die Liste von vorhin bleibt stehen */ }
  }
  async function gespraechOeffnen(nr) {
    try {
      gespraechZeigen(await api('/api/gespraech?id=' + encodeURIComponent(nr)));
      wechseln('reden');
      ganzNachUnten();
    } catch (err) { gespraecheLaden(); } // das Gespräch gibt es nicht mehr
  }
  function neuBeginnen() {
    startbild();
    wechseln('reden');
    window.scrollTo(0, 0);
    B.spiele(ansicht('reden'), [{ opacity: 0 }, { opacity: 1 }], { duration: 220, easing: 'ease' });
  }
  $('#neues-gespraech').addEventListener('click', neuBeginnen);
  $('#neu-im-kopf').addEventListener('click', neuBeginnen);

  // Sprechen statt tippen: der Satz wird wie eine Sprachnachricht gleich abgeschickt
  const Erkennung = window.SpeechRecognition || window.webkitSpeechRecognition;
  function hinweis(text) {
    if (mini && text) { try { nativ.hinweis(text); } catch (e) { /* ältere App */ } }
    const p = $('#chat-hinweis');
    p.textContent = text;
    clearTimeout(p._uhr);
    p._uhr = setTimeout(() => { p.textContent = telefon ? t('telefon_laeuft') : ''; }, 8000);
  }
  function dauerHinweis(text) {
    const p = $('#chat-hinweis');
    clearTimeout(p._uhr);
    p.textContent = text;
  }

  // Mit Sprachdienst: das Handy nimmt auf, der Server lässt die Aufnahme verstehen. Der Dienst erkennt selbst,
  // ob Deutsch oder Chinesisch gesprochen wurde. Nach einer Pause hört Biko von selbst auf zuzuhören.
  const kannAufnehmen = () => sprachdienst && !!window.MediaRecorder && !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
  const AUFNAHME_ARTEN = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']; // iPhones nehmen als mp4 auf
  let mikroStartet = false;
  async function aufnehmen() {
    if (mikroStartet) return;
    mikroStartet = true;
    vorlesenStopp(); // sonst hört Biko sich selbst zu
    stimmeWecken();  // jetzt wird getippt: danach darf Biko die Antwort von selbst vorlesen
    const ac = tonKontext();
    let strom;
    try { strom = await navigator.mediaDevices.getUserMedia({ audio: true }); } catch (err) {
      mikroStartet = false;
      hinweis(t('mikro_verboten'));
      return;
    }
    mikroStartet = false;
    const stuecke = [];
    const aus = () => strom.getTracks().forEach((s) => s.stop());
    let rek;
    try {
      const art = AUFNAHME_ARTEN.find((a) => MediaRecorder.isTypeSupported(a));
      rek = new MediaRecorder(strom, art ? { mimeType: art } : undefined);
    } catch (err) { aus(); hinweis(t('kein_mikro')); return; }

    // Lautstärke mitlesen, um die Pause nach dem Sprechen zu erkennen
    let quelle = null, messer = null, werte = null;
    try {
      if (ac) {
        quelle = ac.createMediaStreamSource(strom);
        messer = ac.createAnalyser();
        messer.fftSize = 1024;
        werte = new Float32Array(messer.fftSize);
        quelle.connect(messer);
      }
    } catch (err) { messer = null; }
    const beginn = performance.now();
    let spitze = 0, gesprochen = false, zuletztLaut = beginn, vorbei = false;
    const beenden = () => {
      if (vorbei) return;
      vorbei = true;
      clearInterval(uhr);
      try { rek.stop(); } catch (err) { if (rek.onstop) rek.onstop(); } // die Aufnahme lief gar nicht erst an
    };
    const uhr = setInterval(() => {
      const jetzt = performance.now();
      const misst = messer && ac.state === 'running';
      if (misst) {
        messer.getFloatTimeDomainData(werte);
        const rms = Math.sqrt(werte.reduce((summe, w) => summe + w * w, 0) / werte.length);
        if (L.istLaut(rms, spitze)) { gesprochen = true; zuletztLaut = jetzt; }
        spitze = Math.max(rms, spitze * 0.995); // ein einzelnes lautes Geräusch zählt nicht ewig
      }
      // Ohne Messung hört nur die Fertig-Taste oder die Minute auf
      const ende = L.aufnahmeEnde(misst ? { dauer: jetzt - beginn, gesprochen, stille: jetzt - zuletztLaut }
        : { dauer: jetzt - beginn, gesprochen: true, stille: 0 });
      if (ende === 'fertig') beenden();
    }, 100);

    rek.ondataavailable = (e) => { if (e.data && e.data.size) stuecke.push(e.data); };
    rek.onerror = () => { stuecke.length = 0; beenden(); };
    rek.onstop = async () => {
      rek.onstop = null;
      aus();
      if (quelle) quelle.disconnect();
      hoert = null;
      let text = '', fehler = '';
      // Gleich wieder angetippt war ein Versehen: in einer Drittelsekunde sagt niemand etwas
      if (stuecke.length && performance.now() - beginn > 300) {
        versteht = true;
        stimmung('tippt');
        knopfZeigen();
        const ton = new Blob(stuecke, { type: rek.mimeType || stuecke[0].type || 'audio/webm' });
        try { text = String((await api('/api/zuhoeren', ton)).text || '').trim(); } catch (err) { fehler = err.message; }
        versteht = false;
      }
      stimmung('da');
      knopfZeigen();
      if (fehler) hinweis(fehler);
      else if (!text) hinweis(t('nichts_gehoert'));
      else senden((feld.value.trim() ? feld.value.trim() + ' ' : '') + text);
    };
    hoert = { stop: beenden };
    stimmung('hoert');
    knopfZeigen();
    try { rek.start(); } catch (err) { beenden(); }
  }

  // Ohne Sprachdienst hört der Browser selbst zu, wenn er das kann
  function zuhoeren() {
    if (!Erkennung) { hinweis(t('kein_mikro')); feld.focus(); return; }
    vorlesenStopp(); // sonst hört Biko sich selbst zu
    const r = new Erkennung();
    const vorher = feld.value ? feld.value + ' ' : '';
    r.lang = STIMME[sprache];
    r.interimResults = true;
    r.onresult = (e) => {
      feld.value = vorher + Array.from(e.results).map((x) => x[0].transcript).join('');
      feldAnpassen();
    };
    const fertig = (fehler) => {
      if (hoert !== r) return;
      hoert = null;
      stimmung('da');
      knopfZeigen();
      if (fehler && fehler !== 'no-speech' && fehler !== 'aborted') hinweis(t('kein_mikro'));
      else if (feld.value.trim()) senden(feld.value);
    };
    r.onend = () => fertig();
    r.onerror = (e) => fertig(e.error || 'fehler');
    hoert = r;
    stimmung('hoert');
    knopfZeigen();
    try { r.start(); } catch (e) { fertig('fehler'); }
  }

  // ---------- Reden wie am Telefon ----------
  // Einmal aufs Mikrofon tippen, dann hört Biko durchgehend zu (Live-Zuhören beim Sprachdienst). Ist ein Satz fertig,
  // geht er von selbst ab. Biko spricht seine Antwort Satz für Satz, schon während sie noch kommt. Wer ihm ins Wort
  // fällt, unterbricht ihn. Der rote Knopf legt auf, nach langer Stille legt Biko selbst auf.
  const Tel = window.BikoTelefon;
  let liveGeht = true; // klappt das Live-Zuhören nicht, nimmt Biko für den Rest der Sitzung wieder Satz für Satz auf
  const STILL_AUFLEGEN = 90000;
  const kannTelefonieren = () => sprachdienst && liveGeht && !!Tel && !!window.WebSocket && !!window.AudioWorkletNode
    && !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);

  async function telefonieren() {
    if (telefon || mikroStartet) return;
    mikroStartet = true;
    vorlesenStopp();
    stimmeWecken();
    const ac = tonKontext(); // jetzt, solange das Antippen gilt: sonst bleibt das iPhone stumm
    const tel = { offen: feld.value.trim(), gesagt: '', puffer: '', stumm: false, zuletzt: Date.now(), versuche: 0 };
    tel.sprecher = Tel.sprecher({
      ac,
      holen: (text, vorher, signal) => fetch('/api/stimme', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Sprache': STIMME[sprache] },
        body: JSON.stringify({ text, vorher }), credentials: 'same-origin', signal,
      }),
      beimStart: () => { tel.zuletzt = Date.now(); messungSchicken(tel); if (telefon === tel) stimmung('da'); },
      beimEnde: () => { tel.zuletzt = Date.now(); if (telefon === tel && !sendet) stimmung('hoert'); },
      beimFehler: () => { if (telefon === tel) hinweis(t('stimme_weg')); },
    });
    try { await verbinden(tel, ac); } catch (e) {
      mikroStartet = false;
      if (e && e.art === 'mikro') { hinweis(t('mikro_verboten')); return; }
      liveGeht = false; // dann eben wie bisher: aufnehmen, nach der Pause verstehen lassen
      aufnehmen();
      return;
    }
    mikroStartet = false;
    telefon = tel;
    hoert = { stop: () => auflegen() };
    wachHalten(tel);
    stimmung('hoert');
    knopfZeigen();
    dauerHinweis(t('telefon_laeuft'));
    tel.uhr = setInterval(() => {
      if (telefon === tel && !sendet && !tel.sprecher.spricht() && Date.now() - tel.zuletzt > STILL_AUFLEGEN) auflegen(t('telefon_still'));
    }, 5000);
  }
  async function verbinden(tel, ac) {
    let zugang;
    try { zugang = await api('/api/live-zugang', {}); } catch (e) { throw { art: 'live' }; }
    tel.hoerer = await Tel.hoeren({
      ac, zugang, sprache,
      beimTeil: (text) => gehoert(tel, text, false),
      beimSatz: (text) => gehoert(tel, text, true),
      beimEnde: () => verbindungWeg(tel),
    });
  }
  // Ein Zugang gilt nur eine Weile: dann still neu verbinden, ohne dass die Person etwas merkt
  async function verbindungWeg(tel) {
    if (telefon !== tel) return;
    if (tel.versuche < 2) {
      tel.versuche++;
      try {
        await verbinden(tel, tonKontext());
        if (telefon !== tel) tel.hoerer.stop(); // inzwischen aufgelegt
        return;
      } catch (e) { /* dann eben auflegen */ }
    }
    auflegen(t('telefon_weg'));
  }
  // `fertig`: der Sprachdienst meint, der Satz ist zu Ende. Sonst ist es, was gerade gesprochen wird.
  function gehoert(tel, text, fertig) {
    if (telefon !== tel) return;
    text = text.trim();
    if (!text) return;
    tel.zuletzt = Date.now();
    if (tel.sprecher.spricht() && !tel.stumm) {
      // Hört das Mikrofon nur Bikos eigene Stimme, passiert nichts. Sonst fällt die Person ihm ins Wort: er hört sofort auf.
      if (fertig ? L.istEcho(text, tel.gesagt) : !L.istUnterbrechung(text, tel.gesagt)) return;
      tel.stumm = true;
      tel.sprecher.stopp();
    }
    clearTimeout(tel.sendeUhr);
    feld.value = (tel.offen ? tel.offen + ' ' : '') + text;
    feldAnpassen();
    if (!sendet) stimmung('hoert');
    if (!fertig) return;
    tel.offen = feld.value.trim();
    tel.versuche = 0;
    tel.messung = { satzEnde: Date.now() };
    tel.sendeUhr = setTimeout(() => abschicken(tel), 500); // wer gleich weiterredet, wird nicht abgeschnitten
  }
  // Wie lange es vom Ende des eigenen Satzes bis zu Bikos Stimme gedauert hat: nur die Zahlen gehen ins Server-Protokoll
  function messungSchicken(tel) {
    const m = tel.messung;
    tel.messung = null;
    if (!m || !m.gesendet || !m.ersteWorte) return;
    const jetzt = Date.now(), satz = m.ersterSatz || jetzt;
    api('/api/messung', { gesamt: jetzt - m.satzEnde, pause: m.gesendet - m.satzEnde, ki: m.ersteWorte - m.gesendet,
      satz: satz - m.ersteWorte, stimme: jetzt - satz }).catch(() => {});
  }
  function abschicken(tel) {
    if (telefon !== tel || !tel.offen) return;
    if (sendet) { tel.sendeUhr = setTimeout(() => abschicken(tel), 300); return; } // erst die vorige Antwort
    const text = tel.offen;
    tel.offen = '';
    feld.value = text;
    if (tel.messung) tel.messung.gesendet = Date.now();
    senden(text);
  }
  function antwortBeginnt(tel) {
    tel.stumm = false;
    tel.gesagt = '';
    tel.puffer = '';
    tel.angefangen = false;
    tel.sprecher.neueAntwort();
  }
  function antwortStueck(tel, s) {
    tel.gesagt += s;
    const m = tel.messung;
    if (m && !m.ersteWorte) m.ersteWorte = Date.now();
    const teil = L.saetzeTeilen(tel.puffer + s);
    if (!tel.angefangen && !teil.saetze.length) {
      const frueh = L.fruehStueck(teil.rest);
      if (frueh) { teil.saetze.push(frueh.stueck); teil.rest = frueh.rest; }
    }
    tel.puffer = teil.rest;
    if (teil.saetze.length) {
      tel.angefangen = true;
      if (m && !m.ersterSatz) m.ersterSatz = Date.now();
    }
    if (!tel.stumm) teil.saetze.forEach((satz) => tel.sprecher.sagen(satz));
  }
  function antwortFertig(tel, j) {
    const saetze = L.saetzeTeilen(tel.puffer, true).saetze;
    tel.puffer = '';
    // Hat Biko eine Nachricht für jemanden geschrieben, liest er sie danach vor
    (j.nachrichten || []).forEach((n) => { saetze.push(...L.saetzeTeilen(n.text, true).saetze); tel.gesagt += ' ' + n.text; });
    // In der Blase gibt es keine Knöpfe: Telefon, WhatsApp oder SMS gehen auf, sobald Biko fertig gesprochen hat.
    // Sonst (z. B. für WeChat) legt die App die Nachricht gleich zum Einfügen bereit.
    const letzte = (j.nachrichten || [])[(j.nachrichten || []).length - 1];
    const oeffnen = mini && (L.telLink(((j.anrufe || [])[0] || {}).nummer) || L.sendeLink(letzte));
    if (oeffnen) nachDemSprechen(tel, () => {
      auflegen();
      try { nativ.oeffnen(oeffnen); } catch (e) { location.href = oeffnen; } // ältere App: über die Seite
    });
    else if (mini && letzte) { try { nativ.kopieren(letzte.text); } catch (e) { /* ältere App */ } }
    if (!tel.stumm) saetze.forEach((satz) => tel.sprecher.sagen(satz));
    if (!tel.sprecher.spricht()) stimmung('hoert');
  }
  // Erst wenn Biko ausgeredet hat (legt die Person vorher auf, passiert nichts)
  function nachDemSprechen(tel, tun) {
    const uhr = setInterval(() => {
      if (telefon !== tel) return clearInterval(uhr);
      if (tel.sprecher.spricht()) return;
      clearInterval(uhr);
      tun();
    }, 300);
  }
  // Während des Gesprächs geht der Bildschirm nicht aus: sonst sperrt sich das Handy nach kurzer Zeit und Biko legt auf
  async function wachHalten(tel) {
    if (!('wakeLock' in navigator)) return;
    try {
      const wach = await navigator.wakeLock.request('screen');
      if (telefon === tel) tel.wach = wach; else wach.release().catch(() => {});
    } catch (e) { /* geht nicht (z. B. Stromsparmodus): dann eben ohne */ }
  }
  function auflegen(meldung) {
    const tel = telefon;
    if (!tel) return;
    telefon = null;
    hoert = null;
    clearInterval(tel.uhr);
    clearTimeout(tel.sendeUhr);
    if (tel.hoerer) tel.hoerer.stop();
    tel.sprecher.stopp();
    if (tel.wach) tel.wach.release().catch(() => {});
    if (tel.offen) feld.value = tel.offen; // was noch nicht abgeschickt war, bleibt im Feld
    feldAnpassen();
    stimmung('da');
    dauerHinweis('');
    if (meldung) hinweis(meldung);
  }
  // Wer die App weglegt oder wechselt, legt auf: sonst hört das Handy im Hintergrund weiter zu
  // (In der Blase entscheidet die App, wann aufgelegt wird.)
  document.addEventListener('visibilitychange', () => { if (document.hidden && !mini) auflegen(); });
  if (mini) {
    window.bikoReden = () => {
      if (angemeldet && kannTelefonieren()) return telefonieren();
      nativMelden('aus');
      try { nativ.hinweis(angemeldet ? t('mikro_verboten') : 'Bitte die Biko-App einmal öffnen und anmelden.'); } catch (e) { /* ältere App */ }
    };
    window.bikoAuflegen = () => { vorlesenStopp(); auflegen(); };
    // Der Wecker der App ist losgegangen (die Blase ist zu sehen): Biko sagt es gleich selbst
    window.bikoMelden = (art, id, text) => {
      if (!angemeldet || telefon) return;
      if (art === 'morgenrunde') return morgenrundeHoeren();
      if (art === 'checkin') return checkinFragen();
      if (art === 'nachfrage' || erinnerungen.some((er) => er.id === id && er.medikament)) return medikamentFragen(art, id, text);
      merken(L.gezeigtSchluessel({ id }, new Date()), '1');
      ton();
      const k = neu('button'); // unsichtbar: zeigt nur, wann Biko fertig vorgelesen hat
      k.appendChild(neu('span'));
      vorlesen(art === 'geburtstag' ? text : `${t('erinnerung')}: ${text}`, k);
      sprichtMelden();
    };
    // Medikament aus der Blase: ist es heute schon genommen, bleibt Biko still. Sonst fragt er, und man antwortet ihm
    // einfach ("ja, hab ich"), das bestätigt er im Gespräch.
    async function medikamentFragen(art, id, text) {
      try { erinnerungen = await api('/api/erinnerungen'); } catch (e) { /* kein Netz: lieber fragen */ }
      const er = erinnerungen.find((x) => x.id === id);
      if (er && er.genommen) return;
      const jetzt = new Date();
      merken(art === 'nachfrage' ? L.nachfrageSchluessel({ id }, jetzt) : L.gezeigtSchluessel({ id }, jetzt), '1');
      ton();
      const k = neu('button');
      k.appendChild(neu('span'));
      vorlesen(t(art === 'nachfrage' ? 'nachfrage_sagen' : 'medikament_sagen').replace('{text}', (er && er.text) || text), k);
      sprichtMelden();
    }
  }

  $('#chat-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const art = chatKnopf.dataset.art;
    if (art === 'stopp') hoert.stop();
    else if (art === 'mikro') (kannTelefonieren() ? telefonieren() : kannAufnehmen() ? aufnehmen() : zuhoeren());
    else senden(feld.value);
  });
  feld.addEventListener('input', feldAnpassen);
  feld.addEventListener('keydown', (e) => {
    // Eingabetaste schickt ab. Nicht, solange die chinesische Tastatur noch Zeichen zusammensetzt.
    if (e.key !== 'Enter' || e.shiftKey || e.isComposing || e.keyCode === 229) return;
    e.preventDefault();
    if (feld.value.trim()) senden(feld.value);
  });

  // ---------- Dolmetscher: Biko übersetzt hin und her, bis man "fertig" sagt ----------
  // Ein- und ausgeschaltet wird im Gespräch. Das Band zeigt, dass er gerade übersetzt; "Fertig" sagt es für einen.
  function dolmetscherZeigen(d) {
    $('#dolmetscher-leiste').hidden = !d;
    document.body.classList.toggle('dolmetscht', !!d);
  }
  $('#dolmetscher-aus').addEventListener('click', () => { if (!sendet) senden(t('dolmetscher_aus_sagen')); });

  // ---------- Foto: einen Brief, eine Rechnung oder ein Schild erklären lassen ----------
  // Das Foto geht wie das Bildschirmfoto der Android-App an den Server (?foto) und gilt für die nächsten Fragen.
  const fotoWahl = $('#foto-wahl');
  $('#foto-knopf').addEventListener('click', () => { stimmeWecken(); fotoWahl.click(); });
  fotoWahl.addEventListener('change', async () => {
    const datei = fotoWahl.files && fotoWahl.files[0];
    fotoWahl.value = '';
    if (!datei || sendet) return;
    let bild;
    try { bild = await fotoKlein(datei); } catch (e) { hinweis(t('foto_geht_nicht')); return; }
    try { await api('/api/bildschirm?foto', bild); } catch (e) { hinweis(e.message); return; }
    senden(feld.value.trim() || t('foto_frage'), null, URL.createObjectURL(bild));
  });
  // Zum Lesen reichen 1600 Pixel: das geht schneller und kostet weniger
  async function fotoKlein(datei) {
    const url = URL.createObjectURL(datei);
    try {
      const img = new Image();
      img.src = url;
      await img.decode();
      const f = Math.min(1, 1600 / Math.max(img.naturalWidth, img.naturalHeight));
      const c = document.createElement('canvas');
      c.width = Math.round(img.naturalWidth * f);
      c.height = Math.round(img.naturalHeight * f);
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      return await new Promise((ok, nein) => c.toBlob((b) => (b ? ok(b) : nein(new Error('kein Bild'))), 'image/jpeg', 0.85));
    } finally { URL.revokeObjectURL(url); }
  }

  // ---------- 3. Erinnerungen ----------
  // Erinnerungen entstehen im Gespräch: Biko schreibt sie sich am Server selbst auf (server.py, Werkzeuge).
  // Die App bekommt mit jeder Antwort die aktuelle Liste, zeigt sie in den Einstellungen und meldet sich zur Uhrzeit.
  function hinweiseErlauben() {
    if ('Notification' in window && Notification.permission === 'default') {
      try { Notification.requestPermission(); } catch (err) { /* alte Browser */ }
    }
  }
  function erinnerungenUebernehmen(liste, gemerkt) {
    erinnerungen = liste;
    erinnerungenZeigen();
    if (gemerkt.length) { M.fidget('hop'); hinweiseErlauben(); }
    // "Jeden Tag um 8", gesagt um halb 9: Biko meldet sich erst morgen, nicht mitten in seine eigene Antwort hinein.
    // Eine einmalige Erinnerung ("in 5 Minuten") darf dagegen sofort kommen.
    const jetzt = new Date();
    gemerkt.filter((er) => !er.datum && L.faelligeErinnerung({ erinnerungen: [er], jetzt }))
      .forEach((er) => merken(L.gezeigtSchluessel(er, jetzt), '1'));
    erinnerungPruefen();
  }

  function erinnerungenZeigen() {
    weckerStellen();
    const ul = $('#erinnerungen');
    if (!erinnerungen.length) { ul.replaceChildren(neu('li', 'leer-zeile reihe', t('keine_erinnerungen'))); return; }
    ul.replaceChildren(...erinnerungen.map((er) => {
      const li = neu('li', 'erinnerung reihe');
      const mitte = neu('div');
      let wann = L.wannText(er, T[sprache], new Date());
      if (er.medikament) {
        wann += ', ' + (er.genommen ? t('genommen_um').replace('{zeit}', er.genommen.slice(11, 16)) : t('medikament_kurz'));
        if (er.melden && er.melden.length) wann += ', ' + t('medikament_melden').replace('{wer}', er.melden.map((k) => k.name).join(', '));
      }
      mitte.append(neu('div', '', er.text), neu('div', 'tage-text', wann));
      const [weg, sicher] = loeschKnopf(er.text, 'loeschen_frage', async () => {
        const liste = await api('/api/erinnerungen', { erinnerungen: erinnerungen.filter((x) => x.id !== er.id) });
        await verschwinden(li);
        erinnerungen = liste;
        erinnerungenZeigen();
      });
      li.append(neu('span', 'zeit', er.zeit), mitte, weg, sicher);
      return li;
    }));
  }

  // Was Biko über die Person weiß: entsteht im Gespräch, hier nur zum Nachsehen und Löschen
  function wissenZeigen() {
    const ul = $('#wissen');
    if (!wissen.length) { ul.replaceChildren(neu('li', 'leer-zeile reihe', t('keine_wissen'))); return; }
    ul.replaceChildren(...wissen.map((w) => {
      const li = neu('li', 'erinnerung wissen-zeile reihe');
      const [weg, sicher] = loeschKnopf(w.text, 'wissen_loeschen_frage', async () => {
        const liste = await api('/api/wissen/loeschen', { id: w.id });
        await verschwinden(li);
        wissen = liste;
        wissenZeigen();
      });
      li.append(neu('div', '', w.text), weg, sicher);
      return li;
    }));
  }

  // Welche Erinnerung wurde heute schon gezeigt? Das merkt sich das Handy.
  const speicherSchluessel = () => { try { return Object.keys(localStorage); } catch (e) { return []; } };
  const spaeterLesen = () => { try { return JSON.parse(holen('spaeter')) || {}; } catch (e) { return {}; } };
  function alteMerkerLoeschen() {
    const heute = L.gezeigtSchluessel({ id: '' }, new Date()).slice(-10);
    speicherSchluessel().filter((k) => k.startsWith('gezeigt-') && !k.endsWith(heute)).forEach((k) => { try { localStorage.removeItem(k); } catch (e) { /* egal */ } });
  }
  const alarm = $('#alarm');
  $$(':scope > *', alarm).forEach((el, i) => el.style.setProperty('--i', i));
  let offen = null;

  function erinnerungPruefen() {
    if (offen || !angemeldet || mini) return; // in der Blase meldet sich Biko über die Wecker der App
    morgenrundePruefen();
    const er = L.faelligeErinnerung({
      erinnerungen, jetzt: new Date(),
      gezeigt: new Set(speicherSchluessel().filter((k) => k.startsWith('gezeigt-'))),
      spaeter: spaeterLesen(),
    });
    if (er) return alarmZeigen(er);
    const nf = L.faelligeNachfrage({ erinnerungen, jetzt: new Date(), gezeigt: new Set(speicherSchluessel()) });
    if (nf) alarmZeigen(nf, true);
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden) erinnerungPruefen(); });

  // Die Wecker der Android-App für die nächsten zwei Tage. Sie werden jedes Mal ganz neu gestellt.
  function weckerStellen() {
    if (!wecker) return;
    const liste = L.naechsteMeldungen({ erinnerungen, morgenrunde, geburtstage, checkin, jetzt: new Date() }).map((m) => (m.art === 'morgenrunde'
      ? { ...m, titel: t('morgen_titel'), text: t('morgen_text') }
      : m.art === 'geburtstag' ? { ...m, titel: 'Biko', text: geburtstagText(m) }
        : m.art === 'checkin' ? { ...m, titel: 'Biko', text: t('checkin_frage') }
          : m.art === 'nachfrage' ? { ...m, titel: 'Biko: ' + t('nachfrage_titel'), text: t('nachfrage_text').replace('{text}', m.text) }
            : { ...m, titel: 'Biko: ' + t(m.medikament ? 'medikament' : 'erinnerung') }));
    try { wecker.planen(JSON.stringify(liste)); } catch (e) { /* ältere App */ }
  }

  // ---------- Täglicher Check-in: Biko fragt, ob alles gut ist ----------
  // Jedes Gespräch und jedes Öffnen der App ist ein Lebenszeichen. Kommt bis zur Frist keins, schickt der Server der
  // Familie eine SMS. Die unsichtbare Seite in der Blase zählt nicht: dort ist ja niemand.
  function lebenszeichen() {
    if (mini || document.hidden || Date.now() - (lebenszeichen.zuletzt || 0) < 5 * 60 * 1000) return;
    lebenszeichen.zuletzt = Date.now();
    api('/api/lebenszeichen', {}).catch(() => { lebenszeichen.zuletzt = 0; });
  }
  document.addEventListener('visibilitychange', () => { if (angemeldet) lebenszeichen(); });
  // Der Wecker in der Blase: hat sie sich heute schon gemeldet, bleibt Biko still
  async function checkinFragen() {
    try { if ((await api('/api/checkin')).gemeldet) return; } catch (e) { /* kein Netz: lieber fragen */ }
    ton();
    const k = neu('button'); // unsichtbar: zeigt nur, wann Biko fertig vorgelesen hat
    k.appendChild(neu('span'));
    vorlesen(t('checkin_sagen'), k);
    sprichtMelden();
  }

  // "ich" ist der eigene Geburtstag: dann gratuliert Biko selbst
  function geburtstagText({ name, alter }) {
    if (name.toLowerCase() === 'ich') return t('geburtstag_selbst');
    return t(alter ? 'geburtstag_alter' : 'geburtstag_heute').replace('{name}', name).replace('{alter}', alter);
  }

  // ---------- Die Morgenrunde: Biko meldet sich von selbst ----------
  // Er schreibt sie am Server kurz vor der eingestellten Zeit (Wetter, Nachrichten, Termine) als eigenes Gespräch.
  // Zur Zeit liest er sie vor: offen in der App, aus der Blase oder nach einem Tipp auf die Mitteilung.
  const morgenSchluessel = () => L.gezeigtSchluessel({ id: 'morgenrunde' }, new Date());
  function morgenrundePruefen() {
    if (!morgenrunde || document.hidden || holen(morgenSchluessel())) return;
    const [h, m] = morgenrunde.split(':').map(Number), jetzt = new Date();
    const seit = jetzt.getHours() * 60 + jetzt.getMinutes() - (h * 60 + m);
    if (seit >= 0 && seit <= 120) morgenrundeHoeren();
  }
  async function morgenrundeHoeren() {
    if (morgenrundeHoeren.laeuft) return;
    morgenrundeHoeren.laeuft = true;
    try {
      const { heute } = await api('/api/morgenrunde?jetzt');
      if (!heute) return;
      merken(morgenSchluessel(), '1');
      gespraechZeigen(await api('/api/gespraech?id=' + encodeURIComponent(heute.gespraech)));
      gespraecheLaden();
      stimmung('winkt', 2600);
      const d = $$('.biko-sagt', verlauf).pop();
      vorlesen(heute.text, d && d.querySelector('.vorlesen'));
      sprichtMelden();
    } catch (e) { /* kein Netz: die Morgenrunde steht später im Verlauf */ }
    finally { morgenrundeHoeren.laeuft = false; }
  }
  // In der Blase: sie zeigt "spricht", bis Biko fertig vorgelesen hat
  function sprichtMelden() {
    if (!mini) return;
    try { nativ.zustand(liest ? 'spricht' : 'aus'); } catch (e) { /* ältere App */ }
    clearInterval(sprichtMelden.uhr);
    sprichtMelden.uhr = setInterval(() => {
      if (liest && !telefon) return;
      clearInterval(sprichtMelden.uhr);
      if (!telefon) nativMelden('da');
    }, 400);
  }

  // Ein Tonwerk für alles: den Erinnerungston und das Mitlesen der Lautstärke beim Sprechen
  function tonKontext() {
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      const ac = tonKontext.ac || (tonKontext.ac = new AC());
      if (ac.state === 'suspended') ac.resume();
      return ac;
    } catch (e) { return null; }
  }
  function ton() {
    try {
      const ac = tonKontext();
      [523, 659, 784].forEach((hz, i) => { // drei freundliche Töne
        const o = ac.createOscillator(), g = ac.createGain(), ab = ac.currentTime + i * 0.28;
        o.frequency.value = hz;
        g.gain.setValueAtTime(0.0001, ab);
        g.gain.exponentialRampToValueAtTime(0.3, ab + 0.03);
        g.gain.exponentialRampToValueAtTime(0.0001, ab + 0.5);
        o.connect(g).connect(ac.destination);
        o.start(ab);
        o.stop(ab + 0.55);
      });
    } catch (e) { /* kein Ton möglich, die Anzeige reicht */ }
  }

  // Medikament: statt "Erledigt" steht "Genommen" da, und Biko fragt, ob es genommen ist. `nachfrage`: das zweite Mal.
  function alarmZeigen(er, nachfrage = false) {
    offen = { ...er, nachfrage };
    alarm.getAnimations().forEach((a) => a.cancel());
    $('#alarm-text').textContent = er.text;
    const titel = $('#alarm-titel'), ok = $('#alarm-ok span');
    titel.dataset.t = nachfrage ? 'nachfrage_titel' : er.medikament ? 'medikament' : 'erinnerung';
    ok.dataset.t = er.medikament ? 'genommen' : 'erledigt';
    titel.textContent = t(titel.dataset.t);
    ok.textContent = t(ok.dataset.t);
    $('#alarm-ok').disabled = $('#alarm-spaeter').disabled = false;
    alarm.hidden = false;
    $('#alarm-ok').focus({ preventScroll: true });
    stimmung('winkt');
    ton();
    vorlesen(er.medikament ? t(nachfrage ? 'nachfrage_sagen' : 'medikament_sagen').replace('{text}', er.text) : `${t('erinnerung')}: ${er.text}`);
    if (navigator.vibrate) navigator.vibrate([300, 150, 300, 150, 300]);
    if ('Notification' in window && Notification.permission === 'granted' && document.hidden) {
      try { new Notification('Biko: ' + t('erinnerung'), { body: er.text, icon: 'icon.svg' }); } catch (e) { /* manche Handys nur per Service Worker */ }
    }
  }
  async function alarmZu(spaeter) {
    if (!offen) return;
    const er = offen, merker = spaeterLesen();
    if (er.id !== 'test') merken(er.nachfrage ? L.nachfrageSchluessel(er, new Date()) : L.gezeigtSchluessel(er, new Date()), '1');
    if (!spaeter && er.medikament && er.id !== 'test') { // "Genommen": der Server schreibt es ins Tagebuch und entwarnt
      api('/api/medikament/genommen', { id: er.id })
        .then((liste) => { erinnerungen = liste; erinnerungenZeigen(); })
        .catch((e) => hinweis(e.message));
    }
    if (spaeter) merker[er.id] = Date.now() + 10 * 60 * 1000; else delete merker[er.id];
    merken('spaeter', JSON.stringify(merker));
    $('#alarm-ok').disabled = $('#alarm-spaeter').disabled = true;
    vorlesenStopp();
    if (!spaeter) { // geschafft: Biko freut sich kurz mit
      stimmung('jubelt');
      B.puls($('#alarm-ok'));
      await new Promise((r) => setTimeout(r, 1100));
    }
    await B.ausblenden(alarm);
    stimmung('da');
    offen = null;
  }
  $('#alarm-ok').addEventListener('click', () => alarmZu(false));
  $('#alarm-spaeter').addEventListener('click', () => alarmZu(true));
  // Beim Testen auch gleich die Erlaubnis für Hinweise holen: hier hat die Person gerade selbst getippt
  $('#ton-test').addEventListener('click', () => { hinweiseErlauben(); alarmZeigen({ id: 'test', text: t('test_text') }); });

  // ---------- Einstellungen ----------
  function profilInsFormular() {
    $('#profil-name').value = profil.name || '';
    $('#profil-anrede').value = profil.anrede === 'Sie' ? 'Sie' : 'du';
  }
  $('#profil-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const knopf = $('#profil-speichern');
    $('#profil-info').textContent = '';
    knopf.disabled = true;
    try {
      profil = await api('/api/profil', {
        name: $('#profil-name').value, anrede: $('#profil-anrede').value, sprache: STIMME[sprache],
      });
      $('#gruss').textContent = profil.name ? t('hallo_name').replace('{name}', profil.name) : t('hallo');
      bestaetigen(knopf, 'gespeichert', 'speichern');
      M.fidget('hop');
    } catch (err) { $('#profil-info').textContent = err.message; }
    knopf.disabled = false;
  });

  // Schalter "immer vorlesen"
  const schalter = $('#vorlesen');
  schalter.setAttribute('aria-checked', String(vorlesenAn()));
  function vorlesenSetzen(an) {
    merken('vorlesen', an ? '1' : '0');
    schalter.setAttribute('aria-checked', String(an));
    if (an) stimmeWecken(); else vorlesenStopp();
  }
  schalter.addEventListener('click', () => {
    if (schalter._gezogen) return; // gerade gezogen: das Loslassen hat schon entschieden
    const an = !vorlesenAn();
    vorlesenSetzen(an);
    B.knaufSchieben($('.knauf', schalter), an);
  });
  B.schalterZiehen(schalter, vorlesenSetzen); // der Schalter lässt sich auch mit dem Finger schieben

  // Schriftgröße: die gelbe Ebene wird auf die gewählte Stelle zugeschnitten
  const AUSSCHNITT = ['inset(0 66.667% 0 0 round 999px)', 'inset(0 33.333% 0 33.333% round 999px)', 'inset(0 0 0 66.667% round 999px)'];
  function schriftSetzen(wert) {
    const knoepfe = $$('#schrift button');
    const i = Math.max(0, knoepfe.findIndex((b) => b.dataset.wert === String(wert)));
    knoepfe.forEach((b, n) => b.setAttribute('aria-pressed', String(n === i)));
    $('#schrift .oben').style.clipPath = AUSSCHNITT[i];
    document.documentElement.style.setProperty('--schrift', knoepfe[i].dataset.wert);
    merken('schrift', knoepfe[i].dataset.wert);
  }
  $('#schrift').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-wert]');
    if (b) schriftSetzen(b.dataset.wert);
  });
  schriftSetzen(holen('schrift') || '1');

  // "Alle Gespräche vergessen" löscht den ganzen Verlauf am Server, deshalb auch hier erst die Nachfrage
  sicherVerdrahten($('#alle-sicher'), $('#verlauf-loeschen'), () => t('alle_loeschen_frage'), async () => {
    await api('/api/verlauf/loeschen', {});
    gespraeche = [];
    startbild();
    const info = $('#vergessen-info');
    info.textContent = t('vergessen_ok');
    clearTimeout(info._uhr);
    info._uhr = setTimeout(() => { info.textContent = ''; }, 6000);
  });

  starten().catch(() => { loginZeigen(); $('#login-fehler').textContent = t('fehler'); });
})();
