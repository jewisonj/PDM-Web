# PDM System - Version History and Release Notes

**Track changes, updates, and system evolution across all versions**
**Related Docs:** [27-WEB-MIGRATION-PLAN.md](27-WEB-MIGRATION-PLAN.md), [15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md](15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md)

---

## Current Version

### v3.9.4 (2026-07-18) -- Part Number Generator Improvements

**Status:** Current Production Release

**Summary:** Fixed Part Number Generator to fill gaps in part number sequences instead of always incrementing from the highest number, and persisted copied numbers server-side to survive browser refresh.

#### Features Added

**1. Gap-Filling Number Generation**

- **Backend Endpoint:** `GET /api/items/available-numbers/{prefix}`
  - Returns lowest available numbers per prefix (fills gaps first)
  - Considers both items in PDM and reserved numbers in `used_item_numbers` table
  - Replaces frontend's direct Supabase queries with centralized API logic

- **Problem Solved:** Previously, generator found highest number and incremented (e.g., if csp0030 existed, always returned csp0031+), skipping all gaps in lower ranges. Now returns lowest available numbers, filling gaps first.

**2. Server-Side Number Reservation**

- **Database Table:** `used_item_numbers` (new)
  - Tracks copied/reserved numbers that aren't yet in PDM
  - Auto-cleanup trigger removes entry when item is created in PDM
  - RLS enabled for authenticated users
  - Migration: `backend/migrations/2026-07-18_used_item_numbers.sql`

- **Backend Endpoint:** `POST /api/items/mark-number-used`
  - Marks number as reserved when copied to clipboard
  - Returns success confirmation

- **Problem Solved:** Previously, copied numbers were only tracked in browser memory and lost on refresh. Now persisted server-side so numbers stay reserved across sessions.

**3. Improved UI Feedback**

- Shows count of items in PDM and reserved numbers per prefix
- Numbers disappear immediately from list when copied
- Calls API instead of direct Supabase queries

#### Use Case

Jack needs a new part number. Opens Part Number Generator, sees csp0015 (gap from deleted part) instead of csp0031 (highest + 1). Clicks csp0015, copies to clipboard, number disappears from list and stays gone after browser refresh. When Jack creates the item in PDM, the reservation is auto-deleted.

#### Files Changed

**Backend:**
- `backend/app/routes/items.py` — Added `/available-numbers/{prefix}` and `/mark-number-used` endpoints
- `backend/migrations/2026-07-18_used_item_numbers.sql` — Created `used_item_numbers` table with auto-cleanup trigger

**Frontend:**
- `frontend/src/views/PartNumbersView.vue` — Refactored to call API, added counts display

#### Documentation

- `Documentation/24-VERSION-HISTORY.md` — This entry
- `Documentation/03-DATABASE-SCHEMA.md` — Added `used_item_numbers` table section

---

### v3.9.3 (2026-07-16) -- Master Design Book Enhancements

**Status:** Released

**Summary:** Two key enhancements to the Master Design Book system: (1) CSV export for purchase lists to streamline procurement, and (2) automatic BOM quantity synchronization to fix stale template project quantities when mBOM exports change.

#### Features Added

**1. Purchase List CSV Download**

- **Backend Endpoint:** `GET /api/mrp/design-books/{book_code}/purchase-list`
  - Reads `buyList` and `bundles` from spine section's `source.payload`
  - Returns CSV with columns: Part #, Source, Description, Qty, Long Lead, Type, Ordered, Received
  - Bundles listed first as Type=BUNDLE (ordered as complete kits)
  - Individual parts listed as Type=PART (mmc/spn items)
  - Applies ASCII sanitization to vendor names and descriptions
  - Filename format: `{book_code}-purchase-list-rev{N}.csv`

- **Frontend UI:** "Purchase List" button in MasterDesignBookView header
  - Downloads CSV file via browser download API
  - Disabled for first-generation books (rev 0)
  - Shows spinner during download
  - Success toast displays item count

- **Spine Section Rename:** Updated section title from "MASTER CHECKLIST + TOC" to "CHECKLIST + BUY LIST + TOC" to reflect the buy list is included in spine content

**2. Automatic BOM Quantity Synchronization** (Commit: cffd2a3)

- **Backend Endpoint:** `POST /api/mrp/design-books/{book_code}/sync-quantities`
  - Calculates correct quantities from BOM tree rollup (source of truth)
  - Updates stale `mrp_project_parts.quantity` rows in the template project
  - Skips `zz*` reference items (not real parts)
  - Returns list of updated items with old→new quantity changes

- **Backend Service:** `master_design_book.py::sync_quantities_from_bom()`
  - Recursive BOM rollup calculation with memoization
  - Detects mismatches between flat project quantities and BOM rollup
  - Bulk updates database with correct quantities

- **Frontend Integration:** Automatic sync in Check & Update workflow
  - When quantity mismatches detected and `allow_qty_mismatch` is not set:
    - Automatically calls `syncQuantities()` to fix database
    - Shows success message with list of synced items
    - Rebuilds master model with fresh data
    - Proceeds seamlessly to update modal
  - Eliminates manual quantity correction workflow

#### Use Cases

**Purchase List:** Jack can download the complete purchase list as a CSV file for procurement. The CSV includes blank "Ordered" and "Received" columns that can be printed and used as a manual tracking checklist when ordering parts from vendors.

**BOM Quantity Sync:** When Jack exports a new mBOM from Creo that changes quantities (e.g., increased fastener count from 4 to 6), the system automatically detects the mismatch, recalculates correct quantities from the BOM tree, updates the database, and proceeds with the Design Book update. Previously, Jack would see a quantity mismatch error and need to manually find and fix each part quantity before proceeding.

#### Files Changed

**Purchase List:**
- `backend/app/routes/design_books.py` — Added purchase-list endpoint
- `backend/app/services/master_design_book.py` — Added `get_purchase_list_csv()` function
- `frontend/src/services/designBook.ts` — Added `downloadPurchaseList()` service
- `frontend/src/utils/masterDesignBook.ts` — Updated spine section title
- `frontend/src/views/MasterDesignBookView.vue` — Added "Purchase List" button

**BOM Sync:**
- `backend/app/services/master_design_book.py` — Added `sync_quantities_from_bom()` and `sync_book_quantities()`
- `backend/app/routes/design_books.py` — Added `POST /{book_code}/sync-quantities` endpoint
- `frontend/src/services/designBook.ts` — Added `SyncQuantitiesResult` interface and `syncQuantities()` function
- `frontend/src/views/MasterDesignBookView.vue` — Modified `checkAndUpdate()` to auto-sync on quantity mismatch

#### Documentation

- Updated `Documentation/36-MASTER-DESIGN-BOOK-PLAN.md`:
  - §7.1 — Purchase List CSV Export
  - §7.2 — BOM Quantity Sync Endpoint (new)
  - Updated API endpoint table in §7 to include sync-quantities endpoint

---

### v3.9.2 (2026-07-07) -- AI Assistant

**Status:** Current Production Release

**Summary:** Added Claude-powered AI assistant at `/mrp/assistant` for natural-language querying of PDM data. Users can ask questions like "How many parts are in assembly csa00010?" or "Pull me the print of csp00200" and receive immediate answers with data grounded in the database. This is a **read-only v1** implementation with no write operations, no authentication (uses admin Supabase client), and in-memory session storage. Features SSE streaming responses, tool status indicators, markdown rendering, and prompt caching for cost optimization.

#### Features Added

**AI Assistant Chat Interface**

- **Frontend UI:** Full-screen chat view at `/mrp/assistant` with empty-state suggestions, message bubbles (user right/blue, assistant left/dark), markdown rendering with syntax highlighting, tool status indicators, typing animation, and auto-scroll
- **Backend Endpoint:** `POST /api/assistant/chat` with SSE streaming response (events: `start`, `text`, `tool`, `done`, `error`)
- **Agent Loop:** Server-side tool execution with max 8 iterations per turn to prevent runaway loops
- **Session Management:** In-memory LRU cache for 50 conversations, max 40 messages per conversation (auto-trimmed)
- **Model:** Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) with prompt caching enabled (90% cost reduction on cached turns)

**Six Read-Only Tools**

1. `search_items` - Search by item number or name fragment
2. `get_item` - Get full details for a specific item
3. `get_bom_tree` - Recursive BOM expansion with quantities
4. `get_where_used` - Find parent assemblies (reverse BOM)
5. `list_item_files` - List files for an item (with type filter)
6. `get_file_download_link` - Generate signed download URL (1 hour expiry)

**System Prompt Engineering**

- Teaches BOM counting rule (multiply ancestor quantities, show math)
- Guides multi-step file delivery workflow (list files → get download link)
- Enforces grounding (never invent data) and concise responses
- Lowercase item number display convention (`csp00200` not CSP00200)

**Integration Points**

- "Ask PDM" button in MRP dashboard navigation bar
- Route: `/mrp/assistant` (requires auth)
- Pinia store (`assistant.ts`) for conversation state
- SSE client (`assistantApi.ts`) using fetch + ReadableStream
- Markdown rendering with `marked` and `DOMPurify` (XSS safety)

#### Configuration

- New environment variable: `ANTHROPIC_API_KEY` in `backend/.env` (optional, disables assistant if not set)
- New dependency: `anthropic>=0.50.0` in `backend/requirements.txt`
- Frontend dependencies: `marked`, `dompurify` (already in package.json)

#### Frontend Changes

- `frontend/src/views/MrpAssistantView.vue` (new) -- chat UI with markdown rendering
- `frontend/src/stores/assistant.ts` (new) -- Pinia store for messages and streaming state
- `frontend/src/services/assistantApi.ts` (new) -- SSE client
- `frontend/src/router/index.ts` -- added `/mrp/assistant` route
- `frontend/src/views/MrpDashboardView.vue` -- "Ask PDM" navigation button

#### Backend Changes

- `backend/app/routes/assistant.py` (new) -- SSE chat endpoint with agent loop
- `backend/app/services/assistant_tools.py` (new) -- 6 tool implementations + Anthropic schemas
- `backend/app/config.py` -- added `anthropic_api_key` setting
- `backend/app/main.py` -- registered assistant router
- `backend/app/routes/__init__.py` -- imported assistant router
- `backend/requirements.txt` -- added `anthropic>=0.50.0`

#### Known Limitations (v1)

- **No authentication** - Skipped JWT validation, uses Supabase admin client (bypasses RLS)
- **In-memory sessions only** - Conversations lost on server restart
- **No conversation history** - Cannot resume old conversations after clearing
- **No rate limiting** - Could be abused if exposed publicly
- **Read-only** - Cannot create/update/delete items, check out files, or trigger workflows

#### Future Enhancements (v2+)

- Add JWT authentication to `/api/assistant/chat`
- Store conversations in `assistant_conversations` table
- Add write tools (`create_checkout`, `submit_feedback`) with auth
- Expand to project schedule queries, work queue status
- Add conversation search/history view

#### Performance & Cost

- **Prompt caching:** System prompt cached after first turn (90% cost reduction)
- **Typical query cost:** $0.003-0.005 per turn
- **Monthly estimate (100 queries/day):** ~$9/month
- **Token logging:** Backend logs input/output/cached tokens for monitoring

#### Testing

- Manual testing checklist included in documentation
- Example test queries for all 6 tools
- Edge cases covered (no results, not found, wrong type)

#### Related Documentation

- [33-AI-ASSISTANT.md](33-AI-ASSISTANT.md) -- Complete feature reference (architecture, tools, system prompt, examples, troubleshooting)
- [04-SERVICES-REFERENCE.md](04-SERVICES-REFERENCE.md) -- Updated with `/api/assistant/*` endpoints
- [00-TABLE-OF-CONTENTS.md](00-TABLE-OF-CONTENTS.md) -- Updated with doc 33

#### Files Changed Summary

**Backend:**
- `backend/app/routes/assistant.py` (new)
- `backend/app/services/assistant_tools.py` (new)
- `backend/app/config.py` (modified)
- `backend/app/main.py` (modified)
- `backend/app/routes/__init__.py` (modified)
- `backend/requirements.txt` (modified)

**Frontend:**
- `frontend/src/views/MrpAssistantView.vue` (new)
- `frontend/src/stores/assistant.ts` (new)
- `frontend/src/services/assistantApi.ts` (new)
- `frontend/src/router/index.ts` (modified)
- `frontend/src/views/MrpDashboardView.vue` (modified)
- `frontend/package.json` (modified - added marked, dompurify if not present)

**Documentation:**
- `Documentation/33-AI-ASSISTANT.md` (new)
- `Documentation/00-TABLE-OF-CONTENTS.md` (modified)
- `Documentation/04-SERVICES-REFERENCE.md` (modified)
- `Documentation/24-VERSION-HISTORY.md` (modified - this entry)

---

### v3.9.1 (2026-07-07) -- Build Book Section Print Sets, Document Items, Purchased Display

**Status:** Previous Release

**Summary:** Follow-up release to v3.9's Build Book. The headline change is **section print sets**: instead of downloading the whole project's prints as one large bound PDF, the shop can now pull a small, task-sized PDF for exactly one section -- the reference docs, a single work package, or a single kit -- from a new toolbar dropdown. Also formalizes two conventions used across the Tracker and Book: **document items** (controlled-document item numbers, excluded from work rows and listed as reference prints instead) and **purchased-item display** (shop-facing documents show the supplier's own part number and source, not the internal PDM item number). Includes routing/data notes from the Spa project that shaped kit sequence rendering, and three engineering gotchas worth remembering for future backend-PDF work.

#### Features Added

**Section Print Sets (Build Book toolbar)**

- **UI:** `MrpBuildBookView.vue` toolbar gained a **"— Print set —"** dropdown (`optgroup`s: Reference / Work packages / Kits) and a **"⬇ Download prints"** button, alongside the existing "Print (8.5x11 portrait)" button
- **Endpoint:** `POST /api/mrp/projects/{project_id}/section-prints` with body `{ label, items: [{ item_number, qty | null }] }`, returns the PDF directly (`application/pdf`, `Content-Disposition: attachment`) plus `X-Pages` / `X-Prints-Bound` / `X-Missing` response headers the UI reads for a status message
- **Backend:** `generate_section_prints()` in `backend/app/services/build_book.py` -- dedupes items by item number (summing quantities), resolves each item's newest PDF via the same `files`-table lookup the full book uses, downloads every resolvable PDF **in parallel** (`ThreadPoolExecutor(max_workers=8)`), renders a cover page (item list with quantity and a `MISSING` flag for anything with no print on file), stamps each print's first page with a white-backed **QTY N** box in the top-right margin (small section-label text underneath; skipped for reference-doc entries since quantity doesn't apply), merges everything with `pypdf`, and returns the bytes directly
- **Verified sizes:** PKG 03 (Waterjet) = 27 pages / 26 prints / 6.9 MB in ~11s; Design Reference set (csd00010 project) = 4 pages / 10.9 MB
- **Supersedes the full-book download as the day-to-day workflow:** the full `POST /projects/{id}/build-book` endpoint (`generate_build_book()`) still exists and still works (107 pages / 62 prints / 54 MB on the same test project) but **no longer has a UI button**. The 54 MB result exceeds Supabase's roughly 50 MB per-project storage upload cap (its own best-effort storage step silently skips anything over 45 MB), and a 100+ page bound book is unwieldy to carry to one machine for a single operation. Section print sets are purpose-sized for the task at hand.

**Per-Kit "Pull Prints" References**

- Each kit chapter in the web Build Book now lists the drawing numbers + revisions to pull before starting that kit -- `BookKit.printRefs` (`{ item_number, revision }[]`) in `frontend/src/utils/buildBook.ts`, rendered as a **PULL PRINTS** line on the kit sheet (`MrpBuildBookView.vue`)
- Built from the assembly's own print (if on file) followed by each kit part's print (if on file), deduplicated by item within the kit

**Document Items Convention**

- Item numbers with a third letter `d` (e.g. `csd00010`, `wmd0100`) are **controlled documents** -- design books, build-reference PDFs -- not physical parts: `isDocumentItem()` in `frontend/src/utils/buildTracker.ts`, checked before purchased/assembly/made classification and assigned class `'doc'`
- Document items are excluded from all work rows on both the Tracker and the Book (no station checkboxes, not counted in fab/assembly/purchased totals)
- The Build Book cover page lists every project document item under **"REFERENCE PRINTS -- READ FIRST"** with item number, title, revision, and PDF-on-file status (`book.referenceDocs`)
- **Check-in flow** (manual, no dedicated UI yet): create the item normally (`??d####` pattern), upload its PDF like any drawing, then attach it to the project via **MRP Dashboard -> manual part add**, which inserts an `mrp_project_parts` row with `is_manual = true` -- this survives every subsequent BOM reload for that project, since the reload logic only deletes `is_manual = false` rows

**Purchased-Item Display Convention**

- Shop-facing printed documents (Tracker, Build Book) now show the **supplier's own part number** for purchased items instead of the internal PDM item number, plus a new **SOURCE** column on the Tracker's purchased-parts checklist
- `purchasedDisplay()` / `purchasedSource()` in `frontend/src/utils/buildTracker.ts`: displays `items.supplier_pn` if set, else the item number with its 3-letter `mmc`/`spn` prefix stripped and uppercased (e.g. `mmc91290a115` -> `91290A115`); source shows `items.supplier_name` if set, else "McMaster-Carr" for `mmc*`, "Supplier" for `spn*`, else `--`
- Non-purchased items pass through unchanged (fab parts keep their real PDM item number on shop documents)

#### Data / Routing Notes (Spa Project, Not Code)

- `csa00080` gained a **Plumbing** routing step
- `csa00010` routing sequence became **Weld Cleanup -> Mechanical Assembly (doors) -> Vinyl Wrap -> Inspection**; Vinyl Wrap is a new workstation, station code `047`
- Assembly-method notes on individual routing steps (`routing.notes`) now render inline under the matching step in each kit's Build Book **SEQUENCE** table (`weldSeq[].notes`) -- e.g. door-hanging or wrap-application instructions print right where the shop needs them
- The Build Tracker's printed Press Brake column label changed `BRK` -> `PB` to match the Build Book's and backend print packet's abbreviations; the Tracker's internal column key is still `BRK` in code (previously documented, carried here for continuity)

#### Frontend Changes

- `frontend/src/utils/buildBook.ts` -- `BookKit.printRefs` field and derivation; `BookReferenceDoc` filtering via `isDocumentItem()`
- `frontend/src/utils/buildTracker.ts` -- `isDocumentItem()`, `purchasedDisplay()`, `purchasedSource()` exported; classifier checks `isDocumentItem()` before purchased/assembly/made; purchased-row builder uses `purchasedDisplay()`/`purchasedSource()` for `displayNumber`/`source` fields
- `frontend/src/views/MrpBuildBookView.vue` -- print-set dropdown (`sections`/`sectionGroups` computed properties), `downloadSectionPrints()`, PULL PRINTS line on kit cards, weld-sequence step notes rendering, REFERENCE PRINTS table on cover
- `frontend/src/views/MrpBuildTrackerView.vue` -- SOURCE column on the purchased-parts checklist table
- `frontend/src/utils/buildBook.test.ts` -- grew from 11 to 14 tests (printRefs, referenceDocs coverage)
- `frontend/src/utils/buildTracker.test.ts` -- grew from 15 to 17 tests (isDocumentItem, purchasedDisplay/purchasedSource coverage)
- `frontend/scripts/emit-book.ts` (new, dev-only) -- computes the `BuildBook` payload with the backend service key from `backend/.env`, writes to JSON; for exercising `/build-book` or `/section-prints` outside a browser session (`npx tsx scripts/emit-book.ts [PROJECT_CODE] [OUT_PATH]`)

#### Backend Changes

- `backend/app/services/build_book.py` -- new `generate_section_prints()` function, `_stamp_qty()` helper (white-backed QTY box overlay via a one-page reportlab canvas merged onto the print's own `mediabox` size)
- `backend/app/routes/mrp.py` -- new `POST /projects/{project_id}/section-prints` route (`SectionPrintsRequest` Pydantic model: `label: str`, `items: list[dict]`); both this and the existing `/build-book` route return a plain `fastapi.Response`, never `StreamingResponse`, over the in-memory PDF bytes

#### Engineering Notes (For Future Backend-PDF Work)

1. **Never use `StreamingResponse` over a `BytesIO` for a binary response.** Starlette iterates it line-by-line (binary "lines" split on stray `\n` bytes), observed at roughly 80 KB/s -- turns a multi-MB PDF into a multi-minute download. Use a plain `Response(content=pdf_bytes, media_type=...)` when the bytes are already fully assembled in memory.
2. **reportlab's default Helvetica/WinAnsi encoding cannot render glyphs like `✓` or `▸`.** All backend-generated PDF text must be ASCII only -- use words ("YES"/"MISSING") instead of icons. Does not affect the Vue web UI, which renders in-browser with full Unicode support.
3. `frontend/scripts/emit-book.ts` is a dev script for computing the Build Book payload with the service key, useful for endpoint testing without a browser session.

#### Known Issues / Notes

- The full-book PDF endpoint (`POST /build-book`) is not deleted or deprecated in code -- just has no UI button as of this release. May get a UI entry point again later (e.g. an end-of-project archival copy).
- Pre-existing failing test in `buildBook.test.ts` (~line 181, a `next` station assertion) noted during this release's verification pass -- unrelated to the section-prints/document-item/purchased-display work; needs separate triage.
- No format toggle for section print sets -- letter portrait cover page only, matching the rest of the Build Book.

#### Files Changed Summary

- `frontend/src/utils/buildBook.ts` -- `printRefs`, `referenceDocs` (isDocumentItem-based)
- `frontend/src/utils/buildTracker.ts` -- `isDocumentItem()`, `purchasedDisplay()`, `purchasedSource()`
- `frontend/src/views/MrpBuildBookView.vue` -- section print set dropdown/download, PULL PRINTS line, step notes, reference prints table
- `frontend/src/views/MrpBuildTrackerView.vue` -- SOURCE column
- `frontend/src/utils/buildBook.test.ts` -- 11 -> 14 tests
- `frontend/src/utils/buildTracker.test.ts` -- 15 -> 17 tests
- `frontend/scripts/emit-book.ts` (new) -- dev payload-emission script
- `backend/app/services/build_book.py` -- `generate_section_prints()`, `_stamp_qty()`
- `backend/app/routes/mrp.py` -- `POST /projects/{project_id}/section-prints` route

#### Related Documentation

- [32-BUILD-BOOK.md](32-BUILD-BOOK.md) -- Full reference, including new "Section Print Sets", "Document Items", and "Purchased-Item Display Convention" sections
- [20-COMMON-WORKFLOWS.md](20-COMMON-WORKFLOWS.md) -- Section 17 (Printing a Manufacturing Build Book), updated with the "Downloading a Section Print Set" sub-workflow
- [31-BUILD-TRACKER-SHEET.md](31-BUILD-TRACKER-SHEET.md) -- `isDocumentItem()`/`purchasedDisplay()`/`purchasedSource()` live in `buildTracker.ts`, shared by both the Tracker and the Book

---

### v3.9 (2026-07-06) -- Manufacturing Build Book (Phase 1, Web Print View)

**Status:** Previous Release (superseded by v3.9.1)

**Summary:** Added a day-by-day manufacturing Build Book per MRP project, the sibling deliverable to the v3.8 Build Tracker Sheet. Where the Tracker is a checkbox grid the shop marks up over the life of a project, the Book is a work-order packet: a cover/plan page, a station-loading calendar, sequence-numbered work packages (`PKG 01`, `PKG 02`, ...) for every part operation in dependency order, and one kit/weld sheet per assembly with a stock-pull list, weld sequence, and print-availability status. It is generated live from the same capacity-constrained scheduler that drives the Gantt, and reuses the Tracker's classification, assembly ordering, and milestone logic rather than duplicating it.

#### Features Added

**Manufacturing Build Book**

- **Access:** MRP Project Tracking (`/mrp/tracking`) -> select a project -> "📖 Build Book" button, or from the Build Tracker Sheet toolbar's own "📖 Build Book" cross-link -> `/mrp/book/:projectCode`
- **Cover/plan page:** project summary stats (est hours, work days, package count, fab/assembly/purchased counts), milestones with plan dates (reused verbatim from the Tracker's milestone derivation), hours by station-group area, and a stock-pull summary aggregated from `routing_materials x project quantity`
- **Day-by-day station loading calendar:** rows are working days with dates, columns are stations, cells show hours plus the package IDs occupying that day/station slot -- built directly from the scheduler's own `stationDays` grid, not a separate estimate
- **Part I -- Work Packages:** one card per `(planned day, station)` group of part tasks, sequence-numbered in dependency order. Each card lists a stock pull (aggregated only at each part's first routed op, so the same material line doesn't repeat on every downstream package), line items (part, description, qty, est minutes, `NEXT ->` abbreviated next station, `FOR KIT` assembly refs), stage-for-kit refs on final-op packages, and a completed-by sign-off line
- **Part II -- Kit & Weld Sheets:** one card per weldment/assembly in the same DFS post-order build sequence as the Tracker's assembly matrix -- required sub-assemblies, a kit parts table with `READY BY` (the package + day that produces each part), the assembly's own weld/assembly sequence with est minutes, an inspection sign-off line, and a print-availability line (assembly print yes/no + `n/m` part prints)
- **Recorded-complete rendering:** packages, lines, and kit rows already recorded complete in `part_completion` print with filled checkboxes and, at the package level, a "RECORDED COMPLETE" badge -- same completion source and semantics as the Tracker and `MrpShopView` (no separate "book completion" concept, and no pre-fill toggle -- recorded completion always renders since the Book is meant to be regenerated as work progresses, not marked up by hand)
- **Sequence-first, dates-advisory (key design decision):** `PKG NN` numbers govern the order the shop should work in; the printed planned day/date on each package is guidance only. The cover page states this directly. This keeps the book valid when the live schedule drifts from the plan -- see `32-BUILD-BOOK.md` for the full rationale
- **Print layout:** letter portrait only (8.5in x 11in, 0.5in margins), no format toggle -- sections use `page-break-after: always`, cards use `break-inside: avoid` so a package/kit is never split across a page boundary

#### Frontend Changes

**New Module:** `frontend/src/utils/buildBook.ts`

Pure data-shaping logic with no Supabase access, composing directly on top of `buildTrackerSheet()` (from `buildTracker.ts`) and a `ScheduleResult` (from `calculateSchedule()`):
- Work packages: part tasks (excluding assembly-level tasks) grouped by `(start_day, station_id)`, sorted by day then station `sort_order`
- Kit chapters: one per `sheet.asmRows` entry, reusing the Tracker's merged per-assembly part groups (`groupByRef`) to recover each kit's part list even though the Tracker may have split that group across print columns/pages
- Calendar matrix: direct read of `schedule.stationDays[code][day].used_minutes`
- Stock pull aggregation: `routing_materials` joined to `raw_materials`, multiplied by project quantity, aggregated at each item's first routed operation only
- `STATION_ABBREV` map exported, deliberately mirroring the backend's `print_packet.py` `STATION_ABBREV` -- **keep both in sync if either changes**. Note this uses `PB` for Press Brake, while the Build Tracker's `PART_COLUMNS` uses `BRK` for the same station -- the two abbreviation schemes are independent

**New Test File:** `frontend/src/utils/buildBook.test.ts` -- 11 Vitest unit tests against a fixture project mirroring `buildTracker.test.ts`'s fixture shape. Run with `cd frontend && npx vitest run` (39 tests total across `scheduling.test.ts` (13), `buildTracker.test.ts` (15), `buildBook.test.ts` (11)).

**New View:** `frontend/src/views/MrpBuildBookView.vue`

- Loads `mrp_projects`, `mrp_project_parts`, `bom`, `routing`, `part_completion`, `workstations` (same base query pattern as `MrpBuildTrackerView`), plus two new queries this feature added: `routing_materials` (+ `raw_materials` join, for stock pulls) and `files` (`file_type = 'PDF'`, for print availability)
- Runs `calculateSchedule()` then `buildBook()` to produce the `BuildBook` structure
- Renders flowing letter-portrait "sheet" divs (cover, calendar, packages, kits) with dark MRP toolbar chrome and cross-links to the Tracker Sheet

**Modified:** `frontend/src/router/index.ts` -- new route `mrp-build-book` at `/mrp/book/:projectCode` (`requiresAuth: true`)

**Modified:** `frontend/src/views/MrpProjectTrackingView.vue` -- added "📖 Build Book" button and `openBuildBook()` navigation helper

**Modified:** `frontend/src/views/MrpBuildTrackerView.vue` -- added "📖 Build Book" cross-link button in the toolbar

#### Design Decisions (User-Confirmed, 2026-07-06)

- Structure = plan page + work packages + kit chapters, all three sections shipped together as phase-1 scope, not staged in incrementally
- Sequence-first, dates-advisory: `PKG NN` numbers are the operative ordering; planned days are guidance (see dedicated rationale in `32-BUILD-BOOK.md`)
- Prints are shown as availability status only in phase 1 (checkmark + `n/m` ratio); actually embedding PDF pages into the book is deferred to a planned phase 2 backend PDF endpoint
- Delivery order: web view first (this release), backend PDF-rendering endpoint next (not yet built)

#### Known Issues / Notes

- Calls `buildTrackerSheet()` internally with `format: 'tabloid'` purely to satisfy that function's required parameter -- no tabloid-specific pagination fields from the returned sheet are used, so this has no effect on the Book's own letter-only layout
- Inherits every classification/ordering caveat already documented for the Build Tracker (`31-BUILD-TRACKER-SHEET.md`): `mrp_project_parts` flat-quantity vs. BOM-tree rollup disagreement, part-level weld ops not surfacing outside the assembly context, Plumbing/Wiring folding into a single station bucket at the assembly level
- No format toggle and no pre-fill toggle -- both deliberate simplifications versus the Tracker for phase 1
- Pre-existing `PdfMeasure.vue` TypeScript errors still fail `npm run build` -- unrelated, previously flagged in v3.8

#### Files Changed Summary

- `frontend/src/utils/buildBook.ts` (new) -- Data-shaping module (packages, kits, calendar, stock summary)
- `frontend/src/utils/buildBook.test.ts` (new) -- 11 unit tests
- `frontend/src/views/MrpBuildBookView.vue` (new) -- Printable book view
- `frontend/src/router/index.ts` -- New route registration
- `frontend/src/views/MrpProjectTrackingView.vue` -- Added launch button
- `frontend/src/views/MrpBuildTrackerView.vue` -- Added cross-link button to the Book

#### Related Documentation

- [32-BUILD-BOOK.md](32-BUILD-BOOK.md) -- Full reference: work package/kit chapter derivation, station abbreviations, sequence-vs-dates rationale, phase 2 plan
- [31-BUILD-TRACKER-SHEET.md](31-BUILD-TRACKER-SHEET.md) -- Sibling feature; classification, DFS assembly ordering, and milestone derivation are reused directly by the Book via `buildTrackerSheet()`
- [20-COMMON-WORKFLOWS.md](20-COMMON-WORKFLOWS.md) -- Section 15 (Project Scheduling) for `calculateSchedule()`; new Section 17 (Printing a Build Book)
- [06-BOM-COST-ROLLUP-GUIDE.md](06-BOM-COST-ROLLUP-GUIDE.md) -- BOM flat-quantity vs. tree-rollup caveat, same one inherited from the Tracker

---

### v3.8 (2026-07-05) -- Shop-Floor Build Tracker Sheet

**Status:** Previous Release (superseded by v3.9)

**Summary:** Added a printable per-project Build Tracker sheet for shop-floor progress marking on paper. Fab parts are grouped under their parent weldment with per-station checkboxes, a weldments/assemblies matrix, derived build milestones with plan dates, a purchased-parts receive checklist, a daily log, and a shortages block. The sheet regenerates from live data on every print, with already-completed stations pre-filled as solid boxes so a mid-project reprint resumes where the shop left off.

#### Features Added

**Build Tracker Sheet**

A new printable view gives the shop floor a paper twin of the same completion data already tracked digitally in the Gantt (Project Tracking) and Shop view:

- **Access:** MRP Project Tracking (`/mrp/tracking`) -> select a project -> "Print Build Tracker Sheet" button -> `/mrp/tracker/:projectCode`
- **Per-station checkboxes:** Fab parts get a box per routing station (SAW/WJ/BRK/BND/DBR/INS/STG), not a single "fab complete" box
- **Assembly matrix:** Second table with JIG/TIG/DS/WCU/ASM/INS columns for weldments and assemblies, ordered by DFS post-order traversal from the project's top assembly
- **Milestones:** 7 standard build milestones (op 10-70: purchased ordered, purchased received, all cut/deburred, all welded, assembly complete, final inspection, ship) with plan dates derived from the existing scheduling engine
- **Purchased parts checklist:** Compact receive checklist; long-lead (`spn`, receive-only) items get ORD+RCV columns, `mmc` stock hardware gets RCV only
- **Pre-fill toggle:** "Pre-fill recorded progress" checkbox in the toolbar; off prints a blank sheet, on prints already-recorded stations as solid boxes with partials shown as a handwritten tally
- **Two print formats:** 11x17 tabloid (whole project on one page when it fits) or 8.5x11 landscape letter (parts pages followed by a dedicated "Assemblies & Status" page); a dynamic `@page` CSS rule matches the browser print dialog to the selected format
- **Photo-capture groundwork (future phase):** every row carries a stable printed ID (`F##`/`A##`/`P##`/`M##`), three corner anchor squares, a QR code encoding the tracker's own URL, and dropout-gray shading -- none of this is wired to a capture pipeline yet, but the layout is built so a later Claude-vision photo-sync phase doesn't require reworking the sheet

**Completion Semantics**

Matches `MrpShopView` exactly: one `part_completion` row per (project, item, station), upserted with `qty_complete`. A station reads as "done" on the sheet when the recorded quantity covers the item's full project quantity. Duplicate rows of the same item (used both directly on a parent and inside a sub-assembly) allocate partial completion across rows in printed order so the same inventory isn't double-counted as done twice.

#### Frontend Changes

**New Module:** `frontend/src/utils/buildTracker.ts`

Pure data-shaping logic with no Supabase access (so the same logic can later back a photo-sync pipeline):
- Item classification (assembly / made / purchased / reference `zz*`) based on item number prefix and routing station groups
- DFS post-order assembly ordering from `mrp_projects.top_assembly_id`
- Per-parent part grouping with quantity computed as `bom.quantity x parent project quantity` (sidesteps known BOM flat-quantity rollup disagreements by working from the BOM tree directly)
- Station-column mapping (`PART_COLUMNS`, `ASM_COLUMNS` constants)
- Pre-fill logic reading `part_completion`, with partial-quantity allocation across duplicate item rows
- Format-aware pagination (tabloid: 48 rows/column with rail reserve; letter: 32 rows/column plus dedicated status page)

**New Test File:** `frontend/src/utils/buildTracker.test.ts` -- 15 Vitest unit tests against a fixture project. Run with `cd frontend && npx vitest run`.

**New View:** `frontend/src/views/MrpBuildTrackerView.vue`

- Loads `mrp_projects`, `mrp_project_parts`, `bom`, `routing`, `part_completion`, `workstations` via Supabase (same query pattern as `MrpProjectTrackingView`)
- Runs `calculateSchedule()` for milestone plan dates
- Renders paper pages using CSS Grid area layouts (`t-main`/`t-cont`/`l-parts`/`l-status`)
- Injects a dynamic `@page` size `<style>` block per selected format
- Computes a live fit-to-width scale factor for on-screen preview (display only, does not affect the printed page size)
- Renders a QR code via the new `qrcode` npm dependency

**Modified:** `frontend/src/router/index.ts` -- new route `mrp-build-tracker` at `/mrp/tracker/:projectCode` (`requiresAuth: true`)

**Modified:** `frontend/src/views/MrpProjectTrackingView.vue` -- added "Print Build Tracker Sheet" button and `openBuildTracker()` navigation helper

**New Dependency:** `qrcode` (+ `@types/qrcode`) added to `frontend/package.json`

**New Dev Config:** `.claude/launch.json` -- new dev-server launch configuration for the frontend (port 5174)

#### Design Decisions (User-Confirmed)

- Per-station boxes, not one box per phase, matching how the shop actually signs off work station by station
- Heavy-X-in-pen marking convention on paper, with quantity handwritten for partial completions
- Purchased items get a compact receive checklist rather than per-station boxes
- Web print view is phase 1; tablet-based interactive marking and a Claude-vision photo-sync pipeline are explicitly deferred future phases
- Approved visual mockup: https://claude.ai/code/artifact/0f926826-c666-4904-a92b-7889314006f7

#### Known Issues / Notes

- Pre-existing `PdfMeasure.vue` TypeScript errors still fail `npm run build` -- unrelated to this feature, flagged separately
- `mrp_project_parts` flat quantities can disagree with the BOM-tree cost rollup (known issue, see `06-BOM-COST-ROLLUP-GUIDE.md`); the tracker avoids this by grouping from the BOM tree directly
- Part-level weld operations in a part's own routing (e.g. `csp00210` having JIG/TIG steps directly) are not shown as fab-part columns -- only reflected at the assembly-matrix level
- Plumbing and Wiring stations both fold into the single ASM column on the assembly matrix

#### Files Changed Summary

- `frontend/src/utils/buildTracker.ts` (new) -- Data-shaping module
- `frontend/src/utils/buildTracker.test.ts` (new) -- 15 unit tests
- `frontend/src/views/MrpBuildTrackerView.vue` (new) -- Printable sheet view
- `frontend/src/router/index.ts` -- New route registration
- `frontend/src/views/MrpProjectTrackingView.vue` -- Added launch button
- `frontend/package.json` -- Added `qrcode` dependency
- `.claude/launch.json` (new) -- Frontend dev-server launch config

#### Related Documentation

- [31-BUILD-TRACKER-SHEET.md](31-BUILD-TRACKER-SHEET.md) -- Full reference: classification rules, station columns, pre-fill semantics, milestones, pagination, photo-capture readiness
- [20-COMMON-WORKFLOWS.md](20-COMMON-WORKFLOWS.md) -- Section 15 (Project Scheduling) -- consumed for milestone plan dates
- [06-BOM-COST-ROLLUP-GUIDE.md](06-BOM-COST-ROLLUP-GUIDE.md) -- BOM flat-quantity vs. tree-rollup caveat referenced by the tracker's grouping logic

---

### v3.7.6 (2026-05-28) -- PDF Measurement Tool

**Status:** Previous Release (superseded by v3.8)

**Summary:** Added interactive PDF measurement tool allowing shop floor to measure dimensions on drawings. Includes calibration mode, measurement mode, and magnifier overlay.

#### Features Added

**PDF Measurement Tool**

Allows shop floor users to measure dimensions directly on PDF drawings without leaving the application:

- **Calibration Mode:** Click "Calibrate" → draw line on known dimension (e.g., 1" scale bar) → enter actual length → click "Calibrate"
- **Measurement Mode:** Click "Measure" → click two points on PDF → distance calculated in calibrated units
- **Unit Selection:** Toggle between inches (in) and millimeters (mm)
- **Magnifier Overlay:** 3x zoom magnifier (120px circle) assists with precise point selection
- **Multi-Page Support:** Page up/down buttons to navigate multi-page PDFs
- **Stored Measurements:** All measurements shown in list below PDF
- **Clear Measurements:** Button to clear all measurements and start fresh

**Integration Points:**

- **Part Lookup Page:** "Measure" button next to PDF viewer in MrpPartLookupView
- **Shop Terminal:** "Measure" button on Shop View (MrpShopView)

**User Workflow:**

1. Open a part with PDF in Part Lookup or Shop Terminal
2. Click "Measure" button to open measurement tool
3. Click "Calibrate" → draw line on known dimension on PDF
4. Enter actual length (e.g., 1" for scale bar)
5. Click "Calibrate" button → scaling established
6. Click "Measure" → click two points on PDF
7. Distance appears in list below (in calibrated units)
8. Repeat for multiple measurements
9. Click X to close measurement tool

#### Backend Changes

No backend changes required. Feature uses existing PDF URLs from Supabase Storage.

#### Frontend Changes

**New Component:** `frontend/src/components/PdfMeasure.vue`

- Standalone measurement component
- Props: `pdfUrl` (string), `partNumber` (optional string)
- Emits: `close` event
- Uses PDF.js library for document rendering
- Canvas overlays for measurement visualization

**Modified Files:**

- `frontend/src/views/MrpPartLookupView.vue` -- Added "Measure" button in PDF detail panel
- `frontend/src/views/MrpShopView.vue` -- Added "Measure" button in PDF viewer

**Technical Decision: shallowRef for PDF.js**

The PDF.js `PDFDocumentProxy` object contains private class fields that become inaccessible when wrapped in a Vue reactive proxy. Solution: Use `shallowRef()` instead of `ref()`:

```typescript
// WRONG: Vue proxy breaks PDF.js internal state
const pdfDoc = ref<pdfjsLib.PDFDocumentProxy | null>(null)

// CORRECT: shallowRef skips proxy wrapping, keeps object intact
const pdfDoc = shallowRef<pdfjsLib.PDFDocumentProxy | null>(null)
```

This is a critical pattern when integrating external libraries that use private fields or Symbol-based properties.

#### Use Cases

- **Dimension Verification:** Shop floor verifies drawing dimensions before manufacturing
- **Off-the-Shelf Parts:** Measure supplier datasheets to verify part dimensions
- **Quality Control:** Compare actual manufactured parts against PDF drawing dimensions
- **Design Review:** Engineers verify dimensions without opening CAD software
- **Documentation:** No need to print drawings or use separate measurement tools

#### Files Changed Summary

- `frontend/src/components/PdfMeasure.vue` (new) -- Measurement tool component
- `frontend/src/views/MrpPartLookupView.vue` -- Added measure button and modal
- `frontend/src/views/MrpShopView.vue` -- Added measure button and modal
- `TODO.md` -- Updated with v3.7.6 feature list

#### Technical Notes

- Calibration unit is global to measurement session (applies to all subsequent measurements)
- Magnifier zoom is 3x and centered on mouse cursor
- Canvas rendering uses `scale` factor (1.5x by default) for crisp display
- Pixel-to-unit conversion: `distance_in_units = pixel_distance / calibration_scale`
- PDF pages rendered on demand (not all pages pre-rendered)

---

### v3.7.5 (2026-05-27) -- Auto-Queue DXF Generation

**Status:** Previous Release

**Summary:** Re-enabled automatic DXF generation queuing when STEP files are uploaded for items with `needs_dxf=true` flag.

#### Features Added

**Auto-Queue DXF for STEP Uploads**

When a STEP file is uploaded for an item that has `needs_dxf=true` in the routing:

- **Automatic Detection:** Upload endpoint checks item's `needs_dxf` flag after STEP file upload
- **Work Queue Entry:** Creates pending GENERATE_DXF job with item_id, file_id, and payload
- **Payload Includes:** `item_number` and `auto_queued: true` flag for tracking
- **No Manual Action:** Engineers no longer need to manually queue DXF generation for sheetmetal parts

**Backend Changes:**

`POST /api/files/upload` in `backend/app/routes/files.py`:

```python
# Auto-queue DXF generation for STEP files when item has needs_dxf flag
if file_type == "STEP":
    item_check = supabase.table("items").select("needs_dxf").eq("id", item_id).single().execute()
    if item_check.data and item_check.data.get("needs_dxf", False):
        supabase.table("work_queue").insert({
            "item_id": item_id,
            "file_id": file_record["id"],
            "task_type": "GENERATE_DXF",
            "status": "pending",
            "payload": {"item_number": clean_item_number, "auto_queued": True}
        }).execute()
```

#### Use Cases

- **Streamlined Workflow:** Upload STEP → DXF automatically queued → Worker processes → DXF available for nesting
- **Sheetmetal Parts:** Parts marked with `needs_dxf=true` in routing get automatic flat pattern generation
- **Bulk Processing:** Engineers can upload multiple STEP files and DXF jobs queue automatically

---

### v3.7.4 (2026-05-23) -- PDF Revision/Iteration Stamping

**Status:** Previous Release

**Summary:** Added automatic revision.iteration stamping to uploaded PDFs, with each file tracking its own iteration count that auto-increments on subsequent uploads.

#### Features Added

**PDF Revision/Iteration Stamping**

PDFs now receive automatic revision and iteration stamps during upload:

- **Revision.Iteration Format:** Stamps appear as "A.15" (revision letter + iteration number)
- **Stamp Location:** Bottom left corner at x=250pt, right next to the existing upload date stamp
- **Auto-Increment:** Each upload of the same filename increments the iteration count (1 → 2 → 3...)
- **Per-File Tracking:** Each file maintains its own revision and iteration in the database
- **All Pages Stamped:** Both stamps (date and revision.iteration) appear on every page of the PDF
- **Example:** First upload shows "A.1", second upload of same file shows "A.2"

**Stamp Details:**
- **Upload Date Stamp:** "Upload - MM/DD/YYYY" at x=82pt, y=8pt (unchanged)
- **Revision Stamp:** "A.1" at x=250pt, y=8pt (NEW)
- **Font:** Helvetica 12pt, black text
- **Position:** Lower left corner, past corner hash marks

**Database Integration:**
- `files` table tracks `revision` (TEXT) and `iteration` (INTEGER) per file
- Iteration determined BEFORE PDF stamping to ensure correct value
- Existing files: iteration = current + 1
- New files: iteration = 1

#### Backend Changes

**Modified Endpoint:** `POST /api/files/upload` in `backend/app/routes/files.py`

- **Iteration Detection:** Queries `files` table for existing file record before stamping
- **Stamp Function:** `stamp_pdf_upload_date(content, revision, iteration)` updated with iteration parameter
- **Stamp Positioning:** Two stamps per page (date at x=82, revision at x=250)
- **File Record Update:** Saves iteration to database after upload

**Key Code Pattern:**
```python
# Check existing iteration BEFORE stamping
existing = supabase.table("files").select("id, iteration").eq("item_id", item_id).eq("file_name", normalized_filename).execute()

if existing.data:
    new_iteration = existing.data[0]["iteration"] + 1
else:
    new_iteration = 1

# Stamp PDF with revision and iteration
if file_type == "PDF":
    content = stamp_pdf_upload_date(content, file_revision, new_iteration)
```

#### Bug Fixes

**Backend Reload Issue on Windows (Pitfall #37)**

- **Issue:** Uvicorn's `--reload` flag on Windows was not reloading changes to `files.py`
- **Root Cause:** File watcher issues on Windows with certain file paths or editors
- **Solution:** Manual restart of backend process after code changes
- **Workaround:** Use `Ctrl+C` and restart `uvicorn app.main:app --reload --port 8001`
- **Note:** This is a known uvicorn/watchfiles limitation on Windows
- **Long-term:** Consider using WSL or Docker for development to avoid Windows file watcher issues

#### Use Cases

- **Drawing Revision Tracking:** Easily see which iteration of a PDF drawing is in the system
- **Upload History:** Stamp shows exact upload date and revision/iteration on every page
- **Version Identification:** Shop floor workers can identify current revision/iteration at a glance
- **Change Management:** Track how many times a drawing has been updated within same revision
- **Audit Trail:** Permanent record of upload date and iteration on PDF itself

#### Files Changed Summary

- `backend/app/routes/files.py` -- Updated `stamp_pdf_upload_date()` function to accept and stamp revision.iteration, modified upload logic to detect iteration before stamping

#### Technical Notes

- Stamping happens AFTER iteration detection to ensure correct value
- Both stamps use same font and style for visual consistency
- Stamp positioning uses absolute coordinates (works for all page sizes)
- If stamping fails, original PDF is uploaded without stamps (fallback behavior)
- Iteration count never resets (continues incrementing across revision changes)
- ReportLab Canvas used to overlay text on existing PDF pages

---

### v3.7.3 (2026-05-23) -- Testing Infrastructure and TypeScript Error Cleanup

**Status:** Previous Release (superseded by v3.7.4)

**Summary:** Added comprehensive testing infrastructure with Vitest (frontend) and pytest (backend), plus CI pipeline. Fixed all 77 build-time TypeScript errors across multiple views.

#### Testing Infrastructure Added

**Frontend Testing (Vitest)**

- **Test Framework:** Added Vitest for Vue 3 component and unit testing
- **Configuration:** New `frontend/vitest.config.ts` with Vue plugin integration
- **Initial Test Suite:** 13 tests for scheduling algorithm in `frontend/src/utils/scheduling.test.ts`
- **Test Coverage:**
  - Dependency graph building (4 tests)
  - Task creation and predecessors (3 tests)
  - Priority scoring (3 tests)
  - Capacity-constrained scheduling (3 tests)
- **Run Command:** `npm test` in frontend directory

**Backend Testing (pytest)**

- **Test Framework:** Added pytest for FastAPI endpoint testing
- **Configuration:** New `backend/pytest.ini` with test discovery settings
- **Initial Test Suite:** 12 tests for items API in `backend/tests/test_items.py`
- **Test Coverage:**
  - List items endpoint (pagination, sorting)
  - Get item by number (success and 404 cases)
  - Create item (valid, invalid, duplicate)
  - Update item (success, 404, validation)
  - Search items by name
  - Filter items by project
- **Fixtures:** Database setup in `backend/tests/conftest.py` with test client
- **Run Command:** `pytest` in backend directory

**CI Pipeline (GitHub Actions)**

- **Configuration:** New `.github/workflows/ci.yml` for automated testing on push/PR
- **Jobs:**
  - Backend tests (Python 3.11, PostgreSQL service, pytest)
  - Frontend tests (Node 20, Vitest)
- **Triggers:** Push to main branch, pull requests
- **Environment:** Uses PostgreSQL 14 service container for backend tests

#### TypeScript Error Cleanup (77 Errors Fixed)

**Core Utilities Fixed:**

- **scheduling.ts** (5 errors) -- Non-null assertions for array access in `calculateSchedule()`
  - `tasks[0]!` for guaranteed non-empty task arrays
  - Safer array access patterns throughout
- **items.ts store** (3 errors) -- Type safety fixes for Pinia store
  - Proper typing for store state updates
  - Fixed undefined checks
- **storage.ts** (2 errors) -- Null safety in storage helper functions
  - Safe navigation for optional chaining

**View Components Fixed:**

- **MrpCostReportView.vue** (8 errors)
  - Array access safety with non-null assertions
  - Color lookup type guards for chart data
  - Proper typing for ECharts options
- **MrpDashboardView.vue** (12 errors)
  - Array access safety for project data
  - Type assertions for component refs
  - `defineExpose` for `openNestModal` method (enables parent component access)
- **MrpPrintLookupView.vue** (4 errors)
  - Safe bucket name parsing from storage paths
  - Type guards for undefined checks
- **MrpProjectTrackingView.vue** (6 errors)
  - Removed unused imports (`onMounted`, `watch`)
  - Safe date parsing with null checks
  - Type safety for schedule data
- **MrpRoutingView.vue** (20 errors)
  - Fixed `API_BASE_URL` import and usage
  - Comprehensive null checks for nested object access
  - Refactored `onClick` handlers to proper TypeScript syntax
  - Type guards for optional properties
  - Safe array access patterns
- **MrpShopView.vue** (17 errors)
  - Regex capture group safety with non-null assertions
  - Bucket parsing type guards
  - Touch event handler typing fixes
  - Safe array operations

**Build Status:**
- **Before:** 77 TypeScript errors, warnings during build
- **After:** Clean build with no TypeScript errors

#### Backend Schema Enhancement

**ItemCreate Pattern Validation Update**

- **File:** `backend/app/schemas.py`
- **Change:** `item_number` pattern now accepts both uppercase and lowercase
- **Before:** `^[a-z]{3}[0-9]{4,6}$` (lowercase only)
- **After:** `^[a-zA-Z]{3}[0-9]{4,6}$` (case-insensitive)
- **Impact:** Allows item creation with mixed-case item numbers (e.g., `CSP0001` and `csp0001`)

#### PowerShell Upload Bridge Fix

**PDM-Upload-Functions.ps1 Improvement**

- **Function:** `Upload-File` in `scripts\pdm-upload\PDM-Upload-Functions.ps1`
- **Issue:** PowerShell errors when API returned null response body
- **Fix:** Added null/empty response handling before JSON parsing
- **Pattern:**
  ```powershell
  if (-not $response -or [string]::IsNullOrWhiteSpace($response)) {
      # Handle null response gracefully
  }
  ```

#### Files Changed Summary

**Testing Infrastructure (NEW):**
- `frontend/vitest.config.ts` -- Vitest configuration with Vue plugin
- `frontend/src/utils/scheduling.test.ts` -- 13 scheduling algorithm tests
- `backend/pytest.ini` -- pytest configuration
- `backend/tests/__init__.py` -- Test package marker
- `backend/tests/conftest.py` -- Test fixtures and database setup
- `backend/tests/test_items.py` -- 12 items API tests
- `.github/workflows/ci.yml` -- GitHub Actions CI pipeline

**TypeScript Fixes:**
- `frontend/src/utils/scheduling.ts` -- Array access safety
- `frontend/src/stores/items.ts` -- Store type fixes
- `frontend/src/services/storage.ts` -- Null safety
- `frontend/src/views/MrpCostReportView.vue` -- Array/color lookup fixes
- `frontend/src/views/MrpDashboardView.vue` -- Type assertions, defineExpose
- `frontend/src/views/MrpPrintLookupView.vue` -- Bucket parsing
- `frontend/src/views/MrpProjectTrackingView.vue` -- Unused imports, date parsing
- `frontend/src/views/MrpRoutingView.vue` -- API_BASE_URL, null checks, onClick handlers
- `frontend/src/views/MrpShopView.vue` -- Regex, bucket parsing, touch events

**Backend/Schema:**
- `backend/app/schemas.py` -- ItemCreate pattern now case-insensitive

**PowerShell:**
- `scripts/pdm-upload/PDM-Upload-Functions.ps1` -- Null response handling

#### Technical Notes

- **Test Isolation:** Backend tests use separate test database with rollback after each test
- **TypeScript Strict Mode:** All fixes maintain strict type safety without using `@ts-ignore`
- **Non-Null Assertions:** Used only where control flow guarantees non-null values
- **CI Performance:** GitHub Actions pipeline runs both test suites in ~3-5 minutes
- **Coverage:** Initial test suites cover critical paths (scheduling, items CRUD)
- **Vitest Speed:** Vitest runs faster than Jest for Vue 3 component testing
- **pytest Fixtures:** Reusable test client and database fixtures in conftest.py

#### Use Cases

- **Automated Testing:** Run `npm test` (frontend) or `pytest` (backend) to verify changes
- **CI/CD Pipeline:** GitHub Actions automatically tests all PRs and commits to main
- **Type Safety:** TypeScript errors caught at build time, preventing runtime issues
- **Regression Prevention:** Test suites prevent breaking existing functionality during refactoring
- **Documentation:** Test files serve as executable examples of API usage

#### Related Documentation

- [TODO.md](../TODO.md) -- Updated to reflect completed testing infrastructure and TypeScript cleanup
- [15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md](15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md) -- TypeScript error patterns documented
- [CONTRIBUTING.md](../CONTRIBUTING.md) -- Testing guidelines (if added in future)

---

### v3.7.2 (2026-05-22) -- DXF Download Enhancements

**Status:** Previous Release (superseded by v3.7.3)

**Summary:** Enhanced DXF bundle download filenames with part info (thickness, quantity), fixed remaining time calculation bug in MRP dashboard, and hidden "Nest DXF" button from slideout UI.

#### Features Added

**DXF Bundle Filename Enhancement**

- **Pattern:** `{item_number}_thk-{thickness}_qty-{quantity}.dxf`
- **Thickness Format:** Thousandths of inch (0.25" → 0250, 0.125" → 0125)
- **Example:** `csp0025_thk-0250_qty-4.dxf` for 0.25" thick part with qty 4
- **Backend:** Modified `/api/mrp/projects/{id}/download-dxf-bundle` endpoint
- **Item Lookup:** Fixed UUID-to-string type mismatch when fetching item info
- **Logging:** Added debug logging for DXF download operations

#### Bug Fixes

**MRP Dashboard "Remaining Time" Calculation**

- **Issue:** Dashboard slideout showed "0h Remaining" for all projects
- **Root Cause:** `remainingMinutes` wasn't being incremented in the `incompleteItems` loop
- **Fix:** Changed from assignment (`remainingMinutes = ...`) to increment (`remainingMinutes += ...`)
- **File:** `frontend/src/views/MrpDashboardView.vue`

#### UI Changes

**MRP Dashboard Slideout**

- **Hidden Button:** "Nest DXF" button removed from slideout UI (functionality preserved in code)
- **Reason:** Nesting typically done from main dashboard, not quick slideout
- **Implementation:** `v-if="false"` on Nest DXF button

#### Files Changed

- `backend/app/routes/mrp.py` -- DXF bundle filename enhancement with thickness/qty
- `frontend/src/views/MrpDashboardView.vue` -- Fixed remaining time calculation, hid Nest DXF button

---

### v3.7.1 (2026-05-22) -- Vite Proxy Timeout Fix

**Status:** Previous Release (superseded by v3.7.2)

**Summary:** Fixed "Unexpected end of JSON" error when generating print packets for large projects.

#### Bug Fixes

**Print Packet Generation Timeout**

- **Issue:** Large projects (20+ parts) caused "Unexpected end of JSON" errors during print packet generation
- **Root Cause:** Vite dev server proxy default timeout (~30-60 seconds) was too short for operations that download multiple PDFs, create overlays, and combine into one packet
- **Fix:** Added `timeout: 300000` (5 minutes) to Vite proxy configuration in `frontend/vite.config.ts`
- **Note:** Only affects development mode; production serves frontend directly from backend (no proxy)
- **Commit:** 03f788e

#### Files Changed

- `frontend/vite.config.ts` -- Added timeout to proxy configuration

#### Documentation

- Added Pitfall #36 to Development Notes explaining the timeout issue and fix
- Added Reminder #35 documenting the Vite proxy timeout pattern

---

### v3.7 (2026-05-12) -- MRP Part Lookup Redesign and PDF Serving Improvements

**Status:** Previous Release (superseded by v3.7.1)

**Summary:** Redesigned MRP Part Lookup view with unified layout, removed Print Lookup page, improved PDF serving via Supabase Storage, and documented mapkey changes for Creo favorites.

#### Features Added

**Unified Part Lookup View**

The MRP Part Lookup view has been completely redesigned to match the Routing Editor layout and serve as the unified view for all part/PDF viewing needs:

- **Sidebar Layout:** Left sidebar with search bar and project filter matches Routing Editor design
- **All Parts Option:** New "All Parts" option in project filter shows all items across all projects (not just project-specific)
- **File Badges:** PDF icons displayed in red (🔴) for visual clarity, Material badges show material type, Operations badges show routing operation count
- **Project Filter:** Dropdown to filter by specific project or view all parts system-wide
- **Removed Print Lookup:** Print Lookup page completely removed (route commented out, all navigation links removed)
- **Shop Terminal Navigation:** MRP Shop view navigation now shows only Shop Terminal and Part Lookup buttons (Print Lookup button removed)

**PDF Serving via Supabase Storage**

PDFs are now served directly from Supabase Storage buckets using storage helper functions:

- **Storage Buckets:** Files stored in three buckets: `pdm-drawings` (PDFs), `pdm-cad` (PRT/ASM), `pdm-exports` (STEP/DXF/SVG)
- **Storage Helper Functions:** New `frontend/src/services/storage.ts` provides helper functions for URL generation
- **Key Function:** `getSignedUrlFromPath()` parses storage paths and creates signed URLs (1-hour expiry)
- **File Path Format:** Stored in `files` table as `pdm-drawings/csp00025/A/1/csp00025.pdf` (no separate `storage_path` column)
- **Bug Fix:** Fixed queries that tried to select non-existent `storage_path` column (use `file_path` column directly)

**Mapkey Changes for Creo Integration**

Documented changes to Creo mapkeys replacing FAV_ favorite references with hard-coded paths:

- **FAV_ Favorites Removed:** All FAV_9_, FAV_10_, FAV_14_ favorite button references replaced with computer_pb navigation
- **Hard-Coded Paths:** Uses `computer_pb` button + double-action Select/Activate for folder navigation
- **Two Destination Paths:**
  - `C:\PTC_Data\formats` (for drawing format files)
  - `C:\PDM-Upload` (for file exports to PDM system)
- **12 Mapkeys Modified:** All export and format selection mapkeys updated
- **Documentation:** Created `MAPKEY_CHANGES.md` at project root with full details

#### Database/Storage Architecture

**Files Table Structure:**
- `id` (UUID) - Primary key
- `item_id` (UUID) - Links to items table
- `file_type` (TEXT) - PDF, STEP, DXF, SVG, CAD, etc.
- `file_name` (TEXT) - Original filename
- `file_path` (TEXT) - Full storage path including bucket (e.g., `pdm-drawings/csp00025/A/1/csp00025.pdf`)
- `file_size` (INTEGER) - Size in bytes
- `revision` (TEXT) - File revision letter
- `iteration` (INTEGER) - File iteration number

**Storage Buckets:**
- `pdm-drawings` - PDF files
- `pdm-cad` - Creo CAD files (PRT, ASM)
- `pdm-exports` - Exported files (STEP, DXF, SVG)
- `pdm-other` - Other file types

**Storage Helper Functions (`frontend/src/services/storage.ts`):**
- `parseStoragePath()` - Parses full path to extract bucket and path
- `getSignedUrl()` - Creates signed URL for bucket/path (1 hour expiry)
- `getSignedUrlFromPath()` - Creates signed URL from full storage path
- `getBucketForFile()` - Maps file extension to bucket
- `buildStoragePath()` - Builds storage path from item/revision/iteration
- `uploadFile()` - Uploads file to appropriate bucket
- `downloadFile()` - Downloads file as blob
- `createFileRecord()` - Creates/updates files table record

#### Frontend Changes

**Modified View:** `frontend/src/views/MrpPartLookupView.vue` (~500 lines redesigned)

- **Layout:** Switched from top search bar to sidebar layout matching Routing Editor
- **Sidebar Components:**
  - Search input with icon
  - Project filter dropdown (All Parts + project-specific options)
  - Parts list with scrollable table
  - File badges (PDF red icon, Material badge, Operations badge)
- **Main Panel:**
  - PDF viewer using signed URLs from Supabase Storage
  - Part details tab with material/operations info
- **Data Loading:**
  - Loads all files and builds availability sets for badge display
  - Uses `getSignedUrlFromPath()` to generate PDF URLs
  - Queries files table using `file_path` column (not `storage_path`)

**Removed View:** `frontend/src/views/MrpPrintLookupView.vue` (DELETED)

- Print Lookup page no longer needed
- Part Lookup view serves all PDF viewing needs

**Modified View:** `frontend/src/views/MrpShopView.vue` (~20 lines modified)

- Removed "Print Lookup" navigation button
- Navigation now shows only "Shop Terminal" and "Part Lookup"

**Modified Router:** `frontend/src/router/index.ts`

- Print Lookup route commented out (lines 97-102)
- Route definition preserved in comments for reference

#### Files Changed Summary

- `frontend/src/views/MrpPartLookupView.vue` -- Complete redesign with sidebar layout, all parts filter, PDF serving
- `frontend/src/views/MrpPrintLookupView.vue` -- DELETED
- `frontend/src/views/MrpShopView.vue` -- Removed Print Lookup navigation button
- `frontend/src/router/index.ts` -- Commented out Print Lookup route
- `frontend/src/services/storage.ts` -- Storage helper functions for PDF serving
- `MAPKEY_CHANGES.md` -- NEW, documents Creo mapkey changes

#### Use Cases

**Part Lookup View:**
- **Shop Floor PDF Access:** Workers can quickly find and view PDFs for any part across all projects
- **Project-Specific View:** Filter to see only parts in a specific project
- **Material Identification:** Material badges show material type at a glance
- **Routing Status:** Operations badges show if routing is defined
- **All Parts View:** "All Parts" option enables cross-project part search

**PDF Serving:**
- **Secure Access:** Signed URLs expire after 1 hour, preventing unauthorized long-term access
- **No Backend Proxy:** PDFs served directly from Supabase Storage, reducing backend load
- **Browser Caching:** Signed URLs enable browser caching for better performance
- **Multiple Buckets:** Files organized by type for easier management and access control

**Mapkey Changes:**
- **Portable Configuration:** Mapkeys no longer depend on Creo favorites being set up correctly
- **Consistent Paths:** All users navigate to same hard-coded paths
- **No Setup Required:** New users don't need to configure favorites

#### Technical Notes

- **Storage Path Format:** Full path includes bucket prefix (e.g., `pdm-drawings/...`) stored in single `file_path` column
- **No `storage_path` Column:** Database does not have separate `storage_path` column; use `file_path` for all queries
- **Signed URL Expiry:** URLs valid for 1 hour (3600 seconds) by default, configurable in `getSignedUrl()` calls
- **File Type Mapping:** `storage.ts` maps file extensions to buckets and database file types
- **Print Lookup Removal:** Route and view files preserved in comments/history for reference, not deleted from git
- **Mapkey Double-Action:** Creo mapkeys require both Select and Activate commands to navigate into folders

#### Related Documentation

- [MAPKEY_CHANGES.md](../MAPKEY_CHANGES.md) -- Creo mapkey changes reference
- [03-DATABASE-SCHEMA.md](03-DATABASE-SCHEMA.md) -- Updated files table schema
- [04-SERVICES-REFERENCE.md](04-SERVICES-REFERENCE.md) -- Storage service reference
- [20-COMMON-WORKFLOWS.md](20-COMMON-WORKFLOWS.md) -- Updated MRP workflows

---

## Previous Versions

### v3.6 (2026-05-01) -- Station Grouping and Cost Report Enhancements

**Status:** Previous Release (superseded by v3.7)

**Summary:** Enhanced MRP cost reporting with station grouping and nested pie chart visualization, plus refined PDF upload date stamping for better drawing readability.

#### Features Added

**Station Grouping for Cost Reports**

The MRP Cost Report now groups workstations into logical categories for better cost analysis and visualization:

- **Database:** Added `station_group` column to `workstations` table
- **Groups Defined:**
  - **Weld:** Stations 014-017 (Weld Jigging, Tack Welding, Final Welding, Weld Finishing)
  - **Assembly:** Stations 020, 025, 035, 045 (Mechanical Assembly, Electrical Assembly, Sub-Assembly, Final Assembly)
  - **Fabrication:** Stations 005, 010 (Saw, Press Brake)
  - **QC:** Station 050 (Inspection)
  - **Outsourced:** Stations 060-080 (Powder Coating, Anodizing, Plating, Heat Treating, Waterjet External)
- **Backend:** New `operations_summary_grouped` and `cost_breakdown_chart_grouped` data structures in `/api/mrp/projects/{id}/cost-report`
- **Use Case:** Quickly identify which cost categories (Weld vs Assembly vs Fabrication) dominate project costs without drilling into individual stations

**ECharts Nested Pie Chart Visualization**

Replaced Chart.js pie chart with ECharts nested pie chart for richer cost visualization:

- **Inner Ring:** Individual workstations color-coded by group (lighter shades)
- **Outer Ring:** Station groups (Weld, Assembly, Fabrication, QC, Outsourced) with bold colors
- **Interactive Legend Toggle:** Switch between "Show Groups" (outer ring only) and "Show Stations" (all stations)
- **Chart Size:** Increased by 50% for better readability
- **Color Palette:**
  - Weld: Red (#ef4444)
  - Assembly: Purple (#8b5cf6)
  - Fabrication: Blue (#3b82f6)
  - QC: Green (#10b981)
  - Outsourced: Orange (#f97316)
  - Raw Material: Amber (#f59e0b)
  - Purchased Parts: Purple (#a855f7)
- **Dependencies:** Added `echarts` and `vue-echarts` to frontend

**Grouped Operations Table**

Cost report operations table now has grouped view with expandable station details:

- **Default View:** Groups (e.g., "Weld") with group-level totals
- **Expandable:** Click group to see individual stations (e.g., "014 - Weld Jigging", "015 - Tack Welding")
- **Color Badges:** Group names displayed with matching chart colors
- **Toggle:** Switch between grouped and flat view using "Group By Station" checkbox

**PDF Upload Date Stamping (Refinement)**

Improved PDF date stamp positioning to avoid title block conflicts:

- **Previous Issue:** Stamp overlapped title blocks in lower-right corner, obscuring revision letters and signatures
- **New Position:** Lower-left corner at x=82pt, y=8pt (~1.1" from left edge, just past corner hash marks)
- **Font Size:** Increased from 8pt to 12pt for better visibility
- **Format:** "Upload - MM/DD/YYYY" in Helvetica, black text, no background box
- **Location:** `backend/app/routes/files.py` in `stamp_pdf_upload_date()` function
- **Files Changed:** `backend/app/routes/files.py`

#### Database Changes

**Migration: Add station_group to workstations**

```sql
ALTER TABLE workstations ADD COLUMN station_group TEXT;

-- Update existing stations with groups
UPDATE workstations SET station_group = 'Fabrication' WHERE station_code IN ('005', '010');
UPDATE workstations SET station_group = 'Weld' WHERE station_code IN ('014', '015', '016', '017');
UPDATE workstations SET station_group = 'Assembly' WHERE station_code IN ('020', '025', '035', '045');
UPDATE workstations SET station_group = 'QC' WHERE station_code = '050';
UPDATE workstations SET station_group = 'Outsourced' WHERE station_code IN ('060', '065', '070', '075', '080');
```

**Schema Change:**

| Table | Column | Type | Description |
|-------|--------|------|-------------|
| `workstations` | `station_group` | TEXT | Logical grouping: Weld, Assembly, Fabrication, QC, Outsourced, Other |

#### Backend Changes

**Modified Endpoint:** `GET /api/mrp/projects/{project_id}/cost-report`

- **Added Fields to Response:**
  - `operations_summary_grouped`: Array of group-level summaries with nested stations
  - `cost_breakdown_chart_grouped`: Chart data with group-level aggregation
- **Query Enhancement:** Fetch `station_group` from `workstations` table
- **Grouping Logic:** Aggregate operations by `station_group`, sum time and cost, collect stations per group
- **Chart Data:** Prepare both individual station slices (with `station_group` tag) and grouped slices (with nested `stations`)
- **File:** `backend/app/routes/mrp.py` (~100 lines modified)

**New Data Structures:**

```python
# Per-group summary
{
  "group_name": "Weld",
  "total_time_min": 245.5,
  "total_cost": 4910.0,
  "station_count": 4,
  "stations": [
    {
      "station_code": "014",
      "station_name": "Weld Jigging",
      "is_outsourced": false,
      "total_time_min": 60.0,
      "total_cost": 1200.0
    },
    ...
  ]
}

# Grouped chart slice
{
  "label": "Weld",
  "value": 4910.0,
  "category": "labor",
  "stations": [...]  # Same as above
}
```

#### Frontend Changes

**Modified View:** `frontend/src/views/MrpCostReportView.vue` (~300 lines modified)

- **Replaced Chart.js with ECharts:** Swapped `vue-chartjs` for `vue-echarts` with nested pie chart
- **New Interfaces:**
  - `OperationSummaryGrouped`: Group-level operation data with nested stations
  - `GroupStation`: Individual station within a group
  - `ChartSliceGrouped`: Chart data with nested station details
- **Chart Configuration:**
  - Inner ring (radius 0-55%): Individual stations with group-based colors
  - Outer ring (radius 60-80%): Station groups
  - Tooltip: Shows station/group name, cost, percentage
  - Legend: Toggle between groups (default) and all stations
- **Operations Table:**
  - Grouped view with expandable rows
  - Group badge with matching chart color
  - Station detail rows hidden by default, expand on click
  - Toggle to switch to flat view (all stations listed)
- **Color System:**
  - `groupColors`: Bold colors for outer ring (Weld red, Assembly purple, etc.)
  - `stationColors`: Lighter shades for inner ring (4 shades per group)
  - Color assignment: Stations inherit group color with index-based shade selection
- **Legend Toggle:** Button switches between `showDetailedLegend` (stations) and group-only view

**Dependencies Added:**

```json
{
  "echarts": "^6.0.0",
  "vue-echarts": "^8.0.1"
}
```

#### Files Changed Summary

- `backend/app/routes/mrp.py` -- Station grouping logic, grouped summaries, chart data
- `frontend/src/views/MrpCostReportView.vue` -- ECharts nested pie, grouped table, legend toggle
- `frontend/package.json` -- Added echarts and vue-echarts
- `backend/app/routes/files.py` -- PDF stamp position refinement (already in v3.5.1)
- Database migration (manual via Supabase SQL Editor) -- Add station_group column

#### Use Cases

- **Cost Category Analysis:** Quickly see if Weld, Assembly, or Fabrication dominates project costs
- **Drill-Down Detail:** Click groups to expand and see individual station costs
- **Visual Cost Distribution:** Nested pie chart shows both high-level (groups) and detailed (stations) at once
- **Legend Clarity:** Toggle legend between groups (fewer items, cleaner) and all stations (detailed)
- **Comparison:** Compare multiple projects by group-level costs without station noise
- **PDF Readability:** Upload stamps no longer obscure title block signatures and revision letters

#### Technical Notes

- **Station Group Assignment:** Groups assigned manually in migration, not auto-detected
- **Ungrouped Stations:** Stations without `station_group` default to "Other"
- **Chart Color Mapping:** Station colors use index modulo to cycle through 4 shades per group
- **ECharts Performance:** Nested pie renders faster than Chart.js for large datasets (>50 slices)
- **Legend Toggle:** Only affects visible legend items, chart data remains unchanged
- **PDF Stamping:** Uses ReportLab Canvas to overlay text on existing PDF pages

#### Related Documentation

- [03-DATABASE-SCHEMA.md](03-DATABASE-SCHEMA.md) -- Updated workstations table schema
- [04-SERVICES-REFERENCE.md](04-SERVICES-REFERENCE.md) -- Updated cost-report endpoint
- [02-PDM-COMPLETE-OVERVIEW.md](02-PDM-COMPLETE-OVERVIEW.md) -- MRP cost reporting overview
- [20-COMMON-WORKFLOWS.md](20-COMMON-WORKFLOWS.md) -- Cost report usage workflow

---

## Previous Versions

### v3.5.1 (2026-04-30) -- Routing Editor Enhancements and PDF Upload Improvements

**Status:** Previous Release (superseded by v3.6)

**Summary:** Enhanced MRP routing editor with automatic waterjet time calculation, new Purchased routing template, improved UI state management, and refined PDF upload date stamping.

#### Features Added

**Automatic Waterjet Time Calculation in Routing Editor**

The routing editor now automatically calculates waterjet cutting time when selecting the Waterjet station or applying routing templates:

- **Auto-calculation trigger:** When "012 - Waterjet" is selected in the station dropdown
- **Data source:** Uses `cut_length` from item data (populated from Creo `CUT_LENGTH` parameter)
- **Formula:** `speed = ref_speed × (0.25/thickness)^exponent × machinability` from `cutting_parameters` table
- **Cut time:** `(cut_length / speed) + handling_time` in minutes
- **Material mapping:** STEEL/STEEL_HSLA → CS, ALUMINUM/AL → AL, STAINLESS/304SS → SS
- **Template integration:** Auto-fills time when applying "Formed SM" or "Flat SM" templates
- **Manual override:** User can edit the calculated time if needed

This eliminates manual time estimation for waterjet operations and ensures consistency with material-specific cutting speeds.

**New Purchased Routing Template**

Added a "Purchased" routing template for supplier parts:
- **005 - Receiving:** 10 minutes
- **020 - Staging:** 5 minutes
- **050 - Inspection:** 5 minutes

Use this template for `mmc` and `spn` prefixed items that don't require manufacturing but need receiving/inspection tracking.

**Price Badge on Item List**

Items with assigned `unit_price` now show a green "$" badge in the routing editor item list, making it easy to identify purchased parts with pricing data at a glance.

#### Bug Fixes

**Purchase Info Save Hanging After Tab Switch**

- **Issue:** Editing purchased part info (supplier name, part number, unit price) and then switching to a different browser tab would cause the save operation to hang indefinitely with a spinning loader.
- **Fix:** Added `AbortError` handling with automatic retry logic. When a tab switch aborts the save request, the system waits 100ms and retries the save operation.
- **Files Changed:** `frontend/src/views/MrpRoutingView.vue`

**Routing State Reset on Item Change**

- **Issue:** When selecting a new item in the routing editor, stale data from the previously selected item would sometimes appear (old operations, materials, purchase info).
- **Fix:** Added explicit state reset with `watch()` on `selectedItem` to clear all reactive state and fetch fresh data when switching items.
- **Files Changed:** `frontend/src/views/MrpRoutingView.vue`

**PDF Upload Date Stamp Position**

- **Issue:** PDF upload date stamps were overlapping with drawing title blocks in the lower-right corner, obscuring revision letters, engineer names, and approval signatures.
- **Fix:**
  - Moved stamp from lower-right to lower-left corner (x=82pt, ~1.1" from left edge, past corner marks)
  - Increased font size from 8pt to 12pt for better visibility
  - Removed white background box for cleaner appearance
  - New position: lower-left, just above bottom edge (y=8pt)
- **Files Changed:** `backend/app/routes/files.py`

#### Files Changed Summary

- `frontend/src/views/MrpRoutingView.vue` - Waterjet auto-calc, Purchased template, state reset, AbortError retry, price badge
- `backend/app/routes/files.py` - PDF stamp repositioning and font size increase

#### Related Documentation

- [15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md](15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md) - Pitfalls #19-20, Important Reminders #22-27
- [20-COMMON-WORKFLOWS.md](20-COMMON-WORKFLOWS.md) - MRP Routing Editor section updated
- [waterjet-cutting-speeds.md](waterjet-cutting-speeds.md) - Waterjet speed reference

---

### v3.5 (2026-02-07) -- Waterjet Cut Time Calculation and Shop Floor Enhancements

**Status:** Previous Release

#### New Features

- **MRP-Based Waterjet Cut Time Calculation** -- Automatic cut time estimation using physics-based power-law formula:
  - New `cutting_parameters` table with material-specific reference speeds, machinability indices, and thickness exponents
  - Formula: `speed = ref_speed × (0.25/thickness)^exponent × machinability`
  - Auto-calculates `cut_time` on BOM upload (replaces Creo estimates which lack machinability data)
  - Material mapping: `STEEL/STEEL_HSLA → CS`, `AL/ALUMINUM → AL`, `SS/STAINLESS → SS`
  - Default parameters (Q3 quality, 60,000 PSI, 0.014" nozzle):
    - Carbon Steel (CS): 12 IPM @ 0.25", machinability 1.0, exponent 0.55
    - Aluminum (AL): 35 IPM @ 0.25", machinability 2.9, exponent 0.55
    - Stainless Steel (SS): 10.8 IPM @ 0.25", machinability 0.9, exponent 0.55
  - Handling time added from `cost_settings.handling_time_min` (default 0.5 min)
- **Batch Recalculate Cut Times** -- New endpoint `POST /api/items/recalculate-cut-times` to recalculate all existing items:
  - Filters for sheet metal parts with valid material, thickness, and cut_length
  - Updates `routing_operations.est_time_min` for waterjet operations
  - Returns count of updated items
- **Cost Settings UI for Cutting Parameters** -- New section in MRP Cost Settings view:
  - View/edit reference speeds, machinability indices, and exponents for CS/AL/SS
  - Live preview calculation at 0.25" thickness
  - Save changes with optimistic UI updates
- **File Upload Normalization** -- Upload endpoint now normalizes all filenames before storage:
  - Removes redundant suffixes: `xxp123_dxf.dxf → xxp123.dxf`, `abc0001_prt.prt → abc0001.prt`
  - Converts file extensions: `.stp → .step` (canonical extension)
  - Strips type suffixes from filenames: `_prt`, `_asm`, `_drw` (legacy Creo naming)
  - Lowercases all filenames for consistency
  - PDM-Upload script also strips suffixes from item numbers extracted from filenames
- **MRP Shop View Material Filter** -- New material/thickness filter for shop floor queue:
  - Dropdown shows all unique material sizes in project (e.g., `0.25" STEEL`, `0.125" 304SS`)
  - Counts displayed for each filter option and "All Sizes"
  - Filters queue table to show only matching material sizes
  - "Select All" checkbox works on filtered items only (not entire queue)
  - Filter resets when switching projects or stations
  - Supports both sheet metal (thickness + material) and tube (size × material from name)

#### Database Changes

- **New Table:** `cutting_parameters` -- Stores material-specific cutting parameters:
  - Columns: `id`, `material_code` (CS/AL/SS), `material_name`, `ref_speed_ipm` (speed at 0.25"), `machinability` (relative to steel), `exponent` (thickness scaling), `created_at`, `updated_at`
  - Seeded with defaults for CS (1.0), AL (2.9), SS (0.9) machinability
- **Migration:** `create_cutting_parameters_table` -- Creates table and inserts default values

#### Backend Changes

- **New Service:** `backend/app/services/cutting.py` (~127 lines) -- Cutting time calculation logic:
  - `calculate_cutting_speed()`: Power-law formula for speed in IPM
  - `calculate_cut_time()`: Cut time = (length / speed) + handling_time
  - `map_material_to_code()`: Maps item material strings to cutting parameter codes
- **Modified Endpoint:** `POST /api/bom/upload` -- Integrated cut time calculation:
  - Calls `calculate_cut_time()` for each part with valid material/thickness/cut_length
  - Updates `est_time_min` in routing_operations if cut_time > 0
  - Logs calculated cut times for debugging
- **New Endpoint:** `POST /api/items/recalculate-cut-times` -- Batch recalculate existing items:
  - Query items with material, thickness, and cut_length
  - Recalculate cut times using current cutting parameters
  - Update routing_operations for waterjet station
  - Return count of updated items
- **Modified Endpoint:** `POST /api/files/upload` -- Added filename normalization:
  - Strip `_dxf`, `_prt`, `_asm`, `_drw` suffixes
  - Convert `.stp → .step`
  - Lowercase all filenames
  - Preserve original extension

#### Frontend Changes

- **Modified View:** `frontend/src/views/MrpCostSettingsView.vue` (~200 lines added) -- New "Cutting Parameters" section:
  - Table showing CS/AL/SS parameters with editable inputs
  - Real-time preview of cutting speed at 0.25" thickness
  - Save button with loading state and optimistic updates
  - Fetches from `/api/cutting-parameters`, updates via PUT
- **Modified View:** `frontend/src/views/MrpShopView.vue` (~150 lines modified) -- Material filter:
  - Added `material`, `thickness`, `material_size` fields to `QueueItem` interface
  - Fetch material/thickness from items table in queue query
  - Build `material_size` display string (handles sheet metal and tube formats)
  - Computed `availableMaterialSizes` with numeric thickness sorting
  - Computed `filteredQueueItems` filtered by selected material size
  - Material filter dropdown in queue header with counts
  - New "Material" column in parts table
  - Modified "Select All" to work on filtered items only

#### PowerShell Changes

- **Modified Script:** `scripts/pdm-upload/PDM-Upload-Functions.ps1` -- Item number extraction:
  - Added suffix stripping: `_prt`, `_asm`, `_drw` removed before item number detection
  - Example: `abc0001_prt.prt → abc0001` (not `abc0001_prt`)
  - Ensures item numbers match database records after upload normalization

#### Documentation

- **New Reference Doc:** `Documentation/waterjet-cutting-speeds.md` -- Comprehensive cutting speed reference:
  - Machinability index table (mild steel 1.0, stainless 0.9, aluminum 2.9, rubber 15-25+)
  - Cutting speed tables for 8 thickness values across 6 materials
  - Quality vs speed multipliers (Q1-Q5)
  - Equipment variables (nozzle size, pressure, abrasive flow, pump type)
  - Material variables (hardness, thickness, brittleness)
  - Pure waterjet vs abrasive waterjet comparison
  - Rubber cutting notes (pure waterjet preferred, stackable, lower pressure)
  - Links to online calculators (Hypertherm, KMT, OMAX IntelliMAX)
  - Sources with citations

#### Use Cases

- **Accurate Time Estimates:** Physics-based cut time calculation replaces Creo's generic estimates (which lack material/thickness awareness)
- **Material Grouping:** Shop workers can filter queue by material size to batch similar cuts (reduces setup time)
- **Batch Updates:** After tweaking cutting parameters, recalculate all existing items with one API call
- **Filename Consistency:** All uploaded files follow consistent naming (lowercase, no redundant suffixes, canonical extensions)
- **Waterjet Optimization:** Adjust machinability indices and exponents per material as shop floor data is collected

#### Technical Notes

- Cut time formula uses inches throughout (Creo exports thickness and cut_length in inches)
- Handling time added to account for setup, loading, unloading (default 0.5 min)
- Material code mapping is case-insensitive and checks for prefixes/substrings
- Filename normalization happens before storage (all database paths already normalized)
- Material filter sorts by thickness numerically, then by material name alphabetically
- Cutting parameters stored separately from cost_settings to allow future expansion (e.g., per-alloy tube pricing)

---

## Previous Versions

### v3.4 (2026-02-05) -- Project Scheduling and Capacity Planning

**Status:** Previous (superseded by v3.5)

#### New Features

- **Capacity-Constrained Project Scheduling** -- MRP Project Tracking view now calculates realistic shop floor schedules with:
  - BOM-based dependency analysis (assemblies wait for all child parts)
  - Per-station capacity limits (waterjet 12 hrs/day, press brake/saw 8 hrs/day, weld/assembly 3 parallel stations)
  - Priority scoring (leaf parts before assemblies, smaller assemblies first, thickness grouping)
  - Task splitting across days when capacity exceeded
  - Real-time schedule recalculation when operations marked complete
- **Live Completion Tracking** -- Project Tracking view subscribes to `part_completion` table changes via Supabase Realtime:
  - Automatic schedule refresh when shop workers mark operations complete
  - Gantt bars update to reflect new start dates for dependent tasks
  - Accurate "days remaining" calculation based on current status
- **Enhanced Gantt Visualization** -- Gantt bars now positioned using scheduled start/end days instead of simple time estimates:
  - In-progress bars show completion percentage as gradient (green → blue)
  - Bar hover shows quantity × total minutes for each part
  - Weekend highlighting for visual reference

#### Architecture

- **New Module:** `frontend/src/utils/scheduling.ts` (~565 lines) -- Complete scheduling algorithm with four phases:
  1. **Build Dependency Graph:** Analyze BOM structure, identify assemblies, calculate BOM depth, map all descendants
  2. **Create Scheduled Tasks:** Convert routing operations to tasks with predecessor relationships (sequential + assembly dependencies)
  3. **Priority Scoring:** Score tasks based on completion status, BOM depth, assembly size, routing sequence, and thickness
  4. **Capacity-Constrained Scheduling:** Allocate tasks to days respecting station capacity, split large tasks across days, track utilization per station per day
- **Station Capacity Configuration:** Hardcoded in `STATION_CAPACITIES` constant (lines 108-119) with per-station daily minutes and parallel capacity
- **Interfaces:** `ScheduledTask`, `PartSchedule`, `StationDaySlot`, `ScheduleResult` for type-safe scheduling data

#### Frontend Changes

- **Modified View:** `frontend/src/views/MrpProjectTrackingView.vue` -- Integrated scheduling into project load:
  - Store raw parts/BOM/routing data for re-scheduling
  - Call `calculateSchedule()` on project load with completion data
  - Subscribe to `part_completion` changes via Supabase Realtime channel
  - Trigger `refreshSchedule()` on completion events
  - Update Gantt bar positioning to use scheduled start/end days
  - Show "Scheduled Days" in project info display
- **Station Capacity Limits:** Configurable per-station (waterjet, press brake, saw, weld jigging, mech assembly) with fallback to shared worker pool (24 hrs/day, 3 workers) for low-volume stations

#### Documentation

- **New Section:** `Documentation/20-COMMON-WORKFLOWS.md` -- Section 15: "Project Scheduling and Capacity Planning" (~210 lines) with:
  - Algorithm overview (four phases explained in detail)
  - Station capacity configuration table and modification guide
  - Real-time updates technical implementation
  - UI usage guide (project info, Gantt bars, progress bar)
  - Limitations and future improvements
  - Troubleshooting table

#### Use Cases

- **Project Timeline Estimation:** Calculate realistic completion dates based on shop floor capacity constraints
- **Workload Planning:** Visualize per-station utilization to identify bottlenecks
- **Progress Tracking:** See live updates as shop workers complete operations
- **Dependency Management:** Ensure assemblies don't start until all child parts are ready
- **Resource Allocation:** Understand how many parallel stations or shifts are needed to meet deadlines

#### Technical Notes

- Schedule recalculates entirely on each update (no incremental patching) to ensure correctness
- Circular BOM references are protected via parent chain tracking in descendant recursion
- Tasks can split across multiple days if operation time exceeds daily capacity
- Completed tasks receive highest priority (+10,000 points) to lock their positions early
- Weekend days are included in day count but not excluded from capacity allocation (limitation to address in future)

---

## Previous Versions

### v3.3 (2026-02-03) -- Project Cost Report and FreeCAD Script Improvements

**Status:** Previous (superseded by v3.4)

#### New Features

- **Project Cost Report** (`/mrp/cost-report`) -- Comprehensive project cost breakdown view with:
  - Project info bar (code, customer, description, total cost)
  - Interactive pie chart (chart.js) showing cost distribution by labor workstation, raw materials, purchased parts, and outsourced operations
  - Summary cards for labor, materials, outsourced, purchased, overhead multiplier, and total
  - Manufactured items table with expandable operations detail
  - Operations summary table (per-workstation totals across all items)
  - Purchased parts table with supplier info and pricing
  - Print support with `@media print` CSS for browser-based printing
  - Accessible from MRP Dashboard via "Cost Report" button (pink dot badge)
- **DXF Flattening Simplification** -- Updated `flatten_sheetmetal.py` to use FreeCAD's built-in `unfold()` method instead of manual bend manipulation, improving robustness and maintainability.
- **SVG Bend Drawing Improvements** -- Enhanced `bend_drawing.py` with better dimension placement, clearer bend line annotations, and improved layout.

#### Backend Changes

- **Migration:** None (uses existing database schema)
- **New Endpoint:** `GET /api/mrp/projects/{project_id}/cost-report` (~255 lines) -- Aggregates cost data from items, routing operations, purchased parts, and MRP cost settings. Returns comprehensive cost breakdown with labor grouped by workstation, material costs by alloy, outsourced operations aggregated, and purchased parts list.

#### Frontend Changes

- **New View:** `frontend/src/views/MrpCostReportView.vue` -- Full-page cost report with chart.js pie chart, summary cards, three data tables (manufactured items, operations summary, purchased parts), and print support.
- **Router:** Added `/mrp/cost-report` route to `frontend/src/router/index.ts`.
- **Navigation:** Added "Cost Report" button with pink dot badge to MRP Dashboard (`MrpDashboardView.vue`). Button passes selected project as query parameter.
- **Dependencies:** Added `chart.js` and `vue-chartjs` to `frontend/package.json`.

#### Files Changed

- `backend/app/routes/mrp.py` -- Added cost-report endpoint with labor, material, outsourced, and purchased parts aggregation
- `frontend/src/views/MrpCostReportView.vue` (NEW) -- Full-page cost report view
- `frontend/src/router/index.ts` -- Added cost-report route
- `frontend/src/views/MrpDashboardView.vue` -- Added Cost Report nav button
- `frontend/package.json` -- Added chart.js and vue-chartjs
- `FreeCAD/Tools/Flatten_sheetmetal_portable.py` -- Simplified to use built-in unfold()
- `FreeCAD/Tools/Create_bend_drawing_portable.py` -- Improved dimension placement

#### Use Cases

- **Project Estimating:** Review total project cost broken down by labor, materials, outsourced operations, and purchased components.
- **Cost Analysis:** Identify which operations or workstations contribute most to project cost via visual pie chart.
- **Quote Preparation:** Print cost report for customer quotes or internal reviews.
- **Budget Tracking:** Compare estimated costs against actual labor/material expenditures (when integrated with time tracking).

---

## Previous Versions

### v3.2 (2026-01-31) -- Per-Material Pricing and Purchased Parts Enhancement

**Status:** Previous (superseded by v3.3)

#### New Features

- **Per-Material Pricing Defaults** -- Replaced generic material pricing ($0.85/lb SM, $8.00/ft tube) with per-alloy defaults: `default_cs_price_per_lb` ($0.85), `default_al_price_per_lb` ($3.00), `default_ss_price_per_lb` ($3.50). Tube $/ft is now derived at runtime as `$/lb × weight_lb_per_ft`.
- **Material Auto-Prefill** -- When selecting a part with no routing materials assigned, the system auto-maps `item.material` (STEEL, 304SS, ALUMINUM) to `material_code` (CS/AL/SS) and finds closest matching thickness within 15% tolerance.
- **Auto-Calculate Blank Mass** -- Auto-trigger blank mass calculation when both width and height dimensions are filled in the routing editor.
- **Material Assignment Badge** -- Added `[Mat]` badge with golden border (`#b8860b`) in part list when material is assigned to routing.
- **Purchased Part Info Section** -- Added "Purchased Part Information" section to routing editor showing supplier name, part number, and unit price for `mmc`/`spn` prefixed items.
- **McMaster Auto-Fill** -- Automatically populate supplier name ("McMaster-Carr") and add product page link when `mmc` prefix detected. For other supplier parts (`spn`), supplier info is editable.

#### Database Changes

- **Migration `replace_material_price_defaults_per_alloy`** -- Replaced `default_sm_price_per_lb` ($0.85) and `default_tube_price_per_ft` ($8.00) with three per-alloy keys: `default_cs_price_per_lb`, `default_al_price_per_lb`, `default_ss_price_per_lb`.
- **Migration `clear_sm_price_per_unit_use_defaults`** -- Cleared all `raw_materials.price_per_unit` for SM materials to ensure they use the new per-alloy defaults.

#### UI/UX Improvements

- Golden border on assigned material rows in routing editor for visibility.
- Sheet metal materials now show "default" placeholder with effective price (matching tube style).
- Purchased part section appears contextually based on item number prefix.
- McMaster parts get automatic product page link with external icon.

#### Files Changed

- `frontend/src/views/MrpRoutingView.vue` -- Major updates: per-alloy pricing, auto-prefill, auto-calculate, Mat badge, purchased part section.
- `frontend/src/views/MrpCostSettingsView.vue` -- Updated for per-alloy pricing display.
- `frontend/src/views/MrpDashboardView.vue` -- Updated to show material assignment badge in part list.
- `backend/app/routes/mrp.py` -- Updated cost-estimate endpoint for per-alloy defaults.
- `.claude/agents/pricing.md` -- New specialized pricing agent with cost estimation expertise.
- `CLAUDE.md` -- Added pricing agent to agent table.

---

## Previous Versions

### v3.1 (2026-01-30) -- Workspace Comparison and Local Service

**Status:** Previous (superseded by v3.2)

#### New Features

- **Workspace Comparison API** (`POST /api/workspace/compare`) -- New FastAPI endpoint that compares local Creo workspace files against the Supabase vault, returning status (Current, Out of Date, Not In Vault) with timestamps.
- **PDM-Local-Service** (`Local_Creo_Files/Powershell/PDM-Local-Service.ps1`) -- New PowerShell HTTP server on `localhost:8083` with endpoints for file timestamps, check-in (upload), download, and health check. Bridges Creo's embedded browser with local file operations.
- **Auto-create items on upload** -- The `POST /api/files/upload` endpoint now automatically creates items when they don't exist, if the `item_number` matches recognized naming conventions (standard, mmc, spn, zzz).
- **workspace.html modernized** -- All legacy endpoint references (DATASERVER:8082, localhost:8083 old service, dataserver:3000) replaced with new `PDM_CONFIG` object pointing to FastAPI backend (port 8001) and local service (port 8083).

#### Database Changes

- **Migration `add_updated_at_to_files`** -- Added `updated_at` column to `files` table with default `now()`, backfill from `created_at`, and auto-update trigger (`files_updated_at_trigger`).

#### Bug Fixes

- **Wrong port (404s):** workspace.html had `apiUrl: 'http://localhost:8000'` but backend runs on port 8001. Fixed by updating to 8001.
- **All items "Not In Vault" (RLS):** `get_supabase_client()` (anon key) was blocked by RLS for unauthenticated reads. Fixed by using `get_supabase_admin()` (service role key).
- **Windows strftime crash:** `format_vault_time` used `%-m` (Linux-only). Fixed with manual f-string formatting.
- **files.updated_at missing:** Workspace comparison referenced a column that didn't exist. Added via migration.
- **UTC vs local timezone mismatch:** Vault UTC timestamps compared directly against local PowerShell timestamps caused false "Out of Date". Fixed with `dt.astimezone()` conversion.
- **Item number regex ordering:** `mmc12555k88` was truncated to `mmc12555` because standard pattern matched first. Fixed by checking mmc/spn/zzz patterns before standard pattern.
- **Post-upload timestamp mismatch:** Local file's LastWriteTime was older than upload time. Fixed by touching file's LastWriteTime to `Get-Date` after successful upload.

#### Files Changed/Created

- `backend/app/routes/workspace.py` (NEW) -- Workspace comparison endpoint
- `backend/app/routes/files.py` (MODIFIED) -- Auto-create items, regex import
- `backend/app/routes/__init__.py` (MODIFIED) -- Added workspace_router
- `backend/app/main.py` (MODIFIED) -- Added workspace_router
- `Local_Creo_Files/Powershell/PDM-Local-Service.ps1` (MODIFIED) -- Port fix, regex reorder, file touch after upload
- `Local_Creo_Files/creowebjs_apps/workspace.html` (MODIFIED) -- PDM_CONFIG, new API endpoints
- `Local_Creo_Files/Powershell/Backup/Local-FileTimestamp-Service.ps1` (DELETED) -- Obsolete

#### Architecture Decisions

- **Keep a local service:** Creo's embedded browser can't access local files directly. A PowerShell HTTP server on localhost:8083 bridges file operations.
- **Admin client for workspace:** Uses `get_supabase_admin()` to bypass RLS since it's an internal service endpoint without user JWTs.
- **UTC to local conversion:** All vault timestamps are converted to local time server-side before comparison and display.

---

## Previous Versions

### v3.0 -- Web Migration (2025)

**Status:** Previous (superseded by v3.1)

This release is a complete architecture rewrite from the legacy Windows/PowerShell/SQLite system to a modern web stack. The core domain (items, files, BOMs, lifecycle states, item numbering) is preserved, but the technology platform is entirely new.

#### Architecture Changes

| Component | v2.0 (Legacy) | v3.0 (Current) |
|-----------|---------------|-----------------|
| Frontend | Node.js Express + HTML templates | Vue 3 + Vite + Pinia |
| Backend | PowerShell services + Node.js server | FastAPI (Python 3) |
| Database | SQLite file (`pdm.sqlite`) | Supabase PostgreSQL (cloud) |
| Auth | None (local access only) | Supabase Auth (JWT) |
| File Storage | Local filesystem (`D:\PDM_Vault\`) | Supabase Storage (cloud) |
| File Processing | PowerShell FileSystemWatcher services | Upload bridge scripts + FastAPI endpoints |
| BOM Processing | BOM-Watcher PowerShell service | PDM-BOM-Parser.ps1 + FastAPI bulk endpoint |
| DXF/SVG Generation | FreeCAD local + batch files | FreeCAD Docker container |
| Service Management | NSSM Windows Services | uvicorn (backend) + npm (frontend) |
| API Documentation | None | OpenAPI auto-generated (`/docs`) |

#### New Features

- **Vue 3 frontend** with desktop-first UI inspired by PLM systems (Windchill/Teamcenter)
- **FastAPI backend** with automatic request validation via Pydantic and OpenAPI docs
- **Supabase PostgreSQL** cloud database with Row Level Security
- **JWT authentication** via Supabase Auth with role-based access
- **Cloud file storage** via Supabase Storage with signed URLs for secure access
- **Item browser** with search, filtering by lifecycle state and project, sortable columns, and detail panel with BOM tree and where-used data
- **BOM tree view** with recursive multi-level hierarchy
- **Where-used lookup** showing all parent assemblies for a given part
- **Bulk BOM upload** endpoint for batch processing from Creo exports
- **Upsert pattern** for item creation/update from upload bridge
- **MRP views** including dashboard, routing, shop, parts lookup, project tracking, and raw materials
- **Upload bridge** PowerShell scripts bridging local CAD files to the web API
- **Interactive API documentation** at `/docs` (Swagger UI) and `/redoc`
- **Health check endpoint** at `/health`
- **SPA routing** with Vue Router and navigation guards for auth

#### Breaking Changes

This is a complete platform rewrite. There is no in-place upgrade path from v2.0 to v3.0.

- **Database:** SQLite replaced by Supabase PostgreSQL. Data must be migrated.
- **File storage:** Local filesystem replaced by Supabase Storage. Files must be re-uploaded.
- **Services:** PowerShell Windows services replaced by web processes. NSSM is no longer used.
- **Web server:** Node.js Express replaced by Vue 3 (frontend) + FastAPI (backend). Port 3000 is no longer used; the system now uses port 5173 (Vite dev) and port 8000/8080 (FastAPI).
- **API:** All endpoints have changed. The legacy Node.js API is replaced by the FastAPI API under `/api/`.
- **Authentication:** Access now requires Supabase Auth credentials (email/password).

#### Migration Path from v2.0

1. **Set up Supabase project** -- Create tables matching the schema in [27-WEB-MIGRATION-PLAN.md](27-WEB-MIGRATION-PLAN.md)
2. **Export legacy data** -- Extract items, files, and BOM records from SQLite
3. **Import to Supabase** -- Use the SQL Editor or migration scripts to load data
4. **Upload files** -- Re-upload files from the local vault to Supabase Storage
5. **Configure environment** -- Set up `.env` with Supabase credentials
6. **Deploy backend** -- Run FastAPI with uvicorn
7. **Deploy frontend** -- Build and serve Vue application
8. **Set up upload bridge** -- Configure `scripts/pdm-upload/` to point to the new API

#### Known Limitations

- Release and revision workflows are not yet fully automated (manual state changes via API)
- FreeCAD Docker worker integration for automatic DXF/SVG generation is in progress
- No offline mode -- requires internet access to reach Supabase
- Upload bridge still uses PowerShell (requires Windows for local CAD file processing)

---

## Previous Versions

### v2.0 (2025-01-03) -- Documentation and BOM Cost Tools

**Status:** Legacy (superseded by v3.0)

#### Features

- Unified PDM web browser (Node.js Express on port 3000)
- Multi-file DXF/SVG generation with corrected scaling
- BOM cost rollup with hierarchical analysis (`Get-BOMCost.ps1`)
- Creo workspace comparison tool (port 8082)
- Database cleanup and maintenance utilities
- Complete PowerShell automation suite

#### Key Improvements Over v1.0

- DXF scaling fixed (was 645.16x too large)
- Explicit millimeter units in DXF headers
- Enhanced Worker-Processor logging
- Added Part-Parameter-Watcher service
- Improved item number extraction logic (suffix stripping, longest-match-first regex)
- Comprehensive documentation (21 files)

#### Services (5 Production)

1. CheckIn-Watcher -- File ingestion from check-in folder
2. BOM-Watcher -- BOM file processing
3. Worker-Processor -- Task execution (DXF/SVG generation)
4. Part-Parameter-Watcher -- Parameter synchronization
5. MLBOM-Watcher -- Multi-level BOM support

#### Technology Stack

- Backend: PowerShell 5.1+ services managed by NSSM
- Web server: Node.js Express on port 3000
- Database: SQLite (`D:\PDM_Vault\pdm.sqlite`)
- File storage: Local filesystem (`D:\PDM_Vault\CADData\`)
- FreeCAD: Local installation with batch scripts

---

### v1.0 (~2024) -- Initial System

**Status:** Legacy (superseded by v2.0)

#### Features

- Core PDM functionality (check-in, file classification, database registration)
- CheckIn-Watcher service for file ingestion
- BOM-Watcher service for BOM processing
- Worker-Processor for DXF/SVG generation
- SQLite database with 6 main tables
- Basic web interface (PowerShell-generated HTML)
- FreeCAD automation for document generation

#### Known Issues (Fixed in v2.0)

- DXF files were 645.16x too large (scaling error)
- Unit specifications missing in DXF headers
- Item number extraction did not handle `_prt`, `_asm`, `_drw` suffixes
- No proper logging for Worker-Processor
- Limited multi-level BOM support
- No Part-Parameter-Watcher

---

## Version Comparison

| Feature | v1.0 | v2.0 | v3.0 |
|---------|------|------|------|
| **Frontend** | PowerShell HTML | Node.js Express | Vue 3 + Vite |
| **Backend** | PowerShell services | PowerShell + Node.js | FastAPI (Python) |
| **Database** | SQLite | SQLite | Supabase PostgreSQL |
| **Auth** | None | None | JWT (Supabase Auth) |
| **File Storage** | Local filesystem | Local filesystem | Supabase Storage (cloud) |
| **File Ingestion** | CheckIn-Watcher | CheckIn-Watcher | Upload bridge + API |
| **BOM Processing** | BOM-Watcher | BOM-Watcher | BOM parser + bulk API |
| **DXF/SVG Generation** | FreeCAD local | FreeCAD local (fixed) | FreeCAD Docker |
| **API Documentation** | None | None | OpenAPI auto-generated |
| **Service Manager** | NSSM | NSSM | uvicorn / npm |
| **Multi-User** | No | No | Yes (auth + roles) |
| **Cloud Deployment** | No | No | Yes |
| **Item Browser** | Basic HTML | Node.js web app | Vue SPA with detail panel |
| **BOM Tree View** | Manual query | Manual query | Interactive recursive tree |
| **Where-Used** | Manual query | Manual query | Built-in endpoint + UI |
| **MRP Views** | No | Basic | Dashboard + 5 views |
| **Documentation** | Minimal | Comprehensive | Updated for web stack |

---

## Version Support Timeline

| Version | Released | Status | Notes |
|---------|----------|--------|-------|
| v1.0 | ~2024 | Archived | No longer maintained |
| v2.0 | 2025-01-03 | Legacy | Superseded by v3.0, documentation preserved for reference |
| v3.0 | 2025 | Previous | Core web migration, superseded by v3.1 |
| v3.1 | 2026-01-30 | Previous | Workspace comparison, PDM-Local-Service, auto-create items |
| v3.2 | 2026-01-31 | Previous | Per-material pricing, purchased parts enhancement |
| v3.3 | 2026-02-03 | Previous | Project cost report, FreeCAD script improvements |
| v3.4 | 2026-02-05 | Previous | Project scheduling, capacity planning |
| v3.5 | 2026-02-07 | Previous | Waterjet cut time calculation, shop floor enhancements |
| v3.6 | 2026-05-01 | Previous | Station grouping, ECharts nested pie, PDF stamp refinement |
| v3.7 | 2026-05-12 | Previous | MRP Part Lookup redesign, PDF serving improvements, mapkey documentation |
| v3.7.1 | 2026-05-22 | Previous | Vite proxy timeout fix for print packet generation |
| v3.7.2 | 2026-05-22 | Previous | DXF download enhancements, MRP dashboard fixes |
| v3.7.3 | 2026-05-23 | Previous | Testing infrastructure (Vitest, pytest, CI), TypeScript error cleanup (77 fixes) |
| v3.7.4 | 2026-05-23 | Current | PDF revision/iteration stamping, backend reload fix (Pitfall #37) |

---

## Checking Your Version

**v3.7.4 indicators:**
- `stamp_pdf_upload_date()` function in `backend/app/routes/files.py` accepts `revision` and `iteration` parameters
- PDF stamping adds both upload date (x=82) and revision.iteration (x=250) stamps
- Upload endpoint queries existing file iteration BEFORE stamping
- Files table tracks per-file iteration that auto-increments on re-upload

**v3.7.3 indicators:**
- `frontend/vitest.config.ts` exists with Vue plugin configuration
- `frontend/src/utils/scheduling.test.ts` exists with 13 scheduling tests
- `backend/tests/test_items.py` exists with 12 items API tests
- `.github/workflows/ci.yml` exists with CI pipeline configuration
- `npm run type-check` in frontend passes with zero errors
- Build passes clean without TypeScript warnings

**v3.7.2 indicators:**
- DXF bundle filenames include thickness and quantity (e.g., `csp0025_thk-0250_qty-4.dxf`)
- MRP Dashboard slideout "Nest DXF" button hidden with `v-if="false"`
- Remaining time calculation uses `remainingMinutes +=` (not `=`)

**v3.7.1 indicators:**
- `frontend/vite.config.ts` has `timeout: 300000` in the proxy configuration
- Development Notes has Pitfall #36 (Vite Proxy Timeout)
- Important Reminders has #35 (Vite proxy timeout for long operations)

**v3.7 indicators:**
- `frontend/src/views/MrpPartLookupView.vue` has sidebar layout with project filter and "All Parts" option
- `frontend/src/views/MrpPrintLookupView.vue` does not exist (deleted)
- `frontend/src/router/index.ts` has Print Lookup route commented out
- `frontend/src/services/storage.ts` has `getSignedUrlFromPath()` function
- `MAPKEY_CHANGES.md` exists at project root
- MRP Shop view has only "Shop Terminal" and "Part Lookup" navigation buttons (no Print Lookup)

**v3.6 indicators:**
- `workstations` table has `station_group` column
- MRP Cost Report view uses ECharts nested pie chart (not Chart.js)
- Cost Report has grouped operations table with expandable groups
- `frontend/package.json` includes `echarts` and `vue-echarts` dependencies

**v3.5 indicators:**
- `backend/app/services/cutting.py` exists
- `cutting_parameters` table exists in database
- MRP Cost Settings view has "Cutting Parameters" section
- MRP Shop view has material/thickness filter dropdown
- `Documentation/waterjet-cutting-speeds.md` reference doc exists
- File upload normalizes filenames (strips `_prt`, `_asm`, `_drw`, lowercases)

**v3.4 indicators:**
- `frontend/src/utils/scheduling.ts` exists
- MRP Project Tracking view has Gantt chart with scheduled start/end days
- Project info shows "Scheduled Days" calculation
- Gantt bars positioned by capacity-constrained schedule

**v3.3 indicators:**
- `frontend/src/views/MrpCostReportView.vue` exists
- `frontend/package.json` includes `chart.js` and `vue-chartjs` dependencies
- `backend/app/routes/mrp.py` has `/projects/{project_id}/cost-report` endpoint
- MRP Dashboard has "Cost Report" button with pink dot badge

**v3.2 indicators:**
- `mrp_cost_settings` table has `default_cs_price_per_lb`, `default_al_price_per_lb`, `default_ss_price_per_lb` columns
- Routing view shows purchased part info section for `mmc`/`spn` items
- Material assignment badge `[Mat]` appears in MRP part list

**v3.1 indicators:**
- `backend/app/routes/workspace.py` exists
- `files` table has `updated_at` column
- `PDM-Local-Service.ps1` exists in `Local_Creo_Files/Powershell/`
- `Local-FileTimestamp-Service.ps1` is deleted (was in `Backup/`)
- Backend runs on port 8001 (check `backend/.env` for `API_PORT=8001`)

**v3.0 indicators:**
- Backend runs with `uvicorn` (not Node.js or PowerShell services)
- Frontend uses Vue 3 (check `frontend/package.json` for `vue` dependency)
- Database is Supabase PostgreSQL (check `backend/.env` for `SUPABASE_URL`)
- API available at `http://localhost:8001/docs`

**v2.0 indicators:**
- Node.js Express server on port 3000
- SQLite database at `D:\PDM_Vault\pdm.sqlite`
- PowerShell services managed by NSSM
- No authentication required

**v1.0 indicators:**
- Same as v2.0 but with DXF scaling issues and limited documentation

---

## Changelog Format

All future releases follow this format:

```
### vX.Y (YYYY-MM-DD) -- Release Title

**Status:** [Stable | Beta | In Development]

#### New Features
- Description of new functionality

#### Improvements
- Description of enhancements to existing features

#### Bug Fixes
- Description: Solution applied

#### Breaking Changes
- Description of changes requiring migration

#### Migration Path
- Steps to upgrade from previous version
```

---

**Last Updated:** 2026-05-23
**Current Version:** v3.7.4
**Related:** [27-WEB-MIGRATION-PLAN.md](27-WEB-MIGRATION-PLAN.md), [15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md](15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md)
