/* Tonight: the next day of games, a card for each, and a preview page per game (#preview/<id>).
   Cards and previews come from the build (tonight.json, preview/<id>.json); scores fill in from the live relay
   once games tip. */
"use strict";

const etToday = () => new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
const NICKS = { ATL: "Hawks", BOS: "Celtics", BKN: "Nets", CHA: "Hornets", CHI: "Bulls", CLE: "Cavaliers", DAL: "Mavericks", DEN: "Nuggets", DET: "Pistons", GSW: "Warriors", HOU: "Rockets", IND: "Pacers", LAC: "Clippers", LAL: "Lakers", MEM: "Grizzlies", MIA: "Heat", MIL: "Bucks", MIN: "Timberwolves", NOP: "Pelicans", NYK: "Knicks", OKC: "Thunder", ORL: "Magic", PHI: "76ers", PHX: "Suns", POR: "Trail Blazers", SAC: "Kings", SAS: "Spurs", TOR: "Raptors", UTA: "Jazz", WAS: "Wizards" };
const nick = (t) => NICKS[t] || t;
const lastName = (n) => { const p = String(n).split(" "); return p.length > 1 ? p.slice(1).join(" ") : n; };
const rec = (r) => `${r[0]}–${r[1]}`;
const GAMBLING = `Lines are the median across the sportsbooks we track, shown for information. Our own projections arrive with the game model. Gambling problem? Call 1-800-GAMBLER.`;

function lineShort(L, home, away) {
  if (!L || L.spread_home == null) return "";
  const s = L.spread_home, fav = s < 0 ? home : away;
  const spread = Math.abs(s) < 0.75 ? "Pick'em" : `${esc(fav)} by ${Math.abs(s)}`;
  return `${spread}${L.total ? `, total ${L.total}` : ""}`;
}
function liveGame(id) {
  return Live.scores && (Live.scores.games || []).find((g) => g.id === +id);
}
function pickSlate(T) {
  const today = etToday();
  return T.slates.find((s) => s.date >= today) || null;
}

async function renderTonight(view) {
  let T;
  try { T = await getJSON("tonight.json"); } catch (e) { T = { slates: [] }; }
  const slate = pickSlate(T);
  if (!slate) {
    view.innerHTML = `<section class="zone"><h1>Tonight</h1><p class="lede">No games on the schedule we have. See <a href="#games">every game so far</a>.</p></section>`;
    return;
  }
  const today = slate.date === etToday();
  const mine = myTeam();
  const games = [...slate.games].sort((a, b) => ((b.home === mine || b.away === mine) - (a.home === mine || a.away === mine)) || String(a.tip).localeCompare(String(b.tip)));
  const next = T.slates.find((s) => s.date > slate.date);
  const asOf = slate.games.map((g) => g.line && g.line.as_of).filter(Boolean).sort().pop();
  view.innerHTML = `<section class="zone"><h1>${today ? "Tonight" : esc(dateLong(slate.date))}</h1>
    <p class="lede">${today ? `${slate.games.length} games today` : `No games today. Next up, ${slate.games.length} games`}: the line, who's rested, who's out and what to watch in each. Times are in your time zone. Tap a game for the full preview.</p>
    <div class="tcards">${games.map((g) => tonightCard(g, mine)).join("")}</div>
    ${next && today ? `<h2 class="day">${esc(dateLong(next.date))}</h2><div class="game-list">${next.games.map((g) => `<a class="game-row" href="#preview/${g.id}">
      <span class="t">${esc(g.away)}</span><span class="s dim">${rec(g.rec[0])}</span><span class="t">${esc(g.home)}</span><span class="s dim">${rec(g.rec[1])}</span>
      <span class="meta">${esc(tipTime(g.tip).replace(/:00 /, " "))}${g.line ? `. ${lineShort(g.line, g.home, g.away)}` : ""}</span></a>`).join("")}</div>` : ""}
    <p class="note">${asOf ? `Lines as of ${esc(new Date(asOf).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }))}. ` : ""}${GAMBLING}</p></section>`;
  tonightLive();
}
function tonightCard(g, mine) {
  const out = [["away", g.away], ["home", g.home]].filter(([s]) => g.out[s].length)
    .map(([s, t]) => `${esc(t)}: ${g.out[s].map((n) => esc(lastName(n))).join(", ")}`).join(". ");
  return `<article class="tcard ${g.home === mine || g.away === mine ? "mine" : ""}" data-gid="${g.id}">
    <a class="tc-head" href="#preview/${g.id}">
      <span class="tc-t"><b>${esc(g.away)}</b> <span class="dim">${rec(g.rec[0])}</span></span><span class="tc-s" data-s="a"></span>
      <span class="tc-t"><b>${esc(g.home)}</b> <span class="dim">${rec(g.rec[1])}</span></span><span class="tc-s" data-s="h"></span>
      <span class="tc-st" data-st>${esc(tipTime(g.tip).replace(/:00 /, " "))}</span></a>
    <p class="tc-line">${g.line ? lineShort(g.line, g.home, g.away) : '<span class="dim">Line not posted yet</span>'}</p>
    ${g.stories.length ? `<ul class="tc-notes">${g.stories.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>` : ""}
    ${out ? `<p class="tc-out"><span class="bad">Out</span> ${out}</p>` : ""}
    <p class="tc-links"><a href="#preview/${g.id}">Preview</a><a href="#live/${g.id}" data-live hidden>Follow it live</a></p></article>`;
}
// called by the live layer after each scores poll
function tonightLive() {
  $$(".tcard[data-gid]").forEach((el) => {
    const g = liveGame(el.dataset.gid);
    if (!g) return;
    const on = LIVE_STATES.has(g.state), done = g.state === "final";
    el.classList.toggle("on", on);
    if (on || done) {
      $("[data-s=a]", el).textContent = g.as; $("[data-s=h]", el).textContent = g.hs;
      $("[data-st]", el).innerHTML = `${on ? '<i class="dot"></i>' : ""}${esc(liveStatus(g))}`;
      const l = $("[data-live]", el); l.hidden = false; l.textContent = on ? "Follow it live" : "Box score and shots";
      $(".tc-head", el).setAttribute("href", `#live/${g.id}`);
    }
  });
  const head = $("#pvLive");
  if (head) {
    const g = liveGame(head.dataset.gid);
    if (g && (LIVE_STATES.has(g.state) || g.state === "final")) {
      head.hidden = false;
      head.innerHTML = `<a href="#live/${g.id}">${LIVE_STATES.has(g.state) ? '<i class="dot"></i>' : ""}${esc(g.away)} ${g.as}, ${esc(g.home)} ${g.hs}: ${esc(liveStatus(g))}. ${LIVE_STATES.has(g.state) ? "Follow it live" : "Box score and every shot"}</a>`;
    }
  }
}

// ------------------------------------------------------------------ the preview
const MROWS = [
  ["Net rating", "net", (v) => signed(v), true],
  ["Offense, points per 100 possessions", "ortg", (v) => num(v), true],
  ["Defense, points allowed per 100", "drtg", (v) => num(v), false],
  ["Net rating from their shots", "x_net", (v) => signed(v), true],
  ["Pace, possessions a game", "pace", (v) => num(v), null],
  ["Effective FG%", "efg", (v) => pct(v), true],
  ["Turnovers per possession", "tov", (v) => pct(v), false],
  ["Offensive rebounding", "orb", (v) => pct(v), true],
  ["Free throws per shot", "ftr", (v) => num(v, 3), true],
  ["Opponents' effective FG%", "opp_efg", (v) => pct(v), false],
  ["Turnovers forced per possession", "opp_tov", (v) => pct(v), true],
  ["Defensive rebounding", "drb", (v) => pct(v), true],
  ["Points their shots usually produce", "xpps", (v) => num(v, 3), true],
  ["Points opponents' shots usually produce", "opp_xpps", (v) => num(v, 3), false],
];
function rkCell(rank, neutral) {
  if (!rank) return "";
  return `<span class="rk ${neutral ? "" : rank <= 8 ? "good" : rank >= 23 ? "bad" : ""}">${ordinal(rank)}</span>`;
}
function matchupTable(p, season) {
  const a = p.teams.away[season], h = p.teams.home[season];
  if (!a || !h) return `<p class="note">No numbers for that season.</p>`;
  return `<div class="table-wrap"><table class="mtable"><thead><tr><th class="l nosort"></th><th class="nosort">${esc(p.away)}</th><th class="nosort">${esc(p.home)}</th></tr></thead><tbody>
    ${MROWS.map(([label, k, f, dir]) => `<tr><td class="l">${label}</td><td>${a[k] == null ? "–" : f(a[k])}${rkCell(a[k + "_rk"], dir === null)}</td><td>${h[k] == null ? "–" : f(h[k])}${rkCell(h[k + "_rk"], dir === null)}</td></tr>`).join("")}
    </tbody></table></div><p class="note">${season === String(p.season) ? `This season: ${esc(p.away)} ${a.gp} games, ${esc(p.home)} ${h.gp}. Early numbers swing a lot.` : "Last season, before this year's roster changes."} Ranks are out of 30 (pace: 1st is fastest); blue is top eight, red bottom eight.</p>`;
}
const ZLAB = { rim: "At the rim", short: "Short range", mid: "Midrange twos", corner3: "Corner threes", above3: "Above-the-break threes" };
function zoneDuel(off, dfn, offT, dfnT, lgz) {
  // where this offense shoots against the league, next to where the other defense lets teams shoot
  if (!off || !dfn) return "";
  const W = 340, rowH = 34, H = 26 + rowH * 5, mid = 190, scale = 9;   // px per percentage point
  let g = "";
  Object.keys(ZLAB).forEach((z, i) => {
    const y = 26 + i * rowH, lg = lgz[z].share;
    const o = 100 * (off[z].share - lg), d = 100 * (dfn[z].share - lg);
    const bar = (v, dy, c) => { const w = Math.min(Math.abs(v) * scale, 140); return `<rect x="${v >= 0 ? mid : mid - w}" y="${y + dy}" width="${w.toFixed(1)}" height="9" class="${c}" rx="2"/>`; };
    g += `<text x="0" y="${y + 14}" class="zl">${ZLAB[z]}</text>${bar(o, 3, "zb-o")}${bar(d, 15, "zb-d")}
      <text x="${W}" y="${y + 11}" text-anchor="end" class="zv">${o >= 0 ? "+" : "−"}${Math.abs(o).toFixed(1)}</text><text x="${W}" y="${y + 23}" text-anchor="end" class="zv d">${d >= 0 ? "+" : "−"}${Math.abs(d).toFixed(1)}</text>`;
  });
  return `<svg class="zduel" viewBox="0 0 ${W} ${H}" role="img" aria-label="Where ${esc(offT)} shoots against where ${esc(dfnT)} allows shots">
    <text x="${mid - 4}" y="12" text-anchor="end" class="zh">less than league</text><text x="${mid + 4}" y="12" class="zh">more</text>
    <line x1="${mid}" x2="${mid}" y1="18" y2="${H}" class="zaxis"/>${g}</svg>
    <p class="legend"><span><i class="lo"></i>${esc(offT)} shoot from here</span><span><i class="ld"></i>${esc(dfnT)} allow shots from here</span></p>`;
}
function injuryBlock(list, team) {
  if (!list.length) return `<p class="note">Nobody listed.</p>`;
  return `<ul class="inj">${list.map((r) => {
    const w = r.without;
    const went = w && w.who.length ? `<br><span class="note-s">When he sat${w.season !== D.meta.current ? " last season" : ""} (${w.missed} games): ${w.who.map((x) => `${esc(lastName(x.name))} played ${num(x.without, 0)} minutes a game instead of ${num(x.with, 0)}`).join("; ")}.</span>` : "";
    return `<li><span class="${STATUS_CLS[r.status] || "dim"} st">${esc(r.status)}</span><span><a class="who" href="#players/${r.id}">${esc(r.name)}</a>${r.mpg >= 8 ? ` <span class="dim">${num(r.mpg, 0)} min a game</span>` : ""}${r.back ? ` <span class="dim">expected back ${esc(fmtBack(r.back))}</span>` : ""}<br><span class="note-s">${esc(r.note || "")}</span>${went}</span></li>`;
  }).join("")}</ul>`;
}
async function renderPreview(view, id) {
  let p;
  try { p = await getJSON(`preview/${id}.json`); }
  catch (e) {
    view.innerHTML = `<a class="back" href="#tonight">Tonight</a><section class="zone"><h1>No preview for this game</h1><p class="lede">Previews cover the next two days of games. Finished games are on <a href="#games">the Games tab</a>${Live.url ? `, or <a href="#live/${esc(id)}">follow this one live</a>` : ""}.</p></section>`;
    return;
  }
  const R = p.records, L = p.line, cur = String(p.season), prev = String(p.season - 1);
  S.pvSeason = S.pvSeason && p.teams.away[S.pvSeason] ? S.pvSeason : p.lead;
  const fav = L && L.spread_home != null ? (L.spread_home < 0 ? p.home : p.away) : null;
  const pf = L && L.p_home != null ? (fav === p.home ? L.p_home : 1 - L.p_home) : null;
  view.innerHTML = `<a class="back" href="#tonight">Tonight</a>
  <section class="zone">
    <div class="score-head"><div class="side"><a class="who" href="#teams/${p.away}">${esc(p.away)}</a><div class="rec">${R.away.w}–${R.away.l}</div></div>
      <div class="mid">${esc(dateShort(p.date))}<br>${esc(tipTime(p.tip))}</div>
      <div class="side r"><a class="who" href="#teams/${p.home}">${esc(p.home)}</a><div class="rec">${R.home.w}–${R.home.l}</div></div></div>
    <p class="pv-live" id="pvLive" data-gid="${p.id}" hidden></p>
    ${L && L.spread_home != null ? `<p class="lede pv-line"><b>The line:</b> ${Math.abs(L.spread_home) < 0.75 ? "a pick'em" : `the ${esc(nick(fav))} by ${Math.abs(L.spread_home)}`}${L.total ? `, total ${L.total}` : ""}.${pf ? ` With the bookmakers' margin taken out, that makes the ${esc(nick(fav))} about a ${Math.round(100 * pf)}% favorite.` : ""} <span class="dim">Median of ${L.books} sportsbooks, as of ${esc(new Date(L.as_of).toLocaleString("en-US", { weekday: "short", hour: "numeric", minute: "2-digit" }))}.</span></p>` : `<p class="lede dim">The line isn't posted yet; we check the books through the day.</p>`}
    ${p.stories.filter((s) => s.kind !== "market").length ? `<h2>Storylines</h2><ul class="stories-l">${p.stories.filter((s) => s.kind !== "market").map((s) => `<li>${esc(s.text)}</li>`).join("")}</ul>` : ""}
  </section>
  <section class="zone grid-2"><div><h2>${esc(nick(p.away))}: who's out</h2>${injuryBlock(p.injuries.away, p.away)}</div><div><h2>${esc(nick(p.home))}: who's out</h2>${injuryBlock(p.injuries.home, p.home)}</div></section>
  <section class="zone"><div class="head-row"><h2 class="grow">Side by side</h2><div class="seg" role="group" aria-label="Season">
      <button type="button" data-pv="${cur}" aria-pressed="${S.pvSeason === cur}">This season</button><button type="button" data-pv="${prev}" aria-pressed="${S.pvSeason === prev}">Last season</button></div></div>
    <div id="pvTable"></div></section>
  <section class="zone"><h2>Where the shots will come from</h2><p class="lede">Each offense's shot diet against the league, next to where the other defense lets teams shoot, in percentage points of all shots. When both bars point the same way, expect more of those shots.</p>
    <div class="grid-2"><div><h3>${esc(nick(p.away))} with the ball</h3><div id="pvZa"></div></div><div><h3>${esc(nick(p.home))} with the ball</h3><div id="pvZh"></div></div></div><p class="note" id="pvZnote"></p></section>
  <section class="zone grid-2"><div><h2>${esc(nick(p.away))} to watch</h2>${watchList(p.watch.away)}</div><div><h2>${esc(nick(p.home))} to watch</h2>${watchList(p.watch.home)}</div></section>
  ${p.meetings.length ? `<section class="zone"><h2>Recent meetings</h2><div class="game-list">${[...p.meetings].reverse().map((m) => {
    const hw = m.hs > m.as;
    return `<a class="game-row" href="#game/${m.season}/${m.id}"><span class="t ${hw ? "lost" : ""}">${esc(m.away)}</span><span class="s ${hw ? "lost" : ""}">${m.as}</span><span class="t ${hw ? "" : "lost"}">${esc(m.home)}</span><span class="s ${hw ? "" : "lost"}">${m.hs}</span><span class="meta">${esc(dateShort(m.date))}${m.date.slice(0, 4) !== p.date.slice(0, 4) || m.season !== p.season ? ` ${m.date.slice(0, 4)}` : ""}${m.type === "playoffs" ? ". Playoffs" : ""}${m.ot ? ". OT" : ""}</span></a>`;
  }).join("")}</div></section>` : ""}
  <section class="zone"><p class="note">${GAMBLING}</p></section>`;
  const draw = () => {
    $("#pvTable").innerHTML = matchupTable(p, S.pvSeason);
    const s = S.pvSeason, a = p.teams.away[s], h = p.teams.home[s], lgz = (p.league[s] || p.league[prev]).zones;
    $("#pvZa").innerHTML = a && h ? zoneDuel(a.zones_for, h.zones_against, p.away, p.home, lgz) : "";
    $("#pvZh").innerHTML = a && h ? zoneDuel(h.zones_for, a.zones_against, p.home, p.away, lgz) : "";
    $("#pvZnote").textContent = s === cur ? "This season's shots so far." : "Last season's shots.";
    $$("[data-pv]", view).forEach((b) => b.setAttribute("aria-pressed", b.dataset.pv === s));
  };
  $$("[data-pv]", view).forEach((b) => b.addEventListener("click", () => { S.pvSeason = b.dataset.pv; draw(); }));
  draw();
  tonightLive();
}
function watchList(list) {
  if (!list.length) return `<p class="note">Nobody stands out yet.</p>`;
  return `<ul class="watch">${list.map((w) => `<li><a class="who" href="#players/${w.id}">${esc(w.name)}</a><span>${esc(w.why)}</span></li>`).join("")}</ul>`;
}
