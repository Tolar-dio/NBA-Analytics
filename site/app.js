/* The Board front end. Plain JS, no build step. Data comes from data/*.json, rebuilt every morning by site/build.py. */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { v === "" || v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch (e) {} },
};
const pct = (p, d = 1) => (p == null ? "–" : (100 * p).toFixed(d) + "%");
const num = (x, d = 1) => (x == null ? "–" : Number(x).toFixed(d));
const signed = (x, d = 1) => (x == null ? "–" : (x > 0 ? "+" : x < 0 ? "−" : "") + Math.abs(x).toFixed(d));
const spct = (p, d = 1) => (p == null ? "–" : signed(100 * p, d));
const cls = (x, flip) => (x == null || Math.abs(x) < 1e-9 ? "" : (x > 0) !== !!flip ? "good" : "bad");
const ordinal = (n) => n + ((n % 100 >= 11 && n % 100 <= 13) ? "th" : ({ 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th"));
const zip = (cols, row) => Object.fromEntries(cols.map((c, i) => [c, row[i]]));
const dateLong = (iso) => new Date(iso + "T12:00:00").toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
const dateShort = (iso) => new Date(iso + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });
const tipTime = (utc) => (utc ? new Date(utc).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZoneName: "short" }) : "");
const heightFt = (inch) => (inch ? `${Math.floor(inch / 12)}-${inch % 12}` : "");

const D = { cache: {} };
const S = {
  season: null, view: "what", lSort: { key: "net", dir: -1 }, pView: "scoring", pSort: { key: "pts_pg", dir: -1 },
  pQ: "", pTeam: "all", pMin: null, pLimit: 60, gDays: 7, gTeam: false, zoneSide: "for",
};

async function getJSON(path) {
  if (D.cache[path]) return D.cache[path];
  const r = await fetch("data/" + path, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return (D.cache[path] = await r.json());
}
const league = (s = S.season) => getJSON(`league.${s}.json`);
const seasonLabel = (s) => (D.meta.seasons.find((x) => x.season === +s) || { label: s }).label;

// ------------------------------------------------------------------ your team, players you follow
const myTeam = () => store.get("board-team");
const follows = {
  list() { try { const v = JSON.parse(store.get("board-follow") || "[]"); return Array.isArray(v) ? v : []; } catch (e) { return []; } },
  has(id) { return this.list().some((x) => x.id === +id); },
  toggle(x) {
    const l = this.list(), i = l.findIndex((y) => y.id === +x.id);
    if (i >= 0) l.splice(i, 1); else l.push({ id: +x.id, name: x.name, team: x.team });
    store.set("board-follow", l.length ? JSON.stringify(l) : "");
    return i < 0;
  },
};
function followBtn(x) {
  const on = follows.has(x.id);
  return `<button class="follow" type="button" data-follow="${x.id}" data-name="${esc(x.name)}" data-team="${esc(x.team || "")}" aria-pressed="${on}">${on ? "Following" : "Follow"}</button>`;
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-follow]");
  if (!b) return;
  const on = follows.toggle({ id: b.dataset.follow, name: b.dataset.name, team: b.dataset.team });
  b.setAttribute("aria-pressed", on); b.textContent = on ? "Following" : "Follow";
});

async function openTeamPicker(after) {
  const L = await league();
  const groups = {};
  L.teams.forEach((t) => (groups[`${t.conference}|${t.division}`] ||= []).push(t));
  const keys = Object.keys(groups).sort();
  const back = document.createElement("div");
  back.className = "dialog-back";
  back.innerHTML = `<div class="dialog" role="dialog" aria-modal="true" aria-label="Pick your team">
    <div class="head-row"><h2 class="grow">Pick your team</h2><button class="pill" data-close type="button">Close</button></div>
    <p class="note">We'll put it first and highlight it everywhere. It's saved in this browser only.</p>
    <div class="picker">${keys.map((k) => `<div><h3>${esc(k.split("|")[1])}</h3><ul>${groups[k].sort((a, b) => a.full_name.localeCompare(b.full_name))
      .map((t) => `<li><a data-pick="${t.abbr}">${esc(t.full_name)}<span>${t.abbr === myTeam() ? "your team" : t.abbr}</span></a></li>`).join("")}</ul></div>`).join("")}</div>
    ${myTeam() ? `<p><button class="more" data-pick="">Clear your team</button></p>` : ""}</div>`;
  document.body.appendChild(back);
  const close = () => back.remove();
  back.addEventListener("click", (e) => {
    if (e.target === back || e.target.closest("[data-close]")) return close();
    const p = e.target.closest("[data-pick]");
    if (!p) return;
    store.set("board-team", p.dataset.pick);
    applyTeamButton(); close();
    if (after) after(); else route();
  });
  document.addEventListener("keydown", function k(e) { if (e.key === "Escape") { close(); document.removeEventListener("keydown", k); } });
  $("[data-pick]", back)?.focus();
}
function applyTeamButton() {
  const t = myTeam();
  $("#teamBtn").textContent = t ? `Your team: ${t}` : "Your team";
  $("#teamBtn").classList.toggle("on", !!t);
}

// ------------------------------------------------------------------ tables
function table(rows, cols, sort, id, rowCls) {
  const head = cols.map((c) => `<th data-key="${c.key}" class="${c.nosort ? "nosort" : ""} ${c.cls || ""}" ${sort && sort.key === c.key ? `aria-sort="${sort.dir < 0 ? "descending" : "ascending"}"` : ""} scope="col" ${c.title ? `title="${esc(c.title)}"` : ""}>${c.label}</th>`).join("");
  const body = rows.map((r) => `<tr class="${rowCls ? rowCls(r) : ""}">${cols.map((c) => `<td class="${c.cls || ""}">${c.fmt ? c.fmt(r) : esc(r[c.key] ?? "–")}</td>`).join("")}</tr>`).join("");
  return `<div class="table-wrap"><table id="${id || ""}"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}
function sortRows(rows, sort) {
  return [...rows].sort((a, b) => {
    const va = a[sort.key], vb = b[sort.key];
    if (va == null && vb == null) return 0; if (va == null) return 1; if (vb == null) return -1;
    return (typeof va === "string" ? va.localeCompare(vb) : va - vb) * sort.dir;
  });
}
function bindSort(root, sort, rerender) {
  $$("th[data-key]:not(.nosort)", root).forEach((th) => th.addEventListener("click", () => {
    const k = th.dataset.key;
    if (sort.key === k) sort.dir *= -1; else { sort.key = k; sort.dir = th.dataset.asc ? 1 : -1; }
    rerender();
  }));
}
const teamLink = (abbr) => `<a class="who" href="#teams/${abbr}">${esc(abbr)}</a>`;
const playerLink = (id, name) => `<a class="who" href="#players/${id}">${esc(name)}</a>`;
const rk = (n) => (n ? `<span class="rk">${ordinal(n)}</span>` : "");

// small-sample warning for the early season
function earlyNote(L) {
  const n = L.league.games;
  if (n >= 300) return "";
  const other = D.meta.seasons.find((s) => s.season !== L.season);
  return `<p class="note warn">Only ${n} games into ${L.label}. One hot shooting night moves these numbers a lot, so read them as first impressions.${other ? ` <a href="#" data-season="${other.season}">See ${other.label}</a> for a full season.` : ""}</p>`;
}
document.addEventListener("click", (e) => {
  const a = e.target.closest("[data-season]");
  if (!a) return;
  e.preventDefault(); setSeason(+a.dataset.season);
});

// ------------------------------------------------------------------ League
async function renderLeague(view) {
  const L = await league();
  const mine = myTeam();
  const x = S.view === "shots";
  const rows = L.teams.map((t) => ({ ...t, luck: t.net - t.x_net }));
  const lg = L.league;
  view.innerHTML = `<section class="zone">
    <h1>League</h1>
    <p class="lede">Every team's offense and defense, measured per 100 possessions so fast and slow teams compare fairly. Switch to what the shots say to see each team with its shot-making luck taken out: every shot valued at how often that kind of shot goes in.</p>
    ${earlyNote(L)}
    <div class="controls"><div class="seg" role="group" aria-label="Ratings">
      <button type="button" data-view="what" aria-pressed="${!x}">What happened</button>
      <button type="button" data-view="shots" aria-pressed="${x}">What the shots say</button></div></div>
    <div id="lgChart"></div>
    <p class="note">Further right scores more; higher up allows less. Dashed lines mark net ratings of +10, 0 and −10 (points per 100 possessions better than the opponent). League average offense: ${num(lg.ortg)}.</p>
  </section>
  <section class="zone"><div class="head-row"><h2 class="grow">Standings by the numbers</h2></div>
    <div id="lgTable"></div>
    <p class="note">Net: points per 100 possessions minus points allowed. Shots: the same with every trip's shots valued at what they usually produce. Luck: the gap between the two; it tends to shrink as a season goes on. Opp. 3P vs lg: how much better or worse opponents have shot from three than the league; a defense has little say over that, so it evens out.</p>
  </section>
  <section class="zone" id="lgLuck"></section>`;
  $$("[data-view]", view).forEach((b) => b.addEventListener("click", () => { S.view = b.dataset.view; renderLeague(view); }));
  $("#lgChart").innerHTML = scatter(rows, x, mine);
  bindScatterTips($("#lgChart"), rows, x);
  const cols = [
    { key: "abbr", label: "Team", cls: "l", fmt: (r) => `${teamLink(r.abbr)} <span class="dim">${esc(r.full_name.replace(/^.* /, ""))}</span>` },
    { key: "w", label: "W–L", fmt: (r) => `${r.w}–${r.l}` },
    { key: "net", label: "Net", fmt: (r) => `<span class="${cls(r.net)}">${signed(r.net)}</span>` },
    { key: "x_net", label: "Shots", title: "Net rating from the shots each team got and gave up", fmt: (r) => signed(r.x_net) },
    { key: "luck", label: "Luck", title: "Net minus shots-based net", fmt: (r) => signed(r.luck) },
    { key: "ortg", label: "Off", fmt: (r) => `${num(r.ortg)}${rk(r.ortg_rk)}` },
    { key: "drtg", label: "Def", fmt: (r) => `${num(r.drtg)}${rk(r.drtg_rk)}` },
    { key: "pace", label: "Pace", fmt: (r) => num(r.pace) },
    { key: "efg", label: "eFG%", fmt: (r) => pct(r.efg) },
    { key: "tov", label: "TOV%", fmt: (r) => pct(r.tov) },
    { key: "orb", label: "OREB%", fmt: (r) => pct(r.orb) },
    { key: "ftr", label: "FT rate", fmt: (r) => num(r.ftr, 3) },
    { key: "opp_efg", label: "Opp eFG%", fmt: (r) => pct(r.opp_efg) },
    { key: "opp_3p_vs_lg", label: "Opp 3P vs lg", fmt: (r) => `<span class="${cls(r.opp_3p_vs_lg, true)}">${spct(r.opp_3p_vs_lg)}</span>` },
  ];
  const draw = () => {
    $("#lgTable").innerHTML = table(sortRows(rows, S.lSort), cols, S.lSort, "lgT", (r) => (r.abbr === mine ? "mine" : ""));
    bindSort($("#lgTable"), S.lSort, draw);
  };
  draw();
  const lucky = [...rows].sort((a, b) => b.luck - a.luck);
  const line = (t) => `<li><a href="#teams/${t.abbr}">${esc(t.full_name)}</a>: ${signed(t.net)} net, ${signed(t.x_net)} on their shots${Math.abs(t.opp_3p_vs_lg) >= 0.015 ? `; opponents shooting ${num(100 * Math.abs(t.opp_3p_vs_lg))} points ${t.opp_3p_vs_lg > 0 ? "better" : "worse"} than the league from three` : ""}.</li>`;
  $("#lgLuck").innerHTML = `<div class="grid-2"><div><h2>Results ahead of their shots</h2><p class="lede">These teams have won more than their shots say they should. Some of it is skill (great shooters beat the averages), much of it doesn't last.</p><ul>${lucky.slice(0, 4).map(line).join("")}</ul></div>
    <div><h2>Better than their record</h2><p class="lede">These teams' shots say they've been better than the scoreboard shows. Teams like this tend to climb.</p><ul>${lucky.slice(-4).reverse().map(line).join("")}</ul></div></div>`;
}

function scatter(rows, x, mine) {
  const W = Math.max(320, Math.min(900, ($("#view").clientWidth || 900) - 32)), narrow = W < 600;
  const H = Math.round(W * (narrow ? 1.05 : 0.62));
  const m = { l: 46, r: 14, t: 30, b: 40 };
  const xs = rows.map((r) => (x ? r.x_ortg : r.ortg)), ys = rows.map((r) => (x ? r.x_drtg : r.drtg));
  const all = [...xs, ...ys];
  const lo = Math.floor(Math.min(...all) - 1), hi = Math.ceil(Math.max(...all) + 1);
  const xmin = Math.min(...xs) - 1.5, xmax = Math.max(...xs) + 1.5, ymin = Math.min(...ys) - 1.5, ymax = Math.max(...ys) + 1.5;
  const X = (v) => m.l + ((v - xmin) / (xmax - xmin)) * (W - m.l - m.r);
  const Y = (v) => m.t + ((v - ymin) / (ymax - ymin)) * (H - m.t - m.b);    // lower (better) defense at the top
  let g = "";
  for (let v = Math.ceil(xmin); v <= xmax; v += 2) g += `<line x1="${X(v)}" x2="${X(v)}" y1="${m.t}" y2="${H - m.b}"/><text x="${X(v)}" y="${H - m.b + 16}" text-anchor="middle">${v}</text>`;
  for (let v = Math.ceil(ymin); v <= ymax; v += 2) g += `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${m.l - 6}" y="${Y(v) + 4}" text-anchor="end">${v}</text>`;
  let iso = "";
  [-10, 0, 10].forEach((k) => {      // net = off - def = k  ->  def = off - k
    const pts = [];
    for (const xv of [xmin, xmax]) { const yv = xv - k; pts.push([xv, Math.max(ymin, Math.min(ymax, yv))]); }
    const a = [Math.max(xmin, ymin + k), Math.min(xmax, ymax + k)];
    if (a[0] < a[1]) iso += `<line class="iso" x1="${X(a[0])}" y1="${Y(a[0] - k)}" x2="${X(a[1])}" y2="${Y(a[1] - k)}"/><text class="iso-lab" x="${X(a[0]) + 6}" y="${Y(a[0] - k) + 14}">net ${k > 0 ? "+" : k < 0 ? "−" : ""}${Math.abs(k)}</text>`;
  });
  const dots = rows.map((r, i) => {
    const cx = X(xs[i]), cy = Y(ys[i]), me = r.abbr === mine;
    return `<g data-i="${i}"><circle class="team-dot ${me ? "mine" : ""}" cx="${cx}" cy="${cy}" r="${me ? 6 : 4.5}"/><text class="team-lab" x="${cx + 7}" y="${cy + 4}">${r.abbr}</text></g>`;
  }).join("");
  const notes = `<text class="hand-blue" x="${W - m.r}" y="${m.t - 8}" text-anchor="end">scores and stops people ↗</text>
    ${narrow ? "" : `<text class="hand" x="${m.l}" y="${H - 4}">↙ can't do either</text>`}`;
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Offensive rating against defensive rating for every team">
    <g class="grid">${g}</g>${iso}${notes}${dots}
    <g class="axis"><text class="title" x="${(W + m.l) / 2}" y="${H - 4}" text-anchor="middle">${narrow ? "Offense per 100" : "Offense: points per 100 possessions"}${x ? " (from shots)" : ""}</text>
    <text class="title" transform="translate(12 ${(H - m.b + m.t) / 2}) rotate(-90)" text-anchor="middle">${narrow ? "Defense: allowed per 100" : "Defense: allowed per 100 (fewer is higher)"}</text></g></svg>`;
}
function bindScatterTips(root, rows, x) {
  const tip = $("#tip");
  $$("g[data-i]", root).forEach((gEl) => {
    const r = rows[+gEl.dataset.i];
    gEl.style.cursor = "pointer";
    gEl.addEventListener("mouseenter", (e) => {
      tip.innerHTML = `<b>${esc(r.full_name)}</b> ${r.w}–${r.l}<br>Off ${num(x ? r.x_ortg : r.ortg)}, Def ${num(x ? r.x_drtg : r.drtg)}, Net ${signed(x ? r.x_net : r.net)}`;
      tip.hidden = false; tip.style.left = e.clientX + 12 + "px"; tip.style.top = e.clientY + 12 + "px";
    });
    gEl.addEventListener("mousemove", (e) => { tip.style.left = e.clientX + 12 + "px"; tip.style.top = e.clientY + 12 + "px"; });
    gEl.addEventListener("mouseleave", () => (tip.hidden = true));
    gEl.addEventListener("click", () => { tip.hidden = true; location.hash = `#teams/${r.abbr}`; });
  });
}

// ------------------------------------------------------------------ Teams
async function renderTeamsHome(view) {
  const L = await league();
  const groups = {};
  L.teams.forEach((t) => (groups[`${t.conference}|${t.division}`] ||= []).push(t));
  view.innerHTML = `<section class="zone"><h1>Teams</h1>
    <p class="lede">Pick a team for its ratings, how it gets its shots and stops yours, the lineups it trusts and what each player does with the floor.</p>
    <div class="picker">${Object.keys(groups).sort().map((k) => `<div><h3>${esc(k.replace("|", ": "))}</h3><ul>${groups[k].sort((a, b) => b.w - a.w || a.l - b.l)
      .map((t) => `<li><a href="#teams/${t.abbr}">${esc(t.full_name)}<span>${t.w}–${t.l}</span></a></li>`).join("")}</ul></div>`).join("")}</div></section>`;
}

const ZONE_NAME = { rim: "At the rim (under 4 ft)", short: "Short range (4–14 ft)", mid: "Midrange twos (14 ft+)", corner3: "Corner threes", above3: "Above-the-break threes" };
function zonesTable(z, who) {
  if (!z) return `<p class="note">No shots yet.</p>`;
  const rows = Object.keys(ZONE_NAME).map((k) => ({ k, ...z[k] }));
  return `<div class="table-wrap zones"><table><thead><tr><th class="l nosort">Where</th><th class="nosort">Share</th><th class="nosort">League share</th><th class="nosort">${who} FG%</th><th class="nosort">Expected</th><th class="nosort">League</th></tr></thead><tbody>
    ${rows.map((r) => `<tr><td class="z">${ZONE_NAME[r.k]}</td><td>${pct(r.share)}</td><td class="dim">${pct(r.lg_share)}</td><td class="${r.fga >= 25 ? cls(r.fg - r.lg_fg) : ""}">${pct(r.fg)}</td><td>${pct(r.xfg)}</td><td class="dim">${pct(r.lg_fg)}</td></tr>`).join("")}
    </tbody></table></div>`;
}

async function renderTeam(view, abbr) {
  let T;
  try { T = await getJSON(`team/${S.season}/${abbr}.json`); } catch (e) { view.innerHTML = `<p class="loading">No ${esc(abbr)} numbers for ${seasonLabel(S.season)} yet.</p>`; return; }
  const L = await league();
  const t = T.team, mine = myTeam() === abbr;
  const res = T.results.map((r) => zip(T.results_cols, r));
  const luckLines = [];
  if (Math.abs(t.net - t.x_net) >= 1.5) luckLines.push(`Their shots say ${signed(t.x_net)} per 100 possessions, ${t.net > t.x_net ? "worse" : "better"} than the ${signed(t.net)} on the scoreboard. ${t.net > t.x_net ? "Some of that edge is shot-making that may not last." : "If the shots keep coming, the results usually follow."}`);
  if (Math.abs(t.opp_3p_vs_lg) >= 0.012) luckLines.push(`Opponents have shot ${pct(Math.abs(t.opp_3p_vs_lg))} ${t.opp_3p_vs_lg > 0 ? "better" : "worse"} than the league from three against them. Defenses control how many threes and how open; whether they drop mostly evens out.`);
  if (Math.abs(t.shotmaking) >= 0.03) luckLines.push(`They've made ${num(Math.abs(t.shotmaking), 2)} points per shot ${t.shotmaking > 0 ? "more" : "fewer"} than their looks usually produce.`);
  view.innerHTML = `<a class="back" href="#teams">All teams</a>
  <section class="zone"><div class="head-row"><h1 class="grow">${esc(t.full_name)}</h1><button class="pill ${mine ? "on" : ""}" id="mineBtn" type="button">${mine ? "Your team" : "Make this my team"}</button></div>
    <p class="lede">${t.w}–${t.l}, ${esc(t.division)} division, ${seasonLabel(T.season)}.</p>
    ${earlyNote(L)}
    <div class="strip">
      <div><b class="${cls(t.net)}">${signed(t.net)}</b><span>Net rating</span><em>${ordinal(t.net_rk)} of 30</em></div>
      <div><b>${num(t.ortg)}</b><span>Offense</span><em>${ordinal(t.ortg_rk)}</em></div>
      <div><b>${num(t.drtg)}</b><span>Defense</span><em>${ordinal(t.drtg_rk)}</em></div>
      <div><b>${signed(t.x_net)}</b><span>From their shots</span><em>${ordinal(t.x_net_rk)}</em></div>
      <div><b>${num(t.pace)}</b><span>Pace</span><em>${ordinal(t.pace_rk)}, possessions a game</em></div>
    </div>
    ${luckLines.length ? `<p class="lede">${luckLines.map(esc).join(" ")}</p>` : ""}
  </section>
  <section class="zone grid-2 extras"><div id="tOut"></div><div id="tNews"></div></section>
  <section class="zone grid-2">
    <div><h2>The four factors</h2><p class="lede">What wins possessions: making shots, not turning it over, second chances and getting to the line. Ranks are out of 30.</p>
      <div class="table-wrap"><table><thead><tr><th class="l nosort"></th><th class="nosort">Their offense</th><th class="nosort">Their defense</th></tr></thead><tbody>
      <tr><td class="l">Effective FG% (threes count 1.5)</td><td>${pct(t.efg)}${rk(t.efg_rk)}</td><td>${pct(t.opp_efg)}${rk(t.opp_efg_rk)}</td></tr>
      <tr><td class="l">Turnovers per possession</td><td>${pct(t.tov)}${rk(t.tov_rk)}</td><td>${pct(t.opp_tov)}${rk(t.opp_tov_rk)}</td></tr>
      <tr><td class="l">Rebounding (own misses / their misses)</td><td>${pct(t.orb)}${rk(t.orb_rk)}</td><td>${pct(t.drb)}${rk(t.drb_rk)}</td></tr>
      <tr><td class="l">Free throws per shot</td><td>${num(t.ftr, 3)}${rk(t.ftr_rk)}</td><td>${num(t.opp_ftr, 3)}${rk(t.opp_ftr_rk)}</td></tr>
      <tr><td class="l">Points a shot usually produces</td><td>${num(t.xpps, 3)}${rk(t.xpps_rk)}</td><td>${num(t.opp_xpps, 3)}${rk(t.opp_xpps_rk)}</td></tr>
      </tbody></table></div></div>
    <div><div class="head-row"><h2 class="grow">Where the shots come from</h2><div class="seg" role="group" aria-label="Shots">
      <button type="button" data-side="for" aria-pressed="${S.zoneSide === "for"}">Theirs</button><button type="button" data-side="against" aria-pressed="${S.zoneSide === "against"}">Against them</button></div></div>
      <div id="tZones"></div></div>
  </section>
  <section class="zone"><h2>Players</h2><p class="lede">Usage is the share of the team's shots, free throws and turnovers a player uses while he's on the floor. On/off is the team's net rating with him on minus with him off: noisy, and it rides on who he plays with.</p><div id="tPlayers"></div></section>
  <section class="zone"><h2>Lineups they trust</h2><p class="lede">Five-man groups with the most possessions together. Even the most-used lineups play only a few hundred possessions, so treat the ratings as hints.</p><div id="tLineups"></div></section>
  <section class="zone"><h2>Results</h2><p class="lede">Every game, with how often the shots each team got would have won it.</p><div id="tResults"></div></section>`;
  $("#mineBtn").addEventListener("click", () => { store.set("board-team", mine ? "" : abbr); applyTeamButton(); renderTeam(view, abbr); });
  if (T.season === D.meta.current) teamExtras(abbr).then(() => { const x = $(".extras"); if (x && !x.children.length) x.remove(); });
  else $(".extras")?.remove();
  const drawZones = () => { $("#tZones").innerHTML = zonesTable(S.zoneSide === "for" ? T.zones_for : T.zones_against, S.zoneSide === "for" ? "Their" : "Opp"); };
  $$("[data-side]", view).forEach((b) => b.addEventListener("click", () => { S.zoneSide = b.dataset.side; $$("[data-side]", view).forEach((x) => x.setAttribute("aria-pressed", x === b)); drawZones(); }));
  drawZones();
  const pSort = { key: "mpg", dir: -1 };
  const pcols = [
    { key: "name", label: "Player", cls: "l", fmt: (r) => playerLink(r.player_id, r.name) },
    { key: "gp", label: "GP" }, { key: "mpg", label: "MPG", fmt: (r) => num(r.mpg) },
    { key: "pts_pg", label: "PTS", fmt: (r) => num(r.pts_pg) }, { key: "reb_pg", label: "REB", fmt: (r) => num(r.reb_pg) },
    { key: "ast_pg", label: "AST", fmt: (r) => num(r.ast_pg) }, { key: "usage", label: "Usage", fmt: (r) => pct(r.usage) },
    { key: "ts", label: "TS%", fmt: (r) => pct(r.ts) },
    { key: "shotmaking", label: "Shot-making", title: "Points per shot above what his looks usually produce", fmt: (r) => (r.shots >= 50 ? `<span class="${cls(r.shotmaking)}">${signed(r.shotmaking, 2)}</span>` : "–") },
    { key: "on_off", label: "On/off", fmt: (r) => (r.poss_on >= 300 ? `<span class="${cls(r.on_off)}">${signed(r.on_off)}</span>` : "–") },
  ];
  const drawP = () => { $("#tPlayers").innerHTML = table(sortRows(T.players, pSort), pcols, pSort); bindSort($("#tPlayers"), pSort, drawP); };
  drawP();
  $("#tLineups").innerHTML = T.lineups.length ? table(T.lineups, [
    { key: "players", label: "Lineup", cls: "l", nosort: true },
    { key: "min", label: "Min", nosort: true, fmt: (r) => num(r.min, 0) }, { key: "poss", label: "Poss", nosort: true, fmt: (r) => num(r.poss, 0) },
    { key: "ortg", label: "Off", nosort: true, fmt: (r) => num(r.ortg) }, { key: "drtg", label: "Def", nosort: true, fmt: (r) => num(r.drtg) },
    { key: "net", label: "Net", nosort: true, fmt: (r) => `<span class="${cls(r.net)}">${signed(r.net)}</span>` },
    { key: "xnet", label: "From shots", nosort: true, fmt: (r) => signed(r.xnet) },
  ]) : `<p class="note">No lineup has 40 possessions together yet.</p>`;
  $("#tResults").innerHTML = table([...res].reverse(), [
    { key: "date", label: "Date", cls: "l", nosort: true, fmt: (r) => `<a href="#game/${T.season}/${r.game_id}">${dateShort(r.date)}</a>` },
    { key: "opp", label: "Opponent", cls: "l", nosort: true, fmt: (r) => `${r.home ? "vs" : "at"} ${teamLink(r.opp)}` },
    { key: "own", label: "Result", nosort: true, fmt: (r) => `<b class="${r.own > r.opp_pts ? "good" : "bad"}">${r.own > r.opp_pts ? "W" : "L"}</b> ${r.own}–${r.opp_pts}${r.type === "playoffs" ? ' <span class="dim">playoffs</span>' : ""}` },
    { key: "win_x", label: "Shots said", nosort: true, title: "How often the shots each team got would have won it", fmt: (r) => (r.win_x == null ? "–" : `<span class="cellbar"><span>${pct(r.win_x, 0)}</span><span class="bar-track"><span class="bar-fill" style="width:${100 * r.win_x}%"></span></span></span>`) },
  ]);
}

// ------------------------------------------------------------------ Players
const PVIEWS = {
  scoring: { label: "Scoring", sort: "pts_pg", cols: [
    { key: "gp", label: "GP" }, { key: "mpg", label: "MPG", fmt: (r) => num(r.mpg) }, { key: "pts_pg", label: "PTS", fmt: (r) => num(r.pts_pg) },
    { key: "reb_pg", label: "REB", fmt: (r) => num(r.reb_pg) }, { key: "ast_pg", label: "AST", fmt: (r) => num(r.ast_pg) },
    { key: "fg3m_pg", label: "3PM", fmt: (r) => num(r.fg3m_pg) }, { key: "usage", label: "Usage", fmt: (r) => pct(r.usage) }, { key: "ts", label: "TS%", fmt: (r) => pct(r.ts) }] },
  shooting: { label: "Shooting", sort: "shotmaking", cols: [
    { key: "shots", label: "Shots" }, { key: "pps", label: "Pts/shot", fmt: (r) => num(r.pps, 2) },
    { key: "xpps", label: "Expected", title: "What his looks usually produce per shot", fmt: (r) => num(r.xpps, 2) },
    { key: "shotmaking", label: "Shot-making", fmt: (r) => `<span class="${cls(r.shotmaking)}">${signed(r.shotmaking, 2)}</span>` },
    { key: "share_rim", label: "At rim", fmt: (r) => pct(r.share_rim, 0) }, { key: "share3", label: "Threes", fmt: (r) => pct(r.share3, 0) },
    { key: "fg3_pct", label: "3P%", fmt: (r) => pct(r.fg3_pct) }, { key: "assisted_share", label: "Assisted", fmt: (r) => pct(r.assisted_share, 0) }] },
  impact: { label: "On/off", sort: "on_off", cols: [
    { key: "mpg", label: "MPG", fmt: (r) => num(r.mpg) }, { key: "poss_on", label: "Poss on", fmt: (r) => num(r.poss_on, 0) },
    { key: "on_net", label: "Net on", fmt: (r) => signed(r.on_net) }, { key: "off_net", label: "Net off", fmt: (r) => signed(r.off_net) },
    { key: "on_off", label: "On/off", fmt: (r) => `<span class="${cls(r.on_off)}">${signed(r.on_off)}</span>` },
    { key: "xon_off", label: "On/off, shots", title: "The same with shot-making luck taken out", fmt: (r) => signed(r.xon_off) }] },
  defense: { label: "Defense", sort: "defended_at_rim_fga", cols: [
    { key: "mpg", label: "MPG", fmt: (r) => num(r.mpg) }, { key: "defended_at_rim_fga", label: "Rim shots defended", fmt: (r) => num(r.defended_at_rim_fga, 0) },
    { key: "rim_dfg_pct", label: "Rim FG% allowed", fmt: (r) => pct(r.rim_dfg_pct) },
    { key: "rim_dfg_vs_lg", label: "vs league", fmt: (r) => `<span class="${cls(r.rim_dfg_vs_lg, true)}">${spct(r.rim_dfg_vs_lg)}</span>` },
    { key: "contested_shots_p36", label: "Contests/36", fmt: (r) => num(r.contested_shots_p36) },
    { key: "deflections_p36", label: "Deflections/36", fmt: (r) => num(r.deflections_p36) },
    { key: "stl_pg", label: "STL", fmt: (r) => num(r.stl_pg) }, { key: "blk_pg", label: "BLK", fmt: (r) => num(r.blk_pg) }] },
};

async function renderPlayersHome(view) {
  const P = await getJSON(`players.${S.season}.json`);
  const L = await league();
  const rows = P.players.map((r) => ({ ...r, share3: (r.share_corner3 || 0) + (r.share_above3 || 0) }));
  const maxGp = Math.max(...rows.map((r) => r.gp));
  if (S.pMin == null || S.pMin > maxGp) S.pMin = Math.max(1, Math.round(maxGp * 0.25));
  const teams = [...new Set(rows.map((r) => r.team))].sort();
  const fl = follows.list();
  view.innerHTML = `<section class="zone"><h1>Players</h1>
    <p class="lede">Search anyone, or sort the league by scoring, shooting against expectation, what happens with him on the floor, or rim defense.</p>
    ${earlyNote(L)}
    ${fl.length ? `<p class="lede">Following: ${fl.map((f) => `<a href="#players/${f.id}">${esc(f.name)}</a>`).join(", ")}</p>` : ""}
    <div class="controls">
      <input class="search" id="pq" type="search" placeholder="Find a player" value="${esc(S.pQ)}" aria-label="Find a player">
      <div class="seg" role="group" aria-label="View">${Object.entries(PVIEWS).map(([k, v]) => `<button type="button" data-pv="${k}" aria-pressed="${S.pView === k}">${v.label}</button>`).join("")}</div>
      <select class="pill" id="pteam" aria-label="Team"><option value="all">All teams</option>${teams.map((t) => `<option ${S.pTeam === t ? "selected" : ""}>${t}</option>`).join("")}</select>
      <label class="dim">at least <select class="pill" id="pmin" aria-label="Minimum games">${[1, 5, 10, 20, 40].filter((n) => n <= maxGp).concat(S.pMin).filter((v, i, a) => a.indexOf(v) === i).sort((a, b) => a - b).map((n) => `<option ${n === S.pMin ? "selected" : ""}>${n}</option>`).join("")}</select> games</label>
    </div>
    <div id="pTable"></div><button class="more" id="pMore" type="button">Show more</button>
    <p class="note">Shot-making: points per shot above what his looks usually produce, from where he shot, what kind of shot and how the play started. On/off needs a few hundred possessions before it means much. Rim defense comes from tracking and is noisy for anyone who doesn't guard the paint every night.</p></section>`;
  const mine = myTeam();
  const draw = () => {
    const v = PVIEWS[S.pView];
    const q = S.pQ.trim().toLowerCase();
    let f = rows.filter((r) => r.gp >= S.pMin && (S.pTeam === "all" || r.team === S.pTeam) && (!q || r.name.toLowerCase().includes(q)));
    if (S.pView === "shooting") f = f.filter((r) => r.shots >= Math.max(50, S.pMin * 6));
    if (S.pView === "impact") f = f.filter((r) => r.poss_on >= 200);
    if (S.pView === "defense") f = f.filter((r) => r.defended_at_rim_fga >= 30);
    const sorted = sortRows(f, S.pSort);
    const cols = [{ key: "name", label: "Player", cls: "l", fmt: (r) => playerLink(r.player_id, r.name) + (follows.has(r.player_id) ? ' <span class="good">●</span>' : "") },
      { key: "team", label: "Team", cls: "l", fmt: (r) => teamLink(r.team) }, ...v.cols];
    $("#pTable").innerHTML = table(sorted.slice(0, S.pLimit), cols, S.pSort, "pT", (r) => (r.team === mine ? "mine" : ""));
    $("#pMore").hidden = sorted.length <= S.pLimit;
    bindSort($("#pTable"), S.pSort, draw);
  };
  $("#pq").addEventListener("input", (e) => { S.pQ = e.target.value; S.pLimit = 60; draw(); });
  $("#pteam").addEventListener("change", (e) => { S.pTeam = e.target.value; draw(); });
  $("#pmin").addEventListener("change", (e) => { S.pMin = +e.target.value; draw(); });
  $("#pMore").addEventListener("click", () => { S.pLimit += 60; draw(); });
  $$("[data-pv]", view).forEach((b) => b.addEventListener("click", () => {
    S.pView = b.dataset.pv; S.pSort = { key: PVIEWS[S.pView].sort, dir: S.pView === "defense" ? -1 : -1 };
    $$("[data-pv]", view).forEach((x) => x.setAttribute("aria-pressed", x === b)); draw();
  }));
  draw();
}

function shotWords(made, three, p, distFt) {
  const kind = three ? "three" : distFt != null && distFt < 4 ? "shot at the rim" : "two";
  return `${made ? "Made" : "Missed"} a ${distFt != null ? Math.round(distFt) + "-ft " : ""}${kind}${p != null ? `, a look that goes in ${Math.round(100 * p)}% of the time` : ""}`;
}
const dist = (x, y) => Math.hypot(x - 25, y - 1);

async function renderPlayer(view, id) {
  let P;
  try { P = await getJSON(`player/${S.season}/${id}.json`); }
  catch (e) {
    const other = D.meta.seasons.find((s) => s.season !== S.season);
    view.innerHTML = `<a class="back" href="#players">All players</a><section class="zone"><h1>No ${seasonLabel(S.season)} games</h1><p class="lede">He hasn't played in ${seasonLabel(S.season)} yet.${other ? ` <a href="#" data-season="${other.season}">See ${other.label}</a>.` : ""}</p></section>`;
    return;
  }
  const b = P.bio, line = P.lines[P.lines.length - 1] || {};
  const log = P.log.map((r) => zip(P.log_cols, r));
  const reg = log.filter((r) => r.type === "regular");
  const tot = (k) => reg.reduce((s, r) => s + (r[k] || 0), 0);
  const gp = reg.length || 1;
  const teams = [...new Set(log.map((r) => r.team))];
  const L = await league();
  view.innerHTML = `<a class="back" href="#players">All players</a>
  <section class="zone"><div class="head-row"><h1 class="grow">${esc(b.name || "")}</h1>${followBtn({ id: P.id, name: b.name, team: teams[teams.length - 1] })}</div>
    <p class="lede">${teams.map((t) => `<a href="#teams/${t}">${t}</a>`).join(", ")}${b.position ? `, ${esc(b.position)}` : ""}${b.height_in ? `, ${heightFt(b.height_in)}` : ""}${b.jersey ? `, #${esc(b.jersey)}` : ""}${b.draft_year ? `. Drafted ${b.draft_year}, round ${b.draft_round}, pick ${b.draft_number}` : ""}${b.college ? `. ${esc(b.college)}` : ""}.</p>
    <div id="pInj"></div>
    <div class="strip">
      <div><b>${num(tot("pts") / gp)}</b><span>Points a game</span></div>
      <div><b>${num(tot("reb") / gp)}</b><span>Rebounds</span></div>
      <div><b>${num(tot("ast") / gp)}</b><span>Assists</span></div>
      <div><b>${num(tot("min") / gp)}</b><span>Minutes</span><em>${reg.length} games</em></div>
      <div><b>${pct(line.usage)}</b><span>Usage</span></div>
      <div><b>${pct(line.ts)}</b><span>True shooting</span></div>
    </div></section>
  <section class="zone grid-2 wide-left">
    <div><h2>Every shot</h2><svg id="pCourt"></svg>${Court.key()}<p class="shot-panel" id="pShot">Tap or hover a shot for the details.</p></div>
    <div><h2>How he scores</h2><p class="lede" id="pScoring"></p>${zonesTable(P.zones, "His")}</div>
  </section>
  <section class="zone" id="pOn"></section>
  <section class="zone" id="pDef"></section>
  <section class="zone" id="pNews"></section>
  <section class="zone"><h2>Game log</h2><div id="pLog"></div></section>`;
  if (P.season === D.meta.current) playerExtras(P.id); else $("#pNews")?.remove();
  const shots = P.shots.map((s) => ({ x: s[0], y: s[1], made: s[2], three: s[3], p: s[4] == null ? null : s[4] / 1000, g: log[s[5]] }));
  Court.draw($("#pCourt"), shots, {
    onPick(i) {
      const s = shots[i];
      $("#pShot").innerHTML = i < 0 ? "Tap or hover a shot for the details." :
        `${esc(shotWords(s.made, s.three, s.p, dist(s.x, s.y)))}. ${s.g ? `${dateShort(s.g.date)} ${s.g.home ? "vs" : "at"} ${esc(s.g.opp)}.` : ""}`;
    },
  });
  // how he scores, in words
  const lines = P.lines;
  if (line.shots >= 30) {
    const lg = L.league.pps;
    $("#pScoring").textContent = `His shots usually produce ${num(line.xpps, 2)} points each (the league average shot is worth ${num(lg, 2)}), and he's scored ${num(line.pps, 2)} a shot: ${Math.abs(line.shotmaking) < 0.02 ? "right about what those looks are worth." : `${num(Math.abs(line.shotmaking), 2)} ${line.shotmaking > 0 ? "more" : "less"} than those looks are worth${line.shots < 300 ? ", over a small sample" : ""}.`} ${line.assisted_share != null ? `${pct(line.assisted_share, 0)} of his makes were assisted.` : ""}`;
  } else $("#pScoring").textContent = "Not enough shots yet to say much.";
  // on/off
  if (line.poss_on >= 150) {
    $("#pOn").innerHTML = `<h2>With him on the floor</h2>
      <div class="strip"><div><b class="${cls(line.on_net)}">${signed(line.on_net)}</b><span>Team net rating with him on</span><em>${num(line.poss_on, 0)} possessions</em></div>
      <div><b>${signed(line.off_net)}</b><span>With him off</span></div>
      <div><b class="${cls(line.on_off)}">${signed(line.on_off)}</b><span>On/off</span></div>
      <div><b>${signed(line.xon_off)}</b><span>On/off from shots</span></div></div>
      <p class="note">On/off is the team's points per 100 possessions better than the opponent with him on the floor, minus with him off. It's honest but noisy: it rides on who he plays with and who's out when he sits.${lines.length > 1 ? " Shown for his latest team." : ""}</p>`;
  }
  if (line.defended_at_rim_fga >= 50) {
    $("#pDef").innerHTML = `<h2>Protecting the rim</h2>
      <div class="strip"><div><b>${num(line.defended_at_rim_fga, 0)}</b><span>Shots at the rim he defended</span></div>
      <div><b class="${cls(line.rim_dfg_vs_lg, true)}">${pct(line.rim_dfg_pct)}</b><span>Made against him</span><em>${spct(line.rim_dfg_vs_lg)} vs league</em></div>
      <div><b>${num(line.contested_shots_p36)}</b><span>Contests per 36 minutes</span></div>
      <div><b>${num(line.deflections_p36)}</b><span>Deflections per 36</span></div></div>
      <p class="note">From player tracking. A few hundred shots at the rim swing several points of FG% on luck alone, so it's a lean, not a verdict.</p>`;
  }
  $("#pLog").innerHTML = table([...log].reverse(), [
    { key: "date", label: "Date", cls: "l", nosort: true, fmt: (r) => `<a href="#game/${P.season}/${r.game_id}">${dateShort(r.date)}</a>${r.type === "playoffs" ? ' <span class="dim">PO</span>' : ""}` },
    { key: "opp", label: "Opp", cls: "l", nosort: true, fmt: (r) => `${r.home ? "vs" : "at"} ${teamLink(r.opp)}` },
    { key: "own", label: "Result", nosort: true, fmt: (r) => `${r.own > r.opp_pts ? "W" : "L"} ${r.own}–${r.opp_pts}` },
    { key: "min", label: "Min", nosort: true, fmt: (r) => num(r.min, 0) }, { key: "pts", label: "Pts", nosort: true },
    { key: "reb", label: "Reb", nosort: true }, { key: "ast", label: "Ast", nosort: true },
    { key: "fgm", label: "FG", nosort: true, fmt: (r) => `${r.fgm}-${r.fga}` }, { key: "fg3m", label: "3PT", nosort: true, fmt: (r) => `${r.fg3m}-${r.fg3a}` },
    { key: "ftm", label: "FT", nosort: true, fmt: (r) => `${r.ftm}-${r.fta}` }, { key: "pm", label: "+/−", nosort: true, fmt: (r) => signed(r.pm, 0) },
    { key: "usage", label: "Usage", nosort: true, fmt: (r) => pct(r.usage, 0) },
  ]);
}

// ------------------------------------------------------------------ Games
async function renderGames(view) {
  const G = await getJSON(`games.${S.season}.json`);
  const games = G.games.map((r) => zip(G.cols, r));
  const mine = myTeam();
  const list = S.gTeam && mine ? games.filter((g) => g.home === mine || g.away === mine) : games;
  const days = [...new Set(list.map((g) => g.date))];
  const shown = days.slice(0, S.gDays);
  view.innerHTML = `<section class="zone"><h1>Games</h1>
    <p class="lede">Every game of ${seasonLabel(S.season)}, newest first. "Shots said" is how often the shots each team got would have won it: replay every trip with the same first shots, second chances at each team's usual rate and free throws as they went.</p>
    ${mine ? `<div class="controls"><div class="seg" role="group"><button type="button" data-gt="0" aria-pressed="${!S.gTeam}">All games</button><button type="button" data-gt="1" aria-pressed="${S.gTeam}">${esc(mine)} only</button></div></div>` : ""}
    ${S.season === D.meta.current ? `<div id="gToday"></div>` : ""}
    ${shown.map((d) => `<h2 class="day">${dateLong(d)}</h2><div class="game-list">${list.filter((g) => g.date === d).map(gameRow).join("")}</div>`).join("")}
    ${days.length > shown.length ? `<button class="more" id="gMore" type="button">Earlier games</button>` : ""}</section>`;
  renderToday();
  $("#gMore")?.addEventListener("click", () => { S.gDays += 7; renderGames(view); });
  $$("[data-gt]", view).forEach((b) => b.addEventListener("click", () => { S.gTeam = b.dataset.gt === "1"; S.gDays = 7; renderGames(view); }));
}
function gameRow(g) {
  const hw = g.hs > g.as;
  const w = g.win_home;
  return `<a class="game-row" href="#game/${S.season}/${g.id}">
    <span class="t ${hw ? "lost" : ""}">${esc(g.away)}</span><span class="s ${hw ? "lost" : ""}">${g.as}</span>
    <span class="t ${hw ? "" : "lost"}">${esc(g.home)}</span><span class="s ${hw ? "" : "lost"}">${g.hs}</span>
    <span class="meta">${g.ot ? (g.ot > 1 ? g.ot + "OT. " : "OT. ") : ""}${g.type === "playoffs" ? "Playoffs. " : g.type === "ist" ? "NBA Cup final. " : ""}${w == null ? "" : `Shots said ${w >= 0.5 ? esc(g.home) : esc(g.away)} ${pct(Math.max(w, 1 - w), 0)}`}</span></a>`;
}
function clockOf(t) {
  const p = t < 2880 ? Math.floor(t / 720) + 1 : 5 + Math.floor((t - 2880) / 300);
  const start = p <= 4 ? (p - 1) * 720 : 2880 + (p - 5) * 300, len = p <= 4 ? 720 : 300;
  const left = Math.max(0, len - (t - start)), m = Math.floor(left / 60), s = Math.floor(left % 60);
  return `${p <= 4 ? "Q" + p : p === 5 ? "OT" : "OT" + (p - 4)} ${m}:${String(s).padStart(2, "0")}`;
}
async function renderGame(view, season, id) {
  const g = await getJSON(`game/${season}/${id}.json`);
  const hw = g.home_score > g.away_score;
  const qs = Math.max(g.quarters.home.length, g.quarters.away.length);
  const qlab = (i) => (i < 4 ? `Q${i + 1}` : i === 4 ? "OT" : `${i - 3}OT`);
  const shots = g.shots.map((r) => zip(g.shot_cols, r));
  const w = g.win_home;
  view.innerHTML = `<a class="back" href="#games">All games</a>
  <section class="zone">
    <div class="score-head"><div class="side ${hw ? "lost" : ""}"><a class="who" href="#teams/${g.away}">${esc(g.away)}</a><div class="pts">${g.away_score}</div></div>
      <div class="mid">${g.ot ? (g.ot > 1 ? g.ot + " OT" : "OT") : "Final"}<br>${dateShort(g.date)}${g.tip_utc ? `, ${tipTime(g.tip_utc)}` : ""}</div>
      <div class="side r ${hw ? "" : "lost"}"><a class="who" href="#teams/${g.home}">${esc(g.home)}</a><div class="pts">${g.home_score}</div></div></div>
    <div class="table-wrap" style="max-width:520px;margin-top:16px"><table><thead><tr><th class="l nosort"></th>${Array.from({ length: qs }, (_, i) => `<th class="nosort">${qlab(i)}</th>`).join("")}<th class="nosort">Final</th></tr></thead><tbody>
      <tr><td class="l">${esc(g.away)}</td>${g.quarters.away.map((v) => `<td>${v ?? ""}</td>`).join("")}<td><b>${g.away_score}</b></td></tr>
      <tr><td class="l">${esc(g.home)}</td>${g.quarters.home.map((v) => `<td>${v ?? ""}</td>`).join("")}<td><b>${g.home_score}</b></td></tr></tbody></table></div>
  </section>
  <section class="zone" id="gHigh"></section>
  <section class="zone"><h2>Did the shots agree?</h2>
    ${w == null ? "" : `<div class="deserve"><span>${esc(g.away)} ${pct(1 - w, 0)}</span><div class="track" role="img" aria-label="${esc(g.home)} ${pct(w, 0)}"><span style="width:${100 * (1 - w)}%;background:var(--ink-2)"></span><span style="width:${100 * w}%"></span></div><span>${esc(g.home)} ${pct(w, 0)}</span></div>`}
    <p class="lede">${w == null ? "" : `Replay this game on the same shots and ${esc(w >= 0.5 ? g.home : g.away)} wins ${pct(Math.max(w, 1 - w), 0)} of the time. `}Their shots were worth ${num(g.x_home, 0)} points to ${num(g.x_away, 0)} for ${esc(g.away)}, free throws included as they went.${(w >= 0.5) !== hw && w != null ? ` ${esc(hw ? g.home : g.away)} won it anyway: the shots fell their way.` : ""}</p>
    <div id="gFlow"></div>
    <p class="legend"><span><i></i>Score margin (${esc(g.home)} ahead above the line)</span><span><i class="x"></i>What the shots were worth</span></p>
  </section>
  <section class="zone"><h2>Every shot</h2>
    <div class="courts-2"><div><h3>${esc(g.away)}</h3><svg id="cAway"></svg></div><div><h3>${esc(g.home)}</h3><svg id="cHome"></svg></div></div>
    ${Court.key()}<p class="shot-panel" id="gShot">Tap or hover a shot for the details.</p></section>
  <section class="zone"><h2>Box score</h2><h3 style="margin:14px 0 6px">${esc(g.away)}</h3><div id="bAway"></div><h3 style="margin:20px 0 6px">${esc(g.home)}</h3><div id="bHome"></div>
    <p class="note">Minutes come from our own count of who was on the floor, play by play.</p></section>`;
  $("#gFlow").innerHTML = flowChart(g, shots);
  gameHighlight(g.id);
  const name = (id) => g.names[id] || "";
  [["cAway", 1], ["cHome", 0]].forEach(([el, away]) => {
    const list = shots.filter((s) => s.away === away && !s.heave).map((s) => ({ ...s, p: s.p_milli == null ? null : s.p_milli / 1000 }));
    Court.draw($("#" + el), list, {
      onPick(i) {
        const s = list[i];
        $("#gShot").innerHTML = i < 0 ? "Tap or hover a shot for the details." :
          `${clockOf(s.t)}. ${esc(name(s.shooter))}: ${esc(shotWords(s.made, s.three, s.p, dist(s.x, s.y)).replace(/^./, (c) => c.toLowerCase()))}.`;
      },
    });
  });
  const bcols = [
    { key: "name", label: "Player", cls: "l", nosort: true, fmt: (r) => `${playerLink(r.id, r.name)}${r.starter ? "" : ' <span class="dim">bench</span>'}` },
    { key: "min", label: "Min", nosort: true, fmt: (r) => num(r.min, 0) }, { key: "pts", label: "Pts", nosort: true },
    { key: "reb", label: "Reb", nosort: true }, { key: "ast", label: "Ast", nosort: true }, { key: "stl", label: "Stl", nosort: true },
    { key: "blk", label: "Blk", nosort: true }, { key: "tov", label: "TO", nosort: true },
    { key: "fgm", label: "FG", nosort: true, fmt: (r) => `${r.fgm}-${r.fga}` }, { key: "fg3m", label: "3PT", nosort: true, fmt: (r) => `${r.fg3m}-${r.fg3a}` },
    { key: "ftm", label: "FT", nosort: true, fmt: (r) => `${r.ftm}-${r.fta}` }, { key: "pm", label: "+/−", nosort: true, fmt: (r) => signed(r.pm, 0) },
  ];
  $("#bAway").innerHTML = table(g.box.away.map((r) => zip(g.box_cols, r)), bcols);
  $("#bHome").innerHTML = table(g.box.home.map((r) => zip(g.box_cols, r)), bcols);
}
function flowChart(g, shots) {
  const W = Math.max(320, Math.min(1000, ($("#view").clientWidth || 900) - 32)), H = 220, m = { l: 36, r: 10, t: 12, b: 26 };
  const end = 2880 + 300 * g.ot, stop = g.now_t != null ? Math.min(g.now_t, end) : end;   // live games stop at the last play
  // actual margin from the scoring flow; expected from each trip's shots plus free throws as they went
  const act = [[0, 0]].concat(g.flow.map(([t, h, a]) => [t, h - a])).concat([[stop, g.home_score - g.away_score]]);
  const ev = shots.filter((s) => s.xtrip_milli).map((s) => [s.t, (s.away ? -1 : 1) * s.xtrip_milli / 1000])
    .concat(g.fts.filter((f) => f[2]).map((f) => [f[0], f[1] ? -1 : 1])).sort((a, b) => a[0] - b[0]);
  let cum = 0;
  const xp = [[0, 0]].concat(ev.map(([t, v]) => [t, (cum += v)])).concat([[stop, cum]]);
  const ys = act.map((p) => p[1]).concat(xp.map((p) => p[1]));
  const lim = Math.max(8, Math.ceil(Math.max(...ys.map(Math.abs)) / 5) * 5);
  const X = (t) => m.l + (t / end) * (W - m.l - m.r), Y = (v) => m.t + ((lim - v) / (2 * lim)) * (H - m.t - m.b);
  const step = (pts) => pts.map(([t, v], i) => (i ? `H${X(t).toFixed(1)}V${Y(v).toFixed(1)}` : `M${X(t).toFixed(1)} ${Y(v).toFixed(1)}`)).join("");
  const line = (pts) => pts.map(([t, v], i) => `${i ? "L" : "M"}${X(t).toFixed(1)} ${Y(v).toFixed(1)}`).join("");
  let grid = "";
  for (let q = 0; q <= 4 + g.ot; q++) { const t = q <= 4 ? q * 720 : 2880 + (q - 4) * 300; grid += `<line x1="${X(t)}" x2="${X(t)}" y1="${m.t}" y2="${H - m.b}"/>`; if (q < 4 + g.ot) grid += `<text x="${X(t + (q < 4 ? 360 : 150))}" y="${H - 8}" text-anchor="middle">${q < 4 ? "Q" + (q + 1) : "OT"}</text>`; }
  for (const v of [-lim, -lim / 2, lim / 2, lim]) grid += `<text x="${m.l - 6}" y="${Y(v) + 4}" text-anchor="end">${v > 0 ? "+" : ""}${v}</text>`;
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Score margin through the game"><g class="grid">${grid}</g>
    <line class="zero" x1="${m.l}" x2="${W - m.r}" y1="${Y(0)}" y2="${Y(0)}"/>
    <text x="${m.l + 4}" y="${m.t + 12}" class="hand-blue">${esc(g.home)} ahead</text><text x="${m.l + 4}" y="${H - m.b - 6}" class="hand">${esc(g.away)} ahead</text>
    <path class="line-x" d="${line(xp)}"/><path class="line-actual" d="${step(act)}"/></svg>`;
}

// ------------------------------------------------------------------ router and masthead
const ROUTES = { tonight: renderTonight, pulse: renderPulse, league: renderLeague, teams: renderTeamsHome, players: renderPlayersHome, games: renderGames, news: renderNews };
async function route() {
  const view = $("#view");
  const [tab, a, b] = (location.hash.replace(/^#/, "") || "tonight").split("/");
  const tabName = tab === "game" || tab === "live" ? "games" : tab === "preview" ? "tonight" : tab;
  $$(".tabs a").forEach((x) => (x.getAttribute("aria-current") === "page" ? x.removeAttribute("aria-current") : 0));
  $(`.tabs a[data-tab="${tabName}"]`)?.setAttribute("aria-current", "page");
  view.innerHTML = `<p class="loading">Loading</p>`;
  try {
    if (tab === "teams" && a) await renderTeam(view, a.toUpperCase());
    else if (tab === "players" && a) await renderPlayer(view, a);
    else if (tab === "game" && a && b) await renderGame(view, a, b);
    else if (tab === "about") renderAbout(view, a);
    else if (tab === "news") await renderNews(view, a);
    else if (tab === "live" && a) await renderLive(view, a);
    else if (tab === "preview" && a) await renderPreview(view, a);
    else await (ROUTES[tab] || renderLeague)(view);
  } catch (e) {
    console.error(e);
    view.innerHTML = `<section class="zone"><h1>That page didn't load</h1><p class="lede">We couldn't load the numbers for it (${esc(e.message)}). Try again in a minute, or start from <a href="#league">the league</a>.</p></section>`;
  }
  if (!location.hash.includes("/") || tab === "game" || tab === "live" || tab === "preview") window.scrollTo(0, 0);
}
function setSeason(s) {
  S.season = +s; store.set("board-season", String(s)); S.pMin = null;
  $("#seasonPick").value = String(s); freshness(); route();
}
function freshness() {
  const m = D.meta, cur = m.seasons.find((x) => x.season === S.season);
  const up = new Date(m.updated_utc);
  $("#freshness").textContent = `Updated ${up.toLocaleDateString("en-US", { month: "short", day: "numeric" })}, ${up.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}. ${cur ? `${cur.label}: ${cur.games} games` : ""}`;
}
function applyTheme() {
  const t = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  $("#themeToggle").textContent = t === "dark" ? "Whiteboard" : "Chalkboard";
}
async function init() {
  try { D.meta = await getJSON("meta.json"); }
  catch (e) { $("#view").innerHTML = `<section class="zone"><h1>No numbers yet</h1><p class="lede">The first build hasn't finished. Check back after the next morning update.</p></section>`; return; }
  const saved = +store.get("board-season");
  S.season = D.meta.seasons.some((x) => x.season === saved) ? saved : D.meta.current;
  $("#seasonPick").innerHTML = D.meta.seasons.map((s) => `<option value="${s.season}">${s.label}</option>`).join("");
  $("#seasonPick").value = String(S.season);
  $("#seasonPick").addEventListener("change", (e) => setSeason(e.target.value));
  $("#teamBtn").addEventListener("click", () => openTeamPicker());
  $("#themeToggle").addEventListener("click", () => {
    const cur = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = cur === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next; store.set("board-theme", next); applyTheme();
  });
  applyTheme(); applyTeamButton(); freshness();
  window.addEventListener("hashchange", route);
  liveInit();
  route();
}
init();
