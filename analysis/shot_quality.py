"""Expected points per shot (the basketball version of xG): the chance a field-goal attempt goes in, times its value.

    python analysis/shot_quality.py 2025          # train out of fold on one season, report, save per-shot values
    python analysis/shot_quality.py 2025 2026     # train on both seasons together (out of fold, grouped by game)

Features, all known before the ball leaves the shooter's hand:
  where     distance from the hoop, distance to the side, 2 or 3, corner three
  what      the scorer's shot description cut into flags: dunk, layup, tip, putback, alley-oop, hook, floater, bank,
            fadeaway, turnaround, step-back, pull-up, running, driving, cutting
  context   seconds since his team got the ball and how (defensive rebound, steal, other turnover, opponent make or
            free throw, period start), whether it follows his team's offensive rebound (within 3 s = putback, or
            any second chance), last 4 seconds of a period, score margin, period
Never used: whether it was assisted or blocked (only known after the shot).

Benchmarks: league average by zone (distance band and 2/3), and by zone x shot family, both out of fold. No free
per-shot NBA model is published to compare against (as far as we know), so the zone baselines are the bar.
Heaves (missed end-of-period heaves aren't attempts in the box) are left out of training and valued at the
league's heave rate.

Output: analysis/output/<season>/shots_xp.csv.gz (game_id, order, team_id, shooter, made, value, p_make, xpts,
xpts_trip, heave, poss, seq, k), trips.json (second-chance parameters) and shot_quality.json (metrics,
calibration). Use xpts for judging a shooter's shots one at a time, xpts_trip for anything summed over a team, a
lineup or a game (see trips()).
"""
import json
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

from common import table, out_path, logloss

FAMILIES = ["dunk", "layup", "tip", "putback", "alley oop", "hook", "float", "bank", "fade", "turnaround",
            "step back", "pullup", "running", "driving", "cutting", "finger roll", "reverse"]


def possession_context(plays, games):
    """For each field-goal attempt: seconds since his team gained the ball, how, second-chance flags, score margin
    before the shot, whether it came in the last 4 seconds of a period, and which possession it belongs to (a new
    one starts after a make, a made last free throw, a defensive rebound, a turnover or a new period; an offensive
    rebound keeps it going)."""
    teams = {r.game_id: (r.home_id, r.away_id) for r in games.itertuples(index=False)}
    rows = []
    for gid, g in plays.groupby("game_id", sort=False):
        home, away = teams.get(gid, (None, None))
        other = {home: away, away: home}
        owner, start_t, kind, oreb_t, period = None, 0.0, "period", None, None
        prev_h, prev_a = 0, 0
        poss, seq = 0, 0

        def new(team, t, k):
            nonlocal owner, start_t, kind, oreb_t, poss
            owner, start_t, kind, oreb_t = team, t, k, None
            poss += 1

        for r in g.itertuples(index=False):
            if r.period != period:
                period = r.period
                new(None, r.t, "period")
            typ, team = r.type, r.team_id
            text = r.text if isinstance(r.text, str) else ""
            if r.shooting == 1 and "Free Throw" not in typ:
                if owner is None:
                    owner = team
                same = owner == team
                if not same:          # the feed missed a change of possession
                    new(team, r.t, "unknown")
                margin = (prev_h - prev_a) if team == home else (prev_a - prev_h)
                rows.append((gid, r.order, (r.t - start_t) if same else np.nan, kind if same else "unknown",
                             int(same and oreb_t is not None and r.t - oreb_t <= 3), int(same and oreb_t is not None),
                             margin, int(r.clock_left <= 4), poss, seq))
                seq += 1
                if r.scoring == 1:
                    new(other.get(team), r.t, "made")
            elif "Free Throw" in typ:
                if r.scoring == 1 and any(k in typ for k in ("1 of 1", "2 of 2", "3 of 3")):
                    new(other.get(team), r.t, "ft")
            elif "Defensive Rebound" in typ:
                new(team, r.t, "dreb")
            elif "Offensive Rebound" in typ:
                if owner != team:
                    new(team, r.t, "dreb")   # the feed missed a change; treat as a fresh start
                oreb_t = r.t
            elif "Turnover" in typ:
                new(other.get(team), r.t, "steal" if "steals" in text else "to")
            if pd.notna(r.home_score):
                prev_h, prev_a = r.home_score, r.away_score
    return pd.DataFrame(rows, columns=["game_id", "order", "since_start", "start_kind", "putback", "second_chance",
                                       "margin", "late", "poss", "seq"])


def trips(df, k_prior=50):
    """Expected points per trip down the floor. Summing every shot's expected points credits a team for shots that
    only happened because the ones before missed (a 107-shot, 26-offensive-rebound night "deserved" 149 points).
    Instead each possession counts its first shot at its own quality, plus, if that misses, the team's rate of
    getting another shot off an offensive rebound (its season rate, shrunk toward the league with 50 misses) times
    the league's points from those second chances. Totals match what actually went in; later shots in a possession
    count as 0 here. Returns per-shot xpts_trip and the parameters."""
    df = df.sort_values(["game_id", "seq"]).copy()
    df["k"] = df.groupby(["game_id", "poss"]).cumcount()
    first = df[df.k == 0]
    cont = df[df.k >= 1].assign(p=df.made * df.value).groupby(["game_id", "poss"]).agg(team_id=("team_id", "first"),
                                                                                         pts=("p", "sum"))
    n_cont = cont.groupby("team_id").size()
    first_miss = (1 - first.made).groupby(first.team_id).sum()
    lg_rate = n_cont.sum() / first_miss.sum()
    rate = ((n_cont.reindex(first_miss.index).fillna(0) + k_prior * lg_rate) / (first_miss + k_prior))
    q2, q3 = float((cont.pts == 2).mean()), float((cont.pts == 3).mean())
    c = 2 * q2 + 3 * q3
    r = df.team_id.map(rate).fillna(lg_rate)
    df["xpts_trip"] = np.where(df.k == 0, df.p_make * df.value + (1 - df.p_make) * r * c, 0.0)
    params = {"second_chance_rate_league": float(lg_rate), "second_chance_points": c, "q2": q2, "q3": q3,
              "rate_by_team": {int(k): float(v) for k, v in rate.items()}}
    return df[["xpts_trip", "k"]], params


def features(shots, ctx):
    s = shots.merge(ctx, on=["game_id", "order"], how="left")
    st = s.shot_type.fillna("").str.lower()
    for f in FAMILIES:
        s["f_" + f.replace(" ", "_")] = st.str.contains(f).astype(int)
    s["side"] = (s.x - 25).abs()
    s["corner3"] = ((s.value == 3) & (s.side >= 21.5) & (s.y <= 9)).astype(int)
    s["three"] = (s.value == 3).astype(int)
    s["since_start"] = s.since_start.clip(0, 30)
    for k in ("dreb", "steal", "to", "made", "ft", "period"):
        s["start_" + k] = (s.start_kind == k).astype(int)
    s["margin"] = s.margin.clip(-30, 30)
    return s


def zone(s):
    d = s.dist
    band = np.select([d < 3, d < 6, d < 10, d < 16, s.value == 2], ["0-3", "3-6", "6-10", "10-16", "16+2"],
                     default="")
    three = np.select([s.corner3 == 1, d < 26, d < 30], ["c3", "ab3", "ab3 deep"], default="ab3 heave-range")
    return np.where(s.value == 3, three, band)


FEATS = ["dist", "side", "y", "three", "corner3", "since_start", "putback", "second_chance", "margin", "period", "late",
         "start_dreb", "start_steal", "start_to", "start_made", "start_ft", "start_period"] + \
        ["f_" + f.replace(" ", "_") for f in FAMILIES]


def oof(model_fn, X, y, groups, k=5):
    p = np.zeros(len(y))
    for tr, te in GroupKFold(k).split(X, y, groups):
        m = model_fn()
        m.fit(X.iloc[tr], y.iloc[tr])
        p[te] = m.predict_proba(X.iloc[te])[:, 1]
    return p


def oof_mean(keys, y, groups, k=5):
    p = np.zeros(len(y))
    df = pd.DataFrame({"k": keys, "y": y.values})
    for tr, te in GroupKFold(k).split(df, y, groups):
        prior = df.y.iloc[tr].mean()
        means = df.iloc[tr].groupby("k").y.agg(["sum", "count"])
        # shrink thin cells toward the overall rate (20 shots)
        rate = (means["sum"] + 20 * prior) / (means["count"] + 20)
        p[te] = df.k.iloc[te].map(rate).fillna(prior).values
    return p


def main():
    seasons = [int(a) for a in sys.argv[1:]] or [2025]
    shots, plays, games = [], [], []
    for se in seasons:
        sh, pl, ga = table(se, "shots"), table(se, "plays"), table(se, "games")
        sh["season"] = se
        shots.append(sh); plays.append(pl); games.append(ga)
    shots, plays, games = pd.concat(shots), pd.concat(plays), pd.concat(games)
    ctx = possession_context(plays, games)
    s = features(shots, ctx)
    heave = s.heave == 1
    heave_rate = float(s[heave].made.mean()) if heave.any() else 0.0
    t = s[~heave & s.dist.notna()].reset_index(drop=True)
    y, g = t.made, t.game_id
    X = t[FEATS].fillna(-1)

    res = {"seasons": seasons, "shots": int(len(t)), "make_rate": round(float(y.mean()), 4),
           "pps": round(float((t.made * t.value).mean()), 4)}
    preds = {
        "zone": oof_mean(zone(t), y, g),
        "zone_x_family": oof_mean(pd.Series(zone(t)) + "|" + t.shot_type.fillna("").values, y, g),
        "logistic": oof(lambda: LogisticRegression(max_iter=2000, C=1.0), X, y, g),
        "boosted": oof(lambda: HistGradientBoostingClassifier(max_iter=400, learning_rate=0.05, max_leaf_nodes=31,
                                                             min_samples_leaf=60, l2_regularization=1.0), X, y, g),
    }
    res["models"] = {k: {"logloss": round(logloss(y, p), 5), "auc": round(float(roc_auc_score(y, p)), 4),
                         "brier": round(float(np.mean((p - y) ** 2)), 5)} for k, p in preds.items()}
    best = min(preds, key=lambda k: res["models"][k]["logloss"])
    res["chosen"] = best
    p = preds[best]
    t["p_make"], t["xpts"] = p, p * t.value
    # calibration by zone and by shot family (predicted vs actual make rate)
    t["zone"] = zone(t)
    cal = t.groupby("zone").agg(n=("made", "size"), actual=("made", "mean"), predicted=("p_make", "mean"))
    res["calibration_by_zone"] = cal.round(4).reset_index().values.tolist()
    t["bin"] = pd.cut(t.p_make, [0, .2, .3, .4, .5, .6, .7, .8, 1])
    cb = t.groupby("bin", observed=True).agg(n=("made", "size"), actual=("made", "mean"), predicted=("p_make", "mean"))
    res["calibration_by_bin"] = [[str(i), int(r.n), round(r.actual, 4), round(r.predicted, 4)] for i, r in cb.iterrows()]
    ctxs = t.groupby("start_kind").agg(n=("made", "size"), make=("made", "mean"), pps=("xpts", "mean"))
    res["by_start"] = ctxs.round(4).reset_index().values.tolist()
    res["putback_make"] = round(float(t[t.putback == 1].made.mean()), 4)
    res["heave_rate"] = round(heave_rate, 4)

    h = s[heave].copy()
    h["p_make"], h["xpts"] = heave_rate, heave_rate * h.value
    allx = pd.concat([t, h], ignore_index=True)
    allx["xpts_trip"], allx["k"] = np.nan, 0
    trip_params = {}
    for se in seasons:
        m = allx.season == se
        tr, prm = trips(allx[m])
        allx.loc[tr.index, ["xpts_trip", "k"]] = tr.values
        trip_params[se] = prm
        fgp = (allx[m].made * allx[m].value).sum()
        res.setdefault("trips", {})[se] = {"fg_points": int(fgp), "sum_xpts": round(float(allx[m].xpts.sum())),
                                          "sum_xpts_trip": round(float(allx[m].xpts_trip.sum())),
                                          **{k: v for k, v in prm.items() if k != "rate_by_team"}}
    allx = allx[["season", "game_id", "order", "team_id", "shooter", "made", "value", "p_make", "xpts", "xpts_trip",
                 "heave", "poss", "seq", "k"]]
    for se in seasons:
        allx[allx.season == se].drop(columns="season").round(4).to_csv(out_path(se, "shots_xp.csv.gz"), index=False)
        with open(out_path(se, "trips.json"), "w") as f:
            json.dump(trip_params[se], f, indent=1)
    with open(out_path(seasons[-1], "shot_quality.json"), "w") as f:
        json.dump(res, f, indent=1, default=str)
    print(json.dumps({k: res[k] for k in ("seasons", "shots", "make_rate", "pps", "models", "chosen",
                                          "trips")}, indent=1))
    print("calibration by zone [zone, n, actual, predicted]:")
    for r in res["calibration_by_zone"]:
        print("  ", r)
    print("by how the possession started [kind, n, make, xPPS]:", res["by_start"])


if __name__ == "__main__":
    main()
