# 35 — Master Design Book (Spa) — Architecture & Implementation Plan

**Status:** PLANNED (decisions pending marked ⚠ JACK)
**Date:** 2026-07-09
**Related:** 32-BUILD-BOOK.md (per-project build book this derives from), 31-BUILD-TRACKER-SHEET.md

---

## 1. What this is

A **product-level, date-free, rev-controlled Master Design Book** for the Standard Spa
(product `csa00010`, template project `SPA0030` — "Elite Equine Spa3", the current
model + print set; TEST-PROG01 was the prototype and is out of date). Unlike the
per-project Build Book (dated, completion-prefilled, regenerated per job), the Master
Design Book is the canonical "how to build one spa" document:

- Days are **relative (D1..Dn)** — never calendar dates.
- All checkboxes **always blank** (photocopy pages for one-off use).
- Delivered as **modular section booklets** — each a standalone, self-contained PDF —
  tied together by a spine (cover + full master checklist + TOC).
- **Section-level revision letters** with auto-generated **CHANGE NOTICE** PDFs that
  tell holders of hard-printed copies exactly which booklets to pull and replace.
- Stored in a dedicated `design-books` Supabase bucket; PDM regenerates **only changed
  sections** on Update. A **full merged bookmarked PDF** is built on demand by
  byte-concatenation of the current section PDFs (streamed — it exceeds the 50MB
  project upload cap).

This plan was produced by a multi-agent research/design/critique pass (2026-07-09):
4 codebase researchers, 2 design-spec writers, 1 adversarial critic, 1 cross-verifier.
All decisions below are reconciled across those outputs.

## 2. Book structure

```
design-books/spa-standard/
  manifest.json                 exported serialization of the DB rows (DB is authoritative)
  00-spine.pdf                  cover + rev history + buy list + MASTER CHECKLIST (D1..Dn) + TOC
  i-saw-1.pdf, i-pb-1.pdf, ...  SECTION I  — one booklet per work package (table + qty-stamped prints)
  ii-csa00020.pdf, ...          SECTION II — one booklet per assembly (kit + sequence + prints)
  ii-ref.pdf                    II-REF     — overall design reference print(s) (csd items)
  iii-00-general-reference.pdf  SECTION III — general reference (blank template v1; III-01+ ingested later)
  archive/                      superseded section PDFs (archive-on-supersede, last few revs)
  assets/                       (reserved) originals for future Section III ingestion
  changes/CHANGE-NOTICE-rev002.pdf   immutable, zero-padded, one per book rev
  full/spa-master-design-book.pdf    only stored if under upload cap; normally streamed
```

## 3. Section identity & codes (reconciled — verifier-approved)

Diffing always matches on **identity**, never on the printed code.

| kind | identity (match key) | printed section_code | filename |
|---|---|---|---|
| spine | singleton | `00-SPINE` | `00-spine.pdf` |
| work_package | `{station_code, occurrence}` | `I-{ABBREV}-{n}` e.g. `I-SAW-1` | `i-saw-1.pdf` |
| assembly | `item_number` | `II-{ITEM}` e.g. `II-CSA00020` | `ii-csa00020.pdf` |
| design_reference | singleton | `II-REF` | `ii-ref.pdf` |
| general_reference | `III-{nn}` | `III-00` (later `III-01+`) | `iii-00-general-reference.pdf` |

- `occurrence` = 1-based index of that station's packages ordered by day (the
  `(day, station)` grouping in buildBook.ts:289 guarantees ≤1 package per station per
  day, so this is total and deterministic).
- **Why not `I-01..I-NN` ordinals or `(day,station)` keys:** an inserted package or a
  one-day slip would renumber/retire everything downstream — change notices degenerate
  to "replace all of Section I". Station+occurrence survives day shifts (rev bump,
  reason `MOVED D2->D3`), splits/merges (clean REPLACE/ADD/REMOVE rows), and matches
  the holder's mental model ("second saw booklet"). ⚠ JACK: printed-code style
  confirmation.
- **Why `II-{ITEM}` not `II-A01`:** the DFS `rid` (A01) reshuffles on any BOM edit;
  printing it as identity would force reprints of unchanged kits. The `A{nn}` binder
  ordinal appears only in the spine TOC (which legitimately revs).
- **Cross-references are translated to section codes before hashing/rendering:**
  `readyBy` (pkg id) → `I-SAW-1 - D2`; `feeds`/`stageFor`/child-assembly rids →
  `II-{ITEM}`. `BookPackageLine.next` is a station abbrev — NOT translated (verifier
  caught the versioning spec mislabeling this).
- Day and PKG position are display metadata: printed, hashed (moves surface as rev
  bumps), never identity.

## 4. Versioning engine

### 4.1 Content hash (semantic inputs, never PDF bytes)
Reportlab output is nondeterministic (CreationDate/ModDate, random /ID) — rendered
bytes are never hashed or compared. Per section, hash =
`sha256(canonical_json({hash_schema, renderer_version, kind, section_code, identity,
display, payload, prints}))` where:

- `payload` = kind-specific table data, done-flags stripped, cross-refs translated.
- `prints` = ordered bind list `{item_number, file_id, revision, iteration, file_path,
  qty}` or `{item_number, missing: true, qty}`.
- **CRITICAL (verifier finding): the `files` table is NOT append-only.** Re-uploading
  the same filename UPDATEs the row in place (backend/app/routes/files.py:390-397):
  same `file_id`, same `file_path`, only `revision`/`iteration` move. Therefore the
  staleness/change predicate is the tuple **(file_id, revision, iteration)** — never
  file_id alone. Print bytes are NOT hashed (keeps `/check` a zero-download dry run).
- Canonicalization: strip excluded keys (timestamps, book_rev, own rev, storage paths,
  done flags, calendar strings, rids), ints for whole floats, `json.dumps(sort_keys=True,
  separators=(',',':'), ensure_ascii=True)`.
- `renderer_version` participates in the hash: bumping it revs every section = a
  deliberate full re-issue ("ALL SECTIONS REVISED — LAYOUT UPDATE"). Never ship visual
  changes without bumping it.

### 4.2 Revision rules
- Section revs: `A..Z, AA, AB..`. Bump iff hash differs. Retired sections freeze;
  reinstatement CONTINUES the letter sequence (never reset to A).
- `book_rev` integer, +1 per update that produces any diff. Book rev N ↔
  `CHANGE-NOTICE-rev{N:03d}.pdf`.
- The **spine always revs when anything changes** (its hash embeds the final section
  rev map — two-phase: hash all sections, then spine). Deliberate: the printed TOC is
  the holder's binder-verification authority.
- Filenames are **stable** (rev in the DB/manifest + printed in every footer, not in
  the filename). On supersede, the outgoing PDF is copied to
  `archive/{code}-rev{old}.pdf` before overwrite (cheap insurance; change notices are
  additionally immutable).

### 4.3 Update algorithm (POST /update)
1. Load book + sections; optimistic concurrency via `expected_book_rev` (409 on
   mismatch).
2. Validate descriptors; **server-side qty verification** — backend recomputes the
   csa00010 BOM rollup from the `bom` table and rejects (400) on mismatch with
   descriptor quantities unless `allow_qty_mismatch` (recorded as warning). Never
   trust the client's qty_check alone (verifier risk #9).
3. Resolve prints once (extend `_fetch_pdf_paths` to return full file rows —
   **ordered by `updated_at` desc, not `created_at`** — in-place updates keep original
   created_at, so created_at newest-selection is unsound).
4. Phase-1 hash & diff all non-spine sections, matched by identity →
   unchanged / changed / added / retired (+ rename handling).
5. Spine hashed against the final rev map.
6. No-op exit if nothing changed (idempotent — requires deterministic scheduling, see
   4.5).
7. Write-ahead `design_book_changes` row; merge any open row from a crashed prior run
   (so notices never lose diff entries).
8. Download print bytes for changed/added sections only (8-worker pool, shared cache).
9. Per section: render → upload (upsert) → only then upsert the DB row. Archive-on-
   supersede before overwrite. Retired: archive, delete object, mark row retired.
10. Render + upload the change notice (immutable).
11. Commit point: bump `design_books.book_rev`.
12. Export `manifest.json` (pure serialization of DB rows; DB authoritative).

Recovery: no multi-statement transactions in PostgREST — ordering invariants instead:
DB never leads storage; storage may lead DB harmlessly; book_rev bump is the commit
point; re-running update always converges; open changes rows merge.

### 4.4 Change notice
Header (book, rev N-1 → N, **issue date — allowed**: date-freeness bans schedule dates,
not document-control dates), instruction box, one ACTIONS table with verbs
REPLACE / INSERT / REMOVE, columns `ACTION|SECTION|TITLE|OLD|NEW|PAGES|REASON`.
Reasons derived mechanically from structured diff of stored vs new hash inputs
(`PRINT csp0030 B->C`, `MOVED D1->D2`, `QTY csp0030 4->6`, `SEQUENCE REVISED`,
`RENAMED FROM I-SAW-1`, `NEW`, `MERGED INTO ...`), max 3 clauses + `+n MORE`.
`00-SPINE` REPLACE row always present. No-action summary line. Three-copy
distribution/acknowledgment block (SHOP WALL / OFFICE / SPARE). First generation
(rev 1) produces NO notice (no holders yet).

### 4.5 Determinism requirement (verifier risk #3)
`prioritizeTasks` breaks ties by input array order (scheduling.ts:368-374) = DB result
order. `masterDesignBook()` MUST canonically sort parts/bom/routing inputs (by
item_number / parent+child / item+sequence) before `calculateSchedule`, or no-op
idempotence is fiction and phantom rev bumps occur. Unit test: two runs over shuffled
inputs → identical descriptors.

## 5. Rendering rules

- **Page numbering is SECTION-LOCAL** (`PAGE 3 OF 9`) — no global page numbers
  anywhere. This is the swap contract: replacing II-CSA00020 rev B (6pp) with rev C
  (9pp) touches nothing else.
- **Footer on EVERY page including bound prints** via `_stamp_footer` (mediabox-sized
  overlay, white-backed 16pt strip; must honor page `/Rotate`):
  `MDB SPA-STANDARD REV 4 | II-CSA00020 REV C | PAGE 3 OF 9 - GEN 2026-07-09`.
  Two-pass: render body → append prints → stamp footers with final count.
- **Calendar dates appear in exactly three places** (all document control): footer GEN
  date, spine REVISION HISTORY issued column, change-notice header. `dayLabel(d) =
  "D" + (d+1)` is a single shared helper (buildBook.ts export + Python mirror).
- **All checkboxes hard-coded blank** — renderer never reads done flags; data layer
  also strips them (belt and suspenders — buildTracker.ts:498 rowDone edge for
  unrouted parts survives `completion: []` alone).
- **ASCII sanitization chokepoint** `_ascii_safe()` applied to EVERY dynamic string
  (item names, routing notes, supplier names): transliterate ° → `deg`, ± → `+/-`,
  Ø → `dia`, smart quotes → straight, else strip. Reportlab Helvetica is WinAnsi; a
  `Ø` in a weld note must not garble a controlled document. Unicode fixture test per
  section type.
- **Print dedup policy:** within a section, each print binds once (qty summed);
  ACROSS sections prints deliberately duplicate — self-contained booklets are what
  make swaps safe. Size cost ~2-2.5x unique bytes (~100-145MB folder total vs 54MB
  unique) — accepted. Run `_compress_pdf` once per unique print at cache time.
- Kit part qty = total across ALL kit instances (buildTracker.ts:466 `c.qty *
  parentQty`); label accordingly (verifier: don't call it per-kit).
- Purchased items: `purchasedDisplay()`/`purchasedSource()` everywhere — raw mmc/spn
  never prints. Purchased lines are `no_print_expected` (excluded from print binding
  and MISSING warnings).
- Missing prints: NO placeholder page (fake pages in a controlled document risk being
  taken as content); cover MISSING band + manifest `missing:true` (in hash — print
  arriving later revs the section) + UI acknowledgment gate before commit. ⚠ JACK.
- Spine contents: cover (governing notes, rev history w/ initials column), BUY LIST
  page (purchased rollup w/ ORD/RCV boxes — requires surfacing `sheet.purchased`
  rows on the BuildBook output; currently only a count), MASTER CHECKLIST D1..Dn
  (packages + kit sequence steps + milestone bands, day-break rules, SEE column w/
  section codes), TOC (code/rev/title/pages/prints/D-days). Checklist rows must map
  1:1 to Section I/II booklets (render-time assertion).

### Full merged book (POST /full)
**Byte-concatenation of the CURRENT stored section PDFs — never re-rendered** (a
headless re-render could bind print bytes never issued under the certified rev,
because print storage paths are overwritten in place). Order: spine, I-* (build
order), II-* (binder order), II-REF, III-*. `PdfWriter.append(reader,
import_outline=False)` (CAD-export junk outlines), nested `add_outline_item`
bookmarks, `set_page_label(prefix=f"{code} ")` (pypdf 6.6.2 — verified). Streamed as
plain `Response` (~105-125MB > 50MB cap); stored to `full/` only if it ever fits.

## 6. Database & storage (DDL verified against live schema conventions)

Three tables + one future-proofing table, Gen-1 RLS pattern (`Authenticated can view`
SELECT + `Engineers can manage` via `public.is_engineer_or_admin()`), updated_at
triggers via existing `update_updated_at_column()`:

```sql
CREATE TABLE design_books (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  book_code TEXT UNIQUE NOT NULL,                 -- 'spa-standard'
  title TEXT NOT NULL,
  product_item_number TEXT NOT NULL REFERENCES items(item_number),
  template_project_id UUID REFERENCES mrp_projects(id),
  book_rev INTEGER NOT NULL DEFAULT 0,
  renderer_version INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','current','archived')),
  generated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE design_book_sections (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  book_id UUID NOT NULL REFERENCES design_books(id) ON DELETE CASCADE,
  section_code TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('spine','work_package','assembly','design_reference','general_reference')),
  title TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  rev TEXT NOT NULL DEFAULT 'A',
  identity JSONB NOT NULL DEFAULT '{}'::jsonb,    -- diff match key
  display JSONB,                                  -- day / pkg position (display metadata)
  content_hash TEXT,
  source JSONB NOT NULL DEFAULT '{}'::jsonb,      -- FULL hash input (reason derivation + headless ops)
  storage_path TEXT,
  page_count INTEGER,
  status TEXT NOT NULL DEFAULT 'current' CHECK (status IN ('current','superseded','retired')),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(book_id, section_code)
);
CREATE INDEX idx_design_book_sections_book ON design_book_sections(book_id);

CREATE TABLE design_book_changes (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  book_id UUID NOT NULL REFERENCES design_books(id) ON DELETE CASCADE,
  from_rev INTEGER NOT NULL,
  to_rev INTEGER NOT NULL,
  diff JSONB NOT NULL DEFAULT '[]'::jsonb,
  notice_storage_path TEXT,                       -- NULL = open/in-flight (write-ahead)
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(book_id, to_rev)
);

-- future Section III ingestion (photos / Word / PDF / PPT) — schema now, pipeline later
CREATE TABLE design_book_assets (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  section_id UUID NOT NULL REFERENCES design_book_sections(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('photo','word','pdf','ppt','note')),
  original_path TEXT,                             -- assets/ prefix in bucket
  converted_pdf_path TEXT,
  caption TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('design-books','design-books', false, 52428800,
        ARRAY['application/pdf','application/json'])
ON CONFLICT (id) DO UPDATE SET file_size_limit = EXCLUDED.file_size_limit,
                               allowed_mime_types = EXCLUDED.allowed_mime_types;
-- bucket limit = 50MB project cap (raise together if the project cap is raised)

CREATE POLICY "Authenticated users can read design books"
  ON storage.objects FOR SELECT TO authenticated
  USING (bucket_id = 'design-books');
-- writes: service-role only (backend), like print-packets. Do NOT copy the pdm-*
-- write policies (they have a users.id-vs-auth_id bug).
```

Staleness badge (passive UI hint only — Update re-hash is the authoritative detector;
routing/bom have NO updated_at columns):

```sql
-- lateral join: newest PDF per bound item vs bound (file_id, revision, iteration)
-- MUST compare all three (in-place file updates keep file_id) and order the newest
-- pick by updated_at (files has an updated_at trigger; created_at is unsound).
```

## 7. API (backend/app/routes/design_books.py, house patterns from mrp.py)

| Endpoint | Purpose |
|---|---|
| `GET /api/mrp/design-books` | list books + stale_print_count badge |
| `GET /api/mrp/design-books/{code}` | book detail: sections, stale_prints, changes, consistency flag |
| `POST .../check` | dry run: hash + diff + reasons; zero downloads/writes |
| `POST .../update` | the algorithm in 4.3; body = frontend-computed `{meta, sections}` |
| `POST .../full` | merged book (byte-concat + bookmarks), streamed plain Response |
| `GET .../sections/{code}/url` | signed URL (frontend may also self-sign via bucket read policy) |

Frontend computes the book JSON (`masterDesignBook()` / `masterSections()` in
buildBook.ts) and POSTs it — same flow as build-book/section-prints; keeps buildBook.ts
the single source of truth (the STATION_ABBREV drift proves Python ports drift).
All PDF responses: plain `Response`, never `StreamingResponse(BytesIO)`.

## 8. UI — MasterDesignBookView at /mrp/design-book/:bookCode

Dedicated view (dashboard slideout too narrow; MrpBuildBookView is an opposite
lifecycle). Dark theme per style.md; nav button on MRP dashboard header.

- Header: title, book rev badge, product/template meta; action bar: **Check for
  Changes** (dry run) / **Update Book** (opens diff modal) / **Full PDF** / **Change
  Notice**.
- Stats row: book rev, sections, last updated, out-of-date count (amber when > 0).
- Section table grouped (Spine / I Work Packages / II Assemblies / III Reference):
  code (mono), title, rev, pages, status chip + visible reason sub-line, updated,
  per-row PDF download. Status colors reuse existing badges: CURRENT #059669,
  OUT OF DATE #d97706, NEW #7c3aed, RETIRED #374151.
- `DesignBookUpdateModal` (NestConfigModal precedent, ~720px): pending diff table with
  rev arrows + reasons, "N unchanged" muted line, missing-print acknowledgment
  checkboxes, `Commit Update (N sections)` = the confirmation (no native confirm()).
- Reads: direct Supabase (design_books + design_book_sections) on mount; writes via
  the API. Extend storage.ts BucketName union with 'design-books'.

## 9. Implementation phases

**Phase 0 — Foundations** (supabase agent)
1. Migration: 4 tables + triggers + RLS + bucket + read policy (reference copy in
   backend/migrations/ per assistant_v2 precedent).
2. Fix `'Vinyl Wrap': 'VW'` in print_packet.py STATION_ABBREV (known gap).
3. Restore print_packet.py MAX_PDF_SIZE_BYTES to 40MB chunks (4MB working-tree cap
   was an error; project cap is 50MB).

**Phase 1 — Master data engine** (frontend/src/utils/buildBook.ts + tests)
1. Surface purchased rows on BuildBook output (from sheet.purchased).
2. `masterDesignBook()`: canonical input sorts (determinism), null start_date AND
   due_date, completion: [], post-build force done=false, dayLabel helper.
3. `masterSections()`: emit descriptors {section_code, kind, identity, display, title,
   payload, print_items, no_print_expected} with cross-refs translated to section
   codes; BOM-rollup qty check.
4. Vitest: determinism (shuffled inputs → identical output), date-free, blank-done,
   section enumeration, split/merge identity behavior, cross-ref translation.

**Phase 2 — Backend service + routes** (backend/app/services/master_design_book.py,
backend/app/routes/design_books.py)
1. Hash-input builder + canonicalization + diff engine (identity match, letter revs).
2. `_ascii_safe()` chokepoint + unicode fixture tests.
3. Renderers: spine (cover/buy-list/checklist/TOC), package section, kit section,
   II-REF, III-00 template; `_stamp_footer` (mediabox + /Rotate); `_bind_prints`
   (fresh PdfReader per binding — stamps mutate pages).
4. Update algorithm w/ write-ahead changes row, archive-on-supersede, manifest export;
   change-notice generator; `/check`; `/full` (byte-concat + outline + page labels).
5. `_fetch_pdf_paths` fix: order by updated_at, return full file rows.
6. Crash-recovery tests: kill between upload and row-update → re-run converges;
   open-changes-row merge.

**Phase 3 — UI** (frontend)
1. MasterDesignBookView.vue + DesignBookUpdateModal.vue + route + dashboard nav button.
2. storage.ts bucket union; status badges + reason sub-lines; missing-print
   acknowledgment gate.

**Phase 4 — First publish + verification**
1. Generate spa-standard rev 1 from SPA0030. Verify bucket contents + manifest.
2. `/check` no-op idempotence immediately after publish (must be empty diff).
3. Print-test one package booklet + one kit booklet (footer legibility on prints,
   qty stamp placement on 11x17/rotated pages, duplex behavior per Jack's answers).
4. Simulate a print rev bump → verify one-section change notice end-to-end.

**Phase 5 — Later**
- Section III ingestion (phone photos, Word/PDF, PPT slides → III-01+ subsections via
  design_book_assets; conversion pipeline TBD — LibreOffice headless or similar).
- Staleness badge on MRP dashboard; holder distribution config; multi-product books
  (book_code is already the namespace).

## 10. Decisions (RESOLVED with Jack, 2026-07-09)

1. Printed codes: **`I-SAW-1` / `II-CSA00020`** (stable station+occurrence / item
   number). Ordinal codes rejected.
2. Purchased parts: **spine BUY LIST page + I-RCV receiving work packages** —
   full per-spa procurement picture, ORD/RCV checkboxes, supplier + supplier PN.
3. Missing prints: **publish with cover MISSING band + explicit per-hole
   acknowledgment in the update modal**. Print arriving later auto-revs the section
   (reason `PRINT ADDED`). No placeholder pages, no hard block.
4. Paper: **mixed 11x17 prints + letter tables, single-sided** — no blank-page
   insertion logic; TOC counts PDF pages.
5. Template governance: **the template project is the live authoring surface** —
   routing/BOM edits there are the update mechanism; master mode ignores completion
   + dates. No lock flag. Template = SPA0030 (Jack, 2026-07-09; TEST-PROG01 was the
   out-of-date prototype). When a newer spa project becomes the reference, repoint
   design_books.template_project_id and run Update — the change notice will show
   exactly what changed between the two models.

## 11. Known landmines (carry into every phase)

- ASCII-only through reportlab Helvetica (WinAnsi); `_ascii_safe()` for all data.
- Plain `Response`, never `StreamingResponse(BytesIO)` (Starlette iterates ~80KB/s).
- files table updates in place — staleness = (file_id, revision, iteration); newest
  PDF by updated_at.
- Schedule tie-breaking is input-order-dependent — canonical sorts required.
- Never reuse a parsed PdfReader page across bindings (stamps mutate pages).
- `mrp_project_parts` flat qty can mismatch BOM rollup — server-side rollup gate.
- Raw mmc/spn numbers never print — purchasedDisplay()/purchasedSource().
- SECONDARY_STATIONS (Deburr/Inspection): no packages, but present in kit sequences.
