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
| work_package | `{station_code}` | `I-{ABBREV}` e.g. `I-SAW` | `i-saw.pdf` |
| assembly | `item_number` | `II-{ITEM}` e.g. `II-CSA00020` | `ii-csa00020.pdf` |
| design_reference | singleton | `II-REF` | `ii-ref.pdf` |
| general_reference | `III-{nn}` | `III-00` (later `III-01+`) | `iii-00-general-reference.pdf` |

- **Work package identity changed (2026-07-21):** Originally `{station_code, occurrence}` where
  `occurrence` = 1-based index of packages per station ordered by day. Now simplified to
  `{station_code}` only — one consolidated section per station, all days combined. Daily
  scheduling is tracked externally on a tracking sheet, not in section identity. See §12.1
  for full rationale and migration impact.
- **Why `{station_code}` identity:** Station-based identity is stable across schedule changes.
  Daily scheduling is tracked on a separate tracking sheet (not finalized yet). The Master
  Design Book shows **WHAT parts** go through each station (the canonical build process), not
  **WHEN** (the schedule). Station-only identity prevents phantom re-numbering when days shift,
  simplifies the section structure, and matches the user's mental model ("saw package" vs
  "first saw package on day 0").
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
  1:1 to Section I/II booklets (render-time assertion). The BUY LIST data (bundles +
  individual purchased items) is stored in the spine section's `source.payload` and
  can be exported as CSV via the `/purchase-list` endpoint (see §7.1).

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
  display JSONB,                                  -- day (printed on header, hashed). NOT the
                                                  -- global PKG ordinal: it is not printed in the
                                                  -- master book, so hashing it phantom-revs on any
                                                  -- resequence (see Documentation/38). Order lives
                                                  -- in the spine checklist.
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
| `POST .../sync-quantities` | auto-fix mrp_project_parts quantities to match BOM rollup (see 7.2) |
| `POST .../update` | the algorithm in 4.3; body = frontend-computed `{meta, sections}` |
| `POST .../full` | merged book (byte-concat + bookmarks), streamed plain Response |
| `GET .../sections/{code}/url` | signed URL (frontend may also self-sign via bucket read policy) |
| `GET .../purchase-list` | CSV download of buyList (purchased items + vendor bundles) for ordering |

Frontend computes the book JSON (`masterDesignBook()` / `masterSections()` in
buildBook.ts) and POSTs it — same flow as build-book/section-prints; keeps buildBook.ts
the single source of truth (the STATION_ABBREV drift proves Python ports drift).
All PDF responses: plain `Response`, never `StreamingResponse(BytesIO)`.

### 7.1 Purchase List CSV Export

**Feature Added:** 2026-07-16

The Master Design Book includes a **Purchase List CSV download** feature that extracts the complete bill of purchased items from the spine section's `buyList` payload. This provides a single-click export for procurement.

**Endpoint:** `GET /api/mrp/design-books/{book_code}/purchase-list`

**Returns:** CSV file with columns:
- **Part #** — Display number (e.g., `McMaster 1234-567`)
- **Source** — Vendor/supplier name
- **Description** — Item name/description
- **Qty** — Total quantity needed for one spa
- **Long Lead** — "YES" if flagged as long lead time item
- **Type** — `BUNDLE` for vendor kits, `PART` for individual purchased items
- **Ordered** — Blank checkbox column for tracking
- **Received** — Blank checkbox column for tracking

**Data Source:** Reads from the `00-SPINE` section's stored `source.payload`:
- `buyList` array — Individual mmc/spn purchased items
- `bundles` array — Vendor kit bundles (e.g., full spa kit from vendor)

**Filename Format:** `{book_code}-purchase-list-rev{N}.csv` (e.g., `spa-standard-purchase-list-rev004.csv`)

**Implementation:**
- **Backend:** `backend/app/services/master_design_book.py::get_purchase_list_csv()`
  - Extracts `buyList` and `bundles` from spine section payload
  - Bundles listed first (Type: BUNDLE) — ordered as single line items
  - Individual parts follow (Type: PART) — mmc/spn items
  - Applies `_ascii()` sanitization to vendor names and descriptions
  - Returns CSV content + book rev + item count
- **Frontend:** `frontend/src/services/designBook.ts::downloadPurchaseList()`
  - Fetches CSV, triggers browser download
  - Extracts filename from Content-Disposition header
  - Returns item count from X-Items response header
- **UI:** `frontend/src/views/MasterDesignBookView.vue`
  - "Purchase List" button in header action bar
  - Disabled for first-generation books (rev 0, no spine section yet)
  - Shows spinner during download
  - Success toast shows item count

**Use Case:** Jack can download the purchase list CSV and send it to vendors or use it as a procurement checklist. The CSV includes blank "Ordered" and "Received" columns for manual tracking.

**Related Change:** The spine section title was updated from "MASTER CHECKLIST + TOC" to "CHECKLIST + BUY LIST + TOC" to reflect that the buy list is part of the spine section content.

**Files Changed:**
- `backend/app/routes/design_books.py` — Added `GET /{book_code}/purchase-list` endpoint
- `backend/app/services/master_design_book.py` — Added `get_purchase_list_csv()` function
- `frontend/src/services/designBook.ts` — Added `downloadPurchaseList()` service function
- `frontend/src/utils/masterDesignBook.ts` — Updated spine section title to "CHECKLIST + BUY LIST + TOC"
- `frontend/src/views/MasterDesignBookView.vue` — Added "Purchase List" button and `purchaseListCsv()` handler

**CSV Format Example:**
```csv
Part #,Source,Description,Qty,Long Lead,Type,Ordered,Received
CSA00010-KIT,Acme Vendor,Standard Spa Kit (145 parts),1,,BUNDLE,,
McMaster 1234-567,McMaster-Carr,Hex Bolt 1/4-20 x 1",24,,PART,,
SPN4567,Supplier XYZ,Custom Bracket Assembly,2,YES,PART,,
```

---

### 7.2 BOM Quantity Sync Endpoint

**Feature Added:** 2026-07-16 (Commit: cffd2a3)

The Master Design Book system now includes an **automatic BOM quantity synchronization** feature that resolves quantity mismatches between the template project's flat `mrp_project_parts` table and the actual BOM rollup calculations.

**Endpoint:** `POST /api/mrp/design-books/{book_code}/sync-quantities`

**Purpose:** When BOM exports from Creo change quantities in the `bom` table, the `mrp_project_parts` quantities (in the template project) can become stale. This endpoint recalculates the correct quantities from the BOM tree and updates the template project to match.

**Returns:** JSON with:
```typescript
{
  book_code: string
  updated: Array<{
    item_number: string
    old_qty: number
    new_qty: number
  }>
  unchanged: number
  error?: string
}
```

**Algorithm (`sync_quantities_from_bom`):**
1. Loads all `mrp_project_parts` for the template project
2. Fetches the `top_assembly_id` from the project
3. Builds a parent-child BOM map from the `bom` table
4. Recursively calculates the rollup quantity for each part from the top assembly down
5. Compares calculated quantities to stored quantities in `mrp_project_parts`
6. Updates any mismatched rows with the correct BOM rollup quantity
7. Skips `zz*` reference items (not real parts)
8. Returns list of updated items with old/new quantities

**Automatic Integration in Check & Update Flow:**

When the user clicks "Check for Changes" in `MasterDesignBookView.vue`, the system:
1. Builds the master model and checks for quantity mismatches
2. If mismatches are detected and `allow_qty_mismatch` is not set:
   - **Automatically calls** `syncQuantities(bookCode)`
   - Updates the database with corrected quantities
   - Rebuilds the master model with fresh data
   - Shows success message: `"Synced N quantities from BOM: item1: 4->6; item2: 2->4"`
3. If mismatches still exist after sync (edge cases), shows error and prompts user to enable "Allow qty mismatch"
4. Only then proceeds to diff and show the update modal

**Implementation:**

**Backend:**
- `backend/app/services/master_design_book.py::sync_quantities_from_bom(supabase, template_project_id)`
  - Core algorithm: BOM rollup calculation with memoization
  - Updates `mrp_project_parts.quantity` where mismatches found
  - Returns `{updated: [...], unchanged: int}`
- `backend/app/services/master_design_book.py::sync_book_quantities(book_code)`
  - Public wrapper that loads the book and template project
  - Calls `sync_quantities_from_bom` with the template project ID
  - Returns result with `book_code` added
- `backend/app/routes/design_books.py`
  - Added `POST /{book_code}/sync-quantities` endpoint
  - Maps to `sync_book_quantities(book_code)`

**Frontend:**
- `frontend/src/services/designBook.ts::syncQuantities(bookCode)`
  - TypeScript interface `SyncQuantitiesResult`
  - Calls `POST /api/mrp/design-books/{book_code}/sync-quantities`
  - Returns parsed JSON result
- `frontend/src/views/MasterDesignBookView.vue::checkAndUpdate()`
  - Modified to auto-call `syncQuantities()` when `!master.qtyCheck.ok && !allowQtyMismatch`
  - Displays synced quantities in success message before proceeding
  - Rebuilds master model after sync to ensure fresh data
  - Falls back to error message if sync doesn't resolve all mismatches

**Use Case:**

**Before this feature:** When Jack exported a new mBOM from Creo that changed quantities (e.g., increased fastener count from 4 to 6), the Design Book Check & Update would fail with a quantity mismatch error. He would need to manually find and update each part quantity in the template project before proceeding.

**After this feature:** The system automatically detects the mismatch, calculates the correct quantities from the BOM tree, updates the database, and proceeds with the update. Jack sees a success message showing what was synced and continues seamlessly.

**Related Schema:**
- `mrp_project_parts.quantity` — Flat quantity field (updated by sync)
- `bom.quantity` — Per-parent-child relationship quantity (source of truth)
- `design_books.template_project_id` — Links book to its source project

**Files Changed:**
- `backend/app/services/master_design_book.py` — Added `sync_quantities_from_bom()` and `sync_book_quantities()`
- `backend/app/routes/design_books.py` — Added `POST /{book_code}/sync-quantities` endpoint
- `frontend/src/services/designBook.ts` — Added `SyncQuantitiesResult` interface and `syncQuantities()` function
- `frontend/src/views/MasterDesignBookView.vue` — Modified `checkAndUpdate()` to auto-sync on quantity mismatch

## 8. UI — MasterDesignBookView at /mrp/design-book/:bookCode

Dedicated view (dashboard slideout too narrow; MrpBuildBookView is an opposite
lifecycle). Dark theme per style.md; nav button on MRP dashboard header.

- Header: title, book rev badge, product/template meta; action bar: **Check for
  Changes** (dry run) / **Update Book** (opens diff modal) / **Full PDF** / **Purchase
  List** / **Change Notice**.
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

---

## 12. Implementation History & Design Changes

### 12.1 Work Package Consolidation: One Per Station (2026-07-21)

**Change:** Simplified Section I work packages from "one per (day, station)" to "one per station" (all parts consolidated).

**Before:**
- Work packages grouped by `(day, station_id)` — e.g., `I-SAW-1` (day 0), `I-SAW-2` (day 1), `I-TIG-1` (day 0), `I-TIG-2` (day 1)
- Section identity: `{ station_code, occurrence }` where `occurrence` = 1-based index of that station's packages ordered by day
- Display metadata: `{ day: 0 }`
- Section code format: `I-{ABBREV}-{occurrence}` (e.g., `I-SAW-1`, `I-SAW-2`)

**After:**
- Work packages grouped by `station_id` only — e.g., `I-SAW`, `I-TIG` (all parts from all days consolidated into one section per station)
- Section identity: `{ station_code }` (occurrence removed)
- Display metadata: `null` (no day field)
- Section code format: `I-{ABBREV}` (e.g., `I-SAW`, `I-TIG`)

**Rationale:**

Days aren't finalized yet — detailed daily scheduling is tracked on a separate tracking sheet, not in the Master Design Book. The Design Book should show **WHAT parts** go through each station (the canonical build process), not **WHEN** (the schedule).

Key benefits:
1. **Stable section codes** — `I-SAW` doesn't become `I-SAW-1` and `I-SAW-2` when scheduling changes
2. **Simpler structure** — fewer sections, less pagination, easier to navigate
3. **No phantom re-numbering** — schedule shifts don't trigger section renaming/retiring
4. **Matches user mental model** — "saw package" vs "first saw package on day 0"

**Impact on Existing Design Books:**

This is a **breaking change** to section identity. Old sections with `{ station_code, occurrence }` will NOT match new sections with `{ station_code }` only. As a result:
- Old sections (e.g., `I-SAW-1`, `I-SAW-2`) will be marked **RETIRED**
- New consolidated sections (e.g., `I-SAW`) will be marked **NEW** at rev A
- Change notice will show: `REMOVED I-SAW-1` / `REMOVED I-SAW-2` / `NEW I-SAW`

This is a **one-time migration** and is acceptable as a design change (not a bug). Future updates will correctly diff the consolidated sections.

**Files Modified:**

1. **`frontend/src/utils/buildBook.ts` (lines 308-334):**
   - Changed grouping key from `${t.start_day}|${t.station_id}` to `${t.station_id}`
   - Removed day-based sorting dimension (now sorts by station `sort_order` only)
   - Added comment: "group by station only, not day"
   - Package day calculation: `Math.min(...tasks.map(t => t.start_day))` (earliest day any task at this station starts)

2. **`frontend/src/utils/masterDesignBook.ts` (lines 441-510):**
   - **Removed occurrence counting logic entirely** (no longer needed)
   - Changed section code from `I-${p.stationAbbrev}-${occ}` to `I-${p.stationAbbrev}`
   - Changed section identity from `{ station_code, occurrence }` to `{ station_code }`
   - Changed display from `{ day: p.day }` to `null`
   - Added comments explaining "one section per station, no occurrence" and "scheduling tracked externally on tracking sheet"

**Section Structure Comparison:**

| Aspect | Before (Day-Based) | After (Station-Based) |
|--------|--------------------|-----------------------|
| **Section Code** | `I-SAW-1`, `I-SAW-2` | `I-SAW` |
| **Identity (match key)** | `{station_code, occurrence}` | `{station_code}` |
| **Display** | `{day: 0}` | `null` |
| **Parts Included** | Only parts scheduled for that station on that day | All parts for that station, across all days |
| **Grouping Logic** | `${t.start_day}|${t.station_id}` | `${t.station_id}` |
| **Occurrence Field** | 1-based index per station (e.g., 1st saw pkg = `1`) | Not used |
| **Day Field** | Specific scheduled day (0, 1, 2...) | Earliest day (metadata only, not in identity) |

**Code Diff (buildBook.ts:308-334):**

```typescript
// OLD:
const key = `${t.start_day}|${t.station_id}`  // group by day AND station

const groupEntries = [...pkgGroups.entries()].sort((a, b) => {
  const [dayA, stationA] = a[0].split('|')
  const [dayB, stationB] = b[0].split('|')
  const dayDiff = parseInt(dayA!) - parseInt(dayB!)
  if (dayDiff !== 0) return dayDiff
  return sortOrderOf(stationA!) - sortOrderOf(stationB!)
})

// NEW:
const key = t.station_id  // group by station only, not day

const groupEntries = [...pkgGroups.entries()].sort((a, b) => {
  return sortOrderOf(a[0]) - sortOrderOf(b[0])
})
```

**Code Diff (masterDesignBook.ts:441-510):**

```typescript
// OLD:
const pkgCode = new Map<string, string>()
const occurrences = new Map<string, number>()  // station_code -> next occurrence number
for (const p of book.packages) {
  const stationCode = stationCodeOf.get(p.stationName) ?? p.stationAbbrev
  const occ = (occurrences.get(stationCode) ?? 0) + 1
  occurrences.set(stationCode, occ)
  pkgCode.set(p.id, `I-${p.stationAbbrev}-${occ}`)
}

sections.push({
  section_code: code,
  identity: { station_code: stationCode, occurrence: occ },
  display: { day: p.day },
  // ...
})

// NEW:
const pkgCode = new Map<string, string>()
for (const p of book.packages) {
  pkgCode.set(p.id, `I-${p.stationAbbrev}`)
}

sections.push({
  section_code: code,
  identity: { station_code: stationCode },  // one section per station, no occurrence
  display: null,  // No day field - scheduling tracked externally on tracking sheet
  // ...
})
```

**Related Documentation:**
- Section 3 (Section identity & codes) — Updated to reflect new identity without occurrence
- Section 4.5 (Determinism requirement) — Still applies (canonical sorting by station only)
- Section 5 (Rendering rules) — No changes needed (day labels already used `D1..Dn` format)

**Version:** First implemented in v3.9.6 (2026-07-21)
