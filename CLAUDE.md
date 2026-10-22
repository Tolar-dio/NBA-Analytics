# Notes for Claude

Tolar's NBA analytics project, The Board: the basketball version of Ice Sheet (Tolar-dio/NHL-Analytics, site https://tolar-dio.github.io/NHL-Analytics/). Ice Sheet's CLAUDE.md and README are the template for architecture, model-testing discipline, the live record, product voice and the rules below. Read them before big changes. Never write to the NHL repo.

## Repos

- Tolar-dio/NBA-Analytics (this one, public): models, site, docs, and the frozen pre-game numbers the site showed. No raw paid data, no raw odds, no wager tracking.
- Tolar-dio/nba-private (private): the BALLDONTLIE pull (`scripts/bdl.py`, `scripts/fetch.py`, workflows `pull.yml` nightly and `snapshot.yml` pre-game), raw data under `bdl/raw/`, table builder and checks (`scripts/tables.py`, `scripts/validate.py`, `bdl/checks/`). Secret there: `BDL_API_KEY`. This repo's nightly will check out nba-private's raw data with a read-only token and build the tables in the runner, never committing them, the way Ice Sheet reads All Three Zones.
- Claude can push to both but can't run workflows or read Actions logs (the session proxy blocks the Actions API). Results come back as committed files; Tolar runs workflows by hand.

## Data sources (checked Oct 22, 2026)

Primary: BALLDONTLIE, GOAT tier (Tolar subscribed Oct 22, 2026; 600 requests a minute, 5 on the 48-hour trial). Terms allow commercial use, display next to our own projections, storage and archiving, no attribution required; forbidden: a feed that substitutes for their API, sharing the key, implying endorsement. They say they aren't the original producer and third-party rights are the user's responsibility. Their play fields mirror ESPN's feed one for one, so the play-by-play is probably ESPN-derived (unverified). Credit them on About anyway.
- Seasons use BDL's label: 2025 = 2025-26 (their docs say so for advanced stats).
- Play-by-play (`/v1/plays?game_id=`), lineups (starters and bench, once a game begins) and odds exist from 2025-26 on. Plays carry type, text, score, clock, team, `coordinate_x/y` on shots, wallclock and `participants` (player ids); no players-on-court field, so five-man stints get rebuilt from substitutions plus starters.
- `/v1/box_scores?date=` returns every game of a day with player lines (min as a string). Advanced stats v2 (`/nba/v2/stats/advanced`, period 0 = full game) carry possessions, ratings, four factors, usage, and hustle/tracking/matchup numbers (contested shots, defended at the rim, touches, speed, distance, matchup minutes) for full games only.
- Game odds (`/v2/odds`): DraftKings, FanDuel, Caesars, BetMGM, BetRivers, bet365 and more, updated live. Opening game odds and opening player props (`/nba/v2/odds/opening`, `/nba/v2/odds/player_props/opening`) are historical for the last completed season and this one. Current player props (`/v2/odds/player_props?game_id=`) are live only: BDL keeps no history, so the pull's `--snapshot` saves them before tip-off or they're gone. Prop types include points, rebounds, assists, threes, points_rebounds_assists, points_rebounds, points_assists, blocks, steals, double_double, as over/under and milestone (alt line) markets.
- Injuries (`/v1/player_injuries`): current list only (status, return date, description). The pull saves a copy each run; that's our history.

What the first pull showed (Oct 22, 2026: 2025-26 opening week, 53 games, plus 2026-27's first 14):
- The key is on the 48-hour trial's speed: 211 calls took 35 minutes with 35 rate-limit waits (about 6 a minute). A full-season backfill is ~4,400 calls: about 11 minutes at the paid 600 a minute, 15 hours on the trial.
- 2025-26 lists 1,322 games: 1,230 regular (NBA Cup games included), 1 tagged `ist` (the Cup final), 6 play-in, 85 playoffs.
- Game lines: `/v2/odds` for a finished game holds the last in-game number (moneylines like -100000), useless for grading. 2025-26 opening game lines are one book (BetMGM) stamped exactly at tip-off, every game covered: in effect a line at tip, usable as the closing benchmark for the team side. 2026-27 "opening" lines are from August (schedule release), too stale to grade against. From here on, closing lines come from our own snapshots.
- Opening props: 2025-26 has 6 books (BetMGM, Fanatics, BetRivers, DraftKings, FanDuel, Caesars), ~590 lines a game, every one stamped exactly 3 hours before tip: in effect a T-3h snapshot, not true openers. 2026-27 has 9 books, opened 9 to 85 hours before tip, ~3,200 lines a game including first-quarter markets.
- Box minutes are whole minutes in 2025-26 and mm:ss in 2026-27. Our stint minutes match the box within a minute for 100% (2025-26) and 99.4% (2026-27) of player-games.
- Play-by-play is ESPN-shaped: shots carry integer x/y with the hoop at (25, 1); non-shots carry a sentinel (-214748340). Some plays arrive out of order (sort by clock, then feed order); a sub is often logged a beat after a play in the same second by the player coming in; missed end-of-period heaves aren't attempts in the box. Misses don't always say "three point": geometry decides (past 22.5 ft, or 21.5+ ft to the side), fit on 5,552 makes with no exceptions.
- Validation (`scripts/validate.py` in nba-private): every box total equals the final; play-by-play team points equal the final in all but 2 fresh 2026-27 games (LAL-GSW 130 vs 127, PHX at POR 82 vs 83; days refetch until 30 hours after tip, so watch whether they correct); player FGA mismatches 9 of 1,197 and 1 of 322, 3PA 7 and 4, points 4 and 0 (a free throw or basket credited to a teammate).

Ruled out by their own terms (read Oct 22, 2026), whether or not they answer:
- NBA.com (cdn.nba.com, stats.nba.com). Terms of use section 9 "NBA Statistics" (updated July 13, 2026): news reporting or private non-commercial use only; not in connection with any gambling activity, including legal gambling; not in a product presenting a live or archived play-by-play account; not in a site featuring a database of full, regularly updated NBA stats without the league's consent. Also cdn.nba.com returned Akamai 403 to the sandbox for every User-Agent, and stats.nba.com hung with an honest one (it wants browser headers; sending them would be spoofing).
- ESPN APIs (site.api.espn.com, sports.core.api.espn.com). They answer and are rich (play-by-play with coordinates, DraftKings props with history), but the Disney Terms of Use (May 24, 2024), which cover ESPN, forbid accessing or extracting the products with "a robot, spider, script, or other automated means" to compile a data set or database. Not used here. (The same clause covers Ice Sheet's ESPN layer; that's Tolar's call, flagged to him Oct 22, 2026.)
- Basketball Reference / Sports Reference: bots capped at 20 requests a minute, no downloads because their data is licensed from third parties. Not used.
- Headlines: outlets' public RSS feeds (published for syndication) are fine, headlines and teasers only, as on Ice Sheet.

Later, if needed: The Odds API (display on a site allowed, including commercial; storage and derived values allowed; no redistributing raw files, so raw odds stay private). $30/month for 20k credits; historical event odds cost 10 x markets x regions; props history from May 2023. Only worth it if BDL's opening props plus our own snapshots aren't enough for the market comparison.

## Rules carried over from Ice Sheet

- Every model change is tested walk-forward (each night predicted only from earlier games) on last season, then checked on this season, and adopted only if it holds in both. Record what failed here as well as what worked. Check calibration by role (starters vs bench, minutes bands).
- Freeze every published number at tip-off, grade it the next morning, show it on the Track record page, including against sportsbook lines. Note: BDL's history is opening lines, which are softer than closing lines; beating the open is a lower bar than beating the close, so the live record (our own pre-tip snapshots) is the real test.
- Product: for every NBA fan, no default team, visitor picks a team and follows players (localStorage), times in the visitor's zone, About page (methods, glossary, data credits, AI, responsible gambling, privacy). Voice: "we" to "you", plain, explains terms, no build internals.
- Sleepers chosen on role, process and matchup, never "he's due", each with reasons and our probability, graded publicly.
- AI writing (recaps, previews, news takes) with the Claude API, model claude-sonnet-5-5, facts from our data only, no invented quotes or feelings, every AI piece labelled. No em dashes in house style.
- No scraping sites whose terms forbid it, no spoofed headers, no rehosted video (link official clips; embed only the NBA's own YouTube uploads), headlines and teasers only from news sources, credit every data source, betting copy informational with the 1-800-GAMBLER line.

## Plan (Oct 22, 2026)

0. Source check: first manual run of the pull (a week of 2025-26 plus this season so far, plus tonight's snapshot). Confirm plays carry substitutions and coordinates, box scores reconcile with plays, odds `updated_at` vs tip-off (are past games' lines closing or in-game?), prop coverage.
1. Pipeline and tables in nba-private: games, plays, shots, stints (five-man units from subs), player-games, team-games with possessions; validate every game (play-by-play points per player = box, team totals = final, stint minutes within a minute of the box). Backfill 2025-26. Add the nightly and pre-game schedules.
2. Possessions, four factors, luck checks, expected points per shot (baseline: league average by zone and shot type), team ratings, player tables. Ship v0 of the site: League, Teams, Players, Games.
3. Minutes model first, then usage redistribution when a player sits, then stat distributions (not Poisson), then spreads and totals against the market. Walk-forward on 2025-26, checked on 2026-27.
4. Site: Tonight, Games, League, Teams, Players, Track record, then Pulse and News.
5. Live layer, story layer, sleepers, AI writing.

## Status

- Oct 22, 2026: BDL pull written and tested offline against a mock API, then run for real (2025-26 Oct 21-27 plus 2026-27 so far, no errors). Tables (`scripts/tables.py`: games, players, player_games, team_games, plays, shots, stints, advanced) and validation built on that data; results above. Tables aren't committed (they'd bloat git nightly); build them from raw with `python scripts/tables.py` in nba-private. Schedules added: nightly pull at 10:23 UTC, pre-game snapshots hourly 15:47-21:47 UTC and every 30 minutes 22:17-03:47 UTC (private repo, so these use Actions minutes: roughly 700 a month).
- Next: full 2025-26 backfill once the key is on the paid tier, then phase 2.
