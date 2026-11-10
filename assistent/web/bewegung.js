// Bewegungen der Oberfläche. Regeln: Eingänge bremsen ab, Wege auf dem Bildschirm laufen ease-in-out,
// Ausgänge sind 20 % kürzer, nichts federt, und solange ein Finger etwas hält, wird nichts nachgezogen.
// Bei "Bewegung reduzieren" bleibt von allem nur das Ein- und Ausblenden.
(function () {
  'use strict';
  const L = window.BikoLogik;
  const AB = 'cubic-bezier(0.23, 1, 0.32, 1)';     // bremst ab: für alles, was erscheint
  const WEG = 'cubic-bezier(0.77, 0, 0.175, 1)';   // für Dinge, die über den Bildschirm wandern
  const mq = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : { matches: false };
  const reduziert = () => mq.matches;

  // Spielt eine Bewegung ab und liefert sie zurück, sobald sie fertig ist (oder null).
  async function spiele(el, bilder, optionen) {
    if (!el || !el.animate) return null;
    let o = { ...optionen };
    if (reduziert()) {
      bilder = bilder.filter((b) => b.opacity !== undefined).map((b) => ({ opacity: b.opacity }));
      if (bilder.length < 2) return null;
      o = { ...o, duration: Math.min(o.duration, 160), easing: 'ease' };
    }
    const a = el.animate(bilder, o);
    try { await a.finished; } catch (e) { return null; } // abgebrochen, weil schon das Nächste läuft
    return a;
  }
  const stoppe = (el) => el.getAnimations().forEach((a) => a.cancel());

  // Aufklappen am Auslöser: beginnt bei 95 % Größe, Ursprung steht im CSS beim Knopf
  function aufklappen(el) {
    stoppe(el);
    el._lauf = (el._lauf || 0) + 1;
    el.hidden = false;
    return spiele(el, [{ opacity: 0, transform: 'scale(0.95)' }, { opacity: 1, transform: 'scale(1)' }], { duration: 200, easing: AB });
  }
  async function zuklappen(el) {
    if (el.hidden) return;
    const lauf = el._lauf = (el._lauf || 0) + 1;
    const a = await spiele(el, [{ opacity: 1, transform: 'scale(1)' }, { opacity: 0, transform: 'scale(0.95)' }],
      { duration: L.ausgang(200), easing: 'ease', fill: 'forwards' });
    if (el._lauf !== lauf) return; // inzwischen wieder geöffnet
    el.hidden = true;
    if (a) a.cancel();
  }

  // Ausblenden und danach verstecken (z. B. die große Erinnerung)
  async function ausblenden(el, dauer = 220) {
    const a = await spiele(el, [{ opacity: 1 }, { opacity: 0 }], { duration: L.ausgang(dauer), easing: 'ease', fill: 'forwards' });
    el.hidden = true;
    if (a) a.cancel();
  }

  // Das Kissen in der Leiste: ein einziges Element, das zum gewählten Knopf wandert und sich unterwegs dehnt
  function kissenSetzen(kissen, ziel, animiert) {
    const leiste = kissen.parentElement.getBoundingClientRect();
    const r = ziel.getBoundingClientRect();
    if (!r.width) return;
    const x = r.left - leiste.left - kissen.parentElement.clientLeft;
    const von = kissen.classList.contains('bereit') ? new DOMMatrix(getComputedStyle(kissen).transform).m41 : x;
    stoppe(kissen);
    kissen.style.width = r.width + 'px';
    kissen.style.transform = `translateX(${x}px)`;
    kissen.classList.add('bereit');
    if (animiert && Math.abs(von - x) > 1 && !reduziert()) kissen.animate(L.dehnung(von, x), { duration: 280, easing: WEG });
  }

  // Der Knauf im Schalter wandert und dehnt sich dabei
  function knaufSchieben(knauf, an) {
    if (reduziert()) return;
    knauf.animate(L.dehnung(an ? 0 : 20, an ? 20 : 0), { duration: 220, easing: WEG });
  }

  // Den Schalter ziehen. Solange der Finger hält, folgt der Knauf direkt (kein Übergang); über die Enden
  // hinaus gibt er wie ein Gummiband nach. Beim Loslassen entscheidet die Lage, `fertig(an)` meldet sie.
  const KNAUF_WEG = 20, KNAUF_GUMMI = 8;
  function schalterZiehen(schalter, fertig) {
    const knauf = schalter.querySelector('.knauf');
    let zug = null;
    schalter.addEventListener('pointerdown', (e) => {
      if (zug || e.button > 0) return; // ein zweiter Finger zählt nicht
      zug = { id: e.pointerId, x: e.clientX, von: schalter.getAttribute('aria-checked') === 'true' ? KNAUF_WEG : 0, lage: null };
      try { schalter.setPointerCapture(e.pointerId); } catch (err) { /* Zeiger schon weg */ }
    });
    schalter.addEventListener('pointermove', (e) => {
      if (!zug || e.pointerId !== zug.id) return;
      const weg = e.clientX - zug.x;
      if (zug.lage === null && Math.abs(weg) < 4) return; // noch ein Tippen, kein Ziehen
      if (zug.lage === null) stoppe(knauf);
      const x = zug.von + weg;
      zug.lage = x < 0 ? -L.gummiband(-x, KNAUF_GUMMI) : x > KNAUF_WEG ? KNAUF_WEG + L.gummiband(x - KNAUF_WEG, KNAUF_GUMMI) : x;
      knauf.style.transform = `translateX(${zug.lage}px)`;
    });
    const ende = (e) => {
      if (!zug || e.pointerId !== zug.id) return;
      const { lage, von } = zug;
      zug = null;
      if (lage === null) return; // nur getippt: das erledigt der Klick
      // Abgebrochen (zum Beispiel weil die Seite rollt): zurück in die alte Stellung
      const an = e.type === 'pointercancel' ? von > 0 : lage > KNAUF_WEG / 2;
      const ziel = an ? KNAUF_WEG : 0;
      schalter._gezogen = true; // der Klick, der auf das Loslassen folgt, schaltet nicht noch einmal um
      setTimeout(() => { schalter._gezogen = false; }, 400);
      knauf.style.transform = '';
      fertig(an);
      if (lage !== ziel && !reduziert()) knauf.animate([{ transform: `translateX(${lage}px)` }, { transform: `translateX(${ziel}px)` }], { duration: 180, easing: AB });
    };
    schalter.addEventListener('pointerup', ende);
    schalter.addEventListener('pointercancel', ende);
  }

  // Ein Ring pulsiert einmal: "hat geklappt"
  function puls(el) {
    el.classList.remove('puls');
    void el.offsetWidth;
    el.classList.add('puls');
    clearTimeout(el._puls);
    el._puls = setTimeout(() => el.classList.remove('puls'), 700);
  }

  // Flug auf einem Bogen: `el` steht schon am Ziel und kommt von der Stelle `von` (Rechteck) dorthin
  function flug(el, von) {
    const r = el.getBoundingClientRect();
    const bilder = L.bogen(von.left - r.left, von.top - r.top, 8).map((p) => ({ transform: `translate(${p.x}px, ${p.y}px)` }));
    bilder[0].opacity = 0.5;
    bilder[bilder.length - 1].opacity = 1;
    return spiele(el, bilder, { duration: 380, easing: WEG });
  }

  // Dasselbe Element an neuer Stelle und in neuer Größe: gleitet von der alten Lage (`vorher`) in die neue
  function umzug(el, vorher) {
    const r = el.getBoundingClientRect();
    if (!r.width || !vorher.width) return null;
    const von = `translate(${vorher.left - r.left}px, ${vorher.top - r.top}px) scale(${vorher.width / r.width})`;
    return spiele(el, [{ transformOrigin: '0 0', transform: von }, { transformOrigin: '0 0', transform: 'none' }], { duration: 360, easing: WEG });
  }

  // Altes bleibt kurz als Kopie stehen und blendet aus, während das Neue schon kommt
  function geist(el) {
    const r = el.getBoundingClientRect();
    if (!r.height || reduziert()) return;
    const k = el.cloneNode(true);
    [k, ...k.querySelectorAll('*')].forEach((n) => {
      n.removeAttribute('id');
      if (n.className && typeof n.className === 'string') n.className = n.className.split(/\s+/).map((c) => c + '-geist').join(' ');
    });
    k.classList.add('geist');
    k.setAttribute('aria-hidden', 'true');
    k.inert = true;
    k.style.left = r.left + window.scrollX + 'px';
    k.style.top = r.top + window.scrollY + 'px';
    k.style.width = r.width + 'px';
    document.body.appendChild(k);
    spiele(k, [{ opacity: 1 }, { opacity: 0 }], { duration: L.ausgang(220), easing: 'ease', fill: 'forwards' }).then(() => k.remove());
  }

  // Aufdecken mit einer Maske von oben nach unten
  function aufdecken(el) {
    return spiele(el, [{ clipPath: 'inset(-24px -24px 100% -24px)', opacity: 0.4 }, { clipPath: 'inset(-24px)', opacity: 1 }], { duration: 320, easing: AB });
  }


  window.BikoBewegung = {
    reduziert, spiele, aufklappen, zuklappen, ausblenden, kissenSetzen, knaufSchieben, schalterZiehen, puls, flug, umzug, geist,
    aufdecken,
  };
})();
