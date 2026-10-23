"""Tonight: the next day of games, a card for each and a preview page.

    tonight.json              the next two days with games (US Eastern dates, as the NBA dates them), one card each
    preview/<id>.json         the preview: the line, storylines, who's out and who has picked up their minutes,
                              both teams side by side this season and last, where each offense shoots against where
                              the other defense gives shots up, players to watch, and the teams' recent meetings

Built from the schedule, our own team and player numbers, the injury report and the consensus line from our
pre-game snapshots (the median across books). Every sentence is written here from those numbers; there are no model
probabilities yet (phase 3), and no raw odds go out, only the consensus.
"""
import datetime as dt
import glob
import gzip
import json
import os
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common import table, out_path, TABLES, PREV, CUR

ET = ZoneInfo("America/New_York")
RAW = os.path.join(os.path.dirname(TABLES), "raw")
NICK = dict(ATL="Hawks", BOS="Celtics", BKN="Nets", CHA="Hornets", CHI="Bulls", CLE="Cavaliers", DAL="Mavericks",
            DEN="Nuggets", DET="Pistons", GSW="Warriors", HOU="Rockets", IND="Pacers", LAC="Clippers", LAL="Lakers",
            MEM="Grizzlies", MIA="Heat", MIL="Bucks", MIN="Timberwolves", NOP="Pelicans", NYK="Knicks", OKC="Thunder",
            ORL="Magic", PHI="76ers", PHX="Suns", POR="Trail Blazers", SAC="Kings", SAS="Spurs", TOR="Raptors",
            UTA="Jazz", WAS="Wizards")
WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
OUTISH = ("Out", "Doubtful")
SMALL = 5            # games before a team's own numbers this season lead its preview


def nw(n):
    return WORDS[n] if 0 <= n < len(WORDS) else str(n)


def ordinal(n):
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def the(team):
    return f"the {NICK.get(team, team)}"


def poss(team):
    n = NICK.get(team, team)
    return f"the {n}'" if n.endswith("s") else f"the {n}'s"


def half(x):
    return None if x is None else round(2 * x) / 2


def cap(s):
    return s[:1].upper() + s[1:]


def d(s):
    return dt.date.fromisoformat(s)


def last_name(name):
    parts = name.split()
    return " ".join(parts[1:]) if len(parts) > 1 else name


# ------------------------------------------------------------------ inputs

def schedule(season):
    path = os.path.join(RAW, str(season), "games.json.gz")
    if not os.path.exists(path):
        return pd.DataFrame()
    with gzip.open(path, "rt", encoding="utf-8") as f:
        data = json.load(f)
    data = data["data"] if isinstance(data, dict) else data
    rows = [dict(game_id=g["id"], date=g["date"][:10], tip=g.get("datetime"), state=g.get("status_state"),
                 postseason=bool(g.get("postseason")), postponed=bool(g.get("postponed")),
                 home_id=g["home_team"]["id"], home=g["home_team"]["abbreviation"],
                 away_id=g["visitor_team"]["id"], away=g["visitor_team"]["abbreviation"]) for g in data]
    return pd.DataFrame(rows).sort_values(["date", "tip"]).reset_index(drop=True)


def implied(american):
    a = float(american)
    return 100 / (a + 100) if a > 0 else -a / (-a + 100)


def market(gid, date):
    """The consensus line from our latest snapshot of this game: median spread and total across books, and the
    home team's chance with the bookmakers' margin taken out of each book's moneylines (median across books)."""
    path = os.path.join(RAW, str(CUR), "pregame", date, f"{gid}.json.gz")
    if not os.path.exists(path):
        return None
    with gzip.open(path, "rt", encoding="utf-8") as f:
        snap = json.load(f)
    odds = snap.get("odds") or []

    def med(key):
        vals = []
        for o in odds:
            try:
                vals.append(float(o.get(key)))
            except (TypeError, ValueError):
                pass
        return float(np.median(vals)) if vals else None
    probs = []
    for o in odds:
        h, a = o.get("moneyline_home_odds"), o.get("moneyline_away_odds")
        if h and a:
            ph, pa = implied(h), implied(a)
            probs.append(ph / (ph + pa))
    if not odds:
        return None
    return {"spread_home": half(med("spread_home_value")), "total": half(med("total_value")),
            "p_home": float(np.median(probs)) if probs else None, "books": len({o.get("vendor") for o in odds}),
            "as_of": snap.get("taken_at")}


def records(games, team_id, before=None):
    """Regular-season W-L, home and away splits and the current streak, from finished games."""
    g = games[(games.game_type == "regular") & ((games.home_id == team_id) | (games.away_id == team_id))]
    if before:
        g = g[g.date < before]
    g = g.sort_values(["date", "tip_utc"])
    res = []
    for r in g.itertuples(index=False):
        home = r.home_id == team_id
        res.append((home, (r.home_score > r.away_score) == home))
    w = sum(x[1] for x in res)
    streak = 0
    for _, won in reversed(res):
        if streak == 0 or (streak > 0) == won:
            streak += 1 if won else -1
        else:
            break
    last10 = res[-10:]
    return {"w": w, "l": len(res) - w, "home": [sum(1 for h, x in res if h and x), sum(1 for h, x in res if h and not x)],
            "away": [sum(1 for h, x in res if not h and x), sum(1 for h, x in res if not h and not x)],
            "streak": streak, "l10": [sum(x for _, x in last10), len(last10) - sum(x for _, x in last10)]
            if len(res) >= 10 else None}


def rest(sch, team_id, gid):
    """Nights off before this game, games in four nights, and where it falls in a home stand or road trip."""
    tg = sch[((sch.home_id == team_id) | (sch.away_id == team_id)) & ~sch.postponed].reset_index(drop=True)
    i = int(tg.index[tg.game_id == gid][0])
    date = tg.date[i]
    home = tg.home_id[i] == team_id
    prev = tg.date[i - 1] if i > 0 else None
    nights = (d(date) - d(prev)).days - 1 if prev else None
    in4 = int(((tg.date >= (d(date) - dt.timedelta(days=3)).isoformat()) & (tg.date <= date)).sum())
    same = (tg.home_id == team_id) == home
    a = i
    while a > 0 and same[a - 1]:
        a -= 1
    b = i
    while b + 1 < len(tg) and same[b + 1]:
        b += 1
    first_home = home and not ((tg.home_id[:i] == team_id).any())
    return {"last": prev, "nights": nights, "b2b": nights == 0, "in4": in4, "home": bool(home), "stand_game": i - a + 1,
            "stand_len": b - a + 1, "opener": i == 0, "home_opener": bool(first_home)}


# ------------------------------------------------------------------ people

class People:
    """Who plays where this season and last, with season lines, for injuries, players to watch and old teams."""

    def __init__(self, cur_pg, prev_pg, cur_pl, prev_pl, bios):
        self.cur_pg, self.prev_pg = cur_pg, prev_pg
        self.cur_pl, self.prev_pl = cur_pl, prev_pl
        self.bio = bios
        last = cur_pg.sort_values("date").groupby("player_id").tail(1)
        self.team_now = dict(zip(last.player_id, last.team_id))
        mins = prev_pg.groupby(["player_id", "team_id"]).sec_on.sum().reset_index().sort_values("sec_on")
        self.team_prev = dict(zip(mins.player_id, mins.team_id))          # where he played most last season
        prev_last = prev_pg.sort_values("date").groupby("player_id").tail(1)
        self.team_prev_last = dict(zip(prev_last.player_id, prev_last.team_id))
        # one line per player last season (his main team) for comparisons
        pl = prev_pl.copy()
        pl["load"] = pl.gp * pl.mpg
        self.prev_line = {int(r.player_id): r for r in pl.sort_values("load").groupby("player_id").tail(1).itertuples()}
        tot = prev_pl.groupby("player_id").apply(lambda q: pd.Series({
            "gp": q.gp.sum(), "mpg": (q.mpg * q.gp).sum() / max(q.gp.sum(), 1),
            "pts_pg": (q.pts_pg * q.gp).sum() / max(q.gp.sum(), 1)}), include_groups=False)
        self.prev_tot = tot.to_dict("index")

    def name(self, pid):
        b = self.bio.get(int(pid))
        return f"{b['first_name']} {b['last_name']}" if b else str(pid)

    def cur_line(self, pid, team_id):
        q = self.cur_pl[(self.cur_pl.player_id == pid) & (self.cur_pl.team_id == team_id)]
        return q.iloc[0] if len(q) else None

    def importance(self, pid, team_id):
        """Minutes a game he'd normally play: this season for this team, else last season anywhere."""
        c = self.cur_line(pid, team_id)
        if c is not None and c.gp >= 2:
            return float(c.mpg)
        p = self.prev_tot.get(pid)
        return float(p["mpg"]) if p and p["gp"] >= 10 else (float(c.mpg) if c is not None else 0.0)

    def minutes_without(self, pid, team_id):
        """Whose minutes went up in the games he missed: this season if there's enough of both, else last season if
        he was on this team. Only teammates who are on the team now. Counts DNPs as zero."""
        roster = {p for p, t in self.team_now.items() if t == team_id and p != pid}
        for season, pg in ((CUR, self.cur_pg), (PREV, self.prev_pg)):
            tg = pg[pg.team_id == team_id]
            mine = tg[tg.player_id == pid]
            if not len(mine):
                continue
            since = mine.date.min() if season == PREV else tg.date.min()
            tg = tg[tg.date >= since]
            played = set(mine[mine.sec_on > 0].game_id)
            missed = set(tg.game_id) - played
            if len(missed) < 2 or len(played) < 3:
                continue
            rows = []
            for tm, q in tg[tg.player_id.isin(roster)].groupby("player_id"):
                a, b = q[q.game_id.isin(missed)], q[q.game_id.isin(played)]
                if len(a) < 2 or len(b) < 3:
                    continue
                delta = a.sec_on.mean() / 60 - b.sec_on.mean() / 60
                if delta >= 3:
                    rows.append({"id": int(tm), "name": self.name(tm), "with": round(b.sec_on.mean() / 60, 1),
                                 "without": round(a.sec_on.mean() / 60, 1)})
            rows.sort(key=lambda r: r["with"] - r["without"])
            return {"season": season, "missed": len(missed), "played": len(played), "who": rows[:3]}
        return None


def team_injuries(inj, abbr, team_id, P):
    out = []
    for r in inj:
        if r["team"] != abbr or r["status"] in ("Available", "Probable") or str(r.get("note", "")).startswith("G League"):
            continue
        if r["id"] is None:
            continue
        mpg = P.importance(r["id"], team_id)
        row = dict(r, mpg=round(mpg, 1))
        if r["status"] in OUTISH and mpg >= 20:
            row["without"] = P.minutes_without(r["id"], team_id)
        out.append(row)
    out.sort(key=lambda r: (r["status"] not in OUTISH, -r["mpg"]))
    return out


def watch(abbr, team_id, P, injured):
    """Up to three players to watch, each with the reason: the main scorer, the biggest change in role, a rookie
    getting minutes, or the hottest shooter once there are enough shots to say so."""
    cur = P.cur_pl[(P.cur_pl.team_id == team_id) & (P.cur_pl.gp >= 1) & ~P.cur_pl.player_id.isin(injured)]
    if not len(cur):
        return []
    picks, seen = [], set()

    def add(pid, why, kind):
        if pid not in seen and len(picks) < 3:
            seen.add(pid)
            picks.append({"id": int(pid), "name": P.name(pid), "why": why, "kind": kind})
    top = cur.sort_values("pts_pg", ascending=False).iloc[0]
    prev = P.prev_tot.get(int(top.player_id))
    gp = int(top.gp)
    after = f", after {prev['pts_pg']:.1f} a game last season" if prev and prev["gp"] >= 10 else ""
    if gp == 1:
        add(top.player_id, f"Scored {top.pts_pg:.0f} in the opener{after}.", "scorer")
    else:
        add(top.player_id, f"Leads the {NICK.get(abbr, abbr)} with {top.pts_pg:.1f} points a game over {nw(gp)} "
            f"games{after}.", "scorer")
    # role changes against last season
    best = None
    for r in cur[cur.gp >= 2].itertuples():
        p = P.prev_tot.get(int(r.player_id))
        prev_team = P.team_prev.get(int(r.player_id))
        if p and p["gp"] >= 10 and prev_team is not None and prev_team != team_id and r.mpg >= 20:
            score, why = r.mpg, (f"New here: {r.mpg:.0f} minutes a game so far after {p['mpg']:.0f} last season for "
                                 f"{the(P.abbr.get(prev_team, ''))}.")
        elif p and p["gp"] >= 10 and r.mpg - p["mpg"] >= 6:
            score, why = r.mpg - p["mpg"], f"Playing {r.mpg:.0f} minutes a game, up from {p['mpg']:.0f} last season."
        elif (not p or p["gp"] < 20) and r.mpg >= 24 and (P.bio.get(int(r.player_id)) or {}).get("draft_year") != CUR:
            n = int(p["gp"]) if p else 0
            score = r.mpg - 10
            why = (f"Back in a big role: {r.mpg:.0f} minutes a game after "
                   + ("not playing last season." if n == 0 else f"only {nw(n)} games last season."))
        elif p and p["gp"] >= 10 and p["mpg"] - r.mpg >= 8 and p["mpg"] >= 24:
            score, why = p["mpg"] - r.mpg - 2, f"Down to {r.mpg:.0f} minutes a game from {p['mpg']:.0f} last season."
        else:
            continue
        if best is None or score > best[0]:
            best = (score, r.player_id, why)
    if best:
        add(best[1], best[2], "role")
    for r in cur[cur.mpg >= 12].itertuples():
        b = P.bio.get(int(r.player_id)) or {}
        if b.get("draft_year") == CUR:
            pick = b.get("draft_number")
            add(r.player_id, f"Rookie{f', the No. {int(pick)} pick' if pick and pick == pick else ''}: "
                f"{r.mpg:.0f} minutes and {r.pts_pg:.1f} points a game so far.", "rookie")
    hot = cur[cur.shots >= 40].copy()
    if len(hot):
        hot["impact"] = hot.shotmaking * hot.shots / hot.gp
        h = hot.sort_values("impact").iloc[-1]
        if h.impact >= 2:
            add(h.player_id, f"Making more than his looks are worth: about {h.impact:.0f} points a game above what "
                f"the same shots usually return, over {int(h.shots)} shots.", "hot")
    if len(picks) < 3:
        for r in cur.sort_values("usage", ascending=False).itertuples():
            if r.mpg >= 20:
                add(r.player_id, f"Uses {100 * r.usage:.0f}% of the team's possessions when he plays, "
                    f"{r.pts_pg:.1f} points a game.", "usage")
    return picks


# ------------------------------------------------------------------ storylines

def meetings(games_by_season, a_id, h_id):
    out = []
    for season, g in games_by_season.items():
        q = g[((g.home_id == a_id) & (g.away_id == h_id)) | ((g.home_id == h_id) & (g.away_id == a_id))]
        for r in q.sort_values("date").itertuples(index=False):
            out.append({"season": season, "id": int(r.game_id), "date": r.date, "type": r.game_type, "home": r.home,
                        "away": r.away, "hs": int(r.home_score), "as": int(r.away_score), "ot": int(r.ot)})
    return out


def storylines(g, ra, rh, rec_a, rec_h, line, inj_a, inj_h, meet, P, lt):
    A, H = g["away"], g["home"]
    out = []

    def add(kind, text, priced=None):
        out.append({"kind": kind, "text": text})
    # schedule
    if rh["home_opener"] and not rh["opener"]:
        add("schedule", f"{cap(poss(H))} home opener.")
    if ra["opener"] and rh["opener"]:
        add("schedule", "Season opener for both teams.")
    elif ra["opener"] or rh["opener"]:
        t = A if ra["opener"] else H
        add("schedule", f"Season opener for {the(t)}.")
    if ra["b2b"] and rh["b2b"]:
        add("schedule", "Both teams played last night.")
    elif ra["b2b"] or rh["b2b"]:
        tired, fresh = (A, rh) if ra["b2b"] else (H, ra)
        other = H if tired == A else A
        rest_txt = "" if fresh["nights"] is None else f"; {the(other)} had {'a night' if fresh['nights'] == 1 else nw(fresh['nights']) + ' nights'} off"
        add("schedule", f"{cap(the(tired))} played last night{rest_txt}.")
    elif ra["nights"] is not None and rh["nights"] is not None and abs(ra["nights"] - rh["nights"]) >= 2:
        t1, r1, t2, r2 = (A, ra, H, rh) if ra["nights"] > rh["nights"] else (H, rh, A, ra)
        add("schedule", f"{cap(the(t1))} come in with {nw(r1['nights'])} nights off to {nw(r2['nights'])} for {the(t2)}.")
    for t, r in ((A, ra), (H, rh)):
        if r["in4"] >= 3 and not r["b2b"]:
            add("schedule", f"{cap(poss(t))} third game in four nights.")
    if ra["stand_len"] >= 3:
        add("schedule", f"Game {nw(ra['stand_game'])} of a {nw(ra['stand_len'])}-game road trip for {the(A)}.")
    if rh["stand_len"] >= 4 and rh["stand_game"] == 1:
        add("schedule", f"{cap(the(H))} start a {nw(rh['stand_len'])}-game home stand.")
    # the market
    if line and line.get("spread_home") is not None:
        s, total, ph = line["spread_home"], line.get("total"), line.get("p_home")
        tot = f", with a total of {total:g}" if total else ""
        if abs(s) < 0.75:
            add("market", f"The books see a coin flip{tot}.")
        else:
            fav, by = (H, -s) if s < 0 else (A, s)
            p = None if ph is None else (ph if fav == H else 1 - ph)
            fv = f", about a {100 * p:.0f}% favorite" if p else ""
            add("market", f"The books have {the(fav)} by {by:g}{fv}{tot}.")
    # who's out
    def listed(names):
        return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
    for t, inj in ((A, inj_a), (H, inj_h)):
        out_ = [r["name"] for r in inj if r["status"] == "Out" and r["mpg"] >= 20][:3]
        doubt = [r["name"] for r in inj if r["status"] == "Doubtful" and r["mpg"] >= 20][:2]
        if out_ and doubt:
            add("injury", f"{cap(the(t))} are without {listed(out_)}, and {listed(doubt)} {'is' if len(doubt) == 1 else 'are'} doubtful.")
        elif out_:
            add("injury", f"{cap(the(t))} are without {listed(out_)}.")
        elif doubt:
            add("injury", f"{cap(the(t))} will likely be without {listed(doubt)}.")
    # streaks and starts
    for t, rc in ((A, rec_a), (H, rec_h)):
        if abs(rc["streak"]) >= 3:
            add("form", f"{cap(the(t))} have {'won' if rc['streak'] > 0 else 'lost'} {nw(abs(rc['streak']))} straight.")
    if rec_a["w"] + rec_a["l"] >= 2 and rec_h["w"] + rec_h["l"] >= 2 and rec_a["l"] == 0 and rec_h["l"] == 0:
        add("form", "Both teams are still unbeaten.")
    elif rec_a["w"] + rec_a["l"] >= 2 and rec_h["w"] + rec_h["l"] >= 2 and rec_a["w"] == 0 and rec_h["w"] == 0:
        add("form", "Both teams are still looking for a first win.")
    # history
    last_po = [m for m in meet if m["season"] == PREV and m["type"] == "playoffs"]
    if last_po:
        wins = {}
        for m in last_po:
            wn = m["home"] if m["hs"] > m["as"] else m["away"]
            wins[wn] = wins.get(wn, 0) + 1
        (w1, n1), = sorted(wins.items(), key=lambda kv: -kv[1])[:1]
        n2 = len(last_po) - n1
        loser = A if w1 == H else H
        add("history", f"A playoff rematch: {the(w1)} beat {the(loser)} {n1}-{n2} in last season's playoffs.")
    reg = [m for m in meet if m["season"] == PREV and m["type"] == "regular"]
    if reg and not last_po:
        wins = sum(1 for m in reg if (m["home"] if m["hs"] > m["as"] else m["away"]) == H)
        if (wins == len(reg) or wins == 0) and len(reg) >= 2:
            w = H if wins else A
            add("history", f"{cap(the(w))} won {'both' if len(reg) == 2 else 'all ' + nw(len(reg))} meetings last season.")
    this = [m for m in meet if m["season"] == CUR]
    if this:
        m = this[-1]
        wn = m["home"] if m["hs"] > m["as"] else m["away"]
        add("history", f"They met on {dt.date.fromisoformat(m['date']):%B} {d(m['date']).day}: {the(wn)} won "
            f"{max(m['hs'], m['as'])}-{min(m['hs'], m['as'])}.")
    # old teams
    for t_id, opp_id, opp in ((g["away_id"], g["home_id"], H), (g["home_id"], g["away_id"], A)):
        for pid, now in P.team_now.items():
            if now != t_id:
                continue
            was = P.team_prev_last.get(pid)
            c = P.cur_line(pid, t_id)
            if was == opp_id and c is not None and c.mpg >= 12:
                add("former", f"{P.name(pid)} faces {the(opp)}, his team last season.")
    # strength against strength, from whichever season says more
    for off, dfn in ((A, H), (H, A)):
        for season in (CUR, PREV):
            t = lt.get(season)
            if t is None:
                continue
            o, f = t[t.abbr == off], t[t.abbr == dfn]
            if not len(o) or not len(f) or (season == CUR and min(o.gp.iloc[0], f.gp.iloc[0]) < 10):
                continue
            ork, drk = int(o.ortg_rk.iloc[0]), int(f.drtg_rk.iloc[0])
            when = "" if season == CUR else " last season"
            if ork <= 5 and drk <= 5:
                add("matchup", f"Strength on strength: {poss(off)} offense ranked {ordinal(ork)} and {poss(dfn)} "
                    f"defense {ordinal(drk)}{when}.")
            elif ork <= 5 and drk >= 26:
                add("matchup", f"{cap(poss(off))} offense ranked {ordinal(ork)}{when}; {poss(dfn)} defense "
                    f"{ordinal(drk)}.")
            break
    return out


# ------------------------------------------------------------------ the page

TEAM_COLS = ["gp", "ortg", "drtg", "net", "x_net", "pace", "efg", "tov", "orb", "ftr", "opp_efg", "opp_tov", "drb",
             "opp_ftr", "xpps", "opp_xpps", "shotmaking", "opp_shotmaking"]


def team_block(lt, zones, abbr):
    out = {}
    for season, t in lt.items():
        q = t[t.abbr == abbr]
        if not len(q):
            continue
        r = q.iloc[0]
        row = {c: r[c] for c in TEAM_COLS if c in q.columns}
        row.update({f"{c}_rk": int(r[f"{c}_rk"]) for c in TEAM_COLS if f"{c}_rk" in q.columns})
        row["zones_for"] = zones.get(season, {}).get(abbr, {}).get("for")
        row["zones_against"] = zones.get(season, {}).get(abbr, {}).get("against")
        out[str(season)] = row
    return out


def build(dump, lt, zones, inj, lg):
    """lt: {season: team table with ranks}; zones: {season: {abbr: {"for", "against"}}}; inj: injury rows;
    lg: {season: league averages}."""
    sch = schedule(CUR)
    if not len(sch):
        return
    today = dt.datetime.now(ET).date().isoformat()
    ahead = sch[(sch.date >= today) & ~sch.postponed]
    dates = sorted(ahead.date.unique())[:2]
    if not dates:
        return
    games = {s: table(s, "games") for s in (PREV, CUR) if os.path.exists(os.path.join(TABLES, str(s), "games.csv.gz"))}
    pgs = {s: table(s, "player_games") for s in games}
    pls = {s: pd.read_csv(out_path(s, "players.csv")) for s in games}
    bios = {}
    for s in games:
        for r in table(s, "players").to_dict("records"):
            bios[int(r["player_id"])] = r
    P = People(pgs[CUR], pgs[PREV], pls[CUR], pls[PREV], bios)
    teams_t = table(CUR, "teams")
    P.abbr = dict(zip(teams_t.team_id, teams_t.abbr))
    slates = []
    for date in dates:
        cards = []
        for g in ahead[ahead.date == date].to_dict("records"):
            gid, A, H = int(g["game_id"]), g["away"], g["home"]
            ra, rh = rest(sch, g["away_id"], gid), rest(sch, g["home_id"], gid)
            rec_a, rec_h = records(games[CUR], g["away_id"], date), records(games[CUR], g["home_id"], date)
            line = market(gid, date)
            inj_a, inj_h = team_injuries(inj, A, g["away_id"], P), team_injuries(inj, H, g["home_id"], P)
            meet = meetings(games, g["away_id"], g["home_id"])
            stories = storylines(g, ra, rh, rec_a, rec_h, line, inj_a, inj_h, meet, P, lt)
            out_ids = {r["id"] for r in inj_a + inj_h if r["status"] in OUTISH}
            w_a, w_h = watch(A, g["away_id"], P, out_ids), watch(H, g["home_id"], P, out_ids)
            lead = "cur" if min(lt[CUR].set_index("abbr").gp.get(A, 0), lt[CUR].set_index("abbr").gp.get(H, 0)) >= SMALL else "prev"
            dump(f"preview/{gid}.json", {
                "id": gid, "date": date, "tip": g["tip"], "away": A, "home": H, "season": CUR,
                "records": {"away": rec_a, "home": rec_h}, "rest": {"away": ra, "home": rh}, "line": line,
                "stories": stories, "injuries": {"away": inj_a, "home": inj_h}, "watch": {"away": w_a, "home": w_h},
                "teams": {"away": team_block(lt, zones, A), "home": team_block(lt, zones, H)},
                "league": {str(s): {"zones": lg[s]["zones"], "ortg": lg[s]["ortg"], "pace": lg[s]["pace"]} for s in lg},
                "lead": str(CUR if lead == "cur" else PREV), "meetings": meet[-6:],
            })
            order = {"market": 0, "injury": 1, "schedule": 2, "history": 3, "former": 4, "form": 5, "matchup": 6}
            top = sorted(stories, key=lambda s: order.get(s["kind"], 9))
            cards.append({"id": gid, "tip": g["tip"], "away": A, "home": H, "rec": [[rec_a["w"], rec_a["l"]],
                          [rec_h["w"], rec_h["l"]]], "line": line,
                          "stories": [s["text"] for s in top if s["kind"] != "market"][:2],
                          "out": {"away": [r["name"] for r in inj_a if r["status"] in OUTISH and r["mpg"] >= 15][:3],
                                  "home": [r["name"] for r in inj_h if r["status"] in OUTISH and r["mpg"] >= 15][:3]}})
        slates.append({"date": date, "games": sorted(cards, key=lambda c: c["tip"] or "")})
    dump("tonight.json", {"built_for": today, "slates": slates})
    print(f"tonight: {sum(len(s['games']) for s in slates)} games on {', '.join(dates)}")
