"""Team ratings: pace, offensive/defensive/net rating per 100 possessions, the four factors for and against, luck
checks, and shot quality from analysis/shot_quality.py.

    python analysis/teams.py 2025        # writes analysis/output/2025/teams.csv and prints the table

Possessions per game are the average of the two teams' box estimates (FGA - OREB + TOV + 0.44 FTA). Four factors:
effective FG% (threes count 1.5), turnovers per possession, offensive rebound rate (OREB / (OREB + opponent DREB)),
free throw rate (FTM / FGA).

Luck checks, the things that swing a rating without saying much about the team:
  opp_3p_vs_lg   opponents' three-point % minus league average. Defense has some say over how many threes and how
                 open, much less over whether they fall; this regresses hard.
  opp_ft_vs_lg   opponents' free-throw %: no defensive control at all.
  shotmaking     points per shot above shot-quality expectation (own, and opponents'). Some of it is skill, a lot of
                 it is noise over a few hundred shots.
  x_net          net rating with every field goal valued at its expected points instead of what happened (free
                 throws and turnovers as they happened): what the shot mix alone says about the team.
"""
import sys

import numpy as np
import pandas as pd

from common import table, out_path


def ratings(season):
    tg = table(season, "team_games")
    games = table(season, "games")
    tg = tg.merge(games[["game_id", "game_type"]], on="game_id")
    tg = tg[tg.game_type.isin(["regular", "ist"])]
    tg["poss_g"] = (tg.poss + tg.opp_poss) / 2
    xp = pd.read_csv(out_path(season, "shots_xp.csv.gz"))
    xp = xp[xp.heave == 0]
    by_team = xp.groupby(["game_id", "team_id"]).agg(fga=("made", "size"), pts=("made", lambda m: 0),
                                                     xpts=("xpts", "sum")).reset_index()
    pts = xp.assign(p=xp.made * xp.value).groupby(["game_id", "team_id"]).p.sum().rename("fg_pts").reset_index()
    by_team = by_team.drop(columns="pts").merge(pts, on=["game_id", "team_id"])
    tg = tg.merge(by_team.rename(columns={"fga": "sq_fga", "xpts": "fg_xpts"}), on=["game_id", "team_id"], how="left")
    opp = by_team.rename(columns={"team_id": "opp_id", "fga": "opp_sq_fga", "xpts": "opp_fg_xpts",
                                  "fg_pts": "opp_fg_pts"})
    tg = tg.merge(opp, on=["game_id", "opp_id"], how="left")

    s = tg.groupby(["team_id", "team"]).sum(numeric_only=True)
    s["gp"] = tg.groupby(["team_id", "team"]).size()
    lg = tg.sum(numeric_only=True)
    out = pd.DataFrame(index=s.index)
    out["gp"] = s.gp
    out["pace"] = s.poss_g / s.gp
    out["ortg"] = 100 * s.pts / s.poss_g
    out["drtg"] = 100 * s.opp_pts / s.poss_g
    out["net"] = out.ortg - out.drtg
    out["efg"] = (s.fgm + 0.5 * s.fg3m) / s.fga
    out["tov"] = s.tov / s.poss_g
    out["orb"] = s.oreb / (s.oreb + s.opp_dreb)
    out["ftr"] = s.ftm / s.fga
    out["opp_efg"] = (s.opp_fgm + 0.5 * s.opp_fg3m) / s.opp_fga
    out["opp_tov"] = s.opp_tov / s.poss_g
    out["drb"] = s.dreb / (s.dreb + s.opp_oreb)
    out["opp_ftr"] = s.opp_ftm / s.opp_fga
    lg3, lgft = lg.fg3m / lg.fg3a, lg.ftm / lg.fta
    out["opp_3p_vs_lg"] = s.opp_fg3m / s.opp_fg3a - lg3
    out["opp_ft_vs_lg"] = s.opp_ftm / s.opp_fta - lgft
    out["xpps"] = s.fg_xpts / s.sq_fga
    out["opp_xpps"] = s.opp_fg_xpts / s.opp_sq_fga
    out["shotmaking"] = (s.fg_pts - s.fg_xpts) / s.sq_fga
    out["opp_shotmaking"] = (s.opp_fg_pts - s.opp_fg_xpts) / s.opp_sq_fga
    # expected net: field goals at expected value, everything else as it happened
    x_pts = s.pts - s.fg_pts + s.fg_xpts
    x_opp = s.opp_pts - s.opp_fg_pts + s.opp_fg_xpts
    out["x_ortg"] = 100 * x_pts / s.poss_g
    out["x_drtg"] = 100 * x_opp / s.poss_g
    out["x_net"] = out.x_ortg - out.x_drtg
    out = out.reset_index().sort_values("net", ascending=False)
    out.round(4).to_csv(out_path(season, "teams.csv"), index=False)
    return out, tg


def main():
    season = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
    out, tg = ratings(season)
    cols = ["team", "gp", "pace", "ortg", "drtg", "net", "x_net", "xpps", "opp_xpps", "shotmaking", "opp_shotmaking",
            "opp_3p_vs_lg"]
    print(out[cols].round(3).to_string(index=False))
    # does the expected rating say anything the actual one doesn't? first half of the games vs second half
    tg = tg.sort_values("date")
    tg["half"] = tg.groupby("team_id").cumcount() < tg.groupby("team_id").game_id.transform("size") / 2
    halves = {}
    for h, q in tg.groupby("half"):
        s = q.groupby("team_id").sum(numeric_only=True)
        net = 100 * (s.pts - s.opp_pts) / s.poss_g
        xnet = 100 * ((s.pts - s.fg_pts + s.fg_xpts) - (s.opp_pts - s.opp_fg_pts + s.opp_fg_xpts)) / s.poss_g
        halves["first" if h else "second"] = pd.DataFrame({"net": net, "xnet": xnet})
    a, b = halves["first"], halves["second"]
    print(f"\nsplit-half check ({len(a)} teams): first-half net rating vs second-half net r = "
          f"{np.corrcoef(a.net, b.net)[0, 1]:.3f}; first-half expected net vs second-half net r = "
          f"{np.corrcoef(a.xnet, b.net)[0, 1]:.3f}; blend 50/50 r = {np.corrcoef((a.net + a.xnet) / 2, b.net)[0, 1]:.3f}")


if __name__ == "__main__":
    main()
