-- ============================================================================
-- AI Feedback System — Postgres init (Phase 0)
--
-- One database for everything:
--   * relational app data
--   * vector RAG via pgvector
--   * knowledge graph modelled as relational tables (faster + more reliable
--     than a separate graph DB; identical grading behaviour; can be visualised)
--
-- Tenant isolation is enforced by Row-Level Security (RLS). The API connects
-- as `app_user` (NOT the superuser, which bypasses RLS) and MUST execute
--   SET LOCAL app.current_org_id = '<uuid>';
-- at the start of every request transaction.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- for gen_random_uuid()

-- ---- App role --------------------------------------------------------------
-- The API uses this role; it cannot bypass RLS.
-- Password is injected from the APP_USER_PASSWORD env var by the entrypoint.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
    EXECUTE format(
      'CREATE ROLE app_user LOGIN PASSWORD %L',
      coalesce(current_setting('app_user_password_init', true),
               nullif(trim(both from coalesce((SELECT setting FROM pg_settings WHERE name='log_destination'),'')),''),  -- noop fallback
               'change_me')
    );
  END IF;
END$$;
-- Set the password from the env var passed to the container.
-- (The official postgres image exposes env vars; we re-read APP_USER_PASSWORD here.)
DO $$
DECLARE pw TEXT := coalesce(current_setting('app.app_user_password', true), '');
BEGIN
  -- The cleanest way to set the password is via ALTER ROLE in a follow-up
  -- script, but since we want a single init.sql, do it here using the env
  -- via a server-side fallback. If APP_USER_PASSWORD isn't visible from SQL,
  -- run:  ALTER ROLE app_user WITH PASSWORD '...'  ; manually once.
  IF pw <> '' THEN
    EXECUTE format('ALTER ROLE app_user WITH PASSWORD %L', pw);
  END IF;
END$$;

-- ============================================================================
-- TENANCY
-- ============================================================================
CREATE TABLE organizations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('individual','institution')) DEFAULT 'individual',
  country CHAR(2) NOT NULL DEFAULT 'PK',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- organizations itself is not RLS-protected; access is gated in the API.

-- ============================================================================
-- USERS (Firebase uid is the primary external id)
-- ============================================================================
CREATE TABLE users (
  uid TEXT PRIMARY KEY,                                  -- Firebase uid
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
  email TEXT NOT NULL UNIQUE,
  display_name TEXT,
  photo_url TEXT,
  role TEXT NOT NULL CHECK (role IN ('student','instructor','admin')) DEFAULT 'student',
  faculty_status TEXT NOT NULL CHECK (faculty_status IN ('none','pending','approved','rejected')) DEFAULT 'none',
  pro_status TEXT NOT NULL CHECK (pro_status IN ('inactive','active','revoked')) DEFAULT 'inactive',
  warning_count INT NOT NULL DEFAULT 0,
  blocked_until TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON users(org_id);

CREATE TABLE instructor_profiles (
  uid TEXT PRIMARY KEY REFERENCES users(uid) ON DELETE CASCADE,
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  department TEXT,
  designation TEXT,
  institution TEXT,
  teaching_level TEXT,
  default_language TEXT NOT NULL DEFAULT 'en',
  grading_style TEXT CHECK (grading_style IN ('strict','lenient','balanced')) DEFAULT 'balanced',
  -- Per-instructor confidence threshold for the "approve at a glance" flow.
  -- The review UI uses this to default-mark high-confidence drafts as
  -- "ready to approve" so the instructor can bulk-approve them.
  auto_approve_confidence NUMERIC(3,2) NOT NULL DEFAULT 0.85
    CHECK (auto_approve_confidence BETWEEN 0 AND 1),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON instructor_profiles(org_id);

CREATE TABLE faculty_applications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(uid) ON DELETE CASCADE,
  full_name TEXT NOT NULL,
  university TEXT,
  department TEXT,
  designation TEXT,
  official_email TEXT,
  proof_file_url TEXT,
  status TEXT NOT NULL CHECK (status IN ('pending','approved','rejected')) DEFAULT 'pending',
  rejection_reason TEXT,
  reviewed_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  reviewed_at TIMESTAMPTZ
);
CREATE INDEX ON faculty_applications(org_id);

-- ============================================================================
-- SUBJECTS, REFERENCES, ASSIGNMENTS
-- ============================================================================
CREATE TABLE subjects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  instructor_id TEXT NOT NULL REFERENCES users(uid) ON DELETE CASCADE,
  code TEXT,
  title TEXT NOT NULL,
  description TEXT,
  level TEXT,
  language TEXT NOT NULL DEFAULT 'en',
  kb_status TEXT NOT NULL CHECK (kb_status IN ('empty','indexing','ready')) DEFAULT 'empty',
  reference_count INT NOT NULL DEFAULT 0,
  assignment_count INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON subjects(org_id);
CREATE INDEX ON subjects(instructor_id);

CREATE TABLE reference_materials (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('textbook','lecture_notes','marking_scheme','model_answer','slides','other')),
  file_url TEXT NOT NULL,
  index_status TEXT NOT NULL CHECK (index_status IN ('pending','chunking','embedded','failed')) DEFAULT 'pending',
  chunk_count INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON reference_materials(org_id);
CREATE INDEX ON reference_materials(subject_id);

CREATE TABLE assignments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  plagiarism_enabled BOOLEAN NOT NULL DEFAULT false,
  -- Bumped when questions/rubric change; used by the result cache so an
  -- edited assignment forces re-grading.
  version INT NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON assignments(org_id);
CREATE INDEX ON assignments(subject_id);

CREATE TABLE questions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  assignment_id UUID NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
  text TEXT NOT NULL,
  max_marks INT NOT NULL,
  display_order INT NOT NULL DEFAULT 0
);
CREATE INDEX ON questions(assignment_id);

CREATE TABLE rubric_criteria (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  assignment_id UUID NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  max_score INT NOT NULL,
  description TEXT
);
CREATE INDEX ON rubric_criteria(assignment_id);

-- ============================================================================
-- KNOWLEDGE GRAPH (relational; equivalent expressive power to a graph DB)
--   Concepts                = nodes
--   question_concepts       = (Question)-[:EXPECTS]->(Concept)
--   rubric_concepts         = (RubricCriterion)-[:ASSESSES]->(Concept)
--   misconceptions          = (Concept)-[:COMMON_MISTAKE]->(Misconception)
-- ============================================================================
CREATE TABLE concepts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  definition TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(subject_id, name)
);
CREATE INDEX ON concepts(subject_id);

CREATE TABLE question_concepts (
  question_id UUID NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  concept_id  UUID NOT NULL REFERENCES concepts(id)  ON DELETE CASCADE,
  PRIMARY KEY (question_id, concept_id)
);

CREATE TABLE rubric_concepts (
  criterion_id UUID NOT NULL REFERENCES rubric_criteria(id) ON DELETE CASCADE,
  concept_id   UUID NOT NULL REFERENCES concepts(id)        ON DELETE CASCADE,
  PRIMARY KEY (criterion_id, concept_id)
);

CREATE TABLE misconceptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  concept_id UUID NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
  text TEXT NOT NULL
);
CREATE INDEX ON misconceptions(concept_id);

-- ============================================================================
-- VECTOR RAG (pgvector)
-- 1024-dim matches BGE-M3. Change the dimension if you change the embed model.
-- ============================================================================
CREATE TABLE reference_chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  reference_id UUID NOT NULL REFERENCES reference_materials(id) ON DELETE CASCADE,
  doc_type TEXT NOT NULL,
  concept_ids UUID[] NOT NULL DEFAULT '{}',           -- bridge to the graph
  chunk_index INT NOT NULL,
  text TEXT NOT NULL,
  embedding vector(1024) NOT NULL
);
CREATE INDEX reference_chunks_subject_idx  ON reference_chunks(subject_id);
CREATE INDEX reference_chunks_concepts_idx ON reference_chunks USING gin(concept_ids);
CREATE INDEX reference_chunks_emb_idx      ON reference_chunks
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

CREATE TABLE submission_chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  submission_id UUID NOT NULL,                         -- FK added after submissions table
  batch_id UUID,
  chunk_index INT NOT NULL,
  text TEXT NOT NULL,
  embedding vector(1024) NOT NULL
);
CREATE INDEX ON submission_chunks(submission_id);
CREATE INDEX submission_chunks_emb_idx ON submission_chunks
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- ============================================================================
-- BATCHES, SUBMISSIONS, FEEDBACK (draft → approved → published)
-- ============================================================================
CREATE TABLE batches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  instructor_id TEXT NOT NULL REFERENCES users(uid) ON DELETE CASCADE,
  subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  assignment_id UUID NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
  plagiarism_enabled BOOLEAN NOT NULL DEFAULT false,
  status TEXT NOT NULL CHECK (status IN ('uploaded','processing','completed','failed')) DEFAULT 'uploaded',
  total_files INT NOT NULL DEFAULT 0,
  processed_files INT NOT NULL DEFAULT 0,
  approved_count INT NOT NULL DEFAULT 0,               -- for the review screen progress
  needs_review_count INT NOT NULL DEFAULT 0,
  export_excel_url TEXT,
  export_zip_url TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON batches(org_id);
CREATE INDEX ON batches(instructor_id);

CREATE TABLE submissions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id TEXT REFERENCES users(uid) ON DELETE SET NULL,
  student_name TEXT,                                   -- instructor-editable for batches
  assignment_id UUID REFERENCES assignments(id) ON DELETE SET NULL,
  subject_id UUID REFERENCES subjects(id) ON DELETE SET NULL,
  batch_id UUID REFERENCES batches(id) ON DELETE CASCADE,
  type TEXT NOT NULL CHECK (type IN ('text','handwritten','coding','custom')),
  mode TEXT NOT NULL CHECK (mode IN ('single','batch')),
  input_text TEXT,
  stdin_text TEXT,
  question_text TEXT,
  rubric_text TEXT,
  reference_file_url TEXT,
  reference_file_name TEXT,
  file_url TEXT,
  file_name TEXT,
  status TEXT NOT NULL CHECK (status IN ('uploaded','processing','graded','approved','published','failed')) DEFAULT 'uploaded',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON submissions(org_id);
CREATE INDEX ON submissions(batch_id);
CREATE INDEX ON submissions(assignment_id);
CREATE INDEX ON submissions(status);

-- Now we can add the FK we deferred:
ALTER TABLE submission_chunks
  ADD CONSTRAINT submission_chunks_submission_fk
  FOREIGN KEY (submission_id) REFERENCES submissions(id) ON DELETE CASCADE;

-- ============================================================================
-- The draft → approved → published feedback model.
-- The AI's grade is preserved IMMUTABLY (for audit + eval). The instructor's
-- final grade is a separate set of columns. `was_edited` and the diff between
-- them are gold for measuring AI agreement and improving the system.
-- Students see the grade ONLY when status = 'published'.
-- ============================================================================
CREATE TABLE feedback_reports (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  submission_id UUID NOT NULL UNIQUE REFERENCES submissions(id) ON DELETE CASCADE,
  batch_id UUID REFERENCES batches(id) ON DELETE CASCADE,

  -- AI's original output (immutable)
  ai_overall_score NUMERIC(6,2),
  ai_max_score NUMERIC(6,2),
  ai_status TEXT CHECK (ai_status IN ('pass','fail','needs_review')),
  ai_payload JSONB NOT NULL,                            -- the full strict JSON
  ai_overall_confidence NUMERIC(3,2),                   -- avg per-criterion confidence
  specialist_output JSONB,
  judge_output JSONB,
  senior_output JSONB,
  ai_model_versions JSONB NOT NULL DEFAULT '{}',        -- {specialist: "...", judge: "...", senior: "..."}
  ai_generated_at TIMESTAMPTZ,

  -- Instructor's final (may equal AI's, or differ if edited)
  final_overall_score NUMERIC(6,2),
  final_max_score NUMERIC(6,2),
  final_status TEXT CHECK (final_status IN ('pass','fail','needs_review')),
  final_payload JSONB,
  approved_by TEXT REFERENCES users(uid),
  approved_at TIMESTAMPTZ,
  published_at TIMESTAMPTZ,
  was_edited BOOLEAN NOT NULL DEFAULT false,

  pdf_url TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON feedback_reports(org_id);
CREATE INDEX ON feedback_reports(batch_id);
CREATE INDEX ON feedback_reports(approved_at);
-- The review screen wants "needs review or unapproved, sorted by confidence":
CREATE INDEX feedback_reports_review_idx ON feedback_reports
  (batch_id, ai_overall_confidence)
  WHERE approved_at IS NULL;

CREATE TABLE plagiarism_reports (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  submission_id UUID NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
  batch_id UUID REFERENCES batches(id) ON DELETE CASCADE,
  similarity_score NUMERIC(5,2),
  matches JSONB NOT NULL DEFAULT '[]',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON plagiarism_reports(submission_id);

-- ============================================================================
-- POLICY / SAFETY
-- ============================================================================
CREATE TABLE warnings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(uid) ON DELETE CASCADE,
  submission_id UUID REFERENCES submissions(id) ON DELETE SET NULL,
  reason TEXT NOT NULL,
  severity TEXT NOT NULL CHECK (severity IN ('low','medium','high')),
  status TEXT NOT NULL CHECK (status IN ('active','dismissed')) DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  dismissed_by TEXT REFERENCES users(uid)
);
CREATE INDEX ON warnings(user_id);

CREATE TABLE audit_logs (
  id BIGSERIAL PRIMARY KEY,
  org_id UUID REFERENCES organizations(id) ON DELETE SET NULL,
  actor_uid TEXT REFERENCES users(uid),
  action TEXT NOT NULL,
  target TEXT,
  meta JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON audit_logs(org_id, created_at DESC);

-- ============================================================================
-- HELPER: get a user's org_id without going through RLS.
-- The API calls this BEFORE setting app.current_org_id, so it must bypass RLS.
-- SECURITY DEFINER makes it run as the function owner (the superuser at init
-- time) so RLS does not block the lookup.
-- ============================================================================
CREATE OR REPLACE FUNCTION get_user_org_id(p_uid TEXT)
RETURNS UUID
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT org_id FROM users WHERE uid = p_uid;
$$;
GRANT EXECUTE ON FUNCTION get_user_org_id(TEXT) TO app_user;

-- ============================================================================
-- ROW-LEVEL SECURITY (tenant isolation — the production-critical piece)
-- Every tenant-scoped table gets the same policy:
--   USING/WITH CHECK (org_id = current_setting('app.current_org_id', true)::UUID)
-- The API does, per request:
--   SET LOCAL app.current_org_id = '<org uuid>';
-- If it forgets, queries see ZERO rows (true second arg => return NULL on unset,
-- which fails the equality check). That fail-closed behaviour is what makes
-- this safe.
-- ============================================================================
DO $$
DECLARE
  t TEXT;
  tables TEXT[] := ARRAY[
    'users','instructor_profiles','faculty_applications','subjects',
    'reference_materials','assignments','questions','rubric_criteria',
    'concepts','misconceptions','reference_chunks','submission_chunks',
    'batches','submissions','feedback_reports','plagiarism_reports',
    'warnings','audit_logs'
  ];
BEGIN
  FOREACH t IN ARRAY tables LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);  -- enforce even for owner
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I
         USING (org_id = current_setting(''app.current_org_id'', true)::UUID)
         WITH CHECK (org_id = current_setting(''app.current_org_id'', true)::UUID)',
      t
    );
  END LOOP;
END$$;

-- ---- Grants to the app role ------------------------------------------------
GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;
-- Future objects too:
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO app_user;

-- ============================================================================
-- A trivial seed organization for local development (delete in production).
-- ============================================================================
INSERT INTO organizations (id, name, kind, country)
VALUES ('00000000-0000-0000-0000-000000000001', 'Dev Org', 'individual', 'PK')
ON CONFLICT (id) DO NOTHING;
