"""
Transaction parser tests. Every line below is copied from the real Pioneer League
2025 and 2026 transaction reports, typos included ("Tradeed").
"""

from datetime import date

import pytest

from scrapers.transactions import classify, parse_date_header, parse_report, status_after

# (line, expected txn, expected player, expected counterparty or None)
REAL_LINES = [
    ("Signed Blake Wilhoite to their 2026 roster", "signed", "Blake Wilhoite", None),
    ("Signed Quintt Landis to their 2025 roster", "signed", "Quintt Landis", None),
    ("Exercised the 2026 contract option for Ethan Crawford", "signed", "Ethan Crawford", None),
    ("Placed CJ Czerwinski on the Injury List (Injury 10 Days)", "injury", "CJ Czerwinski", None),
    ("Placed Kendal Ewell on the Injury List (Injury 60 Days)", "injury", "Kendal Ewell", None),
    ("Moved Adam Fogel to the Injured List (10 days)", "injury", "Adam Fogel", None),
    ("Reinstated Adam Fogel from the Injury List", "injury", "Adam Fogel", None),
    ("Placed Shuto Okumura on Irrevocable waivers", "released", "Shuto Okumura", None),
    ("Placed Joel French on irrevocable waivers", "released", "Joel French", None),
    ("Trae Robertson cleared waivers and is a free agent", "released", "Trae Robertson", None),
    ("Reinstated Michael Ball from the Ineligible List", "other", "Michael Ball", None),
    ("Placed Ian Farrow on Ineligible List (Voluntary Retirement)", "retired", "Ian Farrow", None),
    ("Placed Nick Parker on the Ineligible List (Voluntary Retirement)", "retired", "Nick Parker", None),
    ("Placed Cutter Smith on Ineligible List (Failure to Report)", "other", "Cutter Smith", None),
    ("Placed Kirkland Banks on the Ineligible List (Pending Trade)", "other", "Kirkland Banks", None),
    ("Placed Malik Binns on the Ineligible List (Suspension)", "suspended", "Malik Binns", None),
    ("Claimed Blake Barker off waivers from the Oakland Ballers", "traded", "Blake Barker", "Oakland Ballers"),
    ("Claimed Cam Cowan off waivers", "traded", "Cam Cowan", None),
    ("Traded Andrew Rust to the Down East Bird Dawgs of the Frontier League in exchange for future considerations.",
     "traded", "Andrew Rust", "Down East Bird Dawgs"),
    ("Transferred the contract of Justin Fuson to the Chicago White Sox", "contract_sold", "Justin Fuson", "Chicago White Sox"),
    ("Sold the contract of Chris Sargent to the San Diego Padres", "contract_sold", "Chris Sargent", "San Diego Padres"),
    ("Sold the contract of Augie Mojica to the Arizona Diamondbacks", "contract_sold", "Augie Mojica", "Arizona Diamondbacks"),
    ("Elijah Young Traded Elijah Young to the RedPocket Mobiles to complete a previous transaction.",
     "traded", "Elijah Young", "RedPocket Mobiles"),
    ("Quintt Landis Received Quintt Landis from the Colorado Springs Sky Sox to complete a previous transaction.",
     "traded", "Quintt Landis", "Colorado Springs Sky Sox"),
    ("Michael Riley Acquired RHP Michael Riley from the Tri City Valley Cats in exchange for a player to be named later",
     "traded", "Michael Riley", "Tri City Valley Cats"),
    ("Nick Bautista Traded RHP Nick Bautista to the Long Beach Coast in exchange for a player to be named later.",
     "traded", "Nick Bautista", "Long Beach Coast"),
    ("Acquired Quintt Landis from the Colorado Springs Sky Sox to complete a previous transaction",
     "traded", "Quintt Landis", "Colorado Springs Sky Sox"),
    ("Traded Austyn Coleman to the Ogden Raptors for a player to be named later", "traded", "Austyn Coleman", "Ogden Raptors"),
    ("Traded Malik Binns to the Oakland Ballers for 3 draft picks in 2026", "traded", "Malik Binns", "Oakland Ballers"),
    ("Received Garret Marting from the Southern Maryland Blue Crabs of the Atlantic League in exchange for Future Considerations",
     "traded", "Garret Marting", "Southern Maryland Blue Crabs"),
    ("Traded Cole Calnon to the Billings Mustangs for Evan Berkey", "traded", "Cole Calnon", "Billings Mustangs"),
    ("Traded Shane Spencer to the Idaho Falls Chukars in exchange for OF/RHP Chase Hanson",
     "traded", "Shane Spencer", "Idaho Falls Chukars"),
    ("Yuba-Sutter High Wheelers trade Leyton Barry to the Missoula PaddleHeads for a player to be named later",
     "traded", "Leyton Barry", "Missoula PaddleHeads"),
    ("Austyn Coleman has been traded to the Colorado Sky Sox of the PBL for a player to be named later",
     "traded", "Austyn Coleman", "Colorado Sky Sox"),
    ("Tradeed Jake Dixon to the Idaho Falls Chukars of the Pioneer League for Future Considerations",
     "traded", "Jake Dixon", "Idaho Falls Chukars"),
    ("Boise Hawks trade Andrew Baker to the Down East Bird Dawgs of the Frontier League for a player to be named later",
     "traded", "Andrew Baker", "Down East Bird Dawgs"),
    # Other leagues' phrasing (Fargo-Moorhead, American Association)
    ("Released INF Peter Brookshaw", "released", "Peter Brookshaw", None),
    ("Transferred the contract of RHP Garrett Alexander to Oaxaca (Mexican League)", "contract_sold",
     "Garrett Alexander", "Oaxaca (Mexican League)"),
]


@pytest.mark.parametrize("line,txn,name,cp", REAL_LINES)
def test_classify_real_lines(line, txn, name, cp):
    got_txn, got_name, got_cp = classify(line)
    assert got_txn == txn, line
    assert got_name == name, line
    assert got_cp == cp, line


def test_dates_without_year_follow_the_season_calendar():
    assert parse_date_header("August 30", 2025) == date(2025, 8, 30)
    assert parse_date_header("October 3", 2025) == date(2024, 10, 3)   # prior fall
    assert parse_date_header("Aug. 30", 2025) == date(2025, 8, 30)
    assert parse_date_header("May 13, 2026", 2025) == date(2026, 5, 13)
    assert parse_date_header("Boise Hawks", 2025) is None


REPORT = """
August 30
Idaho Falls Chukars
- Reinstated Bennett Flynn from the Ineligible List
- Placed Benjamin Rosengard on the Injury List (Injury 10 Days)
Yuba-Sutter High Wheelers
- Acquired Quintt Landis from the Colorado Springs Sky Sox to complete a previous transaction
- Signed Quintt Landis to their 2025 roster
• Placed Christian Womble on Irrevocable waivers
August 26
Ogden Raptors
- Sold the contract of Chris Sargent to the San Diego Padres
October 14
Boise Hawks
- Traded Jake Hjelle to the Fargo-Moorhead RedHawks of the American Association for a player to be named later
""".splitlines()


def test_parse_report_tracks_date_and_team():
    rows = parse_report(REPORT, season=2025)
    assert len(rows) == 7
    womble = next(r for r in rows if r.player_name == "Christian Womble")
    assert womble.team == "Yuba-Sutter High Wheelers"
    assert womble.txn_date == date(2025, 8, 30)
    assert status_after(womble) == "free_agent"

    sargent = next(r for r in rows if r.player_name == "Chris Sargent")
    assert sargent.from_team == "Ogden Raptors"
    assert sargent.to_team == "San Diego Padres"
    assert status_after(sargent) == "signed_affiliated"

    hjelle = next(r for r in rows if r.player_name == "Jake Hjelle")
    assert hjelle.txn_date == date(2024, 10, 14)
    assert hjelle.counterparty == "Fargo-Moorhead RedHawks"
    assert status_after(hjelle) == "signed_independent"

    landis_in = next(r for r in rows if r.player_name == "Quintt Landis" and r.txn == "traded")
    assert landis_in.to_team == "Yuba-Sutter High Wheelers"
    assert landis_in.from_team == "Colorado Springs Sky Sox"

    rosengard = next(r for r in rows if r.player_name == "Benjamin Rosengard")
    assert status_after(rosengard) is None     # injury list does not change signing status


def test_status_effects():
    _, _, _ = classify("Released INF Peter Brookshaw")
    rows = parse_report(["June 1", "Boise Hawks",
                         "- Transferred the contract of RHP Garrett Alexander to Oaxaca (Mexican League)",
                         "- Placed Ian Farrow on Ineligible List (Voluntary Retirement)",
                         "- Traded Sam Smith to the Colorado Rockies for cash"], season=2026)
    alexander, farrow, smith = rows
    assert status_after(alexander) == "signed_independent"   # foreign league, not affiliated
    assert status_after(farrow) == "retired"
    assert status_after(smith) == "signed_affiliated"        # traded to an MLB club
