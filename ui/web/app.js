// Biko App: liest nur die REST-API des eigenen Freqtrade-Bots (über /api/v1, vom nginx weitergeleitet).
// Keine Schreibaktionen, kein Tracking, keine externen Server.
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

  // ---------- Formatierung ----------
  const LOCALE = 'de-AT';
  let currency = 'EUR';
  const money = (v, cur = currency) => {
    try {
      return new Intl.NumberFormat(LOCALE, { style: 'currency', currency: cur, maximumFractionDigits: Math.abs(v) < 10 ? 2 : 2 }).format(v);
    } catch {
      return `${v.toFixed(2)} ${cur}`;
    }
  };
  const pct = (ratio) => {
    const v = ratio * 100;
    const s = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: Math.abs(v) < 10 ? 1 : 0, minimumFractionDigits: 0 }).format(Math.abs(v));
    return `${v > 0.05 ? '+' : v < -0.05 ? '−' : '±'}${s} %`;
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
  };
  const coinInfo = (sym) => COINS[sym] || [sym, '#8E86A8'];
  const baseOf = (pair) => String(pair).split('/')[0];

  const STRATEGIES = {
    EmaTrendStrategy: {
      name: 'Trendfolger',
      text: 'Kauft, wenn ein Coin klar nach oben läuft, und verkauft, wenn der Trend kippt. Fällt der Kurs 5 % unter den Kaufpreis, wird automatisch verkauft.',
    },
  };
  const EXCHANGES = { kraken: 'Kraken', binance: 'Binance' };
  const tfText = (tf) => {
    const m = /^(\d+)([mhdw])$/.exec(tf || '');
    if (!m) return '';
    const n = Number(m[1]);
    const unit = { m: ['Minute', 'Minuten'], h: ['Stunde', 'Stunden'], d: ['Tag', 'Tage'], w: ['Woche', 'Wochen'] }[m[2]];
    return n === 1 ? `jede ${unit[0]}` : `alle ${n} ${unit[1]}`;
  };

  // ---------- API ----------
  class AuthError extends Error {}
  class OfflineError extends Error {}

  const b64 = (s) => btoa(String.fromCharCode(...new TextEncoder().encode(s)));

  async function request(path, opts = {}) {
    let res;
    try {
      res = await fetch(API + path, { cache: 'no-store', ...opts });
    } catch {
      throw new OfflineError('Netzwerk');
    }
    if (res.status === 401) throw new AuthError('401');
    if (res.status >= 502) throw new OfflineError(String(res.status));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
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

  async function get(path, retry = true) {
    const token = store.get('biko.access');
    if (!token) throw new AuthError('kein Token');
    try {
      return await request(path, { headers: { Authorization: `Bearer ${token}` } });
    } catch (e) {
      if (e instanceof AuthError && retry) {
        await refreshToken();
        return get(path, false);
      }
      throw e;
    }
  }

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

  // ---------- Darstellung ----------
  function showLogin(message) {
    $('dash').hidden = true;
    $('login').hidden = false;
    $('chips').innerHTML = '';
    Biko.setMood('winkt');
    $('bubble').textContent = sayFor('winkt');
    const err = $('login-error');
    err.hidden = !message;
    err.textContent = message || '';
  }

  function render(d) {
    $('login').hidden = true;
    $('dash').hidden = false;

    const c = d.config;
    currency = c.stake_currency || 'EUR';
    const mood = DEMO && demoMood ? demoMood : moodFor(d);
    Biko.setMood(mood);
    $('bubble').textContent = sayFor(mood, d);

    // Kopf: Börse + Modus
    const ex = EXCHANGES[(c.exchange || '').toLowerCase()] || c.exchange || '';
    $('chips').innerHTML =
      (ex ? `<span class="chip">${esc(ex)}</span>` : '') +
      (c.dry_run ? '<span class="chip play">Spielgeld</span>' : '<span class="chip real">Echtgeld</span>');

    // Guthaben
    const b = d.balance;
    const total = b.total_bot ?? b.total ?? 0;
    $('total').textContent = money(total);
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

    // Offene Trades
    const tradesEl = $('trades');
    if (!d.status.length) {
      tradesEl.innerHTML = '<li class="empty">Gerade kein offener Trade. Biko wartet auf ein gutes Signal.</li>';
    } else {
      tradesEl.innerHTML = d.status.map((t) => {
        const sym = baseOf(t.pair);
        const [name, color] = coinInfo(sym);
        const r = t.profit_ratio ?? 0;
        return `<li class="row">
          <div class="coin" data-color="${esc(color)}">${esc(sym.slice(0, 4))}</div>
          <div class="main">
            <div class="name">${esc(name)}</div>
            <div class="sub">${money(t.stake_amount ?? 0)} drin · gekauft ${esc(since(t.open_timestamp))}</div>
          </div>
          <span class="pill ${r >= 0 ? 'up' : 'down'}">${pct(r)}</span>
        </li>`;
      }).join('');
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
    const s = STRATEGIES[c.strategy] || { name: c.strategy || '–', text: 'Eigene Strategie.' };
    $('strategy-name').textContent = s.name;
    const every = tfText(c.timeframe);
    $('strategy-text').textContent = `${s.text}${every ? ` Schaut ${every} auf die Kurse.` : ''}`;

    $('updated').textContent = DEMO ? 'Demo mit Beispieldaten' : `Aktualisiert ${new Date().toLocaleTimeString(LOCALE, { hour: '2-digit', minute: '2-digit' })}`;
  }

  function renderOffline() {
    Biko.setMood('offline');
    $('bubble').textContent = sayFor('offline');
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
      if (!lastData) { $('login').hidden = true; $('dash').hidden = false; }
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

  // ---------- Demo (?demo oder ?demo=tippt): Beispieldaten ohne Bot ----------
  const DEMO_MOODS = ['tippt', 'schlaeft', 'jubelt', 'traurig', 'pause', 'offline'];
  let demoMood = DEMO_MOODS.includes(params.get('demo')) ? params.get('demo') : null;

  function demoData() {
    const now = Date.now();
    const h = 3600e3;
    const mood = demoMood || 'tippt';
    const open = mood === 'tippt' ? [
      { pair: 'BTC/EUR', profit_ratio: 0.021, stake_amount: 83.2, open_timestamp: now - 26 * h },
      { pair: 'SOL/EUR', profit_ratio: -0.008, stake_amount: 82.5, open_timestamp: now - 3 * h },
    ] : [];
    const closed = [{ pair: 'ETH/EUR', profit_ratio: mood === 'traurig' ? -0.031 : 0.064, close_timestamp: now - (['jubelt', 'traurig'].includes(mood) ? 5 * 60e3 : 3 * 86400e3) }];
    const coins = [{ currency: 'EUR', balance: 352.1, est_stake: 352.1 }];
    if (open.length) coins.push({ currency: 'BTC', balance: 0.00089, est_stake: 84.9 }, { currency: 'SOL', balance: 0.52, est_stake: 81.8 });
    const total = coins.reduce((s, x) => s + x.est_stake, 0);
    return {
      config: { exchange: 'kraken', dry_run: true, strategy: 'EmaTrendStrategy', timeframe: '4h', stake_currency: 'EUR', state: mood === 'pause' ? 'paused' : 'running' },
      balance: { total, starting_capital: 500, starting_capital_ratio: total / 500 - 1, currencies: coins },
      status: open,
      trades: closed,
    };
  }

  // ---------- Start ----------
  Biko.mount($('biko'));
  if (DEMO) {
    // Tippen auf Biko wechselt die Stimmung
    $('biko').addEventListener('click', () => {
      demoMood = DEMO_MOODS[(DEMO_MOODS.indexOf(demoMood || 'tippt') + 1) % DEMO_MOODS.length];
      if (demoMood === 'offline') { renderOffline(); return; }
      lastData = demoData();
      render(lastData);
    });
    if (demoMood === 'offline') { tick().then(renderOffline); } else { tick(); }
  } else if (store.get('biko.access')) {
    tick();
  } else {
    showLogin();
  }
})();
