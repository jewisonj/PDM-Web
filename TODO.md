# PDM-Web Global TODO

**Last Updated:** 2026-01-30
**Current Version:** v3.1
**Project Status:** Active Development

---

## Project Context

PDM-Web is a Product Data Management system migrated from Windows/PowerShell/SQLite to Vue 3 + FastAPI + Supabase. The system manages CAD files, BOMs, manufacturing routing, and automated sheet metal processing.

**Stack:** Vue 3, FastAPI, Supabase (PostgreSQL + Auth + Storage), Docker, PowerShell upload bridge

---

## Recently Completed (v3.1 - Jan 2026)

### CreoJS Web Hosting Migration
- [x] Moved CreoJS apps from `Local_Creo_Files/creowebjs_apps/` to `frontend/public/creojs/`
- [x] Added Vite dev proxy for `/api` requests in `vite.config.ts`
- [x] Updated `workspace.html` with `PDM_CONFIG` auto-origin detection
- [x] Removed hardcoded localhost URLs (now uses `window.location.origin`)
- [x] All CreoJS apps now served from web frontend instead of file:/// URLs

### Workspace Comparison Tool
- [x] Backend endpoint: `POST /api/workspace/compare` compares local Creo files against vault
- [x] Local service: `PDM-Local-Service.ps1` on port 8083 handles file operations
- [x] Added `files.updated_at` column with trigger
- [x] Fixed UTC timezone conversion for timestamp comparison
- [x] Fixed item number regex ordering (mmc/spn/zzz before standard pattern)
- [x] Auto-touch local files after upload to sync timestamps

### MRP System
- [x] MRP Dashboard - Project tracking, routing status, nesting results, cost estimate
- [x] Routing Editor - Operation definition, sheet metal material calc
- [x] Shop View - Work order tracking for shop floor
- [x] Raw Materials view - Material inventory management
- [x] Part Lookup - Cross-project part search
- [x] Project Tracking - MRP project lifecycle management
- [x] Cost Settings - Configurable labor/overhead rates
- [x] Project Cost Estimate - Labor, material, outsourced, purchased breakdown

### Auto-Processing Pipeline
- [x] Auto-queue DXF/SVG generation on STEP upload (via work_queue)
- [x] FreeCAD Docker worker for DXF flat patterns and SVG bend drawings

### Nesting Automation
- [x] Docker nesting worker (`worker/nesting/`) with Bottom-Left Fill algorithm
- [x] DXF parser (lines, arcs, circles, LWPOLYLINE with bulge)
- [x] Multi-sheet output with utilization tracking
- [x] Frontend modal (`NestConfigModal.vue`) for job configuration
- [x] API endpoints: `/api/nesting/projects/{id}/nest`, `/api/nesting/jobs/{id}`
- [x] Database tables: `nest_jobs`, `nest_job_items`, `nest_results`
- [x] Documentation: `29-NESTING-AUTOMATION.md`

### MLBOM Parser
- [x] Multi-level BOM parsing with indent-based hierarchy detection
- [x] Bulk upload endpoint integration
- [x] Parameter sync on parent and child items during BOM upload
- [x] PowerShell scripts: `PDM-BOM-Parser.ps1`, `PDM-Upload-Service.ps1`

### Archived Projects
- [x] Soft-delete pattern: `projects.status = 'archived'`
- [x] Hidden from all views and API queries by default
- [x] Can be restored by changing status back to 'active'

---

## In Progress

### FreeCAD Docker Worker - Testing & Refinement
**Status:** Pipeline exists end-to-end, being tested and improved
**Priority:** HIGH

**What's Done:**
- [x] Docker container built (`worker/freecad-worker`)
- [x] Scripts exist: `flatten_sheetmetal.py`, `bend_drawing.py`
- [x] API endpoints queue tasks: `/api/tasks/generate-dxf`, `/api/tasks/generate-svg`
- [x] Database table: `work_queue` with status lifecycle
- [x] Auto-queue on STEP upload in `backend/app/routes/files.py`
- [x] `worker/worker_loop.py` polls work_queue for pending tasks

**Being Tested/Improved:**
- [ ] Verify worker_loop successfully processes queued tasks end-to-end
- [ ] Error handling and retry logic for failed tasks
- [ ] Edge cases with complex STEP geometry

---

## High Priority (Next Sprint)

### 1. Frontend Build Error Cleanup
**Priority:** MEDIUM
**Effort:** Low-Medium

**Current State:** TypeScript build has pre-existing type errors (non-blocking but noisy)

**Known Issues:**
- Missing type definitions for some Vue component props
- Untyped Supabase responses in some store methods
- Console warnings about reactive objects

**Action Items:**
- [ ] Audit TypeScript errors: `npm run type-check` in frontend
- [ ] Add proper type definitions for component props
- [ ] Type Supabase query responses with generated types
- [ ] Add `// @ts-ignore` with comments for intentional bypasses

---

## Medium Priority (Backlog)

### 4. Lifecycle Automation - Release Validation
**Effort:** Medium

When `lifecycle_state` changes from "Design" to "Released", enforce prerequisites:
- [ ] All required files present (STEP, DXF, PDF)
- [ ] BOM is complete (no missing child items)
- [ ] Item has valid `name` and `description`
- [ ] Optional: Approval record exists

**Implementation:**
- Add validation logic in `PATCH /api/items/{item_number}` endpoint
- Check prerequisites before allowing state transition
- Return 400 with detailed error if validation fails
- Record state change in `lifecycle_history` table

---

### 5. Lifecycle Automation - Revision Management
**Effort:** Medium

Add endpoint for creating new revisions: `POST /api/items/{item_number}/revise`

**Workflow:**
1. Current revision: A, iteration: 3
2. User calls `/revise` → New revision: B, iteration: 1
3. Previous revision files are archived (optionally copied or marked obsolete)
4. New revision starts fresh

**Database Changes:**
- [ ] Consider adding `revision_history` table (optional)
- [ ] Update `lifecycle_history` to track revision changes

---

### 6. Database Cleanup Endpoint
**Effort:** Medium

Admin-only endpoint for data hygiene: `POST /api/admin/cleanup` (dry-run mode + execute mode)

**Features:**
- Find orphaned file records (no matching Supabase Storage file)
- Find orphaned items (no files, no BOM references, lifecycle = "Design")
- Find duplicate BOM entries
- Find files in Storage with no database record
- Optional: Delete orphans (with confirmation)

**UI:**
- Admin view showing cleanup preview
- "Dry Run" button shows what would be deleted
- "Execute" button performs cleanup

---

### 7. ERP Export
**Effort:** Low

Download items as CSV for ERP integration.

**Endpoint:** `GET /api/items/export?format=csv`

**Response:** CSV file with columns:
- item_number, name, description, material, mass, unit_price, lifecycle_state, supplier_name, supplier_pn

**Frontend:**
- Add "Export to CSV" button on Items view
- Download triggers API call with signed CSV response

---

### 8. Multi-Level BOM Proper Nesting
**Effort:** Low-Medium

Currently, MLBOM parser flattens all levels into direct children of the top-level assembly. True multi-level nesting requires each assembly level to have its own BOM entries.

**Current:**
```
Assembly A
  ├── Part B (child of A)
  ├── Part C (child of A)
  └── Subassembly D (child of A)
      ├── Part E (appears as child of A - WRONG)
      └── Part F (appears as child of A - WRONG)
```

**Expected:**
```
Assembly A
  ├── Part B (child of A)
  ├── Part C (child of A)
  └── Subassembly D (child of A)
      ├── Part E (child of D)
      └── Part F (child of D)
```

**Solution:**
- Modify `Parse-BOMFile` in `PDM-BOM-Parser.ps1` to track indent levels
- Call `/api/bom/bulk` once per assembly in the hierarchy
- Or modify bulk endpoint to accept nested JSON structure

---

## Low Priority (Future Enhancements)

### 9. Email Notifications
**Effort:** Medium

**Use Cases:**
- Lifecycle state changes (notify project manager when item is released)
- Task failures (notify engineer when DXF generation fails)
- Checkout conflicts (notify when someone tries to check out a locked item)

**Implementation:**
- Supabase Edge Functions or SendGrid integration
- Notification preferences table (user_id, notification_type, email_enabled)

---

### 10. McMaster-Carr Integration
**Effort:** Medium

Fetch supplier information for `mmc`-prefixed items.

**Note:** McMaster-Carr has no public API. Legacy system likely used web scraping.

**Options:**
- Manual CSV import of McMaster catalog data
- Web scraping (fragile, not recommended)
- Defer until McMaster provides API

---

### 11. Creo Workspace Comparison (Full Local Agent)
**Effort:** High
**Likelihood:** Low (unless specifically requested)

**Current State:** Workspace comparison works via `workspace.html` in Creo's embedded browser + `PDM-Local-Service.ps1` on localhost:8083.

**Future Enhancement:** Standalone local agent that:
- Monitors local Creo workspace directory
- Compares against Supabase vault automatically
- Displays desktop notifications for out-of-date files
- Integrates with PDM-Upload-Service.ps1

**Trade-off:** Adds complexity. Current solution (CreoJS + local service) is working well.

---

## Completed Features (Reference)

### v3.1 Features
- [x] CreoJS web hosting migration
- [x] Workspace comparison API and local service
- [x] Auto-create items on file upload
- [x] UTC timezone conversion for timestamps
- [x] Item number regex ordering fix (mmc/spn/zzz)
- [x] File touch after upload for timestamp sync
- [x] Auto-queue DXF/SVG generation on STEP upload (`backend/app/routes/files.py`)
- [x] MRP project cost estimate endpoint (`/api/mrp/projects/{id}/cost-estimate`) — labor, material, outsourced, purchased breakdown
- [x] Cost settings management (`/api/mrp/cost-settings`)
- [x] Cost estimate display on MRP Dashboard

### v3.0 Core Migration
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
- [x] Projects CRUD
- [x] Lifecycle history tracking
- [x] File upload with auto file type detection
- [x] Signed URL download for all file types

### MRP System (Full Suite)
- [x] MRP Dashboard
- [x] Routing Editor
- [x] Shop View
- [x] Raw Materials
- [x] Part Lookup
- [x] Project Tracking

### Nesting Automation (Full Pipeline)
- [x] Docker nesting worker
- [x] DXF parser (lines, arcs, circles, polylines)
- [x] Bottom-Left Fill algorithm
- [x] Multi-sheet output
- [x] Frontend configuration modal
- [x] Job status polling
- [x] Utilization tracking

---

## Known Issues / Tech Debt

### TypeScript Errors in Build
**Status:** Non-blocking but should be cleaned up
**Impact:** Console noise, potential runtime issues
**Action:** See "Frontend Build Error Cleanup" in High Priority

### Hardcoded Sheet Sizes in Nesting
**Status:** Works but inflexible
**Current:** 48x96, 60x120 hardcoded in frontend modal
**Future:** Add custom sheet size table in database, fetch from API

### No Automated Testing
**Status:** Manual testing only
**Risk:** Regressions during refactoring
**Future:** Add Vitest for frontend, pytest for backend

### Documentation Needs Update
**Files Needing Review:**
- [x] `Update-Compare.md` - Mark as REFERENCE (workspace comparison is complete)
- [x] `Nest_plan.md` - Mark as REFERENCE (nesting service is built)
- [ ] `27-WEB-MIGRATION-PLAN.md` - Update phase checkboxes based on completed work

---

## Documentation Status

### Active Documentation
- `00-TABLE-OF-CONTENTS.md` - Master index (CURRENT)
- `03-DATABASE-SCHEMA.md` - Database reference (CURRENT)
- `04-SERVICES-REFERENCE.md` - Backend API reference (CURRENT)
- `15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md` - Lessons learned (CURRENT)
- `24-VERSION-HISTORY.md` - Release notes (CURRENT)
- `29-NESTING-AUTOMATION.md` - Nesting reference (CURRENT)

### Reference Documentation (Historical)
- `02-PDM-COMPLETE-OVERVIEW.md` - Legacy system overview
- `05-POWERSHELL-SCRIPTS-INDEX.md` - Upload bridge scripts
- `06-BOM-COST-ROLLUP-GUIDE.md` - Cost rollup procedures (to be implemented)
- `12-FREECAD-AUTOMATION.md` - FreeCAD Docker setup
- `20-COMMON-WORKFLOWS.md` - Step-by-step task guides
- `27-WEB-MIGRATION-PLAN.md` - Migration planning (mostly complete)

### Files to Mark as COMPLETED
- `Update-Compare.md` - Workspace comparison is complete
- `Nest_plan.md` - Nesting service is complete

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

# Worker polling loop (NOT YET CONNECTED)
cd worker
python worker_loop.py
```

### Upload Bridge
```bash
cd Local_Creo_Files\Powershell
.\PDM-Upload-Service.ps1  # Watches C:\PDM-Upload folder
.\PDM-Local-Service.ps1   # HTTP service on localhost:8083
```

---

## Next Actions (Prioritized)

1. **Connect FreeCAD worker to work queue** - Complete the polling loop integration
2. **Clean up TypeScript errors** - Run type-check and fix obvious issues
3. **Lifecycle release validation** - Enforce prerequisites for state transitions
4. **Revision management** - Endpoint for creating new revisions
5. **Database cleanup endpoint** - Find orphaned records, dry-run + execute mode
6. **ERP export** - CSV download for items

---

**Maintained by:** Documentation Agent
**Related:** `Documentation/24-VERSION-HISTORY.md`, `Documentation/27-WEB-MIGRATION-PLAN.md`, `CLAUDE.md`
