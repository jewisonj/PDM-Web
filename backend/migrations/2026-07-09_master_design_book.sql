-- ============================================================================
-- Master Design Book — Phase 0 foundations
-- Reference copy of the remote Supabase migration `master_design_book`.
-- See Documentation/36-MASTER-DESIGN-BOOK-PLAN.md for the full architecture.
--
-- Tables:
--   design_books          one row per product book ('spa-standard')
--   design_book_sections  one row per section booklet, updated in place (rev A->B)
--   design_book_changes   change-notice log; notice_storage_path NULL = in-flight
--   design_book_assets    future Section III ingestion (photos/Word/PDF/PPT)
-- Storage:
--   design-books bucket (50MB per-file, pdf+json), authenticated read,
--   service-role-only writes (backend renderer), like print-packets.
-- ============================================================================

CREATE TABLE IF NOT EXISTS design_books (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  book_code TEXT UNIQUE NOT NULL,                      -- 'spa-standard' = folder in design-books bucket
  title TEXT NOT NULL,                                 -- 'Standard Spa Master Design Book'
  product_item_number TEXT NOT NULL REFERENCES items(item_number),  -- 'csa00010'
  template_project_id UUID REFERENCES mrp_projects(id),             -- TEST-PROG01
  book_rev INTEGER NOT NULL DEFAULT 0,                 -- 0 = never published; bump is the update commit point
  renderer_version INTEGER NOT NULL DEFAULT 1,         -- participates in content hashes; bump = full re-issue
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'current', 'archived')),
  generated_at TIMESTAMPTZ,                            -- last successful publish
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS design_book_sections (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  book_id UUID NOT NULL REFERENCES design_books(id) ON DELETE CASCADE,
  section_code TEXT NOT NULL,                          -- '00-SPINE', 'I-SAW-1', 'II-CSA00020', 'II-REF', 'III-00'
  kind TEXT NOT NULL CHECK (kind IN
    ('spine', 'work_package', 'assembly', 'design_reference', 'general_reference')),
  title TEXT NOT NULL,                                 -- 'SAW' / 'LOWER FRAME — csa00030'
  sort_order INTEGER NOT NULL DEFAULT 0,               -- book order (spine TOC / full-book merge order)
  rev TEXT NOT NULL DEFAULT 'A',                       -- section revision letter A..Z, AA..
  identity JSONB NOT NULL DEFAULT '{}'::jsonb,         -- diff match key: {station_code, occurrence} / {item_number} / singleton
  display JSONB,                                       -- display metadata: {day, pkg_position} (hashed, not identity)
  content_hash TEXT,                                   -- sha256 of canonical semantic hash input (never PDF bytes)
  source JSONB NOT NULL DEFAULT '{}'::jsonb,           -- FULL hash input incl prints [(item, file_id, revision, iteration, qty)]
  storage_path TEXT,                                   -- 'spa-standard/i-saw-1.pdf' (stable; rev lives here + footers)
  page_count INTEGER,
  status TEXT NOT NULL DEFAULT 'current' CHECK (status IN ('current', 'superseded', 'retired')),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(book_id, section_code)
);
CREATE INDEX IF NOT EXISTS idx_design_book_sections_book ON design_book_sections(book_id);

CREATE TABLE IF NOT EXISTS design_book_changes (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  book_id UUID NOT NULL REFERENCES design_books(id) ON DELETE CASCADE,
  from_rev INTEGER NOT NULL,
  to_rev INTEGER NOT NULL,
  diff JSONB NOT NULL DEFAULT '[]'::jsonb,             -- [{section_code, action: added|revised|retired, old_rev, new_rev, reasons[]}]
  notice_storage_path TEXT,                            -- NULL = open/in-flight (write-ahead row; merged on crashed-run recovery)
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(book_id, to_rev)
);
CREATE INDEX IF NOT EXISTS idx_design_book_changes_book ON design_book_changes(book_id);

-- Future Section III ingestion (phone photos, Word, PDF, PPT) — schema now, pipeline later
CREATE TABLE IF NOT EXISTS design_book_assets (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  section_id UUID NOT NULL REFERENCES design_book_sections(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('photo', 'word', 'pdf', 'ppt', 'note')),
  original_path TEXT,                                  -- 'spa-standard/assets/...' original upload
  converted_pdf_path TEXT,                             -- rendered/converted pages bound into the subsection
  caption TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_design_book_assets_section ON design_book_assets(section_id);

-- updated_at triggers (reuse the house generic function)
DROP TRIGGER IF EXISTS update_design_books_updated_at ON design_books;
CREATE TRIGGER update_design_books_updated_at BEFORE UPDATE ON design_books
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
DROP TRIGGER IF EXISTS update_design_book_sections_updated_at ON design_book_sections;
CREATE TRIGGER update_design_book_sections_updated_at BEFORE UPDATE ON design_book_sections
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- RLS: house Gen-1 pattern (authenticated read, engineers manage; backend service
-- client bypasses RLS). Never inline the users subquery — use is_engineer_or_admin().
ALTER TABLE design_books ENABLE ROW LEVEL SECURITY;
ALTER TABLE design_book_sections ENABLE ROW LEVEL SECURITY;
ALTER TABLE design_book_changes ENABLE ROW LEVEL SECURITY;
ALTER TABLE design_book_assets ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated can view design_books" ON design_books FOR SELECT USING (true);
CREATE POLICY "Engineers can manage design_books" ON design_books FOR ALL
  USING (public.is_engineer_or_admin()) WITH CHECK (public.is_engineer_or_admin());
CREATE POLICY "Authenticated can view design_book_sections" ON design_book_sections FOR SELECT USING (true);
CREATE POLICY "Engineers can manage design_book_sections" ON design_book_sections FOR ALL
  USING (public.is_engineer_or_admin()) WITH CHECK (public.is_engineer_or_admin());
CREATE POLICY "Authenticated can view design_book_changes" ON design_book_changes FOR SELECT USING (true);
CREATE POLICY "Engineers can manage design_book_changes" ON design_book_changes FOR ALL
  USING (public.is_engineer_or_admin()) WITH CHECK (public.is_engineer_or_admin());
CREATE POLICY "Authenticated can view design_book_assets" ON design_book_assets FOR SELECT USING (true);
CREATE POLICY "Engineers can manage design_book_assets" ON design_book_assets FOR ALL
  USING (public.is_engineer_or_admin()) WITH CHECK (public.is_engineer_or_admin());

-- Storage bucket: 50MB per-file (matches project upload cap), pdf + json only
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'design-books',
  'design-books',
  false,
  52428800,  -- 50MB
  ARRAY['application/pdf', 'application/json']
)
ON CONFLICT (id) DO UPDATE SET
  file_size_limit = EXCLUDED.file_size_limit,
  allowed_mime_types = EXCLUDED.allowed_mime_types;

-- Authenticated read so the frontend can sign its own section-download URLs.
-- No INSERT/UPDATE/DELETE policies: writes are service-role-only via the backend.
CREATE POLICY "Authenticated users can read design books"
  ON storage.objects FOR SELECT TO authenticated
  USING (bucket_id = 'design-books');
