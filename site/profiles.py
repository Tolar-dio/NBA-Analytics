"""How a player plays (percentiles among his position, and a few plain sentences), and who plays when for each team.

profiles(players, bios, min_gp): {player_id: profile} for each player's main team that season, ranked among
guards, forwards or centers with 12+ minutes a game and enough games.
rotation(stints, team_id, game_ids, names): each regular's share of games on the floor in every minute of
regulation, for the team page's rotation chart.
"""
import numpy as np
import pandas as pd

GROUP = {"G": "guards", "F": "forwards", "C": "centers"}
# key, label, kind ("style": neither good nor bad; "good": higher is better; "low": lower is better), format
METRICS = [
    ("usage", "Possessions he uses", "style", "pct0"),
    ("three_share", "Shots that are threes", "style", "pct0"),
    ("share_rim", "Shots at the rim", "style", "pct0"),
    ("share_mid", "Shots that are midrange twos", "style", "pct0"),
    ("assisted_share", "Makes that were assisted", "style", "pct0"),
    ("ast_p36", "Assists per 36 minutes", "style", "d1"),
    ("reb_p36", "Rebounds per 36", "style", "d1"),
    ("touches_p36", "Touches per 36", "style", "d0"),
    ("ts", "True shooting", "good", "pct1"),
    ("shotmaking", "Points per shot above what his looks produce", "good", "s2"),
    ("tov_p36", "Turnovers per 36", "low", "d1"),
    ("stl_p36", "Steals per 36", "good", "d1"),
    ("blk_p36", "Blocks per 36", "good", "d1"),
    ("deflections_p36", "Deflections per 36", "good", "d1"),
    ("rim_dfg_vs_lg", "FG% allowed at the rim, against league", "low", "spct"),
]


def fmt(v, f):
    if v is None or v != v:
        return None
    return {"pct0": f"{100 * v:.0f}%", "pct1": f"{100 * v:.1f}%", "d1": f"{v:.1f}", "d0": f"{v:.0f}",
            "s2": f"{'+' if v >= 0 else '−'}{abs(v):.2f}",
            "spct": f"{'+' if v >= 0 else '−'}{100 * abs(v):.1f}"}[f]


def group_of(position):
    p = str(position or "")[:1].upper()
    return GROUP.get(p)


def profiles(players, positions, min_gp):
    """positions: player_id -> BDL position ("G", "F-C", ...)."""
    p = players.copy()
    p["three_share"] = p.share_above3.fillna(0) + p.share_corner3.fillna(0)
    p["group"] = [group_of(positions.get(int(i))) for i in p.player_id]
    p["load"] = p.gp * p.mpg
    main = p.sort_values("load").groupby("player_id").tail(1)
    pool = main[(main.mpg >= 12) & (main.gp >= min_gp) & main.group.notna()].copy()
    # thin samples don't get a rank: rim defense needs 50 shots defended, shot-making 100 shots
    pool.loc[pool.defended_at_rim_fga.fillna(0) < 50, "rim_dfg_vs_lg"] = np.nan
    pool.loc[pool.shots.fillna(0) < 100, "shotmaking"] = np.nan
    ranks = {}
    for key, _, kind, _ in METRICS:
        if key not in pool.columns:
            continue
        r = pool.groupby("group")[key].rank(pct=True)
        ranks[key] = (1 - r + 1 / pool.groupby("group")[key].transform("count")) if kind == "low" else r
    out = {}
    for i, row in pool.iterrows():
        g = row.group
        rows, P = [], {}
        for key, label, kind, f in METRICS:
            if key not in ranks or pd.isna(ranks[key][i]) or pd.isna(row[key]):
                continue
            pc = int(round(100 * min(max(ranks[key][i], 0), 1)))
            P[key] = pc
            rows.append([key, label, fmt(row[key], f), pc, "style" if kind == "style" else "quality"])
        out[int(row.player_id)] = {"group": g, "pool": int((pool.group == g).sum()), "rows": rows,
                                   "words": describe(row, P, g)}
    return out


def describe(r, P, g):
    s = []
    one = g[:-1]

    def more(pc):
        return f"more than any other {one}" if pc >= 99 else f"more than {pc}% of {g}"
    if P.get("usage", 50) >= 85:
        s.append(f"The offense runs through him: he uses {100 * r.usage:.0f}% of the possessions while he's on the "
                 f"floor, {more(P['usage'])}.")
    elif P.get("usage", 50) <= 15:
        s.append(f"A finisher more than a creator: he uses {100 * r.usage:.0f}% of possessions, fewer than most {g}.")
    # a shot diet worth a sentence has to stand out among his position and in absolute terms
    floor = {"three_share": 0.45, "share_rim": 0.40, "share_mid": 0.15}
    diet = max(((k, P.get(k, 0)) for k in floor if (r[k] if r[k] == r[k] else 0) >= floor[k]),
               key=lambda x: x[1], default=(None, 0))
    if diet[1] >= 80:
        s.append({"three_share": f"Lives behind the arc: {100 * r.three_share:.0f}% of his shots are threes.",
                  "share_rim": f"Gets to the rim: {100 * r.share_rim:.0f}% of his shots come from under four feet.",
                  "share_mid": f"One of the {g} who still lives in the midrange: {100 * r.share_mid:.0f}% of his "
                               f"shots are twos from 14 feet out."}[diet[0]])
    if P.get("assisted_share", 50) >= 85:
        s.append(f"Teammates set him up: {100 * r.assisted_share:.0f}% of his baskets come off a pass.")
    elif P.get("assisted_share", 50) <= 15:
        s.append(f"Makes his own shots: only {100 * r.assisted_share:.0f}% of his baskets are assisted.")
    if P.get("ast_p36", 0) >= 85:
        s.append(f"A playmaker: {r.ast_p36:.1f} assists per 36 minutes, {more(P['ast_p36'])}.")
    if P.get("shotmaking", 50) >= 85:
        s.append(f"Makes more of his shots than the looks are worth, among the best {one}s at it.")
    elif P.get("shotmaking", 50) <= 15:
        s.append("Makes fewer of his shots than the looks are usually worth.")
    if P.get("rim_dfg_vs_lg", 0) >= 80:
        s.append(f"Protects the rim: opponents shoot {100 * abs(r.rim_dfg_vs_lg):.0f} points worse than the league "
                 f"at the rim when he's defending.")
    elif P.get("deflections_p36", 0) >= 85:
        s.append(f"Busy hands on defense: {r.deflections_p36:.1f} deflections per 36 minutes.")
    return s[:4]


def rotation(stints, team_id, game_ids, names):
    """For each regular, the share of his games he was on the floor in each minute of regulation (0-100), with his
    minutes a game: players in at least a quarter of the games (two of the last ten) averaging 8+ minutes."""
    st = stints[(stints.team_id == team_id) & stints.game_id.isin(game_ids) & (stints.start < 2880)]
    n = len(set(st.game_id))
    if not n:
        return None
    occ, games = {}, {}
    for r in st.itertuples(index=False):
        s, e = float(r.start), min(float(r.end), 2880.0)
        if e <= s:
            continue
        b0, b1 = int(s // 60), int(min((e - 1e-9) // 60, 47))
        for pid in (r.p1, r.p2, r.p3, r.p4, r.p5):
            if pid != pid:
                continue
            pid = int(pid)
            a = occ.setdefault(pid, np.zeros(48))
            games.setdefault(pid, set()).add(r.game_id)
            for b in range(b0, b1 + 1):
                a[b] += min(e, (b + 1) * 60) - max(s, b * 60)
    rows = []
    for pid, a in occ.items():
        gp = len(games[pid])
        m = a.sum() / 60 / gp
        if m >= 8 and gp >= max(1, min(0.25 * n, 2 if n <= 10 else 0.25 * n)):
            rows.append([pid, names.get(pid, str(pid)), round(m, 1), gp, [int(round(100 * v / (60 * gp))) for v in a]])
    rows.sort(key=lambda r: -r[2])
    return {"games": n, "players": rows[:13]}
