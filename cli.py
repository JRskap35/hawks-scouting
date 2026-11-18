"""
Command line entry point.

    python cli.py init-db                     create every table and view
    python cli.py pioneer --season 2026       first load: 2026 stats and bios, 2026 and 2027 reports, 2027 statuses
    python cli.py transactions                upcoming season's report and status rebuild only
    python cli.py rebuild-status              recompute every player's signing status
    python cli.py refresh                     what the two week schedule runs
    python cli.py doctor <url>                show what the parser sees on a page (no database needed)
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
        db.init_schema(conn)
    print("Schema created.")


def cmd_pioneer(args):
    with db.connect() as conn:
        # The season's own report is loaded once so its releases and MLB contract sales carry
        # forward. Statuses themselves are computed for the upcoming season only.
        txn = () if args.skip_transactions else (args.season, pioneer.transaction_season())
        result = pioneer.run(conn, PoliteSession(), args.season,
                             rosters=not args.skip_rosters, txn_seasons=txn)
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

    s = sub.add_parser("pioneer")
    s.add_argument("--season", type=int, default=current_season())
    s.add_argument("--skip-rosters", action="store_true")
    s.add_argument("--skip-transactions", action="store_true")
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
