/* The Board's live relay: a Cloudflare Worker that holds the BALLDONTLIE key and hands the site trimmed live scores,
   box scores and play-by-play. The key is a Worker secret (BDL_API_KEY) and never reaches a browser.

   Endpoints (GET, JSON):
     /scores     yesterday's and today's games (US Eastern dates), with score, period, clock and quarters
     /game?id=N  one game: header, both box scores, and every play trimmed to what the live page draws
     /injuries   the current injury report, trimmed

   Each answer is kept for a few seconds (TTL below) in this isolate's memory and Cloudflare's cache, so the number
   of requests to BALLDONTLIE doesn't grow with the number of people watching. Only GitHub Pages (and localhost for
   testing) may read it from a browser: ALLOWED_ORIGINS, comma-separated, overrides that.

   Deploy: Cloudflare dashboard > Workers & Pages > Create > Start with Hello World > paste this file > Deploy;
   then Settings > Variables and Secrets > add BDL_API_KEY as a Secret. */

const BASE = "https://api.balldontlie.io";
const TTL = { scores: 15, game: 20, box: 20, injuries: 600 };
const ORIGINS = "https://tolar-dio.github.io,http://localhost:8765";
const mem = new Map();

async function bdl(env, path, params = {}) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (Array.isArray(v)) v.forEach((x) => q.append(`${k}[]`, String(x)));
    else if (v != null) q.append(k, String(v));
  }
  const r = await fetch(`${BASE}${path}${q.toString() ? "?" + q : ""}`, {
    headers: { Authorization: env.BDL_API_KEY, Accept: "application/json", "User-Agent": "the-board-live/1.0" },
  });
  if (!r.ok) throw new Error(`BDL ${r.status} on ${path}`);
  return r.json();
}

// memory first, then Cloudflare's cache (where the zone allows it), then the source
async function cached(key, ttl, make, ctx) {
  const hit = mem.get(key);
  if (hit && Date.now() - hit.t < ttl * 1000) return hit.body;
  const ck = new Request(`https://board-live.cache/${encodeURIComponent(key)}`);
  let cache = null;
  try { cache = caches.default; const m = await cache.match(ck); if (m) { const body = await m.text(); mem.set(key, { t: Date.now(), body }); return body; } }
  catch (e) { cache = null; }
  const body = JSON.stringify(await make());
  mem.set(key, { t: Date.now(), body });
  if (cache) {
    const put = cache.put(ck, new Response(body, { headers: { "Cache-Control": `max-age=${ttl}`, "Content-Type": "application/json" } })).catch(() => {});
    if (ctx && ctx.waitUntil) ctx.waitUntil(put);
  }
  return body;
}

const etDate = (d) => new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit" }).format(d);

function trimGame(g) {
  const qs = (side) => ["q1", "q2", "q3", "q4", "ot1", "ot2", "ot3"].map((q) => g[`${side}_${q}`]).filter((v) => v != null);
  return {
    id: g.id, date: (g.date || "").slice(0, 10), tip: g.datetime || null, state: g.status_state || null, status: g.status,
    period: g.period, time: (g.time || "").trim(), home: g.home_team?.abbreviation, away: g.visitor_team?.abbreviation,
    hs: g.home_team_score, as: g.visitor_team_score, hq: qs("home"), aq: qs("visitor"),
  };
}

async function scores(env, ctx) {
  const now = new Date();
  const days = [etDate(new Date(now - 864e5)), etDate(now)];
  return cached(`scores:${days[1]}`, TTL.scores, async () => {
    const d = await bdl(env, "/v1/games", { dates: days, per_page: 100 });
    return { as_of: now.toISOString(), today: days[1], games: (d.data || []).map(trimGame) };
  }, ctx);
}

// play kinds: s field goal attempt, f free throw, o offensive rebound, d defensive rebound, t turnover, b period start/end
function kindOf(type) {
  if (/Free Throw/.test(type)) return "f";
  if (/Offensive Rebound/.test(type)) return "o";
  if (/Defensive Rebound/.test(type)) return "d";
  if ((/Turnover/.test(type) && type !== "No Turnover") || type === "Traveling") return "t";
  if (/End Period|End Game|Jumpball/.test(type)) return "b";
  return "x";
}
const SENT = 10000;
function shotValue(p, x, y) {
  if (p.scoring_play && (p.score_value === 2 || p.score_value === 3)) return p.score_value;
  const t = p.text || "";
  if (/three point/i.test(t)) return 3;
  if (/two point/i.test(t) || x == null) return 2;
  return Math.abs(x - 25) >= 21.5 || Math.hypot(x - 25, y - 1) >= 22.5 ? 3 : 2;
}
function clockSec(c) {
  const s = String(c || "0");
  if (s.includes(":")) { const [m, x] = s.split(":"); return +m * 60 + parseFloat(x); }
  return parseFloat(s) || 0;
}

async function box(env, ctx) {
  return cached("box:live", TTL.box, async () => (await bdl(env, "/v1/box_scores/live")).data || [], ctx);
}

function trimBox(team) {
  return (team?.players || []).map((r) => {
    const p = r.player || {};
    return [p.id, `${p.first_name || ""} ${p.last_name || ""}`.trim(), r.min || "0", r.pts, r.reb, r.ast, r.stl, r.blk,
      r.turnover, r.pf, r.fgm, r.fga, r.fg3m, r.fg3a, r.ftm, r.fta, r.plus_minus];
  }).filter((r) => r[2] && r[2] !== "0" && r[2] !== "00" && r[2] !== "0:00");
}

async function game(env, id, ctx) {
  if (!/^\d{1,12}$/.test(id || "")) throw Object.assign(new Error("bad id"), { status: 400 });
  return cached(`game:${id}`, TTL.game, async () => {
    const [gRes, pRes, boxes] = await Promise.all([
      bdl(env, `/v1/games/${id}`), bdl(env, "/v1/plays", { game_id: id }), JSON.parse(await box(env, ctx))]);
    const g = trimGame(gRes.data || gRes);
    let b = boxes.find((x) => x.home_team?.abbreviation === g.home && (x.date || "").slice(0, 10) === g.date);
    if (!b) {
      try { b = ((await bdl(env, "/v1/box_scores", { date: g.date })).data || []).find((x) => x.home_team?.abbreviation === g.home); }
      catch (e) { b = null; }
    }
    const names = {};
    const boxOut = { home: trimBox(b?.home_team), away: trimBox(b?.visitor_team) };
    [...boxOut.home, ...boxOut.away].forEach((r) => (names[r[0]] = r[1]));
    const homeId = (gRes.data || gRes).home_team?.id;
    const plays = (pRes.data || []).map((p) => {
      const side = p.team ? (p.team.id === homeId ? 0 : 1) : -1;
      let kind = p.shooting_play && !/Free Throw/.test(p.type) ? "s" : kindOf(p.type);
      const x = Math.abs(p.coordinate_x ?? SENT * 10) > SENT ? null : p.coordinate_x;
      const y = Math.abs(p.coordinate_y ?? SENT * 10) > SENT ? null : p.coordinate_y;
      const value = kind === "s" ? shotValue(p, x, y) : kind === "f" ? 1 : 0;
      const heave = kind === "s" && !p.scoring_play && /Heave/.test(p.type) ? 1 : 0;
      return [p.order, p.period, clockSec(p.clock), side, kind, p.scoring_play ? 1 : 0, value, x, y,
        (p.participants || [])[0] ?? null, p.home_score, p.away_score, kind === "s" ? p.type : null, heave];
    });
    return {
      as_of: new Date().toISOString(), game: g, box: boxOut, names,
      box_cols: ["id", "name", "min", "pts", "reb", "ast", "stl", "blk", "tov", "pf", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "pm"],
      play_cols: ["order", "period", "clock", "side", "kind", "made", "value", "x", "y", "player", "hs", "as", "type", "heave"],
      plays,
    };
  }, ctx);
}

async function injuries(env, ctx) {
  return cached("injuries", TTL.injuries, async () => {
    // five teams a request and every page: a league-wide request came back with exactly 100 rows (Oct 23, 2026)
    const out = [], seen = new Set();
    for (let first = 1; first <= 30; first += 5) {
      let cursor = null;
      for (let page = 0; page < 5; page++) {
        const d = await bdl(env, "/v1/player_injuries", { team_ids: Array.from({ length: 5 }, (_, i) => first + i), per_page: 100, cursor });
        for (const r of d.data || []) {
          const p = r.player || {};
          const key = `${p.id}|${r.status}|${r.return_date}`;
          if (seen.has(key)) continue;
          seen.add(key);
          out.push({ id: p.id, name: `${p.first_name || ""} ${p.last_name || ""}`.trim(), team_id: p.team_id, status: r.status, back: r.return_date });
        }
        cursor = d.meta?.next_cursor;
        if (!cursor) break;
      }
    }
    return { as_of: new Date().toISOString(), players: out };
  }, ctx);
}

function respond(body, status, origin, env, ttl) {
  const allowed = (env.ALLOWED_ORIGINS || ORIGINS).split(",").map((s) => s.trim());
  const h = {
    "Content-Type": "application/json; charset=utf-8", Vary: "Origin",
    "Access-Control-Allow-Origin": allowed.includes(origin) ? origin : allowed[0],
    "Cache-Control": status === 200 ? `public, max-age=${Math.min(ttl || 10, 15)}` : "no-store",
  };
  return new Response(typeof body === "string" ? body : JSON.stringify(body), { status, headers: h });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url), origin = request.headers.get("Origin") || "";
    if (request.method === "OPTIONS") return new Response(null, { headers: { "Access-Control-Allow-Origin": origin || "*", "Access-Control-Allow-Methods": "GET", "Access-Control-Max-Age": "86400" } });
    if (request.method !== "GET") return respond({ error: "GET only" }, 405, origin, env);
    if (!env.BDL_API_KEY) return respond({ error: "BDL_API_KEY secret is not set" }, 500, origin, env);
    try {
      if (url.pathname === "/scores") return respond(await scores(env, ctx), 200, origin, env, TTL.scores);
      if (url.pathname === "/game") return respond(await game(env, url.searchParams.get("id"), ctx), 200, origin, env, TTL.game);
      if (url.pathname === "/injuries") return respond(await injuries(env, ctx), 200, origin, env, TTL.injuries);
      if (url.pathname === "/" || url.pathname === "/health") return respond({ ok: true, endpoints: ["/scores", "/game?id=", "/injuries"] }, 200, origin, env, 5);
      return respond({ error: "not found" }, 404, origin, env);
    } catch (e) {
      // never echo upstream details: they could include the request we made
      return respond({ error: e.status === 400 ? "bad request" : "the score feed didn't answer; try again shortly" }, e.status || 502, origin, env);
    }
  },
};
