"""
Live site check: fetch one page of each kind from the league site and report what the
parsers read. Needs no database. Run it before the first load, and again whenever a load
looks wrong, since a site redesign shows up here first.

    python cli.py check-site
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from . import pioneer, presto
from .transactions import parse_report

EXPECTED = {
    "h": ["g", "ab", "h", "b2", "hr", "bb", "so"],
    "p": ["g", "gs", "outs", "h", "er", "bb", "so", "hr"],
    "f": ["po", "a", "e"],
}
LABELS = {"h": "Hitting stats", "p": "Pitching stats", "f": "Fielding stats"}


@dataclass
class Check:
    name: str
    status: str = "PASS"          # PASS, WARN, FAIL
    url: str = ""
    lines: list[str] = field(default_factory=list)

    def warn(self, msg):
        if self.status == "PASS":
            self.status = "WARN"
        self.lines.append(msg)

    def fail(self, msg):
        self.status = "FAIL"
        self.lines.append(msg)


def _headers_seen(html: str) -> list[list[str]]:
    soup = BeautifulSoup(html, "lxml")
    return [presto._headers(t) for t in soup.find_all("table")]


def check_site(http, cfg: pioneer.LeagueConfig = pioneer.PIONEER, season: int | None = None) -> list[Check]:
    season = season or pioneer.stats_season()
    checks: list[Check] = []
    first_pitcher = None
    first_team_url = None

    for group in ("h", "p", "f"):
        c = Check(LABELS[group], url=cfg.stats_url(season, group))
        checks.append(c)
        try:
            html = http.get_text(c.url)
            rows = presto.parse_stat_tables(html, group, cfg.site)
            if not rows:
                c.fail("No players found on the page.")
                for h in _headers_seen(html)[:4]:
                    c.lines.append(f"  table headers seen: {h}")
                continue
            views = presto.discover_views(html, group)
            c.lines.append(f"{len(rows)} players on page 1 of {presto.page_count(html)}. Views linked: {', '.join(v or 'standard' for v in views)}.")
            found = set().union(*(r.stats.keys() for r in rows))
            missing = [k for k in EXPECTED[group] if k not in found]
            if missing:
                c.warn(f"Columns not read on the standard view: {', '.join(missing)} (they may come from another view).")
                c.lines.append(f"  headers seen: {_headers_seen(html)[0]}")
            if not all(r.team_name for r in rows):
                c.warn("Some rows have no team link.")
            for r in rows[:3]:
                c.lines.append(f"  {r.player_label:<20} {r.team_name or '?':<24} {dict(list(r.stats.items())[:8])}")
            if group == "p":
                first_pitcher = rows[0]
            if group == "h":
                first_team_url = next((r.team_href for r in rows if r.team_href), None)
        except Exception as e:
            c.fail(f"Could not load the page: {e!r}")

    c = Check("Team roster")
    checks.append(c)
    if not first_team_url:
        c.fail("Skipped: no team link was found on the hitting page.")
    else:
        c.url = f"{first_team_url}?view=roster"
        try:
            roster = presto.parse_roster(http.get_text(c.url), cfg.site)
            if not roster:
                c.fail("No roster table found.")
            else:
                c.lines.append(f"{len(roster)} players.")
                if not any(r.fields.get("bats") for r in roster):
                    c.warn("Bats and throws were not read.")
                for r in roster[:3]:
                    c.lines.append(f"  {r.name:<22} {r.fields}")
        except Exception as e:
            c.fail(f"Could not load the roster: {e!r}")

    c = Check("Game log")
    checks.append(c)
    if not first_pitcher:
        c.fail("Skipped: no pitcher was found on the pitching page.")
    else:
        slug = presto.slug_from_href(first_pitcher.player_href)
        c.url = cfg.site + cfg.gamelog_path.format(season=season, slug=slug)
        try:
            games = presto.parse_gamelog(http.get_text(c.url), season)
            if not games:
                c.fail(f"No games read for {first_pitcher.player_label}. The game log address or layout may differ.")
            else:
                kinds = Counter("pitching" if g.group == "p" else "batting" for g in games)
                c.lines.append(f"{first_pitcher.player_label}: {', '.join(f'{n} {k} games' for k, n in kinds.items())}.")
                for g in games[:3]:
                    c.lines.append(f"  {g.game_date} {g.opponent or '?':<24} {g.result or '':<8} {g.stats}")
        except Exception as e:
            c.fail(f"Could not load the game log: {e!r}")

    for txn_season in dict.fromkeys((pioneer.transaction_season(), season)):
        c = Check(f"Transactions, {txn_season} report")
        checks.append(c)
        try:
            c.url, html = pioneer.fetch_report(http, cfg, txn_season)
            parsed = parse_report(pioneer.report_lines(html), txn_season)
            named = [t for t in parsed if t.player_name]
            if not named:
                c.fail("No transactions read.")
                continue
            counts = Counter(t.txn for t in named)
            c.lines.append(f"{len(named)} moves: {', '.join(f'{n} {k}' for k, n in counts.most_common())}.")
            if len(parsed) > len(named):
                c.warn(f"{len(parsed) - len(named)} lines had no player name and will be skipped.")
            for t in named[:3]:
                c.lines.append(f"  {t.txn_date} {t.team[:22]:<22} {t.txn:<14} {t.player_name}")
        except Exception as e:
            # The upcoming season's report may not exist yet early in the offseason.
            c.warn(f"No report found: {e}")

    return checks


def format_checks(checks: list[Check]) -> str:
    out = []
    for c in checks:
        out.append(f"[{c.status}] {c.name}")
        if c.url:
            out.append(f"  {c.url}")
        out.extend(f"  {line}" for line in c.lines)
        out.append("")
    worst = "FAIL" if any(c.status == "FAIL" for c in checks) else "WARN" if any(c.status == "WARN" for c in checks) else "PASS"
    out.append({"PASS": "Everything read correctly. Ready for the first load.",
                "WARN": "Loaded with warnings. Read them above before the first load.",
                "FAIL": "Something could not be read. Send this output over before the first load."}[worst])
    return "\n".join(out)
