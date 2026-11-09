// Biko, das Maskottchen. Eigenes SVG, alle Animationen in style.css.
// Biko.mount(el) hängt ein Exemplar ein, Biko.setMood(m) stellt die Stimmung für alle ein.
// Stimmungen: schlaeft, tippt, jubelt, traurig, pause, offline, winkt, laedt
(function () {
  const SVG = `
<svg class="biko" viewBox="0 0 240 210" role="img" aria-labelledby="biko-title">
  <title id="biko-title">Biko</title>
  <ellipse class="shadow" cx="120" cy="194" rx="56" ry="8"/>

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
  </g>

  <g class="body-g">
    <g class="antenna">
      <path class="antenna-stick" d="M120 70 Q118 52 122 40"/>
      <circle class="antenna-ball" cx="122" cy="34" r="9"/>
      <circle class="antenna-shine" cx="119" cy="31" r="2.6"/>
    </g>
    <ellipse class="foot" cx="96" cy="182" rx="17" ry="9"/>
    <ellipse class="foot" cx="144" cy="182" rx="17" ry="9"/>
    <g class="arm arm-l"><ellipse cx="64" cy="132" rx="10" ry="16"/></g>
    <g class="arm arm-r"><ellipse cx="176" cy="132" rx="10" ry="16"/></g>
    <ellipse class="torso" cx="120" cy="124" rx="60" ry="57"/>
    <ellipse class="belly" cx="120" cy="146" rx="38" ry="27"/>

    <g class="face">
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
      <path class="mouth mouth-smile line" d="M111 127 q9 8 18 0"/>
      <ellipse class="mouth mouth-o" cx="120" cy="131" rx="3.6" ry="3"/>
      <path class="mouth mouth-sad line" d="M111 134 q9 -7 18 0"/>
      <path class="mouth mouth-open" d="M108 126 q12 17 24 0z"/>
      <path class="mouth mouth-wavy line" d="M109 131 q5.5 -4 11 0 q5.5 4 11 0"/>
      <path class="tear" d="M97 121 q-5 8 0 10 q5 -2 0 -10z"/>
    </g>

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
    </g>
  </g>
</svg>`;

  const MOODS = ['schlaeft', 'tippt', 'jubelt', 'traurig', 'pause', 'offline', 'winkt', 'laedt'];

  // Biko kann mehrfach auf der Seite stehen (groß in der Übersicht, klein oben in den anderen
  // Ansichten). Alle Exemplare zeigen immer dieselbe Stimmung.
  window.Biko = {
    MOODS,
    svgs: [],
    mood: 'laedt',
    mount(el, { decorative = false } = {}) {
      el.innerHTML = decorative
        ? SVG.replace('role="img" aria-labelledby="biko-title"', 'aria-hidden="true"').replace(/<title[^>]*>Biko<\/title>/, '')
        : SVG;
      const svg = el.querySelector('svg');
      svg.dataset.mood = this.mood;
      this.svgs.push(svg);
      return svg;
    },
    setMood(mood) {
      if (!MOODS.includes(mood)) return;
      this.mood = mood;
      this.svgs.forEach((svg) => { svg.dataset.mood = mood; });
    },
  };
})();
