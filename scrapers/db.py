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
SCHEMA_FILES = ["schema.sql", "web.sql"]      # supabase.sql is run separately in the Supabase SQL editor

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


def init_schema(conn: psycopg.Connection):
    for name in SCHEMA_FILES:
        with open(os.path.join(DB_DIR, name)) as f:
            conn.execute(f.read())
    conn.commit()


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


REBUILD_STATUS_SQL = """
-- Status is for ONE upcoming season (the target season). Only that season's transaction report
-- (October of the prior year onward) can confirm a player as signed for it.
--
--   * Latest move in the target season's report decides.
--   * With no move in that report, a few earlier moves still stand because nothing has
--     undone them yet: a release (free agent), a contract sold to an MLB club (affiliated),
--     a retirement. An earlier signing or trade does NOT carry over: a roster spot last
--     season says nothing about next season, so the player is unconfirmed.
--   * No moves at all: unconfirmed.
WITH latest_txn AS (
    SELECT DISTINCT ON (player_id)
           player_id, id, txn_date, status_effect, to_team_id,
           EXTRACT(YEAR FROM txn_date)::int
             + CASE WHEN EXTRACT(MONTH FROM txn_date) >= 10 THEN 1 ELSE 0 END AS txn_season
    FROM transactions
    WHERE player_id IS NOT NULL AND status_effect IS NOT NULL
    ORDER BY player_id, txn_date DESC, id DESC
),
resolved AS (
    SELECT p.id AS player_id,
           CASE WHEN lt.txn_season >= %(target)s THEN true
                WHEN lt.status_effect IN ('free_agent', 'signed_affiliated', 'retired') THEN true
                ELSE false END AS known,
           lt.id, lt.txn_date, lt.status_effect, lt.to_team_id
    FROM players p
    LEFT JOIN latest_txn lt ON lt.player_id = p.id
)
INSERT INTO player_status (player_id, status, current_team_id, status_date, for_season,
                           last_txn_id, unconfirmed, updated_at)
SELECT r.player_id,
       CASE WHEN known THEN r.status_effect ELSE 'unknown'::signing_status END,
       CASE WHEN known AND r.status_effect IN ('signed_independent', 'signed_affiliated') THEN r.to_team_id END,
       CASE WHEN known THEN r.txn_date END,
       %(target)s,
       CASE WHEN known THEN r.id END,
       NOT known,
       now()
FROM resolved r
ON CONFLICT (player_id) DO UPDATE
   SET status = EXCLUDED.status,
       current_team_id = EXCLUDED.current_team_id,
       status_date = EXCLUDED.status_date,
       for_season = EXCLUDED.for_season,
       last_txn_id = EXCLUDED.last_txn_id,
       unconfirmed = EXCLUDED.unconfirmed,
       updated_at = now()
   -- Never overwrite a status another process set from better evidence (college return list).
   WHERE player_status.status <> 'returning_college'
"""


def rebuild_status(conn, target_season: int) -> int:
    """Recompute every player's status for the upcoming season."""
    cur = conn.execute(REBUILD_STATUS_SQL, {"target": target_season})
    return cur.rowcount


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
