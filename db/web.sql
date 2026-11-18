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
-- Only trustworthy when the whole league is loaded (true for the Pioneer League).
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
WHERE ps.split = 'total'
GROUP BY ts.league_id, ps.season;


-- ------------------------------------------------------------
-- Season lines (one row per player per season, all clubs combined)
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW ui_batting_seasons WITH (security_invoker = true) AS
WITH raw AS (
    SELECT b.player_id, b.season,
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
    GROUP BY b.player_id, b.season
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
       (pa < 100) AS small_sample
FROM raw r;

CREATE OR REPLACE VIEW ui_pitching_seasons WITH (security_invoker = true) AS
WITH rows AS (
    SELECT p.*, t.name AS team, l.name AS league, c.fip_constant
    FROM pitching_stats p
    JOIN teams t ON t.id = p.team_id
    LEFT JOIN team_seasons ts ON ts.team_id = p.team_id AND ts.season = p.season
    LEFT JOIN leagues l ON l.id = ts.league_id
    LEFT JOIN league_fip_constants c ON c.league_id = ts.league_id AND c.season = p.season
    WHERE p.split = 'total'
),
raw AS (
    SELECT player_id, season,
           string_agg(DISTINCT team, ', ') AS teams,
           string_agg(DISTINCT league, ', ') AS leagues,
           SUM(w) AS w, SUM(l) AS l, SUM(g) AS g, SUM(COALESCE(gs,0)) AS gs, SUM(sv) AS sv,
           SUM(outs) AS outs, SUM(bf) AS bf, SUM(h) AS h, SUM(r) AS r, SUM(er) AS er, SUM(hr) AS hr,
           SUM(bb) AS bb, SUM(so) AS so, SUM(COALESCE(hbp,0)) AS hbp,
           -- IP weighted league constant, so a pitcher who changed leagues gets a fair blend
           SUM(fip_constant * outs) / NULLIF(SUM(outs) FILTER (WHERE fip_constant IS NOT NULL), 0) AS fip_c
    FROM rows
    GROUP BY player_id, season
)
SELECT player_id, season, teams, leagues, w, l, g, gs, sv, outs, bf, h, r, er, hr, bb, so, hbp,
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
       (outs < 90) AS small_sample                                -- under 30 IP
FROM raw;

CREATE OR REPLACE VIEW ui_fielding_seasons WITH (security_invoker = true) AS
SELECT f.player_id, f.season, f.position,
       string_agg(DISTINCT t.name, ', ') AS teams,
       SUM(f.g) AS g, SUM(f.outs) AS outs, SUM(f.po) AS po, SUM(f.a) AS a, SUM(f.e) AS e, SUM(f.dp) AS dp,
       SUM(f.pb) AS pb, SUM(f.sb_against) AS sb_against, SUM(f.cs_by) AS cs_by,
       ROUND((SUM(f.po) + SUM(f.a))::numeric / NULLIF(SUM(f.po) + SUM(f.a) + SUM(f.e), 0), 3) AS fpct,
       ROUND(100.0 * SUM(f.cs_by) / NULLIF(SUM(f.sb_against) + SUM(f.cs_by), 0), 1) AS cs_pct
FROM fielding_stats f
JOIN teams t ON t.id = f.team_id
GROUP BY f.player_id, f.season, f.position;


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
       e.grad_year,
       col.name AS college,
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
LEFT JOIN staff st ON st.user_id = m.set_by;


-- Each list page shows a player's most recent season. The pop up shows every season.

CREATE OR REPLACE VIEW ui_hitters WITH (security_invoker = true) AS
SELECT pl.*, b.season, b.teams, b.leagues, b.g, b.pa, b.ab, b.r, b.h, b.b2, b.b3, b.hr, b.rbi, b.bb, b.so,
       b.sb, b.cs, b.avg, b.obp, b.slg, b.ops, b.iso, b.babip, b.k_pct, b.bb_pct, b.small_sample
FROM ui_players pl
JOIN LATERAL (SELECT * FROM ui_batting_seasons s WHERE s.player_id = pl.id ORDER BY s.season DESC LIMIT 1) b ON true
WHERE pl.position_group IS DISTINCT FROM 'P' OR pl.is_two_way;

CREATE OR REPLACE VIEW ui_pitchers WITH (security_invoker = true) AS
SELECT pl.*, p.season, p.teams, p.leagues, p.w, p.l, p.g, p.gs, p.sv, p.ip, p.outs, p.h, p.er, p.hr, p.bb, p.so,
       p.era, p.whip, p.k9, p.bb9, p.hr9, p.k_pct, p.bb_pct, p.k_bb_pct, p.fip, p.small_sample
FROM ui_players pl
JOIN LATERAL (SELECT * FROM ui_pitching_seasons s WHERE s.player_id = pl.id ORDER BY s.season DESC LIMIT 1) p ON true
WHERE pl.position_group = 'P' OR pl.position_group IS NULL OR pl.is_two_way;

CREATE OR REPLACE VIEW ui_two_way WITH (security_invoker = true) AS
SELECT pl.*,
       COALESCE(b.teams, p.teams) AS teams,
       b.season AS bat_season, b.pa, b.avg, b.obp, b.slg, b.ops, b.hr, b.sb,
       p.season AS pit_season, p.ip, p.outs, p.era, p.whip, p.fip, p.so AS p_so, p.k9
FROM ui_players pl
LEFT JOIN LATERAL (SELECT * FROM ui_batting_seasons s WHERE s.player_id = pl.id ORDER BY s.season DESC LIMIT 1) b ON true
LEFT JOIN LATERAL (SELECT * FROM ui_pitching_seasons s WHERE s.player_id = pl.id ORDER BY s.season DESC LIMIT 1) p ON true
WHERE pl.is_two_way;
