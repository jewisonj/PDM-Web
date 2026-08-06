# PDM-Web - Product Data Management System (Web Migration)

## ⚠️ CRITICAL: Port Configuration

**ALWAYS check PORTS.md before making any API calls or starting services!**

- **Frontend (Vue/Vite):** Port **5174** (configured in `frontend/vite.config.ts`)
- **Backend (FastAPI):** Port **8001** (configured in `backend/.env` → API_PORT=8001)
- **Frontend API calls:** Use relative URLs (`/api/...`) to leverage Vite proxy
- **Backend startup:** `python -m uvicorn app.main:app --reload --port 8001`

**NEVER hardcode `http://localhost:8000` or assume default ports!**

See `PORTS.md` for complete documentation.

---

## ⚠️ CRITICAL: PDM Data Lives in Supabase, NOT Local Filesystem

**All PDM data is in Supabase. Do NOT search the J: drive or local filesystem for:**
- Part/item information → Query `items` table
- File metadata (DXF, STEP, PDF, SVG) → Query `files` table
- Actual file content → Supabase Storage bucket `pdm-files`
- BOM relationships → Query `bom` table
- Project data → Query `mrp_projects` and `mrp_project_parts` tables

**Local paths that are NOT PDM data storage:**
- `J:\PDM-Web\` → Source code for the web app (this repo)
- `C:\PDM-Upload\` → Temporary staging folder for upload bridge (files move TO Supabase)
- `J:\Aethon\` or other J: drive folders → CAD working directories, NOT the PDM database

**Common PDM Queries:**

```sql
-- Get item with all its files
SELECT i.*, f.file_type, f.file_name, f.file_path
FROM items i
LEFT JOIN files f ON f.item_id = i.id
WHERE i.item_number = 'abc12345';

-- Get project parts with file availability
SELECT i.item_number, i.name, i.material, i.thickness,
       EXISTS(SELECT 1 FROM files f WHERE f.item_id = i.id AND f.file_type = 'DXF') as has_dxf,
       EXISTS(SELECT 1 FROM files f WHERE f.item_id = i.id AND f.file_type = 'STEP') as has_step
FROM mrp_project_parts mpp
JOIN items i ON mpp.item_id = i.id
WHERE mpp.project_id = 'uuid-here';

-- Get BOM tree for an assembly
SELECT parent.item_number as parent, child.item_number as child, b.quantity
FROM bom b
JOIN items parent ON b.parent_item_id = parent.id
JOIN items child ON b.child_item_id = child.id
WHERE parent.item_number = 'asm00100';
```

**Key Data Conventions:**
- `files.file_type` is UPPERCASE: `'DXF'`, `'STEP'`, `'PDF'`, `'SVG'`, `'CAD'`
- `items.item_number` is lowercase: `'jbp00010'`, `'mmc12345'`
- `mrp_projects.status` is Title Case: `'Setup'`, `'Active'`, `'Complete'`

**Common Admin Tasks:**

1. **"Check files for project X"** → Query mrp_project_parts + files, report what's present/missing
2. **"Are STEP files up to date?"** → Compare `files.updated_at` timestamps, check `step_fingerprint` for changes
3. **"Review BOM for project"** → Query bom table joined with items, check source_file and quantities
4. **"What's missing before build?"** → Sheet metal parts (has thickness) need DXF+STEP; assemblies need STEP

**Finding a Project:**
```sql
-- Projects use project_code like 'WM_0513', 'SPA0030'
SELECT id, project_code, top_assembly_id, status
FROM mrp_projects
WHERE project_code = 'WM_0513';
```

---

## STEP File Fingerprinting System

STEP files cannot be compared byte-by-byte (timestamps and entity IDs change on re-export). We use geometric fingerprints instead.

**Key Components:**
- `scripts/pdm-upload/step_fingerprint.py` - CLI tool for PowerShell upload service
- `backend/app/services/step_compare.py` - Python service for backend
- `files.step_fingerprint` column - Stores JSON fingerprint in database

**Fingerprint Contents:**
- Entity counts (CARTESIAN_POINT, LINE, ADVANCED_FACE, etc.)
- Bounding box (min/max X, Y, Z)
- File size

**Comparing STEP Files:**
```sql
-- Check if item has fingerprint stored
SELECT step_fingerprint FROM files
WHERE item_id = (SELECT id FROM items WHERE item_number = 'csp00050')
AND file_type = 'STEP';
```

**Upload Service Behavior:**
- Computes fingerprint of incoming file
- Compares against stored fingerprint (fast - no download needed)
- Skips identical files (same geometry)
- Uploads changed files with automatic revision bump

---

## Upload Bridge (C:\PDM-Upload)

The PowerShell upload service watches `C:\PDM-Upload` and uploads files to PDM.

**Supported File Types:**
- STEP/STP → Items table + Supabase Storage (with fingerprint)
- DXF/SVG/PDF → Files table + Supabase Storage
- PRT/ASM/DRW (Creo) → CAD files
- BOM.txt/MLBOM.txt → BOM relationships
- treetool.txt → Tree structure updates

**File Flow:**
```
C:\PDM-Upload/             → Staging folder (local)
  ↓ PowerShell service
Supabase Storage           → pdm-files bucket
Supabase PostgreSQL        → items, files, bom tables
```

**Service Location:** `scripts/pdm-upload/PDM-Upload-Service.ps1`

---

## ⚠️ CRITICAL: Database Query Discipline

**Before reporting query results to the user, verify the query is correct.**

1. **No assumptions about data format.** Before writing a query, check actual values:
   ```sql
   SELECT DISTINCT column_name FROM table LIMIT 10;
   ```

2. **Zero results = investigate the query first.** If a query returns nothing when data should exist, assume the query is wrong. Check for:
   - Case sensitivity (PostgreSQL strings are case-sensitive)
   - Wrong column names or table names
   - Incorrect JOIN conditions
   - Typos in filter values

3. **Sanity-check before reporting.** If results seem implausible (e.g., "all 39 parts are missing files"), stop and verify before telling the user. The query is more likely wrong than the data.

4. **When uncertain, show your work.** Run exploratory queries first, share what you find, then build the final query.

**Documentation Reference:**
- Detailed pitfalls and patterns: `Documentation/15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md`
- Only read full documentation files when actively debugging an issue in that domain
- For quick lookups, use Grep to search documentation rather than reading entire files

---

## Project Overview

Migrating a Windows/PowerShell-based PDM system to a **web-based architecture**. This is a small-team, desktop-first application for managing CAD files, BOMs, and manufacturing documents.

**Project Type:** Web Migration
**Target Stack:** Vue 3 + FastAPI + PostgreSQL + Docker
**UI Focus:** Desktop/large tablet (not mobile-first)

## Scope & Constraints

**Users (Simple):**
- Jack (CAD Engineer) - Primary user, file uploads, BOM management
- Dan (Project Manager) - View/track projects, approvals
- Shop (Shared account) - View drawings, BOMs, work instructions

**NOT needed:**
- Multi-organization/multi-tenancy
- Mobile-first responsive design
- Offline/PWA capabilities
- Complex role-based permissions

## Target Architecture

```
pdm-web/
├── frontend/               # Vue 3 + Vite (desktop-first UI)
│   ├── src/
│   │   ├── views/          # Item browser, BOM viewer, file upload
│   │   ├── components/     # Tables, forms, file viewers
│   │   ├── stores/         # Pinia state (items, auth)
│   │   └── services/       # Supabase client
│   └── package.json
├── backend/                # FastAPI Python
│   ├── app/
│   │   ├── routes/         # items, files, bom, auth, tasks
│   │   ├── models/         # Pydantic schemas
│   │   ├── services/       # Supabase client, business logic
│   │   └── main.py
│   └── requirements.txt
├── worker/                 # FreeCAD Docker (cloud-ready)
│   ├── Dockerfile
│   └── scripts/
├── docker-compose.yml      # Local dev (worker only)
└── Documentation/          # Legacy docs for reference
```

**Database:** Supabase (PostgreSQL + Auth + Storage) - no local DB needed

## FreeCAD Docker Integration

**Docker Image:** `amrit3701/freecad-cli:latest`

Custom scripts in `FreeCAD/Tools/`:
- `Flatten sheetmetal portable.py` - DXF flat patterns
- `Create bend drawing portable.py` - SVG bend drawings

```bash
# Example Docker usage
docker run -v /files:/data amrit3701/freecad-cli:latest \
  python /data/flatten_sheetmetal.py input.step output.dxf
```

## Database Schema (Supabase PostgreSQL)

```sql
-- Simple users (linked to Supabase Auth)
users (id UUID, username, email, role, created_at, updated_at)
  -- roles: 'admin', 'engineer', 'viewer'

-- Core tables
projects (id, name, description, status, created_at, updated_at)
items (id, item_number, name, revision, iteration, lifecycle_state,
       project_id, material, mass, thickness, cut_length, ...)
files (id, item_id, file_type, file_name, file_path, revision, iteration, uploaded_by, created_at)
bom (id, parent_item_id, child_item_id, quantity, source_file, created_at)
work_queue (id, item_id, file_id, task_type, status, payload, error_message, created_at, ...)
lifecycle_history (id, item_id, old_state, new_state, changed_by, changed_at, ...)
checkouts (item_id, user_id, checked_out_at)
```

Full schema in `Documentation/27-WEB-MIGRATION-PLAN.md`

## Legacy Reference

Legacy system folders have been moved to `Legacy/` for cleaner project structure:
- `Legacy/PDM_PowerShell/` - PowerShell services (replaced by FastAPI backend)
- `Legacy/PDM_WebServer/` - Node.js browser (replaced by Vue frontend)
- `Legacy/PDM-Libraries/` - iTextSharp PDF library (no longer used)

Also archived (migration complete):
- `Legacy/PDM_Vault/` - Legacy SQLite vault (data migrated to Supabase)

Still at root:
- `Documentation/` - System docs (27-WEB-MIGRATION-PLAN.md has full plan)

## Item Numbering (Preserved)

- Format: `ABC####` (3 letters + 4-6 digits)
- Examples: `csp0030`, `wma20120`
- Lowercase normalized
- Prefixes: `mmc` (McMaster), `spn` (supplier), `zzz` (reference)

## Development Commands

```bash
# Local development (Supabase handles DB, Auth, Storage)
cd backend && uvicorn app.main:app --reload --port 8001
cd frontend && npm run dev

# FreeCAD worker (local Docker)
docker-compose up -d freecad-worker
docker exec pdm-freecad-worker python3 /scripts/worker/flatten_sheetmetal.py /data/files/part.stp
```

## Key Documents

- `Documentation/27-WEB-MIGRATION-PLAN.md` - Full migration phases
- `Documentation/28-CLEANUP-RECOMMENDATIONS.md` - Legacy cleanup
- `Documentation/02-PDM-COMPLETE-OVERVIEW.md` - Original architecture
- `Documentation/03-DATABASE-SCHEMA.md` - Legacy SQLite schema

## Specialized Agents (USE THESE)

Custom agents live in `.claude/agents/`. **Delegate to these agents aggressively** to keep the main context window lean. Each agent has deep domain knowledge pre-loaded so it can work autonomously.

| Agent | File | Use For |
|-------|------|---------|
| **supabase** | `supabase.md` | Database schema, queries, RLS policies, auth flows, storage buckets, migrations, backend stability. Knows all 16 tables, indexes, triggers, dual-client pattern. |
| **mrp** | `mrp.md` | Manufacturing features, shop floor UI, routing, materials, labor tracking, cost estimation, print packets. Knows what managers vs shop workers need. |
| **style** | `style.md` | UI consistency, dark theme (MRP) vs light theme (PDM), slideout panels, tables, badges, buttons, spacing. Has the complete color system and component patterns. |
| **documentation** | `documentation.md` | Recording changes, documenting bug fixes, updating docs after features. Knows all 27+ documentation files. |
| **creojs** | `creojs.md` | CreoJS apps in Creo Parametric browser, PFC API (pfcSession, pfcModel, etc.), workspace.html. Reference: `creojs-reference.md` |
| **dxf-pipeline** | `dxf-pipeline.md` | DXF/SVG file creation, FreeCAD sheet metal flattening, nesting geometry, open segment debugging, STEP-to-nested-DXF pipeline. Knows all curve types, coordinate transforms, and the full pipeline. |
| **pricing** | `pricing.md` | Cost estimation, raw material pricing, labor rates, overhead/markup, workstation rates, outsourced ops. Knows all current prices, formulas, industry benchmarks, and improvement opportunities. |

### When to Delegate
- **Changing database/backend** -> Delegate to `supabase` agent
- **Building/fixing MRP features** -> Delegate to `mrp` agent
- **Building/fixing UI components** -> Delegate to `style` agent for review
- **After completing any task** -> Delegate to `documentation` agent to record what changed
- **CreoJS/Creo browser work** -> Delegate to `creojs` agent
- **DXF/SVG/FreeCAD/nesting work** -> Delegate to `dxf-pipeline` agent
- **Pricing/cost estimation work** -> Delegate to `pricing` agent
- **Multiple concerns** -> Delegate to multiple agents in parallel

### Why Delegate
Agents run in isolated context windows. Delegating keeps the main conversation context clean and available for coordination, while agents handle the deep domain work with their full specialized knowledge loaded.

## Next Steps

1. Set up Docker Compose (PostgreSQL + FastAPI skeleton)
2. Create database migrations from legacy schema
3. Build items API (CRUD + search)
4. Build Vue item browser (table + detail view)
5. Add file upload/download
6. Integrate FreeCAD Docker worker for DXF/SVG generation
