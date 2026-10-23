/* The Board's half court, drawn in feet with the hoop at the top, the way it's printed on a coach's clipboard.
   Shots come in feet too (x 0-50 across, y up the floor, hoop at 25, 1). Makes are O, misses are X; a miss on a
   look that goes in 60% of the time or more is drawn in red. Tap or hover picks the nearest shot. */
"use strict";

const Court = (() => {
  const NS = "http://www.w3.org/2000/svg";
  const HOOP = [25, 1], BASE = -4.25, HALF = 42.75;
  const lines = [
    `<rect class="line" x="0" y="${BASE}" width="50" height="${HALF - BASE}"/>`,
    `<rect class="paint" x="17" y="${BASE}" width="16" height="19"/>`,
    `<path class="line" d="M19 14.75 A6 6 0 0 0 31 14.75"/>`,
    `<path class="line" d="M19 14.75 A6 6 0 0 1 31 14.75" stroke-dasharray="0.8 0.8"/>`,
    `<path class="line" d="M21 -0.25 V1 A4 4 0 0 0 29 1 V-0.25"/>`,
    `<path class="line" d="M3 ${BASE} V9.95 A23.75 23.75 0 0 0 47 9.95 V${BASE}"/>`,
    `<line class="line" x1="0" y1="${HALF}" x2="50" y2="${HALF}"/>`,
    `<path class="line" d="M19 ${HALF} A6 6 0 0 1 31 ${HALF}"/>`,
    `<line class="rim" x1="22" y1="-0.25" x2="28" y2="-0.25" stroke-width="0.3"/>`,
    `<circle class="rim" cx="25" cy="1" r="0.75"/>`,
  ].join("");

  function mark(s, i) {
    if (s.made) return `<circle class="o" data-i="${i}" cx="${s.x}" cy="${s.y}" r="0.62"/>`;
    const d = 0.5, hi = s.p != null && s.p >= 0.6 ? " hi" : "";
    return `<path class="x${hi}" data-i="${i}" d="M${s.x - d} ${s.y - d}L${s.x + d} ${s.y + d}M${s.x + d} ${s.y - d}L${s.x - d} ${s.y + d}"/>`;
  }

  // shots: [{x, y, made, p}], opts: {label, onPick(i)}
  function draw(svg, shots, opts = {}) {
    const vis = shots.map((s, i) => [s, i]).filter(([s]) => s.y <= HALF + 0.5 && s.y >= BASE - 1);
    svg.setAttribute("viewBox", `-1 ${BASE - 1} 52 ${HALF - BASE + 2}`);
    svg.setAttribute("class", "court");
    svg.innerHTML = lines + (opts.label ? `<text class="side-lab" x="1" y="${HALF - 1}">${opts.label}</text>` : "")
      + vis.filter(([s]) => !s.made).map(([s, i]) => mark(s, i)).join("")
      + vis.filter(([s]) => s.made).map(([s, i]) => mark(s, i)).join("")
      + `<circle class="pick" r="1.3" cx="-10" cy="-10"/>`;
    const ring = svg.querySelector(".pick");
    let picked = -1;
    function select(i) {
      picked = i;
      if (i < 0 || !shots[i]) { ring.setAttribute("cx", -10); ring.setAttribute("cy", -10); }
      else { ring.setAttribute("cx", shots[i].x); ring.setAttribute("cy", shots[i].y); }
      if (opts.onPick) opts.onPick(i);
    }
    function nearest(ev) {
      const m = svg.getScreenCTM();
      if (!m) return -1;
      const pt = new DOMPoint(ev.clientX, ev.clientY).matrixTransform(m.inverse());
      let best = -1, bd = 2.2 * 2.2;
      for (const [s, i] of vis) {
        const d = (s.x - pt.x) ** 2 + (s.y - pt.y) ** 2;
        if (d < bd) { bd = d; best = i; }
      }
      return best;
    }
    svg.addEventListener("pointermove", (ev) => { if (ev.pointerType === "mouse") { const i = nearest(ev); if (i >= 0 && i !== picked) select(i); } });
    svg.addEventListener("click", (ev) => { const i = nearest(ev); select(i === picked ? -1 : i); });
    return { select };
  }

  function key() {
    const o = `<svg viewBox="-1 -1 2 2"><circle cx="0" cy="0" r="0.7" fill="none" stroke="var(--blue)" stroke-width="0.3"/></svg>`;
    const x = `<svg viewBox="-1 -1 2 2"><path d="M-.6 -.6L.6 .6M.6 -.6L-.6 .6" stroke="var(--ink-2)" stroke-width="0.25" stroke-linecap="round"/></svg>`;
    const xr = `<svg viewBox="-1 -1 2 2"><path d="M-.6 -.6L.6 .6M.6 -.6L-.6 .6" stroke="var(--red)" stroke-width="0.25" stroke-linecap="round"/></svg>`;
    return `<p class="court-key"><span>${o}Made</span><span>${x}Missed</span><span>${xr}Missed a shot that goes in 60% of the time or more</span></p>`;
  }

  return { draw, key, NS };
})();
