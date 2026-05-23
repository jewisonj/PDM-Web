# PDM-Web Global TODO

**Last Updated:** 2026-05-22
**Current Version:** v3.7.2
**Project Status:** Active Development / Production Use

---

## Project Context

PDM-Web is a Product Data Management system migrated from Windows/PowerShell/SQLite to Vue 3 + FastAPI + Supabase. The system manages CAD files, BOMs, manufacturing routing, and automated sheet metal processing.

**Stack:** Vue 3, FastAPI, Supabase (PostgreSQL + Auth + Storage), Docker, PowerShell upload bridge

---

## Recently Completed (v3.3 - v3.7.2)

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

### 1. Automated Testing Setup
**Priority:** HIGH
**Effort:** Medium

**Current State:** Testing infrastructure established.

**Completed:**
- [x] Set up Vitest for frontend unit tests (13 tests for scheduling algorithm)
- [x] Set up pytest for backend API tests (12 tests for items API)
- [x] Add CI pipeline (GitHub Actions) for test runs

**Action Items:**
- [ ] Start with critical paths: BOM upload, print packet generation, routing save

---

### 2. TypeScript Error Cleanup
**Priority:** MEDIUM - COMPLETED
**Effort:** Low-Medium

**Current State:** All 77 build-time TypeScript errors fixed. Build passes clean.

**Completed:**
- [x] Audit TypeScript errors: `npm run type-check` in frontend
- [x] Fixed unused imports/variables across multiple files
- [x] Fixed core scheduling.ts type safety
- [x] Fixed items.ts store type issues
- [x] Fixed MrpCostReportView.vue - array access and color lookup
- [x] Fixed MrpDashboardView.vue - array access and type assertions
- [x] Fixed MrpPrintLookupView.vue - bucket parsing
- [x] Fixed MrpProjectTrackingView.vue - unused imports and date parsing
- [x] Fixed MrpRoutingView.vue - 20 errors including API_BASE_URL, null checks, onClick handler
- [x] Fixed MrpShopView.vue - regex capture groups, bucket parsing, touch events

**Future Improvements (optional):**
- [ ] Generate Supabase types: `npx supabase gen types typescript`
- [ ] Add proper type definitions for component props

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
