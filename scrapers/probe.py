"""
Source probe: can the scraper reach each candidate data source?

For every URL it checks robots.txt for our User-Agent first and never fetches a path that
robots.txt disallows. Then it makes one request, identifying itself honestly, and reports
the HTTP status, the size, and whether the page holds what we expect.

    python -m scrapers.probe
"""

from __future__ import annotations

import json
import time
from urllib import robotparser
from urllib.parse import urlparse

import requests

from .http import USER_AGENT

# (group, label, url, text expected on a working page)
SOURCES = [
    ("Pioneer League", "robots.txt", "https://www.pioneerleague.com/robots.txt", ""),
    ("Pioneer League", "Hitting stats", "https://www.pioneerleague.com/sports/bsb/2026/players?pos=h&r=0", "avg"),
    ("Pioneer League", "Team roster", "https://www.pioneerleague.com/sports/bsb/2026/teams/boisehawks?view=roster", "roster"),
    ("Pioneer League", "Transactions (live)", "https://www.pioneerleague.com/players/transactions", "Signed"),
    ("Pioneer League", "Transactions (prestosports host)", "https://pioneerleague.prestosports.com/players/transactions", "Signed"),

    ("Frontier League", "Home", "https://www.frontierleague.com/", "Frontier"),
    ("Frontier League", "2026 transactions", "https://www.frontierleague.com/2026-transactions", "TRANSACTIONS"),
    ("American Association", "Home", "https://aabaseball.com/", "American Association"),
    ("American Association", "2026 transactions", "https://aabaseball.com/transactions/2026-transactions/", "Released"),
    ("Atlantic League", "Home", "https://www.atlanticleague.com/", "Atlantic"),

    ("MLB Stats API", "Sports list", "https://statsapi.mlb.com/api/v1/sports", "sports"),
    ("MLB Stats API", "Independent league teams 2026", "https://statsapi.mlb.com/api/v1/teams?sportId=23&season=2026", "teams"),
    ("MLB Stats API", "Affiliated transactions Oct to Nov 2026",
     "https://statsapi.mlb.com/api/v1/transactions?sportId=1&startDate=2026-10-01&endDate=2026-11-15", "transactions"),
    ("MLB Stats API", "Minor league transactions Oct to Nov 2026",
     "https://statsapi.mlb.com/api/v1/transactions?sportId=11&startDate=2026-10-01&endDate=2026-11-15", "transactions"),

    ("Baseball Reference", "robots.txt", "https://www.baseball-reference.com/robots.txt", ""),
    ("Baseball Reference", "Register (minors, indy, college)", "https://www.baseball-reference.com/register/", "Register"),

    ("College", "NCAA stats", "https://stats.ncaa.org/", "NCAA"),
    ("College", "Sidearm school site (Oregon State)", "https://osubeavers.com/sports/baseball/stats/2026", "Batting"),
    ("College", "Sidearm school site (Gonzaga)", "https://gozags.com/sports/baseball/stats/2026", "Batting"),
    ("College", "The Baseball Cube", "https://www.thebaseballcube.com/", "Baseball"),
]

_robots: dict[str, robotparser.RobotFileParser | None | str] = {}


def robots_for(url: str):
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        try:
            r = requests.get(f"{base}/robots.txt", headers={"User-Agent": USER_AGENT}, timeout=20)
            if r.status_code == 200:
                rp = robotparser.RobotFileParser()
                rp.parse(r.text.splitlines())
                _robots[base] = rp
            else:
                _robots[base] = f"robots.txt returned {r.status_code}"
        except requests.RequestException as e:
            _robots[base] = f"robots.txt unreachable ({type(e).__name__})"
    return _robots[base]


def probe() -> list[dict]:
    out, last = [], {}
    for group, label, url, expect in SOURCES:
        host = urlparse(url).netloc
        if host in last:
            time.sleep(max(0, 3 - (time.monotonic() - last[host])))
        row = {"group": group, "label": label, "url": url}
        rp = robots_for(url)
        row["robots"] = ("allowed" if rp.can_fetch(USER_AGENT, url) else "DISALLOWED") if hasattr(rp, "can_fetch") else rp
        if row["robots"] == "DISALLOWED" and not url.endswith("robots.txt"):
            row["status"], row["note"] = "skipped", "robots.txt disallows this path for our scraper"
            out.append(row)
            continue
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25)
            last[host] = time.monotonic()
            row["status"] = r.status_code
            row["bytes"] = len(r.content)
            row["expected_text"] = (expect.lower() in r.text.lower()) if expect else None
            row["server"] = r.headers.get("server", "")
            row["note"] = summarize(url, r)
        except requests.RequestException as e:
            row["status"], row["note"] = "error", f"{type(e).__name__}: {e}"[:200]
        out.append(row)
    return out


def summarize(url: str, r: requests.Response) -> str:
    """A one line peek at what came back, for the pages where that matters."""
    if r.status_code != 200:
        body = r.text[:300].replace("\n", " ")
        return "blocked page: " + body if any(k in body.lower() for k in ("cloudflare", "access denied", "forbidden", "captcha")) else ""
    if "statsapi" in url:
        try:
            d = r.json()
        except ValueError:
            return "not JSON"
        if "sports" in d:
            return "sports: " + ", ".join(f"{s['id']}={s['name']}" for s in d["sports"][:30])
        if "teams" in d:
            leagues = sorted({t.get("league", {}).get("name", "?") for t in d["teams"]})
            return f"{len(d['teams'])} teams; leagues: " + ", ".join(leagues)
        if "transactions" in d:
            kinds = {}
            for t in d["transactions"]:
                kinds[t.get("typeDesc", "?")] = kinds.get(t.get("typeDesc", "?"), 0) + 1
            top = sorted(kinds.items(), key=lambda x: -x[1])[:8]
            return f"{len(d['transactions'])} moves; " + ", ".join(f"{k} {v}" for k, v in top)
    if url.endswith("robots.txt"):
        lines = [ln for ln in r.text.splitlines() if ln.strip() and not ln.startswith("#")]
        return " | ".join(lines[:12])[:400]
    return ""


def main():
    rows = probe()
    for row in rows:
        mark = row["status"]
        print(f"[{mark}] {row['group']}: {row['label']}")
        print(f"    {row['url']}")
        print(f"    robots: {row['robots']}   bytes: {row.get('bytes', '')}   expected text found: {row.get('expected_text')}")
        if row.get("note"):
            print(f"    {row['note']}")
    print("\nJSON:", json.dumps(rows))


if __name__ == "__main__":
    main()
