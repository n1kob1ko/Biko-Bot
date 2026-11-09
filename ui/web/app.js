// Biko App: liest die REST-API des eigenen Freqtrade-Bots (über /api/v1, vom nginx weitergeleitet).
// Schreibend nur: Pause/Weiter, Trade verkaufen, Einstellungen speichern (jeweils mit Abfrage).
// Kein Tracking, keine externen Server.
(function () {
  'use strict';

  const API = '/api/v1';
  const POLL_MS = 15000;
  const RECENT_CLOSE_MS = 20 * 60 * 1000; // so lange freut/ärgert sich Biko nach einem geschlossenen Trade

  const $ = (id) => document.getElementById(id);
  const params = new URLSearchParams(location.search);
  const DEMO = params.has('demo');

  // ---------- Speicher (nur Komfort: Login merken) ----------
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* privat */ } },
    del(k) { try { localStorage.removeItem(k); } catch { /* privat */ } },
  };

  // ---------- Bewegung ----------
  // Regeln: Eingänge ease-out, Bewegungen ease-in-out, Ausgänge 20 % kürzer, nichts federt,
  // nur transform/opacity (plus Blur beim Textwechsel). Bei "weniger Bewegung" nur Ein-/Ausblenden.
  const EASE_OUT = 'cubic-bezier(0.23, 1, 0.32, 1)';
  const EASE_IN_OUT = 'cubic-bezier(0.77, 0, 0.175, 1)';
  const T = { enter: 200, exit: 160, move: 220, text: 140 };
  const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
  const reduced = () => motionQuery.matches;
  const canAnimate = typeof Element.prototype.animate === 'function';

  function animate(el, frames, opts) {
    if (!canAnimate) return Promise.resolve();
    if (reduced()) {
      // Bewegung raus, Ein-/Ausblenden bleibt (hilft beim Verstehen)
      frames = frames.map((f) => ({ opacity: f.opacity ?? 1, offset: f.offset }));
      opts = { ...opts, duration: Math.min(opts.duration || 160, 160) };
    }
    const a = el.animate(frames, { fill: 'none', ...opts });
    return a.finished.catch(() => {});
  }

  // Text wechseln: altes blendet mit leichtem Blur aus, neues ein (statt zwei Zustände übereinander)
  const swapping = new WeakMap();
  async function swapText(el, text) {
    if (!el) return;
    if (el.textContent === text) return;
    if (!canAnimate || reduced() || el.offsetParent === null) { el.textContent = text; return; }
    const token = (swapping.get(el) || 0) + 1;
    swapping.set(el, token);
    await animate(el, [{ opacity: 1, filter: 'blur(0)' }, { opacity: 0, filter: 'blur(2px)' }], { duration: T.text * 0.8, easing: 'ease' });
    if (swapping.get(el) !== token) return;
    el.textContent = text;
    animate(el, [{ opacity: 0, filter: 'blur(2px)' }, { opacity: 1, filter: 'blur(0)' }], { duration: T.text, easing: EASE_OUT });
  }

  // Kurzer Puls als Bestätigung ("hat geklappt")
  const pulse = (el) => el && animate(el, [{ transform: 'scale(1)' }, { transform: 'scale(1.035)', offset: .4 }, { transform: 'scale(1)' }], { duration: 320, easing: EASE_IN_OUT });
  // Gummiband am Anschlag (kein Bounce, nur ein kurzes Nachgeben)
  const rubber = (el, dir) => el && animate(el, [{ transform: 'translateX(0)' }, { transform: `translateX(${6 * dir}px)`, offset: .35 }, { transform: 'translateX(0)' }], { duration: 260, easing: EASE_OUT });

  // Ein "Kissen" hinter dem aktiven Knopf, das zur neuen Position wandert und sich unterwegs 12 % dehnt
  function placePill(container, pill, target, doAnimate) {
    if (!pill || !target) return;
    const x = target.offsetLeft, y = target.offsetTop, w = target.offsetWidth, h = target.offsetHeight;
    const prev = container.dataset.pill ? JSON.parse(container.dataset.pill) : null;
    container.dataset.pill = JSON.stringify({ x, y, w, h });
    pill.style.width = `${w}px`;
    pill.style.height = `${h}px`;
    const to = `translate(${x}px, ${y}px)`;
    pill.style.transform = to;
    pill.classList.add('ready');
    if (!doAnimate || !prev || !prev.w || reduced() || !canAnimate || (prev.x === x && prev.y === y)) return;
    const horizontal = Math.abs(x - prev.x) >= Math.abs(y - prev.y);
    const scaleW = horizontal ? w / prev.w : 1, scaleH = horizontal ? 1 : h / prev.h;
    const stretch = horizontal ? `scale(1.12, 1)` : `scale(1, 1.12)`;
    const mid = `translate(${(x + prev.x) / 2}px, ${(y + prev.y) / 2}px) ${stretch}`;
    pill.animate([
      { transform: `translate(${prev.x}px, ${prev.y}px) scale(${1 / scaleW}, ${1 / scaleH})` },
      { transform: mid, offset: .5 },
      { transform: to },
    ], { duration: T.move, easing: EASE_IN_OUT });
  }

  // ---------- Formatierung ----------
  const LOCALE = 'de-AT';
  let currency = 'EUR';
  const money = (v, cur = currency) => {
    try {
      return new Intl.NumberFormat(LOCALE, { style: 'currency', currency: cur, maximumFractionDigits: 2 }).format(v);
    } catch {
      return `${v.toFixed(2)} ${cur}`;
    }
  };
  const pct = (ratio) => {
    const v = ratio * 100;
    const s = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: Math.abs(v) < 10 ? 1 : 0, minimumFractionDigits: 0 }).format(Math.abs(v));
    return `${v > 0.05 ? '+' : v < -0.05 ? '−' : '±'}${s}\u00a0%`;
  };
  const rtf = new Intl.RelativeTimeFormat('de', { numeric: 'auto' });
  const since = (ts) => {
    const s = Math.max(0, (Date.now() - ts) / 1000);
    if (s < 60) return 'gerade eben';
    if (s < 3600) return rtf.format(-Math.round(s / 60), 'minute');
    if (s < 86400) return rtf.format(-Math.round(s / 3600), 'hour');
    return rtf.format(-Math.round(s / 86400), 'day');
  };
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // ---------- Coins & Strategien in Alltagssprache ----------
  const COINS = {
    BTC: ['Bitcoin', '#F7931A'], XBT: ['Bitcoin', '#F7931A'], ETH: ['Ethereum', '#6F7CBA'],
    SOL: ['Solana', '#9A5BF0'], EUR: ['Euro', '#2FB894'], USDC: ['USD Coin', '#2775CA'],
    USDT: ['Tether', '#26A17B'], XRP: ['XRP', '#3A4B5C'], ADA: ['Cardano', '#2A71D0'],
    DOT: ['Polkadot', '#E6007A'], LINK: ['Chainlink', '#2A5ADA'], BNB: ['BNB', '#E0A800'],
    AVAX: ['Avalanche', '#E84142'], LTC: ['Litecoin', '#345D9D'], DOGE: ['Dogecoin', '#C2A633'],
  };
  const coinInfo = (sym) => COINS[sym] || [sym, '#8E86A8'];
  const baseOf = (pair) => String(pair).split('/')[0];

  // Klassennamen wie in user_data/strategies. Alle teilen Stop-Loss, Positionsgröße und Schutzregeln (BikoBase).
  const STRATEGIES = {
    EmaTrendStrategy: {
      name: 'Trendfolger',
      text: 'Kauft, wenn ein Coin klar nach oben läuft (kurze Durchschnittslinie über der langen, Kurs über dem 200er), und verkauft, wenn der Trend kippt.',
      who: 'Ruhig, wenige Trades, lässt Gewinne laufen.',
      tested: true,
    },
    BreakoutStrategy: {
      name: 'Ausbruch',
      text: 'Kauft, wenn ein Coin über sein Hoch der letzten 20 Kerzen steigt, und verkauft, wenn er unter das Tief der letzten 10 Kerzen fällt.',
      who: 'Für kräftige Bewegungen. Öfter mal ein Fehlausbruch, dafür große Treffer.',
      tested: false,
    },
    DipBuyStrategy: {
      name: 'Rücksetzer',
      text: 'Kauft kurze Durchhänger in einem Aufwärtstrend und verkauft nach der Erholung oder bei +8 % Gewinn.',
      who: 'Mehr kleine Gewinne, hält Trades nur kurz.',
      tested: false,
    },
  };
  const stratInfo = (name) => STRATEGIES[name] || { name: name || '–', text: 'Eigene Strategie.', who: '', tested: false };
  const EXCHANGES = { kraken: 'Kraken', binance: 'Binance' };
  const tfText = (tf) => {
    const m = /^(\d+)([mhdw])$/.exec(tf || '');
    if (!m) return '';
    const n = Number(m[1]);
    const unit = { m: ['Minute', 'Minuten'], h: ['Stunde', 'Stunden'], d: ['Tag', 'Tage'], w: ['Woche', 'Wochen'] }[m[2]];
    return n === 1 ? `jede ${unit[0]}` : `alle ${n} ${unit[1]}`;
  };

  const TF_MS = { m: 60e3, h: 3600e3, d: 86400e3, w: 7 * 86400e3 };
  function nextCheck(tf) {
    const m = /^(\d+)([mhdw])$/.exec(tf || '');
    if (!m) return '–';
    const step = Number(m[1]) * TF_MS[m[2]];
    const mins = Math.max(1, Math.ceil((Math.ceil(Date.now() / step) * step - Date.now()) / 60e3));
    if (mins < 60) return `${mins} Min.`;
    const h = Math.floor(mins / 60);
    return `${h} Std.${mins % 60 ? ` ${mins % 60} Min.` : ''}`;
  }

  // ---------- API ----------
  class AuthError extends Error {}
  class OfflineError extends Error {}

  const b64 = (s) => btoa(String.fromCharCode(...new TextEncoder().encode(s)));

  async function request(path, opts = {}) {
    let res;
    try {
      const url = path.startsWith('/settings-api/') ? path : API + path;
      res = await fetch(url, { cache: 'no-store', ...opts });
    } catch {
      throw new OfflineError('Netzwerk');
    }
    if (res.status === 401) throw new AuthError('401');
    if (res.status >= 502) throw new OfflineError(String(res.status));
    if (!res.ok) {
      let detail = '';
      try { detail = (await res.json()).detail || ''; } catch { /* kein JSON */ }
      const err = new Error(typeof detail === 'string' && detail ? detail : `HTTP ${res.status}`);
      err.status = res.status;
      throw err;
    }
    return res.json();
  }

  async function login(user, pass) {
    const data = await request('/token/login', {
      method: 'POST',
      headers: { Authorization: `Basic ${b64(`${user}:${pass}`)}` },
    });
    store.set('biko.access', data.access_token);
    store.set('biko.refresh', data.refresh_token);
  }

  async function refreshToken() {
    const refresh = store.get('biko.refresh');
    if (!refresh) throw new AuthError('kein Token');
    const data = await request('/token/refresh', { method: 'POST', headers: { Authorization: `Bearer ${refresh}` } });
    store.set('biko.access', data.access_token);
  }

  async function call(path, opts = {}, retry = true) {
    const token = store.get('biko.access');
    if (!token) throw new AuthError('kein Token');
    try {
      return await request(path, { ...opts, headers: { ...(opts.headers || {}), Authorization: `Bearer ${token}` } });
    } catch (e) {
      if (e instanceof AuthError && retry) {
        await refreshToken();
        return call(path, opts, false);
      }
      throw e;
    }
  }
  const get = (path) => call(path);
  const post = (path, body) => call(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });

  async function loadAll() {
    const [config, balance, status, trades] = await Promise.all([
      get('/show_config'),
      get('/balance'),
      get('/status'),
      get('/trades?limit=10').catch(() => ({ trades: [] })),
    ]);
    return { config, balance, status, trades: trades.trades || [] };
  }

  // ---------- Stimmung ----------
  function lastClosed(trades) {
    return trades
      .filter((t) => t.close_timestamp)
      .sort((a, b) => b.close_timestamp - a.close_timestamp)[0];
  }

  function moodFor(d) {
    const state = (d.config.state || 'running').toLowerCase();
    if (state !== 'running') return 'pause';
    const last = lastClosed(d.trades);
    if (last && Date.now() - last.close_timestamp < RECENT_CLOSE_MS) {
      return (last.profit_ratio ?? 0) >= 0 ? 'jubelt' : 'traurig';
    }
    return d.status.length > 0 ? 'tippt' : 'schlaeft';
  }

  const pick = (arr) => arr[Math.floor(Date.now() / 60000) % arr.length]; // wechselt einmal pro Minute

  function sayFor(mood, d) {
    const n = d ? d.status.length : 0;
    const last = d ? lastClosed(d.trades) : null;
    switch (mood) {
      case 'schlaeft': return pick(['Gerade ist nichts los … Nickerchen.', 'Kein guter Moment zum Kaufen. Ich warte.', 'Zzz … ich wach auf, wenn sich was tut.']);
      case 'tippt': return n === 1
        ? `Ich passe auf 1 Trade auf: ${coinInfo(baseOf(d.status[0].pair))[0]}.`
        : `Ich passe auf ${n} Trades auf.`;
      case 'jubelt': return last ? `Juhu! ${coinInfo(baseOf(last.pair))[0]} mit ${pct(last.profit_ratio)} verkauft.` : 'Juhu!';
      case 'traurig': return last ? `Schade, ${coinInfo(baseOf(last.pair))[0]} mit ${pct(last.profit_ratio)} verkauft. Gehört dazu.` : 'Schade …';
      case 'pause': return 'Ich mache Pause und kaufe nichts Neues.';
      case 'offline': return 'Hm, ich erreiche den Bot gerade nicht.';
      case 'winkt': return 'Hallo! Schön, dass du da bist.';
      default: return 'Ich schau kurz nach …';
    }
  }

  // Sprechblase: groß in der Übersicht, klein in den anderen Ansichten
  function say(text) {
    swapText($('bubble'), text);
    swapText($('mini-bubble'), text);
  }

  // ---------- Ansichten ----------
  const VIEWS = ['home', 'bot', 'trades', 'konto', 'einstellungen'];
  let currentView = VIEWS.includes(location.hash.slice(1)) ? location.hash.slice(1) : 'home';
  const viewEl = (id) => $(`view-${id}`);
  const navBtns = [...document.querySelectorAll('.nav-btn')];
  const rail = $('rail');
  const railPill = rail.querySelector('.rail-pill');

  // Reihenfolge für den versetzten Eingang (30 ms pro Element)
  function indexStagger(view) {
    view.querySelectorAll('.row, .tile, .set-block, .qcard, .panel > h2').forEach((el, i) => el.style.setProperty('--i', String(Math.min(i, 12))));
  }

  let staggerTimer = null;
  function showView(id, { animateIt = true, fromHash = false } = {}) {
    if (!VIEWS.includes(id)) id = 'home';
    const prevId = currentView;
    currentView = id;
    navBtns.forEach((b) => { if (b.getAttribute('aria-current') === 'page') b.removeAttribute('aria-current'); });
    const btn = navBtns.find((b) => b.dataset.view === id);
    if (btn) btn.setAttribute('aria-current', 'page');
    placePill(rail, railPill, btn, animateIt);
    if (!fromHash) history.replaceState(null, '', `#${id}`);
    $('mini').hidden = id === 'home' || $('views').hidden;
    if (prevId === id && !viewEl(id).hidden) return;

    const next = viewEl(id);
    indexStagger(next);
    next.hidden = false;
    if (id === 'einstellungen') placeSegPills(false); // Kissen brauchen sichtbare Maße
    VIEWS.forEach((v) => { if (v !== id && v !== prevId) viewEl(v).hidden = true; });
    window.scrollTo(0, 0);
    const prev = viewEl(prevId);
    if (!animateIt || prev === next) {
      if (prev !== next) prev.hidden = true;
      return;
    }
    // Alte und neue Ansicht überlappen kurz: alte blendet aus (kürzer), neue kommt von unten (ease-out)
    $('views').classList.add('switching');
    prev.classList.add('leaving');
    animate(prev, [{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateY(-6px)' }], { duration: T.exit, easing: 'ease' })
      .then(() => { if (currentView !== prevId) prev.hidden = true; prev.classList.remove('leaving'); });
    animate(next, [{ opacity: 0, transform: 'translateY(10px)' }, { opacity: 1, transform: 'none' }], { duration: T.enter, easing: EASE_OUT })
      .then(() => $('views').classList.remove('switching'));
    clearTimeout(staggerTimer);
    VIEWS.forEach((v) => viewEl(v).classList.remove('stagger'));
    next.classList.add('stagger');
    staggerTimer = setTimeout(() => next.classList.remove('stagger'), 900);
  }

  navBtns.forEach((b) => b.addEventListener('click', () => showView(b.dataset.view)));
  document.addEventListener('click', (ev) => {
    const go = ev.target.closest('[data-go]');
    if (go) showView(go.dataset.go);
  });
  window.addEventListener('hashchange', () => showView(location.hash.slice(1) || 'home', { fromHash: true }));
  if (window.ResizeObserver) {
    new ResizeObserver(() => {
      const btn = navBtns.find((b) => b.dataset.view === currentView);
      if (!rail.hidden) placePill(rail, railPill, btn, false);
    }).observe(rail);
  }

  // ---------- Darstellung ----------
  function showLogin(message) {
    $('views').hidden = true;
    $('mini').hidden = true;
    rail.hidden = true;
    $('login').hidden = false;
    $('chips').innerHTML = '';
    Biko.setMood('winkt');
    $('bubble').textContent = sayFor('winkt');
    const err = $('login-error');
    err.hidden = !message;
    err.textContent = message || '';
  }

  function showApp() {
    const wasHidden = $('views').hidden;
    $('login').hidden = true;
    $('views').hidden = false;
    rail.hidden = false;
    if (wasHidden) {
      showView(currentView, { animateIt: false });
      // Erster Eindruck: einmal weich einblenden
      animate($('views'), [{ opacity: 0, transform: 'translateY(8px)' }, { opacity: 1, transform: 'none' }], { duration: T.enter, easing: EASE_OUT });
      indexStagger(viewEl(currentView));
      viewEl(currentView).classList.add('stagger');
      clearTimeout(staggerTimer);
      staggerTimer = setTimeout(() => viewEl(currentView).classList.remove('stagger'), 900);
    }
  }

  function render(d) {
    showApp();

    const c = d.config;
    currency = c.stake_currency || 'EUR';
    const mood = DEMO && demoMood ? demoMood : moodFor(d);
    Biko.setMood(mood);
    say(sayFor(mood, d));

    // Kopf: Börse + Modus
    const ex = EXCHANGES[(c.exchange || '').toLowerCase()] || c.exchange || '';
    $('chips').innerHTML =
      (ex ? `<span class="chip">${esc(ex)}</span>` : '') +
      (c.dry_run ? '<span class="chip play">Spielgeld</span>' : '<span class="chip real">Echtgeld</span>');

    // Guthaben
    const b = d.balance;
    const total = b.total_bot ?? b.total ?? 0;
    swapText($('total'), money(total));
    const ratio = b.starting_capital_ratio;
    const delta = $('delta');
    if (typeof ratio === 'number' && b.starting_capital) {
      const diff = total - b.starting_capital;
      delta.className = `delta ${ratio > 0.0005 ? 'up' : ratio < -0.0005 ? 'down' : 'flat'}`;
      delta.textContent = `${pct(ratio)} (${diff >= 0 ? '+' : '−'}${money(Math.abs(diff))}) seit Start`;
      delta.hidden = false;
    } else {
      delta.hidden = true;
    }

    // Status (Kacheln in "Bot" und Schnellzugriff in der Übersicht)
    const state = (c.state || 'running').toLowerCase();
    const stateText = { running: 'Aktiv', paused: 'Kauft nichts', stopped: 'Gestoppt' }[state] || state;
    swapText($('t-state'), stateText);
    swapText($('q-state'), stateText);
    $('t-hub').className = `tile-hub ${state === 'running' ? 'running' : 'paused'}`;
    const next = state === 'running' ? nextCheck(c.timeframe) : '–';
    swapText($('t-next'), next);
    $('q-next').textContent = state === 'running' ? `Nächster Check in ${next}` : 'Pause: kauft nichts Neues';
    renderRiskTile(c);
    const tr = $('toggle-run');
    tr.hidden = false;
    tr.dataset.action = state === 'running' ? 'pause' : 'start';
    swapText(tr.querySelector('.swap'), state === 'running' ? 'Pause: nichts Neues kaufen' : 'Weiter handeln');
    tr.className = `action ${state === 'running' ? '' : 'go'}`;
    const tp = $('t-profit');
    if (typeof ratio === 'number' && b.starting_capital) {
      swapText(tp, pct(ratio));
      tp.className = `t-value ${ratio > 0.0005 ? 'up' : ratio < -0.0005 ? 'down' : ''}`;
    } else {
      tp.textContent = '–';
      tp.className = 't-value';
    }

    // Trades: offene zuerst, dann die letzten verkauften
    const closed = d.trades.filter((t) => t.close_timestamp).sort((x, y) => y.close_timestamp - x.close_timestamp);
    const rows = [
      ...d.status.map((t) => ({ t, open: true, ts: t.open_timestamp })),
      ...closed.slice(0, 10).map((t) => ({ t, open: false, ts: t.close_timestamp })),
    ];
    const tradesEl = $('trades');
    if (!rows.length) {
      tradesEl.innerHTML = '<li class="empty">Noch keine Trades. Biko wartet auf ein gutes Signal.</li>';
    } else {
      tradesEl.innerHTML = rows.map(({ t, open, ts }) => {
        const [base, quote = currency] = String(t.pair).split('/');
        const color = coinInfo(base)[1];
        const r = t.profit_ratio ?? 0;
        const abs = t.profit_abs;
        const amount = open ? money(t.stake_amount ?? 0) : (typeof abs === 'number' ? `${abs >= 0 ? '+' : '−'}${money(Math.abs(abs))}` : pct(r));
        const stateCls = open ? 'open' : r >= 0 ? 'win' : 'loss';
        const stateText2 = open ? `Offen · ${pct(r)}` : `Verkauft · ${pct(r)}`;
        return `<li class="row">
          <div class="coin" data-color="${esc(color)}">${esc(base.slice(0, 4))}</div>
          <div class="main">
            <div class="pair">${esc(base)}<span class="arrow"> → </span>${esc(quote)}</div>
            <div class="state ${stateCls}">${esc(stateText2)}</div>
          </div>
          <div class="val"><div class="amount ${open ? '' : r >= 0 ? 'up' : 'down'}">${amount}</div><div class="sub">${esc(since(ts))}</div>
            ${open && t.trade_id != null ? `<button type="button" class="sell" data-trade="${esc(t.trade_id)}" data-name="${esc(coinInfo(base)[0])}" data-ratio="${r}">Verkaufen</button>` : ''}</div>
        </li>`;
      }).join('');
    }
    const nOpen = d.status.length;
    const qt = $('q-trades');
    swapText(qt, nOpen ? `${nOpen} offen` : 'Keine offen');
    const last = closed[0];
    if (last) {
      const lr = last.profit_ratio ?? 0;
      $('q-last').textContent = `Zuletzt ${coinInfo(baseOf(last.pair))[0]} ${pct(lr)}`;
      qt.className = `q-value ${nOpen ? '' : ''}`;
    } else {
      $('q-last').textContent = 'Noch nichts verkauft';
    }

    // Coins im Konto
    const coins = (b.currencies || [])
      .map((x) => ({ sym: x.currency, value: x.est_stake_bot ?? x.est_stake ?? 0, amount: x.balance ?? x.free ?? 0 }))
      .filter((x) => x.value > 0.01)
      .sort((a, b2) => b2.value - a.value);
    const sum = coins.reduce((s, x) => s + x.value, 0) || 1;
    $('alloc').innerHTML = coins.map((x) => `<span data-color="${esc(coinInfo(x.sym)[1])}" data-share="${(x.value / sum) * 100}"></span>`).join('');
    $('coins').innerHTML = coins.length ? coins.map((x) => {
      const [name, color] = coinInfo(x.sym);
      const amount = x.sym === currency ? '' : `${new Intl.NumberFormat(LOCALE, { maximumSignificantDigits: 4 }).format(x.amount)} ${esc(x.sym)}`;
      return `<li class="row">
        <div class="coin" data-color="${esc(color)}">${esc(x.sym.slice(0, 4))}</div>
        <div class="main"><div class="name">${esc(name)}</div><div class="sub">${amount || 'nicht investiert'}</div></div>
        <div class="val">${money(x.value)}<div class="sub">${Math.round((x.value / sum) * 100)} %</div></div>
      </li>`;
    }).join('') : '<li class="empty">Noch keine Coins.</li>';

    // Farben per CSSOM setzen (CSP erlaubt keine Inline-Styles)
    document.querySelectorAll('[data-color]').forEach((el) => el.style.setProperty('--coin', el.dataset.color));
    document.querySelectorAll('[data-share]').forEach((el) => { el.style.width = `${el.dataset.share}%`; });

    // Strategie
    const s = stratInfo(c.strategy);
    swapText($('strategy-name'), s.name);
    $('strategy-text').textContent = `${s.text} ${s.who}`;
    const every = tfText(c.timeframe);
    const sl = Math.abs(Number(c.stoploss) || 0);
    $('strategy-facts').innerHTML = [
      every ? ['Schaut', every] : null,
      sl ? ['Stopp', `−${new Intl.NumberFormat(LOCALE).format(sl * 100)} %`] : null,
      ['Max. Trades', c.max_open_trades ?? '–'],
      [s.tested ? 'Im Backtest geprüft' : 'Noch nicht im Backtest geprüft', ''],
    ].filter(Boolean).map(([k, v]) => `<span class="fact">${esc(k)}${v !== '' ? `: <b>${esc(v)}</b>` : ''}</span>`).join('');

    // Fakten im Konto
    const facts = [
      ['Börse', ex || '–'],
      ['Modus', c.dry_run ? 'Spielgeld' : 'Echtgeld'],
      ['Startkapital', b.starting_capital ? money(b.starting_capital) : '–'],
    ];
    $('facts').innerHTML = facts.map(([k, v]) => `<span class="fact">${esc(k)}: <b>${esc(v)}</b></span>`).join('');

    if (!settings.loaded && !settings.loading) loadSettings();
    renderSettingsHints();
    VIEWS.forEach((v) => indexStagger(viewEl(v)));

    $('updated').textContent = DEMO ? 'Demo mit Beispieldaten' : `Aktualisiert ${new Date().toLocaleTimeString(LOCALE, { hour: '2-digit', minute: '2-digit' })}`;
  }

  // Risiko-Kachel: eingestelltes Risiko pro Trade (aus den Einstellungen), sonst nur der Stop
  function renderRiskTile(c) {
    const sl = Math.abs(Number((c || {}).stoploss) || 0);
    const stopText = sl ? `Stopp bei −${new Intl.NumberFormat(LOCALE).format(sl * 100)} %` : '';
    const r = settings.saved && settings.saved.risk_per_trade;
    if (r) {
      swapText($('t-risk'), `${riskLabel(r)} pro Trade`);
      $('t-risk-sub').textContent = stopText;
    } else {
      swapText($('t-risk'), !sl ? '–' : sl <= 0.05 ? 'Niedrig' : sl <= 0.1 ? 'Mittel' : 'Hoch');
      $('t-risk-sub').textContent = stopText;
    }
  }

  function renderOffline() {
    Biko.setMood('offline');
    swapText($('t-state'), 'Offline');
    swapText($('q-state'), 'Offline');
    $('q-next').textContent = 'Keine Verbindung';
    $('t-hub').className = 'tile-hub offline';
    say(sayFor('offline'));
    $('updated').textContent = 'Keine Verbindung, versuche es weiter …';
  }

  // ---------- Ablauf ----------
  let timer = null;
  let lastData = null;

  async function tick() {
    clearTimeout(timer);
    try {
      lastData = DEMO ? demoData() : await loadAll();
      render(lastData);
    } catch (e) {
      if (e instanceof AuthError) {
        store.del('biko.access');
        store.del('biko.refresh');
        showLogin(lastData ? 'Bitte neu anmelden.' : '');
        lastData = null;
        return; // kein Polling ohne Login
      }
      if (!lastData) showApp();
      renderOffline();
    }
    timer = setTimeout(tick, POLL_MS);
  }

  $('login-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const f = ev.target;
    const btn = f.querySelector('button');
    btn.disabled = true;
    Biko.setMood('laedt');
    try {
      await login(f.user.value.trim(), f.pass.value);
      f.pass.value = '';
      await tick();
    } catch (e) {
      if (e instanceof AuthError) showLogin('Benutzer oder Passwort stimmt nicht.');
      else if (e instanceof OfflineError) showLogin('Der Bot antwortet nicht. Läuft er (docker compose ps)?');
      else showLogin('Anmelden hat nicht geklappt.');
    } finally {
      btn.disabled = false;
    }
  });

  $('logout').addEventListener('click', () => {
    settings.loaded = false;
    settings.saved = settings.draft = null;
    $('set-form').hidden = true;
    $('set-loading').hidden = false;
    store.del('biko.access');
    store.del('biko.refresh');
    clearTimeout(timer);
    lastData = null;
    showLogin();
  });

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && (DEMO || store.get('biko.access'))) tick();
    else clearTimeout(timer);
  });

  // ---------- Sicherheitsabfrage (Modal: startet bei 0.95, bleibt mittig, schließt schneller) ----------
  const dlg = $('confirm');
  let dlgResolve = null;
  function closeDialog(value) {
    if (!dlg.open || !dlgResolve) return;
    const done = dlgResolve;
    dlgResolve = null;
    dlg.classList.add('closing');
    animate(dlg, [{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'scale(0.97)' }], { duration: T.exit, easing: 'ease' })
      .then(() => { dlg.close(); dlg.classList.remove('closing'); done(value === 'yes'); });
  }
  dlg.addEventListener('cancel', (ev) => { ev.preventDefault(); closeDialog('no'); });
  dlg.addEventListener('click', (ev) => {
    const btn = ev.target.closest('[data-answer]');
    if (btn) closeDialog(btn.dataset.answer);
    else if (ev.target === dlg) closeDialog('no'); // Tipp daneben = Abbrechen
  });
  function ask(title, text, okLabel) {
    $('confirm-title').textContent = title;
    $('confirm-text').textContent = text;
    $('confirm-ok').textContent = okLabel;
    return new Promise((resolve) => {
      dlgResolve = resolve;
      dlg.showModal();
      animate(dlg, [{ opacity: 0, transform: 'scale(0.95)' }, { opacity: 1, transform: 'none' }], { duration: T.enter, easing: EASE_OUT });
    });
  }

  // ---------- Eingreifen: Pause/Weiter und Trade verkaufen ----------
  async function act(fn, okText, okEl) {
    try {
      if (DEMO) { await fn(true); demoMood = null; } else await fn(false);
      say(okText);
      pulse(okEl);
      setTimeout(tick, 1200);
    } catch (e) {
      if (e instanceof AuthError) { showLogin('Bitte neu anmelden.'); return; }
      say(`Hat nicht geklappt (${e.message}). Versuch es gleich nochmal.`);
    }
  }

  $('toggle-run').addEventListener('click', async (ev) => {
    const btn = ev.currentTarget;
    if (btn.dataset.action === 'pause') {
      const ok = await ask('Pause machen?', 'Biko kauft dann nichts Neues mehr. Offene Trades laufen normal weiter und werden wie gewohnt verkauft.', 'Ja, Pause');
      if (!ok) return;
      btn.disabled = true;
      await act(async (demo) => {
        if (demo) { demoPaused = true; return; }
        try { await post('/stopentry'); } catch (e) { if (e.status === 404) await post('/pause'); else throw e; }
      }, 'Okay, ich kaufe erst mal nichts Neues.', btn);
    } else {
      const ok = await ask('Weiter handeln?', 'Biko kauft und verkauft dann wieder selbst nach seiner Strategie.', 'Ja, weiter');
      if (!ok) return;
      btn.disabled = true;
      await act(async (demo) => {
        if (demo) { demoPaused = false; return; }
        await post('/start');
      }, 'Los geht\'s, ich passe wieder auf!', btn);
    }
    btn.disabled = false;
  });

  $('trades').addEventListener('click', async (ev) => {
    const btn = ev.target.closest('button.sell');
    if (!btn) return;
    const { trade, name } = btn.dataset;
    const r = Number(btn.dataset.ratio) || 0;
    const ok = await ask(`${name} jetzt verkaufen?`,
      `Aktuell ${pct(r)}. Biko verkauft sofort zum aktuellen Preis, das lässt sich nicht rückgängig machen.`, 'Ja, verkaufen');
    if (!ok) return;
    btn.disabled = true;
    btn.textContent = 'Verkaufe …';
    await act(async (demo) => {
      if (demo) { demoSold.add(Number(trade)); return; }
      await post('/forceexit', { tradeid: String(trade) });
    }, `Mach ich! ${name} wird verkauft.`);
  });

  // ---------- Einstellungen: Strategie, Coins, Takt, Risiko, gleichzeitige Trades ----------
  const settings = { loaded: false, loading: false, saved: null, draft: null, options: null, stoploss: 0.05 };
  const TF_INFO = {
    '15m': ['15 Min', 'Sehr schnell: viele Trades, aber die Gebühren fressen viel vom Gewinn.'],
    '1h': ['1 Std', 'Schneller: mehr Trades als mit 4 Std, etwas mehr Gebühren.'],
    '4h': ['4 Std', 'Ruhig: wenige Trades, dafür größere Trends. So wurde der Trendfolger getestet.'],
  };
  const riskLabel = (r) => `${new Intl.NumberFormat(LOCALE).format(r * 100)} %`;
  const COST_BUFFER = 0.01; // Gebühren + Slippage, wie cost_buffer in BikoBase
  const costPerTrade = () => Math.abs(settings.stoploss || 0.05) + COST_BUFFER;

  async function loadSettings() {
    settings.loading = true;
    try {
      const data = DEMO ? demoSettings() : await get('/settings-api/settings');
      settings.options = data.options;
      if (!settings.options.strategies) settings.options.strategies = Object.keys(STRATEGIES);
      if (typeof data.stoploss === 'number') settings.stoploss = Math.abs(data.stoploss);
      if (!data.settings.strategy) data.settings.strategy = (lastData && lastData.config.strategy) || 'EmaTrendStrategy';
      settings.saved = data.settings;
      settings.draft = JSON.parse(JSON.stringify(data.settings));
      settings.loaded = true;
      $('set-loading').hidden = true;
      $('set-form').hidden = false;
      renderSettings(false);
      if (lastData) renderRiskTile(lastData.config);
    } catch (e) {
      if (e instanceof AuthError) return;
      $('set-loading').textContent = 'Einstellungen gerade nicht erreichbar. Läuft der Dienst biko-settings?';
    } finally {
      settings.loading = false;
    }
  }

  const same = (x, y) => JSON.stringify(x) === JSON.stringify(y);

  function renderSeg(seg, items, selected, attr, label, doAnimate) {
    let pill = seg.querySelector('.seg-pill');
    const html = items.map((v) => `<button type="button" role="radio" aria-checked="${selected === v}" class="${selected === v ? 'on' : ''}" ${attr}="${esc(v)}">${esc(label(v))}</button>`).join('');
    if (!pill) {
      seg.innerHTML = `<span class="seg-pill" aria-hidden="true"></span>${html}`;
      pill = seg.querySelector('.seg-pill');
    } else {
      seg.querySelectorAll('button').forEach((b) => b.remove());
      pill.insertAdjacentHTML('afterend', html);
    }
    placePill(seg, pill, seg.querySelector('button.on'), doAnimate);
  }

  function placeSegPills(doAnimate) {
    document.querySelectorAll('.seg').forEach((seg) => placePill(seg, seg.querySelector('.seg-pill'), seg.querySelector('button.on'), doAnimate));
  }

  function renderSettings(doAnimate = true) {
    const { draft, options } = settings;
    if (!draft) return;
    $('set-strategy').innerHTML = options.strategies.map((k) => {
      const s = stratInfo(k);
      const on = draft.strategy === k;
      return `<button type="button" role="radio" aria-checked="${on}" class="scard ${on ? 'on' : ''}" data-strategy="${esc(k)}">
        <span class="s-head"><span class="s-name">${esc(s.name)}</span>
          <span class="s-tag ${s.tested ? 'ok' : ''}">${s.tested ? 'getestet' : 'neu'}</span></span>
        <span class="s-check" aria-hidden="true"></span>
        <span class="s-text">${esc(s.text)} ${esc(s.who)}</span>
      </button>`;
    }).join('');
    $('set-coins').innerHTML = options.coins.map((c) => {
      const on = draft.coins.includes(c);
      return `<button type="button" class="pick ${on ? 'on' : ''}" data-coin="${esc(c)}" aria-pressed="${on}">
        <span class="dot" data-color="${esc(coinInfo(c)[1])}"></span>${esc(c)}</button>`;
    }).join('');
    renderSeg($('set-tf'), options.timeframes, draft.timeframe, 'data-tf', (t) => (TF_INFO[t] || [t])[0], doAnimate);
    renderSeg($('set-risk'), options.risks, draft.risk_per_trade, 'data-risk', riskLabel, doAnimate);
    $('set-mot').textContent = draft.max_open_trades;
    $('set-mot-minus').setAttribute('aria-disabled', String(draft.max_open_trades <= options.max_open_trades[0]));
    $('set-mot-plus').setAttribute('aria-disabled', String(draft.max_open_trades >= options.max_open_trades[1]));
    document.querySelectorAll('#set-coins [data-color]').forEach((el) => el.style.setProperty('--coin', el.dataset.color));
    renderSettingsHints();
  }

  function renderSettingsHints() {
    const { draft } = settings;
    if (!draft) return;
    const total = lastData ? (lastData.balance.total_bot ?? lastData.balance.total ?? 0) : 0;
    const cost = costPerTrade();
    $('set-tf-hint').textContent = (TF_INFO[draft.timeframe] || ['', ''])[1];
    const r = draft.risk_per_trade;
    $('set-risk-hint').textContent = total
      ? `Pro Trade ca. ${money(total * r / cost)} Einsatz. Greift der Stopp, sind ca. ${money(total * r)} weg.`
      : `Greift der Stopp, ist ${riskLabel(r)} vom Konto weg.`;
    const share = Math.min(100, Math.round(draft.max_open_trades * r / cost * 100));
    $('set-mot-hint').textContent = share >= 100
      ? `Bis zu ${draft.max_open_trades} Trades: dann kann fast das ganze Konto investiert sein.`
      : `Bis zu ${draft.max_open_trades} Trades gleichzeitig, dann sind ca. ${share} % vom Konto investiert.`;
    const btn = $('set-save');
    const dirty = !same(draft, settings.saved);
    btn.disabled = !dirty;
    if (dirty) btn.classList.remove('ok');
    swapText(btn.querySelector('.swap'), dirty ? 'Speichern' : 'Gespeichert');
  }

  $('set-strategy').addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-strategy]');
    if (b) { settings.draft.strategy = b.dataset.strategy; renderSettings(); }
  });
  $('set-coins').addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-coin]');
    if (!b) return;
    const c = b.dataset.coin;
    const list = settings.draft.coins;
    if (list.includes(c)) {
      if (list.length === 1) { say('Mindestens ein Coin muss bleiben.'); rubber(b, 1); return; }
      settings.draft.coins = list.filter((x) => x !== c);
    } else {
      settings.draft.coins = settings.options.coins.filter((x) => x === c || list.includes(x));
    }
    renderSettings();
  });
  $('set-tf').addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-tf]');
    if (b) { settings.draft.timeframe = b.dataset.tf; renderSettings(); }
  });
  $('set-risk').addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-risk]');
    if (b) { settings.draft.risk_per_trade = Number(b.dataset.risk); renderSettings(); }
  });
  $('set-mot-minus').addEventListener('click', (ev) => {
    if (settings.draft.max_open_trades <= settings.options.max_open_trades[0]) { rubber($('set-mot'), -1); return; }
    settings.draft.max_open_trades -= 1; renderSettings();
  });
  $('set-mot-plus').addEventListener('click', (ev) => {
    if (settings.draft.max_open_trades >= settings.options.max_open_trades[1]) { rubber($('set-mot'), 1); return; }
    settings.draft.max_open_trades += 1; renderSettings();
  });

  $('set-save').addEventListener('click', async () => {
    const d = settings.draft;
    const stratChanged = settings.saved && d.strategy !== settings.saved.strategy;
    const text = `${stratInfo(d.strategy).name} · Coins: ${d.coins.join(', ')} · Takt: ${(TF_INFO[d.timeframe] || [d.timeframe])[0]} · `
      + `Risiko: ${riskLabel(d.risk_per_trade)} pro Trade · bis zu ${d.max_open_trades} Trades. `
      + 'Biko startet dafür kurz neu. Offene Trades bleiben offen'
      + (stratChanged ? ' und werden ab jetzt nach den Regeln der neuen Strategie verkauft (der Stop-Loss bleibt).' : '.');
    const ok = await ask('Einstellungen speichern?', text, 'Ja, speichern');
    if (!ok) return;
    const btn = $('set-save');
    btn.disabled = true;
    swapText(btn.querySelector('.swap'), 'Speichere …');
    try {
      if (DEMO) {
        demoSettingsSaved = JSON.parse(JSON.stringify(d));
      } else {
        await post('/settings-api/settings', d);
      }
      settings.saved = JSON.parse(JSON.stringify(d));
      Biko.setMood('laedt');
      say('Gespeichert! Ich lade kurz neu …');
      btn.classList.add('ok');
      pulse(btn);
      if (lastData) renderRiskTile(lastData.config);
      clearTimeout(timer);
      timer = setTimeout(tick, DEMO ? 1500 : 8000);
    } catch (e) {
      if (e instanceof AuthError) { showLogin('Bitte neu anmelden.'); return; }
      say(`Speichern hat nicht geklappt: ${e.message}`);
    }
    renderSettingsHints();
  });

  // ---------- Demo (?demo oder ?demo=tippt): Beispieldaten ohne Bot ----------
  let demoSettingsSaved = { strategy: 'EmaTrendStrategy', coins: ['BTC', 'ETH', 'SOL'], timeframe: '4h', risk_per_trade: 0.01, max_open_trades: 3 };
  function demoSettings() {
    return {
      settings: JSON.parse(JSON.stringify(demoSettingsSaved)),
      options: {
        strategies: ['EmaTrendStrategy', 'BreakoutStrategy', 'DipBuyStrategy'],
        coins: ['BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'LINK', 'DOT', 'AVAX', 'LTC', 'DOGE'],
        timeframes: ['15m', '1h', '4h'], risks: [0.005, 0.01, 0.02, 0.03], max_open_trades: [1, 6],
      },
      stoploss: -0.05,
    };
  }
  let demoPaused = false;
  const demoSold = new Set();
  const DEMO_MOODS = ['tippt', 'schlaeft', 'jubelt', 'traurig', 'pause', 'offline'];
  let demoMood = DEMO_MOODS.includes(params.get('demo')) ? params.get('demo') : null;

  function demoData() {
    const now = Date.now();
    const h = 3600e3;
    const mood = demoMood || 'tippt';
    const open = mood === 'tippt' ? [
      { trade_id: 7, pair: 'BTC/EUR', profit_ratio: 0.021, stake_amount: 83.2, open_timestamp: now - 26 * h },
      { trade_id: 8, pair: 'SOL/EUR', profit_ratio: -0.008, stake_amount: 82.5, open_timestamp: now - 3 * h },
    ].filter((t) => !demoSold.has(t.trade_id)) : [];
    const recent = ['jubelt', 'traurig'].includes(mood);
    const closed = [
      { pair: 'ETH/EUR', profit_ratio: mood === 'traurig' ? -0.031 : 0.064, profit_abs: mood === 'traurig' ? -2.58 : 5.31, close_timestamp: now - (recent ? 5 * 60e3 : 3 * 86400e3) },
      { pair: 'BTC/EUR', profit_ratio: -0.012, profit_abs: -0.98, close_timestamp: now - 6 * 86400e3 },
    ];
    const coins = [{ currency: 'EUR', balance: open.length ? 352.1 : 518.8, est_stake: open.length ? 352.1 : 518.8 }];
    if (open.length) coins.push({ currency: 'BTC', balance: 0.00089, est_stake: 84.9 }, { currency: 'SOL', balance: 0.52, est_stake: 81.8 });
    const total = coins.reduce((s, x) => s + x.est_stake, 0);
    return {
      config: {
        exchange: 'kraken', dry_run: true, strategy: demoSettingsSaved.strategy, timeframe: demoSettingsSaved.timeframe, stake_currency: 'EUR',
        stoploss: -0.05, max_open_trades: demoSettingsSaved.max_open_trades, state: mood === 'pause' || demoPaused ? 'paused' : 'running',
      },
      balance: { total, starting_capital: 500, starting_capital_ratio: total / 500 - 1, currencies: coins },
      status: open,
      trades: closed,
    };
  }

  // ---------- Start ----------
  Biko.mount($('biko'));
  Biko.mount($('biko-mini'), { decorative: true });
  Biko.mount($('biko-login'), { decorative: true });
  if (DEMO) {
    // Tippen auf Biko wechselt die Stimmung
    const cycle = () => {
      demoMood = DEMO_MOODS[(DEMO_MOODS.indexOf(demoMood || 'tippt') + 1) % DEMO_MOODS.length];
      if (demoMood === 'offline') { renderOffline(); return; }
      lastData = demoData();
      render(lastData);
    };
    $('biko').addEventListener('click', cycle);
    $('biko-mini').addEventListener('click', cycle);
    if (demoMood === 'offline') { tick().then(renderOffline); } else { tick(); }
  } else if (store.get('biko.access')) {
    tick();
  } else {
    showLogin();
  }
})();
