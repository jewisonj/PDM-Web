# PDM System - Version History and Release Notes

**Track changes, updates, and system evolution across all versions**
**Related Docs:** [27-WEB-MIGRATION-PLAN.md](27-WEB-MIGRATION-PLAN.md), [15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md](15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md)

---

## Current Version

### v3.3 (2026-02-03) -- Project Cost Report and FreeCAD Script Improvements

**Status:** Current Production Release

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
| v3.3 | 2026-02-03 | Current | Project cost report, FreeCAD script improvements |

---

## Checking Your Version

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

**Last Updated:** 2026-02-03
**Current Version:** v3.3
**Related:** [27-WEB-MIGRATION-PLAN.md](27-WEB-MIGRATION-PLAN.md), [15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md](15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md)
