# Boise Hawks Scouting Database

Scrapers, database, and website for the Hawks scouting tool. The scrapers load the Pioneer League,
which is the baseline every other league and college gets translated into. The website is a static
site on GitHub Pages that reads from Supabase, with staff logins.

## What runs today

| Piece | What it does |
| --- | --- |
| `db/schema.sql` | Every table and view: players, stats, transactions, eligibility, markers, reports |
| `db/web.sql` | The views the website reads, with AVG through FIP calculated |
| `db/supabase.sql` | Logins and row level security (run once in Supabase) |
| `web/` | The website (React, AG Grid) |
| `.github/workflows/deploy-site.yml` | Publishes the website to GitHub Pages on every push |
| `scrapers/pioneer.py` | Pioneer League hitting, pitching, fielding, rosters, transactions |
| `scrapers/presto.py` | Parser for PrestoSports sites (Pioneer League plus many college and summer leagues) |
| `scrapers/transactions.py` | Turns transaction report lines into signings, releases, trades, and contract sales |
| `scrapers/http.py` | Polite fetching: robots.txt, 3 second spacing, disk cache, retries |
| `.github/workflows/refresh.yml` | Reruns everything every other Monday |

## Setup (about 15 minutes)

1. **Create the database.** Make a free project at supabase.com. Under Project Settings > Database,
   copy the session pooler connection string.
2. **Install.**
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env        # paste DATABASE_URL and your email into it
   ```
3. **Create the tables, then lock them down.**
   ```bash
   python cli.py init-db
   ```
   Then open the Supabase SQL editor, paste in `db/supabase.sql`, and run it. Until that runs, the
   data is not protected by logins.
4. **Check the parser against the live site before the first full load.** This needs no database
   and fetches one page:
   ```bash
   python cli.py doctor "https://www.pioneerleague.com/sports/bsb/2026/players?pos=h&r=0"
   python cli.py doctor "https://www.pioneerleague.com/sports/bsb/2026/players?pos=p&r=0" --group p
   python cli.py doctor "https://www.pioneerleague.com/players/transactions"
   ```
   You should see the table headers, the views and page count, and five parsed players with team
   names and stats. If a stat is missing, its header is not in the alias table at the top of
   `scrapers/presto.py`. Add it there.
5. **First load.**
   ```bash
   python cli.py pioneer --season 2026
   ```
   This pulls 2026 stats and bio details, reads the 2026 report once (for releases and MLB contract
   sales), reads the 2027 report, and sets every player's 2027 status. At 3 seconds between requests
   it takes a few minutes. The output lists any transaction names it could not match to a player.

## The website

**Try it now without any setup.** In `web/`, run `npm install` then `npm run dev` and open the
address it prints. With no Supabase settings it runs on made up demo players.

**Publish it on GitHub Pages.**

1. Push this whole folder to a GitHub repo. On a free GitHub account Pages only works from a public
   repo. That is fine here: the repo holds code, never player data, and the data stays behind the
   staff login. A paid plan (Pro or Team) can publish from a private repo.
2. Repo Settings > Pages > Source: **GitHub Actions**.
3. Repo Settings > Secrets and variables > Actions > **Variables**: add `SUPABASE_URL` and
   `SUPABASE_ANON_KEY` from Supabase Project Settings > API. The anon key is meant to be public;
   row level security is what protects the data.
4. Run the **Deploy site** workflow from the Actions tab (it also runs on every push to `web/`).
   The site appears at `https://<your-username>.github.io/<repo-name>/`.

**Give the staff logins.** In Supabase Authentication, turn off public sign ups, then invite each
scout by email. Set the Site URL and redirect URL to your GitHub Pages address so the emailed sign
in links come back to the site. Each person who signs in gets a staff record automatically, and
their name shows next to any marker they set.

**What is on the site.**

* Position Players, Pitchers, Two Way Players, and Scouted Players in the header, plus a search box
  that opens any player from any page.
* Infield, Outfield, Catcher on Position Players. Starters and Relievers on Pitchers.
* A status filter (Free agents, Signed, Unconfirmed) and min and max filters on any stat, stacked
  as removable chips.
* The star on each row sets a shared marker: Looking to Sign, Potential, or Already Reviewed.
  Every change is logged with who made it.
* Clicking a name opens the profile with Batting, Pitching, and Fielding season tables.
* Export downloads exactly the rows shown, in the order shown, as CSV or PDF.
* Hover any stat header for its formula. Grey numbers are small samples (under 100 PA or 30 IP).

## Commands

```bash
python cli.py pioneer --season 2026        # first load (see above)
python cli.py transactions                 # 2027 report and status rebuild only
python cli.py rebuild-status               # recompute every 2027 status
python cli.py refresh                      # what the biweekly schedule runs
```

## The biweekly schedule

Push this folder to a private GitHub repo, then add two secrets under Settings > Secrets and
variables > Actions: `DATABASE_URL` and `SCRAPER_CONTACT`. The workflow runs every other Monday
morning, and you can start it by hand from the Actions tab.

## How signing status is decided

Status is for the upcoming season only (2027). The season rolls forward on its own each October.

* **The 2027 report decides.** It covers moves from October 2026 on. The latest move wins:
  signed (independent), contract sold to an MLB club (affiliated, leaves the pool), released or
  cleared waivers (free agent), retired (leaves the pool), traded (follows the new club). Injury and
  reinstatement moves change nothing.
* **Last season's roster spots do not count.** A player who played in 2026 but has no 2027 move is
  Unconfirmed. His 2026 stats are still there for scouting.
* **Three 2026 moves still stand** until a 2027 move changes them, since nothing has undone them
  yet: a release (free agent), a contract sold to an MLB club (excluded), and a retirement (excluded).
* Reports have no year on their dates. October to December dates belong to the prior calendar year,
  and the live page is only ever read as the upcoming season's report.
* `eligible_players` drops anyone affiliated, retired, or returning to college. `can_sign_now` is
  true only for free agents. Signed and Unconfirmed players stay visible with their badge.

## Tests

```bash
pytest -q                                                    # parser tests
TEST_DATABASE_URL=postgresql://localhost/scouting_test pytest -q   # plus the full Postgres run
```

The transaction tests use 38 real lines from the 2025 and 2026 Pioneer League reports. The stat
parser tests use pages built to match PrestoSports markup, because the live site could not be
fetched while this was built. Step 4 above is the check against the real pages.
