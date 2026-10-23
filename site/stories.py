"""The story of a finished game, written from the play-by-play and box score: who won and how (comebacks,
wire to wire, blowouts), the play that put the winner ahead for good, the biggest run, lead changes, the quarter
that swung it, and the night's best lines (triple-doubles, 40-point games, season highs). Plus the game's top
three performers by game score. No model calls; the same rules every night.
"""
import numpy as np

from tonight import NICK, nw, cap, poss

QWORD = {1: "first quarter", 2: "second quarter", 3: "third quarter", 4: "fourth quarter"}


def when(t):
    """'with 2:13 left in the fourth quarter' from seconds elapsed (OT periods are five minutes)."""
    if t < 2880:
        p = min(int(t // 720) + 1, 4)
        left = 720 - (t - (p - 1) * 720)
        name = QWORD[p]
    else:
        k = int((t - 2880) // 300)
        left = 300 - (t - 2880 - k * 300)
        name = "overtime" if k == 0 else f"{['second', 'third', 'fourth'][min(k - 1, 2)]} overtime"
    m, s = int(left // 60), int(left % 60)
    return f"with {m}:{s:02d} left in the {name}" if left >= 1 else f"at the end of the {name}"


def period_of(t):
    return min(int(t // 720) + 1, 4) if t < 2880 else 5 + int((t - 2880) // 300)


def pname(p):
    return QWORD[p] if p <= 4 else "overtime" if p == 5 else f"{['second', 'third', 'fourth'][min(p - 6, 2)]} overtime"


def half_word(t):
    p = period_of(t)
    return "in the first half" if p <= 2 else "in the fourth quarter" if p == 4 else "in the third quarter" if p == 3 \
        else "in overtime"


def game_score(r):
    return (r.pts + 0.4 * r.fgm - 0.7 * r.fga - 0.4 * (r.fta - r.ftm) + 0.7 * r.oreb + 0.3 * r.dreb + r.stl
            + 0.7 * r.ast + 0.7 * r.blk - 0.4 * r.pf - r.tov)


def shot_word(kind, value):
    k = (kind or "").lower()
    if value == 1:
        return "free throw"
    if value == 3:
        return "three"
    for w in ("dunk", "layup", "hook", "floater", "tip", "jumper", "jump shot", "fadeaway"):
        if w in k:
            return {"jump shot": "jumper", "tip": "tip-in"}.get(w, w)
    return "basket"


def game_story(g, sc, box, names, before):
    """g: games row; sc: scoring plays (t, team_id, value, p1, type, home_score, away_score) in order;
    box: this game's player lines; names: id -> name; before: (game_id, player_id) -> (season high so far,
    games so far)."""
    H, A = g.home, g.away
    hw = g.home_score > g.away_score
    W, L = (H, A) if hw else (A, H)
    w_id = g.home_id if hw else g.away_id
    ws, ls = (g.home_score, g.away_score) if hw else (g.away_score, g.home_score)
    nW, nL = NICK.get(W, W), NICK.get(L, L)
    ot = int(g.ot)
    sc = sc[sc.home_score.notna()]
    m = (sc.home_score - sc.away_score).to_numpy(dtype=float)
    t = sc.t.to_numpy(dtype=float)
    wm = m if hw else -m                                   # margin from the winner's side after each score
    out = []
    if not len(m):
        return [f"The {nW} beat the {nL} {ws}-{ls}{' in overtime' if ot else ''}."], []
    # how they won
    lead = f"The {nW} beat the {nL} {ws}-{ls}" + ("" if not ot else " in overtime" if ot == 1 else f" in {nw(ot)} overtimes")
    deficit = -wm.min() if wm.min() < 0 else 0
    big = wm.max()
    if deficit >= 10:
        i = int(np.argmin(wm))
        lead += f", coming back from {int(deficit)} down {half_word(t[i])}"
    elif wm.min() >= 0 and (wm > 0).all():
        lead += ", leading from the first basket to the last"
    elif big >= 25:
        lead += f", leading by as many as {int(big)}"
    out.append(lead + ".")
    # the play that put them ahead for good
    not_ahead = np.where(wm <= 0)[0]
    if len(not_ahead):
        j = int(not_ahead[-1]) + 1
        if j < len(sc):
            r = sc.iloc[j]
            if r.t >= 2160:
                who = names.get(int(r.p1)) if r.p1 == r.p1 and r.p1 is not None else None
                what = shot_word(r.type, int(r.value))
                tied = wm[j - 1] == 0
                if who:
                    out.append(f"{who}'s {what} put them ahead for good {when(r.t)}"
                               f"{', breaking a tie' if tied else ''}.")
                else:
                    out.append(f"They went ahead for good {when(r.t)}.")
    # a close finish without a late go-ahead line
    late = (t >= 2880 - 120) if not ot else (t >= 2880 + 300 * ot - 120)
    if late.any() and (np.abs(m[late]) <= 3).any() and len(out) == 1:
        out.append("It was a one-possession game in the final two minutes.")
    # the biggest run (unanswered points)
    best, cur_team, cur_pts, start = (0, None, 0, 0), None, 0, 0
    for k, r in enumerate(sc.itertuples(index=False)):
        if r.team_id == cur_team:
            cur_pts += int(r.value)
        else:
            cur_team, cur_pts, start = r.team_id, int(r.value), k
        if cur_pts > best[0]:
            best = (cur_pts, cur_team, start, k)
    if best[0] >= 10:
        run_team = H if best[1] == g.home_id else A
        p0, p1 = period_of(t[best[2]]), period_of(t[best[3]])
        span = (f"in the {pname(p0)}" if p0 == p1 else
                f"across the {pname(p0).split()[0]} and {pname(p1).split()[0]} quarters" if p1 <= 4 else
                f"from the {pname(p0)} into {pname(p1)}")
        out.append(f"The biggest run was {best[0]}-0 by the {NICK.get(run_team, run_team)} {span}.")
    # lead changes and ties
    signs = np.sign(m)
    nz = signs[signs != 0]
    changes = int((nz[1:] != nz[:-1]).sum()) if len(nz) > 1 else 0
    ties = int(((signs[1:] == 0) & (signs[:-1] != 0)).sum())
    if changes >= 10:
        out.append(f"The lead changed hands {changes} times, with {ties} ties.")
    # the quarter that swung it
    qs = []
    for i, q in enumerate(("q1", "q2", "q3", "q4")):
        h, a = getattr(g, f"home_{q}"), getattr(g, f"away_{q}")
        if h == h and a == a:
            qs.append((i + 1, int(h), int(a)))
    if qs:
        qn, qh, qa = max(qs, key=lambda x: abs(x[1] - x[2]))
        if abs(qh - qa) >= 12:
            tq = H if qh > qa else A
            out.append(f"The {NICK.get(tq, tq)} won the {QWORD[qn]} {max(qh, qa)}-{min(qh, qa)}.")
    # the best lines
    notes = []
    stars = []
    b = box.copy()
    b["gs"] = [game_score(r) for r in b.itertuples()]
    for r in b.sort_values("gs", ascending=False).itertuples():
        nm = names.get(int(r.player_id), str(r.player_id))
        tens = sum(v >= 10 for v in (r.pts, r.reb, r.ast, r.stl, r.blk))
        hi, n = before.get((int(g.game_id), int(r.player_id)), (None, 0))
        if tens >= 3:
            notes.append(f"{nm} had a triple-double: {int(r.pts)} points, {int(r.reb)} rebounds and {int(r.ast)} assists.")
        elif r.pts >= 40:
            notes.append(f"{nm} scored {int(r.pts)} on {int(r.fgm)}-of-{int(r.fga)} shooting.")
        elif r.pts >= 20 and r.reb >= 20:
            notes.append(f"{nm} had {int(r.pts)} points and {int(r.reb)} rebounds.")
        elif hi is not None and n >= 3 and r.pts >= 25 and r.pts > hi:
            notes.append(f"{nm}'s {int(r.pts)} points were his most this season.")
        if len(stars) < 3:
            stars.append({"id": int(r.player_id), "name": nm, "team": H if r.team_id == g.home_id else A,
                          "pts": int(r.pts), "reb": int(r.reb), "ast": int(r.ast), "stl": int(r.stl), "blk": int(r.blk),
                          "fg": f"{int(r.fgm)}-{int(r.fga)}", "fg3": f"{int(r.fg3m)}-{int(r.fg3a)}", "gs": round(r.gs, 1)})
    out += notes[:3]
    # the bench, when it decided things
    if "starter" in b.columns:
        bw = b[(b.team_id == w_id) & (b.starter == 0)].pts.sum()
        bl = b[(b.team_id != w_id) & (b.starter == 0)].pts.sum()
        if bw - bl >= 20:
            out.append(f"{cap(poss(W))} bench outscored {poss(L)} {int(bw)}-{int(bl)}.")
    return out, stars
