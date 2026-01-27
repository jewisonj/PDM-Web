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
│   │   ├── stores/         # Pinia state (items, user)
│   │   └── services/       # API client
│   └── package.json
├── backend/                # FastAPI Python
│   ├── app/
│   │   ├── routes/         # items, files, bom, auth
│   │   ├── models/         # SQLAlchemy models
│   │   └── main.py
│   └── requirements.txt
├── worker/                 # Background task processor
│   └── freecad/            # FreeCAD Docker scripts
├── docker-compose.yml      # PostgreSQL + API + Worker
└── Documentation/          # Legacy docs for reference
```

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

## Database Schema (PostgreSQL - Simplified)

```sql
-- No organizations table needed (single org)
-- Simple users table
users (id, username, email, password_hash, role, created_at)
  -- roles: 'admin', 'engineer', 'viewer'

-- Core tables (similar to legacy)
items (id, item_number, name, revision, iteration, lifecycle_state,
       project, material, mass, thickness, ...)
files (id, item_id, file_type, file_path, revision, uploaded_at)
bom (id, parent_item_id, child_item_id, quantity, source_file)
work_queue (id, item_id, task_type, status, created_at, completed_at)
lifecycle_history (id, item_id, old_state, new_state, changed_by, changed_at)
```

## Legacy Reference

These folders contain the original system for reference during migration:
- `PDM_PowerShell/` - PowerShell services (replace with API + worker)
- `PDM_WebServer/` - Node.js browser (replace with Vue frontend)
- `PDM_Vault/` - Schema reference (migrate to PostgreSQL)
- `Documentation/` - System docs (27-WEB-MIGRATION-PLAN.md has full plan)

## Item Numbering (Preserved)

- Format: `ABC####` (3 letters + 4-6 digits)
- Examples: `csp0030`, `wma20120`
- Lowercase normalized
- Prefixes: `mmc` (McMaster), `spn` (supplier), `zzz` (reference)

## Development Commands

```bash
# Local development
docker-compose up -d db        # Start PostgreSQL
cd backend && uvicorn app.main:app --reload
cd frontend && npm run dev

# Run FreeCAD processing
docker run -v $(pwd)/files:/data amrit3701/freecad-cli python script.py
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
