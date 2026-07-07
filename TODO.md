# PDM-Web Global TODO

**Last Updated:** 2026-07-07
**Current Version:** v3.9.1
**Project Status:** Active Development / Production Use

---

## Project Context

PDM-Web is a Product Data Management system migrated from Windows/PowerShell/SQLite to Vue 3 + FastAPI + Supabase. The system manages CAD files, BOMs, manufacturing routing, and automated sheet metal processing.

**Stack:** Vue 3, FastAPI, Supabase (PostgreSQL + Auth + Storage), Docker, PowerShell upload bridge

---

## Recently Completed (v3.3 - v3.9.1)

### v3.9.1 (2026-07-07) - Build Book Section Print Sets, Document Items, Purchased Display
- [x] New Build Book toolbar print-set dropdown (Reference / Work packages / Kits optgroups) + "Download prints" button
- [x] New endpoint `POST /api/mrp/projects/{id}/section-prints` -- task-sized PDF of one section's prints, qty-stamped, with a cover page flagging missing prints
- [x] `generate_section_prints()` in `backend/app/services/build_book.py`: parallel PDF download, white-backed QTY stamp on each print's first page, pypdf merge
- [x] Verified: PKG 03 (Waterjet) = 27 pages/26 prints/6.9MB in ~11s; Design Reference set = 4 pages/10.9MB
- [x] Supersedes the full-book PDF button for day-to-day use (full book = 107 pages/62 prints/54MB, exceeds Supabase's ~50MB storage cap, no longer has a UI button but still works via API)
- [x] Per-kit "PULL PRINTS" reference line (drawing numbers + revisions) -- `BookKit.printRefs` in `buildBook.ts`
- [x] Document items convention formalized: third-letter-`d` item numbers (csd00010) are controlled documents, excluded from work rows, listed on Build Book cover as "REFERENCE PRINTS -- READ FIRST" -- `isDocumentItem()` in `buildTracker.ts`
- [x] Purchased-item display convention formalized: shop documents show supplier PN + SOURCE column instead of internal mmc/spn item numbers -- `purchasedDisplay()`/`purchasedSource()` in `buildTracker.ts`
- [x] Routing/data notes: csa00080 gained Plumbing step; csa00010 became Weld Cleanup -> Mech Assembly (doors) -> Vinyl Wrap (new station 047) -> Inspection; routing.notes render inline in kit sequences
- [x] Engineering notes recorded: never StreamingResponse over in-memory PDF bytes (~80KB/s vs plain Response), reportlab Helvetica/WinAnsi is ASCII-only (no checkmark/arrow glyphs)
- [x] `buildBook.test.ts` grew 11 -> 14 tests, `buildTracker.test.ts` grew 15 -> 17 tests
- [x] Full reference: `Documentation/32-BUILD-BOOK.md` (Section Print Sets, Document Items, Purchased-Item Display Convention)

### v3.9 (2026-07-06) - Manufacturing Build Book (Phase 1, Web Print View)
- [x] New day-by-day manufacturing Build Book per project: `/mrp/tracking` -> "Build Book" or from Build Tracker toolbar -> `/mrp/book/:projectCode`
- [x] Cover/plan page, day-by-day station-loading calendar, Part I work packages (`PKG NN` sequence order), Part II kit/weld sheets
- [x] Sequence-first, dates-advisory design: PKG numbers govern order, printed days are guidance only
- [x] Recorded-complete rendering matches Tracker/Shop view (`part_completion`, no separate book-completion concept)
- [x] New pure data-shaping module `frontend/src/utils/buildBook.ts`, composes on top of `buildTrackerSheet()` and `calculateSchedule()`
- [x] New view `frontend/src/views/MrpBuildBookView.vue`, letter-portrait print layout
- [x] `buildBook.test.ts` -- 11 Vitest unit tests (39 tests total across scheduling/buildTracker/buildBook at time of release)
- [x] Full reference: `Documentation/32-BUILD-BOOK.md`

### v3.8 (2026-07-05) - Shop-Floor Build Tracker Sheet
- [x] New printable per-project Build Tracker sheet: `/mrp/tracking` -> "Print Build Tracker Sheet" -> `/mrp/tracker/:projectCode`
- [x] Fab parts grouped under parent weldment with per-station checkboxes (SAW/WJ/BRK/BND/DBR/INS/STG)
- [x] Weldments/assemblies matrix (JIG/TIG/DS/WCU/ASM/INS columns), DFS post-order assembly ordering
- [x] 7 derived build milestones (op 10-70) with plan dates from the existing scheduling engine
- [x] Purchased-parts receive checklist (ORD/RCV, long-lead flag for spn/receive-only vs. mmc)
- [x] Pre-fill toggle: already-completed stations print as solid boxes for mid-project reprints; toggle off for a blank sheet
- [x] Two print formats: 11x17 tabloid (one page) or 8.5x11 landscape letter (parts pages + status page), dynamic `@page` CSS per format
- [x] Photo-capture groundwork for a future phase: printed row IDs (F##/A##/P##/M##), corner anchor squares, QR code, dropout-gray shading
- [x] New pure data-shaping module `frontend/src/utils/buildTracker.ts` with 15 Vitest unit tests (first unit tests besides `scheduling.test.ts`)
- [x] New dependency: `qrcode`
- [x] Full reference: `Documentation/31-BUILD-TRACKER-SHEET.md`

### v3.7.6 (2026-05-28) - PDF Measurement Tool
- [x] Added PDF measurement tool to Part Lookup and Shop Terminal views
- [x] Calibration mode: draw line on known dimension, enter actual length
- [x] Measurement mode: click two points on PDF to measure distance
- [x] Fixed Vue proxy compatibility with PDF.js using shallowRef for PDFDocumentProxy
- [x] Measurement results displayed with unit selection (inches or mm)
- [x] Magnifier overlay assists with precise point selection
- [x] Multi-page PDF support with page navigation
- [x] Measure button added to MrpPartLookupView and MrpShopView

### v3.7.5 (2026-05-27) - Auto-Queue DXF Generation
- [x] Re-enabled automatic DXF queuing when STEP files uploaded for items with `needs_dxf=true`
- [x] Upload endpoint checks item's `needs_dxf` flag after STEP file save
- [x] Creates pending GENERATE_DXF job with item_number and auto_queued flag in payload
- [x] Engineers no longer need to manually queue DXF generation for sheetmetal parts

### v3.7.4 (2026-05-23) - PDF Revision/Iteration Stamping
- [x] Added automatic revision.iteration stamp to uploaded PDFs (e.g., "A.15")
- [x] Stamp appears in bottom left corner next to existing upload date stamp (x=250pt)
- [x] File iteration auto-increments on each upload of same filename (1 → 2 → 3...)
- [x] Each file tracks its own revision and iteration in the database
- [x] Iteration determined BEFORE stamping to ensure correct value
- [x] Both stamps (upload date and revision.iteration) appear on every page
- [x] Fixed backend reload issues on Windows (documented as Pitfall #37)

### v3.7.3 (2026-05-23) - Testing Infrastructure and TypeScript Error Cleanup
- [x] Set up Vitest for frontend unit tests (13 tests for scheduling algorithm)
- [x] Set up pytest for backend API tests (12 tests for items API)
- [x] Added GitHub Actions CI pipeline for automated testing on push/PR
- [x] Fixed all 77 build-time TypeScript errors across multiple views
- [x] Fixed scheduling.ts non-null assertions for array access
- [x] Fixed items.ts store type issues
- [x] Fixed storage.ts null safety
- [x] Fixed MrpCostReportView.vue array access and color lookup
- [x] Fixed MrpDashboardView.vue array access, type assertions, defineExpose
- [x] Fixed MrpPrintLookupView.vue bucket parsing
- [x] Fixed MrpProjectTrackingView.vue unused imports and date parsing
- [x] Fixed MrpRoutingView.vue (20 errors: API_BASE_URL, null checks, onClick handlers)
- [x] Fixed MrpShopView.vue regex capture groups, bucket parsing, touch events
- [x] Updated ItemCreate schema pattern to accept both uppercase and lowercase
- [x] Improved PDM-Upload-Functions.ps1 null response handling

### v3.7.2 (2026-05-22) - DXF Download Enhancements
- [x] DXF bundle filenames now include part info: {item_number}_thk-{thickness}_qty-{quantity}.dxf
- [x] Thickness formatted as thousandths of inch (0.25" → 0250, 0.125" → 0125)
- [x] Quantity from BOM included in filename
- [x] Fixed UUID-to-string type mismatch in item info lookup
- [x] Added logging for DXF download debugging
- [x] Fixed "0h Remaining" bug in MRP dashboard slideout (remainingMinutes wasn't being incremented)
- [x] Added 5-minute timeout to Vite proxy for long print packet generation
- [x] Hid "Nest DXF" button from MRP slideout (functionality kept, just UI hidden)

### v3.7.1 (2026-05-22) - Vite Proxy Timeout Fix
- [x] Fixed "Unexpected end of JSON" error when generating print packets
- [x] Added 5-minute timeout to Vite dev server proxy configuration
- [x] Documented in Development Notes as Pitfall #36

### v3.7 (2026-05-12) - MRP Part Lookup Redesign
- [x] Unified Part Lookup view with sidebar layout matching Routing Editor
- [x] "All Parts" filter option for cross-project part search
- [x] PDF serving via Supabase Storage with signed URLs
- [x] Removed Print Lookup page (functionality merged into Part Lookup)
- [x] Documented Creo mapkey changes (FAV_ favorites → hard-coded paths)
- [x] Storage helper functions (`frontend/src/services/storage.ts`)

### v3.6 (2026-05-01) - Station Grouping and Cost Report
- [x] Station grouping for workstations (Weld, Assembly, Fabrication, QC, Outsourced)
- [x] ECharts nested pie chart for cost visualization (replaced Chart.js)
- [x] Grouped operations table with expand/collapse
- [x] Print packet routing stamp made transparent (no longer covers drawing content)

### v3.5.1 (2026-04-30) - Routing Editor Enhancements
- [x] Automatic waterjet time calculation using physics-based formula
- [x] New "Purchased" routing template (Receiving → Staging → Inspection)
- [x] Price badge ($) on items with unit_price in routing editor
- [x] Fixed purchase info save hanging after tab switch (AbortError retry)
- [x] Fixed routing state reset on item change

### v3.5 (2026-02-07) - Waterjet Cut Time Calculation
- [x] Physics-based cut time calculation using `cutting_parameters` table
- [x] Material/thickness filter in MRP Shop view
- [x] File upload filename normalization (strips `_prt`, `_asm`, `_drw`)
- [x] Batch recalculate cut times endpoint
- [x] `Documentation/waterjet-cutting-speeds.md` reference doc

### v3.4 (2026-02-05) - Project Scheduling
- [x] Capacity-constrained project scheduling algorithm
- [x] BOM-based dependency analysis for assemblies
- [x] Gantt chart visualization with scheduled start/end days
- [x] Real-time schedule updates via Supabase Realtime

### v3.3 (2026-02-03) - Project Cost Report
- [x] Project Cost Report view with pie chart visualization
- [x] Labor by workstation, materials, outsourced, purchased breakdown
- [x] Print support with `@media print` CSS
- [x] Simplified FreeCAD DXF flattening (uses built-in `unfold()`)

---

## In Progress

### FreeCAD Docker Worker - Production Validation
**Status:** Pipeline built and tested, running in production
**Priority:** LOW (monitoring only)

**Full Pipeline (Complete):**
- [x] Docker container built (`worker/freecad-worker`)
- [x] FreeCAD scripts: `flatten_sheetmetal.py`, `bend_drawing.py`
- [x] Auto-queue on STEP upload
- [x] Worker loop with atomic task claiming
- [x] Error handling with status tracking

**Monitoring:**
- [ ] Review error rates in `work_queue` table
- [ ] Consider retry logic for transient failures if needed

---

## High Priority (Next Sprint)

### 1. Expand Test Coverage
**Priority:** HIGH
**Effort:** Medium

**Current State:** Testing infrastructure established with initial test suites.

**Completed (v3.7.3):**
- [x] Set up Vitest for frontend unit tests (13 tests for scheduling algorithm)
- [x] Set up pytest for backend API tests (12 tests for items API)
- [x] Add CI pipeline (GitHub Actions) for test runs

**Next Steps:**
- [ ] Add tests for BOM upload endpoint and parsing logic
- [ ] Add tests for print packet generation workflow
- [ ] Add tests for routing save and cost estimation
- [ ] Add component tests for MRP views using Vue Test Utils
- [ ] Add integration tests for file upload and processing

**Future Improvements:**
- [ ] Generate Supabase types: `npx supabase gen types typescript`
- [ ] Add test coverage reporting (Vitest coverage, pytest-cov)
- [ ] Set up E2E tests with Playwright or Cypress

---

## Medium Priority (Backlog)

### 3. Lifecycle Automation - Release Validation
**Effort:** Medium

When `lifecycle_state` changes from "Design" to "Released", enforce prerequisites:
- [ ] All required files present (STEP, DXF, PDF)
- [ ] BOM is complete (no missing child items)
- [ ] Item has valid `name` and `description`
- [ ] Optional: Approval record exists

**Implementation:**
- Add validation logic in `PATCH /api/items/{item_number}` endpoint
- Return 400 with detailed error if validation fails
- Record state change in `lifecycle_history` table

---

### 4. Lifecycle Automation - Revision Management
**Effort:** Medium

Add endpoint for creating new revisions: `POST /api/items/{item_number}/revise`

**Workflow:**
1. Current revision: A, iteration: 3
2. User calls `/revise` → New revision: B, iteration: 1
3. Previous revision files are archived
4. New revision starts fresh

---

### 5. Database Cleanup Endpoint
**Effort:** Medium

Admin-only endpoint for data hygiene: `POST /api/admin/cleanup`

**Features:**
- [ ] Find orphaned file records (no matching Supabase Storage file)
- [ ] Find orphaned items (no files, no BOM references, lifecycle = "Design")
- [ ] Find duplicate BOM entries
- [ ] Dry-run mode + execute mode

---

### 6. ERP Export
**Effort:** Low

Download items as CSV for ERP integration.

**Endpoint:** `GET /api/items/export?format=csv`
- [ ] Add export endpoint
- [ ] Add "Export to CSV" button on Items view

---

### 7. Multi-Level BOM Proper Nesting
**Effort:** Low-Medium

**Current:** MLBOM parser flattens all levels into direct children
**Expected:** Each assembly level should have its own BOM entries

**Solution:**
- Modify `Parse-BOMFile` in `PDM-BOM-Parser.ps1` to track indent levels
- Call `/api/bom/bulk` once per assembly in the hierarchy

---

## Low Priority (Future Enhancements)

### 8. Email Notifications
**Effort:** Medium

**Use Cases:**
- Lifecycle state changes (notify PM when item released)
- Task failures (notify engineer when DXF generation fails)
- Checkout conflicts

**Implementation:**
- Supabase Edge Functions or SendGrid integration

---

### 9. McMaster-Carr Integration
**Effort:** Medium

Fetch supplier information for `mmc`-prefixed items.

**Note:** McMaster-Carr has no public API. Options:
- Manual CSV import of catalog data
- Web scraping (fragile, not recommended)
- Defer until McMaster provides API

---

### 10. Mobile-Responsive Shop View
**Effort:** Medium

**Current:** Desktop-first design works on tablets but not phones
**Future:** Add responsive breakpoints for phone-sized screens on Shop View only

---

## Known Issues / Tech Debt

### TypeScript Errors in Build
**Status:** Non-blocking but should be cleaned up
**Action:** See "TypeScript Error Cleanup" in High Priority

### Hardcoded Sheet Sizes in Nesting
**Status:** Works but inflexible
**Current:** 48x96, 60x120 hardcoded in frontend modal
**Future:** Add custom sheet size table in database

### No Automated Testing
**Status:** Manual testing only
**Risk:** Regressions during refactoring
**Action:** See "Automated Testing Setup" in High Priority

---

## Completed Features (Reference)

### MRP System (Complete)
- [x] MRP Dashboard with project selection, cost estimate, print packet generation
- [x] Routing Editor with operations, materials, purchased part info
- [x] Shop View with station queues, material filtering, batch marking
- [x] Raw Materials view with inventory management
- [x] Part Lookup with cross-project search and PDF viewing
- [x] Project Tracking with Gantt chart and capacity scheduling
- [x] Cost Settings with per-alloy defaults, labor rates, overhead
- [x] Cost Report with nested pie chart, grouped operations, print support
- [x] Print Packet generation with cover sheet, tracking sheets, routing stamps

### Core PDM System (Complete)
- [x] Vue 3 + Vite frontend
- [x] FastAPI backend with OpenAPI docs
- [x] Supabase PostgreSQL database
- [x] Supabase Auth with JWT
- [x] Supabase Storage for files
- [x] Item browser with search, filters, detail panel
- [x] BOM tree view (recursive multi-level)
- [x] Where-used lookup
- [x] Bulk BOM upload endpoint
- [x] Upload bridge PowerShell scripts

### Automation Pipelines (Complete)
- [x] Auto-queue DXF/SVG generation on STEP upload
- [x] FreeCAD Docker worker for DXF flat patterns and SVG bend drawings
- [x] Nesting automation with Bottom-Left Fill algorithm
- [x] Workspace comparison tool (CreoJS + local service)
- [x] Waterjet cut time calculation with physics-based formula

---

## Documentation Status

### Active Documentation (Current)
- `00-TABLE-OF-CONTENTS.md` - Master index
- `03-DATABASE-SCHEMA.md` - Database reference
- `04-SERVICES-REFERENCE.md` - Backend API reference
- `15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md` - 36 pitfalls, 35 reminders
- `24-VERSION-HISTORY.md` - Release notes (v1.0 through v3.7.1)
- `29-NESTING-AUTOMATION.md` - Nesting reference
- `TODO.md` - This file

### Reference Documentation (Historical)
- `02-PDM-COMPLETE-OVERVIEW.md` - Legacy system overview
- `05-POWERSHELL-SCRIPTS-INDEX.md` - Upload bridge scripts
- `12-FREECAD-AUTOMATION.md` - FreeCAD Docker setup
- `20-COMMON-WORKFLOWS.md` - Step-by-step task guides
- `27-WEB-MIGRATION-PLAN.md` - Migration planning (complete)

---

## Development Commands Quick Reference

### Backend
```bash
cd backend
uvicorn app.main:app --reload --port 8001
```

### Frontend
```bash
cd frontend
npm run dev  # Runs on port 5174
```

### Workers
```bash
# FreeCAD worker (for DXF/SVG generation)
docker-compose up -d freecad-worker

# Nesting worker (for sheet nesting)
docker-compose up -d nesting-worker
```

### Upload Bridge
```bash
cd scripts\pdm-upload
.\Start-PDMUpload.bat  # Watches C:\PDM-Upload folder

cd Local_Creo_Files\Powershell
.\PDM-Local-Service.ps1  # HTTP service on localhost:8083
```

---

## Next Actions (Prioritized)

1. **Set up automated testing** - Vitest + pytest + GitHub Actions
2. **Clean up TypeScript errors** - Run type-check and fix obvious issues
3. **Lifecycle release validation** - Enforce prerequisites for state transitions
4. **Database cleanup endpoint** - Find orphaned records
5. **ERP export** - CSV download for items

---

**Maintained by:** Documentation Agent
**Related:** `Documentation/24-VERSION-HISTORY.md`, `Documentation/15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md`, `CLAUDE.md`
