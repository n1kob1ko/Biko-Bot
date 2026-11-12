// Familienblick: die Familie sieht kurz, wie es der Person heute geht. Der Verwalter sieht alle Personen,
// legt neue an und holt die Einladungscodes. Nie der Inhalt der Gespräche.
(function () {
  'use strict';
  const T = {
    de: {
      titel: 'Familienblick', untertitel_familie: 'So geht es heute. Was gesprochen wird, bleibt privat.',
      untertitel_verwalter: 'Alle Personen, ihre Codes und was Biko kostet.',
      code: 'Code von der Einladung', anmelden: 'Anmelden', fehler: 'Das hat nicht geklappt, bitte nochmal.',
      keine_verbindung: 'Keine Verbindung. Ist das Internet da?',
      gut_heute: 'Heute schon bei Biko gewesen', zuletzt_um: 'Zuletzt {wann}', mal: ', heute {n} Mal mit Biko geredet', mal1: ', heute einmal mit Biko geredet',
      warten: 'Heute noch nichts gehört', warten_checkin: 'Biko fragt um {zeit} nach, ob alles gut ist.',
      nie: 'Noch nie bei Biko gewesen.',
      alarm: 'Hat sich heute nicht gemeldet', alarm_sms: 'Biko hat {wer} eine SMS geschickt. Bitte kurz anrufen.',
      alarm_ohne: 'Bitte kurz anrufen.', entwarnt: 'Hat sich gemeldet', entwarnt_sub: 'Nach der Warnung heute hat sie sich doch gemeldet.',
      checkin_titel: 'Täglicher Check-in', checkin_um: 'Jeden Tag um {zeit}. Ohne Lebenszeichen bekommt {wer} eine SMS.',
      checkin_aus: 'Nicht eingestellt. Dafür sagt man Biko zum Beispiel: "Frag mich jeden Tag um 10, ob alles gut ist, sonst gib Peter Bescheid."',
      erinnerungen: 'Erinnerungen heute', keine_erinnerungen: 'Heute keine.',
      genommen: 'Genommen um {zeit}', nicht_genommen: 'Noch nicht als genommen bestätigt',
      listen: 'Listen', keine_listen: 'Alles erledigt.',
      geburtstage: 'Nächste Geburtstage', heute: 'heute', morgen: 'morgen', in_tagen: 'in {n} Tagen', wird: ', wird {n}',
      gesundheit: 'Gesundheitstagebuch, zwei Wochen', keine_gesundheit: 'Nichts eingetragen.',
      geteilt: '{name} teilt mit der Familie: {ja}.', nicht_geteilt: ' Nicht geteilt: {nein}.',
      geteilt_nichts: '{name} teilt außer dem Lebenszeichen nichts.',
      geteilt_wie: ' Das ändert {name} selbst im Gespräch mit Biko, zum Beispiel: "Meine Familie darf mein Tagebuch sehen."',
      teile: { erinnerungen: 'Erinnerungen', listen: 'Listen', geburtstage: 'Geburtstage', gesundheit: 'Gesundheitstagebuch' },
      sie: 'sie', offen: 'Du redest in der App gerade als diese Person.',
      kosten: 'KI diesen Monat: {d} US-Dollar bei {n} Antworten. Stimme: {z} Zeichen.',
      code_person: 'Code für {name}', code_familie: 'Code für die Familie', oeffnen: 'Biko als {name} öffnen',
      abmelden_alle: 'Alle Geräte abmelden', abmelden_frage: 'Alle Handys von {name} und der Familie abmelden? Danach braucht es neue Codes.',
      ja_abmelden: 'Abmelden', nein: 'Lieber nicht', abgemeldet: 'Abgemeldet. Hol neue Codes, um wieder hineinzukommen.',
      code_fuer_person: 'Für {name}: Link auf dem Handy öffnen oder den Code in Biko eingeben. Dann zum Home-Bildschirm hinzufügen.',
      code_fuer_familie: 'Für die Familie: Link öffnen, dann sieht man hier, wie es {name} geht.',
      gueltig: '{n} Tage gültig, auf mehreren Handys. Ein neuer Code ersetzt den alten; wer schon angemeldet ist, bleibt es.',
      teilen: 'Link teilen', kopiert: 'Link kopiert',
      einladung_person: 'Hallo! Das ist dein Biko. Tipp auf den Link: {link} (Code {code})',
      einladung_familie: 'Familienblick für {name}: {link} (Code {code})',
      neu_titel: 'Neue Person', neu_hilfe: 'Für jede Person ein eigenes Biko: eigenes Gedächtnis, eigene Listen, eigene Erinnerungen.',
      name: 'Name, so wie Biko grüßt', sprache: 'Sprache', anrede: 'Anrede', neu_knopf: 'Anlegen und Codes holen',
      zur_app: 'Zurück zu Biko', abmelden: 'Abmelden',
      hinweis: 'Biko ist eine KI und kann sich irren. Im Notfall: 144.',
    },
    zh: {
      titel: '家人看板', untertitel_familie: '看看今天怎么样。聊天内容是保密的。',
      untertitel_verwalter: '所有人、他们的邀请码和 Biko 的费用。',
      code: '邀请码', anmelden: '登录', fehler: '没有成功，请再试一次。', keine_verbindung: '没有网络连接。',
      gut_heute: '今天已经用过 Biko', zuletzt_um: '最近一次：{wann}', mal: '，今天和 Biko 说了 {n} 次话', mal1: '，今天和 Biko 说了一次话',
      warten: '今天还没有消息', warten_checkin: 'Biko 会在 {zeit} 问问是否一切都好。', nie: '还没有用过 Biko。',
      alarm: '今天还没有回复', alarm_sms: 'Biko 已经给 {wer} 发了短信。请打个电话问问。', alarm_ohne: '请打个电话问问。',
      entwarnt: '已经回复了', entwarnt_sub: '今天提醒之后，已经回复了。',
      checkin_titel: '每日问候', checkin_um: '每天 {zeit}。没有回复的话，{wer} 会收到短信。',
      checkin_aus: '还没有设置。可以对 Biko 说：“每天十点问我是否一切都好，不然就告诉 Peter。”',
      erinnerungen: '今天的提醒', keine_erinnerungen: '今天没有。',
      genommen: '{zeit} 已服用', nicht_genommen: '还没有确认服用', listen: '清单', keine_listen: '都完成了。',
      geburtstage: '最近的生日', heute: '今天', morgen: '明天', in_tagen: '{n} 天后', wird: '，{n} 岁',
      gesundheit: '健康日记（两周）', keine_gesundheit: '没有记录。',
      geteilt: '{name} 和家人分享：{ja}。', nicht_geteilt: ' 不分享：{nein}。', geteilt_nichts: '{name} 只分享是否平安。',
      geteilt_wie: ' {name} 可以自己对 Biko 说来改变，比如：“我的家人可以看我的健康日记。”',
      teile: { erinnerungen: '提醒', listen: '清单', geburtstage: '生日', gesundheit: '健康日记' },
      sie: '她', offen: '你现在在 App 里以这个人的身份使用 Biko。',
      kosten: '本月 AI：{d} 美元，{n} 次回答。语音：{z} 个字。',
      code_person: '{name} 的邀请码', code_familie: '家人的邀请码', oeffnen: '以 {name} 的身份打开 Biko',
      abmelden_alle: '所有设备退出登录', abmelden_frage: '让 {name} 和家人的所有手机都退出登录？之后需要新的邀请码。',
      ja_abmelden: '退出登录', nein: '算了', abgemeldet: '已退出登录。需要新的邀请码才能再登录。',
      code_fuer_person: '给 {name}：在手机上打开链接，或在 Biko 里输入邀请码。然后添加到主屏幕。',
      code_fuer_familie: '给家人：打开链接，就能看到 {name} 今天怎么样。',
      gueltig: '{n} 天内有效，可以用在多部手机上。新的邀请码会替换旧的；已经登录的不受影响。',
      teilen: '分享链接', kopiert: '链接已复制',
      einladung_person: '你好！这是你的 Biko。点这个链接：{link}（邀请码 {code}）',
      einladung_familie: '{name} 的家人看板：{link}（邀请码 {code}）',
      neu_titel: '新的人', neu_hilfe: '每个人都有自己的 Biko：自己的记忆、清单和提醒。',
      name: '名字（Biko 怎么称呼）', sprache: '语言', anrede: '称呼', neu_knopf: '创建并获取邀请码',
      zur_app: '回到 Biko', abmelden: '退出登录', hinweis: 'Biko 是 AI，可能会出错。紧急情况：144。',
    },
  };
  const holen = (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } };
  let sprache = holen('sprache') || ((navigator.language || '').toLowerCase().startsWith('zh') ? 'zh' : 'de');
  if (!T[sprache]) sprache = 'de';
  const t = (k, w) => {
    let s = T[sprache][k] ?? T.de[k] ?? k;
    for (const [a, b] of Object.entries(w || {})) s = s.split('{' + a + '}').join(String(b));
    return s;
  };
  const $ = (s) => document.querySelector(s);
  const el = (tag, attrs, ...kinder) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === 'text') e.textContent = v; else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v);
    }
    kinder.flat().filter(Boolean).forEach((k) => e.append(k));
    return e;
  };
  if (window.Maskottchen) {
    document.querySelectorAll('[data-biko]').forEach((e) => window.Maskottchen.mount(e, { decorative: true }));
    window.Maskottchen.setMood('da');
  }

  async function api(pfad, daten) {
    let r;
    try {
      r = await fetch(pfad, {
        method: daten === undefined ? 'GET' : 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-Sprache': sprache === 'zh' ? 'zh-CN' : 'de-AT' },
        body: daten === undefined ? undefined : JSON.stringify(daten),
      });
    } catch (e) { throw new Error(t('keine_verbindung')); }
    let j = {};
    try { j = await r.json(); } catch (e) { /* leer */ }
    if (!r.ok) { const f = new Error(j.fehler || t('fehler')); f.status = r.status; throw f; }
    return j;
  }

  // ---------- Zeit ----------
  const zweistellig = (n) => String(n).padStart(2, '0');
  function wann(iso) {
    const d = new Date(iso), jetzt = new Date();
    const uhr = `${d.getHours()}:${zweistellig(d.getMinutes())}`;
    const tage = Math.round((new Date(jetzt.toDateString()) - new Date(d.toDateString())) / 86400000);
    if (sprache === 'zh') return tage === 0 ? `今天 ${uhr}` : tage === 1 ? `昨天 ${uhr}` : `${d.getMonth() + 1}月${d.getDate()}日 ${uhr}`;
    return tage === 0 ? `heute um ${uhr}` : tage === 1 ? `gestern um ${uhr}` : `am ${d.getDate()}.${d.getMonth() + 1}. um ${uhr}`;
  }
  const heuteSchon = (iso) => iso && new Date(iso).toDateString() === new Date().toDateString();

  // ---------- Eine Person ----------
  function status(p) {
    const c = p.checkin, name = p.name || t('sie');
    if (c.alarm && !c.entwarnt) {
      return ['alarm', t('alarm'), c.kontakte.length ? t('alarm_sms', { wer: c.kontakte.join(', ') }) : t('alarm_ohne')];
    }
    if (c.alarm && c.entwarnt) return ['gut', t('entwarnt'), t('entwarnt_sub', { name })];
    if (heuteSchon(p.zuletzt)) {
      const mal = p.heute_geredet === 1 ? t('mal1') : p.heute_geredet > 1 ? t('mal', { n: p.heute_geredet }) : '';
      return ['gut', t('gut_heute'), t('zuletzt_um', { wann: wann(p.zuletzt) }) + mal];
    }
    const sub = c.zeit && !c.gemeldet ? t('warten_checkin', { zeit: c.zeit }) + ' ' : '';
    return ['warten', t('warten'), sub + (p.zuletzt ? t('zuletzt_um', { wann: wann(p.zuletzt) }) : t('nie'))];
  }

  function teil(titel, eintraege, leer) {
    return el('div', { class: 'teil' }, el('h3', { text: titel }),
      eintraege.length ? el('ul', {}, eintraege) : el('p', { class: 'leer', text: leer }));
  }

  function personKarte(p, verwalter) {
    const name = p.name || p.bezeichnung || t('sie');
    const [art, titel, sub] = status(p);
    const karte = el('section', { class: 'karte person', 'data-person': p.person },
      el('div', {}, el('h2', { text: name }), p.offen ? el('p', { class: 'offen-hinweis', text: t('offen') }) : null),
      el('div', { class: 'status', 'data-art': art, role: 'status' }, el('i', { class: 'punkt', 'aria-hidden': 'true' }),
        el('strong', { text: titel }), el('span', { text: sub })));
    const c = p.checkin;
    karte.append(el('div', { class: 'teil' }, el('h3', { text: t('checkin_titel') }),
      el('p', { class: c.zeit ? '' : 'leer', text: c.zeit ? t('checkin_um', { zeit: c.zeit, wer: c.kontakte.join(', ') || '-' }) : t('checkin_aus') })));
    if (p.erinnerungen) {
      karte.append(teil(t('erinnerungen'), p.erinnerungen.map((e) => el('li', {}, el('span', { class: 'zeit', text: e.zeit }), el('span', { text: e.text }),
        e.medikament && (e.genommen || e.faellig) ? el('span', { class: 'notiz-text', text: e.genommen ? t('genommen', { zeit: e.genommen }) : t('nicht_genommen') }) : null)), t('keine_erinnerungen')));
    }
    if (p.listen) {
      karte.append(teil(t('listen'), Object.entries(p.listen).map(([liste, dinge]) => el('li', { class: 'einfach' },
        el('span', {}, el('strong', { text: liste + ': ' }), dinge.join(', ')))), t('keine_listen')));
    }
    if (p.geburtstage && p.geburtstage.length) {
      karte.append(teil(t('geburtstage'), p.geburtstage.map((g) => el('li', {}, el('span', { class: 'zeit', text: `${g.tag}.${g.monat}.` }),
        el('span', { text: g.name + ' (' + (g.in_tagen === 0 ? t('heute') : g.in_tagen === 1 ? t('morgen') : t('in_tagen', { n: g.in_tagen }))
          + (g.alter ? t('wird', { n: g.alter }) : '') + ')' }))), ''));
    }
    if (p.gesundheit) {
      karte.append(teil(t('gesundheit'), p.gesundheit.slice().reverse().map((e) => {
        const d = new Date(e.zeit);
        return el('li', {}, el('span', { class: 'zeit', text: `${d.getDate()}.${d.getMonth() + 1}.` }),
          el('span', { text: `${e.art} ${e.wert}` }), e.notiz ? el('span', { class: 'notiz-text', text: e.notiz }) : null);
      }), t('keine_gesundheit')));
    }
    const f = p.freigabe, ja = Object.keys(f).filter((k) => f[k]).map((k) => t('teile')[k]);
    const nein = Object.keys(f).filter((k) => !f[k]).map((k) => t('teile')[k]);
    karte.append(el('p', { class: 'geteilt', text: (ja.length ? t('geteilt', { name, ja: ja.join(', ') }) : t('geteilt_nichts', { name }))
      + (nein.length ? t('nicht_geteilt', { nein: nein.join(', ') }) : '') + t('geteilt_wie', { name }) }));
    if (verwalter) karte.append(verwalten(p, name));
    return karte;
  }

  // ---------- Verwalter: Codes, Biko öffnen, abmelden ----------
  function codeKarte(rolle, name, c) {
    const pfad = rolle === 'familie' ? '/familie.html' : '/';
    const link = `${location.origin}${pfad}?code=${encodeURIComponent(c.code)}`;
    const text = t(rolle === 'familie' ? 'einladung_familie' : 'einladung_person', { name, link, code: c.code });
    const knopf = el('button', { type: 'button', class: 'knopf druck', text: t('teilen') });
    knopf.addEventListener('click', async () => {
      if (navigator.share) { try { await navigator.share({ text }); return; } catch (e) { if (e.name === 'AbortError') return; } }
      try { await navigator.clipboard.writeText(text); knopf.textContent = t('kopiert'); } catch (e) { /* Link steht ja da */ }
    });
    return el('div', { class: 'code-karte', role: 'status' },
      el('p', { text: t(rolle === 'familie' ? 'code_fuer_familie' : 'code_fuer_person', { name }) }),
      el('p', { class: 'code', text: c.code }), el('p', { class: 'link', text: link }),
      el('p', { class: 'leise klein', text: t('gueltig', { n: c.tage }) }), knopf);
  }

  function verwalten(p, name) {
    const k = p.kosten || { dollar: 0, antworten: 0, zeichen: 0 };
    const zahl = (n, s) => n.toLocaleString(sprache === 'zh' ? 'zh-CN' : 'de-AT', { minimumFractionDigits: s, maximumFractionDigits: s });
    const platz = el('div', {});
    const meldung = el('p', { class: 'meldung fehler', role: 'alert' });
    const codeHolen = (rolle) => async () => {
      meldung.textContent = '';
      try { platz.replaceChildren(codeKarte(rolle, name, await api('/api/verwaltung/code', { person: p.person, rolle }))); } catch (e) { meldung.textContent = e.message; }
    };
    const box = el('div', { class: 'verwalten' },
      el('p', { class: 'leise klein kosten', text: t('kosten', { d: zahl(k.dollar, 2), n: k.antworten, z: zahl(k.zeichen, 0) }) }),
      el('button', { type: 'button', class: 'knopf druck', text: t('code_person', { name }), onclick: codeHolen('person') }),
      el('button', { type: 'button', class: 'knopf druck', text: t('code_familie'), onclick: codeHolen('familie') }),
      platz,
      p.offen ? null : el('button', { type: 'button', class: 'knopf haupt druck', text: t('oeffnen', { name }), onclick: async () => {
        try { await api('/api/verwaltung/oeffnen', { person: p.person }); location.href = '/'; } catch (e) { meldung.textContent = e.message; }
      } }),
      el('button', { type: 'button', class: 'knopf druck', text: t('abmelden_alle'), onclick: () => {
        platz.replaceChildren(el('div', { class: 'sicher-zeile' }, el('p', { text: t('abmelden_frage', { name }) }),
          el('button', { type: 'button', class: 'knopf druck', text: t('nein'), onclick: () => platz.replaceChildren() }),
          el('button', { type: 'button', class: 'knopf druck ja', text: t('ja_abmelden'), onclick: async () => {
            try { await api('/api/verwaltung/abmelden', { person: p.person }); platz.replaceChildren(el('p', { class: 'meldung', text: t('abgemeldet') })); } catch (e) { meldung.textContent = e.message; }
          } })));
      } }),
      meldung);
    return box;
  }

  // ---------- Seite ----------
  let rolle = null;
  function texte() {
    document.documentElement.lang = sprache === 'zh' ? 'zh-CN' : 'de';
    $('#titel').textContent = t('titel');
    $('#untertitel').textContent = rolle === 'verwalter' ? t('untertitel_verwalter') : t('untertitel_familie');
    $('#code-label').textContent = t('code');
    $('#anmelden').textContent = t('anmelden');
    $('#neu-titel').textContent = t('neu_titel');
    $('#neu-hilfe').textContent = t('neu_hilfe');
    $('#neu-name-label').textContent = t('name');
    $('#neu-sprache-label').textContent = t('sprache');
    $('#neu-anrede-label').textContent = t('anrede');
    $('#neu-knopf').textContent = t('neu_knopf');
    $('#zur-app').textContent = t('zur_app');
    $('#abmelden').textContent = t('abmelden');
    $('#hinweis').textContent = t('hinweis');
  }

  let erstesMal = true;
  async function laden() {
    let d;
    try { d = await api('/api/familie'); } catch (e) {
      if (e.status === 401) return loginZeigen();
      if (e.status === 403) { location.replace('/'); return; }
      $('#login-fehler').textContent = e.message;
      return;
    }
    rolle = d.rolle;
    if (rolle === 'person') { location.replace('/'); return; }
    $('#login').hidden = true;
    const verwalter = rolle === 'verwalter';
    $('#neu').hidden = !verwalter;
    $('#zur-app').hidden = !verwalter;
    $('#abmelden').hidden = verwalter;
    texte();
    // Offene Codes und Nachfragen nicht wegwerfen, wenn die Seite von selbst neu lädt
    if (!erstesMal && document.querySelector('.code-karte, .sicher-zeile')) return;
    $('#personen').replaceChildren(...d.personen.map((p) => {
      const k = personKarte(p, verwalter);
      if (erstesMal) k.classList.add('kommt');
      return k;
    }));
    erstesMal = false;
  }

  function loginZeigen() {
    $('#login').hidden = false;
    $('#neu').hidden = true;
    $('#abmelden').hidden = true;
    $('#zur-app').hidden = true;
    $('#personen').replaceChildren();
    texte();
  }

  async function anmelden(code) {
    $('#login-fehler').textContent = '';
    try {
      const j = await api('/api/login', { code });
      if (j.rolle === 'person') { location.replace('/'); return; }
      history.replaceState(null, '', '/familie.html');
      await laden();
    } catch (e) { $('#login-fehler').textContent = e.message; }
  }

  $('#login-form').addEventListener('submit', (e) => { e.preventDefault(); anmelden($('#code').value); });
  $('#neu-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    $('#neu-fehler').textContent = '';
    const name = $('#neu-name').value.trim();
    try {
      const j = await api('/api/verwaltung/person', { name, sprache: $('#neu-sprache').value, anrede: $('#neu-anrede').value });
      $('#neu-name').value = '';
      erstesMal = true;
      await laden();
      const karte = document.querySelector(`[data-person="${j.person}"] .verwalten > div`);
      if (karte) {
        karte.replaceChildren(codeKarte('person', name, j.person_code), codeKarte('familie', name, j.familie_code));
        karte.closest('.person').scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    } catch (err) { $('#neu-fehler').textContent = err.message; }
  });
  $('#zur-app').addEventListener('click', () => { location.href = '/'; });
  $('#abmelden').addEventListener('click', async () => {
    try { await api('/api/abmelden', {}); } catch (e) { /* trotzdem */ }
    loginZeigen();
  });

  texte();
  const code = new URLSearchParams(location.search).get('code');
  if (code) anmelden(code); else laden();
  setInterval(() => { if (rolle && document.visibilityState === 'visible') laden(); }, 60000);
})();
