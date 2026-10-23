// Offline test of worker/live.js against BDL-shaped fixtures: node worker/test_live.mjs <fixtures dir>
import fs from "node:fs";
import path from "node:path";
import worker from "./live.js";

const dir = process.argv[2];
const read = (f) => JSON.parse(fs.readFileSync(path.join(dir, f), "utf8"));
const calls = [];
globalThis.fetch = async (url, init) => {
  calls.push(String(url));
  if (init.headers.Authorization !== "test-key") return new Response("no", { status: 401 });
  const u = new URL(url);
  let body;
  if (u.pathname === "/v1/games") body = { data: read("games.json"), meta: {} };
  else if (/^\/v1\/games\/\d+$/.test(u.pathname)) body = { data: read("game.json") };
  else if (u.pathname === "/v1/plays") body = { data: read("plays.json") };
  else if (u.pathname === "/v1/box_scores/live") body = read("box.json");
  else if (u.pathname === "/v1/player_injuries") {
    // one player per five-team group, and the first group needs a second page
    const t = +u.searchParams.getAll("team_ids[]")[0], c = u.searchParams.get("cursor");
    const row = (id) => ({ player: { id, first_name: "A", last_name: `B${id}`, team_id: t }, status: "Out", return_date: "Nov 1" });
    body = t === 1 && !c ? { data: [row(1)], meta: { next_cursor: 7 } } : t === 1 ? { data: [row(2), row(1)], meta: {} } : { data: [row(100 + t)], meta: {} };
  }
  else return new Response("{}", { status: 404 });
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
};
const env = { BDL_API_KEY: "test-key" };
const get = async (p, origin = "https://tolar-dio.github.io") => worker.fetch(new Request("https://live.example" + p, { headers: { Origin: origin } }), env, { waitUntil() {} });
const ok = (c, m) => { if (!c) { console.error("FAIL:", m); process.exit(1); } console.log("ok:", m); };

let r = await get("/scores"); let j = await r.json();
ok(r.status === 200 && j.games.length > 0, `scores: ${j.games.length} games, first ${JSON.stringify(j.games[0])}`);
ok(r.headers.get("Access-Control-Allow-Origin") === "https://tolar-dio.github.io", "CORS for the site");
ok(!JSON.stringify(j).includes("test-key"), "key never in a response");
const n = calls.length; await get("/scores"); ok(calls.length === n, "second request served from memory");

r = await get("/game?id=21717861"); j = await r.json();
const shots = j.plays.filter((p) => p[4] === "s");
ok(r.status === 200 && j.plays.length > 300 && shots.length > 100, `game: ${j.plays.length} plays, ${shots.length} shots, box ${j.box.home.length}+${j.box.away.length} players`);
ok(j.box.home.length >= 8 && Object.keys(j.names).length >= 16, "box scores and names present");
const pts = j.plays.filter((p) => p[5]).reduce((s, p) => s + p[6], 0);
ok(pts === j.game.hs + j.game.as, `points in plays (${pts}) = final (${j.game.hs + j.game.as})`);
ok(shots.every((p) => p[7] == null || (p[7] >= 0 && p[7] <= 50)), "shot x within the court or null");
console.log("size", JSON.stringify(j).length, "bytes");

r = await get("/game?id=abc"); ok(r.status === 400, "bad id rejected");
r = await get("/nope"); ok(r.status === 404, "unknown path 404");
r = await worker.fetch(new Request("https://live.example/scores"), { BDL_API_KEY: "" }, {}); ok(r.status === 500, "missing key reported");
r = await get("/injuries"); j = await r.json(); ok(j.players.length === 7, "injuries: every five-team group and every page, no duplicates (mock)");
r = await get("/scores", "https://evil.example"); ok(r.headers.get("Access-Control-Allow-Origin") !== "https://evil.example", "other origins not allowed");
console.log("ALL PASSED", calls.length, "upstream calls");
