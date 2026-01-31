# PDM Migration Gap Analysis

**STATUS:** REFERENCE DOCUMENT (Workspace Comparison Feature COMPLETED)

This document compares the legacy Windows/PowerShell/SQLite PDM system against the current web-based Vue 3 + FastAPI + Supabase implementation. Its purpose is to identify features that have been fully migrated, partially migrated, not yet migrated, or intentionally left behind.

**Last updated:** 2026-01-30
**Current Status:** Workspace comparison feature completed in v3.1 (see Documentation/24-VERSION-HISTORY.md)

---

## 1. Fully Migrated

These legacy features have equivalent or improved functionality in the web system.

| Legacy Feature | Web Equivalent | Notes |
|---|---|---|
| **Item Browser** (Node.js Express, port 3000) | Vue 3 `ItemsView.vue` + `ItemDetailView.vue` | Table view with search, sort, filter by lifecycle state and project. Detail panel shows files, BOM, where-used, and lifecycle history. Significant improvement over the Express version. |
| **Item CRUD** (SQLite direct) | FastAPI `/api/items` endpoints | Full create, read, update, delete. Upsert mode for automated services. Lowercase normalization preserved. Supabase PostgreSQL replaces SQLite. |
| **File Upload & Storage** (CheckIn folder -> filesystem) | FastAPI `/api/files/upload` + Supabase Storage | Multipart upload to cloud storage. Signed URL download. File type auto-detection from extension. Files stored in `pdm-files` bucket rather than local filesystem. |
| **File Viewing/Download** | Signed URLs + browser-native PDF/image preview | Opens files in new browser tab. Handles PDF, SVG, images natively. Legacy system required network file share access. |
| **BOM Display** (Node.js detail panel) | Vue 3 BOM section in item detail + `/api/bom/{item_number}/tree` | Single-level and recursive tree queries. Where-used (reverse BOM) lookup. Navigable BOM links in the UI. |
| **BOM Upload** (BOM-Watcher, filesystem) | `PDM-BOM-Parser.ps1` -> `/api/bom/bulk` endpoint | Creo fixed-width BOM text parsing preserved in PowerShell. Uploads via REST API to bulk endpoint. Replaces entire BOM for an assembly in one call. Auto-creates missing items. |
| **CheckIn-Watcher** (FileSystemWatcher service) | `PDM-Upload-Service.ps1` (FileSystemWatcher -> API) | Watches `C:\PDM-Upload` folder. Classifies files by extension. Uploads via HTTP to FastAPI. Processes BOM, MLBOM, and parameter files. Failed files moved to `Failed/` subfolder. |
| **Part-Parameter-Watcher** (filesystem monitor) | `PDM-Upload-Service.ps1` handles `param.txt` files | `Parse-ParameterFile` function in `PDM-BOM-Parser.ps1` extracts item properties from Creo parameter exports. Calls `/api/items/{item_number}?upsert=true` to update or create. |
| **Authentication** (none / open access) | Supabase Auth with JWT | Login/logout, route guards, role-based user records (admin/engineer/viewer). Major improvement over the legacy open-access model. |
| **Search & Filtering** | Client-side filtering in `ItemsView.vue` + server-side `ilike` queries | Search by item number, name, description, project. Filter by lifecycle state and project. Sort by any column. |
| **Part Numbers List** (Express, port 3002) | `PartNumbersView.vue` | Dedicated view for browsing part number prefixes and finding next available numbers. |
| **Project Management** | FastAPI `/api/projects` + `ProjectsView.vue` | Full CRUD for projects. Items linked to projects via `project_id`. |
| **Work Queue Schema** (SQLite `work_queue` table) | FastAPI `/api/tasks` + Supabase `work_queue` table + `TasksView.vue` | Task CRUD, status tracking (pending/processing/completed/failed), queue endpoints for DXF and SVG generation. UI view shows task history. |
| **Lifecycle History Tracking** | `/api/items/{item_number}/history` + `lifecycle_history` table | History tab in item detail view shows state transitions with timestamps. |

---

## 2. Partially Migrated

These features exist in the web system but are incomplete compared to the legacy implementation.

| Legacy Feature | Current State | What Is Missing |
|---|---|---|
| **File Classification by Type** | `get_file_type()` in `files.py` maps extensions to types (STEP, DXF, SVG, PDF, CAD, IMAGE, OTHER). Upload service determines action by extension. | Legacy system moved files into typed subfolders (STEP/, DXF/, SVG/, PDF/). Web system stores all files flat under `pdm-files/{item_number}/`. No subfolder organization, but this may be intentional since Supabase Storage has different conventions. |
| **Multi-Level BOM Processing** | `PDM-Upload-Service.ps1` handles `MLBOM` action and calls `Upload-BOM` (same as single-level). `Parse-BOMFile` uses indent-based parsing. | The BOM parser detects indent levels but the `/api/bom/bulk` endpoint only creates single-level parent-child relationships. True multi-level BOM nesting (grandchildren as separate BOM levels) requires the parser to make multiple API calls, one per assembly level. Current behavior flattens the MLBOM into direct children of the top-level assembly. |
| **FreeCAD Docker Worker** | Dockerfile built, `docker-compose.yml` configured, `run_job.py` with handlers for flatten/bend_drawing/convert_stl/convert_obj. Worker scripts exist at `worker/scripts/`. | The worker container exists but has **no automated polling loop** connecting it to the `work_queue` table. No service fetches pending tasks and dispatches them to the Docker container. The API can queue tasks (`/api/tasks/generate-dxf`, `/api/tasks/generate-svg`) and update their status, but nothing reads the queue and executes the jobs. |
| **Automatic DXF/SVG Regeneration on Re-checkin** | API endpoints exist to queue GENERATE_DXF and GENERATE_SVG tasks. Task status lifecycle is modeled (pending -> processing -> completed/failed). | Legacy system automatically queued regeneration when a STEP file was re-checked in. The web upload service does not trigger regeneration tasks. A re-uploaded STEP file updates the file record but does not queue DXF/SVG generation. Requires either: (a) upload service to call the queue endpoints after STEP upload, or (b) a database trigger on the `files` table. |
| **Item Number Pattern Validation** | `ItemBase` schema has regex pattern `^[a-z]{3}\d{4,6}$`. Upload functions support `mmc`, `spn`, `zzz` patterns. | The Pydantic pattern on `ItemBase` is strict and would reject `mmc` or `spn` prefixed items during direct API create (they have alphanumeric suffixes, not purely digits). The bulk BOM endpoint and upsert path bypass this validation. Needs a more permissive pattern or separate handling for supplier/McMaster items. |

---

## 3. Not Yet Migrated

These legacy features have no implementation in the web system. Listed in approximate priority order.

### High Priority

| Legacy Feature | Description | Effort | Notes |
|---|---|---|---|
| **Worker Queue Processor** | A service (Python loop or cron) that polls the `work_queue` table for pending tasks, downloads the STEP file from Supabase Storage, runs the FreeCAD Docker command, and uploads the output (DXF/SVG) back to storage. Updates task status throughout. | Medium | All the building blocks exist: Docker container with scripts, API endpoints for task lifecycle, storage upload. Needs a ~100-line Python polling service that ties them together. Could run as a background thread in FastAPI or a separate `worker.py` process. |
| **Auto-Queue DXF/SVG on STEP Upload** | When a STEP file is uploaded (or re-uploaded), automatically create GENERATE_DXF and GENERATE_SVG tasks in the work queue. | Low | Add 5-10 lines to the `upload_file` endpoint in `files.py`: after a successful STEP upload, insert tasks into `work_queue`. This was the core automation loop in the legacy system. |

### Medium Priority

| Legacy Feature | Description | Effort | Notes |
|---|---|---|---|
| **BOM Cost Rollup** (`Get-BOMCost.ps1`) | Recursive BOM traversal that multiplies quantities through the tree, sums costs from `price_est`/`unit_price` fields, and detects circular references. Produced formatted cost breakdown output. | Medium | The BOM tree endpoint (`/api/bom/{item_number}/tree`) already does recursive traversal. Adding cost accumulation requires a new endpoint or extending the tree response with rolled-up cost fields. Could also be a frontend calculation from the tree data. |
| **Database Cleanup Utilities** (`PDM-Database-Cleanup.ps1`) | Dry-run + execute tool that found orphaned file records (no matching storage file), orphaned items (no files, no BOM references), and duplicate entries. | Medium | Useful for data hygiene. Implement as an admin-only API endpoint (`/api/admin/cleanup`) that queries for orphans and optionally deletes them. Could also include storage bucket cleanup (files in storage with no database record). |
| **Lifecycle Automation - Release** (`Release-Watcher` stub) | Planned automation for Design -> Released lifecycle transitions. Would enforce rules (all files present, BOM complete, approval recorded) before allowing state change. | Medium | Implement as validation logic in the item update endpoint. When `lifecycle_state` changes to "Released", check prerequisites. Record in `lifecycle_history`. Could add an approval workflow with the `users` table. |
| **Lifecycle Automation - Revise** (`Revise-Watcher` stub) | Planned automation for revision management. When an item is revised (A -> B), create a new revision, increment iteration, archive previous files. | Medium | Implement as a dedicated `/api/items/{item_number}/revise` endpoint. Increment revision letter, reset iteration to 1, optionally copy file records. Record in `lifecycle_history`. |
| **Multi-Level BOM Proper Nesting** | Process Creo MLBOM exports so that each assembly level gets its own BOM entries, not flattened into one level. | Low-Medium | Modify `Parse-BOMFile` in `PDM-BOM-Parser.ps1` to track indent levels and call `/api/bom/bulk` once per assembly in the hierarchy. Or modify the bulk endpoint to accept nested data. |

### Low Priority

| Legacy Feature | Description | Effort | Notes |
|---|---|---|---|
| **ERP Export** (`Export-To-ERP.ps1`) | Exported items to CSV format for ERP system integration. Fields included item number, description, material, mass, cost. | Low | Implement as a download endpoint (`/api/items/export?format=csv`) or a frontend "Export" button that generates a CSV from the items list. Straightforward query + CSV formatting. |
| **McMaster-Carr Integration** (`Get-McMasterPrint.ps1`) | Fetched supplier information and documentation from McMaster-Carr for `mmc`-prefixed items. | Low-Medium | McMaster-Carr does not have a public API. The legacy script likely used web scraping. Could be reimplemented as a utility script or deferred. Items already track `supplier_name`, `supplier_pn`, and `unit_price` fields. |
| **Fix Item Number Suffixes** (`Fix-STEP-Item-Numbers.ps1`, `Fix-Files-Table-Suffixes.ps1`) | One-time cleanup scripts that removed `_prt`, `_asm` suffixes from item numbers in the database. | Low | Write as a one-time migration script or admin endpoint. The web system's `Get-ItemNumber` function in `PDM-Upload-Functions.ps1` already strips suffixes during upload, so this issue should not recur. |
| **File Name Validation** (`Validate-File-Names.ps1`) | Checked that files followed naming conventions (item number prefix, correct extension). | Low | Add validation in the upload endpoint or as a periodic audit query. The upload service already extracts and validates item numbers from filenames. |
| **Pre-Migration Backup** (`Pre-Migration-Backup.ps1`) | Created timestamped full backups of SQLite database and file storage before data operations. | N/A | Supabase provides automated daily backups, point-in-time recovery, and database snapshots. Manual backup scripts are unnecessary in the cloud architecture. |
| **Email Notifications** | Not implemented in legacy (no evidence of email functionality), but commonly expected in PDM systems. | Medium | Would require an email service integration (Supabase Edge Functions, SendGrid, or similar). Use cases: notify on lifecycle changes, task failures, checkout conflicts. Not a migration gap per se, but a potential enhancement. |

### Unlikely to Migrate

| Legacy Feature | Description | Reason |
|---|---|---|
| **Workspace Comparison Tool** (CreoJS HTML tool + `CompareWorkspace.ps1`) | HTML page running inside Creo's embedded browser. Compared local workspace files against PDM database via a local HTTP service on port 8082. Showed file status (Up To Date, Modified, New, Out of Date). Supported bulk file opening in Creo. | Deeply tied to Creo's embedded browser environment and local filesystem access. The web system cannot inspect local Creo workspace files. A partial equivalent could compare files in Supabase Storage against the `files` table, but the local workspace comparison requires a local agent. Could potentially be reimplemented as a feature of `PDM-Upload-Service.ps1` that reports workspace status to the API. Low priority unless Jack specifically requests it. |

---

## 4. Intentionally Not Migrated

These legacy features are obsolete, unnecessary, or superseded by the web architecture.

| Legacy Feature | Reason Not Migrated |
|---|---|
| **NSSM Windows Services** | Legacy services ran as Windows services via NSSM (Non-Sucking Service Manager). The web system uses cloud-hosted FastAPI (Uvicorn) and `PDM-Upload-Service.ps1` as a local script (Task Scheduler or manual). Docker worker replaces dedicated Windows service. NSSM is unnecessary. |
| **SQLite Database** | Replaced by Supabase PostgreSQL. No local database to manage, backup, or VACUUM. |
| **SQLite VACUUM / maintenance** | Supabase handles all database maintenance, autovacuum, and optimization automatically. |
| **Local Filesystem File Storage** (D:\PDM_Vault\CADData\) | Replaced by Supabase Storage buckets. Files accessible via signed URLs from anywhere, not just the local network. |
| **File Subfolder Organization** (STEP/, DXF/, SVG/, PDF/) | Supabase Storage organizes by item number (`pdm-files/{item_number}/`). File type is tracked in the database `file_type` column rather than by folder structure. |
| **Port-Based Multi-Service Architecture** (Express on 3000, 3002, PowerShell on 8082) | Single FastAPI application serves all API routes under `/api/`. Vue SPA handles all frontend routes. No port management needed. |
| **Multi-Database Support** (PDM + MRP as separate SQLite files) | Single Supabase PostgreSQL database with separate tables/schemas for PDM and MRP data. Simpler architecture, proper foreign keys across domains. |
| **Node.js Express Web Server** | Replaced by Vue 3 SPA served from FastAPI static files (production) or Vite dev server (development). |
| **PowerShell Watcher Services** (5 separate watchers) | Consolidated into single `PDM-Upload-Service.ps1` that handles all file types (STEP, PDF, DXF, SVG, BOM, MLBOM, parameters). One watcher replaces five. |
| **Network File Share Access** | Legacy system required Windows network share access to view files. Web system uses Supabase signed URLs accessible from any browser on the Tailnet. |

---

## 5. Summary Status

| Category | Count | Key Items |
|---|---|---|
| Fully Migrated | 13 features | Item CRUD, file upload/download, BOM, auth, search, projects, work queue schema |
| Partially Migrated | 4 features | File classification, MLBOM, FreeCAD worker, auto-regeneration |
| Not Yet Migrated (High) | 2 features | Worker queue processor, auto-queue on STEP upload |
| Not Yet Migrated (Medium) | 5 features | BOM cost rollup, DB cleanup, lifecycle release/revise, MLBOM nesting |
| Not Yet Migrated (Low) | 6 features | ERP export, McMaster integration, suffix fixes, file validation, backup, email |
| Unlikely to Migrate | 1 feature | Creo workspace comparison |
| Intentionally Not Migrated | 10 features | NSSM, SQLite, local filesystem, multi-port architecture, etc. |

### Recommended Next Steps (in order)

1. **Connect the worker to the queue.** Write a Python polling loop that picks up pending tasks from `work_queue`, runs the FreeCAD Docker container, and uploads results. All building blocks exist.
2. **Auto-queue DXF/SVG generation on STEP upload.** Add task creation to the file upload endpoint for STEP files. This closes the core automation loop.
3. **BOM cost rollup endpoint.** The data (`price_est`, `unit_price`, BOM quantities) is already in the database. Add a recursive calculation endpoint.
4. **Lifecycle transition validation.** Add pre-condition checks when moving items to "Released" state.
5. **ERP export.** Simple CSV download from items query.
