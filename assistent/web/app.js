// Biko Helfer: Oberfläche auf Deutsch und Chinesisch. Keine externen Abhängigkeiten.
(function () {
  'use strict';

  // ---------- Texte ----------
  const T = {
    de: {
      login_titel: 'Hallo, ich bin Biko!',
      login_text: 'Bitte einmal das Passwort eingeben. Danach merkt sich das Handy dich.',
      passwort: 'Passwort', anmelden: 'Anmelden',
      erinnerung: 'Erinnerung', erledigt: 'Erledigt', spaeter: 'In 10 Minuten nochmal',
      hallo: 'Hallo!', hallo_name: 'Hallo, {name}!',
      reden_text: 'Frag mich, was du willst. Oder erzähl mir einfach etwas.',
      hier_schreiben: 'Hier schreiben …', sprechen: '🎤 Sprechen', hoere: '● Ich höre zu …', senden: 'Senden',
      vorlesen: '🔊 Vorlesen', stopp: '■ Stopp', denkt: 'Biko denkt nach …',
      vorschlaege: ['Gibt es diese Woche Angebote für Kaffee?', 'Was kann ich heute Gesundes kochen?', 'Erzähl mir etwas Schönes', 'Wie wird das Wetter morgen?'],
      nachricht_titel: 'Nachricht schreiben', nachricht_text: 'Sag mir kurz, was du sagen willst. Ich schreibe es schön.',
      an_wen: 'An wen?', an_wen_ph: 'z. B. meine Enkelin Anna',
      was_sagen: 'Was willst du sagen?', was_sagen_ph: 'z. B. danke für die Blumen, Sonntag Kaffee?',
      schreiben: 'Schreiben', so_lautet: 'So könnte die Nachricht lauten:',
      kopieren: 'Kopieren', teilen: 'Senden mit …',
      kopiert: 'Kopiert! Jetzt in WeChat, WhatsApp oder SMS lange drücken und "Einfügen" wählen.',
      kopieren_geht_nicht: 'Kopieren ging nicht. Bitte den Text lange drücken und kopieren.',
      erinnern_titel: 'Erinnerungen', erinnern_text: 'Ich melde mich, wenn es so weit ist. Dafür diese Seite offen lassen.',
      neue_erinnerung: 'Neue Erinnerung', uhrzeit: 'Uhrzeit', woran: 'Woran soll ich erinnern?',
      woran_ph: 'z. B. Blutdrucktablette nehmen', welche_tage: 'An welchen Tagen?', speichern: 'Speichern',
      ton_test: 'Ton und Hinweis testen', test_text: 'So sieht eine Erinnerung aus.',
      keine_erinnerungen: 'Noch keine Erinnerungen.', jeden_tag: 'jeden Tag', loeschen: 'Löschen',
      tage: { mo: 'Mo', di: 'Di', mi: 'Mi', do: 'Do', fr: 'Fr', sa: 'Sa', so: 'So' },
      einstellen_titel: 'Einstellungen', einstellen_text: 'Für die Familie. Biko liest das bei jeder Antwort mit.',
      name: 'Name', name_ph: 'z. B. Oma Li', anrede: 'Anrede', anrede_du: 'du', anrede_sie: 'Sie',
      diaet: 'Diät-Regeln', diaet_ph: 'z. B. Diabetes: wenig Zucker und Weißmehl. Kein Grapefruitsaft (Medikament).',
      notizen: 'Gut zu wissen', notizen_ph: 'z. B. Enkel heißt Niko. Hört schlecht, mag Gartenarbeit.',
      vorlesen_immer: 'Antworten immer laut vorlesen', schrift: 'Schriftgröße',
      schrift_normal: 'Normal', schrift_gross: 'Groß', schrift_sehr_gross: 'Sehr groß',
      gespeichert: 'Gespeichert.', vergessen: 'Gespräch vergessen', vergessen_ok: 'Biko hat das Gespräch vergessen.',
      hinweis: 'Biko ist eine KI und kann sich irren. Notfall: 144. Fragen zur Gesundheit: 1450.',
      tab_reden: 'Reden', tab_nachricht: 'Nachricht', tab_erinnern: 'Erinnern', tab_einstellen: 'Einstellen',
      kein_mikro: 'Sprechen geht in diesem Browser leider nicht. Bitte die Mikrofon-Taste der Tastatur benutzen.',
      fehler: 'Das hat nicht geklappt. Bitte nochmal probieren.',
      sprache_knopf: '中文',
    },
    zh: {
      login_titel: '你好，我是 Biko！',
      login_text: '请输入一次密码。之后手机会记住你。',
      passwort: '密码', anmelden: '登录',
      erinnerung: '提醒', erledigt: '已完成', spaeter: '10 分钟后再提醒',
      hallo: '你好！', hallo_name: '你好，{name}！',
      reden_text: '想问什么都可以。或者跟我聊聊天。',
      hier_schreiben: '在这里输入……', sprechen: '🎤 说话', hoere: '● 我在听……', senden: '发送',
      vorlesen: '🔊 朗读', stopp: '■ 停止', denkt: 'Biko 正在想……',
      vorschlaege: ['这周超市有什么优惠？', '今天做什么健康的菜？', '跟我说点开心的事', '明天天气怎么样？'],
      nachricht_titel: '写消息', nachricht_text: '简单告诉我你想说什么，我帮你写好。',
      an_wen: '发给谁？', an_wen_ph: '例如：我的孙女安娜',
      was_sagen: '想说什么？', was_sagen_ph: '例如：谢谢你的花，周日一起喝咖啡？',
      schreiben: '帮我写', so_lautet: '消息可以这样写：',
      kopieren: '复制', teilen: '发送到……',
      kopiert: '已复制！在微信、WhatsApp 或短信里长按，选择"粘贴"。',
      kopieren_geht_nicht: '复制失败。请长按文字复制。',
      erinnern_titel: '提醒', erinnern_text: '时间到了我会提醒你。请让这个页面保持打开。',
      neue_erinnerung: '新提醒', uhrzeit: '时间', woran: '提醒什么？',
      woran_ph: '例如：吃降压药', welche_tage: '哪几天？', speichern: '保存',
      ton_test: '测试声音和提醒', test_text: '提醒就是这个样子。',
      keine_erinnerungen: '还没有提醒。', jeden_tag: '每天', loeschen: '删除',
      tage: { mo: '一', di: '二', mi: '三', do: '四', fr: '五', sa: '六', so: '日' },
      einstellen_titel: '设置', einstellen_text: '给家人填写。Biko 每次回答都会参考这些内容。',
      name: '名字', name_ph: '例如：李奶奶', anrede: '称呼', anrede_du: '你（德语 du）', anrede_sie: '您（德语 Sie）',
      diaet: '饮食规则', diaet_ph: '例如：糖尿病，少糖少白面。不喝西柚汁（药物）。',
      notizen: '其他信息', notizen_ph: '例如：孙子叫 Niko。听力不好，喜欢种花。',
      vorlesen_immer: '总是朗读回答', schrift: '字体大小',
      schrift_normal: '正常', schrift_gross: '大', schrift_sehr_gross: '特大',
      gespeichert: '已保存。', vergessen: '忘记对话', vergessen_ok: 'Biko 已经忘记这段对话。',
      hinweis: 'Biko 是人工智能，可能会出错。紧急情况请拨 144。健康问题请拨 1450。',
      tab_reden: '聊天', tab_nachricht: '消息', tab_erinnern: '提醒', tab_einstellen: '设置',
      kein_mikro: '这个浏览器不能用语音。请用键盘上的麦克风按钮。',
      fehler: '没有成功，请再试一次。',
      sprache_knopf: 'Deutsch',
    },
  };
  const STIMME = { de: 'de-AT', zh: 'zh-CN' };
  const TAGE = ['mo', 'di', 'mi', 'do', 'fr', 'sa', 'so'];
  const JS_TAG = ['so', 'mo', 'di', 'mi', 'do', 'fr', 'sa']; // Date.getDay()

  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const merken = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* egal */ } };
  const holen = (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } };

  let sprache = holen('sprache') === 'zh' ? 'zh' : 'de';
  let profil = {};
  let erinnerungen = [];
  const t = (k) => T[sprache][k] ?? T.de[k] ?? k;

  // ---------- Sprache der Oberfläche ----------
  function texteSetzen() {
    document.documentElement.lang = sprache === 'zh' ? 'zh-CN' : 'de';
    $$('[data-t]').forEach((el) => { el.textContent = t(el.dataset.t); });
    $$('[data-t-ph]').forEach((el) => { el.placeholder = t(el.dataset.tPh); });
    $('#sprache-knopf').textContent = t('sprache_knopf');
    $('#gruss').textContent = profil.name ? t('hallo_name').replace('{name}', profil.name) : t('hallo');
    tageAufbauen();
    vorschlaegeZeigen();
    erinnerungenZeigen();
  }

  $('#sprache-knopf').addEventListener('click', () => {
    sprache = sprache === 'zh' ? 'de' : 'zh';
    merken('sprache', sprache);
    texteSetzen();
    if (!$('#app').hidden) {
      profil.sprache = STIMME[sprache];
      api('/api/profil', profil).catch(() => {});
    }
  });

  // ---------- Server ----------
  async function api(pfad, daten) {
    const r = await fetch(pfad, {
      method: daten === undefined ? 'GET' : 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Sprache': STIMME[sprache] },
      body: daten === undefined ? undefined : JSON.stringify(daten),
      credentials: 'same-origin',
    });
    let j = {};
    try { j = await r.json(); } catch (e) { /* leer */ }
    if (r.status === 401) { loginZeigen(); }
    if (!r.ok) throw new Error(j.fehler || t('fehler'));
    return j;
  }

  // ---------- Anmelden ----------
  function loginZeigen() { $('#app').hidden = true; $('#login').hidden = false; }

  $('#login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    $('#login-fehler').textContent = '';
    try {
      await api('/api/login', { passwort: $('#passwort').value });
      $('#passwort').value = '';
      await starten();
    } catch (err) { $('#login-fehler').textContent = err.message; }
  });

  async function starten() {
    const s = await api('/api/status');
    if (!s.angemeldet) { texteSetzen(); loginZeigen(); return; }
    $('#login').hidden = true;
    $('#app').hidden = false;
    [profil, erinnerungen] = await Promise.all([api('/api/profil'), api('/api/erinnerungen')]);
    if (!holen('sprache') && profil.sprache) sprache = profil.sprache.startsWith('zh') ? 'zh' : 'de';
    profilInsFormular();
    texteSetzen();
    const verlauf = await api('/api/verlauf');
    $('#verlauf').innerHTML = '';
    verlauf.forEach((m) => blase(m.content, m.role === 'user' ? 'ich' : 'biko-sagt'));
    vorschlaegeZeigen();
    setInterval(erinnerungPruefen, 15000);
    erinnerungPruefen();
  }

  // ---------- Ansichten ----------
  $$('.leiste button').forEach((b) => b.addEventListener('click', () => {
    $$('.leiste button').forEach((x) => x.removeAttribute('aria-current'));
    b.setAttribute('aria-current', 'page');
    $$('.ansicht').forEach((a) => { a.hidden = a.dataset.ansicht !== b.dataset.ziel; });
    window.scrollTo(0, 0);
  }));

  // ---------- Vorlesen ----------
  let liestGerade = null;
  function vorlesen(text, knopf) {
    if (!('speechSynthesis' in window)) return;
    speechSynthesis.cancel();
    if (liestGerade === knopf && knopf) { liestGerade = null; knopf.textContent = t('vorlesen'); return; }
    const u = new SpeechSynthesisUtterance(text);
    // Sprache am Text erkennen: chinesische Schriftzeichen -> Chinesisch
    u.lang = /[一-鿿]/.test(text) ? 'zh-CN' : 'de-AT';
    u.rate = 0.92;
    if (knopf) {
      liestGerade = knopf;
      knopf.textContent = t('stopp');
      u.onend = u.onerror = () => { knopf.textContent = t('vorlesen'); liestGerade = null; };
    }
    speechSynthesis.speak(u);
  }

  // ---------- Sprechen statt tippen ----------
  const Erkennung = window.SpeechRecognition || window.webkitSpeechRecognition;
  $$('.mikro').forEach((knopf) => knopf.addEventListener('click', () => {
    const feld = document.getElementById(knopf.dataset.ziel);
    if (!Erkennung) { alertSanft(knopf, t('kein_mikro')); feld.focus(); return; }
    const r = new Erkennung();
    r.lang = STIMME[sprache];
    r.interimResults = true;
    const vorher = feld.value ? feld.value + ' ' : '';
    knopf.classList.add('hoert');
    knopf.textContent = t('hoere');
    r.onresult = (e) => {
      feld.value = vorher + Array.from(e.results).map((x) => x[0].transcript).join('');
    };
    r.onend = () => {
      knopf.classList.remove('hoert');
      knopf.textContent = t('sprechen');
      // Im Gespräch gleich abschicken, wie bei einer Sprachnachricht
      if (feld.id === 'chat-text' && feld.value.trim()) $('#chat-form').requestSubmit();
    };
    r.onerror = () => { knopf.classList.remove('hoert'); knopf.textContent = t('sprechen'); };
    r.start();
  }));

  function alertSanft(nahe, text) {
    const p = document.createElement('p');
    p.className = 'leise';
    p.textContent = text;
    nahe.closest('form').appendChild(p);
    setTimeout(() => p.remove(), 6000);
  }

  // ---------- 1. Reden ----------
  function blase(text, art) {
    const d = document.createElement('div');
    d.className = 'blase ' + art;
    d.textContent = text;
    if (art === 'biko-sagt') {
      const k = document.createElement('button');
      k.type = 'button';
      k.className = 'vorlesen';
      k.textContent = t('vorlesen');
      k.addEventListener('click', () => vorlesen(text, k));
      d.appendChild(k);
    }
    $('#verlauf').appendChild(d);
    // Ganz nach unten, damit die neue Blase über dem Eingabefeld sichtbar ist
    window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'smooth' });
    return d;
  }

  function vorschlaegeZeigen() {
    const box = $('#vorschlaege');
    box.innerHTML = '';
    if ($('#verlauf').children.length) return;
    t('vorschlaege').forEach((v) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'vorschlag';
      b.textContent = v;
      b.addEventListener('click', () => { $('#chat-text').value = v; $('#chat-form').requestSubmit(); });
      box.appendChild(b);
    });
  }

  let sendet = false;
  $('#chat-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const feld = $('#chat-text');
    const text = feld.value.trim();
    if (!text || sendet) return;
    sendet = true;
    feld.value = '';
    $('#vorschlaege').innerHTML = '';
    blase(text, 'ich');
    const warte = blase(t('denkt'), 'denkt-blase');
    $('#biko-reden').classList.add('denkt');
    try {
      const { antwort } = await api('/api/chat', { text });
      warte.remove();
      const d = blase(antwort, 'biko-sagt');
      if ($('#vorlesen').checked) vorlesen(antwort, d.querySelector('.vorlesen'));
    } catch (err) {
      warte.remove();
      blase(err.message, 'fehler-blase');
      feld.value = text;
    } finally {
      sendet = false;
      $('#biko-reden').classList.remove('denkt');
    }
  });

  // ---------- 2. Nachricht ----------
  $('#nachricht-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const knopf = e.submitter || $('#nachricht-form .haupt');
    knopf.disabled = true;
    knopf.textContent = t('denkt');
    $('#nachricht-info').textContent = '';
    try {
      const { nachricht } = await api('/api/nachricht', { an: $('#nachricht-an').value, was: $('#nachricht-was').value });
      $('#nachricht-text').textContent = nachricht;
      $('#nachricht-ergebnis').hidden = false;
      $('#nachricht-teilen').hidden = !navigator.share;
      $('#nachricht-ergebnis').scrollIntoView({ behavior: 'smooth' });
    } catch (err) {
      $('#nachricht-info').textContent = err.message;
      $('#nachricht-ergebnis').hidden = false;
    } finally {
      knopf.disabled = false;
      knopf.textContent = t('schreiben');
    }
  });
  $('#nachricht-kopieren').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText($('#nachricht-text').textContent);
      $('#nachricht-info').textContent = t('kopiert');
    } catch (e) { $('#nachricht-info').textContent = t('kopieren_geht_nicht'); }
  });
  $('#nachricht-teilen').addEventListener('click', () => {
    navigator.share({ text: $('#nachricht-text').textContent }).catch(() => {});
  });

  // ---------- 3. Erinnerungen ----------
  function tageAufbauen() {
    const fs = $('#tage-wahl');
    const gewaehlt = new Set($$('#tage-wahl input:checked').map((i) => i.value));
    const ersterAufbau = !fs.querySelector('input');
    fs.querySelectorAll('label').forEach((l) => l.remove());
    TAGE.forEach((tag) => {
      const l = document.createElement('label');
      const i = document.createElement('input');
      i.type = 'checkbox';
      i.value = tag;
      i.checked = ersterAufbau || gewaehlt.has(tag);
      l.append(i, ' ' + t('tage')[tag]);
      fs.appendChild(l);
    });
  }

  function erinnerungenZeigen() {
    const ul = $('#erinnerungen');
    ul.innerHTML = '';
    if (!erinnerungen.length) {
      const li = document.createElement('li');
      li.className = 'leer-zeile';
      li.textContent = t('keine_erinnerungen');
      ul.appendChild(li);
      return;
    }
    erinnerungen.forEach((er) => {
      const li = document.createElement('li');
      const zeit = document.createElement('span');
      zeit.className = 'zeit';
      zeit.textContent = er.zeit;
      const mitte = document.createElement('div');
      const text = document.createElement('div');
      text.textContent = er.text;
      const tage = document.createElement('div');
      tage.className = 'tage-text';
      tage.textContent = er.tage.length === 7 ? t('jeden_tag') : er.tage.map((x) => t('tage')[x]).join(', ');
      mitte.append(text, tage);
      const weg = document.createElement('button');
      weg.type = 'button';
      weg.className = 'weg';
      weg.textContent = '🗑';
      weg.setAttribute('aria-label', t('loeschen'));
      weg.addEventListener('click', () => erinnerungenSpeichern(erinnerungen.filter((x) => x.id !== er.id)));
      li.append(zeit, mitte, weg);
      ul.appendChild(li);
    });
  }

  async function erinnerungenSpeichern(liste) {
    erinnerungen = await api('/api/erinnerungen', { erinnerungen: liste });
    erinnerungenZeigen();
  }

  $('#erinnerung-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const tage = $$('#tage-wahl input:checked').map((i) => i.value);
    try {
      await erinnerungenSpeichern(erinnerungen.concat({
        zeit: $('#erinnerung-zeit').value, text: $('#erinnerung-text').value, tage,
      }));
      $('#erinnerung-text').value = '';
    } catch (err) { alertSanft($('#erinnerung-form .haupt'), err.message); }
    // Erlaubnis für Hinweise holen, solange die Person gerade etwas angetippt hat
    if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission();
  });

  // Welche Erinnerung wurde heute schon gezeigt? (pro Handy, im Browser gemerkt)
  const heute = () => new Date().toISOString().slice(0, 10);
  let snooze = {}; // id -> Zeitpunkt in ms
  let offen = null;

  function erinnerungPruefen() {
    if (offen) return;
    const jetzt = new Date();
    const hhmm = jetzt.toTimeString().slice(0, 5);
    const tag = JS_TAG[jetzt.getDay()];
    for (const er of erinnerungen) {
      if (!er.aktiv || !er.tage.includes(tag)) continue;
      const schluessel = 'gezeigt-' + er.id + '-' + heute();
      const faellig = (er.zeit <= hhmm && !holen(schluessel)) || (snooze[er.id] && snooze[er.id] <= jetzt.getTime());
      // Nur bis 2 Stunden nach der Uhrzeit nachholen (z. B. wenn das Handy kurz aus war)
      const [h, m] = er.zeit.split(':').map(Number);
      const minutenSeit = jetzt.getHours() * 60 + jetzt.getMinutes() - (h * 60 + m);
      if (faellig && minutenSeit <= 120) { alarm(er); return; }
    }
  }

  function alarm(er) {
    offen = er;
    $('#alarm-text').textContent = er.text;
    $('#alarm').hidden = false;
    ton();
    vorlesen((sprache === 'zh' ? '提醒：' : 'Erinnerung: ') + er.text);
    if (navigator.vibrate) navigator.vibrate([300, 150, 300, 150, 300]);
    if ('Notification' in window && Notification.permission === 'granted' && document.hidden) {
      try { new Notification('Biko: ' + t('erinnerung'), { body: er.text, icon: 'icon.svg' }); } catch (e) { /* manche Handys nur per Service Worker */ }
    }
  }

  function alarmZu(spaeter) {
    if (!offen) return;
    if (offen.id !== 'test') merken('gezeigt-' + offen.id + '-' + heute(), '1');
    if (spaeter) snooze[offen.id] = Date.now() + 10 * 60 * 1000; else delete snooze[offen.id];
    offen = null;
    $('#alarm').hidden = true;
    speechSynthesis && speechSynthesis.cancel();
  }
  $('#alarm-ok').addEventListener('click', () => alarmZu(false));
  $('#alarm-spaeter').addEventListener('click', () => alarmZu(true));
  $('#ton-test').addEventListener('click', () => {
    if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission();
    alarm({ id: 'test', text: t('test_text') });
  });

  // Freundlicher Dreiklang, ohne Audiodatei
  function ton() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      [523, 659, 784].forEach((f, i) => {
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.frequency.value = f;
        o.connect(g); g.connect(ctx.destination);
        const s = ctx.currentTime + i * 0.25;
        g.gain.setValueAtTime(0.0001, s);
        g.gain.exponentialRampToValueAtTime(0.4, s + 0.03);
        g.gain.exponentialRampToValueAtTime(0.0001, s + 0.5);
        o.start(s); o.stop(s + 0.55);
      });
    } catch (e) { /* kein Ton möglich */ }
  }

  // ---------- Einstellungen ----------
  function profilInsFormular() {
    $('#profil-name').value = profil.name || '';
    $('#profil-anrede').value = profil.anrede || 'du';
    $('#profil-diaet').value = profil.diaet || '';
    $('#profil-notizen').value = profil.notizen || '';
    $('#vorlesen').checked = holen('vorlesen') === '1';
    $('#schrift').value = holen('schrift') || '1';
    document.documentElement.style.setProperty('--schrift', $('#schrift').value);
  }
  $('#schrift').addEventListener('change', () => {
    document.documentElement.style.setProperty('--schrift', $('#schrift').value);
    merken('schrift', $('#schrift').value);
  });
  $('#vorlesen').addEventListener('change', () => merken('vorlesen', $('#vorlesen').checked ? '1' : '0'));

  $('#profil-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      profil = await api('/api/profil', {
        name: $('#profil-name').value, anrede: $('#profil-anrede').value,
        diaet: $('#profil-diaet').value, notizen: $('#profil-notizen').value, sprache: STIMME[sprache],
      });
      $('#profil-info').textContent = t('gespeichert');
      texteSetzen();
    } catch (err) { $('#profil-info').textContent = err.message; }
  });

  $('#verlauf-loeschen').addEventListener('click', async () => {
    await api('/api/verlauf/loeschen', {});
    $('#verlauf').innerHTML = '';
    vorschlaegeZeigen();
    $('#profil-info').textContent = t('vergessen_ok');
  });

  document.documentElement.style.setProperty('--schrift', holen('schrift') || '1');
  texteSetzen();
  starten().catch(() => { texteSetzen(); loginZeigen(); });
})();
