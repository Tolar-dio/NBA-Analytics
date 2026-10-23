"""Build the site's JSON from the tables (private repo) and the analysis outputs.

    python site/build.py            # writes site/data/ (gitignored); the workflow deploys site/ to GitHub Pages

Run analysis/shot_quality.py, teams.py and players.py for each season first. Only derived numbers and box-score
lines go out; no raw feed files, odds or play text.

site/data/
  meta.json                         seasons we have, which is current, when this was built
  league.<season>.json              every team: record, ratings, four factors, luck checks, ranks; league averages
  players.<season>.json             one row per player and team, for the Players tab and search
  player/<season>/<id>.json         bio, season lines, game log, shots, shot zones against the league
  team/<season>/<abbr>.json         team line, players, lineups, results, shot profile for and against
  games.<season>.json               every game: date, tip, teams, score, expected points
  game/<season>/<id>.json           quarters, box scores, shots, scoring flow, how likely each team was to win
                                    on the shots it took
"""
import datetime as dt
import json
import os
import re
import shutil
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "analysis"))
from common import table, out_path, TABLES, PREV, CUR  # noqa: E402
import stories  # noqa: E402
import profiles as prof  # noqa: E402

DATA = os.path.join(ROOT, "site", "data")
LABEL = lambda s: f"{s}-{(s + 1) % 100:02d}"  # noqa: E731
REG = ("regular",)   # the NBA Cup final ("ist") does not count in the standings
RIM, SHORT = 4, 14
ZONES = ["rim", "short", "mid", "corner3", "above3"]


def dump(rel, obj):
    path = os.path.join(DATA, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(clean(obj), f, separators=(",", ":"), allow_nan=False)


def clean(v):
    if isinstance(v, dict):
        return {k: clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [clean(x) for x in v]
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if not np.isfinite(v) else round(float(v), 4)
    if v is pd.NA or v is pd.NaT:
        return None
    return v


def records(df, cols=None):
    df = df if cols is None else df[cols]
    return [clean(r) for r in df.to_dict("records")]


def zone(sh):
    return np.select([sh.dist < RIM, sh.dist < SHORT, sh.value == 2, (sh.x - 25).abs() >= 21.5],
                     ["rim", "short", "mid", "corner3"], default="above3")


def zone_table(sh, lg=None):
    """FG%, expected FG%, share of shots per zone; with league rates when given."""
    out = {}
    n = len(sh)
    for z in ZONES:
        q = sh[sh.zone == z]
        row = {"fga": int(len(q)), "share": len(q) / n if n else None,
               "fg": q.made.mean() if len(q) else None, "xfg": q.p_make.mean() if len(q) else None}
        if lg is not None:
            row["lg_fg"], row["lg_share"] = lg[z]["fg"], lg[z]["share"]
        out[z] = row
    return out


def trip_pmfs(first, rate, q2, q3):
    """Points distribution of each trip: its first shot goes in (its own value) or, if it misses, a second chance
    comes at the team's rate and scores 2 or 3 at the league's second-chance rates."""
    out = []
    for p, v in first:
        miss_cont = (1 - p) * rate
        pmf = np.zeros(4)
        pmf[v] += p
        pmf[2] += miss_cont * q2
        pmf[3] += miss_cont * q3
        pmf[0] += 1 - pmf[1:].sum()
        out.append(pmf)
    return out


def win_chance(pmfs_a, pmfs_b, fixed_a, fixed_b):
    """P(team A outscores B) if every trip were replayed with the same first shots, second chances at each team's
    usual rate, and free throws as they happened; ties split. Exact convolution of the two point distributions."""
    def dist(pmfs, fixed):
        d = np.zeros(fixed + 1)
        d[fixed] = 1.0
        for pmf in pmfs:
            d = np.convolve(d, pmf)
        return d
    a, b = dist(pmfs_a, fixed_a), dist(pmfs_b, fixed_b)
    n = max(len(a), len(b))
    a, b = np.pad(a, (0, n - len(a))), np.pad(b, (0, n - len(b)))
    below = np.concatenate([[0.0], np.cumsum(b)[:-1]])     # P(B < k)
    return float(np.sum(a * (below + 0.5 * b)))


def season_data(season):
    games = table(season, "games")
    teams_t = table(season, "teams")
    pl_bio = table(season, "players")
    box = table(season, "player_games")
    shots = table(season, "shots")
    plays = table(season, "plays")[["game_id", "order", "period", "t", "team_id", "type", "scoring", "value",
                                    "home_score", "away_score", "p1"]]
    xp = pd.read_csv(out_path(season, "shots_xp.csv.gz"))
    shots = shots.merge(xp[["game_id", "order", "p_make", "xpts", "xpts_trip", "k"]], on=["game_id", "order"],
                        how="left")
    with open(out_path(season, "trips.json")) as f:
        trips = json.load(f)
    shots["zone"] = zone(shots)
    teams_csv = pd.read_csv(out_path(season, "teams.csv"))
    players_csv = pd.read_csv(out_path(season, "players.csv"))
    lineups = pd.read_csv(out_path(season, "lineups.csv"))
    usage = pd.read_csv(out_path(season, "player_games.csv.gz"))
    abbr = dict(zip(teams_t.team_id, teams_t.abbr))
    reg_ids = set(games[games.game_type.isin(REG)].game_id)
    stints = table(season, "stints")
    return dict(games=games, teams_t=teams_t, bio=pl_bio, box=box, shots=shots, plays=plays, teams=teams_csv, stints=stints,
                players=players_csv, lineups=lineups, usage=usage, abbr=abbr, reg_ids=reg_ids, trips=trips)


# ------------------------------------------------------------------ league

def league(season, D):
    g = D["games"][D["games"].game_type.isin(REG)]
    rec = []
    for r in g.itertuples(index=False):
        hw = r.home_score > r.away_score
        rec += [(r.home_id, hw), (r.away_id, not hw)]
    rec = pd.DataFrame(rec, columns=["team_id", "w"]).groupby("team_id").w.agg(["sum", "size"])
    t = D["teams"].merge(D["teams_t"], on="team_id", how="left")
    t["w"] = t.team_id.map(rec["sum"]).fillna(0).astype(int)
    t["l"] = (t.team_id.map(rec["size"]).fillna(0) - t.w).astype(int)
    # ranks: 1 is best (lower is better for defense-side numbers)
    lower_better = {"drtg", "x_drtg", "tov", "opp_efg", "opp_ftr", "opp_xpps", "opp_shotmaking", "opp_3p_vs_lg",
                    "opp_ft_vs_lg"}
    for c in ["net", "x_net", "ortg", "drtg", "x_ortg", "x_drtg", "pace", "efg", "tov", "orb", "ftr", "opp_efg",
              "opp_tov", "drb", "opp_ftr", "xpps", "opp_xpps"]:
        t[f"{c}_rk"] = t[c].rank(ascending=c in lower_better, method="min").astype(int)
    tg = D["games"]
    lgdf = table(season, "team_games")
    lgdf = lgdf[lgdf.game_id.isin(D["reg_ids"])]
    s = lgdf.sum(numeric_only=True)
    poss = ((lgdf.poss + lgdf.opp_poss) / 2).sum()
    lg = {"ortg": 100 * s.pts / poss, "pace": poss / len(lgdf), "efg": (s.fgm + 0.5 * s.fg3m) / s.fga,
          "tov": s.tov / poss, "orb": s.oreb / (s.oreb + s.opp_dreb), "ftr": s.ftm / s.fga,
          "fg3": s.fg3m / s.fg3a, "ft": s.ftm / s.fta, "games": int(len(D["reg_ids"]))}
    sh = D["shots"][D["shots"].game_id.isin(D["reg_ids"]) & (D["shots"].heave == 0)]
    lg["zones"] = {z: {"fg": float(sh[sh.zone == z].made.mean()), "share": float((sh.zone == z).mean())}
                   for z in ZONES}
    lg["pps"] = float((sh.made * sh.value).mean())
    cols = ["team_id", "abbr", "full_name", "conference", "division", "w", "l", "gp", "pace", "ortg", "drtg", "net",
            "x_ortg", "x_drtg", "x_net", "efg", "tov", "orb", "ftr", "opp_efg", "opp_tov", "drb", "opp_ftr",
            "opp_3p_vs_lg", "opp_ft_vs_lg", "xpps", "opp_xpps", "shotmaking", "opp_shotmaking"] + \
        [c for c in t.columns if c.endswith("_rk")]
    dump(f"league.{season}.json", {"season": season, "label": LABEL(season), "league": lg,
                                  "teams": records(t.sort_values("net", ascending=False), cols)})
    return lg, t


# ------------------------------------------------------------------ players

PCOLS = ["player_id", "name", "team", "position", "gp", "gs", "mpg", "pts_pg", "reb_pg", "ast_pg", "stl_pg",
         "blk_pg", "tov_pg", "fg3m_pg", "ts", "fg3_pct", "ft_pct", "usage", "shots", "pps", "xpps", "shotmaking",
         "assisted_share", "share_rim", "share_short", "share_mid", "share_corner3", "share_above3", "on_ortg",
         "on_drtg", "on_net", "off_net", "on_off", "xon_off", "poss_on", "rim_dfg_pct", "rim_dfg_vs_lg",
         "defended_at_rim_fga", "contested_shots_p36", "deflections_p36", "touches_p36"]


def players(season, D, lg):
    p = D["players"]
    cols = [c for c in PCOLS if c in p.columns]
    dump(f"players.{season}.json", {"season": season, "players": records(p.sort_values("pts_pg", ascending=False),
                                                                           cols)})
    bio = D["bio"].set_index("player_id")
    per_team = 2 * len(D["reg_ids"]) / 30
    profs = prof.profiles(D["players"], bio.position.to_dict(), max(5, min(20, int(per_team / 3))))
    games = D["games"].set_index("game_id")
    box = D["box"].merge(D["usage"][["game_id", "player_id", "usage", "poss_on"]], on=["game_id", "player_id"],
                         how="left")
    box = box[box.sec_on > 0].sort_values("date")
    sh = D["shots"][D["shots"].heave == 0]
    by_player_shots = dict(tuple(sh.groupby("shooter")))
    for pid, log in box.groupby("player_id"):
        b = bio.loc[pid] if pid in bio.index else None
        rows = []
        gidx = {}
        for r in log.itertuples(index=False):
            gm = games.loc[r.game_id]
            gidx[r.game_id] = len(rows)
            opp = gm.away if r.home == 1 else gm.home
            own = gm.home_score if r.home == 1 else gm.away_score
            oth = gm.away_score if r.home == 1 else gm.home_score
            rows.append([r.game_id, r.date, D["abbr"].get(r.team_id), opp, int(r.home), int(own), int(oth),
                         gm.game_type, int(r.starter), round(r.sec_on / 60, 1), int(r.pts), int(r.reb), int(r.ast),
                         int(r.stl), int(r.blk), int(r.tov), int(r.fgm), int(r.fga), int(r.fg3m), int(r.fg3a),
                         int(r.ftm), int(r.fta), None if pd.isna(r.plus_minus) else int(r.plus_minus),
                         None if pd.isna(r.usage) else round(float(r.usage), 3)])
        ps = by_player_shots.get(pid)
        shots_out, zones = [], None
        if ps is not None:
            ps = ps[ps.game_id.isin(gidx)]
            shots_out = [[int(r.x), int(r.y), int(r.made), int(r.value == 3),
                          None if pd.isna(r.p_make) else int(round(1000 * r.p_make)), gidx[r.game_id]]
                         for r in ps.itertuples(index=False)]
            reg = ps[ps.game_id.isin(D["reg_ids"])]
            zones = zone_table(reg, lg["zones"]) if len(reg) else None
        lines = records(D["players"][D["players"].player_id == pid], [c for c in PCOLS if c in D["players"].columns])
        info = {}
        if b is not None:
            info = {"name": f"{b.first_name} {b.last_name}", "position": b.position,
                    "height_in": None if pd.isna(b.height_in) else int(b.height_in), "jersey": b.jersey,
                    "weight": None if pd.isna(b.weight) else int(b.weight),
                    "country": b.country, "college": b.college, "draft_year": b.draft_year,
                    "draft_round": b.draft_round, "draft_number": b.draft_number}
        dump(f"player/{season}/{pid}.json", {"season": season, "id": int(pid), "bio": info, "lines": lines,
                                             "profile": profs.get(int(pid)),
                                             "log_cols": ["game_id", "date", "team", "opp", "home", "own", "opp_pts",
                                                          "type", "starter", "min", "pts", "reb", "ast", "stl", "blk",
                                                          "tov", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "pm",
                                                          "usage"],
                                             "log": rows, "shots": shots_out, "zones": zones})


# ------------------------------------------------------------------ teams

def teams(season, D, lg, lt):
    sh = D["shots"][D["shots"].game_id.isin(D["reg_ids"]) & (D["shots"].heave == 0)]
    games = D["games"]
    g_reg = games[games.game_type.isin(REG)]
    names = {int(r.player_id): f"{r.first_name} {r.last_name}" for r in D["bio"].itertuples()}
    zones = {}
    gl = pd.read_csv(out_path(season, "games_x.csv")) if os.path.exists(out_path(season, "games_x.csv")) else None
    for r in lt.itertuples(index=False):
        tid, ab = r.team_id, r.abbr
        own = sh[sh.team_id == tid]
        opp_games = set(games[(games.home_id == tid) | (games.away_id == tid)].game_id)
        against = sh[sh.game_id.isin(opp_games) & (sh.team_id != tid)]
        pl = D["players"][D["players"].team_id == tid].sort_values("mpg", ascending=False)
        lu = D["lineups"][D["lineups"].team_id == tid].sort_values("poss", ascending=False).head(15)
        res = []
        g = games[(games.home_id == tid) | (games.away_id == tid)].sort_values("date")
        for x in g.itertuples(index=False):
            home = x.home_id == tid
            row = [x.game_id, x.date, x.game_type, x.away if home else x.home, int(home),
                   int(x.home_score if home else x.away_score), int(x.away_score if home else x.home_score)]
            if gl is not None:
                m = gl[gl.game_id == x.game_id]
                if len(m):
                    m = m.iloc[0]
                    row += [m.x_home if home else m.x_away, m.x_away if home else m.x_home,
                            m.win_home if home else 1 - m.win_home]
            res.append(row)
        zones[ab] = {"for": zone_table(own, lg["zones"]), "against": zone_table(against, lg["zones"])}
        reg_g = g_reg[(g_reg.home_id == tid) | (g_reg.away_id == tid)].sort_values("date")
        rot_ids = set(reg_g.game_id.tail(10)) if season == CUR else set(reg_g.game_id)
        rot = prof.rotation(D["stints"], tid, rot_ids, names)
        dump(f"team/{season}/{ab}.json", {
            "season": season, "team": clean(next(iter(records(lt[lt.team_id == tid])))),
            "players": records(pl, [c for c in PCOLS if c in pl.columns]),
            "lineups": records(lu, ["players", "unit", "min", "poss", "ortg", "drtg", "net", "xnet"]),
            "results_cols": ["game_id", "date", "type", "opp", "home", "own", "opp_pts", "x_own", "x_opp", "win_x"],
            "results": res,
            "zones_for": zones[ab]["for"], "zones_against": zones[ab]["against"],
            "rotation": rot, "rotation_recent": season == CUR,
        })
    return zones


# ------------------------------------------------------------------ games

def games_out(season, D):
    games, box, sh, plays = D["games"], D["box"], D["shots"], D["plays"]
    bio = D["bio"].set_index("player_id")
    name = {pid: f"{r.first_name} {r.last_name}" for pid, r in bio.iterrows()}
    ft = plays[plays.type.str.contains("Free Throw")]
    idx, xrows = [], []
    shots_by = dict(tuple(sh.groupby("game_id")))
    ft_by = dict(tuple(ft.groupby("game_id")))
    sc = plays[(plays.scoring == 1) & (plays.value > 0)]
    sc_by = dict(tuple(sc.groupby("game_id")))
    box_by = dict(tuple(box.groupby("game_id")))
    # each player's season high and games played before each game, for "his most this season"
    played = box[box.sec_on > 0].sort_values(["date", "game_id"])
    hi = played.groupby("player_id").pts.transform(lambda s_: s_.shift().cummax())
    n_before = played.groupby("player_id").cumcount()
    before = {(int(a), int(b)): (None if pd.isna(h) else int(h), int(n))
              for a, b, h, n in zip(played.game_id, played.player_id, hi, n_before)}
    for g in games.itertuples(index=False):
        gid, home, away = g.game_id, g.home_id, g.away_id
        s = shots_by.get(gid, sh.iloc[:0])
        f = ft_by.get(gid, ft.iloc[:0])
        ft_home = int(f[(f.team_id == home) & (f.scoring == 1)].value.sum())
        ft_away = int(f[(f.team_id == away) & (f.scoring == 1)].value.sum())
        xh = float(s[s.team_id == home].xpts_trip.sum()) + ft_home
        xa = float(s[s.team_id == away].xpts_trip.sum()) + ft_away
        tr = D["trips"]
        pm = {}
        for tid in (home, away):
            q = s[(s.team_id == tid) & (s.k == 0) & s.p_make.notna()]
            rate = tr["rate_by_team"].get(str(tid), tr["second_chance_rate_league"])
            pm[tid] = trip_pmfs(zip(q.p_make.astype(float), q.value.astype(int)), rate, tr["q2"], tr["q3"])
        wh = win_chance(pm[home], pm[away], ft_home, ft_away) if pm[home] and pm[away] else None
        xrows.append([gid, xh, xa, wh])
        quarters = {side: [None if pd.isna(getattr(g, f"{side}_{q}")) else int(getattr(g, f"{side}_{q}"))
                           for q in ("q1", "q2", "q3", "q4", "ot1", "ot2", "ot3")] for side in ("home", "away")}
        for side in quarters:
            while quarters[side] and quarters[side][-1] is None:
                quarters[side].pop()
        b = box_by.get(gid, box.iloc[:0]).sort_values(["home", "starter", "sec_on"], ascending=[False, False, False])
        boxes = {}
        for side, tid in (("home", home), ("away", away)):
            q = b[b.team_id == tid]
            boxes[side] = [[int(r.player_id), name.get(r.player_id, str(r.player_id)), int(r.starter),
                            round(r.sec_on / 60, 1), int(r.pts), int(r.reb), int(r.oreb), int(r.ast), int(r.stl),
                            int(r.blk), int(r.tov), int(r.pf), int(r.fgm), int(r.fga), int(r.fg3m), int(r.fg3a),
                            int(r.ftm), int(r.fta), None if pd.isna(r.plus_minus) else int(r.plus_minus)]
                           for r in q.itertuples(index=False) if r.sec_on > 0 or r.min_box > 0]
        shots_out = [[int(r.x), int(r.y), int(r.made), int(r.value == 3),
                      None if pd.isna(r.p_make) else int(round(1000 * r.p_make)), int(r.team_id == away),
                      round(float(r.t), 1), int(r.shooter), int(r.heave),
                      0 if pd.isna(r.xpts_trip) else int(round(1000 * r.xpts_trip))] for r in s.itertuples(index=False)]
        fts = [[round(float(r.t), 1), int(r.team_id == away), int(r.scoring)] for r in f.itertuples(index=False)
               if pd.notna(r.team_id)]
        scoring = sc_by.get(gid)
        flow = [[round(float(r.t), 1), int(r.home_score), int(r.away_score)] for r in scoring.itertuples(index=False)
                if pd.notna(r.home_score)] if scoring is not None else []
        gb = box_by.get(gid, box.iloc[:0])
        story, stars = stories.game_story(g, scoring if scoring is not None else sc.iloc[:0], gb[gb.sec_on > 0], name,
                                          before)
        dump(f"game/{season}/{gid}.json", {
            "season": season, "id": int(gid), "date": g.date, "tip_utc": g.tip_utc, "type": g.game_type,
            "story": story, "stars": stars,
            "home": g.home, "away": g.away, "home_score": int(g.home_score), "away_score": int(g.away_score),
            "ot": int(g.ot), "quarters": quarters, "x_home": xh, "x_away": xa, "win_home": wh,
            "box_cols": ["id", "name", "starter", "min", "pts", "reb", "oreb", "ast", "stl", "blk", "tov", "pf",
                         "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "pm"],
            "shot_cols": ["x", "y", "made", "three", "p_milli", "away", "t", "shooter", "heave", "xtrip_milli"],
            "box": boxes, "shots": shots_out, "fts": fts, "flow": flow,
            "names": {str(k): name.get(k, str(k)) for k in set(s.shooter)},
        })
        idx.append([int(gid), g.date, g.tip_utc, g.game_type, g.home, g.away, int(g.home_score), int(g.away_score),
                    int(g.ot), round(xh, 1), round(xa, 1), None if wh is None else round(wh, 3)])
    pd.DataFrame(xrows, columns=["game_id", "x_home", "x_away", "win_home"]).to_csv(out_path(season, "games_x.csv"),
                                                                                    index=False)
    dump(f"games.{season}.json", {"season": season, "cols": ["id", "date", "tip_utc", "type", "home", "away", "hs",
                                                              "as", "ot", "xh", "xa", "win_home"],
                                  "games": sorted(idx, key=lambda r: (r[1], r[2] or ""), reverse=True)})


def live_zone(sh):
    """The zones the live page uses to value a shot (same cut as shot_quality.zone, computable in the browser)."""
    d, side = sh.dist, (sh.x - 25).abs()
    two = np.select([d < 3, d < 6, d < 10, d < 16], ["0-3", "3-6", "6-10", "10-16"], default="16+2")
    three = np.select([(side >= 21.5) & (sh.y <= 9), d < 26, d < 30], ["c3", "ab3", "ab3 deep"], default="ab3 far")
    return np.where(sh.value == 3, three, two)


def shot_values():
    """Make rates by zone and by zone x shot description, for valuing live shots in the browser (the full model
    needs Python; this table scored 0.641 log loss against the model's 0.636 on 2025-26), plus each team's
    second-chance rate for per-trip expected points."""
    frames = []
    for season in (PREV, CUR):
        if os.path.exists(out_path(season, "shots_xp.csv.gz")):
            sh = table(season, "shots")
            frames.append(sh[(sh.heave == 0) & sh.dist.notna()])
    if not frames:
        return
    sh = pd.concat(frames)
    sh["zone"] = live_zone(sh)
    z = sh.groupby("zone").made.agg(["sum", "count"])
    zr = (z["sum"] / z["count"]).to_dict()
    zt = sh.groupby(["zone", "shot_type"]).made.agg(["sum", "count"]).reset_index()
    k = 30
    rates = {f"{r.zone}|{r.shot_type}": round((r["sum"] + k * zr[r.zone]) / (r["count"] + k), 4)
             for _, r in zt.iterrows() if r["count"] >= 5}
    trips = {}
    path = out_path(CUR, "trips.json")
    if os.path.exists(path):
        with open(path) as f:
            tp = json.load(f)
        abbr = dict(zip(table(CUR, "teams").team_id, table(CUR, "teams").abbr))
        trips = {"league": tp["second_chance_rate_league"], "points": tp["second_chance_points"],
                 "q2": tp["q2"], "q3": tp["q3"],
                 "team": {abbr.get(int(t), t): round(v, 4) for t, v in tp["rate_by_team"].items()}}
    dump("shotvalue.json", {"zones": {k_: round(v, 4) for k_, v in zr.items()}, "rates": rates, "trips": trips})


def injuries():
    """The latest injury report: the nightly pull's league-wide list, with each team playing today replaced by its
    list from the newest pre-game snapshot when that is newer. Who's out or questionable, when they're expected
    back, and the report's note (shortened)."""
    import glob
    import gzip
    raw = os.path.join(os.path.dirname(TABLES), "raw")
    files = sorted(glob.glob(os.path.join(raw, "injuries", "*.json.gz")))
    if not files:
        return []
    with gzip.open(files[-1], "rt", encoding="utf-8") as f:
        rep = json.load(f)
    entries, as_of = list(rep.get("data", [])), rep.get("taken_at") or ""
    snaps = {}
    for path in sorted(glob.glob(os.path.join(raw, str(CUR), "pregame", "*", "*.json.gz")))[-40:]:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            sn = json.load(f)
        g = sn.get("game") or {}
        for side in ("home_team", "visitor_team"):
            tid = (g.get(side) or {}).get("id")
            if tid and sn.get("taken_at", "") > max(as_of, snaps.get(tid, ("", None))[0]):
                snaps[tid] = (sn["taken_at"], [r for r in sn.get("injuries") or []
                                              if (r.get("player") or {}).get("team_id") == tid])
    if snaps:
        entries = [r for r in entries if (r.get("player") or {}).get("team_id") not in snaps]
        for _, rows_ in snaps.values():
            entries += rows_
        as_of = max([as_of] + [t for t, _ in snaps.values()])
    teams = table(CUR, "teams") if os.path.exists(os.path.join(TABLES, str(CUR), "teams.csv.gz")) else table(PREV, "teams")
    abbr = dict(zip(teams.team_id, teams.abbr))
    order = {"Out": 0, "Doubtful": 1, "Questionable": 2, "Day-To-Day": 3, "Probable": 4, "Available": 5}
    rows = []
    for r in entries:
        p = r.get("player") or {}
        note = re.sub(r"\s+", " ", r.get("description") or "").strip()
        note = re.sub(r"^Injury/Illness - ", "", note)
        note = re.split(r"(?<=\.) Prior reporting", note)[0]
        if len(note) > 240:
            note = note[:240].rsplit(" ", 1)[0] + "…"
        rows.append({"id": p.get("id"), "name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
                     "team": abbr.get(p.get("team_id")), "status": r.get("status"), "back": r.get("return_date"),
                     "note": note})
    rows.sort(key=lambda r: (r["team"] or "", order.get(r["status"], 9), r["name"]))
    dump("injuries.json", {"as_of": as_of, "players": rows})
    print(f"injuries: {len(rows)} players as of {as_of}")
    return rows


def main():
    if os.path.isdir(DATA):
        shutil.rmtree(DATA)
    seasons, lts, zones, lgs = [], {}, {}, {}
    for season in (CUR, PREV):
        if not os.path.exists(os.path.join(TABLES, str(season), "games.csv.gz")) or \
                not os.path.exists(out_path(season, "players.csv")):
            print(f"skipping {season}: no tables or analysis outputs")
            continue
        D = season_data(season)
        lg, lt = league(season, D)
        games_out(season, D)          # first: writes games_x.csv for the team pages
        zones[season] = teams(season, D, lg, lt)
        lts[season], lgs[season] = lt, lg
        players(season, D, lg)
        n = int(len(D["reg_ids"]))
        last = D["games"].date.max()
        seasons.append({"season": season, "label": LABEL(season), "games": n, "through": last})
        print(f"{season}: {n} regular-season games through {last}")
    inj = injuries()
    shot_values()
    if CUR in lts and PREV in lts:
        import tonight
        import pulse
        tonight.build(dump, lts, zones, inj, lgs)
        pulse.build(dump)
    news = os.path.join(ROOT, "data", "news", "index.json")
    if os.path.exists(news):            # a copy as of this build; the site prefers the repository's live file
        shutil.copy(news, os.path.join(DATA, "news.json"))
    dump("meta.json", {"updated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "current": seasons[0]["season"] if seasons else None, "seasons": seasons,
                       "live_url": os.environ.get("LIVE_URL", "").strip() or None})


if __name__ == "__main__":
    main()
