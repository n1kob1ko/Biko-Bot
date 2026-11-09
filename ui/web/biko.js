// Die Maskottchen (Biko, Yojji). Eigene SVGs, alle Animationen in style.css.
// Maskottchen.mount(el) hängt ein Exemplar ein, setMood(m) stellt die Stimmung für alle ein.
// Stimmungen: schlaeft, tippt, jubelt, traurig, pause, offline, winkt, laedt
//
// Alle Maskottchen teilen Gesicht, Laptop, Schild und Effekte, damit jede Stimmung gleich funktioniert.
// Sie unterscheiden sich in Farben (CSS-Variablen, [data-maskottchen="..."] in style.css) und Form
// (Federschopf, Schnabel und Flügel bzw. Ohren und Schwanz). Neues Maskottchen: unten in MASKOTTCHEN eintragen, Farben in style.css,
// ein icon-<id>.svg anlegen und in install.sh bei MASKOTTCHEN_LISTE ergänzen.
(function () {
  // Effekte hinter/neben der Figur (für alle gleich)
  const FX = `
  <g class="fx fx-zzz">
    <text class="z z1" x="160" y="66">z</text>
    <text class="z z2" x="174" y="48">z</text>
    <text class="z z3" x="190" y="28">Z</text>
  </g>
  <g class="fx fx-question"><text x="168" y="58">?</text></g>
  <g class="fx fx-sparkles">
    <path class="spark s1" d="M44 64 l4 10 l10 4 l-10 4 l-4 10 l-4 -10 l-10 -4 l10 -4z"/>
    <path class="spark s2" d="M196 54 l3 8 l8 3 l-8 3 l-3 8 l-3 -8 l-8 -3 l8 -3z"/>
    <path class="spark s3" d="M200 132 l3 7 l7 3 l-7 3 l-3 7 l-3 -7 l-7 -3 l7 -3z"/>
    <path class="spark s4" d="M34 138 l3 7 l7 3 l-7 3 l-3 7 l-3 -7 l-7 -3 l7 -3z"/>
  </g>
  <g class="fx fx-floaters">
    <text class="fl f1" x="92" y="130">€</text>
    <text class="fl f2" x="118" y="130">↗</text>
    <text class="fl f3" x="142" y="130">+</text>
  </g>`;

  // Gesicht: Augen, Brauen, Bäckchen, Münder, Träne. `extra` kommt davor (z. B. Schnurrhaare, Nase).
  // `mouth` ersetzt die Münder (z. B. Schnabel beim Vogel).
  const MOUTHS = (smile) => `
      <path class="mouth mouth-smile line" d="${smile}"/>
      <ellipse class="mouth mouth-o" cx="120" cy="131" rx="3.6" ry="3"/>
      <path class="mouth mouth-sad line" d="M111 134 q9 -7 18 0"/>
      <path class="mouth mouth-open" d="M108 126 q12 17 24 0z"/>
      <path class="mouth mouth-wavy line" d="M109 131 q5.5 -4 11 0 q5.5 4 11 0"/>`;
  const face = ({ extra = '', smile = 'M111 127 q9 8 18 0', mouth } = {}) => `
    <g class="face">
      ${extra}
      <g class="eyes eyes-open">
        <g class="eye"><ellipse cx="100" cy="112" rx="7.5" ry="9.5"/><circle class="shine" cx="103" cy="108" r="2.6"/></g>
        <g class="eye"><ellipse cx="140" cy="112" rx="7.5" ry="9.5"/><circle class="shine" cx="143" cy="108" r="2.6"/></g>
      </g>
      <g class="eyes eyes-closed line">
        <path d="M91 113 q9 6 18 0"/><path d="M131 113 q9 6 18 0"/>
      </g>
      <g class="eyes eyes-happy line">
        <path d="M91 116 q9 -11 18 0"/><path d="M131 116 q9 -11 18 0"/>
      </g>
      <g class="brows-sad line"><path d="M90 100 L107 95"/><path d="M133 95 L150 100"/></g>
      <ellipse class="blush" cx="85" cy="128" rx="9" ry="5"/>
      <ellipse class="blush" cx="155" cy="128" rx="9" ry="5"/>
      ${mouth || MOUTHS(smile)}
      <path class="tear" d="M97 121 q-5 8 0 10 q5 -2 0 -10z"/>
    </g>`;

  // Laptop, Hände und Pause-Schild (für alle gleich)
  const PROPS = `
    <g class="laptop">
      <rect class="laptop-back" x="78" y="141" width="84" height="44" rx="6"/>
      <circle class="laptop-logo" cx="120" cy="163" r="6"/>
      <rect class="laptop-base" x="68" y="183" width="104" height="7" rx="3.5"/>
    </g>
    <g class="hands">
      <ellipse class="hand hand-l" cx="78" cy="180" rx="9" ry="7"/>
      <ellipse class="hand hand-r" cx="162" cy="180" rx="9" ry="7"/>
    </g>
    <g class="sign">
      <rect class="sign-stick" x="186" y="108" width="5" height="74" rx="2"/>
      <rect class="sign-board" x="158" y="82" width="66" height="32" rx="7"/>
      <text class="sign-text" x="191" y="104">Pause</text>
    </g>`;

  // Körper: `behind` liegt hinter dem Rumpf (Schwanz, Ohren, Schopf), `top` darüber.
  // `body`, `belly`, `feet` und `arms` ändern die Grundform (Standard: rund mit Ärmchen).
  const ARMS = `
    <g class="arm arm-l"><ellipse cx="64" cy="132" rx="10" ry="16"/></g>
    <g class="arm arm-r"><ellipse cx="176" cy="132" rx="10" ry="16"/></g>`;
  const FEET = `
    <ellipse class="foot" cx="96" cy="182" rx="17" ry="9"/>
    <ellipse class="foot" cx="144" cy="182" rx="17" ry="9"/>`;
  const svg = ({ behind = '', top = '', faceOpts, body = { rx: 60, ry: 57, cy: 124 }, belly = { rx: 38, ry: 27, cy: 146 }, feet = FEET, arms = ARMS } = {}) => `
<svg class="biko" viewBox="0 0 240 210" role="img" aria-labelledby="biko-title">
  <title id="biko-title">__NAME__</title>
  <ellipse class="shadow" cx="120" cy="194" rx="56" ry="8"/>
  ${FX}
  <g class="fidget-g">
  <g class="body-g">
    ${behind}
    ${feet}
    ${arms}
    <ellipse class="torso" cx="120" cy="${body.cy}" rx="${body.rx}" ry="${body.ry}"/>
    <ellipse class="belly" cx="120" cy="${belly.cy}" rx="${belly.rx}" ry="${belly.ry}"/>
    ${top}
    ${face(faceOpts)}
    ${PROPS}
  </g>
  </g>
</svg>`;

  const MASKOTTCHEN = {
    // Biko: kugelrunder, dicker gelber Vogel mit Federschopf, Schnabel und Flügeln
    biko: {
      svg: svg({
        body: { rx: 68, ry: 60, cy: 124 },
        belly: { rx: 48, ry: 32, cy: 148 },
        behind: `
    <g class="tail"><path class="tail-feathers" d="M162 182 Q194 186 212 166 Q204 162 197 168 Q208 154 200 147 Q191 157 189 166 Q193 151 183 147 Q174 165 162 182 Z"/></g>
    <g class="tuft">
      <path class="tuft-f" d="M118 70 Q104 52 108 40 Q118 50 121 66 Z"/>
      <path class="tuft-f" d="M119 68 Q116 46 126 34 Q130 50 124 68 Z"/>
      <path class="tuft-f" d="M122 68 Q132 52 144 48 Q140 62 126 70 Z"/>
    </g>`,
        feet: `
    <g class="bird-feet line">
      <path d="M96 176 v8 M96 184 l-8 5 M96 184 v7 M96 184 l8 5"/>
      <path d="M144 176 v8 M144 184 l-8 5 M144 184 v7 M144 184 l8 5"/>
    </g>`,
        arms: '',
        // Flügel liegen vorne am Bauch an, damit der Vogel schön rund wirkt
        top: `
    <path class="chest-feathers" d="M106 134 q4 4 8 0 q4 4 8 0 q4 4 8 0 M112 142 q4 4 8 0 q4 4 8 0"/>
    <g class="arm arm-l"><path class="wing" d="M62 112 Q42 122 44 150 Q47 158 54 152 Q56 160 63 153 Q68 158 72 150 Q78 130 62 112 Z"/></g>
    <g class="arm arm-r"><path class="wing" d="M178 112 Q198 122 196 150 Q193 158 186 152 Q184 160 177 153 Q172 158 168 150 Q162 130 178 112 Z"/></g>`,
        faceOpts: {
          mouth: `
      <g class="beak beak-open"><path class="beak-inside" d="M109.5 121 Q120 147 130.5 121 Z"/><path class="beak-low" d="M111 129 Q120 146 129 129 Q120 136 111 129 Z"/></g>
      <path class="beak beak-top" d="M108.5 118.5 Q120 111 131.5 118.5 Q126 127 120 129 Q114 127 108.5 118.5 Z"/>
      <path class="beak-shine" d="M114 117.5 q4 -2.5 8 -2"/>`,
        },
      }),
      fidgets: ['tuft', 'flap', 'tail'],
    },
    // Yojji: runde Katze mit Ohren, Schnurrhaaren und Ringelschwanz
    yojji: {
      svg: svg({
        behind: `
    <g class="tail"><path class="tail-path" d="M168 170 C 200 168 214 146 206 120 C 202 106 190 104 188 114"/></g>
    <g class="ear ear-l"><path class="ear-outer" d="M70 104 Q62 58 80 48 Q92 46 114 70 Z"/><path class="ear-inner" d="M79 92 Q75 66 85 60 Q92 60 104 72 Z"/></g>
    <g class="ear ear-r"><path class="ear-outer" d="M170 104 Q178 58 160 48 Q148 46 126 70 Z"/><path class="ear-inner" d="M161 92 Q165 66 155 60 Q148 60 136 72 Z"/></g>`,
        top: `
    <path class="stripe" d="M112 70 q8 -3 16 0 M108 80 q12 -4 24 0"/>`,
        faceOpts: {
          smile: 'M111 127 q4.5 6 9 0 q4.5 6 9 0',
          extra: `
      <g class="whiskers line"><path d="M82 122 L58 117"/><path d="M82 129 L57 131"/><path d="M158 122 L182 117"/><path d="M158 129 L183 131"/></g>
      <path class="nose" d="M114.5 119.5 Q120 116.5 125.5 119.5 Q122 124.5 120 124.5 Q118 124.5 114.5 119.5 Z"/>`,
        },
      }),
      fidgets: ['ear', 'tail'],
    },
  };

  const MOODS = ['schlaeft', 'tippt', 'jubelt', 'traurig', 'pause', 'offline', 'winkt', 'laedt'];

  const inst = window.BIKO_INSTANZ || {};
  const id = Object.prototype.hasOwnProperty.call(MASKOTTCHEN, inst.maskottchen) ? inst.maskottchen : 'biko';
  const name = (typeof inst.name === 'string' && inst.name.trim()) ? inst.name.trim().slice(0, 20) : 'Biko';
  const safeName = name.replace(/[&<>"']/g, '');
  const CHOSEN = MASKOTTCHEN[id].svg.replace('__NAME__', safeName);

  // Kleine Zwischendurch-Bewegungen, damit das Maskottchen lebendig wirkt.
  // Welche passen, hängt von der Stimmung ab (beim Jubeln hüpft es schon, beim Schlafen bewegt sich höchstens ein Ohr oder der Federschopf).
  const own = MASKOTTCHEN[id].fidgets;
  const FIDGETS = {
    schlaeft: id === 'yojji' ? ['ear', 'tail'] : ['tuft'],
    tippt: ['tilt', ...own],
    jubelt: [],
    traurig: id === 'yojji' ? ['ear'] : ['tail'],
    pause: ['tilt', 'hop', ...own],
    offline: ['tilt', ...own],
    winkt: ['hop', 'tilt', 'wiggle', ...own],
    laedt: ['tilt', ...own],
  };
  const FIDGET_MS = { hop: 650, tilt: 1400, wiggle: 700, boop: 520, tuft: 900, flap: 600, ear: 450, tail: 750 };
  const reduced = () => window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Ein Maskottchen kann mehrfach auf der Seite stehen (groß in der Übersicht, klein oben in den
  // anderen Ansichten, beim Login). Alle Exemplare zeigen immer dieselbe Stimmung.
  const M = {
    MOODS,
    id,
    name,
    svgs: [],
    mood: 'laedt',
    mount(el, { decorative = false } = {}) {
      el.innerHTML = decorative
        ? CHOSEN.replace('role="img" aria-labelledby="biko-title"', 'aria-hidden="true"').replace(/<title[^>]*>[^<]*<\/title>/, '')
        : CHOSEN;
      const s = el.querySelector('svg');
      s.dataset.maskottchen = id;
      s.dataset.mood = this.mood;
      this.svgs.push(s);
      this.startFidgets();
      return s;
    },
    setMood(mood) {
      if (!MOODS.includes(mood)) return;
      if (mood === this.mood) return;
      this.mood = mood;
      this.svgs.forEach((s) => { s.dataset.mood = mood; });
    },
    // Eine Zwischendurch-Bewegung abspielen (z. B. 'boop' beim Antippen)
    fidget(kind) {
      if (reduced() || !FIDGET_MS[kind]) return;
      this.svgs.forEach((s) => {
        delete s.dataset.fidget;
        void s.getBoundingClientRect(); // Neustart, falls dieselbe Bewegung gerade lief
        s.dataset.fidget = kind;
        clearTimeout(s._fidgetTimer);
        s._fidgetTimer = setTimeout(() => { if (s.dataset.fidget === kind) delete s.dataset.fidget; }, FIDGET_MS[kind]);
      });
    },
    startFidgets() {
      if (this._fidgetLoop) return;
      const next = () => {
        this._fidgetLoop = setTimeout(() => {
          const options = FIDGETS[this.mood] || [];
          if (options.length && document.visibilityState === 'visible') {
            this.fidget(options[Math.floor(Math.random() * options.length)]);
          }
          next();
        }, 4500 + Math.random() * 6000);
      };
      next();
    },
  };
  window.Maskottchen = M;
  window.Biko = M; // alter Name, bleibt für bestehenden Code
})();
