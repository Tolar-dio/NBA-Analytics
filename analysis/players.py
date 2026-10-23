"""Player tables: role, usage, shooting against expectation, on/off, defense, and five-man lineups.

    python analysis/players.py 2025      # needs analysis/output/<season>/shots_xp.csv.gz from shot_quality.py

Everything on-court comes from our stints (five-man stretches rebuilt from the play-by-play). Each team stint gets
its own and its opponent's field-goal attempts, free-throw attempts, offensive rebounds (players only, not team
rebounds after a missed first free throw), turnovers (any play type with "Turnover" in it, plus Traveling: this
matches the box for 99.8% of player-games), points and expected points. Possessions in a stint are the average of
the two sides' FGA - OREB + TOV + 0.44 FTA.

Outputs (analysis/output/<season>/):
  stint_stats.csv.gz   per team stint: seconds, possessions, points and expected points for and against
  player_games.csv.gz  per player-game: seconds on, team possessions on, his usage plays and usage share
  players.csv          per player and team: role, box rates, usage, true shooting, shot mix, expected points per
                       shot and shot-making, on/off (actual and from shot quality), BDL tracking (rim defense,
                       contests, deflections, touches)
  lineups.csv          five-man units with 40+ possessions: minutes, possessions, ratings, expected net
"""
import sys

import numpy as np
import pandas as pd

from common import table, out_path

RIM, SHORT = 4, 14


def is_tov(types):
    return (types.str.contains("Turnover") & (types != "No Turnover")) | (types == "Traveling")


def stint_stats(season):
    pl = table(season, "plays")
    games = table(season, "games")[["game_id", "home_id", "away_id", "game_type"]]
    xp = pd.read_csv(out_path(season, "shots_xp.csv.gz"))[["game_id", "order", "xpts_trip", "heave"]] \
        .rename(columns={"xpts_trip": "xpts"})   # per trip, so a stint isn't credited twice for one possession
    pl = pl.merge(games, on="game_id").merge(xp, on=["game_id", "order"], how="left")
    ft = pl.type.str.contains("Free Throw")
    pl["fga"] = ((pl.shooting == 1) & ~ft & (pl.heave != 1)).astype(int)
    pl["fta"] = ft.astype(int)
    pl["oreb"] = ((pl.type == "Offensive Rebound") & pl.p1.notna()).astype(int)
    pl["tov"] = is_tov(pl.type).astype(int)
    pl["pts"] = np.where(pl.scoring == 1, pl.value, 0)
    pl["xp"] = pl.xpts.fillna(0) + np.where(ft & (pl.scoring == 1), 1, 0)   # free throws count as they happened
    acting = pl[pl.team_id.notna()]
    cols = ["fga", "fta", "oreb", "tov", "pts", "xp"]
    parts = []
    for side in ("home", "away"):
        team = acting[f"{side}_id"]
        d = acting[["game_id", f"{side}_stint"] + cols].rename(columns={f"{side}_stint": "stint"})
        own = acting.team_id == team
        a = d[own].groupby("stint")[cols].sum().add_suffix("_for")
        b = d[~own].groupby("stint")[cols].sum().add_suffix("_against")
        parts.append(a.join(b, how="outer"))
    st = pd.concat(parts).fillna(0)
    # the stints table's own pts_for/pts_against are the same points; the play-level sums replace them
    stints = table(season, "stints").drop(columns=["pts_for", "pts_against"]).set_index("stint")
    stints = stints.join(st, how="left").fillna({c: 0 for c in st.columns})
    stints["sec"] = stints.end - stints.start
    stints = stints[stints.sec > 0]
    pf = stints.fga_for - stints.oreb_for + stints.tov_for + 0.44 * stints.fta_for
    pa = stints.fga_against - stints.oreb_against + stints.tov_against + 0.44 * stints.fta_against
    stints["poss"] = (pf + pa) / 2
    stints = stints.reset_index().merge(games[["game_id", "game_type"]], on="game_id")
    stints.round(3).to_csv(out_path(season, "stint_stats.csv.gz"), index=False)
    return stints, pl


def long_on(stints):
    """One row per (stint, player on court)."""
    return pd.concat([stints.assign(player_id=stints[f"p{i}"]) for i in range(1, 6)]).dropna(subset=["player_id"]) \
        .astype({"player_id": int})


def rate(num, den, k=100):
    return np.where(den > 0, k * num / np.maximum(den, 1e-9), np.nan)


def build(season):
    stints, pl = stint_stats(season)
    reg = stints[stints.game_type == "regular"]
    on = long_on(reg)

    # usage: his FGA + 0.44 FTA + TOV over his team's while he's on court
    pl["usage_plays"] = pl.fga + 0.44 * pl.fta + pl.tov
    mine = pl[pl.p1.notna() & (pl.usage_plays > 0)].copy()
    mine["player_id"] = mine.p1.astype(int)
    up = mine.groupby(["game_id", "player_id"]).usage_plays.sum()
    on["team_plays"] = on.fga_for + 0.44 * on.fta_for + on.tov_for
    pgon = on.groupby(["game_id", "team_id", "player_id"]).agg(sec_on=("sec", "sum"), poss_on=("poss", "sum"),
                                                                team_plays=("team_plays", "sum")).reset_index()
    pgon = pgon.merge(up.rename("usage_plays").reset_index(), on=["game_id", "player_id"], how="left").fillna(
        {"usage_plays": 0})
    pgon["usage"] = np.where(pgon.team_plays > 0, pgon.usage_plays / pgon.team_plays, np.nan)
    pgon.round(4).to_csv(out_path(season, "player_games.csv.gz"), index=False)

    # box per player-team (regular season and Cup)
    box = table(season, "player_games").merge(table(season, "games")[["game_id", "game_type"]], on="game_id")
    box = box[(box.game_type == "regular") & (box.sec_on > 0)]
    agg = box.groupby(["player_id", "team_id", "team"]).agg(
        gp=("game_id", "nunique"), gs=("starter", "sum"), sec=("sec_on", "sum"),
        **{k: (k, "sum") for k in ["pts", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "reb", "ast",
                                    "stl", "blk", "tov", "pf"]}).reset_index()
    mins = agg.sec / 60
    out = agg[["player_id", "team_id", "team", "gp", "gs"]].copy()
    out["mpg"] = mins / agg.gp
    for k in ["pts", "reb", "ast", "stl", "blk", "tov", "fg3m"]:
        out[f"{k}_pg"] = agg[k] / agg.gp
        out[f"{k}_p36"] = rate(agg[k], mins, 36)
    out["ts"] = agg.pts / (2 * (agg.fga + 0.44 * agg.fta)).replace(0, np.nan)
    out["fg3_pct"] = agg.fg3m / agg.fg3a.replace(0, np.nan)
    out["ft_pct"] = agg.ftm / agg.fta.replace(0, np.nan)
    u = pgon.groupby(["player_id", "team_id"])[["usage_plays", "team_plays", "poss_on"]].sum()
    out = out.merge((u.usage_plays / u.team_plays).rename("usage").reset_index(), on=["player_id", "team_id"],
                    how="left")
    out = out.merge(u.poss_on.rename("poss_on").reset_index(), on=["player_id", "team_id"], how="left")

    # shooting against expectation and shot mix
    sh = table(season, "shots").merge(pd.read_csv(out_path(season, "shots_xp.csv.gz"))[["game_id", "order", "xpts"]],
                                      on=["game_id", "order"])
    sh = sh[sh.heave == 0]
    sh["pts"] = sh.made * sh.value
    sh["zone"] = np.select([sh.dist < RIM, sh.dist < SHORT, sh.value == 2, (sh.x - 25).abs() >= 21.5],
                           ["rim", "short", "mid", "corner3"], default="above3")
    g = sh.groupby(["shooter", "team_id"])
    s = pd.DataFrame({"shots": g.size(), "pps": g.pts.mean(), "xpps": g.xpts.mean(),
                      "assisted_share": g.apply(lambda q: q[q.made == 1].assist.notna().mean()
                                                if (q.made == 1).any() else np.nan, include_groups=False)})
    s["shotmaking"] = s.pps - s.xpps
    mix = pd.crosstab([sh.shooter, sh.team_id], sh.zone, normalize="index").add_prefix("share_")
    s = s.join(mix).reset_index().rename(columns={"shooter": "player_id"})
    out = out.merge(s, on=["player_id", "team_id"], how="left")

    # on/off per 100 possessions, actual and from shot quality
    team = reg.groupby("team_id")[["poss", "pts_for", "pts_against", "xp_for", "xp_against"]].sum()
    o = on.groupby(["player_id", "team_id"])[["poss", "pts_for", "pts_against", "xp_for", "xp_against"]].sum()
    o = o.join(team, on="team_id", rsuffix="_team")
    for k in ("", "x"):
        f, a = ("pts_for", "pts_against") if not k else ("xp_for", "xp_against")
        on_net = rate(o[f] - o[a], o.poss)
        off_poss = o.poss_team - o.poss
        off_net = rate((o[f + "_team"] - o[f]) - (o[a + "_team"] - o[a]), off_poss)
        o[f"{k}on_net"] = on_net
        o[f"{k}off_net"] = off_net
        o[f"{k}on_off"] = on_net - off_net
    o["on_ortg"] = rate(o.pts_for, o.poss)
    o["on_drtg"] = rate(o.pts_against, o.poss)
    keep = ["on_ortg", "on_drtg", "on_net", "off_net", "on_off", "xon_net", "xoff_net", "xon_off"]
    out = out.merge(o[keep].reset_index(), on=["player_id", "team_id"], how="left")

    # BDL tracking, summed over full games (rim protection, contests, deflections, touches)
    try:
        adv = table(season, "advanced")
        adv = adv.merge(box[["game_id", "player_id", "team_id"]], on=["game_id", "player_id", "team_id"])
        tk = [c for c in ("defended_at_rim_fga", "defended_at_rim_fgm", "contested_shots", "deflections", "touches",
                          "screen_assists", "charges_drawn", "box_outs") if c in adv.columns]
        t = adv.groupby(["player_id", "team_id"])[tk].sum().reset_index()
        t["rim_dfg_pct"] = t.defended_at_rim_fgm / t.defended_at_rim_fga.replace(0, np.nan)
        out = out.merge(t, on=["player_id", "team_id"], how="left")
        for c in ("contested_shots", "deflections", "touches"):
            if c in out:
                out[f"{c}_p36"] = rate(out[c], out.mpg * out.gp, 36)
        lg_rim = adv.defended_at_rim_fgm.sum() / max(1, adv.defended_at_rim_fga.sum())
        out["rim_dfg_vs_lg"] = out.rim_dfg_pct - lg_rim
    except FileNotFoundError:
        pass

    names = table(season, "players")[["player_id", "first_name", "last_name", "position", "height_in"]]
    out = names.merge(out, on="player_id")
    out["name"] = out.first_name + " " + out.last_name
    out = out.drop(columns=["first_name", "last_name"]).sort_values("pts_pg", ascending=False)
    out.round(4).to_csv(out_path(season, "players.csv"), index=False)

    # five-man units
    reg = reg.dropna(subset=[f"p{i}" for i in range(1, 6)]).copy()   # a stint the feed left short of five
    reg["unit"] = reg[[f"p{i}" for i in range(1, 6)]].astype(int).astype(str).agg("-".join, axis=1)
    lu = reg.groupby(["team_id", "unit"]).agg(sec=("sec", "sum"), poss=("poss", "sum"), pf=("pts_for", "sum"),
                                              pa=("pts_against", "sum"), xf=("xp_for", "sum"),
                                              xa=("xp_against", "sum")).reset_index()
    lu = lu[lu.poss >= 40].copy()
    lu["min"] = lu.sec / 60
    lu["ortg"], lu["drtg"] = rate(lu.pf, lu.poss), rate(lu.pa, lu.poss)
    lu["net"], lu["xnet"] = lu.ortg - lu.drtg, rate(lu.xf - lu.xa, lu.poss)
    # last names, with the first name when two teammates share one (Jalen and Jaylin Williams), ordered by
    # each player's minutes for that team so the core of the lineup reads first
    mins = (out.set_index(["player_id", "team_id"]).mpg * out.set_index(["player_id", "team_id"]).gp).to_dict()
    first = dict(zip(names.player_id, names.first_name))
    last = dict(zip(names.player_id, names.last_name))

    def label(row):
        ids = sorted((int(p) for p in row.unit.split("-")), key=lambda p: -mins.get((p, row.team_id), 0))
        roster = out[out.team_id == row.team_id].player_id
        dup = {last.get(p) for p in roster if sum(last.get(q) == last.get(p) for q in roster) > 1}
        return ", ".join(f"{first.get(p, '')} {last.get(p, p)}" if last.get(p) in dup else str(last.get(p, p))
                         for p in ids)
    lu["players"] = [label(r) for r in lu.itertuples(index=False)]
    lu = lu.sort_values(["team_id", "poss"], ascending=[True, False])
    lu.round(3).to_csv(out_path(season, "lineups.csv"), index=False)
    return out, lu, stints


def checks(season, out, stints):
    tg = table(season, "team_games").merge(table(season, "games")[["game_id", "game_type"]], on="game_id")
    tg = tg[tg.game_type == "regular"]
    box_poss = ((tg.poss + tg.opp_poss) / 2).groupby(tg.game_id).mean()
    st_poss = stints[stints.game_type == "regular"].groupby("game_id").poss.sum() / 2
    d = (st_poss - box_poss).dropna()
    adv = table(season, "advanced")
    bdl_usg = adv.groupby(["player_id", "team_id"]).usage_percentage.mean()
    q = out.set_index(["player_id", "team_id"]).join(bdl_usg)
    q = q[q.gp >= 10]
    print(f"possessions per game, stints vs box estimate: mean diff {d.mean():+.2f}, |diff| p95 {d.abs().quantile(.95):.2f}"
          f" ({len(d)} games)")
    print(f"usage vs BDL's usage_percentage (10+ games, {len(q)} players): r {q.usage.corr(q.usage_percentage):.3f}, "
          f"mean ours {q.usage.mean():.3f} vs theirs {q.usage_percentage.mean():.3f}")


def main():
    season = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
    out, lu, stints = build(season)
    checks(season, out, stints)
    q = out[out.gp >= 15]
    cols = ["name", "team", "gp", "mpg", "pts_pg", "usage", "ts", "xpps", "shotmaking", "on_off", "xon_off"]
    print("\nTop scorers (15+ games):")
    print(q[cols].head(12).round(3).to_string(index=False))
    print("\nBest shot-making (300+ shots):")
    print(q[q.shots >= 300].sort_values("shotmaking", ascending=False)[cols].head(8).round(3).to_string(index=False))
    print("\nMost-used lineups:")
    print(lu.sort_values("poss", ascending=False)[["players", "min", "poss", "net", "xnet"]].head(8).round(1)
          .to_string(index=False))


if __name__ == "__main__":
    main()
