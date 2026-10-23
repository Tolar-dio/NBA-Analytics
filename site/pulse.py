"""The Pulse: last night's best games, who's hot and cold (judged against the shots they're getting), role changes
against last season, hot starts and what's behind them, rookies, streaks, and teams whose results are running
ahead of or behind their shots.

    pulse.json

Every sentence is written here from our own tables; no web search and no model calls. Two rules from Ice Sheet:
process before results (hot and cold are measured against what the same shots usually return, and every hot
start says whether more minutes, more shots or better shooting is behind it), and small samples say so.
"""
import os

import numpy as np
import pandas as pd

from common import table, out_path, PREV, CUR
from tonight import NICK, nw, the, cap, poss

WINDOW = 10          # games for hot and cold
MIN_SHOTS = 40       # shots in the window before we call anyone hot or cold


def game_score(r):
    """John Hollinger's game score: one number for a box-score line (about 10 is an average game, 40 a great one)."""
    return (r.pts + 0.4 * r.fgm - 0.7 * r.fga - 0.4 * (r.fta - r.ftm) + 0.7 * r.oreb + 0.3 * r.dreb + r.stl
            + 0.7 * r.ast + 0.7 * r.blk - 0.4 * r.pf - r.tov)


def line_of(r):
    return {"min": round(r.sec_on / 60), "pts": int(r.pts), "reb": int(r.reb), "ast": int(r.ast), "stl": int(r.stl),
            "blk": int(r.blk), "tov": int(r.tov), "fg": f"{int(r.fgm)}-{int(r.fga)}", "fg3": f"{int(r.fg3m)}-{int(r.fg3a)}",
            "ft": f"{int(r.ftm)}-{int(r.fta)}"}


def statline(l):
    parts = [f"{l['pts']} points"]
    for k, w in (("reb", "rebounds"), ("ast", "assists"), ("stl", "steals"), ("blk", "blocks")):
        if l[k] >= (8 if k in ("reb", "ast") else 4):
            parts.append(f"{l[k]} {w}")
    return ", ".join(parts[:-1]) + (f" and {parts[-1]}" if len(parts) > 1 else parts[0])


def build(dump, inj=None):
    if not os.path.exists(out_path(CUR, "players.csv")) or not os.path.exists(out_path(PREV, "players.csv")):
        return
    pg = table(CUR, "player_games")
    pg = pg[pg.sec_on > 0].sort_values(["date", "game_id"])
    games = table(CUR, "games")
    bio = {int(r.player_id): r for r in table(CUR, "players").itertuples()}
    for r in table(PREV, "players").itertuples():
        bio.setdefault(int(r.player_id), r)
    cur = pd.read_csv(out_path(CUR, "players.csv"))
    prev = pd.read_csv(out_path(PREV, "players.csv"))
    teams_t = table(CUR, "teams")
    abbr = dict(zip(teams_t.team_id, teams_t.abbr))
    name = lambda pid: f"{bio[pid].first_name} {bio[pid].last_name}" if pid in bio else str(pid)   # noqa: E731
    # one line per player: this season (summed over teams) and last season
    def per_player(df):
        g = df.assign(min_tot=df.mpg * df.gp, pts_tot=df.pts_pg * df.gp, use_w=df.usage * df.mpg * df.gp)
        a = g.groupby("player_id").agg(gp=("gp", "sum"), min_tot=("min_tot", "sum"), pts_tot=("pts_tot", "sum"),
                                       use_w=("use_w", "sum"))
        a["mpg"] = a.min_tot / a.gp
        a["pts_pg"] = a.pts_tot / a.gp
        a["usage"] = a.use_w / a.min_tot.where(a.min_tot > 0)
        main = g.sort_values("min_tot").groupby("player_id").tail(1).set_index("player_id")
        a["team_id"] = main.team_id
        return a
    C, Pv = per_player(cur), per_player(prev)
    last_team = pg.groupby("player_id").team_id.last()
    C["team_id"] = last_team.reindex(C.index).fillna(C.team_id)
    out = {"season": CUR, "through": games.date.max(), "games": int(len(games))}

    # ---------------------------------------------------------------- last night
    last = pg.date.max()
    ln = pg[pg.date == last].copy()
    ln["gs"] = [game_score(r) for r in ln.itertuples()]
    season_high = pg.groupby("player_id").pts.max()
    best_before = pg[pg.date < last].groupby("player_id").pts.max()
    perf = []
    for r in ln.sort_values("gs", ascending=False).head(10).itertuples():
        l = line_of(r)
        notes = []
        if sum(v >= 10 for v in (r.pts, r.reb, r.ast, r.stl, r.blk)) >= 3:
            notes.append("Triple-double.")
        top_pts = int(pg.pts.max())
        if r.pts == top_pts and r.pts >= 30:
            notes.append("The most points by anyone this season." if (pg.pts == top_pts).sum() == 1 else
                         "Ties the most points by anyone this season.")
        elif r.player_id in best_before.index and r.pts > best_before[r.player_id] and r.pts >= 25:
            notes.append(f"His best this season (was {int(best_before[r.player_id])}).")
        won = None
        g = games[games.game_id == r.game_id]
        if len(g):
            g = g.iloc[0]
            won = (g.home_score > g.away_score) == (g.home_id == r.team_id)
        perf.append({"id": int(r.player_id), "name": name(r.player_id), "team": abbr.get(r.team_id),
                     "opp": abbr.get(r.opp_id), "home": int(r.home), "game_id": int(r.game_id), "won": won,
                     "gs": round(r.gs, 1), "line": l, "text": f"{statline(l)} on {l['fg']} shooting"
                     f"{', ' + l['fg3'] + ' from three' if r.fg3m >= 4 else ''} in {l['min']} minutes.", "notes": notes})
    out["last_night"] = {"date": last, "players": perf}

    # ---------------------------------------------------------------- hot and cold, against the shots
    sh = pd.read_csv(out_path(CUR, "shots_xp.csv.gz"))
    sh = sh[(sh.heave == 0) & sh.xpts.notna()]
    sh = sh.merge(games[["game_id", "date"]], on="game_id")
    prev_sh = pd.read_csv(out_path(PREV, "shots_xp.csv.gz"), usecols=["shooter", "heave", "xpts"])
    prev_xpps = prev_sh[prev_sh.heave == 0].groupby("shooter").xpts.agg(["mean", "size"])
    hot = []
    for pid, q in sh.groupby("shooter"):
        days = sorted(q.date.unique())[-WINDOW:]
        w = q[q.date.isin(days)]
        if len(w) < MIN_SHOTS:
            continue
        n = len(days)
        above = (w.made * w.value).sum() - w.xpts.sum()
        xpps = w.xpts.mean()
        pv = prev_xpps.loc[pid] if pid in prev_xpps.index and prev_xpps.loc[pid, "size"] >= 150 else None
        hot.append({"id": int(pid), "name": name(pid), "team": abbr.get(int(last_team[pid])) if pid in last_team.index else None,
                    "games": n, "shots": int(len(w)), "per_game": above / n, "pps": (w.made * w.value).mean(),
                    "xpps": xpps, "prev_xpps": None if pv is None else float(pv["mean"])})
    for h in hot:
        better = h["prev_xpps"] is not None and h["xpps"] - h["prev_xpps"] >= 0.04
        worse = h["prev_xpps"] is not None and h["prev_xpps"] - h["xpps"] >= 0.04
        span = f"over {'his first ' if h['games'] < WINDOW else 'his last '}{nw(h['games'])} games ({h['shots']} shots)"
        if h["per_game"] > 0:
            why = ("His looks are better than last season's too, so not all of it is shooting luck." if better else
                   "And that's on worse looks than last season, which makes it harder to keep up." if worse else
                   "Same kind of looks as last season; they're just falling more often, which rarely lasts." if
                   h["prev_xpps"] is not None else "No season of looks to compare against yet.")
            h["text"] = f"{h['per_game']:.1f} points a game more than his shots usually return, {span}. {why}"
        else:
            why = ("The looks have gotten worse than last season's, so this may not bounce back on its own." if worse
                   else "His looks are as good as last season's or better, so expect the shots to start falling." if
                   h["prev_xpps"] is not None else "No season of looks to compare against yet.")
            h["text"] = f"{-h['per_game']:.1f} points a game fewer than his shots usually return, {span}. {why}"
    hot.sort(key=lambda h: -h["per_game"])
    out["hot"] = [h for h in hot if h["per_game"] >= 2][:8]
    out["cold"] = [h for h in reversed(hot) if h["per_game"] <= -2][:8]

    # ---------------------------------------------------------------- roles against last season
    both = C.join(Pv, rsuffix="_prev", how="inner")
    team_gp = table(CUR, "team_games").groupby("team_id").size()
    early = team_gp.median() < 5 if len(team_gp) else True
    out["early"] = bool(early)
    both = both[(both.gp >= (1 if early else 2)) & (both.gp_prev >= 20)]
    so_far = lambda gp: "in his first game" if gp == 1 else "a game"   # noqa: E731
    roles_up, roles_down, new = [], [], []
    for pid, r in both.iterrows():
        t = abbr.get(int(r.team_id))
        moved = int(r.team_id) != int(r.team_id_prev)
        item = {"id": int(pid), "name": name(pid), "team": t, "mpg": r.mpg, "mpg_prev": r.mpg_prev,
                "usage": r.usage, "usage_prev": r.usage_prev, "pts": r.pts_pg, "pts_prev": r.pts_pg_prev, "gp": int(r.gp)}
        if moved and r.mpg >= 15:
            item["from"] = abbr.get(int(r.team_id_prev))
            item["text"] = (f"{r.mpg:.0f} minutes and {r.pts_pg:.0f} points {so_far(r.gp)} for {the(t)}, after "
                            f"{r.mpg_prev:.0f} and {r.pts_pg_prev:.1f} a game for {the(item['from'])} last season.")
            new.append(item)
        elif r.mpg - r.mpg_prev >= 6:
            use = (f" and using {100 * r.usage:.0f}% of possessions, up from {100 * r.usage_prev:.0f}%"
                   if r.usage - r.usage_prev >= 0.03 else "")
            item["text"] = f"{r.mpg:.0f} minutes {so_far(r.gp)}, up from {r.mpg_prev:.0f} a game last season{use}."
            roles_up.append(item)
        elif r.mpg_prev - r.mpg >= 6 and r.mpg_prev >= 20:
            item["text"] = f"{r.mpg:.0f} minutes {so_far(r.gp)}, down from {r.mpg_prev:.0f} a game last season."
            roles_down.append(item)
    out["roles"] = {"up": sorted(roles_up, key=lambda x: x["mpg_prev"] - x["mpg"])[:10],
                    "down": sorted(roles_down, key=lambda x: x["mpg"] - x["mpg_prev"])[:8],
                    "new": sorted(new, key=lambda x: -x["mpg"])[:12]}

    # ---------------------------------------------------------------- hot starts and what's behind them
    shotm = cur.groupby("player_id").apply(lambda q: pd.Series({"sm": (q.shotmaking * q.shots).sum(),
                                                                 "shots": q.shots.sum()}), include_groups=False)
    starts = []
    for pid, r in both.iterrows():
        d = r.pts_pg - r.pts_pg_prev
        if abs(d) < 6:
            continue
        reasons = []
        if r.mpg - r.mpg_prev >= 5:
            reasons.append(f"more minutes ({r.mpg:.0f}, up from {r.mpg_prev:.0f})")
        elif r.mpg_prev - r.mpg >= 5:
            reasons.append(f"fewer minutes ({r.mpg:.0f}, down from {r.mpg_prev:.0f})")
        if r.usage - r.usage_prev >= 0.03:
            reasons.append(f"a bigger share of the offense ({100 * r.usage:.0f}% of possessions, from {100 * r.usage_prev:.0f}%)")
        elif r.usage_prev - r.usage >= 0.03:
            reasons.append(f"a smaller share of the offense ({100 * r.usage:.0f}% of possessions, from {100 * r.usage_prev:.0f}%)")
        sm = shotm.loc[pid] if pid in shotm.index else None
        if sm is not None and sm.shots >= 20:
            per = sm.sm / r.gp
            if per >= 2:
                reasons.append(f"shots falling ({per:.1f} points a game above what his looks usually return)")
            elif per <= -2:
                reasons.append(f"shots not falling ({-per:.1f} points a game below what his looks usually return)")
        why = (", ".join(reasons[:-1]) + (" and " if len(reasons) > 1 else "") + reasons[-1]) if reasons else \
            "the same minutes and role, so watch whether it holds"
        starts.append({"id": int(pid), "name": name(pid), "team": abbr.get(int(r.team_id)), "pts": r.pts_pg,
                       "pts_prev": r.pts_pg_prev, "gp": int(r.gp), "delta": d,
                       "text": (f"{r.pts_pg:.0f} points in his first game" if r.gp == 1 else
                                f"{r.pts_pg:.1f} points a game over {nw(int(r.gp))} games") + f", {'up' if d > 0 else 'down'} from "
                       f"{r.pts_pg_prev:.1f} a game last season. Behind it: {why}."})
    out["starts"] = {"up": sorted([s for s in starts if s["delta"] > 0], key=lambda s: -s["delta"])[:10],
                     "down": sorted([s for s in starts if s["delta"] < 0], key=lambda s: s["delta"])[:8]}

    # ---------------------------------------------------------------- rookies
    rk = []
    for pid, r in C.iterrows():
        b = bio.get(int(pid))
        if b is None or b.draft_year != CUR or r.mpg < 8:
            continue
        line = cur[cur.player_id == pid].sort_values("gp").iloc[-1]
        pick = None if pd.isna(b.draft_number) else int(b.draft_number)
        rk.append({"id": int(pid), "name": name(pid), "team": abbr.get(int(r.team_id)), "pick": pick, "gp": int(r.gp),
                   "mpg": r.mpg, "pts": r.pts_pg, "reb": float(line.reb_pg), "ast": float(line.ast_pg),
                   "usage": r.usage, "ts": float(line.ts) if pd.notna(line.ts) else None,
                   "college": None if pd.isna(b.college) else b.college})
    out["rookies"] = sorted(rk, key=lambda x: -x["mpg"] * x["gp"])[:15]

    # ---------------------------------------------------------------- streaks (this season, games he played)
    tests = [("30", lambda r: r.pts >= 30, 2, "straight games with 30 or more points"),
             ("20", lambda r: r.pts >= 20, 4, "straight games with 20 or more points"),
             ("dd", lambda r: sum(v >= 10 for v in (r.pts, r.reb, r.ast, r.stl, r.blk)) >= 2, 3, "straight double-doubles"),
             ("3s", lambda r: r.fg3m >= 4, 3, "straight games with four or more threes"),
             ("cold", lambda r: r.fga >= 8 and r.fgm / r.fga < 0.35, 3, "straight games under 35% shooting on eight or more shots")]
    streaks = []
    for pid, q in pg.groupby("player_id"):
        rows = list(q.itertuples())
        for key, test, need, words in tests:
            n = 0
            for r in reversed(rows):
                if test(r):
                    n += 1
                else:
                    break
            if n >= need:
                streaks.append({"id": int(pid), "name": name(pid), "team": abbr.get(int(rows[-1].team_id)), "kind": key,
                                "n": n, "text": f"{cap(nw(n))} {words}." if n <= 10 else f"{n} {words}."})
    order = {"30": 0, "dd": 1, "20": 2, "3s": 3, "cold": 4}
    # one streak per player, the most notable
    best = {}
    for s in sorted(streaks, key=lambda s: (order[s["kind"]], -s["n"])):
        best.setdefault(s["id"], s)
    out["streaks"] = sorted(best.values(), key=lambda s: (order[s["kind"]], -s["n"]))[:14]

    # ---------------------------------------------------------------- teams against their shots
    tm = pd.read_csv(out_path(CUR, "teams.csv"))
    rec = {}
    for g in games[games.game_type == "regular"].itertuples():
        for tid, won in ((g.home_id, g.home_score > g.away_score), (g.away_id, g.away_score > g.home_score)):
            w, l = rec.get(tid, (0, 0))
            rec[tid] = (w + won, l + (not won))
    trows = []
    for r in tm.itertuples():
        gap = r.net - r.x_net
        w, l = rec.get(r.team_id, (0, 0))
        text = (f"{w}-{l}, {'outscoring opponents' if r.net >= 0 else 'outscored'} by {abs(r.net):.1f} per 100 "
                f"possessions; their shots say {'+' if r.x_net >= 0 else '−'}{abs(r.x_net):.1f}.")
        why = []
        if gap > 0:
            if r.shotmaking > 0.02:
                why.append("they've made more of their looks than usual")
            if r.opp_shotmaking < -0.02:
                why.append("opponents have missed more of theirs")
        else:
            if r.shotmaking < -0.02:
                why.append("they've missed more of their looks than usual")
            if r.opp_shotmaking > 0.02:
                why.append("opponents have made more of theirs")
        if why:
            text += " " + cap(" and ".join(why)) + "."
        trows.append({"team": abbr.get(r.team_id), "gp": int(r.gp), "w": w, "l": l, "net": r.net, "x_net": r.x_net,
                      "gap": gap, "text": text})
    trows = [t for t in trows if t["gp"] >= 3]
    out["teams"] = {"ahead": sorted([t for t in trows if t["gap"] >= 3], key=lambda t: -t["gap"])[:6],
                    "behind": sorted([t for t in trows if t["gap"] <= -3], key=lambda t: t["gap"])[:6]}
    dump("pulse.json", out)
    print(f"pulse: last night {last}, {len(out['hot'])} hot, {len(out['cold'])} cold, {len(new)} on new teams, "
          f"{len(rk)} rookies, {len(out['streaks'])} streaks")
