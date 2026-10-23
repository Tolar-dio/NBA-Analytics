# The Board

**Site:** https://tolar-dio.github.io/NBA-Analytics/ (rebuilt every morning after the night's games)

NBA analytics for every fan, the basketball sibling of [Ice Sheet](https://tolar-dio.github.io/NHL-Analytics/). Teams measured per possession, every shot valued by how often that kind of shot goes in, who was on the floor rebuilt for every play, and plain words on how much each number can be trusted.

## What's on it

- **Tonight** (the front page): every game today with the betting line, rest, who's out and storylines, and a preview of each: both teams side by side, where each offense shoots against where the other defense gives shots up, whose minutes go up when a regular sits, players to watch and recent meetings.
- **Pulse**: last night's best games, who's hot and cold judged against the shots they're getting, fast and slow starts and what's behind them, new faces, changed roles, rookies, streaks, and teams whose results are running ahead of or behind their shots.
- **League**: every team's offense and defense per 100 possessions, with a switch to what their shots say (shot-making luck taken out), the four factors, and which teams' results are running ahead of or behind their shots.
- **Teams**: ratings and ranks, the four factors for and against, where shots come from against the league, players with usage and on/off, who plays when (minute by minute), the five-man lineups each team trusts, and every result with how often the shots would have won it.
- **Players**: search and leaderboards for scoring, shooting against expectation, on/off and rim defense. Player pages have how he plays (percentiles among his position, in plain words), every shot drawn the way a coach would (O for a make, X for a miss), how he scores by zone against the league, on/off, rim protection and his game log.
- **Games**: every game with the story of how it was won, the top three performers, quarter scores, a score-margin chart against what the shots were worth, both teams' shots, the box score and the NBA's official highlights. Today's games update live, with a scores strip on every page.
- **News**: headlines from The Athletic, CBS Sports, Yahoo Sports and SB Nation grouped by story, the injury report, the NBA's own videos and the best basketball podcasts, playable in the page.

No default team: pick yours with the button at the top and it's highlighted everywhere. Your team, followed players, season and theme stay in your browser.

## How it's built

The data comes from [BALLDONTLIE](https://www.balldontlie.io) and is pulled nightly into a private repository (it's licensed, so the raw files stay there). This repository holds the models, the site and its build:

- `analysis/shot_quality.py`: expected points per shot (where, what kind of shot, how the play started), and per trip down the floor.
- `analysis/teams.py`, `analysis/players.py`: team ratings, four factors and luck checks; usage, on/off and lineups from rebuilt five-man stints.
- `site/build.py` writes the site's JSON, with `tonight.py` (Tonight and previews), `pulse.py`, `stories.py` (game stories) and `profiles.py` (how he plays, who plays when) writing every sentence from our own numbers; `site/index.html`, `app.js`, `tonight.js`, `pulse.js`, `news.js`, `live.js`, `court.js`, `about.js` and `style.css` are a static page that reads it.
- `.github/workflows/site.yml` builds everything and deploys to GitHub Pages. It needs the `PRIVATE_DATA_TOKEN` secret (read-only access to the private data) and, for live scores, the `LIVE_URL` variable.
- `scripts/news.py` and `.github/workflows/news.yml` gather the news hourly into `data/news/`, which the site reads directly.
- `worker/live.js` is the live-score relay, a Cloudflare Worker that keeps the data key out of the browser.

Methods, tests and what didn't work are in [CLAUDE.md](CLAUDE.md).

Our numbers are for information and entertainment, not betting advice. Gambling problem? Call 1-800-GAMBLER.
