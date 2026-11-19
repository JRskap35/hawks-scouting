-- ============================================================
-- Boise Hawks Scouting Database
-- Schema proposal v1 (PostgreSQL 15+, built for Supabase)
--
-- Layout
--   1. Reference data: sources, leagues, teams, parks, league constants
--   2. Players and identity matching
--   3. Eligibility, status, transactions
--   4. Raw stats (batting, pitching, fielding, tracking)
--   5. Calculated metrics (views) and metric definitions
--   6. Scouting side: markers, reports, notes, tags, extras
--   7. App support: saved views, ranking profiles, Hawks roster
--   8. Scrape bookkeeping and cache
--
-- Conventions
--   * Every scraped row carries source_id and pulled_at.
--   * Innings are stored as OUTS (integer) so 6.2 IP is 20 outs, never 6.2.
--   * Splits live in the same stat tables via a split column ('total' by default),
--     so totals and splits share one shape.
--   * Nothing is estimated. If an input is missing, the metric is NULL and
--     the UI shows it as unavailable.
-- ============================================================


CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- fuzzy name search in the header


-- ------------------------------------------------------------
-- 1. Reference data
-- ------------------------------------------------------------

CREATE TABLE sources (
    id              serial PRIMARY KEY,
    name            text NOT NULL UNIQUE,          -- 'Baseball Reference', 'Pioneer League site', 'Sidearm: Boise State'
    base_url        text,
    priority        smallint NOT NULL DEFAULT 50,  -- lower wins when two sources disagree (BR = 1)
    rate_limit_sec  numeric(5,2) NOT NULL DEFAULT 3.0,
    robots_checked  boolean NOT NULL DEFAULT false,
    terms_notes     text
);

CREATE TYPE org_type AS ENUM ('affiliated', 'independent', 'college');

CREATE TYPE comp_level AS ENUM (
    'mlb', 'aaa', 'aa', 'high_a', 'single_a', 'complex',
    'independent', 'mlb_partner',
    'ncaa_d1', 'ncaa_d2', 'ncaa_d3', 'naia', 'juco',
    'summer_collegiate', 'ncaa'
);

-- Leagues AND college conferences live here (SEC, Big West, Pioneer League, Frontier League...).
CREATE TABLE leagues (
    id          serial PRIMARY KEY,
    name        text NOT NULL,
    abbrev      text,
    org         org_type NOT NULL,
    level       comp_level NOT NULL,
    website     text,
    complete    boolean NOT NULL DEFAULT false,   -- every player in the league is loaded
    UNIQUE (name, level)
);

CREATE TABLE parks (
    id            serial PRIMARY KEY,
    name          text NOT NULL,
    city          text,
    state         text,
    elevation_ft  integer,          -- drives the altitude adjustment
    latitude      numeric(8,5),
    longitude     numeric(8,5)
);

CREATE TABLE teams (
    id        serial PRIMARY KEY,
    name      text NOT NULL UNIQUE,   -- 'Boise Hawks', 'Oregon State'
    city      text,
    org       org_type NOT NULL,
    site_url  text                    -- team page on its league or school site
);

-- A team's league and park can change year to year.
CREATE TABLE team_seasons (
    team_id    integer REFERENCES teams(id),
    season     smallint NOT NULL,
    league_id  integer REFERENCES leagues(id),
    park_id    integer REFERENCES parks(id),
    PRIMARY KEY (team_id, season)
);

-- League run environment, computed from league totals each season.
-- This is what makes wOBA, wRC+, and FIP league specific instead of borrowing MLB constants.
CREATE TABLE league_seasons (
    league_id        integer REFERENCES leagues(id),
    season           smallint NOT NULL,
    lg_pa            integer,
    lg_runs          integer,
    lg_woba          numeric(5,4),
    woba_scale       numeric(5,4),
    w_bb             numeric(5,3),
    w_hbp            numeric(5,3),
    w_1b             numeric(5,3),
    w_2b             numeric(5,3),
    w_3b             numeric(5,3),
    w_hr             numeric(5,3),
    runs_per_pa      numeric(6,5),
    fip_constant     numeric(5,3),
    lg_hr_per_fb     numeric(5,4),     -- NULL when the league publishes no batted ball data
    lg_era           numeric(5,3),
    -- Translation into Pioneer League context. 1.000 = Pioneer League.
    strength_factor_bat   numeric(5,3),
    strength_factor_pitch numeric(5,3),
    strength_method       text,        -- how the factor was derived, shown in the UI
    PRIMARY KEY (league_id, season)
);

CREATE TABLE park_factors (
    park_id       integer REFERENCES parks(id),
    season        smallint NOT NULL,
    years_used    smallint NOT NULL,    -- multi year factors are more stable
    pf_runs       numeric(5,3),         -- 1.000 = neutral
    pf_hr         numeric(5,3),
    pf_h          numeric(5,3),
    pf_so         numeric(5,3),
    pf_bb         numeric(5,3),
    regressed     boolean NOT NULL DEFAULT true,
    method        text,
    PRIMARY KEY (park_id, season)
);


-- ------------------------------------------------------------
-- 2. Players and identity
-- ------------------------------------------------------------

CREATE TYPE hand AS ENUM ('L', 'R', 'S');

CREATE TABLE players (
    id               serial PRIMARY KEY,
    first_name       text NOT NULL,
    last_name        text NOT NULL,
    full_name        text GENERATED ALWAYS AS (first_name || ' ' || last_name) STORED,
    birth_date       date,
    height_in        smallint,
    weight_lb        smallint,
    bats             hand,
    throws           hand,
    hometown_city    text,
    hometown_state   text,
    high_school      text,
    primary_position text,              -- 'C','1B','2B','3B','SS','LF','CF','RF','DH','P'
    -- Manual overrides. NULL means "use the stat based rule" (see player_classification view).
    role_override    text CHECK (role_override IN ('SP','RP')),
    two_way_override boolean,
    grad_year        smallint,
    college_team_id  integer REFERENCES teams(id),
    agent_name       text,
    agent_contact    text,              -- only when publicly listed
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX players_name_trgm ON players USING gin (full_name gin_trgm_ops);  -- fast header search

-- One player shows up under different IDs on BR, school sites, and league sites.
-- This table is how scrapers match a row to the right person.
CREATE TABLE player_external_ids (
    player_id    integer REFERENCES players(id) ON DELETE CASCADE,
    source_id    integer REFERENCES sources(id),
    external_id  text NOT NULL,
    profile_url  text,
    fetched_at   timestamptz,                -- when the player's own page was last read
    PRIMARY KEY (source_id, external_id)
);

-- Potential duplicates the matcher was not sure about, for a human to resolve.
CREATE TABLE identity_review (
    id            serial PRIMARY KEY,
    candidate_a   integer REFERENCES players(id),
    candidate_b   integer REFERENCES players(id),
    match_score   numeric(4,3),
    resolved      boolean NOT NULL DEFAULT false
);


-- ------------------------------------------------------------
-- 3. Eligibility, status, transactions
-- ------------------------------------------------------------

CREATE TYPE eligibility_rule AS ENUM ('grad_2026_no_team', 'independent', 'released_affiliated');

CREATE TYPE signing_status AS ENUM (
    'free_agent',
    'signed_independent',
    'signed_affiliated',     -- leaves the eligible pool
    'returning_college',     -- grad or fifth year coming back, excluded
    'retired',               -- voluntary retirement list, excluded
    'unknown'
);

-- Evidence for each rule a player qualifies under. A player can have more than one row.
CREATE TABLE eligibility_evidence (
    player_id     integer REFERENCES players(id) ON DELETE CASCADE,
    rule          eligibility_rule NOT NULL,
    confirmed     boolean NOT NULL DEFAULT false,
    source_id     integer REFERENCES sources(id),
    source_url    text,
    verified_at   timestamptz NOT NULL DEFAULT now(),
    notes         text,
    PRIMARY KEY (player_id, rule)
);

-- Current snapshot shown in the row badge. Rebuilt from transactions on every refresh.
CREATE TABLE player_status (
    player_id        integer PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
    status           signing_status NOT NULL DEFAULT 'unknown',
    current_team_id  integer REFERENCES teams(id),
    status_date      date,
    for_season       smallint,          -- the season this status applies to (the upcoming season)
    last_txn_id      integer,
    unconfirmed      boolean NOT NULL DEFAULT true,   -- class year, release, or team not verified
    updated_at       timestamptz NOT NULL DEFAULT now()
);

-- What each type does to player_status is defined in scrapers/transactions.py (STATUS_EFFECT).
CREATE TYPE txn_type AS ENUM (
    'signed',            -- signed to an independent roster
    'contract_sold',     -- sold or transferred to an MLB organization (signed_affiliated)
    'released',          -- released, irrevocable waivers, cleared waivers (free_agent)
    'traded',            -- traded, acquired, received, claimed (team changes, stays independent)
    'drafted',
    'retired',
    'suspended',
    'injury',            -- injury list moves and reinstatements, no status change
    'other'
);

CREATE TABLE transactions (
    id            serial PRIMARY KEY,
    player_id     integer REFERENCES players(id),     -- NULL until matched
    raw_name      text NOT NULL,                      -- name as printed in the report
    txn_date      date NOT NULL,
    txn           txn_type NOT NULL,
    from_team_id  integer REFERENCES teams(id),
    to_team_id    integer REFERENCES teams(id),
    status_effect signing_status,                     -- status this move leaves him in (NULL = no change)
    team_name     text,                               -- team header the line sat under
    counterparty  text,                               -- other club named in the line, as printed
    raw_text      text,                               -- original line from the report
    source_id     integer REFERENCES sources(id),
    source_url    text,
    pulled_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (raw_name, txn_date, txn, source_id)
);
CREATE INDEX transactions_player_date ON transactions (player_id, txn_date DESC);


-- ------------------------------------------------------------
-- 4. Raw stats
-- ------------------------------------------------------------

-- split examples: 'total', 'vs_lhp', 'vs_rhp', 'home', 'away', 'm04', 'm05' ... 'm09'
CREATE TABLE batting_stats (
    id          bigserial PRIMARY KEY,
    player_id   integer NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    season      smallint NOT NULL,
    team_id     integer NOT NULL REFERENCES teams(id),
    split       text NOT NULL DEFAULT 'total',
    g    smallint, pa  smallint, ab  smallint, r   smallint, h   smallint,
    b2   smallint, b3  smallint, hr  smallint, rbi smallint,
    bb   smallint, ibb smallint, so  smallint, hbp smallint,
    sf   smallint, sh  smallint, sb  smallint, cs  smallint, gdp smallint,
    source_id   integer NOT NULL REFERENCES sources(id),
    pulled_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (player_id, season, team_id, split)
);

CREATE TABLE pitching_stats (
    id          bigserial PRIMARY KEY,
    player_id   integer NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    season      smallint NOT NULL,
    team_id     integer NOT NULL REFERENCES teams(id),
    split       text NOT NULL DEFAULT 'total',
    w    smallint, l   smallint, g   smallint, gs  smallint, cg smallint,
    sho  smallint, sv  smallint,
    outs integer,                           -- IP * 3
    bf   smallint, h   smallint, r   smallint, er  smallint, hr smallint,
    bb   smallint, ibb smallint, so  smallint, hbp smallint,
    wp   smallint, bk  smallint,
    -- Batted ball inputs for xFIP and SIERA. Usually NULL for college and indy.
    gb   smallint, fb  smallint, ld  smallint, iffb smallint,
    source_id   integer NOT NULL REFERENCES sources(id),
    pulled_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (player_id, season, team_id, split)
);

CREATE TABLE fielding_stats (
    id          bigserial PRIMARY KEY,
    player_id   integer NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    season      smallint NOT NULL,
    team_id     integer NOT NULL REFERENCES teams(id),
    position    text NOT NULL,
    g    smallint, gs  smallint,
    outs integer,                           -- defensive innings * 3
    po   smallint, a   smallint, e   smallint, dp  smallint,
    pb   smallint, sb_against smallint, cs_by smallint,   -- catchers
    source_id   integer NOT NULL REFERENCES sources(id),
    pulled_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (player_id, season, team_id, position)
);

-- Game logs: one row per player per game. Pulled from the player's game log page.
-- game_no separates the two games of a doubleheader.
CREATE TABLE batting_games (
    id          bigserial PRIMARY KEY,
    player_id   integer NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    season      smallint NOT NULL,
    game_date   date NOT NULL,
    game_no     smallint NOT NULL DEFAULT 1,
    team_id     integer REFERENCES teams(id),
    opponent    text,
    home_away   char(1) CHECK (home_away IN ('H', 'A', 'N')),
    result      text,                       -- as printed, e.g. 'W 7-3'
    pa   smallint, ab  smallint, r   smallint, h   smallint, b2  smallint, b3 smallint, hr smallint,
    rbi  smallint, bb  smallint, ibb smallint, so  smallint, hbp smallint, sf smallint, sh smallint,
    sb   smallint, cs  smallint,
    source_id   integer REFERENCES sources(id),
    pulled_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (player_id, game_date, game_no)
);

CREATE TABLE pitching_games (
    id          bigserial PRIMARY KEY,
    player_id   integer NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    season      smallint NOT NULL,
    game_date   date NOT NULL,
    game_no     smallint NOT NULL DEFAULT 1,
    team_id     integer REFERENCES teams(id),
    opponent    text,
    home_away   char(1) CHECK (home_away IN ('H', 'A', 'N')),
    result      text,
    started     boolean,                    -- NULL when the source does not say
    decision    text,                       -- 'W', 'L', 'S', 'H', 'BS'
    outs integer, bf smallint, h smallint, r smallint, er smallint, hr smallint,
    bb   smallint, ibb smallint, so smallint, hbp smallint, wp smallint, bk smallint,
    pitches smallint, strikes smallint,
    source_id   integer REFERENCES sources(id),
    pulled_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (player_id, game_date, game_no)
);
CREATE INDEX batting_games_season ON batting_games (player_id, season);
CREATE INDEX pitching_games_season ON pitching_games (player_id, season);

-- Sparse by nature. Only filled when a source actually publishes it.
CREATE TABLE pitch_tracking (
    player_id   integer REFERENCES players(id) ON DELETE CASCADE,
    season      smallint NOT NULL,
    pitch_type  text NOT NULL,              -- 'FF','SI','SL','CU','CH'...
    pitches     integer,
    velo_avg    numeric(4,1),
    velo_max    numeric(4,1),
    spin_avg    integer,
    ivb_in      numeric(4,1),
    hb_in       numeric(4,1),
    extension_ft numeric(3,1),
    source_id   integer REFERENCES sources(id),
    pulled_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (player_id, season, pitch_type, source_id)
);

CREATE TABLE batted_ball (
    player_id     integer REFERENCES players(id) ON DELETE CASCADE,
    season        smallint NOT NULL,
    bbe           integer,
    ev_avg        numeric(4,1),
    ev_max        numeric(4,1),
    ev_90th       numeric(4,1),
    la_avg        numeric(4,1),
    hard_hit_pct  numeric(4,3),
    source_id     integer REFERENCES sources(id),
    pulled_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (player_id, season, source_id)
);


-- ------------------------------------------------------------
-- 5. Calculated metrics
-- ------------------------------------------------------------

-- Every formula the UI shows lives here, so the math is always visible and checkable.
CREATE TABLE metric_definitions (
    key             text PRIMARY KEY,        -- 'woba', 'wrc_plus', 'fip', 'xfip', 'siera'...
    label           text NOT NULL,
    applies_to      text NOT NULL CHECK (applies_to IN ('batting','pitching','fielding')),
    formula_text    text NOT NULL,           -- human readable, shown on hover
    required_inputs text[] NOT NULL,         -- if any are NULL, metric is NULL
    min_sample      integer,                 -- PA or BF threshold for the small sample flag
    higher_is_better boolean NOT NULL
);

-- Materialized views, refreshed after each scrape run. Sketch of the batting one:
--
-- CREATE MATERIALIZED VIEW batting_metrics AS
-- SELECT b.*, ts.league_id, ts.park_id,
--        h / NULLIF(ab,0)                                    AS avg,
--        (h+bb+hbp) / NULLIF(ab+bb+hbp+sf,0)                 AS obp,
--        ... slg, ops, iso, babip, k_pct, bb_pct ...
--        (ls.w_bb*(bb-ibb) + ls.w_hbp*hbp + ls.w_1b*(h-b2-b3-hr)
--          + ls.w_2b*b2 + ls.w_3b*b3 + ls.w_hr*hr)
--          / NULLIF(ab+bb-ibb+sf+hbp,0)                      AS woba,
--        ... wrc_plus using ls.runs_per_pa and park factor ...
--        ... adjusted columns: *_adj = raw value after park, altitude, and strength factor ...
--        (pa < md.min_sample)                                AS small_sample
-- FROM batting_stats b
-- JOIN team_seasons ts USING (team_id, season)
-- JOIN league_seasons ls ON ls.league_id = ts.league_id AND ls.season = b.season
-- ...;
--
-- pitching_metrics follows the same pattern (ERA, WHIP, K%, BB%, K-BB%, FIP, xFIP, SIERA),
-- and both views expose raw and adjusted values side by side.

-- Pitcher role
-- Looks at a pitcher's last three seasons, weighted 3 / 2 / 1 toward the most recent.
-- weighted_gs_share = sum(weight * GS) / sum(weight * G). Starter when >= 0.50.
-- A one season pitcher is judged on that season alone. role_override wins when set.
CREATE VIEW pitcher_role AS
WITH by_season AS (
    SELECT player_id, season, SUM(g) AS g, SUM(gs) AS gs
    FROM pitching_stats
    WHERE split = 'total'
    GROUP BY player_id, season
    HAVING SUM(g) > 0
),
ranked AS (
    SELECT *, row_number() OVER (PARTITION BY player_id ORDER BY season DESC) AS recency
    FROM by_season
)
SELECT r.player_id,
       ROUND(SUM((4 - recency) * COALESCE(gs,0))::numeric / NULLIF(SUM((4 - recency) * g), 0), 3)
           AS weighted_gs_share,
       COUNT(*) AS seasons_used,
       COALESCE(p.role_override,
                CASE WHEN SUM((4 - recency) * COALESCE(gs,0))::numeric
                          / NULLIF(SUM((4 - recency) * g), 0) >= 0.5
                     THEN 'SP' ELSE 'RP' END) AS role,
       (p.role_override IS NOT NULL) AS role_overridden
FROM ranked r
JOIN players p ON p.id = r.player_id
WHERE recency <= 3
GROUP BY r.player_id, p.role_override;

-- Two way players
-- Rule: at least 50 PA and 20 IP (60 outs) in the same season, within his last three seasons.
-- PA falls back to AB + BB + HBP + SF + SH when a source does not publish PA.
-- two_way_override wins when set (true forces in, false forces out).
CREATE VIEW two_way_status AS
WITH bat AS (
    SELECT player_id, season,
           SUM(COALESCE(pa, ab + COALESCE(bb,0) + COALESCE(hbp,0) + COALESCE(sf,0) + COALESCE(sh,0))) AS pa
    FROM batting_stats WHERE split = 'total'
    GROUP BY player_id, season
),
pit AS (
    SELECT player_id, season, SUM(outs) AS outs
    FROM pitching_stats WHERE split = 'total'
    GROUP BY player_id, season
),
seasons AS (
    SELECT player_id, season,
           row_number() OVER (PARTITION BY player_id ORDER BY season DESC) AS recency
    FROM (SELECT player_id, season FROM bat UNION SELECT player_id, season FROM pit) s
)
SELECT p.id AS player_id,
       COALESCE(bool_or(b.pa >= 50 AND t.outs >= 60), false) AS meets_rule,
       COALESCE(p.two_way_override, bool_or(b.pa >= 50 AND t.outs >= 60), false) AS is_two_way,
       (p.two_way_override IS NOT NULL) AS two_way_overridden
FROM players p
LEFT JOIN seasons s ON s.player_id = p.id AND s.recency <= 3
LEFT JOIN bat b ON b.player_id = s.player_id AND b.season = s.season
LEFT JOIN pit t ON t.player_id = s.player_id AND t.season = s.season
GROUP BY p.id, p.two_way_override;

-- The eligible pool. Every list page reads from this, which enforces the hard filter in one place.
CREATE VIEW eligible_players AS
SELECT p.*,
       s.status,
       s.current_team_id,
       s.status_date,
       s.unconfirmed,
       (s.status = 'free_agent') AS can_sign_now,     -- drives the eligible to sign flag in each row
       array_agg(e.rule ORDER BY e.rule) AS rules,
       pr.role       AS pitcher_role,
       tw.is_two_way
FROM players p
JOIN player_status s        ON s.player_id = p.id
JOIN eligibility_evidence e ON e.player_id = p.id
LEFT JOIN pitcher_role pr   ON pr.player_id = p.id
LEFT JOIN two_way_status tw ON tw.player_id = p.id
WHERE s.status NOT IN ('signed_affiliated', 'returning_college', 'retired')
GROUP BY p.id, s.status, s.current_team_id, s.status_date, s.unconfirmed, pr.role, tw.is_two_way;


-- ------------------------------------------------------------
-- 6. Scouting side
-- ------------------------------------------------------------

-- Staff accounts come from Supabase Auth (auth.users). This adds name and role.
CREATE TABLE staff (
    user_id    uuid PRIMARY KEY,           -- references auth.users(id)
    full_name  text NOT NULL,
    role       text NOT NULL DEFAULT 'scout' CHECK (role IN ('admin','scout','viewer'))
);

CREATE TYPE marker_status AS ENUM ('looking_to_sign', 'potential', 'already_reviewed');

-- One shared, team wide marker per player. Drives the Scouted Players tab.
CREATE TABLE player_markers (
    player_id   integer PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
    status      marker_status NOT NULL,
    set_by      uuid REFERENCES staff(user_id),
    set_at      timestamptz NOT NULL DEFAULT now()
);

-- Full history so you can see who changed a marker and when.
CREATE TABLE player_marker_log (
    id          bigserial PRIMARY KEY,
    player_id   integer REFERENCES players(id) ON DELETE CASCADE,
    status      marker_status,              -- NULL means the marker was cleared
    set_by      uuid REFERENCES staff(user_id),
    set_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE scouting_reports (
    id           serial PRIMARY KEY,
    player_id    integer REFERENCES players(id) ON DELETE CASCADE,
    author_id    uuid REFERENCES staff(user_id),
    report_date  date NOT NULL DEFAULT current_date,
    summary      text,
    overall_fv   smallint CHECK (overall_fv BETWEEN 20 AND 80),
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- Key/value grades so hitters and pitchers use the same table.
-- Hitter tools: hit, power, run, field, arm. Pitcher tools: fb, sl, cb, ch, cut, spl, command.
CREATE TABLE report_grades (
    report_id   integer REFERENCES scouting_reports(id) ON DELETE CASCADE,
    tool        text NOT NULL,
    present     smallint CHECK (present BETWEEN 20 AND 80),
    future      smallint CHECK (future  BETWEEN 20 AND 80),
    PRIMARY KEY (report_id, tool)
);

CREATE TABLE player_notes (
    id          bigserial PRIMARY KEY,
    player_id   integer REFERENCES players(id) ON DELETE CASCADE,
    author_id   uuid REFERENCES staff(user_id),
    body        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE tags (
    id    serial PRIMARY KEY,
    name  text NOT NULL UNIQUE
);

CREATE TABLE player_tags (
    player_id  integer REFERENCES players(id) ON DELETE CASCADE,
    tag_id     integer REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (player_id, tag_id)
);

CREATE TABLE awards (
    id          serial PRIMARY KEY,
    player_id   integer REFERENCES players(id) ON DELETE CASCADE,
    season      smallint,
    award       text NOT NULL,              -- 'First Team All Big West'
    source_url  text
);

CREATE TABLE injuries (
    id            serial PRIMARY KEY,
    player_id     integer REFERENCES players(id) ON DELETE CASCADE,
    start_date    date,
    end_date      date,
    description   text,
    games_missed  smallint,
    source_url    text                       -- only publicly reported injuries
);

CREATE TABLE media_links (
    id         serial PRIMARY KEY,
    player_id  integer REFERENCES players(id) ON DELETE CASCADE,
    kind       text NOT NULL CHECK (kind IN ('video','article','profile')),
    title      text,
    url        text NOT NULL
);


-- ------------------------------------------------------------
-- 7. App support
-- ------------------------------------------------------------

CREATE TABLE saved_views (
    id         serial PRIMARY KEY,
    owner_id   uuid REFERENCES staff(user_id),
    name       text NOT NULL,
    page       text NOT NULL CHECK (page IN ('position','pitchers','two_way','scouted')),
    filters    jsonb NOT NULL DEFAULT '{}',   -- {"ops":{"min":0.850},"position":["SS","2B"]}
    columns    jsonb NOT NULL DEFAULT '[]',
    sort       jsonb NOT NULL DEFAULT '[]',
    shared     boolean NOT NULL DEFAULT true
);

-- Adjustable weights for the candidate ranking. The weights are the formula, so it stays transparent.
CREATE TABLE ranking_profiles (
    id         serial PRIMARY KEY,
    owner_id   uuid REFERENCES staff(user_id),
    name       text NOT NULL,                 -- 'Need: LH reliever'
    page       text NOT NULL,
    weights    jsonb NOT NULL,                -- {"k_bb_pct":0.4,"fip_adj":0.4,"gb_pct":0.2}
    shared     boolean NOT NULL DEFAULT true
);

-- Current Boise Hawks roster for the roster needs view.
CREATE TABLE hawks_roster (
    season       smallint NOT NULL,
    player_name  text NOT NULL,
    player_id    integer REFERENCES players(id),
    position     text NOT NULL,
    bats         hand,
    throws       hand,
    PRIMARY KEY (season, player_name)
);


-- ------------------------------------------------------------
-- 8. Scrape bookkeeping
-- ------------------------------------------------------------

CREATE TABLE scrape_runs (
    id             serial PRIMARY KEY,
    source_id      integer REFERENCES sources(id),
    started_at     timestamptz NOT NULL DEFAULT now(),
    finished_at    timestamptz,
    status         text CHECK (status IN ('running','ok','partial','failed')),
    rows_upserted  integer DEFAULT 0,
    error_log      text
);

-- Page cache so reruns do not hit sites again unless the content is stale.
CREATE TABLE page_cache (
    url           text PRIMARY KEY,
    source_id     integer REFERENCES sources(id),
    fetched_at    timestamptz NOT NULL,
    http_status   smallint,
    content_hash  text,
    storage_path  text                        -- raw HTML kept in object storage, not in the table
);
