// Biko-Chef: Niko redet mit dem KI-Geschäftsführer. Projekte, Aufgaben und Fragen entstehen im Gespräch,
// die Karten zeigen nur den Stand. Biko zeigt, was gerade passiert: tippt (denkt oder Arbeiter laufen),
// winkt (eine Frage wartet), jubelt (gerade etwas fertig), traurig (Fehler), sonst einfach da.
(function () {
  'use strict';
  const $ = (s) => document.querySelector(s);
  const el = (tag, attrs, ...kinder) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === 'text') e.textContent = v; else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v);
    }
    kinder.flat().filter(Boolean).forEach((k) => e.append(k));
    return e;
  };
  const M = window.Maskottchen;
  if (M) { document.querySelectorAll('[data-biko]').forEach((e) => M.mount(e, { decorative: true })); M.setMood('da'); }
  const stimmung = (m) => { if (M) M.setMood(m); };

  async function api(pfad, daten) {
    let r;
    try {
      r = await fetch(pfad, {
        method: daten === undefined ? 'GET' : 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: daten === undefined ? undefined : JSON.stringify(daten),
      });
    } catch (e) { throw new Error('Keine Verbindung. Ist das Internet da?'); }
    let j = {};
    try { j = await r.json(); } catch (e) { /* leer */ }
    if (!r.ok) { const f = new Error(j.fehler || 'Das hat nicht geklappt, bitte nochmal.'); f.status = r.status; throw f; }
    return j;
  }

  const dollar = (x) => (x || 0).toFixed(2).replace('.', ',') + ' $';
  const STAND = { aktiv: 'Läuft', fertig: 'Fertig', wartet: 'Wartet auf dich', pausiert: 'Pausiert' };
  const AUFGABE = { offen: 'Wartet', laeuft: 'Arbeitet gerade', fertig: 'Fertig', fehler: 'Fehler' };
  let denkt = false, zuletztFertig = 0, gesehen = null, pc = null;

  // ---------- Anzeige ----------
  function aufgabeZeile(a) {
    const knoepfe = [];
    if (a.status === 'fertig' || a.zusammenfassung) knoepfe.push(el('button', { type: 'button', class: 'klein-knopf druck', text: 'Ergebnis ansehen', onclick: () => ergebnisZeigen(a.id) }));
    if (a.pr) knoepfe.push(el('a', { class: 'klein-knopf druck', href: a.pr, target: '_blank', rel: 'noopener', text: 'PR ansehen' }));
    if (a.vorschau) knoepfe.push(el('a', { class: 'klein-knopf druck', href: `/api/chef/vorschau?id=${a.id}`, target: '_blank', rel: 'noopener', text: 'Webseite öffnen' }));
    return el('li', { class: 'aufgabe', 'data-s': a.status },
      el('span', { class: 'punkt', 'aria-hidden': 'true' }),
      el('strong', { text: a.titel }),
      el('span', { class: 'rolle', text: `${a.rolle_name}${a.repo ? ' · ' + a.repo : ''} · ${aufgabeStand(a)}${a.versuche > 1 ? ` · ${a.versuche} Versuche` : ''}${a.kosten ? ' · ' + dollar(a.kosten) : ''}` }),
      a.zusammenfassung ? el('span', { class: 'zf', text: a.zusammenfassung }) : null,
      knoepfe.length ? el('div', { class: 'knoepfe' }, knoepfe) : null);
  }

  function aufgabeStand(a) {
    if (!a.repo) return AUFGABE[a.status] || a.status;   // nur Programmierer-Aufgaben laufen auf Nikos PC
    if (a.status === 'laeuft') return 'Arbeitet auf deinem PC';
    if (a.status === 'offen' && pc && !pc.verbunden) return 'Wartet auf deinen PC';
    return AUFGABE[a.status] || a.status;
  }

  function projektKarte(p, neu) {
    const anteil = Math.min(100, Math.round((p.ausgegeben / p.budget) * 100));
    const fuellung = el('span');
    fuellung.style.width = anteil + '%';   // über CSSOM, die Seite erlaubt keine style-Attribute
    return el('article', { class: 'karte projekt' + (neu ? ' kommt' : ''), 'data-id': p.id },
      el('div', { class: 'projekt-kopf' }, el('h2', { text: p.name }), el('span', { class: 'stand', 'data-s': p.status, text: STAND[p.status] || p.status })),
      el('p', { class: 'ziel', text: p.ziel }),
      el('div', { class: 'balken', role: 'img', 'aria-label': `${anteil} Prozent vom Budget verbraucht` }, fuellung),
      el('p', { class: 'geld', text: `${dollar(p.ausgegeben)} von ${dollar(p.budget)}` }),
      el('ul', { class: 'aufgaben' }, p.aufgaben.map(aufgabeZeile)));
  }

  function frageKarte(p, f) {
    const antworten = async (ja, knopf) => {
      knopf.disabled = true;
      stimmung('tippt');
      try { zeigen(await api('/api/chef/freigabe', { projekt: p.id, frage: f.id, ja })); } catch (e) { $('#chat-fehler').textContent = e.message; stimmung('traurig'); }
    };
    let jaK, neinK;
    return el('div', { class: 'karte frage-karte kommt' },
      el('span', { class: 'leise klein', text: `Frage zu „${p.name}“` }),
      el('p', { text: f.frage }),
      el('div', { class: 'zwei' },
        neinK = el('button', { type: 'button', class: 'knopf druck', text: 'Nein', onclick: () => antworten(false, neinK) }),
        jaK = el('button', { type: 'button', class: 'knopf haupt druck', text: 'Ja, freigeben', onclick: () => antworten(true, jaK) })));
  }

  function blase(e) {
    const art = { niko: 'ich', chef: 'biko-sagt', meldung: 'meldung-blase', bericht: 'bericht-blase', frage: 'frage-blase' }[e.wer] || 'meldung-blase';
    return el('div', { class: 'blase ' + art, text: e.text });
  }

  function zeigen(z) {
    const alt = gesehen ? new Set(gesehen.projekte.map((p) => p.id)) : null;
    const ds = z.dreamstudy && z.dreamstudy.an
      ? ` · DreamStudy ${z.dreamstudy.fehler ? 'gestört' : 'verbunden'}${z.dreamstudy.heute ? `, heute ${z.dreamstudy.heute} erledigt` : ''}` : '';
    pc = z.abo && z.abo.an ? z.abo : null;
    const abo = pc ? ` · PC ${pc.verbunden ? 'verbunden' : 'nicht verbunden'}, ${pc.heute} von ${pc.max_tag} Abo-Läufen${pc.pause_bis && new Date(pc.pause_bis) > new Date() ? ', Pause bis ' + pc.pause_bis.slice(11, 16) : ''}` : '';
    $('#kosten').textContent = `Heute ${dollar(z.heute)} von ${dollar(z.grenzen.tag)} · ${z.laufen} von ${z.grenzen.gleichzeitig} Arbeitern aktiv${ds}${abo}`;
    $('#fragen').replaceChildren(...z.projekte.flatMap((p) => p.fragen.map((f) => frageKarte(p, f))));
    $('#projekte').replaceChildren(...(z.projekte.length ? z.projekte.map((p) => projektKarte(p, alt && !alt.has(p.id)))
      : [el('p', { class: 'leer-zeile', text: 'Noch keine Projekte. Sag mir unten, was erledigt werden soll, zum Beispiel: „Bau eine Landingpage für meine Nachhilfe.“' })]));
    const v = $('#verlauf');
    const unten = v.childElementCount === 0 || window.innerHeight + window.scrollY > document.body.scrollHeight - 120;
    v.replaceChildren(...z.gespraech.map(blase));
    if (denkt) v.append(el('div', { class: 'blase denkt', text: 'Ich denke nach …' }));
    if (unten && gesehen && z.gespraech.length !== gesehen.gespraech.length) v.lastElementChild?.scrollIntoView({ block: 'end', behavior: 'smooth' });

    const fertig = z.projekte.reduce((n, p) => n + p.aufgaben.filter((a) => a.status === 'fertig').length, 0);
    const fragen = z.projekte.reduce((n, p) => n + p.fragen.length, 0);
    if (gesehen && fertig > zuletztFertig) { stimmung('jubelt'); setTimeout(() => zustand(z), 2600); }
    else zustand(z);
    zuletztFertig = fertig;
    const amPc = z.projekte.some((p) => p.aufgaben.some((a) => a.repo && a.status === 'laeuft'));
    $('#zustand-text').textContent = denkt ? 'Ich denke nach' : amPc && !z.laufen ? 'Claude arbeitet auf deinem PC' : z.laufen ? `${z.laufen} ${z.laufen === 1 ? 'Arbeiter ist' : 'Arbeiter sind'} dran` : fragen ? 'Eine Frage wartet auf dich' : 'Dein KI-Geschäftsführer';
    gesehen = z;
  }

  function zustand(z) {
    const fragen = z.projekte.some((p) => p.fragen.length);
    const fehler = z.projekte.some((p) => p.aufgaben.some((a) => a.status === 'fehler'));
    const amPc = z.projekte.some((p) => p.aufgaben.some((a) => a.repo && a.status === 'laeuft'));
    stimmung(denkt || z.laufen || amPc ? 'tippt' : fragen ? 'winkt' : fehler ? 'traurig' : 'da');
  }

  async function ergebnisZeigen(id) {
    try {
      const e = await api('/api/chef/ergebnis?id=' + encodeURIComponent(id));
      $('#ergebnis-titel').textContent = `${e.titel} (${e.rolle})`;
      $('#ergebnis-urteil').textContent = e.urteil ? 'Prüfer: ' + e.urteil : '';
      $('#ergebnis-text').textContent = e.ergebnis || 'Noch kein Ergebnis.';
      $('#ergebnis').showModal();
    } catch (err) { $('#chat-fehler').textContent = err.message; }
  }

  // ---------- Laden, Anmelden, Gespräch ----------
  async function laden() {
    try {
      const z = await api('/api/chef');
      $('#login').hidden = true; $('#inhalt').hidden = false;
      zeigen(z);
    } catch (e) {
      if (e.status === 401 || e.status === 403) { $('#login').hidden = false; $('#inhalt').hidden = true; stimmung('winkt'); }
      else $('#chat-fehler').textContent = e.message;
    }
  }

  $('#login-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    $('#login-fehler').textContent = '';
    try { await api('/api/login', { passwort: $('#passwort').value }); laden(); }
    catch (e) { $('#login-fehler').textContent = e.message; stimmung('traurig'); }
  });

  const feld = $('#chat-text');
  feld.addEventListener('input', () => { feld.style.height = 'auto'; feld.style.height = feld.scrollHeight + 'px'; });
  feld.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); $('#chat-form').requestSubmit(); } });
  $('#chat-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const text = feld.value.trim();
    if (!text || denkt) return;
    $('#chat-fehler').textContent = '';
    denkt = true;
    if (gesehen) zeigen({ ...gesehen, gespraech: [...gesehen.gespraech, { wer: 'niko', text }] });
    feld.value = ''; feld.style.height = 'auto';
    $('#chat-knopf').disabled = true;
    try { const z = await api('/api/chef/chat', { text }); denkt = false; zeigen(z); }
    catch (e) { denkt = false; feld.value = text; $('#chat-fehler').textContent = e.message; stimmung('traurig'); laden(); }
    finally { $('#chat-knopf').disabled = false; }
  });

  laden();
  setInterval(() => { if (document.visibilityState === 'visible' && !denkt && !$('#inhalt').hidden && !$('#ergebnis').open) laden(); }, 5000);
})();
