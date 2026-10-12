-- Apply as the database owner before deploying core feature support.
-- Existing semantic vectors remain intact; NULL denotes a text-only chunk.
ALTER TABLE reference_chunks ALTER COLUMN embedding DROP NOT NULL;
ALTER TABLE reference_materials ADD COLUMN IF NOT EXISTS index_method TEXT NOT NULL DEFAULT 'semantic';
CREATE INDEX IF NOT EXISTS reference_chunks_text_idx
  ON reference_chunks USING gin(to_tsvector('simple', text));
