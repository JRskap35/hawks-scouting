"""
Staff status edits from the site: set_player_status, the history view, and how edits
interact with pasted league transactions.
"""

import json
import os

import psycopg
import pytest
from psycopg.rows import dict_row

from scrapers import bref, db, pioneer
from tests.test_bref import FakeHttp

TEST_DB = os.getenv("TEST_DATABASE_URL")


@pytest.fixture
def conn():
    if not TEST_DB:
        pytest.skip("TEST_DATABASE_URL not set")
    c = psycopg.connect(TEST_DB, row_factory=dict_row)
    c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    c.commit()
    db.init_schema(c)
    bref.load_league_season(c, FakeHttp(), bref.PIONEER, 2026, {"rows": 0, "errors": []})
    db.rebuild_status(c, pioneer.transaction_season())
    c.commit()
    yield c
    c.close()


def player(conn, last):
    return conn.execute("SELECT * FROM ui_players WHERE last_name = %s", (last,)).fetchone()


def test_staff_edit_sets_status_and_history(conn):
    staff_id = "00000000-0000-0000-0000-00000000abcd"
    conn.execute("INSERT INTO staff (user_id, full_name) VALUES (%s, 'Joe')", (staff_id,))
    b = player(conn, "Bardowell")
    assert b["status_label"] == "Unconfirmed"

    # As the site calls it: a signed in user's request claims
    conn.execute("SELECT set_config('request.jwt.claims', %s, true)",
                 (json.dumps({"role": "authenticated", "sub": staff_id}),))
    conn.execute("SELECT set_player_status(%s, 'free_agent', NULL, 'Released at season end, agent confirmed')", (b["id"],))
    b = player(conn, "Bardowell")
    assert (b["status_label"], b["status_by_staff"], b["status_set_by"]) == ("Free Agent", True, "Joe")
    boise_today = conn.execute("SELECT boise_today() AS d").fetchone()["d"]
    assert b["status_note"].startswith("Released") and b["status_date"] == boise_today
    assert b["can_sign_now"] is True

    conn.execute("SELECT set_player_status(%s, 'signed_independent', 'Ogden Raptors', NULL)", (b["id"],))
    b = player(conn, "Bardowell")
    assert (b["status_label"], b["status_team"]) == ("Signed", "Ogden Raptors")

    # Same day, changed back: the edit entered last wins
    conn.execute("SELECT set_player_status(%s, 'free_agent', NULL, NULL)", (b["id"],))
    assert player(conn, "Bardowell")["status_label"] == "Free Agent"
    conn.execute("SELECT set_player_status(%s, 'unknown', NULL, NULL)", (b["id"],))
    assert player(conn, "Bardowell")["status_label"] == "Unconfirmed"

    hist = conn.execute("SELECT * FROM ui_player_transactions WHERE player_id = %s ORDER BY pulled_at DESC",
                        (b["id"],)).fetchall()
    assert len(hist) == 3 and all(h["by_staff"] and h["entered_by_name"] == "Joe" for h in hist)


def test_signed_out_visitor_cannot_edit(conn):
    b = player(conn, "Bardowell")
    conn.execute("SELECT set_config('request.jwt.claims', %s, true)", (json.dumps({"role": "anon"}),))
    with pytest.raises(psycopg.errors.RaiseException, match="Sign in"):
        conn.execute("SELECT set_player_status(%s, 'free_agent', NULL, NULL)", (b["id"],))
    conn.rollback()


def test_signed_needs_a_team(conn):
    b = player(conn, "Bardowell")
    with pytest.raises(psycopg.errors.RaiseException, match="team"):
        conn.execute("SELECT set_player_status(%s, 'signed_independent', '  ', NULL)", (b["id"],))
    conn.rollback()


def test_edit_holds_until_a_newer_league_move(conn):
    tally = {"rows": 0, "errors": []}
    b = player(conn, "Bardowell")
    conn.execute("SELECT set_player_status(%s, 'free_agent', NULL, NULL)", (b["id"],))

    # An older league move pasted later does not override today's edit
    older = "November 10\nLong Beach Coast\nSigned Matthew Bardowell to their 2027 roster\n"
    pioneer.load_transactions_text(conn, older, 2027, tally, label="paste")
    db.rebuild_status(conn, 2027)
    assert player(conn, "Bardowell")["status_label"] == "Free Agent"

    # A newer league move does
    newer = "December 2\nGreat Falls Voyagers\nSigned Matthew Bardowell to their 2027 roster\n"
    pioneer.load_transactions_text(conn, newer, 2027, tally, label="paste")
    db.rebuild_status(conn, 2027)
    b = player(conn, "Bardowell")
    assert (b["status_label"], b["status_team"], b["status_by_staff"]) == ("Signed", "Great Falls Voyagers", False)
