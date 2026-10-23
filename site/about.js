/* About The Board: what it is, how the numbers work, a glossary, data credits, privacy and responsible gambling. */
"use strict";

function renderAbout(view, section) {
  const S_ = {
    about: ["About The Board", `
      <p class="lede">The Board explains the NBA with the numbers behind it, for every fan of every team. We measure teams per possession, value every shot by how often that kind of shot goes in, rebuild who was on the floor for every play, and say plainly how much a number can be trusted.</p>
      <p>We're independent: not affiliated with the NBA, its teams or any sportsbook. Pick your team with the button at the top and we'll highlight it everywhere; follow players from their pages. Both are saved in your browser only.</p>
      <p>Everything updates every morning after the night's games.</p>`],
    methods: ["How the numbers work", `
      <h2>Possessions and ratings</h2>
      <p>A possession ends when a team scores, misses and the other team rebounds, turns it over, or finishes a trip to the line. We count them from the box score (field-goal attempts, minus offensive rebounds, plus turnovers, plus 0.44 of free-throw attempts) and average the two teams. Offensive and defensive ratings are points scored and allowed per 100 possessions; net rating is the difference.</p>
      <h2>Shot quality</h2>
      <p>For every field-goal attempt we estimate how often it goes in, from where it was taken, what kind of shot it was (a dunk, a floater, a pull-up three and so on), and how the play started: off a steal, a defensive rebound, an inbound after a make, a putback. We trained it on every shot of 2025-26 and this season, always predicting each game's shots from other games. It's calibrated: shots we call 40% looks go in about 40% of the time, in every area of the floor. It doesn't know who's shooting, on purpose: that's what lets us say who makes more than his looks are worth.</p>
      <p>Shot-making is a player's points per shot minus what his shots usually produce. Great shooters beat it year after year; over a few hundred shots, a lot of it is luck.</p>
      <h2>What the shots say</h2>
      <p>To judge a team or a game on its shots, we value each trip down the floor by its first shot, plus, if that misses, the team's usual rate of getting a second chance off an offensive rebound, worth what second chances usually produce. Counting every shot instead would credit a team twice for one trip when it misses and rebounds. Free throws and turnovers count as they happened. In a full season, a team's net rating on its shots predicted its second-half results almost as well as its actual net rating, and a mix of the two did best.</p>
      <p>"Shots said" on a game is how often each team wins if the game were replayed on those trips, with every shot a fresh roll of the dice at its own odds.</p>
      <h2>Who was on the floor</h2>
      <p>The play-by-play records substitutions but not who's on the floor, so we rebuild it: the starters, every sub, and at the start of each quarter whoever acts before being subbed. Our minutes match the official box within a minute for 99.97% of player-games last season. That's what lineups and on/off come from.</p>
      <h2>Small samples</h2>
      <p>Early in a season, and for any lineup or bench player, the numbers swing a lot. We flag it where it matters, and hold back numbers that don't have enough behind them yet.</p>`],
    glossary: ["Glossary", `<dl>
      <dt>Net rating</dt><dd>Points per 100 possessions scored minus allowed. +5 is a very good team; +10 is a great one.</dd>
      <dt>Pace</dt><dd>Possessions per game.</dd>
      <dt>Effective FG% (eFG%)</dt><dd>Field-goal percentage with threes counted as 1.5 makes, since they're worth 50% more.</dd>
      <dt>True shooting (TS%)</dt><dd>Points per shooting chance, counting free throws: points divided by 2 × (FGA + 0.44 × FTA).</dd>
      <dt>Turnover rate (TOV%)</dt><dd>Turnovers per possession.</dd>
      <dt>Offensive rebound rate (OREB%)</dt><dd>The share of a team's own misses it gets back.</dd>
      <dt>Free throw rate</dt><dd>Made free throws per field-goal attempt.</dd>
      <dt>Usage</dt><dd>The share of his team's shots, free throws and turnovers a player uses while he's on the floor. 20% is average for a rotation player; stars sit above 30%.</dd>
      <dt>Expected points per shot</dt><dd>What a shot is usually worth, given where and how it was taken.</dd>
      <dt>Shot-making</dt><dd>Points per shot above (or below) what those shots are usually worth.</dd>
      <dt>On/off</dt><dd>The team's net rating with a player on the floor minus with him off.</dd>
      <dt>Four factors</dt><dd>Shooting (eFG%), turnovers, offensive rebounding and free throws: the four ways a possession is won or lost.</dd>
      <dt>Corner three</dt><dd>A three from the short stretch along the baseline, 22 feet from the rim instead of 23.75. The best shot in basketball outside the paint.</dd>
      </dl>`],
    data: ["Data and credits", `
      <p>Games, box scores, play-by-play with shot locations, lineups, player tracking and injury reports come from <a href="https://www.balldontlie.io">BALLDONTLIE</a>. Shot quality, ratings, on/off, lineups and everything labelled "from shots" are our own.</p>
      <p>We don't use NBA.com's or ESPN's data, because their terms don't allow it for a site like this, and we don't rehost video or photos.</p>`],
    privacy: ["Privacy", `
      <p>No accounts, no ads, no tracking. Your team, the players you follow, your season and your light or dark setting are saved in your own browser (local storage) and never leave it. Clear your browser's site data to remove them.</p>
      <p>The site loads its fonts from Google Fonts, which sees your IP address like any web request.</p>`],
    gambling: ["Responsible gambling", `
      <p>Our numbers are estimates for information and entertainment, not betting advice. If you bet, do it only where it's legal and you're of age, set a budget before you start, and never chase losses.</p>
      <p>If gambling has stopped being fun, call or text 1-800-GAMBLER, any time.</p>`],
  };
  const key = S_[section] ? section : "about";
  const nav = Object.entries(S_).map(([k, [t]]) => (k === key ? `<b>${t}</b>` : `<a href="#about${k === "about" ? "" : "/" + k}">${t}</a>`)).join("");
  view.innerHTML = `<section class="zone about"><h1>${S_[key][0]}</h1><nav class="subnav" aria-label="About">${nav}</nav>${S_[key][1]}</section>`;
}
