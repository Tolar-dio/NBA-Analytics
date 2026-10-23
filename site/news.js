/* The Board's news layer: headlines grouped across outlets, the injury report, the NBA's own videos and podcast
   episodes. News comes from data/news/index.json in the repository (updated hourly without a site rebuild), with
   the copy made at the last build as a fallback. Videos play through YouTube's own player, loaded on tap. */
"use strict";

const NEWS_RAW = "https://raw.githubusercontent.com/Tolar-dio/NBA-Analytics/main/data/news/index.json";
const NEWS_TABS = [["top", "Top stories"], ["injuries", "Injuries"], ["watch", "Watch"], ["listen", "Listen"]];
const NS = { tab: "top", mine: false, limit: 25 };

async function loadNews() {
  if (D.news) return D.news;
  for (const url of [NEWS_RAW, "data/news.json"]) {
    try {
      const r = await fetch(url, { cache: "no-cache" });
      if (r.ok) return (D.news = await r.json());
    } catch (e) { /* try the next copy */ }
  }
  return (D.news = { stories: [], listen: [], watch: [], highlights: {} });
}
async function loadInjuries() {
  if (D.injuries) return D.injuries;
  try { D.injuries = await getJSON("injuries.json"); } catch (e) { D.injuries = { players: [] }; }
  return D.injuries;
}

function ago(iso) {
  const m = (Date.now() - new Date(iso)) / 60000;
  if (m < 60) return `${Math.max(1, Math.round(m))} min ago`;
  if (m < 60 * 24) return `${Math.round(m / 60)} hr ago`;
  const d = Math.round(m / 1440);
  return d === 1 ? "yesterday" : `${d} days ago`;
}
const chips = (teams) => (teams || []).map((t) => `<a class="chip" href="#teams/${t}">${esc(t)}</a>`).join("");

function storyItem(s) {
  const lead = s.items.find((i) => !i.paywalled) || s.items[0];
  const others = s.items.filter((i) => i !== lead);
  const srcs = [...new Set(others.map((i) => i.source))];
  return `<li class="story">
    <a class="story-t" href="${esc(lead.link)}" target="_blank" rel="noopener">${esc(s.title)}</a>
    ${s.desc ? `<p class="story-d">${esc(s.desc)}</p>` : ""}
    <p class="story-m"><span>${esc(lead.source)}${lead.via ? ` via ${esc(lead.via)}` : ""}${lead.paywalled ? " (subscription)" : ""}, ${ago(s.latest)}</span>
      ${srcs.length ? `<span>Also: ${srcs.map((src) => { const i = others.find((x) => x.source === src); return `<a href="${esc(i.link)}" target="_blank" rel="noopener">${esc(src)}</a>`; }).join(", ")}</span>` : ""}
      ${chips(s.teams)}${(s.players || []).slice(0, 3).map((p) => `<a class="chip p" href="#players/${p.id}">${esc(p.name)}</a>`).join("")}</p></li>`;
}

function videoCard(v) {
  return `<li class="video"><button class="yt" type="button" data-yt="${esc(v.id)}" aria-label="Play ${esc(v.title)}">
    <img loading="lazy" alt="" src="https://i.ytimg.com/vi/${esc(v.id)}/mqdefault.jpg"><span class="play" aria-hidden="true"></span></button>
    <p class="video-t">${esc(v.title)}</p><p class="story-m"><span>${esc(v.channel)}, ${ago(v.published)}</span>${v.game ? `<a href="#game/${S.season}/${v.game}">Game page</a>` : ""}</p></li>`;
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-yt]");
  if (!b) return;
  const f = document.createElement("iframe");
  f.className = "yt-frame";
  f.src = `https://www.youtube-nocookie.com/embed/${encodeURIComponent(b.dataset.yt)}?autoplay=1&rel=0`;
  f.title = "Video"; f.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen"; f.allowFullscreen = true;
  b.replaceWith(f);
});

function episode(x) {
  const mins = x.duration ? `${Math.round(x.duration / 60)} min` : "";
  return `<li class="episode"><p class="story-m"><b>${esc(x.show)}</b><span>${ago(x.published)}${mins ? `, ${mins}` : ""}</span>${chips(x.teams)}</p>
    <p class="video-t">${esc(x.title)}</p>${x.desc ? `<p class="story-d">${esc(x.desc)}</p>` : ""}
    <audio controls preload="none" src="${esc(x.audio)}"></audio>
    <p class="story-m"><a href="${esc(x.apple)}" target="_blank" rel="noopener">Show page</a></p></li>`;
}

const STATUS_CLS = { Out: "bad", Doubtful: "bad", Questionable: "warn-t", "Day-To-Day": "warn-t" };
function injuryRows(list, withTeam) {
  return `<ul class="inj">${list.map((p) => `<li><span class="${STATUS_CLS[p.status] || "dim"} st">${esc(p.status || "")}</span>
    <span><a class="who" href="#players/${p.id}">${esc(p.name)}</a>${withTeam ? ` <span class="dim">${esc(p.team || "")}</span>` : ""}${p.back ? ` <span class="dim">expected back ${esc(fmtBack(p.back))}</span>` : ""}<br>
    <span class="note-s">${esc(p.note || "")}</span></span></li>`).join("")}</ul>`;
}
function fmtBack(s) {
  const d = /^\d{4}-\d{2}-\d{2}$/.test(s) ? new Date(s + "T12:00:00") : null;
  if (!d || isNaN(d)) return s;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: d.getFullYear() !== new Date().getFullYear() ? "numeric" : undefined });
}

async function renderNews(view, tab) {
  NS.tab = NEWS_TABS.some(([k]) => k === tab) ? tab : "top";
  const [N, I] = await Promise.all([loadNews(), loadInjuries()]);
  const mine = myTeam();
  const pick = (list) => (NS.mine && mine ? list.filter((x) => (x.teams || []).includes(mine) || x.team === mine) : list);
  const counts = { top: N.stories.length, injuries: I.players.length, watch: N.watch.length, listen: N.listen.length };
  view.innerHTML = `<section class="zone"><h1>News</h1>
    <p class="lede">The day's NBA news from The Athletic, CBS Sports, Yahoo Sports and SB Nation, with the same story from several outlets grouped together, plus the injury report, the league's own highlights and the best basketball podcasts. Headlines link to the outlets; we don't republish their stories.</p>
    <div class="controls"><div class="seg" role="tablist" aria-label="News">${NEWS_TABS.map(([k, l]) => `<button type="button" role="tab" data-nt="${k}" aria-pressed="${NS.tab === k}">${l}<span class="cnt"> ${counts[k]}</span></button>`).join("")}</div>
    ${mine ? `<label class="dim"><input type="checkbox" id="nMine" ${NS.mine ? "checked" : ""}> ${esc(mine)} only</label>` : ""}</div>
    <div id="nBody"></div>
    <p class="note">${N.updated_utc ? `News checked ${ago(N.updated_utc)}.` : ""} ${I.as_of ? `Injury report as of ${ago(I.as_of)}.` : ""}</p></section>`;
  const body = $("#nBody");
  const draw = () => {
    if (NS.tab === "top") {
      const list = pick(N.stories);
      body.innerHTML = list.length ? `<ul class="stories">${list.slice(0, NS.limit).map(storyItem).join("")}</ul>${list.length > NS.limit ? `<button class="more" id="nMore" type="button">More stories</button>` : ""}` : `<p class="note">No stories right now.</p>`;
      $("#nMore")?.addEventListener("click", () => { NS.limit += 25; draw(); });
    } else if (NS.tab === "injuries") {
      const list = pick(I.players);
      const teams = [...new Set(list.map((p) => p.team))].sort((a, b) => (a === mine ? -1 : b === mine ? 1 : a.localeCompare(b)));
      body.innerHTML = teams.length ? `<div class="inj-grid">${teams.map((t) => `<div><h3><a class="who" href="#teams/${t}">${esc(t)}</a></h3>${injuryRows(list.filter((p) => p.team === t))}</div>`).join("")}</div>`
        : `<p class="note">Nobody listed.</p>`;
    } else if (NS.tab === "watch") {
      const list = pick(N.watch);
      body.innerHTML = list.length ? `<ul class="videos">${list.map(videoCard).join("")}</ul><p class="note">From the NBA's YouTube channel, played through YouTube.</p>` : `<p class="note">No new videos.</p>`;
    } else {
      const list = pick(N.listen);
      body.innerHTML = list.length ? `<ul class="episodes">${list.map(episode).join("")}</ul><p class="note">Episodes play from each show's public feed.</p>` : `<p class="note">No new episodes.</p>`;
    }
  };
  $$("[data-nt]", view).forEach((b) => b.addEventListener("click", () => { history.replaceState(null, "", `#news/${b.dataset.nt}`); renderNews(view, b.dataset.nt); }));
  $("#nMine")?.addEventListener("change", (e) => { NS.mine = e.target.checked; draw(); });
  draw();
}

// pieces for other pages
async function teamExtras(abbr) {
  const [N, I] = await Promise.all([loadNews(), loadInjuries()]);
  // two-way players listed for G League duty aren't injuries; they stay on the Injuries tab only
  const out = I.players.filter((p) => p.team === abbr && p.status !== "Available" && !/^G League/i.test(p.note || ""));
  const st = N.stories.filter((s) => s.teams.includes(abbr)).slice(0, 6);
  const el = $("#tOut"), en = $("#tNews");
  if (el) el.innerHTML = out.length ? `<h2>Who's out</h2><p class="lede">From the latest injury report${I.as_of ? `, ${ago(I.as_of)}` : ""}.</p>${injuryRows(out)}` : "";
  if (en) en.innerHTML = st.length ? `<h2>In the news</h2><ul class="stories">${st.map(storyItem).join("")}</ul>` : "";
  if (el && !out.length) el.remove();
  if (en && !st.length) en.remove();
}
async function playerExtras(id) {
  const [N, I] = await Promise.all([loadNews(), loadInjuries()]);
  const inj = I.players.find((p) => p.id === +id);
  const st = N.stories.filter((s) => (s.players || []).some((p) => p.id === +id)).slice(0, 5);
  const vids = N.watch.filter((v) => (v.players || []).some((p) => p.id === +id)).slice(0, 3);
  const el = $("#pInj"), en = $("#pNews");
  if (el) el.innerHTML = inj && inj.status !== "Available" ? `<p class="inj-line"><span class="${STATUS_CLS[inj.status] || "dim"} st">${esc(inj.status)}</span> ${esc(inj.note || "")}${inj.back ? ` <span class="dim">Expected back ${esc(fmtBack(inj.back))}.</span>` : ""}</p>` : "";
  if (en) {
    en.innerHTML = st.length || vids.length ? `<h2>In the news</h2>${st.length ? `<ul class="stories">${st.map(storyItem).join("")}</ul>` : ""}${vids.length ? `<ul class="videos">${vids.map(videoCard).join("")}</ul>` : ""}` : "";
    if (!st.length && !vids.length) en.remove();
  }
}
async function gameHighlight(id) {
  const N = await loadNews();
  const v = N.highlights && N.highlights[String(id)];
  const el = $("#gHigh");
  if (!el) return;
  if (!v) { el.remove(); return; }
  el.innerHTML = `<h2>Highlights</h2><div class="video-one"><button class="yt" type="button" data-yt="${esc(v)}" aria-label="Play the official highlights">
    <img loading="lazy" alt="" src="https://i.ytimg.com/vi/${esc(v)}/hqdefault.jpg"><span class="play" aria-hidden="true"></span></button></div>
    <p class="note">The NBA's official highlights, played through YouTube.</p>`;
}
