-- ============================================================
-- Web layer: the views the site reads, and marker history.
-- Runs after schema.sql. Plain Postgres, so it is tested locally.
-- Supabase specific pieces (logins, row level security) live in supabase.sql.
--
-- Stats in this file are the ones that need nothing beyond the raw counts:
--   AVG, OBP, SLG, OPS, ISO, BABIP, K%, BB%, ERA, WHIP, K/9, BB/9, HR/9, K%, BB%, K-BB%, FIP.
-- FIP uses a constant computed from each league's own totals, never MLB's.
-- wOBA, wRC+, xFIP, SIERA, and the park, altitude, and strength adjustments come next.
-- ============================================================


-- Views are dropped and rebuilt so this file can be rerun after any change to them.
DROP VIEW IF EXISTS ui_two_way, ui_pitchers, ui_hitters, ui_players, ui_fielding_seasons,
                    ui_pitching_seasons, ui_batting_seasons, ui_batting_games, ui_pitching_games,
                    league_fip_constants, eligible_players, pitcher_role, two_way_status CASCADE;


-- ------------------------------------------------------------
-- Roles, two way status, and the eligible pool
-- ------------------------------------------------------------

-- Pitcher role
-- Looks at a pitcher's last three seasons, weighted 3 / 2 / 1 toward the most recent.
-- weighted_gs_share = sum(weight * GS) / sum(weight * G). Starter when >= 0.50.
-- A one season pitcher is judged on that season alone. role_override wins when set.
CREATE VIEW pitcher_role WITH (security_invoker = true) AS
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
CREATE VIEW two_way_status WITH (security_invoker = true) AS
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
CREATE VIEW eligible_players WITH (security_invoker = true) AS
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
-- Marker history: every change to player_markers is logged automatically
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION log_marker_change() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        INSERT INTO player_marker_log (player_id, status, set_by) VALUES (OLD.player_id, NULL, OLD.set_by);
        RETURN OLD;
    END IF;
    INSERT INTO player_marker_log (player_id, status, set_by) VALUES (NEW.player_id, NEW.status, NEW.set_by);
    NEW.set_at := now();
    RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS player_markers_log ON player_markers;
CREATE TRIGGER player_markers_log
    BEFORE INSERT OR UPDATE OR DELETE ON player_markers
    FOR EACH ROW EXECUTE FUNCTION log_marker_change();


-- ------------------------------------------------------------
-- League FIP constants, from each league's own totals
--   cFIP = lgERA - (13*HR + 3*(BB+HBP) - 2*K) / IP
-- Only calculated for leagues marked complete (every player loaded), such as the Pioneer League.
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW league_fip_constants WITH (security_invoker = true) AS
SELECT ts.league_id, ps.season,
       SUM(ps.outs) AS lg_outs,
       ROUND(9.0 * SUM(ps.er) / NULLIF(SUM(ps.outs) / 3.0, 0), 3) AS lg_era,
       ROUND(9.0 * SUM(ps.er) / NULLIF(SUM(ps.outs) / 3.0, 0)
             - (13.0 * SUM(ps.hr) + 3.0 * (SUM(ps.bb) + SUM(COALESCE(ps.hbp, 0))) - 2.0 * SUM(ps.so))
               / NULLIF(SUM(ps.outs) / 3.0, 0), 3) AS fip_constant
FROM pitching_stats ps
JOIN team_seasons ts ON ts.team_id = ps.team_id AND ts.season = ps.season
JOIN leagues lg ON lg.id = ts.league_id AND lg.complete     -- partial leagues would skew the constant
WHERE ps.split = 'total'
GROUP BY ts.league_id, ps.season;


-- ------------------------------------------------------------
-- Season lines: one row per player, season, and league (clubs in the same league combined).
-- Split by league so a 2026 college senior who signed in the summer keeps his college and pro
-- numbers apart. is_pro marks independent and affiliated leagues.
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW ui_batting_seasons WITH (security_invoker = true) AS
WITH raw AS (
    SELECT b.player_id, b.season, COALESCE(ts.league_id, 0) AS league_key,
           bool_or(t.org IN ('independent', 'affiliated')) AS is_pro,
           string_agg(DISTINCT t.name, ', ') AS teams,
           string_agg(DISTINCT l.name, ', ') AS leagues,
           SUM(b.g) AS g,
           SUM(COALESCE(b.pa, b.ab + COALESCE(b.bb,0) + COALESCE(b.hbp,0) + COALESCE(b.sf,0) + COALESCE(b.sh,0))) AS pa,
           SUM(b.ab) AS ab, SUM(b.r) AS r, SUM(b.h) AS h, SUM(b.b2) AS b2, SUM(b.b3) AS b3, SUM(b.hr) AS hr,
           SUM(b.rbi) AS rbi, SUM(b.bb) AS bb, SUM(b.so) AS so, SUM(COALESCE(b.hbp,0)) AS hbp,
           SUM(COALESCE(b.sf,0)) AS sf, SUM(b.sb) AS sb, SUM(b.cs) AS cs
    FROM batting_stats b
    JOIN teams t ON t.id = b.team_id
    LEFT JOIN team_seasons ts ON ts.team_id = b.team_id AND ts.season = b.season
    LEFT JOIN leagues l ON l.id = ts.league_id
    WHERE b.split = 'total'
    GROUP BY b.player_id, b.season, COALESCE(ts.league_id, 0)
)
SELECT r.*,
       ROUND(h::numeric / NULLIF(ab, 0), 3) AS avg,
       ROUND((h + bb + hbp)::numeric / NULLIF(ab + bb + hbp + sf, 0), 3) AS obp,
       ROUND((h + b2 + 2 * b3 + 3 * hr)::numeric / NULLIF(ab, 0), 3) AS slg,
       ROUND((h + bb + hbp)::numeric / NULLIF(ab + bb + hbp + sf, 0)
             + (h + b2 + 2 * b3 + 3 * hr)::numeric / NULLIF(ab, 0), 3) AS ops,
       ROUND((b2 + 2 * b3 + 3 * hr)::numeric / NULLIF(ab, 0), 3) AS iso,
       ROUND((h - hr)::numeric / NULLIF(ab - so - hr + sf, 0), 3) AS babip,
       ROUND(100.0 * so / NULLIF(pa, 0), 1) AS k_pct,
       ROUND(100.0 * bb / NULLIF(pa, 0), 1) AS bb_pct,
       (pa < 100) AS small_sample,
       CASE WHEN is_pro THEN (SELECT count(*) FROM batting_games g WHERE g.player_id = r.player_id AND g.season = r.season)
            ELSE 0 END AS games_logged
FROM raw r;

CREATE OR REPLACE VIEW ui_pitching_seasons WITH (security_invoker = true) AS
WITH rows AS (
    SELECT p.*, t.name AS team, t.org AS team_org, l.name AS league, COALESCE(ts.league_id, 0) AS league_key, c.fip_constant
    FROM pitching_stats p
    JOIN teams t ON t.id = p.team_id
    LEFT JOIN team_seasons ts ON ts.team_id = p.team_id AND ts.season = p.season
    LEFT JOIN leagues l ON l.id = ts.league_id
    LEFT JOIN league_fip_constants c ON c.league_id = ts.league_id AND c.season = p.season
    WHERE p.split = 'total'
),
raw AS (
    SELECT player_id, season, league_key,
           bool_or(team_org IN ('independent', 'affiliated')) AS is_pro,
           string_agg(DISTINCT team, ', ') AS teams,
           string_agg(DISTINCT league, ', ') AS leagues,
           SUM(w) AS w, SUM(l) AS l, SUM(g) AS g, SUM(COALESCE(gs,0)) AS gs, SUM(sv) AS sv,
           SUM(outs) AS outs, SUM(bf) AS bf, SUM(h) AS h, SUM(r) AS r, SUM(er) AS er, SUM(hr) AS hr,
           SUM(bb) AS bb, SUM(so) AS so, SUM(COALESCE(hbp,0)) AS hbp,
           -- IP weighted league constant, so a pitcher who changed leagues gets a fair blend
           SUM(fip_constant * outs) / NULLIF(SUM(outs) FILTER (WHERE fip_constant IS NOT NULL), 0) AS fip_c
    FROM rows
    GROUP BY player_id, season, league_key
)
SELECT player_id, season, league_key, is_pro, teams, leagues, w, l, g, gs, sv, outs, bf, h, r, er, hr, bb, so, hbp,
       -- display innings in baseball notation: 45.2 means 45 and two thirds
       (outs / 3) + (outs % 3) / 10.0 AS ip,
       ROUND(9.0 * er / NULLIF(outs / 3.0, 0), 2) AS era,
       ROUND((bb + h) / NULLIF(outs / 3.0, 0), 2) AS whip,
       ROUND(9.0 * so / NULLIF(outs / 3.0, 0), 1) AS k9,
       ROUND(9.0 * bb / NULLIF(outs / 3.0, 0), 1) AS bb9,
       ROUND(9.0 * hr / NULLIF(outs / 3.0, 0), 1) AS hr9,
       ROUND(100.0 * so / NULLIF(bf, 0), 1) AS k_pct,          -- NULL when the source has no batters faced
       ROUND(100.0 * bb / NULLIF(bf, 0), 1) AS bb_pct,
       ROUND(100.0 * (so - bb) / NULLIF(bf, 0), 1) AS k_bb_pct,
       ROUND((13.0 * hr + 3.0 * (bb + hbp) - 2.0 * so) / NULLIF(outs / 3.0, 0) + fip_c, 2) AS fip,
       (outs < 90) AS small_sample,                               -- under 30 IP
       CASE WHEN is_pro THEN (SELECT count(*) FROM pitching_games g WHERE g.player_id = raw.player_id AND g.season = raw.season)
            ELSE 0 END AS games_logged
FROM raw;

CREATE OR REPLACE VIEW ui_fielding_seasons WITH (security_invoker = true) AS
SELECT f.player_id, f.season, f.position, COALESCE(ts.league_id, 0) AS league_key,
       string_agg(DISTINCT t.name, ', ') AS teams,
       SUM(f.g) AS g, SUM(f.outs) AS outs, SUM(f.po) AS po, SUM(f.a) AS a, SUM(f.e) AS e, SUM(f.dp) AS dp,
       SUM(f.pb) AS pb, SUM(f.sb_against) AS sb_against, SUM(f.cs_by) AS cs_by,
       ROUND((SUM(f.po) + SUM(f.a))::numeric / NULLIF(SUM(f.po) + SUM(f.a) + SUM(f.e), 0), 3) AS fpct,
       ROUND(100.0 * SUM(f.cs_by) / NULLIF(SUM(f.sb_against) + SUM(f.cs_by), 0), 1) AS cs_pct
FROM fielding_stats f
JOIN teams t ON t.id = f.team_id
LEFT JOIN team_seasons ts ON ts.team_id = f.team_id AND ts.season = f.season
GROUP BY f.player_id, f.season, f.position, COALESCE(ts.league_id, 0);


-- ------------------------------------------------------------
-- Game logs as the site shows them
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW ui_batting_games WITH (security_invoker = true) AS
SELECT g.id, g.player_id, g.season, g.game_date, g.game_no, t.name AS team, g.opponent, g.home_away, g.result,
       COALESCE(g.pa, g.ab + COALESCE(g.bb,0) + COALESCE(g.hbp,0) + COALESCE(g.sf,0) + COALESCE(g.sh,0)) AS pa,
       g.ab, g.r, g.h, g.b2, g.b3, g.hr, g.rbi, g.bb, g.so, g.hbp, g.sf, g.sb, g.cs
FROM batting_games g
LEFT JOIN teams t ON t.id = g.team_id;

CREATE OR REPLACE VIEW ui_pitching_games WITH (security_invoker = true) AS
SELECT g.id, g.player_id, g.season, g.game_date, g.game_no, t.name AS team, g.opponent, g.home_away, g.result,
       g.started, g.decision, g.outs,
       (g.outs / 3) + (g.outs % 3) / 10.0 AS ip,
       g.bf, g.h, g.r, g.er, g.hr, g.bb, g.so, g.hbp, g.wp, g.pitches, g.strikes
FROM pitching_games g
LEFT JOIN teams t ON t.id = g.team_id;


-- ------------------------------------------------------------
-- Players as the site shows them
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW ui_players WITH (security_invoker = true) AS
SELECT e.id, e.first_name, e.last_name, e.full_name,
       e.primary_position,
       CASE
           WHEN e.primary_position = 'C' THEN 'C'
           WHEN e.primary_position IN ('1B','2B','3B','SS','IF','INF','MIF','CIF','UT','UTL','UTIL') THEN 'IF'
           WHEN e.primary_position IN ('LF','CF','RF','OF') THEN 'OF'
           WHEN e.primary_position IN ('P','RHP','LHP','SP','RP') THEN 'P'
       END AS position_group,
       e.bats, e.throws, e.height_in, e.weight_lb,
       concat_ws(', ', e.hometown_city, e.hometown_state) AS hometown,
       e.high_school,
       e.grad_year,
       col.name AS college,
       -- Team column: his 2027 club if signed, otherwise the last professional team he played for.
       COALESCE(CASE WHEN e.status = 'signed_independent' THEN ct.name END, lp.team_name) AS team,
       lp.team_name AS last_pro_team,
       lp.season AS last_pro_season,
       e.status,
       CASE e.status
           WHEN 'free_agent' THEN 'Free Agent'
           WHEN 'signed_independent' THEN 'Signed'
           ELSE 'Unconfirmed'
       END AS status_label,
       ct.name AS status_team,
       e.status_date,
       e.unconfirmed,
       e.can_sign_now,
       e.rules,
       e.pitcher_role,
       COALESCE(e.is_two_way, false) AS is_two_way,
       m.status AS marker,
       m.set_at AS marker_set_at,
       st.full_name AS marker_set_by
FROM eligible_players e
LEFT JOIN teams col ON col.id = e.college_team_id
LEFT JOIN teams ct ON ct.id = e.current_team_id
LEFT JOIN player_markers m ON m.player_id = e.id
LEFT JOIN staff st ON st.user_id = m.set_by
LEFT JOIN LATERAL (
    SELECT t.name AS team_name, s.season
    FROM (SELECT player_id, season, team_id, COALESCE(g, 0) AS g FROM batting_stats WHERE split = 'total'
          UNION ALL
          SELECT player_id, season, team_id, COALESCE(g, 0) AS g FROM pitching_stats WHERE split = 'total') s
    JOIN teams t ON t.id = s.team_id AND t.org <> 'college'
    WHERE s.player_id = e.id
    ORDER BY s.season DESC, s.g DESC
    LIMIT 1
) lp ON true;


-- Each list page shows a player's most recent season. The pop up shows every season.

CREATE OR REPLACE VIEW ui_hitters WITH (security_invoker = true) AS
SELECT pl.*, b.season, b.teams, b.leagues, b.g, b.pa, b.ab, b.r, b.h, b.b2, b.b3, b.hr, b.rbi, b.bb, b.so,
       b.sb, b.cs, b.avg, b.obp, b.slg, b.ops, b.iso, b.babip, b.k_pct, b.bb_pct, b.small_sample
FROM ui_players pl
JOIN LATERAL (SELECT * FROM ui_batting_seasons s WHERE s.player_id = pl.id ORDER BY s.season DESC, s.is_pro DESC, s.pa DESC LIMIT 1) b ON true
WHERE pl.position_group IS DISTINCT FROM 'P' OR pl.is_two_way;

CREATE OR REPLACE VIEW ui_pitchers WITH (security_invoker = true) AS
SELECT pl.*, p.season, p.teams, p.leagues, p.w, p.l, p.g, p.gs, p.sv, p.ip, p.outs, p.h, p.er, p.hr, p.bb, p.so,
       p.era, p.whip, p.k9, p.bb9, p.hr9, p.k_pct, p.bb_pct, p.k_bb_pct, p.fip, p.small_sample
FROM ui_players pl
JOIN LATERAL (SELECT * FROM ui_pitching_seasons s WHERE s.player_id = pl.id ORDER BY s.season DESC, s.is_pro DESC, s.outs DESC LIMIT 1) p ON true
WHERE pl.position_group = 'P' OR pl.position_group IS NULL OR pl.is_two_way;

CREATE OR REPLACE VIEW ui_two_way WITH (security_invoker = true) AS
SELECT pl.*,
       COALESCE(b.teams, p.teams) AS teams,
       b.season AS bat_season, b.pa, b.avg, b.obp, b.slg, b.ops, b.hr, b.sb,
       p.season AS pit_season, p.ip, p.outs, p.era, p.whip, p.fip, p.so AS p_so, p.k9
FROM ui_players pl
LEFT JOIN LATERAL (SELECT * FROM ui_batting_seasons s WHERE s.player_id = pl.id ORDER BY s.season DESC, s.is_pro DESC, s.pa DESC LIMIT 1) b ON true
LEFT JOIN LATERAL (SELECT * FROM ui_pitching_seasons s WHERE s.player_id = pl.id ORDER BY s.season DESC, s.is_pro DESC, s.outs DESC LIMIT 1) p ON true
WHERE pl.is_two_way;
