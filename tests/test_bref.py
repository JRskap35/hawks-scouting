"""
Baseball Reference scraper and pasted transactions, end to end.

The fixture pages copy the layouts read from the live site on 2026-11-18 (table ids,
header labels, the unlabeled fielding position column, comment wrapped tables).
"""

import os
from datetime import date

import psycopg
import pytest
from psycopg.rows import dict_row

from scrapers import bref, db, pioneer

TEST_DB = os.getenv("TEST_DATABASE_URL")
B = bref.BASE


def a_player(pid, name):
    return f'<a href="/register/player.fcgi?id={pid}">{name}</a>'


def a_team(tid, name):
    return f'<a href="/register/team.cgi?id={tid}">{name}</a>'


def table(tid, headers, rows, comment=False):
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    html = f'<table id="{tid}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'
    return f"<!-- {html} -->" if comment else html


LEAGUE = ('<html><head><title>Pioneer League (Independent) Encyclopedia</title></head><body>'
          '<a href="/register/league.cgi?id=aaa25">2025</a> <a href="/register/league.cgi?id=bbb26">2026</a></body></html>')
SEASON = (f'<html><body>{a_team("lbc26", "Long Beach Coast")} {a_team("bh26", "Boise Hawks")}</body></html>')

BAT_H = ["Rk", "Name", "Age", "G", "PA", "AB", "R", "H", "2B", "3B", "HR", "RBI", "SB", "CS", "BB", "SO",
         "BA", "OBP", "SLG", "OPS", "TB", "GDP", "HBP", "SH", "SF", "IBB", "Notes"]
PIT_H = ["Rk", "Name", "Age", "W", "L", "W-L%", "ERA", "G", "GS", "GF", "CG", "SHO", "SV", "IP", "H", "R", "ER",
         "HR", "BB", "IBB", "SO", "HBP", "BK", "WP", "BF", "WHIP", "H9", "HR9", "BB9", "SO9", "SO/W", "Notes"]
ROS_H = ["Name", "Age", "B", "T", "Ht", "Wt", "DoB", "Birthplace", "Stint", "From", "To"]


def team_page(title, bat, pit, roster):
    return (f"<html><head><title>2026 {title} Statistics | Baseball-Reference.com</title></head><body>"
            + table("team_batting", BAT_H, bat) + table("team_pitching", PIT_H, pit)
            + table("standard_roster", ROS_H, roster, comment=True) + "</body></html>")


LBC = team_page("Long Beach Coast",
    bat=[[1, a_player("bardow000mat", "Matthew Bardowell"), 24, 81, 379, 311, 65, 112, 25, 2, 13, 83, 4, 2, 49, 72,
          ".360", ".463", ".595", "1.058", 185, 6, 14, 0, 5, 1, ""],
         ["", "Team Totals", "", 96, 3500, 3000, 500, 900, 180, 20, 90, 450, 80, 30, 350, 700, "", "", "", "", "", "", "", "", "", "", ""]],
    pit=[[1, a_player("bautis000nic", "Nick Bautista*"), 24, 6, 3, ".667", "4.74", 18, 14, 0, 0, 0, 0, "79.2", 86, 49, 42,
          10, 41, 1, 81, 3, 2, 6, 360, "1.594", "", "", "", "", "", ""]],
    roster=[[a_player("bardow000mat", "Matthew Bardowell"), 24, "R", "R", "6' 4\"", 245, "Apr 13, 2002", "Bell, CA, US", "", "", ""],
            [a_player("bautis000nic", "Nick Bautista"), 24, "L", "L", "6' 3\"", 200, "Feb 22, 2002", "Monterey Park, CA, US", "", "", ""]])

BH = team_page("Boise Hawks",
    bat=[[1, a_player("grad--000tom", "Tom Grad"), 22, 30, 110, 98, 12, 30, 6, 0, 2, 14, 1, 0, 9, 25,
          ".306", "", "", "", "", 1, 2, 0, 1, 0, ""]],
    pit=[],
    roster=[[a_player("grad--000tom", "Tom Grad"), 22, "S", "R", "5' 11\"", 185, "Mar 1, 2004", "Boise, ID, US", "", "", ""]])

CAR_BAT_H = ["Year", "Age", "AgeDif", "Tm", "Lg", "Lev", "Aff", "G", "PA", "AB", "R", "H", "2B", "3B", "HR", "RBI",
             "SB", "CS", "BB", "SO", "BA", "OBP", "SLG", "OPS", "TB", "GDP", "HBP", "SH", "SF", "IBB"]
CAR_FLD_H = ["Year", "Age", "Tm", "Lg", "Lev", "Aff", "", "G", "GS", "CG", "Inn", "Ch", "PO", "A", "E", "DP", "Fld%",
             "RF/9", "RF/G", "PB", "WP", "SB", "CS", "CS%", "lgCS%", "PO"]
CAR_ROS_H = ["Year", "Age", "Tm", "Lg", "Lev", "Aff", "Stint", "From", "To"]

BARDOWELL = ("<html><body><div id='meta'><h1><span>Matthew Bardowell</span></h1>"
    "<p><strong>Positions:</strong> Leftfielder and Rightfielder</p>"
    "<p><strong>Bats: </strong>Right • <strong>Throws: </strong>Right</p>"
    "<p><span>6-4</span>, <span>245lb</span> (193cm, 111kg)</p>"
    "<p><strong>Born:</strong> <span data-birth='2002-04-13'>April 13, 2002</span> in Bell, CA us</p>"
    "<p><strong>High School:</strong> Etiwanda HS (Rancho Cucamonga, CA)</p>"
    "<p><strong>Schools:</strong> California State University, Fullerton (Fullerton, CA)</p></div>"
    + table("standard_batting", CAR_BAT_H, [
        [2025, 23, "", a_team("csf25", "CS Fullerton"), "BigW", "NCAA", "", 52, 241, 206, 42, 67, 16, 1, 8, 40, 3, 1, 25, 40,
         ".325", "", "", "", "", 3, 8, 0, 2, 0],
        [2025, 23, "", a_team("wil25", "Williamsport"), "MLBD", "Smr", "", 23, 96, 72, 13, 21, 2, 1, 2, 10, 2, 0, 18, 20,
         "", "", "", "", "", 0, 4, 0, 2, 0],
        [2026, 24, "", a_team("lbc26", "Long Beach"), "PION", "Ind", "", 81, 379, 311, 65, 112, 25, 2, 13, 83, 4, 2, 49, 72,
         "", "", "", "", "", 6, 14, 0, 5, 1],
        ["", "", "", "", "", "", "", 156, 716, 589, 120, 200, 43, 4, 23, 133, 9, 3, 92, 132, "", "", "", "", "", 9, 26, 0, 9, 1],
    ])
    + table("standard_fielding", CAR_FLD_H, [
        [2025, 23, a_team("csf25", "CS Fullerton"), "BigW", "NCAA", "", "LF", 39, 38, "", "330.0", 70, 65, 3, 2, 1, ".971",
         "", "", "", "", "", "", "", "", ""],
        [2025, 23, a_team("csf25", "CS Fullerton"), "BigW", "NCAA", "", "RF", 12, 10, "", "90.1", 20, 18, 1, 1, 0, ".950",
         "", "", "", "", "", "", "", "", ""],
    ], comment=True)
    + table("standard_roster", CAR_ROS_H, [
        [2025, 23, a_team("csf25", "Cal State Fullerton Titans"), "Big West Conference", "NCAA", "", "", "", ""],
        [2025, 23, a_team("wil25", "Williamsport Crosscutters"), "MLB Draft League", "Smr", "", "", "", ""],
        [2026, 24, a_team("lbc26", "Long Beach Coast"), "Pioneer League", "Ind", "", "", "", ""],
    ])
    + "</body></html>")

BAUTISTA = ("<html><body><div id='meta'><h1>Nick Bautista</h1><p><strong>Position:</strong> Pitcher</p>"
            "<p><strong>Bats: </strong>Left • <strong>Throws: </strong>Left</p></div></body></html>")
GRAD = ("<html><body><div id='meta'><h1>Tom Grad</h1><p><strong>Position:</strong> Shortstop</p></div>"
        + table("standard_batting", CAR_BAT_H, [
            [2026, 22, "", a_team("bsu26", "Boise St"), "MWC", "NCAA", "", 55, 230, 200, 40, 70, 14, 1, 6, 38, 10, 2, 22, 30,
             "", "", "", "", "", 2, 5, 0, 3, 0],
            [2026, 22, "", a_team("bh26", "Boise"), "PION", "Ind", "", 30, 110, 98, 12, 30, 6, 0, 2, 14, 1, 0, 9, 25,
             "", "", "", "", "", 1, 2, 0, 1, 0],
        ]) + "</body></html>")


class FakeHttp:
    def __init__(self):
        self.pages = {
            PIONEER_URL: LEAGUE, f"{B}/register/league.cgi?id=bbb26": SEASON,
            f"{B}/register/team.cgi?id=lbc26": LBC, f"{B}/register/team.cgi?id=bh26": BH,
            f"{B}/register/player.fcgi?id=bardow000mat": BARDOWELL,
            f"{B}/register/player.fcgi?id=bautis000nic": BAUTISTA,
            f"{B}/register/player.fcgi?id=grad--000tom": GRAD,
        }
        self.requested = []

    def get_text(self, url, **_):
        self.requested.append(url)
        return self.pages[url]


PIONEER_URL = bref.PIONEER.league_url()


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def test_team_page():
    page = bref.parse_team_page(LBC)
    assert page.name == "Long Beach Coast"
    assert len(page.batting) == 1                         # totals row has no player link
    assert page.batting[0].stats["pa"] == 379 and page.batting[0].stats["gdp"] == 6
    p = page.pitching[0]
    assert p.name == "Nick Bautista" and p.stats["outs"] == 239 and p.stats["bf"] == 360
    bio = page.roster["bardow000mat"]                      # roster was inside an HTML comment
    assert (bio["height_in"], bio["weight_lb"], bio["birth_date"], bio["hometown_state"]) == (76, 245, date(2002, 4, 13), "CA")


def test_player_page():
    pp = bref.parse_player_page(BARDOWELL)
    assert pp.bio["primary_position"] == "LF" and pp.bio["high_school"].startswith("Etiwanda")
    assert pp.bio["schools"].startswith("California State")
    hit = [r for r in pp.career if r.group == "h"]
    assert len(hit) == 3                                   # career totals row skipped
    assert hit[0].team_name == "Cal State Fullerton Titans" and hit[0].league == "Big West Conference"
    fld = [r for r in pp.career if r.group == "f"]
    assert [r.position for r in fld] == ["LF", "RF"]
    assert fld[1].stats["outs"] == 271 and fld[1].stats["po"] == 18   # 90.1 innings, first PO column wins


# ---------------------------------------------------------------------------
# Loader
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


def test_load_league_season(conn):
    tally = {"rows": 0, "errors": []}
    http = FakeHttp()
    s = bref.load_league_season(conn, http, bref.PIONEER, 2026, tally)
    assert tally["errors"] == []
    assert (s["teams"], s["players"], s["player_pages"]) == (2, 3, 3)
    db.rebuild_status(conn, 2027)
    conn.commit()

    hit = {r["last_name"]: r for r in conn.execute("SELECT * FROM ui_hitters").fetchall()}
    b = hit["Bardowell"]
    assert (b["team"], b["college"], b["grad_year"], b["primary_position"]) == ("Long Beach Coast", "Cal State Fullerton Titans", 2025, "LF")
    assert (b["season"], b["pa"], float(b["avg"])) == (2026, 379, 0.360)
    assert b["status_label"] == "Unconfirmed"              # no 2027 move yet
    assert b["high_school"].startswith("Etiwanda")

    # A 2026 grad who signed in the summer: college and pro lines stay separate,
    # and the list shows the pro line.
    g = hit["Grad"]
    assert (g["pa"], g["team"], g["college"], g["grad_year"]) == (110, "Boise Hawks", "Boise St", 2026)
    rows = conn.execute("SELECT season, is_pro, pa FROM ui_batting_seasons WHERE player_id = %s ORDER BY is_pro",
                        (g["id"],)).fetchall()
    assert [(r["is_pro"], r["pa"]) for r in rows] == [(False, 230), (True, 110)]

    pit = {r["last_name"]: r for r in conn.execute("SELECT * FROM ui_pitchers").fetchall()}
    assert (pit["Bautista"]["primary_position"], pit["Bautista"]["throws"]) == ("LHP", "L")
    assert pit["Bautista"]["fip"] is not None              # Pioneer League is complete, so FIP is calculated

    # College FIP is never calculated from a partial league
    assert conn.execute("SELECT count(*) AS n FROM leagues WHERE complete").fetchone()["n"] == 1

    f = conn.execute("SELECT position, outs FROM ui_fielding_seasons WHERE player_id = %s ORDER BY position",
                     (b["id"],)).fetchall()
    assert [(r["position"], r["outs"]) for r in f] == [("LF", 990), ("RF", 271)]

    # Rerun: team pages again, player pages skipped because they were read today
    again = bref.load_league_season(conn, FakeHttp(), bref.PIONEER, 2026, tally)
    assert again["player_pages"] == 0 and again["player_pages_skipped"] == 3
    assert conn.execute("SELECT count(*) AS n FROM batting_stats").fetchone()["n"] == 5


PASTED = """
Home   Schedule   Standings   Stats
PBL Player Transactions
November 15
Great Falls Voyagers
Signed Michael Quinones to their 2027 roster
November 10
Long Beach Coast
Signed Matthew Bardowell to their 2027 roster
Boise Hawks
Placed Tom Grad on Irrevocable waivers
October 20
Long Beach Coast
Transferred the contract of Nick Bautista to the Los Angeles Angels
Privacy Policy
"""


def test_pasted_transactions(conn):
    tally = {"rows": 0, "errors": []}
    bref.load_league_season(conn, FakeHttp(), bref.PIONEER, 2026, tally)
    summary = pioneer.load_transactions_text(conn, PASTED, 2027, tally, label="data/transactions/2027.txt")
    assert summary["parsed"] == 4 and summary["matched"] == 3
    assert summary["newest"] == "2026-11-15" and summary["oldest"] == "2026-10-20"
    assert any("Quinones" in u for u in summary["unmatched"])       # not in our pool, flagged
    db.rebuild_status(conn, 2027)
    conn.commit()
    st = {r["last_name"]: r for r in conn.execute("SELECT * FROM ui_players").fetchall()}
    assert (st["Bardowell"]["status_label"], st["Bardowell"]["status_team"]) == ("Signed", "Long Beach Coast")
    assert st["Grad"]["status_label"] == "Free Agent"
    assert "Bautista" not in st                                      # sold to an MLB club, out of the pool

    # Pasting the page again adds nothing new
    again = pioneer.load_transactions_text(conn, PASTED, 2027, tally, label="data/transactions/2027.txt")
    assert again["inserted"] == 0
