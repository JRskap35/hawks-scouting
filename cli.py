"""
Command line entry point.

    python cli.py init-db                     create every table and view (rerun: rebuilds views only)
    python cli.py check-site                  read one page of each kind from the league site
    python cli.py pioneer --season 2026       first load: 2026 stats and bios, 2026 and 2027 reports, 2027 statuses
    python cli.py transactions                upcoming season's report and status rebuild only
    python cli.py rebuild-status              recompute every player's signing status
    python cli.py refresh                     what the two week schedule runs
    python cli.py doctor <url>                show what the parser sees on a page (no database needed)
                                              works on stat lists, rosters, game logs, and transaction pages
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

from scrapers import db, pioneer, presto          # noqa: E402  (env must load first)
from scrapers.http import PoliteSession           # noqa: E402


def current_season() -> int:
    """Most recent season with stats."""
    return pioneer.stats_season()


def cmd_init_db(_args):
    with db.connect() as conn:
        did = db.init_schema(conn)
    print("Tables and views created." if did == "created" else "Tables already exist. New columns added and views rebuilt; no data touched.")


def cmd_bref(args):
    from scrapers import bref
    with db.connect() as conn:
        source_id = db.get_or_create_source(conn, bref.SOURCE_NAME, bref.BASE, priority=1)
        with db.scrape_run(conn, source_id) as tally:
            result = bref.load_league_season(conn, PoliteSession(), bref.PIONEER, args.season, tally,
                                             players=not args.skip_players, force_players=args.force_players)
            result["status_rows"] = db.rebuild_status(conn, pioneer.transaction_season())
            result["errors"] = list(tally["errors"])
    print(json.dumps(result, indent=2, default=str))


def cmd_bref_check(args):
    from scrapers import bref
    print(bref.check(PoliteSession(), bref.PIONEER, args.season))


def cmd_check_site(args):
    from scrapers.check import check_site, format_checks
    print(format_checks(check_site(PoliteSession(), season=args.season)))


def cmd_pioneer(args):
    with db.connect() as conn:
        # The season's own report is loaded once so its releases and MLB contract sales carry
        # forward. Statuses themselves are computed for the upcoming season only.
        txn = () if args.skip_transactions else (args.season, pioneer.transaction_season())
        result = pioneer.run(conn, PoliteSession(), args.season,
                             rosters=not args.skip_rosters, txn_seasons=txn, gamelogs=not args.skip_gamelogs)
    print(json.dumps(result, indent=2, default=str))


def cmd_transactions(args):
    with db.connect() as conn:
        cfg = pioneer.PIONEER
        source_id = db.get_or_create_source(conn, f"{cfg.name} site", cfg.site, priority=10)
        with db.scrape_run(conn, source_id) as tally:
            summary = pioneer.load_transactions(conn, PoliteSession(), cfg, args.season, source_id, tally)
            summary["status_rows"] = db.rebuild_status(conn, pioneer.transaction_season())
    print(json.dumps(summary, indent=2, default=str))


def cmd_rebuild_status(_args):
    with db.connect() as conn:
        target = pioneer.transaction_season()
        n = db.rebuild_status(conn, target)
        conn.commit()
    print(f"Updated {target} status for {n} players.")


def cmd_refresh(_args):
    """Latest season's stats and bio pages, plus the upcoming season's transaction report."""
    with db.connect() as conn:
        result = pioneer.run(conn, PoliteSession(), pioneer.stats_season(),
                             txn_seasons=(pioneer.transaction_season(),))
    print(json.dumps(result, indent=2, default=str))


def cmd_doctor(args):
    """Fetch one page and print what each parser finds. Use this when a site changes its layout."""
    http = PoliteSession()
    html = http.get_text(args.url)
    group = args.group
    print(f"Fetched {len(html):,} bytes from {args.url}\n")

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    for i, t in enumerate(soup.find_all("table")):
        print(f"table {i}: headers = {presto._headers(t)}")
    print(f"\nviews for pos={group}: {presto.discover_views(html, group)}")
    print(f"pages: {presto.page_count(html)}")

    rows = presto.parse_stat_tables(html, group, args.url)
    print(f"\nstat rows parsed: {len(rows)}")
    for r in rows[:5]:
        print(f"  {r.player_label:<22} {r.team_name or '?':<24} {r.stats}")

    roster = presto.parse_roster(html, args.url)
    if roster:
        print(f"\nroster rows parsed: {len(roster)}")
        for r in roster[:5]:
            print(f"  {r.name:<24} {r.fields}")

    games = presto.parse_gamelog(html, args.season or current_season())
    if games:
        print(f"\ngame log rows parsed: {len(games)}")
        for g in games[:8]:
            side = {"H": "vs", "A": "at"}.get(g.home_away, "")
            print(f"  {g.game_date} {g.group} {side} {g.opponent or '?':<22} {g.result or '':<8} {g.decision or '':<3} {g.stats}")

    if "transaction" in args.url:
        from scrapers.transactions import parse_report
        parsed = parse_report(pioneer.report_lines(html), args.season or current_season())
        print(f"\ntransactions parsed: {len(parsed)}")
        for t in parsed[:15]:
            print(f"  {t.txn_date} {t.team[:20]:<20} {t.txn:<14} {t.player_name or '?':<22} -> {t.counterparty or ''}")


def main(argv=None):
    p = argparse.ArgumentParser(description="Boise Hawks scouting database scrapers")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db").set_defaults(fn=cmd_init_db)

    s = sub.add_parser("bref", help="load a league season from Baseball Reference")
    s.add_argument("--season", type=int, default=current_season())
    s.add_argument("--skip-players", action="store_true", help="team pages only, no player pages (fast)")
    s.add_argument("--force-players", action="store_true", help="re-read every player page, even recent ones")
    s.set_defaults(fn=cmd_bref)

    s = sub.add_parser("bref-check", help="read one page of each kind from Baseball Reference, no database needed")
    s.add_argument("--season", type=int, default=current_season())
    s.set_defaults(fn=cmd_bref_check)

    s = sub.add_parser("check-site", help="read one page of each kind from the league site, no database needed")
    s.add_argument("--season", type=int)
    s.set_defaults(fn=cmd_check_site)

    s = sub.add_parser("pioneer")
    s.add_argument("--season", type=int, default=current_season())
    s.add_argument("--skip-rosters", action="store_true")
    s.add_argument("--skip-transactions", action="store_true")
    s.add_argument("--skip-gamelogs", action="store_true", help="skip the one request per player for game logs")
    s.set_defaults(fn=cmd_pioneer)

    s = sub.add_parser("transactions")
    s.add_argument("--season", type=int, default=pioneer.transaction_season(),
                   help="report season; moves made since October belong to next season's report")
    s.set_defaults(fn=cmd_transactions)

    sub.add_parser("rebuild-status").set_defaults(fn=cmd_rebuild_status)

    sub.add_parser("refresh").set_defaults(fn=cmd_refresh)

    s = sub.add_parser("doctor")
    s.add_argument("url")
    s.add_argument("--group", default="h", choices=["h", "p", "f"])
    s.add_argument("--season", type=int)
    s.set_defaults(fn=cmd_doctor)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
