"""
Pioneer Baseball League scraper.

Pulls, for one season:
  1. Player stats (hitting, pitching, fielding) from the league's PrestoSports player lists,
     every view the page links to, every page.
  2. Team rosters, for full names and bio fields (B/T, height, weight, hometown, college).
  3. The transaction report, matched to players and turned into signing status changes.

The league is the baseline for the whole tool, so this is the first scraper. Other
PrestoSports leagues can reuse it by passing a different LeagueConfig.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date

from bs4 import BeautifulSoup

from . import db, presto
from .http import PoliteSession
from .transactions import is_affiliated_club, parse_report, status_after

log = logging.getLogger(__name__)


@dataclass
class LeagueConfig:
    name: str
    abbrev: str
    org: str
    level: str
    site: str
    stats_path: str = "/sports/bsb/{season}/players"
    gamelog_path: str = "/sports/bsb/{season}/players/{slug}?view=gamelog"
    transactions_archive: str = ""              # one season's report, {season} is filled in
    transactions_current: tuple[str, ...] = ()  # the live report, only valid for the current transaction season

    def stats_url(self, season: int, group: str, view: str = "", page: int = 1) -> str:
        url = f"{self.site}{self.stats_path.format(season=season)}?pos={group}&r=0"
        if view:
            url += f"&view={view}"
        if page > 1:
            url += f"&page={page}"
        return url


PIONEER = LeagueConfig(
    name="Pioneer League",
    abbrev="PBL",
    org="independent",
    level="mlb_partner",
    site="https://www.pioneerleague.com",
    transactions_archive="https://www.pioneerleague.com/players/transactions/{season}_Transactions",
    transactions_current=(
        "https://www.pioneerleague.com/players/transactions",
        "https://pioneerleague.prestosports.com/players/transactions",
    ),
)


def transaction_season(today: date | None = None) -> int:
    """
    A league's transaction report runs from October through September, labeled by the
    season it leads into. Moves made in November 2026 belong to the 2027 report.
    """
    today = today or date.today()
    return today.year + 1 if today.month >= 10 else today.year


def stats_season(today: date | None = None) -> int:
    """Most recent season with stats. Before May, that is last year."""
    today = today or date.today()
    return today.year if today.month >= 5 else today.year - 1


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def fetch_group(http: PoliteSession, cfg: LeagueConfig, season: int, group: str) -> list[presto.StatRow]:
    """Every view and every page of one stat group, merged into one row per player per team."""
    first_url = cfg.stats_url(season, group)
    first = http.get_text(first_url)
    views = presto.discover_views(first, group)
    log.info("%s %s group=%s views=%s", cfg.abbrev, season, group, views or [""])

    batches = []
    for view in views:
        html = first if view == "" else http.get_text(cfg.stats_url(season, group, view))
        pages = presto.page_count(html)
        rows = presto.parse_stat_tables(html, group, cfg.site)
        for p in range(2, pages + 1):
            rows += presto.parse_stat_tables(http.get_text(cfg.stats_url(season, group, view, p)), group, cfg.site)
        batches.append(rows)
    return presto.merge_rows(*batches)


def load_stats(conn, http: PoliteSession, cfg: LeagueConfig, season: int, source_id: int, league_id: int,
               tally: dict) -> dict[str, str]:
    """Load hitting, pitching, fielding. Returns {team url: team name} for the roster pass."""
    teams: dict[str, str] = {}
    for group in ("h", "p", "f"):
        rows = fetch_group(http, cfg, season, group)
        log.info("%s %s group=%s rows=%d", cfg.abbrev, season, group, len(rows))
        for r in rows:
            if not r.team_name:
                tally["errors"].append(f"no team link for {r.player_label} ({group})")
                continue
            teams.setdefault(r.team_href, r.team_name)
            team_id = db.get_or_create_team(conn, r.team_name, cfg.org, r.team_href)
            db.upsert_team_season(conn, team_id, season, league_id)

            first, last = presto.split_name(r.player_label)
            pid = db.upsert_player(conn, source_id, presto.slug_from_href(r.player_href), r.player_href, first, last)
            db.add_eligibility(conn, pid, "independent", source_id, cfg.stats_url(season, group))

            if group == "h":
                db.upsert_batting(conn, pid, season, team_id, r.stats, source_id)
            elif group == "p":
                db.upsert_pitching(conn, pid, season, team_id, r.stats, source_id)
            else:
                stats = dict(r.stats)
                position = stats.pop("position", None) or "ALL"
                db.upsert_fielding(conn, pid, season, team_id, position, stats, source_id)
            tally["rows"] += 1
        conn.commit()
    return teams


# ---------------------------------------------------------------------------
# Rosters
# ---------------------------------------------------------------------------

def _hometown(text: str | None) -> tuple[str | None, str | None]:
    """'Boise, Idaho / Capital HS' -> ('Boise', 'Idaho')."""
    if not text:
        return None, None
    place = text.split("/")[0].strip()
    if "," in place:
        city, state = [p.strip() for p in place.split(",", 1)]
        return city or None, state or None
    return place or None, None


def load_rosters(conn, http: PoliteSession, cfg: LeagueConfig, season: int, source_id: int, league_id: int,
                 teams: dict[str, str], tally: dict):
    for team_url, team_name in teams.items():
        try:
            html = http.get_text(f"{team_url}?view=roster")
        except Exception as e:                       # one bad roster page should not stop the run
            tally["errors"].append(f"roster {team_name}: {e!r}")
            continue
        rows = presto.parse_roster(html, cfg.site)
        if not rows:
            tally["errors"].append(f"roster {team_name}: no roster table found")
        for r in rows:
            first, last = presto.split_name(r.name)
            city, state = _hometown(r.fields.get("hometown"))
            college_id = None
            if r.fields.get("college"):
                college_id = db.get_or_create_team(conn, r.fields["college"], "college")
            pid = db.upsert_player(
                conn, source_id, presto.slug_from_href(r.player_href), r.player_href, first, last,
                bats=r.fields.get("bats"), throws=r.fields.get("throws"),
                height_in=r.fields.get("height_in"), weight_lb=r.fields.get("weight_lb"),
                hometown_city=city, hometown_state=state,
                # "OF/RHP" -> "OF": the first listed position is his primary one
                primary_position=(r.fields.get("position") or "").upper().split("/")[0].strip() or None,
                college_team_id=college_id,
            )
            db.add_eligibility(conn, pid, "independent", source_id, f"{team_url}?view=roster")
            tally["rows"] += 1
        conn.commit()


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

def report_lines(html: str) -> list[str]:
    """Pull the transaction text out of the page, turning list items into '- ' bullets."""
    soup = BeautifulSoup(html, "lxml")
    for junk in soup(["script", "style", "nav", "header", "footer", "form"]):
        junk.decompose()
    main = soup.find("main") or soup.find(id=re.compile(r"(main|content)", re.I)) or soup.body or soup
    for li in main.find_all("li"):
        li.insert(0, "- ")
    return [ln.strip() for ln in main.get_text("\n").splitlines() if ln.strip()]


def fetch_report(http: PoliteSession, cfg: LeagueConfig, season: int,
                 today: date | None = None) -> tuple[str, str]:
    """
    The season's archive page first. The live page is only used for the current transaction
    season, because its dates carry no year and parsing it as the wrong season would shift
    every date by a year.
    """
    urls = [cfg.transactions_archive.format(season=season)] if cfg.transactions_archive else []
    if season == transaction_season(today):
        urls += list(cfg.transactions_current)
    last_err = None
    for url in urls:
        try:
            html = http.get_text(url)
            if re.search(r"\b(signed|traded|released|waivers|injury list)\b", html, re.I):
                return url, html
        except Exception as e:
            last_err = e
    raise RuntimeError(f"no transaction report found for {season}: {last_err!r}")


def load_transactions(conn, http: PoliteSession, cfg: LeagueConfig, season: int, source_id: int,
                      tally: dict) -> dict:
    url, html = fetch_report(http, cfg, season)
    known = [r["name"] for r in conn.execute("SELECT name FROM teams WHERE org = 'independent'").fetchall()]
    parsed = parse_report(report_lines(html), season, known_teams=known)
    idx = db.name_index(conn)

    summary = {"url": url, "parsed": len(parsed), "inserted": 0, "unmatched": [], "unclassified": []}
    for t in parsed:
        if not t.player_name:
            summary["unclassified"].append(t.raw_text)
            continue

        header_team_id = db.find_team(conn, t.team) if t.team else None
        cp_id = None
        if t.counterparty:
            cp_id = db.find_team(conn, t.counterparty) or db.get_or_create_team(
                conn, re.sub(r"\s*\(.*?\)\s*$", "", t.counterparty),
                "affiliated" if is_affiliated_club(t.counterparty) else "independent")
        to_id = header_team_id if t.to_team == t.team else (cp_id if t.to_team else None)
        from_id = header_team_id if t.from_team == t.team else (cp_id if t.from_team else None)

        pid = db.match_player(idx, t.player_name, team_hint=[t.team, t.counterparty or ""])
        if pid is None:
            summary["unmatched"].append(f"{t.txn_date} {t.team}: {t.raw_text}")

        if db.insert_transaction(
                conn, player_id=pid, raw_name=t.player_name, txn_date=t.txn_date, txn=t.txn,
                status_effect=status_after(t), team_name=t.team or None, counterparty=t.counterparty,
                from_team_id=from_id, to_team_id=to_id, raw_text=t.raw_text,
                source_id=source_id, source_url=url):
            summary["inserted"] += 1
            tally["rows"] += 1
    conn.commit()
    return summary


# ---------------------------------------------------------------------------
# Game logs
# ---------------------------------------------------------------------------

def season_is_live(season: int, today: date | None = None) -> bool:
    """Games are still being added May through September of that season."""
    today = today or date.today()
    return today.year == season and 5 <= today.month <= 9


def load_gamelogs(conn, http: PoliteSession, cfg: LeagueConfig, season: int, source_id: int, tally: dict,
                  force: bool = False) -> dict:
    """
    One request per player. A finished season is fetched once and then skipped, so the
    biweekly refresh does not re-download hundreds of pages that cannot change.
    """
    players = conn.execute(
        """SELECT x.player_id, x.external_id FROM player_external_ids x
           WHERE x.source_id = %s AND x.player_id IN (
               SELECT player_id FROM batting_stats WHERE season = %s
               UNION SELECT player_id FROM pitching_stats WHERE season = %s)
           ORDER BY x.player_id""", (source_id, season, season)).fetchall()
    live = season_is_live(season)
    summary = {"players": len(players), "fetched": 0, "skipped": 0, "games": 0, "empty": 0}
    for row in players:
        pid = row["player_id"]
        if not force and not live and db.has_games(conn, pid, season):
            summary["skipped"] += 1
            continue
        url = cfg.site + cfg.gamelog_path.format(season=season, slug=row["external_id"])
        try:
            games = presto.parse_gamelog(http.get_text(url), season)
        except Exception as e:                       # one bad page should not stop the run
            tally["errors"].append(f"game log {row['external_id']}: {e!r}")
            continue
        summary["fetched"] += 1
        if not games:
            summary["empty"] += 1
            continue
        team_id = db.single_team(conn, pid, season)
        for g in games:
            db.upsert_game(conn, g, pid, season, team_id, source_id)
        summary["games"] += len(games)
        tally["rows"] += len(games)
        conn.commit()
    return summary


# ---------------------------------------------------------------------------
# Full run
# ---------------------------------------------------------------------------

def run(conn, http: PoliteSession, season: int, cfg: LeagueConfig = PIONEER,
        rosters: bool = True, txn_seasons: tuple[int, ...] | None = None,
        target_season: int | None = None, gamelogs: bool = True) -> dict:
    """
    season         stats and roster season (rosters are read for names and bio only)
    txn_seasons    transaction reports to load; default is just the upcoming season's
    target_season  the season statuses are computed for; default is the upcoming season
    """
    target_season = target_season or transaction_season()
    txn_seasons = txn_seasons if txn_seasons is not None else (target_season,)
    source_id = db.get_or_create_source(conn, f"{cfg.name} site", cfg.site, priority=10)
    league_id = db.get_or_create_league(conn, cfg.name, cfg.org, cfg.level, cfg.abbrev, cfg.site)
    db.mark_league_complete(conn, league_id)       # every player in the league gets loaded
    conn.commit()

    result: dict = {}
    with db.scrape_run(conn, source_id) as tally:
        teams = load_stats(conn, http, cfg, season, source_id, league_id, tally)
        result["teams"] = len(teams)
        if rosters:
            load_rosters(conn, http, cfg, season, source_id, league_id, teams, tally)
        if gamelogs:
            result["gamelogs"] = load_gamelogs(conn, http, cfg, season, source_id, tally)
        result["transactions"] = {}
        if txn_seasons:
            for txn_season in dict.fromkeys(txn_seasons):
                try:
                    result["transactions"][txn_season] = load_transactions(conn, http, cfg, txn_season, source_id, tally)
                except RuntimeError as e:      # e.g. no archive page yet for a season
                    tally["errors"].append(str(e))
        result["status_for_season"] = target_season
        result["status_rows"] = db.rebuild_status(conn, target_season)
        result["rows"] = tally["rows"]
        result["errors"] = list(tally["errors"])
    return result
