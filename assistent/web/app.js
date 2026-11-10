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
  function stimmung(art, zurueckNach) {
    clearTimeout(ruheUhr);
    M.setMood(art);
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
    $$('.entwurf').forEach(entwurfTexte);
    zustand($('#profil-speichern'), 'ruhe', 'speichern');
    knopfZeigen();
    vorschlaegeZeigen();
    erinnerungenZeigen();
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
      await api('/api/login', { passwort: $('#passwort').value });
      $('#passwort').value = '';
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
    if (!s.angemeldet) { loginZeigen(); return; }
    sprachdienst = !!s.sprachdienst;
    [profil, erinnerungen, gespraeche] = await Promise.all([api('/api/profil'), api('/api/erinnerungen'), api('/api/gespraeche')]);
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

  function knopfZeigen() {
    const art = L.knopfArt(feld.value, !!hoert);
    chatKnopf.dataset.art = art;
    chatKnopf.setAttribute('aria-label', t('knopf_' + art));
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
  // Kleine Zeile unter Bikos Antwort: was er sich gerade aufgeschrieben ("Gemerkt") oder gestrichen hat
  function notizFuellen(n) {
    const er = n._er, gemerkt = !n.classList.contains('gestrichen');
    n.innerHTML = icon(gemerkt ? 'erinnern' : 'loeschen');
    const zeile = neu('span');
    zeile.append(neu('strong', '', t(gemerkt ? 'gemerkt_notiz' : 'gestrichen_notiz')), er.text);
    n.appendChild(zeile);
    if (gemerkt) n.appendChild(neu('span', 'wann', `${L.wannText(er, T[sprache], new Date())}, ${er.zeit}`));
  }
  function notiz(er, gemerkt) {
    const n = neu('div', 'notiz' + (gemerkt ? '' : ' gestrichen'));
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
    const n = el._n, kop = $('.kopieren', el), teil = $('.teilen', el);
    $('.entwurf-an span', el).textContent = n.an ? t('nachricht_an').replace('{name}', n.an) : t('nachricht_ohne');
    kop.lastElementChild.textContent = t(kop.dataset.zustand === 'ok' ? 'kopiert' : 'kopieren');
    if (teil) teil.lastElementChild.textContent = t('teilen');
    $('.meldung', el).textContent = '';
  }
  function entwurf(n) {
    const el = neu('div', 'entwurf');
    el._n = n;
    const an = neu('p', 'entwurf-an');
    an.innerHTML = icon('nachricht') + '<span></span>';
    const text = neu('p', 'entwurf-text', n.text);
    const knoepfe = neu('div', 'zwei');
    const kop = neu('button', 'knopf haupt druck kopieren');
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
    if (navigator.share) {
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

  // Bikos Antwort mit allem, was er dabei getan hat: gemerkt, gestrichen, eine Nachricht geschrieben, Links gefunden
  function bikoSagt(m) {
    const d = blase(m.text, 'biko-sagt', L.vorleseText(m.text, m.nachrichten));
    (m.vergessen || []).forEach((er) => notiz(er, false));
    (m.gemerkt || []).forEach((er) => notiz(er, true));
    (m.nachrichten || []).forEach(entwurf);
    linksZeigen(m.links || []);
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

  // `von`: Stelle, von der die Frage losfliegt (Vorschlag oder Eingabefeld)
  async function senden(text, von) {
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
    B.flug(blase(text, 'ich'), start);
    const warte = denkBlase();
    const hier = sitzung;
    try {
      const j = await api('/api/chat', { text, gespraech: gespraechNr });
      gespraeche = [j.gespraech, ...gespraeche.filter((g) => g.id !== j.gespraech.id)];
      if (hier === sitzung) { // sonst wurde inzwischen ein anderes Gespräch geöffnet: die Antwort steht dann im Verlauf
        warte.remove();
        stimmung('da');
        gespraechNr = j.gespraech.id;
        const d = bikoSagt({ ...j, text: j.antwort });
        if (vorlesenAn()) vorlesen(L.vorleseText(j.antwort, j.nachrichten), d.querySelector('.vorlesen'));
      }
      gespraecheZeigen();
      if (j.erinnerungen) erinnerungenUebernehmen(j.erinnerungen, j.gemerkt || []);
    } catch (err) {
      if (hier === sitzung) {
        warte.remove();
        stimmung('traurig', 5000);
        blase(err.message, 'fehler-blase');
        if (!feld.value) feld.value = text; // nichts geht verloren
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
    const p = $('#chat-hinweis');
    p.textContent = text;
    clearTimeout(p._uhr);
    p._uhr = setTimeout(() => { p.textContent = ''; }, 8000);
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

  $('#chat-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const art = chatKnopf.dataset.art;
    if (art === 'stopp') hoert.stop();
    else if (art === 'mikro') (kannAufnehmen() ? aufnehmen() : zuhoeren());
    else senden(feld.value);
  });
  feld.addEventListener('input', feldAnpassen);
  feld.addEventListener('keydown', (e) => {
    // Eingabetaste schickt ab. Nicht, solange die chinesische Tastatur noch Zeichen zusammensetzt.
    if (e.key !== 'Enter' || e.shiftKey || e.isComposing || e.keyCode === 229) return;
    e.preventDefault();
    if (feld.value.trim()) senden(feld.value);
  });

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
    const ul = $('#erinnerungen');
    if (!erinnerungen.length) { ul.replaceChildren(neu('li', 'leer-zeile reihe', t('keine_erinnerungen'))); return; }
    ul.replaceChildren(...erinnerungen.map((er) => {
      const li = neu('li', 'erinnerung reihe');
      const mitte = neu('div');
      mitte.append(neu('div', '', er.text), neu('div', 'tage-text', L.wannText(er, T[sprache], new Date())));
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
    if (offen || !angemeldet) return;
    const er = L.faelligeErinnerung({
      erinnerungen, jetzt: new Date(),
      gezeigt: new Set(speicherSchluessel().filter((k) => k.startsWith('gezeigt-'))),
      spaeter: spaeterLesen(),
    });
    if (er) alarmZeigen(er);
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden) erinnerungPruefen(); });

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

  function alarmZeigen(er) {
    offen = er;
    alarm.getAnimations().forEach((a) => a.cancel());
    $('#alarm-text').textContent = er.text;
    $('#alarm-ok').disabled = $('#alarm-spaeter').disabled = false;
    alarm.hidden = false;
    $('#alarm-ok').focus({ preventScroll: true });
    stimmung('winkt');
    ton();
    vorlesen(`${t('erinnerung')}: ${er.text}`);
    if (navigator.vibrate) navigator.vibrate([300, 150, 300, 150, 300]);
    if ('Notification' in window && Notification.permission === 'granted' && document.hidden) {
      try { new Notification('Biko: ' + t('erinnerung'), { body: er.text, icon: 'icon.svg' }); } catch (e) { /* manche Handys nur per Service Worker */ }
    }
  }
  async function alarmZu(spaeter) {
    if (!offen) return;
    const er = offen, merker = spaeterLesen();
    if (er.id !== 'test') merken(L.gezeigtSchluessel(er, new Date()), '1');
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
    $('#profil-diaet').value = profil.diaet || '';
    $('#profil-notizen').value = profil.notizen || '';
  }
  $('#profil-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const knopf = $('#profil-speichern');
    $('#profil-info').textContent = '';
    knopf.disabled = true;
    try {
      profil = await api('/api/profil', {
        name: $('#profil-name').value, anrede: $('#profil-anrede').value, sprache: STIMME[sprache],
        diaet: $('#profil-diaet').value, notizen: $('#profil-notizen').value,
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
  const AUSSCHNITT = ['inset(0 66.667% 0 0 round 12px)', 'inset(0 33.333% 0 33.333% round 12px)', 'inset(0 0 0 66.667% round 12px)'];
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
