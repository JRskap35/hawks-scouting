"""
Baseball Reference register scraper.

The register covers the minors, the independent leagues, college, and summer leagues. Its
robots.txt allows /register/ with a 3 second crawl delay, which the shared HTTP client honors.

For one league season it reads:
  1. the league page, to find that season           /register/league.cgi?code=PION&class=Ind
  2. the season page, to find every team             /register/league.cgi?id=<season id>
  3. each team page: hitting, pitching, roster bios  /register/team.cgi?id=<team season id>
  4. each player's own page, once a month: bio, high school, colleges, and every season he
     played anywhere (college, summer, independent, affiliated), with fielding by position
                                                     /register/player.fcgi?id=<player id>

Tables are read by header text and by links, not by CSS classes, so small site redesigns
do not break it. Sports Reference wraps some tables in HTML comments, so comments are
unwrapped before parsing.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from . import db
from .http import PoliteSession
from .presto import innings_to_outs, split_name, to_int

log = logging.getLogger(__name__)

BASE = "https://www.baseball-reference.com"
SOURCE_NAME = "Baseball Reference"
PLAYER_REFRESH_DAYS = 30          # a player's own page changes rarely; re-read it monthly


@dataclass
class LeagueSpec:
    name: str                     # our league name, e.g. "Pioneer League"
    code: str                     # Baseball Reference code, e.g. "PION"
    bref_class: str = "Ind"       # register class: Ind, Smr, ...
    org: str = "independent"
    level: str = "mlb_partner"

    def league_url(self) -> str:
        return f"{BASE}/register/league.cgi?code={self.code}&class={self.bref_class}"


PIONEER = LeagueSpec("Pioneer League", "PION")
# Ready for when we add them; same page layout on Baseball Reference.
FRONTIER = LeagueSpec("Frontier League", "FRON", level="mlb_partner")
AMERICAN_ASSOCIATION = LeagueSpec("American Association", "AMAS", level="mlb_partner")
ATLANTIC = LeagueSpec("Atlantic League", "ATLA", level="mlb_partner")


# ---------------------------------------------------------------------------
# Header aliases (Baseball Reference column labels -> our columns)
# ---------------------------------------------------------------------------

BAT = {"G": "g", "PA": "pa", "AB": "ab", "R": "r", "H": "h", "2B": "b2", "3B": "b3", "HR": "hr", "RBI": "rbi",
       "SB": "sb", "CS": "cs", "BB": "bb", "SO": "so", "HBP": "hbp", "SH": "sh", "SF": "sf", "IBB": "ibb",
       "GDP": "gdp", "GIDP": "gdp"}
PIT = {"W": "w", "L": "l", "G": "g", "GS": "gs", "CG": "cg", "SHO": "sho", "SV": "sv", "IP": "outs",
       "H": "h", "R": "r", "ER": "er", "HR": "hr", "BB": "bb", "IBB": "ibb", "SO": "so", "HBP": "hbp",
       "BK": "bk", "WP": "wp", "BF": "bf"}
FLD = {"G": "g", "GS": "gs", "Inn": "outs", "PO": "po", "A": "a", "E": "e", "DP": "dp",
       "PB": "pb", "SB": "sb_against", "CS": "cs_by"}

# Register level codes -> (our comp_level, team org)
LEVELS = {
    "MLB": ("mlb", "affiliated"), "AAA": ("aaa", "affiliated"), "AA": ("aa", "affiliated"),
    "A+": ("high_a", "affiliated"), "A": ("single_a", "affiliated"), "A-": ("single_a", "affiliated"),
    "Rk": ("complex", "affiliated"), "FRk": ("complex", "affiliated"), "ROK": ("complex", "affiliated"),
    "Ind": ("independent", "independent"),
    "Smr": ("summer_collegiate", "college"),      # amateur summer ball counts as amateur, never as a pro team
    "NCAA": ("ncaa", "college"), "JUCO": ("juco", "college"), "NAIA": ("naia", "college"),
}

POSITIONS = {
    "pitcher": "P", "catcher": "C", "first baseman": "1B", "second baseman": "2B", "third baseman": "3B",
    "shortstop": "SS", "leftfielder": "LF", "centerfielder": "CF", "rightfielder": "RF", "outfielder": "OF",
    "designated hitter": "DH", "infielder": "INF", "utility": "UT", "pinch hitter": "PH", "pinch runner": "PR",
}


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def soup_of(html: str) -> BeautifulSoup:
    return BeautifulSoup(html.replace("<!--", "").replace("-->", ""), "lxml")


def bref_id(href: str) -> Optional[str]:
    q = parse_qs(urlparse(href).query)
    return (q.get("id") or [None])[0]


def clean_player_name(text: str) -> str:
    return re.sub(r"[*#+†]+$", "", text.strip()).strip()


def headers_of(table) -> list[str]:
    rows = table.select("thead tr")
    if not rows:
        return []
    return [c.get_text(" ", strip=True) for c in rows[-1].find_all(["th", "td"])]


def body_rows(table):
    for tr in table.select("tbody tr"):
        cls = tr.get("class") or []
        if "thead" in cls or "spacer" in cls:
            continue
        cells = tr.find_all(["th", "td"])
        if cells:
            yield tr, cells


def read_stats(cells, headers, aliases) -> dict:
    out = {}
    for i, h in enumerate(headers):
        col = aliases.get(h)
        if not col or i >= len(cells) or col in out:
            continue
        text = cells[i].get_text(" ", strip=True)
        val = innings_to_outs(text) if col == "outs" else to_int(text)
        if val is not None and text != "":
            out[col] = val
    return out


def team_name_from_title(soup: BeautifulSoup) -> Optional[str]:
    """'2026 Long Beach Coast Statistics | Baseball-Reference.com' -> 'Long Beach Coast'."""
    t = soup.title.get_text(strip=True) if soup.title else ""
    m = re.match(r"^\d{4}\s+(.+?)\s+(?:Statistics|Roster|Stats)\b", t)
    if m:
        return m.group(1).strip()
    h1 = soup.find("h1")
    if h1:
        m = re.match(r"^\d{4}\s+(.+?)(?:\s+Statistics)?$", h1.get_text(" ", strip=True))
        if m:
            return m.group(1).strip()
    return None


def parse_birth_date(text: str, csk: Optional[str] = None) -> Optional[date]:
    if csk and re.fullmatch(r"\d{8}", csk):
        try:
            return date(int(csk[:4]), int(csk[4:6]), int(csk[6:]))
        except ValueError:
            pass
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def parse_height(text: str) -> Optional[int]:
    m = re.match(r"^\s*(\d)-(\d{1,2})", text or "")
    return int(m.group(1)) * 12 + int(m.group(2)) if m else None


def split_place(text: str) -> tuple[Optional[str], Optional[str]]:
    """'Bell, CA us' -> ('Bell', 'CA')."""
    t = re.sub(r"\s+[a-z]{2}$", "", (text or "").strip())       # drop the trailing country code
    if "," in t:
        city, state = [p.strip() for p in t.split(",", 1)]
        return city or None, state or None
    return (t or None), None


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def season_links(html: str) -> dict[str, str]:
    """League page -> {'2026': season url, ...}."""
    s = soup_of(html)
    out = {}
    for a in s.find_all("a", href=True):
        if "league.cgi?id=" in a["href"]:
            year = a.get_text(strip=True)
            if re.fullmatch(r"\d{4}", year):
                out.setdefault(year, urljoin(BASE, a["href"]))
    return out


def team_links(html: str) -> dict[str, str]:
    """Season page -> {team season url: link text}."""
    s = soup_of(html)
    out = {}
    for a in s.find_all("a", href=True):
        if "team.cgi?id=" in a["href"]:
            out.setdefault(urljoin(BASE, a["href"]).split("#")[0], a.get_text(" ", strip=True))
    return out


@dataclass
class TeamRow:
    bref_id: str
    url: str
    name: str
    stats: dict


@dataclass
class TeamPage:
    name: Optional[str]
    batting: list[TeamRow] = field(default_factory=list)
    pitching: list[TeamRow] = field(default_factory=list)
    roster: dict = field(default_factory=dict)          # bref player id -> bio fields


def parse_team_page(html: str) -> TeamPage:
    s = soup_of(html)
    page = TeamPage(team_name_from_title(s))
    for table in s.find_all("table"):
        tid = (table.get("id") or "").lower()
        headers = headers_of(table)
        if not headers:
            continue
        kind = ("batting" if "batting" in tid else "pitching" if "pitching" in tid else
                "roster" if "roster" in tid else None)
        if kind is None:
            # fall back to the headers when a table id changes
            if "PA" in headers and "AB" in headers:
                kind = "batting"
            elif "IP" in headers and "ERA" in headers:
                kind = "pitching"
            elif "DoB" in headers or ("B" in headers and "T" in headers and "Wt" in headers):
                kind = "roster"
            else:
                continue
        for tr, cells in body_rows(table):
            a = tr.find("a", href=lambda h: h and "player.fcgi" in h)
            if not a:
                continue                                     # totals and blank rows
            pid = bref_id(a["href"])
            url = urljoin(BASE, a["href"])
            name = clean_player_name(a.get_text(" ", strip=True))
            if kind == "roster":
                vals = {headers[i]: cells[i] for i in range(min(len(headers), len(cells)))}
                txt = lambda k: vals[k].get_text(" ", strip=True) if k in vals else ""   # noqa: E731
                bio = {
                    "name": name, "url": url,
                    "bats": (txt("B")[:1] or None), "throws": (txt("T")[:1] or None),
                    "height_in": parse_height(txt("Ht")),
                    "weight_lb": to_int(re.sub(r"[^\d]", "", txt("Wt"))) if txt("Wt") else None,
                    "birth_date": parse_birth_date(txt("DoB"), vals["DoB"].get("csk") if "DoB" in vals else None),
                }
                city, state = split_place(txt("Birthplace"))
                bio["hometown_city"], bio["hometown_state"] = city, state
                page.roster[pid] = {k: v for k, v in bio.items() if v not in (None, "")}
            else:
                stats = read_stats(cells, headers, BAT if kind == "batting" else PIT)
                if stats:
                    getattr(page, kind).append(TeamRow(pid, url, name, stats))
    return page


@dataclass
class CareerRow:
    group: str                    # 'h', 'p', 'f'
    season: int
    team_name: str
    team_bref_id: Optional[str]
    league: str                   # league code as printed, e.g. 'PION', 'BigW'
    level: str                    # register level code, e.g. 'Ind', 'NCAA', 'Smr', 'AA'
    position: Optional[str]
    stats: dict


@dataclass
class PlayerPage:
    name: Optional[str] = None
    bio: dict = field(default_factory=dict)
    career: list[CareerRow] = field(default_factory=list)


def parse_player_page(html: str) -> PlayerPage:
    s = soup_of(html)
    page = PlayerPage()
    meta = s.find(id="meta")
    if meta:
        h1 = meta.find("h1")
        page.name = h1.get_text(" ", strip=True) if h1 else None
        text = " ".join(meta.get_text(" ", strip=True).split())
        bio = {}
        m = re.search(r"Positions?:\s*(.+?)(?:\s+Bats:|\s+Throws:|$)", text)
        if m:
            first = re.split(r",| and ", m.group(1))[0].strip().lower()
            bio["position_text"] = m.group(1).strip()
            bio["primary_position"] = POSITIONS.get(first)
        m = re.search(r"Bats:\s*(Right|Left|Both)", text)
        if m:
            bio["bats"] = {"Right": "R", "Left": "L", "Both": "S"}[m.group(1)]
        m = re.search(r"Throws:\s*(Right|Left)", text)
        if m:
            bio["throws"] = m.group(1)[0]
        m = re.search(r"(\d)-(\d{1,2})\s*,\s*(\d{2,3})\s*lb", text)
        if m:
            bio["height_in"] = int(m.group(1)) * 12 + int(m.group(2))
            bio["weight_lb"] = int(m.group(3))
        birth = meta.find(attrs={"data-birth": True})
        if birth:
            bio["birth_date"] = parse_birth_date(birth["data-birth"])
        m = re.search(r"Born:\s*.+?\d{4}\s+in\s+(.+?)(?:\s+(?:High School|Schools?|School|Draft|Full Name|View|More)\b|$)", text)
        if m:
            bio["hometown_city"], bio["hometown_state"] = split_place(m.group(1))
        m = re.search(r"High School:\s*(.+?)(?:\s+(?:Schools?|School|Draft|Full Name|View|More)\b:?|$)", text)
        if m:
            bio["high_school"] = m.group(1).strip()
        m = re.search(r"Schools?:\s*(.+?)(?:\s+(?:Draft|Full Name|View|More)\b|$)", text)
        if m:
            bio["schools"] = m.group(1).strip()
        page.bio = {k: v for k, v in bio.items() if v not in (None, "")}

    for table in s.find_all("table"):
        tid = (table.get("id") or "").lower()
        group = "h" if "batting" in tid else "p" if "pitching" in tid else "f" if "fielding" in tid else None
        if group is None or not tid.startswith("standard"):
            continue
        headers = headers_of(table)
        aliases = {"h": BAT, "p": PIT, "f": FLD}[group]
        idx = {h: i for i, h in enumerate(headers)}
        for tr, cells in body_rows(table):
            def cell(name):
                i = idx.get(name)
                return cells[i] if i is not None and i < len(cells) else None
            year_c, tm_c = cell("Year"), cell("Tm")
            if year_c is None or tm_c is None:
                continue
            year = to_int(re.sub(r"[^\d]", "", year_c.get_text(strip=True))[:4] or "")
            team_a = tm_c.find("a", href=lambda h: h and "team.cgi" in h)
            if not year or not team_a:
                continue                                    # multi team summary rows and career totals
            lg_c, lev_c, pos_c = cell("Lg"), cell("Lev"), cell("Pos")
            stats = read_stats(cells, headers, aliases)
            if not stats:
                continue
            page.career.append(CareerRow(
                group=group, season=year, team_name=team_a.get_text(" ", strip=True),
                team_bref_id=bref_id(team_a["href"]),
                league=lg_c.get_text(" ", strip=True) if lg_c else "",
                level=lev_c.get_text(" ", strip=True) if lev_c else "",
                position=pos_c.get_text(" ", strip=True) if pos_c else None,
                stats=stats,
            ))
    return page


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _pitcher_position(primary: Optional[str], throws: Optional[str]) -> Optional[str]:
    if primary == "P":
        return "LHP" if throws == "L" else "RHP" if throws == "R" else "P"
    return primary


def _player_needs_fetch(conn, source_id: int, bref_pid: str, force: bool) -> bool:
    if force:
        return True
    row = conn.execute("SELECT fetched_at FROM player_external_ids WHERE source_id = %s AND external_id = %s",
                       (source_id, bref_pid)).fetchone()
    if not row or row["fetched_at"] is None:
        return True
    return row["fetched_at"] < datetime.now(timezone.utc) - timedelta(days=PLAYER_REFRESH_DAYS)


def load_league_season(conn, http: PoliteSession, spec: LeagueSpec, season: int, tally: dict,
                       players: bool = True, force_players: bool = False, max_players: int | None = None) -> dict:
    source_id = db.get_or_create_source(conn, SOURCE_NAME, BASE, priority=1, rate_limit_sec=3.5)
    league_id = db.get_or_create_league(conn, spec.name, spec.org, spec.level, spec.code, spec.league_url())
    db.mark_league_complete(conn, league_id)       # every team page is read, so every player is loaded
    conn.commit()

    seasons = season_links(http.get_text(spec.league_url()))
    if str(season) not in seasons:
        raise RuntimeError(f"Baseball Reference has no {season} season for {spec.name}. Seasons listed: {sorted(seasons)[-5:]}")
    teams = team_links(http.get_text(seasons[str(season)]))
    summary = {"teams": len(teams), "hitters": 0, "pitchers": 0, "players": 0,
               "player_pages": 0, "player_pages_skipped": 0, "career_rows": 0}

    team_by_bref: dict[str, int] = {}
    league_players: dict[str, int] = {}             # bref player id -> our player id
    for url, link_text in teams.items():
        try:
            page = parse_team_page(http.get_text(url))
        except Exception as e:
            tally["errors"].append(f"team page {url}: {e!r}")
            continue
        name = page.name or link_text
        team_id = db.get_or_create_team(conn, name, spec.org, url)
        db.upsert_team_season(conn, team_id, season, league_id)
        team_by_bref[bref_id(url)] = team_id

        def ensure_player(row_pid: str, row_url: str, row_name: str) -> int:
            bio = page.roster.get(row_pid, {})
            first, last = split_name(bio.get("name") or row_name)
            pid = db.upsert_player(conn, source_id, row_pid, row_url, first, last,
                                   **{k: v for k, v in bio.items() if k not in ("name", "url")})
            league_players[row_pid] = pid
            db.add_eligibility(conn, pid, "independent" if spec.org == "independent" else "released_affiliated",
                               source_id, url)
            return pid

        for r in page.batting:
            pid = ensure_player(r.bref_id, r.url, r.name)
            db.upsert_batting(conn, pid, season, team_id, r.stats, source_id)
            summary["hitters"] += 1
        for r in page.pitching:
            pid = ensure_player(r.bref_id, r.url, r.name)
            db.upsert_pitching(conn, pid, season, team_id, r.stats, source_id)
            summary["pitchers"] += 1
        tally["rows"] += len(page.batting) + len(page.pitching)
        conn.commit()

    summary["players"] = len(league_players)
    if not players:
        return summary

    for n, (bref_pid, pid) in enumerate(league_players.items()):
        if max_players is not None and summary["player_pages"] >= max_players:
            break
        if not _player_needs_fetch(conn, source_id, bref_pid, force_players):
            summary["player_pages_skipped"] += 1
            continue
        url = f"{BASE}/register/player.fcgi?id={bref_pid}"
        try:
            pp = parse_player_page(http.get_text(url))
        except Exception as e:
            tally["errors"].append(f"player page {bref_pid}: {e!r}")
            continue
        summary["player_pages"] += 1
        summary["career_rows"] += load_player_page(conn, pp, pid, source_id, team_by_bref)
        conn.execute("UPDATE player_external_ids SET fetched_at = now() WHERE source_id = %s AND external_id = %s",
                     (source_id, bref_pid))
        conn.commit()
        if n and n % 50 == 0:
            log.info("%s: %d of %d player pages", spec.name, n, len(league_players))
    return summary


def load_player_page(conn, pp: PlayerPage, pid: int, source_id: int, team_by_bref: dict[str, int]) -> int:
    """Bio plus every season on the player's page. Returns rows written."""
    bio = dict(pp.bio)
    primary = _pitcher_position(bio.pop("primary_position", None), bio.get("throws"))
    bio.pop("position_text", None)
    bio.pop("schools", None)
    fields = {k: v for k, v in bio.items() if k in ("bats", "throws", "height_in", "weight_lb", "birth_date",
                                                     "hometown_city", "hometown_state", "high_school")}
    if primary:
        fields["primary_position"] = primary
    if fields:
        sets = ", ".join(f"{k} = COALESCE(%s, {k})" for k in fields)
        conn.execute(f"UPDATE players SET {sets}, updated_at = now() WHERE id = %s", (*fields.values(), pid))

    written = 0
    last_college = None                                 # (season, team_id) of his final college season
    league_cache: dict[tuple, int] = {}
    for row in pp.career:
        level, org = LEVELS.get(row.level, (None, None))
        if level is None:
            continue                                    # winter and foreign leagues are left out
        team_id = team_by_bref.get(row.team_bref_id)
        if team_id is None:
            team_id = db.get_or_create_team(conn, row.team_name, org)
            key = (row.league or row.level, level)
            if key not in league_cache:
                league_cache[key] = db.get_or_create_league(conn, row.league or row.level, org if org != "college" else "college", level, row.league)
            db.upsert_team_season(conn, team_id, row.season, league_cache[key])
        if row.group == "h":
            db.upsert_batting(conn, pid, row.season, team_id, row.stats, source_id)
        elif row.group == "p":
            db.upsert_pitching(conn, pid, row.season, team_id, row.stats, source_id)
        else:
            db.upsert_fielding(conn, pid, row.season, team_id, row.position or "ALL", row.stats, source_id)
        written += 1
        if level in ("ncaa", "juco", "naia") and (last_college is None or row.season >= last_college[0]):
            last_college = (row.season, team_id)
    if last_college:
        # His final college season stands in for the graduation year.
        conn.execute("UPDATE players SET grad_year = %s, college_team_id = %s WHERE id = %s",
                     (last_college[0], last_college[1], pid))
    return written


# ---------------------------------------------------------------------------
# Live check: one page of each kind, no database
# ---------------------------------------------------------------------------

def check(http: PoliteSession, spec: LeagueSpec = PIONEER, season: int = 2026) -> str:
    lines = []
    seasons = season_links(http.get_text(spec.league_url()))
    lines.append(f"League page: seasons {sorted(seasons)[-5:]}")
    if str(season) not in seasons:
        return "\n".join(lines + [f"FAIL: no {season} season"])
    teams = team_links(http.get_text(seasons[str(season)]))
    lines.append(f"{season} season page: {len(teams)} teams: {', '.join(list(teams.values())[:12])}")
    url = next(iter(teams))
    page = parse_team_page(http.get_text(url))
    lines.append(f"Team page {url}: name '{page.name}', {len(page.batting)} hitters, {len(page.pitching)} pitchers, {len(page.roster)} roster bios")
    for r in page.batting[:2]:
        lines.append(f"  hit  {r.name:<22} {r.bref_id:<14} {r.stats}")
    for r in page.pitching[:2]:
        lines.append(f"  pit  {r.name:<22} {r.bref_id:<14} {r.stats}")
    for pid, bio in list(page.roster.items())[:2]:
        lines.append(f"  bio  {pid:<14} {bio}")
    sample = (page.batting or page.pitching)[0]
    pp = parse_player_page(http.get_text(sample.url))
    lines.append(f"Player page {sample.url}: name '{pp.name}'")
    lines.append(f"  bio {pp.bio}")
    for row in pp.career[:12]:
        lines.append(f"  {row.group} {row.season} {row.level:<5} {row.league:<6} {row.team_name:<28} {row.position or '':<4} {dict(list(row.stats.items())[:8])}")
    groups = {g: sum(1 for r in pp.career if r.group == g) for g in "hpf"}
    ok = page.name and page.batting and page.pitching and page.roster and pp.career
    lines.append(f"Career rows: {groups}")
    lines.append("PASS: every page kind read." if ok else "CHECK: something above came back empty.")
    return "\n".join(lines)
