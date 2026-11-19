-- ============================================================
-- Changes to tables that already hold data. Every statement is safe to run again.
-- `python cli.py init-db` runs this file on every call, before rebuilding the views.
-- New columns are also in schema.sql, so a fresh database gets them either way.
-- ============================================================

-- Baseball Reference lists college seasons without the division, so a plain NCAA level exists.
ALTER TYPE comp_level ADD VALUE IF NOT EXISTS 'ncaa';

-- When a player's own page was last read, so the refresh only re-reads stale ones.
ALTER TABLE player_external_ids ADD COLUMN IF NOT EXISTS fetched_at timestamptz;

ALTER TABLE players ADD COLUMN IF NOT EXISTS high_school text;

-- A league counts as complete when every player in it was loaded. League constants such as the
-- FIP constant are only calculated for complete leagues, since a handful of players would skew them.
ALTER TABLE leagues ADD COLUMN IF NOT EXISTS complete boolean NOT NULL DEFAULT false;

-- Staff edits to a player's status are stored as transactions: who made it, and an optional note.
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS entered_by uuid;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS note text;
