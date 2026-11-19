# Pasted transactions

The Pioneer League site blocks automated requests, so its transaction page is copied in by hand.
Each file is named for the season the report covers: `2027.txt` holds the 2027 report, which
includes every move since October 2026.

## Updating it (about a minute)

1. Open https://www.pioneerleague.com/players/transactions/index in your browser.
2. Select everything on the page (Ctrl+A, or Cmd+A on a Mac) and copy it.
3. Here on GitHub, open `2027.txt`, click the pencil icon, select all of its text, and paste over it.
4. Click **Commit changes**.

Saving the file runs the **Load pasted transactions** workflow. It reads every move, matches the
names to players, and updates each player's Free Agent, Signed, or Unconfirmed badge. Its summary
lists any names it could not match.

Paste the whole page each time. Moves already loaded are skipped, so nothing is counted twice, and
extra text from the page (menus, footers) is ignored.
