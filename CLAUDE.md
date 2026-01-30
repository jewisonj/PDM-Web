# PDM-Web - Product Data Management System (Web Migration)

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

Still at root (actively used or pending migration):
- `PDM_Vault/` - Schema reference (migrate to PostgreSQL)
- `Documentation/` - System docs (27-WEB-MIGRATION-PLAN.md has full plan)

## Item Numbering (Preserved)

- Format: `ABC####` (3 letters + 4-6 digits)
- Examples: `csp0030`, `wma20120`
- Lowercase normalized
- Prefixes: `mmc` (McMaster), `spn` (supplier), `zzz` (reference)

## Development Commands

```bash
# Local development (Supabase handles DB, Auth, Storage)
cd backend && uvicorn app.main:app --reload
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

## Next Steps

1. Set up Docker Compose (PostgreSQL + FastAPI skeleton)
2. Create database migrations from legacy schema
3. Build items API (CRUD + search)
4. Build Vue item browser (table + detail view)
5. Add file upload/download
6. Integrate FreeCAD Docker worker for DXF/SVG generation
