"""
Database helpers: lookups, upserts, run logging, and the status rebuild.

All writes are idempotent (ON CONFLICT ... DO UPDATE / DO NOTHING), so any scraper can
be rerun safely and a refresh simply overwrites older numbers with newer ones.
"""

from __future__ import annotations

import os
import re
import unicodedata
from contextlib import contextmanager
from typing import Iterable, Optional

import psycopg
from psycopg.rows import dict_row

DB_DIR = os.path.join(os.path.dirname(__file__), "..", "db")
SCHEMA_FILES = ["schema.sql", "migrations.sql", "web.sql"]   # supabase.sql runs separately, in Supabase

BATTING_COLS = ["g", "pa", "ab", "r", "h", "b2", "b3", "hr", "rbi", "bb", "ibb", "so",
                "hbp", "sf", "sh", "sb", "cs", "gdp"]
PITCHING_COLS = ["w", "l", "g", "gs", "cg", "sho", "sv", "outs", "bf", "h", "r", "er", "hr",
                 "bb", "ibb", "so", "hbp", "wp", "bk", "gb", "fb", "ld", "iffb"]
FIELDING_COLS = ["g", "gs", "outs", "po", "a", "e", "dp", "pb", "sb_against", "cs_by"]


def connect(url: Optional[str] = None) -> psycopg.Connection:
    url = url or os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set. Copy .env.example to .env and fill it in.")
    return psycopg.connect(url, row_factory=dict_row)


def init_schema(conn: psycopg.Connection) -> str:
    """
    First run: create everything. Later runs: the tables already hold data, so only the
    rerunnable files run: migrations.sql (new columns) and web.sql (views). Returns what it did.
    """
    exists = conn.execute("SELECT to_regclass('public.players') IS NOT NULL AS e").fetchone()["e"]
    files = SCHEMA_FILES[1:] if exists else SCHEMA_FILES
    for name in files:
        with open(os.path.join(DB_DIR, name)) as f:
            conn.execute(f.read())
    conn.commit()
    return "updated views" if exists else "created"


# ---------------------------------------------------------------------------
# Name normalization (used for matching transaction names to players)
# ---------------------------------------------------------------------------

def norm_name(name: str) -> str:
    """'José Ramírez Jr.' -> 'jose ramirez'."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[.,'’]", "", s.lower())
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------------
# Reference lookups
# ---------------------------------------------------------------------------

def get_or_create_source(conn, name: str, base_url: str, priority: int = 50, rate_limit_sec: float = 3.0) -> int:
    row = conn.execute(
        """INSERT INTO sources (name, base_url, priority, rate_limit_sec, robots_checked)
           VALUES (%s, %s, %s, %s, true)
           ON CONFLICT (name) DO UPDATE SET base_url = EXCLUDED.base_url
           RETURNING id""", (name, base_url, priority, rate_limit_sec)).fetchone()
    return row["id"]


def get_or_create_league(conn, name: str, org: str, level: str, abbrev: str | None = None,
                         website: str | None = None) -> int:
    row = conn.execute(
        """INSERT INTO leagues (name, abbrev, org, level, website) VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (name, level) DO UPDATE SET website = COALESCE(EXCLUDED.website, leagues.website)
           RETURNING id""", (name, abbrev, org, level, website)).fetchone()
    return row["id"]


def mark_league_complete(conn, league_id: int):
    conn.execute("UPDATE leagues SET complete = true WHERE id = %s", (league_id,))


def get_or_create_team(conn, name: str, org: str, site_url: str | None = None) -> int:
    row = conn.execute(
        """INSERT INTO teams (name, org, site_url) VALUES (%s, %s, %s)
           ON CONFLICT (name) DO UPDATE SET site_url = COALESCE(EXCLUDED.site_url, teams.site_url)
           RETURNING id""", (name.strip(), org, site_url)).fetchone()
    return row["id"]


def find_team(conn, name: str) -> Optional[int]:
    """Loose team lookup: exact, then case and hyphen insensitive, then nickname match."""
    if not name:
        return None
    rows = conn.execute("SELECT id, name FROM teams").fetchall()
    key = re.sub(r"[\s\-]+", " ", name.lower()).strip()
    for r in rows:
        if re.sub(r"[\s\-]+", " ", r["name"].lower()).strip() == key:
            return r["id"]
    nick = key.split()[-1]
    hits = [r["id"] for r in rows if r["name"].lower().split()[-1] == nick]
    return hits[0] if len(hits) == 1 else None


def upsert_team_season(conn, team_id: int, season: int, league_id: int, park_id: int | None = None):
    conn.execute(
        """INSERT INTO team_seasons (team_id, season, league_id, park_id) VALUES (%s, %s, %s, %s)
           ON CONFLICT (team_id, season) DO UPDATE
             SET league_id = EXCLUDED.league_id, park_id = COALESCE(EXCLUDED.park_id, team_seasons.park_id)""",
        (team_id, season, league_id, park_id))


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------

def player_by_external(conn, source_id: int, external_id: str) -> Optional[int]:
    row = conn.execute("SELECT player_id FROM player_external_ids WHERE source_id = %s AND external_id = %s",
                       (source_id, external_id)).fetchone()
    return row["player_id"] if row else None


def upsert_player(conn, source_id: int, external_id: str, profile_url: str,
                  first_name: str, last_name: str, **bio) -> int:
    """
    Create or update a player keyed by his ID on a source site. Bio fields only overwrite
    existing values when the new value is not empty, so a sparse page never wipes good data.
    """
    allowed = {"birth_date", "height_in", "weight_lb", "bats", "throws", "hometown_city",
               "hometown_state", "primary_position", "grad_year", "college_team_id"}
    bio = {k: v for k, v in bio.items() if k in allowed and v not in (None, "")}

    pid = player_by_external(conn, source_id, external_id)
    if pid is None:
        cols = ["first_name", "last_name", *bio.keys()]
        vals = [first_name, last_name, *bio.values()]
        pid = conn.execute(
            f"INSERT INTO players ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) RETURNING id",
            vals).fetchone()["id"]
        conn.execute(
            "INSERT INTO player_external_ids (player_id, source_id, external_id, profile_url) VALUES (%s, %s, %s, %s)",
            (pid, source_id, external_id, profile_url))
    else:
        sets = ["updated_at = now()"]
        vals: list = []
        # A full name from a roster beats an abbreviated "J Trimble" from a stats list.
        if first_name and len(first_name) > 1:
            sets += ["first_name = %s", "last_name = %s"]
            vals += [first_name, last_name]
        for k, v in bio.items():
            sets.append(f"{k} = %s")
            vals.append(v)
        conn.execute(f"UPDATE players SET {', '.join(sets)} WHERE id = %s", (*vals, pid))
    return pid


def add_eligibility(conn, player_id: int, rule: str, source_id: int, source_url: str,
                    confirmed: bool = True, notes: str | None = None):
    conn.execute(
        """INSERT INTO eligibility_evidence (player_id, rule, confirmed, source_id, source_url, notes)
           VALUES (%s, %s, %s, %s, %s, %s)
           ON CONFLICT (player_id, rule) DO UPDATE
             SET confirmed = EXCLUDED.confirmed OR eligibility_evidence.confirmed,
                 source_url = EXCLUDED.source_url, verified_at = now()""",
        (player_id, rule, confirmed, source_id, source_url, notes))


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def _upsert_stats(conn, table: str, cols: list[str], key: dict, stats: dict, source_id: int):
    present = [c for c in cols if c in stats]
    names = [*key.keys(), *present, "source_id", "pulled_at"]
    values = [*key.values(), *(stats[c] for c in present), source_id]
    conflict = ", ".join(key.keys())
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in [*present, "source_id"]) + ", pulled_at = now()"
    conn.execute(
        f"""INSERT INTO {table} ({', '.join(names)})
            VALUES ({', '.join(['%s'] * (len(values)))}, now())
            ON CONFLICT ({conflict}) DO UPDATE SET {updates}""",
        values)


def upsert_batting(conn, player_id, season, team_id, stats, source_id, split="total"):
    _upsert_stats(conn, "batting_stats", BATTING_COLS,
                  {"player_id": player_id, "season": season, "team_id": team_id, "split": split}, stats, source_id)


def upsert_pitching(conn, player_id, season, team_id, stats, source_id, split="total"):
    _upsert_stats(conn, "pitching_stats", PITCHING_COLS,
                  {"player_id": player_id, "season": season, "team_id": team_id, "split": split}, stats, source_id)


def upsert_fielding(conn, player_id, season, team_id, position, stats, source_id):
    _upsert_stats(conn, "fielding_stats", FIELDING_COLS,
                  {"player_id": player_id, "season": season, "team_id": team_id, "position": position},
                  stats, source_id)


BAT_GAME_COLS = ["pa", "ab", "r", "h", "b2", "b3", "hr", "rbi", "bb", "ibb", "so", "hbp", "sf", "sh", "sb", "cs"]
PIT_GAME_COLS = ["outs", "bf", "h", "r", "er", "hr", "bb", "ibb", "so", "hbp", "wp", "bk", "pitches", "strikes"]


def upsert_game(conn, g, player_id: int, season: int, team_id, source_id: int):
    """One game log row. g is a presto.GameRow."""
    table, cols = ("batting_games", BAT_GAME_COLS) if g.group == "h" else ("pitching_games", PIT_GAME_COLS)
    base = {"player_id": player_id, "season": season, "game_date": g.game_date, "game_no": g.game_no,
            "team_id": team_id, "opponent": g.opponent, "home_away": g.home_away, "result": g.result}
    if g.group == "p":
        base.update({"started": g.started, "decision": g.decision})
    stats = {c: g.stats[c] for c in cols if c in g.stats}
    names = [*base.keys(), *stats.keys(), "source_id"]
    values = [*base.values(), *stats.values(), source_id]
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in names if c not in ("player_id", "game_date", "game_no"))
    conn.execute(
        f"""INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join(['%s'] * len(values))})
            ON CONFLICT (player_id, game_date, game_no) DO UPDATE SET {updates}, pulled_at = now()""",
        values)


def has_games(conn, player_id: int, season: int) -> bool:
    row = conn.execute(
        """SELECT EXISTS (SELECT 1 FROM batting_games WHERE player_id = %s AND season = %s)
               OR EXISTS (SELECT 1 FROM pitching_games WHERE player_id = %s AND season = %s) AS has""",
        (player_id, season, player_id, season)).fetchone()
    return bool(row["has"])


def single_team(conn, player_id: int, season: int):
    """The player's team that season, or None if he played for more than one."""
    rows = conn.execute(
        """SELECT DISTINCT team_id FROM batting_stats WHERE player_id = %s AND season = %s
           UNION SELECT DISTINCT team_id FROM pitching_stats WHERE player_id = %s AND season = %s""",
        (player_id, season, player_id, season)).fetchall()
    return rows[0]["team_id"] if len(rows) == 1 else None


# ---------------------------------------------------------------------------
# Transactions and status
# ---------------------------------------------------------------------------

def insert_transaction(conn, *, player_id, raw_name, txn_date, txn, status_effect, team_name,
                       counterparty, from_team_id, to_team_id, raw_text, source_id, source_url) -> bool:
    row = conn.execute(
        """INSERT INTO transactions (player_id, raw_name, txn_date, txn, status_effect, team_name, counterparty,
                                     from_team_id, to_team_id, raw_text, source_id, source_url)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (raw_name, txn_date, txn, source_id) DO UPDATE
             SET player_id = COALESCE(transactions.player_id, EXCLUDED.player_id)
           RETURNING (xmax = 0) AS inserted""",
        (player_id, raw_name, txn_date, txn, status_effect, team_name, counterparty,
         from_team_id, to_team_id, raw_text, source_id, source_url)).fetchone()
    return bool(row["inserted"])


def name_index(conn) -> dict[str, list[dict]]:
    """normalized full name -> [{id, teams}] for matching transaction lines to players."""
    rows = conn.execute(
        """SELECT p.id, p.first_name, p.last_name,
                  ARRAY(SELECT DISTINCT t.name FROM batting_stats b JOIN teams t ON t.id = b.team_id WHERE b.player_id = p.id
                        UNION
                        SELECT DISTINCT t.name FROM pitching_stats s JOIN teams t ON t.id = s.team_id WHERE s.player_id = p.id) AS teams
           FROM players p""").fetchall()
    idx: dict[str, list[dict]] = {}
    for r in rows:
        idx.setdefault(norm_name(f"{r['first_name']} {r['last_name']}"), []).append(r)
        # Also index "j trimble" style keys so abbreviated names can still match within a team.
        if r["first_name"]:
            idx.setdefault(norm_name(f"{r['first_name'][0]} {r['last_name']}"), []).append(r)
    return idx


def match_player(idx: dict, name: str, team_hint: Iterable[str] = ()) -> Optional[int]:
    """Match a printed name to one player. Uses the team(s) on the line to break ties. None if unsure."""
    if not name:
        return None
    hints = {h.lower() for h in team_hint if h}
    for key in (norm_name(name), norm_name(f"{name.split()[0][0]} {name.split()[-1]}") if " " in name else None):
        if not key or key not in idx:
            continue
        cands = {c["id"]: c for c in idx[key]}.values()
        cands = list(cands)
        if len(cands) == 1 and key == norm_name(name):
            return cands[0]["id"]
        on_team = [c for c in cands if hints & {t.lower() for t in (c["teams"] or [])}]
        if len(on_team) == 1:
            return on_team[0]["id"]
    return None


def rebuild_status(conn, target_season: int) -> int:
    """Recompute every player's status for the upcoming season. The rules live in web.sql (rebuild_status)."""
    return conn.execute("SELECT rebuild_status(%s) AS n", (target_season,)).fetchone()["n"]


# ---------------------------------------------------------------------------
# Run logging
# ---------------------------------------------------------------------------

@contextmanager
def scrape_run(conn, source_id: int):
    run_id = conn.execute("INSERT INTO scrape_runs (source_id, status) VALUES (%s, 'running') RETURNING id",
                          (source_id,)).fetchone()["id"]
    conn.commit()
    tally = {"rows": 0, "errors": []}
    try:
        yield tally
        status = "partial" if tally["errors"] else "ok"
        conn.commit()
    except Exception as e:
        conn.rollback()
        tally["errors"].append(repr(e))
        status = "failed"
        raise
    finally:
        conn.execute(
            """UPDATE scrape_runs SET finished_at = now(), status = %s, rows_upserted = %s, error_log = %s
               WHERE id = %s""",
            (status, tally["rows"], "\n".join(tally["errors"])[:20000] or None, run_id))
        conn.commit()
