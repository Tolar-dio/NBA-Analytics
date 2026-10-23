"""Gather NBA news, podcasts and the NBA's own highlight videos into data/news/index.json for the News tab.

    python scripts/news.py            # standard library only; run hourly by .github/workflows/news.yml

Sources are in scripts/news_sources.json. Only headlines, short teasers, links, podcast audio links (what any
podcast app uses) and YouTube video ids (played through YouTube's own embed) are kept; full article text is never
stored or shown. Betting-pick articles are left out. Player names for tagging and the game list for matching
highlights come from the live site's own data files (SITE_DATA_URL), so this job needs no private data.

index.json:
  stories     the same news grouped across outlets, newest first, tagged with teams and players
  listen      latest podcast episodes
  watch       the NBA channel's latest videos (full-game highlights, nightly recaps, top plays), no Shorts
  highlights  {game id: YouTube id} of each game's official full-game highlights (kept in data/news/cache/)
"""
import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "data", "news")
UA = "Mozilla/5.0 (compatible; The Board news job; +https://github.com/Tolar-dio/NBA-Analytics)"
NOW = dt.datetime.now(dt.timezone.utc)
SITE = os.environ.get("SITE_DATA_URL", "https://tolar-dio.github.io/NBA-Analytics/data/")

TEAMS = {
    "ATL": ["Atlanta Hawks", "Hawks"], "BOS": ["Boston Celtics", "Celtics"], "BKN": ["Brooklyn Nets", "Nets"],
    "CHA": ["Charlotte Hornets", "Hornets"], "CHI": ["Chicago Bulls", "Bulls"],
    "CLE": ["Cleveland Cavaliers", "Cavaliers", "Cavs"], "DAL": ["Dallas Mavericks", "Mavericks", "Mavs"],
    "DEN": ["Denver Nuggets", "Nuggets"], "DET": ["Detroit Pistons", "Pistons"],
    "GSW": ["Golden State Warriors", "Warriors"], "HOU": ["Houston Rockets", "Rockets"], "IND": ["Indiana Pacers", "Pacers"],
    "LAC": ["LA Clippers", "Los Angeles Clippers", "Clippers"], "LAL": ["Los Angeles Lakers", "Lakers"],
    "MEM": ["Memphis Grizzlies", "Grizzlies"], "MIA": ["Miami Heat", "Heat"], "MIL": ["Milwaukee Bucks", "Bucks"],
    "MIN": ["Minnesota Timberwolves", "Timberwolves", "Wolves"], "NOP": ["New Orleans Pelicans", "Pelicans"],
    "NYK": ["New York Knicks", "Knicks"], "OKC": ["Oklahoma City Thunder", "Thunder"], "ORL": ["Orlando Magic", "Magic"],
    "PHI": ["Philadelphia 76ers", "76ers", "Sixers"], "PHX": ["Phoenix Suns", "Suns"],
    "POR": ["Portland Trail Blazers", "Trail Blazers", "Blazers"], "SAC": ["Sacramento Kings", "Kings"],
    "SAS": ["San Antonio Spurs", "Spurs"], "TOR": ["Toronto Raptors", "Raptors"], "UTA": ["Utah Jazz", "Jazz"],
    "WAS": ["Washington Wizards", "Wizards"],
}
NICK = {n: ab for ab, names in TEAMS.items() for n in names}
# case-sensitive on purpose: "Heat", "Magic", "Jazz", "Kings" are everyday words in lower case
TEAM_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, NICK), key=len, reverse=True)) + r")\b")
UPPER = {n.upper(): ab for n, ab in NICK.items()}
FAMILIES = {
    "trade": r"\b(trades?|traded|acquires?|acquired|deal sends)\b",
    "sign": r"\b(signs?|signed|signing|extension|re-signs?|contract|two-way|buyout)\b",
    "injury": r"\b(injur\w*|surgery|sprain\w*|strain\w*|fracture\w*|torn|tear|day-to-day|out for|out indefinitely|to miss|will miss|sidelined|leaves game|ruled out|questionable|doubtful|return\w*)\b",
    "waiver": r"\b(waiv\w*|releases?|released|claims?|claimed)\b",
    "discipline": r"\b(suspend\w*|fined|ejected)\b",
    "staff": r"\b(fires?|fired|hires?|hired|head coach|general manager|president of basketball)\b",
}
FEATURE_RE = re.compile(r"^(how|why|what|which|who|where|could|can|should|would|is|are|does|do|will|ranking|rankings|"
                        r"grading|grades|power rankings|takeaways|observations|three|four|five|six|seven|eight|nine|ten|"
                        r"\d+)\b|\?\s*$|\b(roundup|mailbag|rankings|podcast)\b", re.I)
BET_RE = re.compile(r"\b(odds|picks?|player props?|parlays?|best bets?|betting|sportsbook|sportsline|spread|"
                    r"over/under|bet|DFS|DraftKings|FanDuel|PrizePicks|Underdog|Perfect 5)\b|\$\d+ lineup", re.I)
NAME_RE = re.compile(r"\b([A-Z][\w'’.-]+ [A-Z][\w'’-]+)\b")
STOP = set("a an the to of for in on at by with from and or vs vs. as is are be after before over into out his "
           "their its nba".split())


# ------------------------------------------------------------------ helpers

def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def plain(s, n=260):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "…"


def fetch(url, tries=2):
    err = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(2)
    raise err


def iso(s):
    if not s:
        return None
    try:
        d = email.utils.parsedate_to_datetime(s.strip())
    except (TypeError, ValueError):
        try:
            d = dt.datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def age_days(iso_s):
    try:
        return (NOW - dt.datetime.fromisoformat(iso_s)).total_seconds() / 86400
    except (TypeError, ValueError):
        return 999


def local(tag):
    return tag.split("}")[-1]


def parse_feed(raw):
    """RSS 2.0 items or Atom entries as plain dicts (title, link, published, desc, author, audio, duration, image)."""
    root = ET.fromstring(raw)
    chan_img = next((el.get("href") for el in root.iter() if local(el.tag) == "image" and el.get("href")), None)
    entries = [el for el in root.iter() if local(el.tag) in ("item", "entry")]
    out = []
    for it in entries:
        d = {}
        for c in it:
            t = local(c.tag)
            if t == "title":
                d["title"] = plain(c.text, 300)
            elif t == "link":
                d["link"] = (c.get("href") if c.get("href") and c.get("rel", "alternate") == "alternate" else (c.text or "").strip()) \
                    or d.get("link")
            elif t in ("pubDate", "published") or (t == "updated" and "published" not in d):
                d["published"] = iso(c.text)
            elif t in ("description", "summary") and not d.get("desc"):
                d["desc"] = plain(c.text)
            elif t in ("creator", "author"):
                d["author"] = plain(c.text or (c.find("{http://www.w3.org/2005/Atom}name").text
                                               if c.find("{http://www.w3.org/2005/Atom}name") is not None else ""), 80)
            elif t == "source":
                d["via"] = plain(c.text, 60)
            elif t == "enclosure" and (c.get("type") or "").startswith("audio"):
                d["audio"] = c.get("url")
            elif t == "duration":
                d["duration"] = (c.text or "").strip()
            elif t == "image" and c.get("href"):
                d["image"] = c.get("href")
        d.setdefault("image", chan_img)
        if d.get("title"):
            out.append(d)
    return out


def secs(duration):
    if not duration:
        return None
    if duration.isdigit():
        return int(duration)
    tot = 0
    for p in duration.split(":"):
        if p.isdigit():
            tot = tot * 60 + int(p)
    return tot or None


class Tagger:
    """Teams and players an item mentions (full player names only; last names alone are too ambiguous)."""

    def __init__(self, players):
        self.people = {}
        for p in players:
            self.people.setdefault(norm(p["name"]), {"id": p["player_id"], "name": p["name"], "team": p.get("team")})
        names = sorted((n for n in self.people if " " in n), key=len, reverse=True)
        self.re = re.compile(r"\b(" + "|".join(map(re.escape, names)) + r")\b") if names else None

    def tag(self, text):
        teams = sorted({NICK[m] for m in TEAM_RE.findall(text or "")})
        players = [self.people[m] for m in dict.fromkeys(self.re.findall(norm(text)))] if self.re else []
        return teams, players


def family(title):
    return next((k for k, rx in FAMILIES.items() if re.search(rx, title or "", re.I)), None)


def words(title):
    return {w for w in norm(title).split() if w not in STOP and len(w) > 2}


def proper_names(title):
    return {norm(m) for m in NAME_RE.findall(title or "") if m not in NICK and m.split()[-1] not in NICK}


def same_story(a, b):
    """Same event: near-identical headlines, a shared player (or unlisted name) in the same kind of news, or the
    same teams in the same kind of transaction within a day."""
    try:
        gap = abs((dt.datetime.fromisoformat(a["published"]) - dt.datetime.fromisoformat(b["published"])).total_seconds()) / 3600
    except (TypeError, ValueError):
        gap = 99
    if gap > 36:
        return False
    wa, wb = words(a["title"]), words(b["title"])
    jac = len(wa & wb) / max(1, len(wa | wb))
    if jac >= 0.45:
        return True
    pa, pb = {p["id"] for p in a["players"]}, {p["id"] for p in b["players"]}
    if (pa & pb or proper_names(a["title"]) & proper_names(b["title"])) and \
            ((a["family"] and a["family"] == b["family"]) or jac >= 0.25):
        return True
    ta, tb = set(a["teams"]), set(b["teams"])
    return bool(a["family"] and a["family"] == b["family"] and a["family"] != "injury" and ta & tb
                and (ta == tb or jac >= 0.15) and gap <= 24)


def sid(x):
    return "s" + hashlib.sha1((x.get("link") or x["title"]).encode()).hexdigest()[:10]


def youtube(cid, cache):
    """Latest uploads from the channel feed; the Data API (YOUTUBE_API_KEY, optional) or the last good copy when
    the feed fails."""
    try:
        root = ET.fromstring(fetch(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}", tries=1))
        ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
        vids = []
        for e in root.findall("a:entry", ns):
            link = e.find("a:link", ns)
            vids.append({"id": e.find("yt:videoId", ns).text, "title": plain(e.find("a:title", ns).text, 200),
                         "published": iso(e.find("a:published", ns).text),
                         "short": "/shorts/" in (link.get("href", "") if link is not None else "")})
        cache[cid] = vids
        return vids, "feed"
    except Exception:  # noqa: BLE001
        pass
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if key:
        try:
            q = urllib.parse.urlencode({"part": "snippet", "playlistId": "UU" + cid[2:], "maxResults": 25, "key": key})
            d = json.loads(fetch("https://www.googleapis.com/youtube/v3/playlistItems?" + q, tries=1))
            vids = [{"id": x["snippet"]["resourceId"]["videoId"], "title": plain(x["snippet"]["title"], 200),
                     "published": iso(x["snippet"]["publishedAt"]),
                     "short": "#short" in (x["snippet"]["title"] + x["snippet"].get("description", "")).lower()}
                    for x in d.get("items", [])]
            cache[cid] = vids
            return vids, "api"
        except Exception:  # noqa: BLE001
            pass
    return cache.get(cid, []), "cache"


HL_RE = re.compile(r"^(.+?) (?:at|vs\.?) (.+?) \| FULL GAME HIGHLIGHTS \| (\w+ \d{1,2}, \d{4})", re.I)


# ------------------------------------------------------------------ main

def gather():
    cfg = json.load(open(os.path.join(HERE, "news_sources.json")))
    log = []
    meta = json.loads(fetch(SITE + "meta.json"))
    players, games = [], []
    for s in meta.get("seasons", []):
        try:
            players += json.loads(fetch(SITE + f"players.{s['season']}.json"))["players"]
            g = json.loads(fetch(SITE + f"games.{s['season']}.json"))
            games += [dict(zip(g["cols"], r)) for r in g["games"]]
        except Exception as e:  # noqa: BLE001
            log.append(f"site data {s['season']} failed: {e!r}")
    tagger = Tagger(players)

    items = []
    for src in cfg["news"]:
        try:
            got = parse_feed(fetch(src["url"]))[:50]
            kept = 0
            for it in got:
                if BET_RE.search(it["title"]) or "/betting/" in (it.get("link") or ""):
                    continue
                teams, players_ = tagger.tag(f'{it["title"]} {it.get("desc", "")}')
                items.append({"source": src["name"], "via": it.get("via") if it.get("via") != src["name"] else None,
                              "title": it["title"], "desc": it.get("desc"), "link": it.get("link"),
                              "published": it.get("published"), "paywalled": src.get("paywalled", False),
                              "teams": teams, "players": players_, "family": family(it["title"])})
                kept += 1
            log.append(f'{src["name"]}: {kept} of {len(got)}')
        except Exception as e:  # noqa: BLE001
            log.append(f'{src["name"]} failed: {e!r}')
    items = [x for x in items if x.get("published") and age_days(x["published"]) <= 5 and (x["teams"] or x["players"])]
    items.sort(key=lambda x: x["published"])

    def is_news(x):   # a transaction, injury, signing or the like; analysis and features stay single items
        return bool(x["family"]) and not FEATURE_RE.search(x["title"]) and len(x["teams"]) <= 3
    clusters = [[x] for x in items if not is_news(x)]
    news_clusters = []
    for x in (y for y in items if is_news(y)):
        for c in news_clusters:
            if any(same_story(x, y) for y in c):
                c.append(x)
                break
        else:
            news_clusters.append([x])
    stories = []
    for c in news_clusters + clusters:
        lead = next((y for y in c if not y["paywalled"]), c[0])
        kind = "news" if is_news(lead) else "read"
        stories.append({
            "id": sid(c[0]), "title": lead["title"], "desc": lead.get("desc"), "kind": kind, "family": lead["family"],
            "published": min(y["published"] for y in c), "latest": max(y["published"] for y in c),
            "teams": sorted({t for y in c for t in y["teams"]}),
            "players": list({p["id"]: p for y in c for p in y["players"]}.values()),
            "items": [{"source": y["source"], "via": y["via"], "title": y["title"], "link": y["link"],
                       "published": y["published"], "paywalled": y["paywalled"]} for y in c]})
    stories.sort(key=lambda s: s["latest"], reverse=True)

    listen = []
    for src in cfg["podcasts"]:
        try:
            for it in parse_feed(fetch(src["url"]))[:3]:
                if not it.get("audio") or not it.get("published") or age_days(it["published"]) > 10:
                    continue
                teams, players_ = tagger.tag(f'{it["title"]} {it.get("desc", "")}')
                listen.append({"show": src["name"], "title": it["title"], "desc": plain(it.get("desc"), 220),
                               "audio": it["audio"], "duration": secs(it.get("duration")), "published": it["published"],
                               "image": it.get("image"), "apple": f'https://podcasts.apple.com/podcast/id{src["apple"]}',
                               "teams": teams, "players": players_})
            log.append(f'{src["name"]} ok')
        except Exception as e:  # noqa: BLE001
            log.append(f'{src["name"]} failed: {e!r}')
    listen.sort(key=lambda x: x["published"], reverse=True)

    cache_dir = os.path.join(OUT, "cache")
    os.makedirs(cache_dir, exist_ok=True)
    cpath, hpath = os.path.join(cache_dir, "youtube.json"), os.path.join(cache_dir, "highlights.json")
    cache = json.load(open(cpath)) if os.path.exists(cpath) else {}
    highlights = json.load(open(hpath)) if os.path.exists(hpath) else {}
    by_game = {(g["date"], g["away"], g["home"]): g["id"] for g in games}
    watch = []
    for ch in cfg["youtube"]:
        vids, how = youtube(ch["channel"], cache)
        log.append(f'YouTube {ch["name"]}: {how} ({len(vids)})')
        for v in vids:
            if v.get("short") or not v.get("published"):
                continue
            m = HL_RE.match(v["title"])
            game = None
            if m:
                a, h = UPPER.get(m.group(1).strip().upper()), UPPER.get(m.group(2).strip().upper())
                try:
                    day = dt.datetime.strptime(m.group(3), "%B %d, %Y").date().isoformat()
                except ValueError:
                    day = None
                game = by_game.get((day, a, h))
                if game:
                    highlights[str(game)] = v["id"]
            if age_days(v["published"]) > 7:
                continue
            teams, players_ = tagger.tag(v["title"])
            watch.append({"id": v["id"], "channel": ch["name"], "title": v["title"], "published": v["published"],
                          "game": game, "teams": teams, "players": players_})
    watch.sort(key=lambda x: x["published"], reverse=True)
    with open(cpath, "w") as f:
        json.dump(cache, f, separators=(",", ":"))
    with open(hpath, "w") as f:
        json.dump(highlights, f, separators=(",", ":"), sort_keys=True)
    return {"updated_utc": NOW.isoformat(timespec="seconds"), "stories": stories[:60], "listen": listen[:30],
            "watch": watch[:30], "highlights": highlights}, log


def main():
    out, log = gather()
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "index.json")
    old = json.load(open(path)) if os.path.exists(path) else None
    body = {k: v for k, v in out.items() if k != "updated_utc"}
    if old and {k: v for k, v in old.items() if k != "updated_utc"} == body:
        print("No change.")
    else:
        with open(path, "w") as f:
            json.dump(out, f, separators=(",", ":"))
    print("\n".join(log))
    print({k: len(v) for k, v in out.items() if isinstance(v, (list, dict))})
    for s in out["stories"][:12]:
        print(f'  {len(s["items"])}x [{s["kind"]}] {s["title"][:70]} | {s["teams"]} | '
              f'{[p["name"] for p in s["players"]][:3]} | {[i["source"] for i in s["items"]]}')
    if not out["stories"]:
        sys.exit("no stories: every news feed failed?")


if __name__ == "__main__":
    main()
