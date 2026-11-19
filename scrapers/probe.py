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


if __name__ == "__main__" and not ({"--deep", "--coverage"} & set(__import__("sys").argv)):
    main()


# ---------------------------------------------------------------------------
# Deep probe of the MLB Stats API for the independent leagues (sportId 23)
# ---------------------------------------------------------------------------

API = "https://statsapi.mlb.com/api"


def _get(path: str):
    time.sleep(1.0)
    r = requests.get(f"{API}{path}", headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    return r.json()


def deep():
    def show(label, fn):
        try:
            print(f"[ok] {label}: {fn()}")
        except Exception as e:
            print(f"[--] {label}: {type(e).__name__}: {str(e)[:160]}")

    teams = _get("/v1/teams?sportId=23&season=2026")["teams"]
    pion = [t for t in teams if t.get("league", {}).get("name") == "Pioneer League"]
    print(f"Pioneer League teams in the API: {len(pion)}: {', '.join(t['name'] for t in pion)}")
    boise = next((t for t in pion if "Boise" in t["name"]), pion[0] if pion else None)
    league_id = boise["league"]["id"] if boise else None
    copyright_note = _get("/v1/sports").get("copyright", "")
    print(f"API copyright notice: {copyright_note}")
    if not boise:
        return
    print(f"Using {boise['name']} (team {boise['id']}, league {league_id})")

    roster = _get(f"/v1/teams/{boise['id']}/roster?season=2026&rosterType=fullSeason").get("roster", [])
    show("Full season roster", lambda: f"{len(roster)} players, e.g. " + ", ".join(
        f"{p['person']['fullName']} ({p['position']['abbreviation']})" for p in roster[:4]))
    hitter = next((p for p in roster if p["position"]["type"] != "Pitcher"), None)
    pitcher = next((p for p in roster if p["position"]["type"] == "Pitcher"), None)

    def bio():
        pid = (hitter or pitcher)["person"]["id"]
        p = _get(f"/v1/people/{pid}")["people"][0]
        keys = ["fullName", "birthDate", "currentAge", "height", "weight", "batSide", "pitchHand", "birthCity",
                "birthStateProvince", "draftYear", "mlbDebutDate", "primaryPosition"]
        return {k: (p[k]["code"] if isinstance(p.get(k), dict) and "code" in p[k] else p.get(k)) for k in keys if k in p}
    show("Player bio fields", bio)

    def season(pid, group):
        d = _get(f"/v1/people/{pid}/stats?stats=season&group={group}&sportId=23&season=2026")
        splits = d["stats"][0]["splits"] if d.get("stats") else []
        if not splits:
            return "no splits"
        s = splits[0]["stat"]
        return f"{len(s)} fields: " + ", ".join(list(s.keys())[:40])
    if hitter:
        show(f"Season hitting ({hitter['person']['fullName']})", lambda: season(hitter["person"]["id"], "hitting"))
        show("Season fielding", lambda: season(hitter["person"]["id"], "fielding"))
    if pitcher:
        show(f"Season pitching ({pitcher['person']['fullName']})", lambda: season(pitcher["person"]["id"], "pitching"))

    def gamelog(pid, group):
        d = _get(f"/v1/people/{pid}/stats?stats=gameLog&group={group}&sportId=23&season=2026")
        splits = d["stats"][0]["splits"] if d.get("stats") else []
        if not splits:
            return "no games"
        g = splits[0]
        return f"{len(splits)} games; first: {g.get('date')} vs {g.get('opponent', {}).get('name')} {dict(list(g['stat'].items())[:10])}"
    if pitcher:
        show("Pitching game log", lambda: gamelog(pitcher["person"]["id"], "pitching"))
    if hitter:
        show("Hitting game log", lambda: gamelog(hitter["person"]["id"], "hitting"))

    def splits():
        pid = hitter["person"]["id"]
        d = _get(f"/v1/people/{pid}/stats?stats=statSplits&group=hitting&sportId=23&season=2026&sitCodes=vl,vr,h,a")
        sp = d["stats"][0]["splits"] if d.get("stats") else []
        return f"{len(sp)} splits: " + ", ".join(f"{s['split']['description']} AVG {s['stat'].get('avg')}" for s in sp)
    if hitter:
        show("Splits vs LHP / RHP, home / away", splits)

    def advanced():
        pid = hitter["person"]["id"]
        d = _get(f"/v1/people/{pid}/stats?stats=seasonAdvanced&group=hitting&sportId=23&season=2026")
        sp = d["stats"][0]["splits"] if d.get("stats") else []
        return ", ".join(list(sp[0]["stat"].keys())[:30]) if sp else "none"
    if hitter:
        show("Advanced hitting fields", advanced)

    def league_wide(group):
        d = _get(f"/v1/stats?stats=season&group={group}&sportId=23&season=2026&leagueIds={league_id}&playerPool=ALL&limit=2000")
        sp = d["stats"][0]["splits"] if d.get("stats") else []
        return f"{len(sp)} players in one request"
    show("Whole league hitting in one call", lambda: league_wide("hitting"))
    show("Whole league pitching in one call", lambda: league_wide("pitching"))

    def txns():
        d = _get("/v1/transactions?sportId=23&startDate=2025-10-01&endDate=2026-11-18")
        t = d.get("transactions", [])
        pl = [x for x in t if "Pioneer" in json.dumps(x.get("toTeam", {})) + json.dumps(x.get("fromTeam", {}))
              or any(b["id"] == x.get("toTeam", {}).get("id") or b["id"] == x.get("fromTeam", {}).get("id") for b in pion)]
        kinds = {}
        for x in pl:
            kinds[x.get("typeDesc", "?")] = kinds.get(x.get("typeDesc", "?"), 0) + 1
        sample = pl[0]["description"] if pl else ""
        return f"{len(t)} indy moves, {len(pl)} Pioneer League; types {kinds}; e.g. {sample}"
    show("Independent league transactions", txns)

    def pitch_tracking():
        sched = _get(f"/v1/schedule?sportId=23&teamId={boise['id']}&startDate=2026-07-01&endDate=2026-07-10")
        pks = [g["gamePk"] for d in sched.get("dates", []) for g in d["games"]]
        if not pks:
            return "no games found in that week"
        feed = _get(f"/v1.1/game/{pks[0]}/feed/live")
        plays = feed.get("liveData", {}).get("plays", {}).get("allPlays", [])
        pitches = [e for p in plays for e in p.get("playEvents", []) if e.get("isPitch")]
        velo = [e for e in pitches if e.get("pitchData", {}).get("startSpeed")]
        spin = [e for e in pitches if e.get("pitchData", {}).get("breaks", {}).get("spinRate")]
        ev = [e for e in pitches if e.get("hitData", {}).get("launchSpeed")]
        ex = velo[0]["pitchData"] if velo else {}
        return (f"game {pks[0]}: {len(pitches)} pitches, {len(velo)} with velocity, {len(spin)} with spin, "
                f"{len(ev)} with exit velocity; sample speed {ex.get('startSpeed')} type "
                f"{velo[0].get('details', {}).get('type', {}).get('description') if velo else None}")
    show("Pitch tracking in game feeds", pitch_tracking)

    def college():
        d = _get("/v1/teams?sportId=22&season=2026")
        return f"{len(d.get('teams', []))} college teams"
    show("College coverage (sportId 22)", college)

    def affiliated_releases():
        d = _get("/v1/transactions?sportId=11&startDate=2026-09-01&endDate=2026-11-18")
        t = [x for x in d.get("transactions", []) if x.get("typeCode") in ("REL", "DFA") or "free agency" in x.get("typeDesc", "").lower()]
        return f"{len(t)} Triple-A releases or free agency moves since Sep 1; e.g. {t[0]['description'] if t else ''}"
    show("Affiliated releases (Triple-A sample)", affiliated_releases)


if __name__ == "__main__" and len(__import__("sys").argv) > 1 and __import__("sys").argv[1] == "--deep":
    deep()


def coverage():
    """Which leagues in the API actually carry players and stats, not just team names."""
    for sport_id, label in ((23, "Independent"), (22, "College")):
        teams = _get(f"/v1/teams?sportId={sport_id}&season=2026")["teams"]
        leagues: dict = {}
        for t in teams:
            lg = t.get("league", {})
            leagues.setdefault((lg.get("id"), lg.get("name", "?")), []).append(t)
        print(f"== {label}: {len(teams)} teams, {len(leagues)} leagues")
        for (lid, lname), ts in list(leagues.items())[:8]:
            t = ts[0]
            try:
                full = len(_get(f"/v1/teams/{t['id']}/roster?season=2026&rosterType=fullSeason").get("roster", []))
                active = len(_get(f"/v1/teams/{t['id']}/roster?season=2026").get("roster", []))
                games = sum(len(d["games"]) for d in _get(f"/v1/schedule?sportId={sport_id}&teamId={t['id']}&season=2026").get("dates", []))
                stats = _get(f"/v1/stats?stats=season&group=hitting&sportId={sport_id}&season=2026&leagueIds={lid}&playerPool=ALL&limit=2000") if lid else {}
                n = len(stats["stats"][0]["splits"]) if stats.get("stats") else 0
                print(f"   {lname} ({len(ts)} teams): {t['name']} roster {full}/{active}, games {games}; league hitting rows {n}")
            except Exception as e:
                print(f"   {lname}: {type(e).__name__} {str(e)[:120]}")
    # Was the Pioneer League ever covered? Try 2025 and 2024.
    for yr in (2025, 2024):
        try:
            s = _get(f"/v1/stats?stats=season&group=hitting&sportId=23&season={yr}&leagueIds=128&playerPool=ALL&limit=2000")
            n = len(s["stats"][0]["splits"]) if s.get("stats") else 0
            print(f"Pioneer League hitting rows {yr}: {n}")
        except Exception as e:
            print(f"Pioneer League {yr}: {type(e).__name__}")


if __name__ == "__main__" and "--coverage" in __import__("sys").argv:
    coverage()
