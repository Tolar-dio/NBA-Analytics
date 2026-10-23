/* The Board's live layer. Scores, box scores and plays come from our relay (meta.live_url, a Cloudflare Worker that
   holds the data key), never straight from the data provider. Without a relay configured, none of this shows.

   - a strip of yesterday's late games and today's games under the masthead, every page
   - Today on the Games tab
   - #live/<id>: a game as it happens, with the score, what the shots say so far, both shot charts and box scores

   Live shots are valued with a lookup table (make rate by zone and shot description, data/shotvalue.json), since
   the full shot model only runs in the nightly build; per trip, as on the game pages. */
"use strict";

const Live = { url: null, scores: null, timer: null, gameTimer: null, sv: null, failed: 0 };
const LIVE_STATES = new Set(["in_progress", "delayed", "suspended"]);

async function liveFetch(path) {
  const r = await fetch(Live.url.replace(/\/$/, "") + path, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
}

// ------------------------------------------------------------------ scores strip
function liveInit() {
  Live.url = D.meta && D.meta.live_url;
  if (!Live.url) return;
  pollScores();
  document.addEventListener("visibilitychange", () => { if (!document.hidden) pollScores(); });
}
async function pollScores() {
  clearTimeout(Live.timer);
  if (document.hidden) return;
  try { Live.scores = await liveFetch("/scores"); Live.failed = 0; }
  catch (e) { Live.failed++; }
  renderStrip();
  if (location.hash.replace(/^#/, "").split("/")[0] === "games") renderToday();
  const games = (Live.scores && Live.scores.games) || [];
  const soon = games.some((g) => g.state === "scheduled" && g.tip && new Date(g.tip) - Date.now() < 45 * 60000);
  const live = games.some((g) => LIVE_STATES.has(g.state));
  // every 60 s while games are on: the relay's free tier is 100,000 requests a day across all visitors
  Live.timer = setTimeout(pollScores, live || soon ? 60000 : Live.failed ? 120000 : 300000);
}
function stripGames() {
  if (!Live.scores) return [];
  const today = Live.scores.today;
  // today's games, plus last night's that are still going or ended in the last three hours
  return Live.scores.games.filter((g) => g.date === today || LIVE_STATES.has(g.state)
    || (g.state === "final" && g.tip && Date.now() - new Date(g.tip) < 6 * 3600e3))
    .sort((a, b) => (LIVE_STATES.has(b.state) - LIVE_STATES.has(a.state)) || String(a.tip).localeCompare(String(b.tip)));
}
function liveStatus(g) {
  if (LIVE_STATES.has(g.state)) {
    if (/half/i.test(g.status)) return "Halftime";
    const q = g.period > 4 ? (g.period === 5 ? "OT" : `${g.period - 4}OT`) : `Q${g.period}`;
    return g.time && g.time !== "Final" ? `${q} ${g.time}` : q;
  }
  if (g.state === "final") return g.period > 4 ? (g.period === 5 ? "Final/OT" : `Final/${g.period - 4}OT`) : "Final";
  if (g.state === "postponed" || g.state === "canceled") return g.state === "postponed" ? "Postponed" : "Canceled";
  return g.tip ? tipTime(g.tip).replace(/:00 /, " ") : g.status;
}
function renderStrip() {
  const el = $("#liveStrip");
  const games = stripGames();
  if (!el) return;
  if (!games.length) { el.hidden = true; return; }
  const mine = myTeam();
  el.hidden = false;
  el.innerHTML = `<div class="strip-inner">${games.map((g) => {
    const live = LIVE_STATES.has(g.state), started = live || g.state === "final";
    const hw = g.hs > g.as;
    return `<a class="sg ${live ? "on" : ""} ${g.home === mine || g.away === mine ? "mine" : ""}" href="#live/${g.id}">
      <span class="r ${started && hw && g.state === "final" ? "lost" : ""}">${esc(g.away)}${started ? ` <b>${g.as}</b>` : ""}</span>
      <span class="r ${started && !hw && g.state === "final" ? "lost" : ""}">${esc(g.home)}${started ? ` <b>${g.hs}</b>` : ""}</span>
      <span class="st">${live ? '<i class="dot"></i>' : ""}${esc(liveStatus(g))}</span></a>`;
  }).join("")}</div>`;
}

// ------------------------------------------------------------------ Today, on the Games tab
function renderToday() {
  const el = $("#gToday");
  if (!el) return;
  const games = stripGames();
  if (!games.length) { el.innerHTML = ""; return; }
  el.innerHTML = `<h2 class="day">Today</h2><div class="game-list">${games.map((g) => {
    const started = LIVE_STATES.has(g.state) || g.state === "final", hw = g.hs > g.as, fin = g.state === "final";
    return `<a class="game-row" href="#live/${g.id}">
      <span class="t ${fin && hw ? "lost" : ""}">${esc(g.away)}</span><span class="s ${fin && hw ? "lost" : ""}">${started ? g.as : ""}</span>
      <span class="t ${fin && !hw ? "lost" : ""}">${esc(g.home)}</span><span class="s ${fin && !hw ? "lost" : ""}">${started ? g.hs : ""}</span>
      <span class="meta">${LIVE_STATES.has(g.state) ? '<i class="dot"></i>' : ""}${esc(liveStatus(g))}</span></a>`;
  }).join("")}</div>`;
}

// ------------------------------------------------------------------ valuing live shots
function liveZone(x, y, value) {
  const d = Math.hypot(x - 25, y - 1), side = Math.abs(x - 25);
  if (value === 3) return side >= 21.5 && y <= 9 ? "c3" : d < 26 ? "ab3" : d < 30 ? "ab3 deep" : "ab3 far";
  return d < 3 ? "0-3" : d < 6 ? "3-6" : d < 10 ? "6-10" : d < 16 ? "10-16" : "16+2";
}
function shotP(s) {
  const sv = Live.sv;
  if (!sv || s.x == null || s.y == null) return null;
  const z = liveZone(s.x, s.y, s.value);
  return sv.rates[`${z}|${s.type}`] ?? sv.zones[z] ?? null;
}
function gameSec(period, clock) {
  const start = period <= 4 ? (period - 1) * 720 : 2880 + (period - 5) * 300;
  return start + (period <= 4 ? 720 : 300) - clock;
}

// the live feed in order, with each team's expected points by trip
function liveModel(G) {
  const c = G.play_cols, P = G.plays.map((r) => Object.fromEntries(c.map((k, i) => [k, r[i]])));
  P.forEach((p) => (p.t = gameSec(p.period, p.clock)));
  P.sort((a, b) => a.period - b.period || a.t - b.t || a.order - b.order);
  for (let i = 0; i + 1 < P.length; i++) {      // a rebound logged a beat before the miss it came off
    const a = P[i], b = P[i + 1];
    if ((a.kind === "o" || a.kind === "d") && b.kind === "s" && !b.made && a.t === b.t && !(a.kind === "o" && a.player === b.player)) { P[i] = b; P[i + 1] = a; }
  }
  const tr = (Live.sv && Live.sv.trips) || {}, pts = tr.points || 1.3;
  const rate = [tr.team?.[G.game.home] ?? tr.league ?? 0.23, tr.team?.[G.game.away] ?? tr.league ?? 0.23];
  const x = [0, 0], shots = [], fts = [], flow = [];
  let poss = -1, fresh = true, period = 0;
  for (const p of P) {
    if (p.period !== period) { period = p.period; fresh = true; }
    if (p.kind === "s" && !p.heave && p.side >= 0) {
      const first = fresh || p.side !== poss;
      poss = p.side; fresh = false;
      const pr = shotP(p);
      const xt = pr == null ? 0 : first ? pr * p.value + (1 - pr) * rate[p.side] * pts : 0;
      x[p.side] += xt;
      shots.push({ x: p.x, y: p.y, made: p.made, three: p.value === 3 ? 1 : 0, p: pr, t: p.t, away: p.side, shooter: p.player, xtrip_milli: Math.round(1000 * xt), type: p.type });
      if (p.made) fresh = true;
    } else if (p.kind === "f" && p.side >= 0) {
      fts.push([p.t, p.side, p.made]);
      if (p.made) x[p.side] += 1;
    } else if (p.kind === "d" || p.kind === "t") fresh = true;
    else if (p.kind === "o") { fresh = false; poss = p.side; }
    if (p.made && p.value > 0 && p.hs != null) flow.push([p.t, p.hs, p.as]);
  }
  return { x, shots, fts, flow, now: P.length ? P[P.length - 1].t : 0 };
}

// ------------------------------------------------------------------ the live game page
async function renderLive(view, id) {
  clearTimeout(Live.gameTimer);
  Live.url = Live.url || (D.meta && D.meta.live_url);
  if (!Live.url) { view.innerHTML = `<section class="zone"><h1>Live games aren't switched on yet</h1><p class="lede">Check back soon, or see <a href="#games">every finished game</a>.</p></section>`; return; }
  if (!Live.sv) { try { Live.sv = await getJSON("shotvalue.json"); } catch (e) { Live.sv = null; } }
  let G;
  try { G = await liveFetch(`/game?id=${encodeURIComponent(id)}`); }
  catch (e) { view.innerHTML = `<section class="zone"><h1>This game didn't load</h1><p class="lede">The live feed didn't answer. It usually comes back within a minute; this page will retry.</p></section>`; Live.gameTimer = setTimeout(() => routeIs("live", id) && renderLive(view, id), 60000); return; }
  const g = G.game, live = LIVE_STATES.has(g.state), fin = g.state === "final", started = live || fin;
  const M = liveModel(G);
  const keep = Court && $("#lvAway") ? { scroll: window.scrollY } : null;
  const hw = g.hs > g.as;
  const qn = Math.max(g.hq.length, g.aq.length, 4);
  const qlab = (i) => (i < 4 ? `Q${i + 1}` : i === 4 ? "OT" : `${i - 3}OT`);
  const built = fin && D.meta.seasons.some((s) => s.through >= g.date);
  const em = M.x[0] - M.x[1], am = g.hs - g.as;
  view.innerHTML = `<a class="back" href="#games">All games</a>
  <section class="zone">
    <div class="score-head"><div class="side ${fin && hw ? "lost" : ""}"><a class="who" href="#teams/${g.away}">${esc(g.away)}</a><div class="pts">${started ? g.as : ""}</div></div>
      <div class="mid">${live ? '<i class="dot"></i>' : ""}${esc(liveStatus(g))}<br>${g.date ? dateShort(g.date) : ""}</div>
      <div class="side r ${fin && !hw ? "lost" : ""}"><a class="who" href="#teams/${g.home}">${esc(g.home)}</a><div class="pts">${started ? g.hs : ""}</div></div></div>
    ${started ? `<div class="table-wrap" style="max-width:520px;margin-top:16px"><table><thead><tr><th class="l nosort"></th>${Array.from({ length: qn }, (_, i) => `<th class="nosort">${qlab(i)}</th>`).join("")}<th class="nosort">Total</th></tr></thead><tbody>
      <tr><td class="l">${esc(g.away)}</td>${Array.from({ length: qn }, (_, i) => `<td>${g.aq[i] ?? ""}</td>`).join("")}<td><b>${g.as}</b></td></tr>
      <tr><td class="l">${esc(g.home)}</td>${Array.from({ length: qn }, (_, i) => `<td>${g.hq[i] ?? ""}</td>`).join("")}<td><b>${g.hs}</b></td></tr></tbody></table></div>` : `<p class="lede">Tips off ${g.tip ? tipTime(g.tip) : "soon"}. This page fills in once the game starts.</p>`}
    ${live ? `<p class="note">Updates every 30 seconds.</p>` : ""}${built ? `<p class="note">The full game page, with every shot valued by our model: <a href="#game/${seasonOf(g.date)}/${g.id}">open it</a>.</p>` : ""}
  </section>
  ${started && M.shots.length ? `<section class="zone"><h2>What the shots say${fin ? "" : " so far"}</h2>
    <p class="lede">Their shots have been worth ${num(M.x[1], 0)} points to ${esc(g.away)} and ${num(M.x[0], 0)} to ${esc(g.home)}, free throws as they went: ${Math.abs(em) < 1 ? "dead even" : `${esc(em > 0 ? g.home : g.away)} by ${num(Math.abs(em), 0)}`}, against ${Math.abs(am) < 1 ? "a tie" : `${esc(am > 0 ? g.home : g.away)} by ${Math.abs(am)}`} on the scoreboard.</p>
    <div id="lvFlow"></div>
    <p class="legend"><span><i></i>Score margin (${esc(g.home)} ahead above the line)</span><span><i class="x"></i>What the shots were worth</span></p></section>
  <section class="zone"><h2>Every shot</h2>
    <div class="courts-2"><div><h3>${esc(g.away)}</h3><svg id="lvAway"></svg></div><div><h3>${esc(g.home)}</h3><svg id="lvHome"></svg></div></div>
    ${Court.key()}<p class="shot-panel" id="lvShot">Tap or hover a shot for the details.</p></section>` : ""}
  ${started ? `<section class="zone"><h2>Box score</h2><h3 style="margin:14px 0 6px">${esc(g.away)}</h3><div id="lvBA"></div><h3 style="margin:20px 0 6px">${esc(g.home)}</h3><div id="lvBH"></div></section>` : ""}`;
  if (started && M.shots.length) {
    const fg = { home: g.home, away: g.away, home_score: g.hs, away_score: g.as, ot: Math.max(0, (g.period || 4) - 4), flow: M.flow, fts: M.fts,
      now_t: fin ? null : M.now };
    $("#lvFlow").innerHTML = flowChart(fg, M.shots);
    [["lvAway", 1], ["lvHome", 0]].forEach(([el, side]) => {
      const list = M.shots.filter((s) => s.away === side && s.x != null);
      Court.draw($("#" + el), list, {
        onPick(i) {
          const s = list[i];
          $("#lvShot").innerHTML = i < 0 ? "Tap or hover a shot for the details." :
            `${clockOf(s.t)}. ${esc(G.names[s.shooter] || "")}: ${esc(shotWords(s.made, s.three, s.p, dist(s.x, s.y)).replace(/^./, (ch) => ch.toLowerCase()))}.`;
        },
      });
    });
  }
  if (started) {
    const cols = [
      { key: "name", label: "Player", cls: "l", nosort: true, fmt: (r) => playerLink(r.id, r.name) },
      { key: "min", label: "Min", nosort: true, fmt: (r) => esc(String(r.min).replace(/:\d+$/, "")) }, { key: "pts", label: "Pts", nosort: true },
      { key: "reb", label: "Reb", nosort: true }, { key: "ast", label: "Ast", nosort: true }, { key: "stl", label: "Stl", nosort: true },
      { key: "blk", label: "Blk", nosort: true }, { key: "tov", label: "TO", nosort: true },
      { key: "fgm", label: "FG", nosort: true, fmt: (r) => `${r.fgm}-${r.fga}` }, { key: "fg3m", label: "3PT", nosort: true, fmt: (r) => `${r.fg3m}-${r.fg3a}` },
      { key: "ftm", label: "FT", nosort: true, fmt: (r) => `${r.ftm}-${r.fta}` }, { key: "pm", label: "+/−", nosort: true, fmt: (r) => (r.pm == null ? "–" : signed(r.pm, 0)) },
    ];
    const rows = (list) => list.map((r) => Object.fromEntries(G.box_cols.map((k, i) => [k, r[i]])));
    $("#lvBA").innerHTML = G.box.away.length ? table(rows(G.box.away), cols) : `<p class="note">No box score yet.</p>`;
    $("#lvBH").innerHTML = G.box.home.length ? table(rows(G.box.home), cols) : `<p class="note">No box score yet.</p>`;
  }
  if (keep) window.scrollTo(0, keep.scroll);
  if (live || (g.state === "scheduled" && g.tip && new Date(g.tip) - Date.now() < 3600e3)) {
    Live.gameTimer = setTimeout(() => routeIs("live", id) && renderLive(view, id), live ? 30000 : 60000);
  }
}
const seasonOf = (date) => (+date.slice(5, 7) >= 9 ? +date.slice(0, 4) : +date.slice(0, 4) - 1);
const routeIs = (tab, id) => location.hash.replace(/^#/, "").split("/")[0] === tab && location.hash.split("/")[1] === String(id);
