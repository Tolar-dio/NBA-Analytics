/* The Pulse: last night's best games, hot and cold against the shots, hot starts and what's behind them, new
   faces and changed roles, rookies, streaks, and teams running ahead of or behind their shots. All of it is
   written by the build from our own numbers (pulse.json). */
"use strict";

function pulseItem(x, mine, extra = "") {
  return `<li class="${x.team && x.team === mine ? "mine" : ""}"><a class="who" href="#players/${x.id}">${esc(x.name)}</a>${x.team ? ` <a class="chip" href="#teams/${x.team}">${esc(x.team)}</a>` : ""}${extra}<span>${esc(x.text)}</span></li>`;
}
function pulseList(list, mine, empty) {
  return list && list.length ? `<ul class="watch pulse">${list.map((x) => pulseItem(x, mine)).join("")}</ul>` : `<p class="note">${empty}</p>`;
}

async function renderPulse(view) {
  const P = await getJSON("pulse.json");
  const mine = myTeam();
  const ln = P.last_night;
  const perf = ln.players.map((p) => `<li class="perf ${p.team === mine ? "mine" : ""}">
      <div class="perf-h"><a class="who" href="#players/${p.id}">${esc(p.name)}</a> <span class="dim">${esc(p.team)} ${p.home ? "vs" : "at"} ${esc(p.opp)}${p.won == null ? "" : p.won ? ", won" : ", lost"}</span></div>
      <div class="perf-l"><b>${p.line.pts}</b> pts <b>${p.line.reb}</b> reb <b>${p.line.ast}</b> ast${p.line.stl >= 3 ? ` <b>${p.line.stl}</b> stl` : ""}${p.line.blk >= 3 ? ` <b>${p.line.blk}</b> blk` : ""}</div>
      <div class="dim perf-s">${esc(p.line.fg)} FG, ${esc(p.line.fg3)} 3PT, ${esc(p.line.ft)} FT, ${p.line.min} min. <a href="#game/${D.meta.current}/${p.game_id}">Game</a></div>
      ${p.notes.length ? `<div class="perf-n">${p.notes.map(esc).join(" ")}</div>` : ""}</li>`).join("");
  const rk = P.rookies;
  view.innerHTML = `<section class="zone"><h1>Pulse</h1>
    <p class="lede">Who's playing well, who's changed roles and what's behind it. Hot and cold are measured against what the same shots usually return, so you can tell a player getting better looks from one whose shots are just falling.</p>
    ${P.early ? `<p class="note warn">It's the first week of the season: most of this rests on one or two games. Read it as what to watch, not what's true yet.</p>` : ""}
  </section>
  <section class="zone"><h2>Best games ${ln.date === P.through ? `of ${esc(dateLong(ln.date))}` : ""}</h2>
    <p class="lede">Ranked by game score, one number for a whole box-score line (about 10 is an ordinary night, 30 a great one).</p>
    <ol class="perfs">${perf}</ol></section>
  ${P.hot.length || P.cold.length ? `<section class="zone grid-2"><div><h2>Hot</h2><p class="lede">Making more than their shots usually return, last ten games.</p>${pulseList(P.hot, mine, "Nobody yet.")}</div>
    <div><h2>Cold</h2><p class="lede">Making less than their shots usually return.</p>${pulseList(P.cold, mine, "Nobody yet.")}</div></section>`
    : `<section class="zone"><h2>Hot and cold</h2><p class="note">Nobody has taken ${40} shots yet. This fills in after a few games.</p></section>`}
  <section class="zone grid-2"><div><h2>Fast starts</h2><p class="lede">Scoring more than last season, and what's behind it.</p>${pulseList(P.starts.up, mine, "Nobody yet.")}</div>
    <div><h2>Slow starts</h2><p class="lede">Scoring less than last season.</p>${pulseList(P.starts.down, mine, "Nobody yet.")}</div></section>
  <section class="zone"><h2>New faces</h2><p class="lede">Players on a different team from last season, by minutes.</p>${pulseList(P.roles.new, mine, "Nobody yet.")}</section>
  <section class="zone grid-2"><div><h2>Bigger roles</h2>${pulseList(P.roles.up, mine, "Nobody yet.")}</div><div><h2>Smaller roles</h2>${pulseList(P.roles.down, mine, "Nobody yet.")}</div></section>
  <section class="zone"><h2>Rookies</h2>${rk.length ? `${table(rk, [
    { key: "name", label: "Rookie", cls: "l", nosort: true, fmt: (r) => `${playerLink(r.id, r.name)} <a class="chip" href="#teams/${r.team}">${esc(r.team)}</a>` },
    { key: "pick", label: "Pick", nosort: true, fmt: (r) => (r.pick ? `No. ${r.pick}` : "Undrafted") },
    { key: "gp", label: "GP", nosort: true }, { key: "mpg", label: "Min", nosort: true, fmt: (r) => num(r.mpg) },
    { key: "pts", label: "Pts", nosort: true, fmt: (r) => num(r.pts) }, { key: "reb", label: "Reb", nosort: true, fmt: (r) => num(r.reb) },
    { key: "ast", label: "Ast", nosort: true, fmt: (r) => num(r.ast) }, { key: "usage", label: "Usage", nosort: true, fmt: (r) => pct(r.usage, 0) },
    { key: "ts", label: "TS%", nosort: true, fmt: (r) => pct(r.ts) },
  ], null, null, (r) => (r.team === mine ? "mine" : ""))}` : `<p class="note">No rookies in the rotation yet.</p>`}</section>
  <section class="zone"><h2>Streaks</h2>${pulseList(P.streaks, mine, "No streaks of note yet.")}</section>
  <section class="zone grid-2"><div><h2>Results ahead of the shots</h2><p class="lede">Winning by more than their shots say they should. Usually comes back to earth.</p>${teamPulse(P.teams.ahead, mine)}</div>
    <div><h2>Results behind the shots</h2><p class="lede">Better than their record. Usually picks up.</p>${teamPulse(P.teams.behind, mine)}</div></section>
  <section class="zone"><p class="note">Through ${esc(dateLong(P.through))}. Every sentence here is written from our own numbers, the same way every night.</p></section>`;
}
function teamPulse(list, mine) {
  return list.length ? `<ul class="watch pulse">${list.map((t) => `<li class="${t.team === mine ? "mine" : ""}"><a class="who" href="#teams/${t.team}">${esc(nick(t.team))}</a><span>${esc(t.text)}</span></li>`).join("")}</ul>`
    : `<p class="note">Not after so few games. This fills in once teams have played three.</p>`;
}
