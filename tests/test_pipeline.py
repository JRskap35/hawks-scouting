"""
End to end test: PrestoSports style pages -> parsers -> Postgres -> views.

Needs a throwaway Postgres database in TEST_DATABASE_URL. The test drops and recreates
the public schema, so never point it at the real database.

    TEST_DATABASE_URL=postgresql://localhost/scouting_test pytest -q
"""

import os
from datetime import date

import psycopg
import pytest
from psycopg.rows import dict_row

from scrapers import db, pioneer, presto

TEST_DB = os.getenv("TEST_DATABASE_URL")
SITE = "https://www.pioneerleague.com"
S = "/sports/bsb/2026"


def p(slug, label):
    return f'<a href="{S}/players/{slug}">{label}</a>'


def t(slug, name):
    return f'<a href="{S}/teams/{slug}">{name}</a>'


TEAMS = {
    "idahofallschukars": "Idaho Falls Chukars",
    "billingsmustangs": "Billings Mustangs",
    "ogdenraptors": "Ogden Raptors",
    "boisehawks": "Boise Hawks",
    "yubasutterfreebirds": "Yuba-Sutter Freebirds",
}


def table(headers, rows):
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def page(inner, extra=""):
    return f"<html><body><nav><a href='/'>Home</a></nav><main>{extra}{inner}</main></body></html>"


TABS_H = ('<div class="tabs"><a href="?pos=h&r=0">Hitting</a> <a href="?pos=h&r=0&view=extended">Extended</a> '
          '<a href="?pos=p&r=0">Pitching</a> <a href="?pos=f&r=0">Fielding</a></div>')

# Default hitting view. Note the blank team header, as on the real 2024 page.
HIT_1 = page(table(
    ["Rk", "Name", "", "g", "ab", "r", "h", "2b", "3b", "hr", "rbi", "bb", "k", "sb", "cs", "avg", "obp", "slg"],
    [
        [1, p("jaketrimble7k2", "J Trimble"), t("idahofallschukars", "Idaho Falls Chukars"),
         88, 340, 121, 120, 30, 2, 22, 90, 45, 60, 13, "-", ".353", ".440", ".641"],
        [2, p("alexshaver9q1", "A Shaver"), t("billingsmustangs", "Billings Mustangs"),
         91, 360, 120, 115, 25, 4, 18, 70, 40, 75, 35, 5, ".319", ".390", ".561"],
        [3, p("chrissargent3x8", "C Sargent"), t("ogdenraptors", "Ogden Raptors"),
         60, 230, 50, 80, 15, 0, 20, 66, 20, 50, 1, 1, ".348", ".400", ".678"],
        ["", "Totals", "", 239, 930, 291, 315, 70, 6, 60, 226, 105, 185, 49, 6, "", "", ""],
    ]), TABS_H + "<div>Page 1/2</div><a href='?pos=h&r=0&page=2'>2</a>")

HIT_2 = page(table(
    ["Rk", "Name", "", "g", "ab", "r", "h", "2b", "3b", "hr", "rbi", "bb", "k", "sb", "cs", "avg", "obp", "slg"],
    [[4, p("chasehanson5m4", "C Hanson"), t("billingsmustangs", "Billings Mustangs"),
      40, 105, 15, 28, 6, 0, 3, 18, 10, 30, 2, 0, ".267", ".330", ".410"]]), TABS_H + "<div>Page 2/2</div>")

HIT_EXT = page(table(
    ["Rk", "Name", "Team", "g", "hbp", "sf", "sh", "tb", "pa", "gdp"],
    [
        [1, p("jaketrimble7k2", "J Trimble"), t("idahofallschukars", "Idaho Falls Chukars"), 88, 8, 4, 0, 220, 397, 6],
        [2, p("alexshaver9q1", "A Shaver"), t("billingsmustangs", "Billings Mustangs"), 91, 5, 3, 1, 202, 409, 4],
        [3, p("chrissargent3x8", "C Sargent"), t("ogdenraptors", "Ogden Raptors"), 60, 2, 2, 0, 155, 256, 3],
        [4, p("chasehanson5m4", "C Hanson"), t("billingsmustangs", "Billings Mustangs"), 40, 2, 1, 0, 43, 118, 1],
    ]), TABS_H)

PIT = page(table(
    ["Rk", "Name", "Team", "app", "gs", "w", "l", "sv", "ip", "h", "r", "er", "bb", "k", "hr", "era", "whip"],
    [
        [1, p("noahstarter1a1", "N Starter"), t("boisehawks", "Boise Hawks"), 18, 17, 9, 4, 0, "101.2", 90, 40, 35, 25, 110, 8, "3.10", "1.13"],
        [2, p("ryanreliever2b2", "R Reliever"), t("boisehawks", "Boise Hawks"), 40, "-", 4, 3, 12, "45.1", 38, 15, 14, 18, 60, 3, "2.78", "1.24"],
        [3, p("samswing3c3", "S Swing"), t("ogdenraptors", "Ogden Raptors"), 20, 9, 5, 5, 1, "70.0", 72, 35, 31, 22, 66, 7, "3.99", "1.34"],
        [4, p("chasehanson5m4", "C Hanson"), t("billingsmustangs", "Billings Mustangs"), 12, 4, 2, 2, 0, "30.1", 31, 15, 14, 12, 28, 3, "4.15", "1.42"],
        [5, p("christianwomble4d4", "C Womble"), t("yubasutterfreebirds", "Yuba-Sutter Freebirds"), 25, 0, 1, 2, 3, "28.0", 30, 18, 16, 15, 30, 4, "5.14", "1.61"],
    ]))

FLD = page(table(
    ["Rk", "Name", "Team", "pos", "g", "po", "a", "e", "dp", "fpct"],
    [
        [1, p("jaketrimble7k2", "J Trimble"), t("idahofallschukars", "Idaho Falls Chukars"), "SS", 85, 120, 250, 12, 50, ".969"],
        [2, p("alexshaver9q1", "A Shaver"), t("billingsmustangs", "Billings Mustangs"), "CF", 90, 210, 6, 3, 1, ".986"],
    ]))


def roster(rows):
    return page(table(["No.", "Name", "Pos.", "B/T", "Ht.", "Wt.", "Hometown", "College"], rows))


ROSTERS = {
    "idahofallschukars": roster([[7, p("jaketrimble7k2", "Jake Trimble"), "INF", "R/R", "6-1", "190", "Meridian, Idaho", "Boise State"]]),
    "billingsmustangs": roster([
        [2, p("alexshaver9q1", "Alex Shaver"), "OF", "L/L", "5-11", "180", "Tulsa, Okla.", "Oral Roberts"],
        [33, p("chasehanson5m4", "Chase Hanson"), "OF/RHP", "R/R", "6-3", "205", "Fresno, Calif.", "Fresno State"],
    ]),
    "ogdenraptors": roster([
        [24, p("chrissargent3x8", "Chris Sargent"), "1B", "R/R", "6-4", "225", "Reno, Nev.", "Nevada"],
        [41, p("samswing3c3", "Sam Swing"), "RHP", "R/R", "6-2", "200", "Provo, Utah", "BYU"],
    ]),
    "boisehawks": roster([
        [19, p("noahstarter1a1", "Noah Starter"), "LHP", "L/L", "6-5", "215", "Spokane, Wash.", "Gonzaga"],
        [52, p("ryanreliever2b2", "Ryan Reliever"), "RHP", "R/R", "6-0", "195", "Nampa, Idaho", "College of Idaho"],
    ]),
    "yubasutterfreebirds": roster([
        [30, p("christianwomble4d4", "Christian Womble"), "RHP", "R/R", "6-2", "210", "Sacramento, Calif.", "Sacramento State"],
    ]),
}

TXN_PAGE = page("""
<h2>PBL Player Transactions</h2>
<p>August 30</p>
<p>Yuba-Sutter Freebirds</p>
<ul><li>Placed Christian Womble on Irrevocable waivers</li></ul>
<p>August 26</p>
<p>Ogden Raptors</p>
<ul><li>Sold the contract of Chris Sargent to the San Diego Padres</li></ul>
<p>July 1</p>
<p>Billings Mustangs</p>
<ul><li>Placed Alex Shaver on the Injury List (Injury 10 Days)</li>
<li>Signed Jordan Unknown to their 2026 roster</li></ul>
<p>June 2</p>
<p>Billings Mustangs</p>
<ul><li>Signed Alex Shaver to their 2026 roster</li></ul>
""")

# The upcoming season's report: moves made from October 2026 on.
TXN_2027 = page("""
<h2>PBL Player Transactions</h2>
<p>November 10</p>
<p>Idaho Falls Chukars</p>
<ul><li>Signed Jake Trimble to their 2027 roster</li></ul>
<p>October 20</p>
<p>Billings Mustangs</p>
<ul><li>Placed Chase Hanson on Irrevocable waivers</li></ul>
""")


GAMELOG_STARTER = page(table(
    ["Date", "Opponent", "Score", "gs", "dec", "ip", "h", "r", "er", "bb", "k", "hr", "np"],
    [
        ["Jun 3", "at Ogden Raptors", "W, 5-2", 1, "W", "6.0", 4, 2, 2, 1, 8, 0, 92],
        ["Jun 9", "vs. Missoula PaddleHeads", "L, 1-3", 1, "L", "5.2", 6, 3, 3, 2, 5, 1, 101],
        ["Totals", "", "", 2, "", "11.2", 10, 5, 5, 3, 13, 1, 193],
    ]))

GAMELOG_HANSON = page(
    "<h3>Hitting</h3>" + table(
        ["Date", "Opponent", "Score", "ab", "r", "h", "2b", "3b", "hr", "rbi", "bb", "k", "sb"],
        [
            ["Jul 4", "vs. Boise Hawks", "W, 4-3", 4, 1, 2, 1, 0, 0, 1, 0, 1, 0],
            ["Jul 4", "vs. Boise Hawks", "L, 2-6", 3, 0, 1, 0, 0, 1, 2, 1, 0, 1],
        ])
    + "<h3>Pitching</h3>" + table(
        ["Date", "Opponent", "Score", "gs", "dec", "ip", "h", "r", "er", "bb", "k", "hr"],
        [["Jul 8", "at Great Falls Voyagers", "W, 9-4", 0, "S", "1.1", 0, 0, 0, 0, 2, 0]]))


class FakeHttp:
    def __init__(self):
        base = f"{SITE}{S}/players"
        self.pages = {
            f"{base}?pos=h&r=0": HIT_1,
            f"{base}?pos=h&r=0&page=2": HIT_2,
            f"{base}?pos=h&r=0&view=extended": HIT_EXT,
            f"{base}?pos=p&r=0": PIT,
            f"{base}?pos=f&r=0": FLD,
            f"{SITE}/players/transactions/2026_Transactions": TXN_PAGE,
            f"{SITE}/players/transactions/2027_Transactions": TXN_2027,
        }
        for slug, html in ROSTERS.items():
            self.pages[f"{SITE}{S}/teams/{slug}?view=roster"] = html
        self.pages[f"{SITE}{S}/players/noahstarter1a1?view=gamelog"] = GAMELOG_STARTER
        self.pages[f"{SITE}{S}/players/chasehanson5m4?view=gamelog"] = GAMELOG_HANSON
        self.requested = []

    def get_text(self, url, **_):
        self.requested.append(url)
        if "view=gamelog" in url and url not in self.pages:
            return page("<p>No game log available.</p>")
        if url not in self.pages:
            raise RuntimeError(f"unexpected url {url}")
        return self.pages[url]


# ---------------------------------------------------------------------------
# Parser unit tests (no database)
# ---------------------------------------------------------------------------

def test_innings_to_outs():
    assert presto.innings_to_outs("101.2") == 305
    assert presto.innings_to_outs("45.1") == 136
    assert presto.innings_to_outs("70.0") == 210
    assert presto.innings_to_outs("-") == 0
    assert presto.innings_to_outs("4.5") is None      # not valid baseball notation


def test_stat_table_parsing_and_merge():
    rows = presto.parse_stat_tables(HIT_1, "h", SITE)
    assert len(rows) == 3                              # totals row skipped
    trimble = rows[0]
    assert trimble.team_name == "Idaho Falls Chukars"  # found by link despite the blank header
    assert trimble.stats["so"] == 60 and trimble.stats["cs"] == 0 and trimble.stats["b2"] == 30
    merged = presto.merge_rows(rows, presto.parse_stat_tables(HIT_EXT, "h", SITE))
    assert next(r for r in merged if r.player_label == "J Trimble").stats["pa"] == 397


def test_navigation_helpers():
    assert presto.discover_views(HIT_1, "h") == ["", "extended"]
    assert presto.page_count(HIT_1) == 2


def test_gamelog_parsing():
    games = presto.parse_gamelog(GAMELOG_STARTER, 2026)
    assert len(games) == 2                                   # totals row skipped
    g = games[0]
    assert (g.group, g.game_date, g.opponent, g.home_away, g.decision, g.started) == \
        ("p", date(2026, 6, 3), "Ogden Raptors", "A", "W", True)
    assert g.stats["outs"] == 18 and g.stats["so"] == 8 and g.stats["pitches"] == 92
    assert games[1].stats["outs"] == 17 and games[1].home_away == "H"

    both = presto.parse_gamelog(GAMELOG_HANSON, 2026)
    hit = [x for x in both if x.group == "h"]
    pit = [x for x in both if x.group == "p"]
    assert [x.game_no for x in hit] == [1, 2]                # doubleheader
    assert hit[1].stats["hr"] == 1 and hit[1].stats["sb"] == 1
    assert pit[0].started is False and pit[0].decision == "S" and pit[0].stats["outs"] == 4


def test_roster_parsing():
    rows = presto.parse_roster(ROSTERS["billingsmustangs"], SITE)
    hanson = rows[1]
    assert hanson.name == "Chase Hanson"
    assert hanson.fields["bats"] == "R" and hanson.fields["height_in"] == 75 and hanson.fields["weight_lb"] == 205


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------

@pytest.fixture
def conn():
    if not TEST_DB:
        pytest.skip("TEST_DATABASE_URL not set")
    c = psycopg.connect(TEST_DB, row_factory=dict_row)
    c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    c.commit()
    db.init_schema(c)
    yield c
    c.close()


def test_full_pioneer_run(conn):
    """First load: 2026 stats and bios, the 2026 and 2027 reports, statuses for 2027."""
    http = FakeHttp()
    result = pioneer.run(conn, http, 2026, txn_seasons=(2026, 2027), target_season=2027)
    assert result["errors"] == []
    assert result["teams"] == 5
    assert result["status_for_season"] == 2027

    # Names came from rosters, bio fields filled in
    trimble = conn.execute("SELECT * FROM players WHERE last_name = 'Trimble'").fetchone()
    assert (trimble["first_name"], trimble["bats"], trimble["height_in"]) == ("Jake", "R", 73)

    # Hitting views merged into one row
    b = conn.execute("SELECT pa, ab, hbp, so FROM batting_stats bs JOIN players p ON p.id = bs.player_id "
                     "WHERE p.last_name = 'Trimble'").fetchone()
    assert b == {"pa": 397, "ab": 340, "hbp": 8, "so": 60}

    # Innings stored as outs
    outs = conn.execute("SELECT outs FROM pitching_stats ps JOIN players p ON p.id = ps.player_id "
                        "WHERE p.last_name = 'Starter'").fetchone()["outs"]
    assert outs == 305

    # Transactions matched, with dates placed in the right calendar year
    assert result["transactions"][2026]["inserted"] == 5
    assert result["transactions"][2027]["inserted"] == 2
    assert any("Jordan Unknown" in u for u in result["transactions"][2026]["unmatched"])

    status = {r["last_name"]: r for r in conn.execute(
        "SELECT p.last_name, s.status, s.status_date, s.unconfirmed, s.for_season, t.name AS team "
        "FROM player_status s JOIN players p ON p.id = s.player_id "
        "LEFT JOIN teams t ON t.id = s.current_team_id").fetchall()}

    # Moves in the 2027 report decide
    assert status["Trimble"]["status"] == "signed_independent"
    assert status["Trimble"]["team"] == "Idaho Falls Chukars"
    assert status["Trimble"]["status_date"] == date(2026, 11, 10)
    assert status["Hanson"]["status"] == "free_agent"
    assert status["Hanson"]["status_date"] == date(2026, 10, 20)

    # 2026 releases and MLB sales still stand
    assert status["Womble"]["status"] == "free_agent"
    assert status["Sargent"]["status"] == "signed_affiliated"
    assert status["Sargent"]["team"] == "San Diego Padres"

    # A 2026 signing or roster spot says nothing about 2027
    assert status["Shaver"]["status"] == "unknown" and status["Shaver"]["unconfirmed"] is True
    assert status["Shaver"]["team"] is None
    assert status["Starter"]["status"] == "unknown"                 # no moves at all
    assert {r["for_season"] for r in status.values()} == {2027}

    # The eligible pool
    pool = {r["last_name"]: r for r in conn.execute("SELECT * FROM eligible_players").fetchall()}
    assert "Sargent" not in pool
    assert pool["Womble"]["can_sign_now"] is True
    assert pool["Hanson"]["can_sign_now"] is True
    assert pool["Trimble"]["can_sign_now"] is False                 # signed for 2027
    assert pool["Shaver"]["unconfirmed"] is True and pool["Shaver"]["can_sign_now"] is False

    # Roles and two way flags
    assert pool["Starter"]["pitcher_role"] == "SP"                  # 17 / 18
    assert pool["Reliever"]["pitcher_role"] == "RP"                 # 0 / 40
    assert pool["Swing"]["pitcher_role"] == "RP"                    # 9 / 20 = 45%
    assert pool["Hanson"]["is_two_way"] is True                     # 118 PA, 30.1 IP
    assert pool["Trimble"]["is_two_way"] is False

    # Rerunning is safe: nothing duplicates
    pioneer.run(conn, http, 2026, txn_seasons=(2026, 2027), target_season=2027)
    assert conn.execute("SELECT count(*) AS n FROM batting_stats").fetchone()["n"] == 4
    assert conn.execute("SELECT count(*) AS n FROM transactions").fetchone()["n"] == 7


def test_web_views(conn):
    pioneer.run(conn, FakeHttp(), 2026, txn_seasons=(2026, 2027), target_season=2027)
    hit = {r["last_name"]: r for r in conn.execute("SELECT * FROM ui_hitters").fetchall()}
    pit = {r["last_name"]: r for r in conn.execute("SELECT * FROM ui_pitchers").fetchall()}
    two = {r["last_name"]: r for r in conn.execute("SELECT * FROM ui_two_way").fetchall()}

    # Who shows where
    assert set(hit) == {"Trimble", "Shaver", "Hanson"}             # Sargent is affiliated, gone
    assert set(pit) == {"Starter", "Reliever", "Swing", "Hanson", "Womble"}
    assert set(two) == {"Hanson"}
    assert two["Hanson"]["teams"] == "Billings Mustangs"

    t = hit["Trimble"]
    assert (t["position_group"], t["status_label"], t["status_team"]) == ("IF", "Signed", "Idaho Falls Chukars")
    assert hit["Shaver"]["status_label"] == "Unconfirmed"
    # Team: 2027 club when signed, otherwise last professional team
    assert t["team"] == "Idaho Falls Chukars"
    assert hit["Shaver"]["team"] == "Billings Mustangs"
    assert pit["Womble"]["team"] == "Yuba-Sutter Freebirds"
    assert hit["Hanson"]["status_label"] == "Free Agent"
    assert hit["Hanson"]["position_group"] == "OF"                 # roster says OF/RHP
    # .353 / (120+45+8)/(340+45+8+4) / (120+30+4+66)/340
    assert float(t["avg"]) == 0.353 and float(t["obp"]) == 0.436 and float(t["slg"]) == 0.647
    assert float(t["k_pct"]) == round(100 * 60 / 397, 1)

    s = pit["Starter"]
    assert float(s["ip"]) == 101.2 and float(s["era"]) == 3.10 and float(s["whip"]) == 1.13
    c = conn.execute("SELECT fip_constant FROM league_fip_constants").fetchone()["fip_constant"]
    # league: ER 110, outs 826 (305+136+210+91+84), HR 25, BB 92, SO 294, HBP 0
    lg_ip = 826 / 3
    expected_c = 9 * 110 / lg_ip - (13 * 25 + 3 * 92 - 2 * 294) / lg_ip
    assert float(c) == pytest.approx(expected_c, abs=0.001)
    expected_fip = (13 * 8 + 3 * 25 - 2 * 110) / (305 / 3) + float(c)
    assert float(s["fip"]) == pytest.approx(expected_fip, abs=0.01)
    assert s["k_pct"] is None                                        # no batters faced published

    # Markers log every change
    conn.execute("INSERT INTO player_markers (player_id, status) VALUES (%s, 'looking_to_sign')", (t["id"],))
    conn.execute("UPDATE player_markers SET status = 'potential' WHERE player_id = %s", (t["id"],))
    conn.execute("DELETE FROM player_markers WHERE player_id = %s", (t["id"],))
    log = [r["status"] for r in conn.execute(
        "SELECT status FROM player_marker_log WHERE player_id = %s ORDER BY id", (t["id"],)).fetchall()]
    assert log == ["looking_to_sign", "potential", None]

    f = conn.execute("SELECT * FROM ui_fielding_seasons WHERE position = 'SS'").fetchone()
    assert float(f["fpct"]) == 0.969


def test_gamelogs_load_and_finished_seasons_skip(conn):
    http = FakeHttp()
    result = pioneer.run(conn, http, 2026, txn_seasons=(), target_season=2027)
    gl = result["gamelogs"]
    assert gl["players"] == 8 and gl["games"] == 5 and gl["empty"] == 6     # Hanson hits and pitches: 8 players

    games = conn.execute("SELECT * FROM ui_pitching_games g JOIN players p ON p.id = g.player_id "
                         "WHERE p.last_name = 'Starter' ORDER BY game_date").fetchall()
    assert [float(g["ip"]) for g in games] == [6.0, 5.2]
    assert games[0]["team"] == "Boise Hawks" and games[0]["started"] is True and games[0]["pitches"] == 92

    s = conn.execute("SELECT games_logged FROM ui_pitching_seasons s JOIN players p ON p.id = s.player_id "
                     "WHERE p.last_name = 'Starter'").fetchone()
    assert s["games_logged"] == 2
    dh = conn.execute("SELECT game_no, hr FROM ui_batting_games g JOIN players p ON p.id = g.player_id "
                      "WHERE p.last_name = 'Hanson' ORDER BY game_no").fetchall()
    assert [(r["game_no"], r["hr"]) for r in dh] == [(1, 0), (2, 1)]

    # 2026 is finished (it is November), so players with logs are not fetched again
    again = pioneer.run(conn, http, 2026, txn_seasons=(), target_season=2027)["gamelogs"]
    assert again["skipped"] == 2 and again["fetched"] == 6
    assert conn.execute("SELECT count(*) AS n FROM pitching_games").fetchone()["n"] == 3


def test_refresh_reads_only_the_upcoming_report(conn):
    http = FakeHttp()
    pioneer.run(conn, http, 2026, txn_seasons=(2027,), target_season=2027)
    txn_pages = [u for u in http.requested if "transactions" in u]
    assert txn_pages == [f"{SITE}/players/transactions/2027_Transactions"]


def test_weighted_role_and_overrides(conn):
    """Last three seasons weighted 3/2/1. A long time starter who relieved last year stays a starter."""
    src = db.get_or_create_source(conn, "test", "x")
    team = db.get_or_create_team(conn, "Test Club", "independent")
    pid = db.upsert_player(conn, src, "vet1", "x", "Vet", "Arm")
    for season, g, gs in [(2024, 20, 20), (2025, 20, 18), (2026, 25, 4)]:
        db.upsert_pitching(conn, pid, season, team, {"g": g, "gs": gs, "outs": 300}, src)
    # weighted = (3*4 + 2*18 + 1*20) / (3*25 + 2*20 + 1*20) = 68 / 135 = 0.504
    r = conn.execute("SELECT * FROM pitcher_role WHERE player_id = %s", (pid,)).fetchone()
    assert float(r["weighted_gs_share"]) == pytest.approx(0.504, abs=0.001)
    assert r["role"] == "SP"

    conn.execute("UPDATE players SET role_override = 'RP', two_way_override = true WHERE id = %s", (pid,))
    r = conn.execute("SELECT role, role_overridden FROM pitcher_role WHERE player_id = %s", (pid,)).fetchone()
    assert r == {"role": "RP", "role_overridden": True}
    assert conn.execute("SELECT is_two_way FROM two_way_status WHERE player_id = %s", (pid,)).fetchone()["is_two_way"]


def test_report_season_routing():
    assert pioneer.transaction_season(date(2026, 11, 18)) == 2027    # offseason moves go to next year's report
    assert pioneer.transaction_season(date(2026, 7, 1)) == 2026
    assert pioneer.stats_season(date(2027, 2, 1)) == 2026

    class Recorder:
        def __init__(self):
            self.urls = []

        def get_text(self, url, **_):
            self.urls.append(url)
            raise RuntimeError("404")

    rec = Recorder()
    with pytest.raises(RuntimeError):
        pioneer.fetch_report(rec, pioneer.PIONEER, 2026, today=date(2026, 11, 18))
    assert rec.urls == [f"{SITE}/players/transactions/2026_Transactions"]   # never the live page for a past season

    rec = Recorder()
    with pytest.raises(RuntimeError):
        pioneer.fetch_report(rec, pioneer.PIONEER, 2027, today=date(2026, 11, 18))
    assert rec.urls[1:] == list(pioneer.PIONEER.transactions_current)
