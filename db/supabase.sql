-- ============================================================
-- Supabase only: logins and row level security.
-- Run once in the Supabase SQL editor after `python cli.py init-db`.
--
-- Rules:
--   * Nobody signed out can read anything. The site is public on GitHub Pages,
--     so this is what keeps the data private.
--   * Signed in staff can read every table and view.
--   * Signed in staff can set and clear markers. Everything else is written by the scrapers,
--     which connect with the database password and are not affected by these rules.
-- ============================================================

-- 1. Turn on row level security for every table, and allow reads for signed in staff.
DO $$
DECLARE t text;
BEGIN
    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS staff_read ON public.%I', t);
        EXECUTE format('CREATE POLICY staff_read ON public.%I FOR SELECT TO authenticated USING (true)', t);
    END LOOP;
END $$;

-- 2. Markers: any staff member can set, change, or clear one. The log is written by a trigger.
DROP POLICY IF EXISTS staff_write ON player_markers;
CREATE POLICY staff_write ON player_markers FOR ALL TO authenticated USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS staff_log ON player_marker_log;
CREATE POLICY staff_log ON player_marker_log FOR INSERT TO authenticated WITH CHECK (true);

ALTER TABLE player_markers ALTER COLUMN set_by SET DEFAULT auth.uid();
ALTER TABLE player_marker_log ALTER COLUMN set_by SET DEFAULT auth.uid();

-- 3. Signed out visitors get nothing, even if a policy is added by mistake later.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon;

-- 4. Every new login gets a staff row automatically (name taken from the invite, else the email).
CREATE OR REPLACE FUNCTION public.handle_new_staff() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
    INSERT INTO public.staff (user_id, full_name)
    VALUES (NEW.id, COALESCE(NEW.raw_user_meta_data ->> 'full_name', split_part(NEW.email, '@', 1)))
    ON CONFLICT (user_id) DO NOTHING;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_staff();

-- Backfill anyone invited before this ran.
INSERT INTO public.staff (user_id, full_name)
SELECT id, COALESCE(raw_user_meta_data ->> 'full_name', split_part(email, '@', 1)) FROM auth.users
ON CONFLICT (user_id) DO NOTHING;
