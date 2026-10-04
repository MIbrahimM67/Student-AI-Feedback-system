-- Apply as the schema owner AFTER postgres/init.sql, never using app_user.
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user' AND (rolsuper OR rolbypassrls)) THEN
        RAISE EXCEPTION 'app_user must be created with SQL as a restricted role';
    END IF;
END $$;
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS plan TEXT DEFAULT 'free';
ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_status TEXT DEFAULT 'inactive';
ALTER TABLE users ADD COLUMN IF NOT EXISTS current_period_end TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS demo_files (
    id UUID PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES organizations(id),
    owner_uid TEXT NOT NULL REFERENCES users(uid) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    content BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE demo_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE demo_files FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON demo_files;
CREATE POLICY tenant_isolation ON demo_files
    USING (org_id = nullif(current_setting('app.current_org_id', true), '')::uuid)
    WITH CHECK (org_id = nullif(current_setting('app.current_org_id', true), '')::uuid);

-- Internal service metadata. These tables have no public API routes.
CREATE TABLE IF NOT EXISTS demo_storage_budget (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    bytes_used BIGINT NOT NULL DEFAULT 0 CHECK (bytes_used >= 0)
);
INSERT INTO demo_storage_budget(id) VALUES (1) ON CONFLICT DO NOTHING;
CREATE OR REPLACE FUNCTION demo_release_storage() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
    UPDATE demo_storage_budget SET bytes_used = greatest(0, bytes_used - octet_length(OLD.content)) WHERE id = 1;
    RETURN OLD;
END $$;
DROP TRIGGER IF EXISTS demo_release_storage ON demo_files;
CREATE TRIGGER demo_release_storage AFTER DELETE ON demo_files
    FOR EACH ROW EXECUTE FUNCTION demo_release_storage();

CREATE TABLE IF NOT EXISTS demo_jobs (
    id BIGSERIAL PRIMARY KEY,
    task TEXT NOT NULL CHECK (task IN ('tasks.grade_submission','tasks.index_reference_material')),
    target_id UUID NOT NULL,
    org_id UUID NOT NULL REFERENCES organizations(id),
    subject_id UUID,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','done','failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    UNIQUE(task, target_id)
);
GRANT SELECT, INSERT, UPDATE, DELETE ON demo_files, demo_jobs TO app_user;
GRANT SELECT, UPDATE ON demo_storage_budget TO app_user;
GRANT USAGE, SELECT ON SEQUENCE demo_jobs_id_seq TO app_user;
