"""
Parser for PrestoSports stat sites.

PrestoSports powers the Pioneer League site and many college and summer league sites,
so this module is written to be reused. It avoids depending on CSS class names, which
change between site themes. Instead it:

* finds player rows by the link to a player page ("/players/<slug>"),
* finds the team by the link to a team page ("/teams/<slug>"),
* maps column headers through an alias table to the database column names.

League player list:   /sports/bsb/{season}/players?pos=h|p|f&r=0[&view=...][&page=N]
Team roster:          /sports/bsb/{season}/teams/{slug}?view=roster
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Header aliases -> database columns, per stat group
# ---------------------------------------------------------------------------

BATTING_ALIASES = {
    "g": "g", "gp": "g", "games": "g",
    "gs": "gs",
    "pa": "pa", "tpa": "pa",
    "ab": "ab", "r": "r", "h": "h",
    "2b": "b2", "dbl": "b2", "3b": "b3", "tpl": "b3", "hr": "hr",
    "rbi": "rbi", "bb": "bb", "ibb": "ibb", "k": "so", "so": "so",
    "hbp": "hbp", "hp": "hbp", "sf": "sf", "sh": "sh", "sac": "sh",
    "sb": "sb", "cs": "cs", "gdp": "gdp", "hdp": "gdp", "gidp": "gdp",
}

PITCHING_ALIASES = {
    "w": "w", "l": "l", "g": "g", "gp": "g", "app": "g", "gs": "gs",
    "cg": "cg", "sho": "sho", "sv": "sv",
    "ip": "outs",                    # converted from innings to outs
    "bf": "bf", "tbf": "bf",
    "h": "h", "r": "r", "er": "er", "hr": "hr",
    "bb": "bb", "ibb": "ibb", "k": "so", "so": "so",
    "hbp": "hbp", "hb": "hbp", "wp": "wp", "bk": "bk",
    "go": "gb", "gb": "gb", "fb": "fb", "ld": "ld",
}

FIELDING_ALIASES = {
    "g": "g", "gp": "g", "gs": "gs",
    "inn": "outs", "ip": "outs",     # defensive innings, converted to outs
    "po": "po", "a": "a", "e": "e", "dp": "dp",
    "pb": "pb", "sba": "sb_against", "sb": "sb_against", "csb": "cs_by", "cs": "cs_by",
    "pos": "position",
}

ROSTER_ALIASES = {
    "name": "name", "player": "name", "full name": "name",
    "no": "number", "no.": "number", "#": "number",
    "pos": "position", "pos.": "position", "position": "position",
    "b/t": "bt", "bats/throws": "bt", "b-t": "bt",
    "bats": "bats", "throws": "throws",
    "ht": "height", "ht.": "height", "height": "height",
    "wt": "weight", "wt.": "weight", "weight": "weight",
    "hometown": "hometown", "home town": "hometown", "hometown/high school": "hometown",
    "college": "college", "school": "college", "last school": "college", "previous school": "college",
    "dob": "birth_date", "birthdate": "birth_date", "born": "birth_date",
    "age": "age", "yr": "year", "yr.": "year",
}

GROUP_ALIASES = {"h": BATTING_ALIASES, "p": PITCHING_ALIASES, "f": FIELDING_ALIASES}

COUNTING_ZERO = {"-", "—", "–", ""}


# ---------------------------------------------------------------------------
# Value parsing
# ---------------------------------------------------------------------------

def innings_to_outs(text: str) -> Optional[int]:
    """'45.2' -> 137. Baseball notation: the decimal is outs, not tenths."""
    t = text.strip()
    if t in COUNTING_ZERO:
        return 0
    m = re.match(r"^(\d+)(?:\.(\d))?$", t)
    if not m:
        return None
    whole, frac = int(m.group(1)), int(m.group(2) or 0)
    if frac > 2:
        return None
    return whole * 3 + frac


def to_int(text: str) -> Optional[int]:
    t = text.strip().replace(",", "")
    if t in COUNTING_ZERO:
        return 0
    try:
        return int(t)
    except ValueError:
        try:
            f = float(t)
            return int(f) if f.is_integer() else None
        except ValueError:
            return None


def norm_header(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def slug_from_href(href: str) -> str:
    """'/sports/bsb/2026/players/jaketrimble1a2b' -> 'jaketrimble1a2b'."""
    return urlparse(href).path.rstrip("/").split("/")[-1]


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def _headers(table) -> list[str]:
    thead = table.find("thead")
    row = thead.find_all("tr")[-1] if thead and thead.find_all("tr") else table.find("tr")
    if row is None:
        return []
    return [norm_header(c.get_text(" ")) for c in row.find_all(["th", "td"])]


def _body_rows(table):
    body = table.find("tbody")
    rows = body.find_all("tr") if body else table.find_all("tr")[1:]
    return rows


@dataclass
class StatRow:
    player_href: str
    player_label: str
    team_href: Optional[str]
    team_name: Optional[str]
    stats: dict = field(default_factory=dict)

    @property
    def key(self):
        return (self.player_href, self.team_href)


def parse_stat_tables(html: str, group: str, base_url: str) -> list[StatRow]:
    """
    Parse every table on a league player list page for one stat group ('h', 'p', 'f').
    Rows without a player link (totals, headers repeated mid table) are skipped.
    """
    aliases = GROUP_ALIASES[group]
    soup = BeautifulSoup(html, "lxml")
    out: list[StatRow] = []

    for table in soup.find_all("table"):
        headers = _headers(table)
        if not headers:
            continue
        for tr in _body_rows(table):
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue
            p_link = tr.find("a", href=re.compile(r"/players/[^/?#]+"))
            if not p_link:
                continue
            t_link = tr.find("a", href=re.compile(r"/teams/[^/?#]+"))
            row = StatRow(
                player_href=urljoin(base_url, p_link["href"]).split("?")[0],
                player_label=p_link.get_text(" ", strip=True),
                team_href=urljoin(base_url, t_link["href"]).split("?")[0] if t_link else None,
                team_name=t_link.get_text(" ", strip=True) if t_link else None,
            )
            for i, cell in enumerate(cells):
                if i >= len(headers):
                    break
                col = aliases.get(headers[i])
                if not col:
                    continue
                text = cell.get_text(" ", strip=True)
                if col == "outs":
                    val = innings_to_outs(text)
                elif col == "position":
                    val = text or None
                else:
                    val = to_int(text)
                if val is not None and col not in row.stats:
                    row.stats[col] = val
            out.append(row)
    return out


def merge_rows(*row_lists: list[StatRow]) -> list[StatRow]:
    """Merge rows from several views of the same page (standard, extended...) by player and team."""
    merged: dict[tuple, StatRow] = {}
    for rows in row_lists:
        for r in rows:
            if r.key not in merged:
                merged[r.key] = StatRow(r.player_href, r.player_label, r.team_href, r.team_name, dict(r.stats))
            else:
                for k, v in r.stats.items():
                    merged[r.key].stats.setdefault(k, v)
    return list(merged.values())


# ---------------------------------------------------------------------------
# Page navigation
# ---------------------------------------------------------------------------

def discover_views(html: str, group: str) -> list[str]:
    """Return the view= values linked from the page for this stat group (always includes the default '')."""
    soup = BeautifulSoup(html, "lxml")
    views = {""}
    for a in soup.find_all("a", href=True):
        q = parse_qs(urlparse(a["href"]).query, keep_blank_values=True)
        if "view" in q and q.get("pos", [group])[0] == group:
            views.add(q["view"][0])
    # Skip views that are not stat tables.
    return sorted(v for v in views if v not in {"roster", "schedule", "news", "bio", "gamelog"})


def page_count(html: str) -> int:
    """Read 'Page 1/4' text or the highest page= link. Defaults to 1."""
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ")
    m = re.search(r"Page\s+\d+\s*/\s*(\d+)", text)
    pages = int(m.group(1)) if m else 1
    for a in soup.find_all("a", href=True):
        q = parse_qs(urlparse(a["href"]).query)
        if "page" in q and q["page"][0].isdigit():
            pages = max(pages, int(q["page"][0]))
    return pages


def team_links(html: str, base_url: str) -> dict[str, str]:
    """All team page links on a page: {absolute team url: team name}."""
    soup = BeautifulSoup(html, "lxml")
    out = {}
    for a in soup.find_all("a", href=re.compile(r"/teams/[^/?#]+")):
        url = urljoin(base_url, a["href"]).split("?")[0]
        name = a.get_text(" ", strip=True)
        if name:
            out.setdefault(url, name)
    return out


# ---------------------------------------------------------------------------
# Rosters
# ---------------------------------------------------------------------------

@dataclass
class RosterRow:
    player_href: str
    name: str
    fields: dict


def parse_height(text: str) -> Optional[int]:
    """'6-2', "6'2\"", '6 2' -> 74 inches."""
    m = re.match(r"^\s*(\d)\s*['\-’ ]\s*(\d{1,2})", text or "")
    return int(m.group(1)) * 12 + int(m.group(2)) if m else None


def parse_roster(html: str, base_url: str) -> list[RosterRow]:
    soup = BeautifulSoup(html, "lxml")
    out: list[RosterRow] = []
    for table in soup.find_all("table"):
        headers = _headers(table)
        if not any(ROSTER_ALIASES.get(h) == "name" for h in headers):
            continue
        for tr in _body_rows(table):
            link = tr.find("a", href=re.compile(r"/players/[^/?#]+"))
            if not link:
                continue
            cells = tr.find_all(["td", "th"])
            f: dict = {}
            for i, cell in enumerate(cells[: len(headers)]):
                col = ROSTER_ALIASES.get(headers[i])
                if col:
                    f[col] = cell.get_text(" ", strip=True)
            if "bt" in f:
                parts = re.split(r"\s*[/\-]\s*", f.pop("bt"))
                if len(parts) == 2:
                    f["bats"], f["throws"] = parts[0][:1].upper() or None, parts[1][:1].upper() or None
            if "height" in f:
                f["height_in"] = parse_height(f.pop("height"))
            if "weight" in f:
                f["weight_lb"] = to_int(re.sub(r"[^\d]", "", f.pop("weight")) or "")
            name = link.get_text(" ", strip=True) or f.get("name", "")
            out.append(RosterRow(urljoin(base_url, link["href"]).split("?")[0], name, f))
    return out


def split_name(full: str) -> tuple[str, str]:
    """'Jake Trimble' -> ('Jake', 'Trimble'); 'Trimble, Jake' -> ('Jake', 'Trimble'); keeps suffixes on the last name."""
    full = re.sub(r"\s+", " ", full.strip())
    if "," in full:
        last, first = [p.strip() for p in full.split(",", 1)]
        return first, last
    parts = full.split(" ")
    if len(parts) == 1:
        return "", parts[0]
    if parts[-1].rstrip(".").lower() in {"jr", "sr", "ii", "iii", "iv"} and len(parts) > 2:
        return " ".join(parts[:-2]), " ".join(parts[-2:])
    return " ".join(parts[:-1]), parts[-1]
