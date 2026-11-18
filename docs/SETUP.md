# Setup

GitHub holds the code and runs the site. Supabase holds the data and the staff logins. These steps
connect the two.

## 1. Create the database (Supabase)

1. Make a free account and a new project at [supabase.com](https://supabase.com). Save the database
   password it asks for.
2. Click **Connect** at the top of the project and copy the session pooler connection string. This is
   your `DATABASE_URL`. Put your database password in place of `[YOUR-PASSWORD]`.
3. Copy the **Project URL** and the **publishable key** (starts with `sb_publishable_`). Both are in the
   Connect dialog, and the key is also under **Settings > API Keys**.

## 2. Create the tables

On your computer, from the repo folder:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # paste in DATABASE_URL and your email
python cli.py init-db
```

Then open the Supabase **SQL Editor**, paste in all of `db/supabase.sql`, and run it. This is the step
that blocks anyone who isn't signed in, so don't skip it.

## 3. Connect Supabase to GitHub

In this repo, go to **Settings > Secrets and variables > Actions**.

| Add as a | Name | Value |
| --- | --- | --- |
| Variable | `SUPABASE_URL` | Project URL |
| Variable | `SUPABASE_PUBLISHABLE_KEY` | publishable key |
| Secret | `DATABASE_URL` | session pooler connection string |
| Secret | `SCRAPER_CONTACT` | your email |

The two variables go into the website. The publishable key is meant to be public, and the login rules
from step 2 protect the data. The two secrets are only used by the refresh job and never appear on the site.

Then run **Actions > Deploy site > Run workflow**. The site switches from demo players to a login page.

## 4. Load the data

First check that the scraper reads the league site correctly. This fetches one page and needs no
database:

```bash
python cli.py doctor "https://www.pioneerleague.com/sports/bsb/2026/players?pos=h&r=0"
```

You should see five players with team names and stats. To check game logs, open any player on the league
site, copy his page address, add `?view=gamelog` to the end, and run `doctor` on it. You should see his
games listed.

Then load everything:

```bash
python cli.py pioneer --season 2026
```

After this, **Actions > Biweekly refresh** keeps it current every other Monday.

## 5. Add the staff

In Supabase **Authentication**:

1. Turn off public sign ups.
2. Set the Site URL to `https://jrskap35.github.io/hawks-scouting/`, so emailed sign in links come back
   to the site.
3. Invite each scout by email.

## Reference

### Commands

```bash
python cli.py pioneer --season 2026    # full load, including game logs (one request per player)
python cli.py pioneer --season 2026 --skip-gamelogs   # faster, no game logs
python cli.py transactions             # 2027 transactions only
python cli.py rebuild-status           # recompute every 2027 status
python cli.py refresh                  # what the biweekly job runs
```

### How signing status works

* Status is for 2027 only, from the 2027 transaction report (moves from October 2026 on).
* A 2026 roster spot does not count. Players with no 2027 move show as Unconfirmed.
* Three 2026 moves still stand until a 2027 move changes them: a release, a contract sold to an MLB
  club, and a retirement.
* The season rolls forward on its own each October.

### Tests

```bash
pytest -q
```

Add `TEST_DATABASE_URL=postgresql://localhost/scouting_test` in front to also run the full database
test against a throwaway local Postgres.

### Working on the website

In `web/`, run `npm install` then `npm run dev`. With no Supabase settings it uses demo players.
