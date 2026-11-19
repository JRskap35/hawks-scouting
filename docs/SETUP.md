# Setup

GitHub holds the code and runs the site. Supabase holds the data and the staff logins. These steps
connect the two.

## 1. Create the database (Supabase)

1. Make a free account and a new project at [supabase.com](https://supabase.com). When it asks for a
   database password, click Generate and save it somewhere safe.
2. Click **Connect** at the top of the project, choose **Session pooler**, and copy the connection
   string. Put your database password in place of `[YOUR-PASSWORD]`. This is your `DATABASE_URL`.
3. Copy the **Project URL** and the **publishable key** (starts with `sb_publishable_`). Both are in the
   Connect dialog, and the key is also under **Settings > API Keys**.

## 2. Connect Supabase to GitHub

In this repo, go to **Settings > Secrets and variables > Actions**. Use the **Repository** tabs, not
Environment.

| Add as a | Name | Value |
| --- | --- | --- |
| Variable | `SUPABASE_URL` | Project URL |
| Variable | `SUPABASE_PUBLISHABLE_KEY` | publishable key |
| Secret | `DATABASE_URL` | session pooler connection string |
| Secret | `SCRAPER_CONTACT` | your email |

The two variables go into the website. The publishable key is meant to be public, and the login rules
from step 3 protect the data. The two secrets are only used by the workflows and never appear on the
site.

## 3. Create the tables and lock them down

1. **Actions > Set up database > Run workflow**, task **Create tables**.
2. Open the Supabase **SQL Editor**, paste in all of `db/supabase.sql`, and run it. This is the step
   that blocks anyone who isn't signed in, so don't skip it.

## 4. Load the data

Player stats come from Baseball Reference, because the Pioneer League site blocks automated
requests. Transactions are pasted in from the league page.

1. **Actions > Set up database > Run workflow**, task **Check Baseball Reference**. It reads one
   page of each kind and ends with PASS. If it doesn't, send that output over.
2. Run it again with task **First load**. It reads every team page and every player's own page at
   Baseball Reference's requested pace, so it takes about 45 minutes.
3. Paste the 2027 transactions: follow `data/transactions/README.md`. Saving the file updates every
   player's badge.

After this, **Biweekly refresh** re-reads the team pages every other Monday (player pages once a
month), and the badges update whenever you paste the transaction page again.

### What comes from where

| On the site | Source |
| --- | --- |
| Players, season stats, team | Baseball Reference team pages |
| Bats, throws, height, weight, birth date, birthplace, high school | Baseball Reference roster and player pages |
| College and graduation year, past seasons, college fielding | Baseball Reference player pages (final college season) |
| Free Agent, Signed, Unconfirmed | Pasted league transactions |
| Game logs, Pioneer League fielding | Not available yet: only the league site has them |

## 5. Add the staff

In Supabase **Authentication**:

1. Turn off public sign ups.
2. Set the Site URL to `https://jrskap35.github.io/hawks-scouting/`, so emailed sign in links come back
   to the site.
3. Invite each scout by email.

## Reference

### Running it on your own computer

Everything the workflows do also runs locally:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                   # paste in DATABASE_URL and your email
python cli.py bref-check               # no database needed
python cli.py init-db                  # rerunning adds new columns and rebuilds the views
python cli.py bref --season 2026       # full load from Baseball Reference
python cli.py transactions-file        # load data/transactions/*.txt
python cli.py rebuild-status           # recompute every 2027 status
python cli.py check-site               # test the league site (blocked from cloud servers)
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
