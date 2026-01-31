# PDM System Web Migration Plan

## Overview

Migrating the current PowerShell/Windows-based PDM system to a modern web-based architecture.

**Current State:** Windows-native, PowerShell services, SQLite, Node.js simple web browser
**Target State:** Web-based, Vue 3 frontend, FastAPI backend, Supabase (PostgreSQL + Auth + Storage)

---

## Technology Stack

| Component | Target |
|-----------|--------|
| Frontend | Vue 3 + Vite |
| Backend | FastAPI (Python) |
| Database | Supabase (PostgreSQL) |
| Auth | Supabase Auth (JWT) |
| File Storage | Supabase Storage |
| CAD Processing | FreeCAD Docker (cloud-ready) |
| State Management | Pinia |

---

## Scope & Constraints

### Users (Simple - 3 users)
- **Jack** (CAD Engineer) - Primary user, file uploads, BOM management
- **Dan** (Project Manager) - View/track projects, approvals
- **Shop** (Shared account) - View drawings, BOMs, work instructions

### NOT in Scope
- Multi-organization/multi-tenancy
- Mobile-first responsive design
- Offline/PWA capabilities
- Complex role-based permissions

---

## Database Schema (Supabase PostgreSQL)

Simplified single-organization schema:

```sql
-- Users (simple roles)
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  username TEXT UNIQUE NOT NULL,
  email TEXT UNIQUE,
  role TEXT DEFAULT 'viewer', -- 'admin', 'engineer', 'viewer'
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Projects
CREATE TABLE projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  description TEXT,
  status TEXT DEFAULT 'active', -- active, archived, completed
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Items (parts/components)
CREATE TABLE items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  item_number TEXT UNIQUE NOT NULL, -- e.g., 'csp0030'
  name TEXT,
  revision TEXT DEFAULT 'A',
  iteration INTEGER DEFAULT 1,
  lifecycle_state TEXT DEFAULT 'Design', -- Design, Released, Obsolete
  description TEXT,
  project_id UUID REFERENCES projects(id),
  material TEXT,
  mass NUMERIC,
  thickness NUMERIC,
  cut_length NUMERIC,
  is_supplier_part BOOLEAN DEFAULT false,
  supplier_name TEXT,
  supplier_pn TEXT,
  unit_price NUMERIC,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Files/Documents
CREATE TABLE files (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id UUID REFERENCES items(id) NOT NULL,
  file_type TEXT NOT NULL, -- 'CAD', 'STEP', 'DXF', 'SVG', 'PDF'
  file_name TEXT NOT NULL,
  file_path TEXT, -- Supabase Storage path
  file_size INTEGER,
  revision TEXT,
  iteration INTEGER DEFAULT 1,
  uploaded_by UUID REFERENCES users(id),
  created_at TIMESTAMPTZ DEFAULT now()
);

-- BOM (Bill of Materials)
CREATE TABLE bom (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_item_id UUID REFERENCES items(id) NOT NULL,
  child_item_id UUID REFERENCES items(id) NOT NULL,
  quantity INTEGER DEFAULT 1,
  source_file TEXT, -- audit trail
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(parent_item_id, child_item_id)
);

-- Work Queue (task processing)
CREATE TABLE work_queue (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id UUID REFERENCES items(id),
  file_id UUID REFERENCES files(id),
  task_type TEXT NOT NULL, -- 'GENERATE_DXF', 'GENERATE_SVG'
  status TEXT DEFAULT 'pending', -- pending, processing, completed, failed
  payload JSONB,
  error_message TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ
);

-- Lifecycle History (audit trail)
CREATE TABLE lifecycle_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id UUID REFERENCES items(id) NOT NULL,
  old_state TEXT,
  new_state TEXT,
  old_revision TEXT,
  new_revision TEXT,
  old_iteration INTEGER,
  new_iteration INTEGER,
  changed_by UUID REFERENCES users(id),
  change_notes TEXT,
  changed_at TIMESTAMPTZ DEFAULT now()
);

-- Checkouts (file locking)
CREATE TABLE checkouts (
  item_id UUID REFERENCES items(id) PRIMARY KEY,
  user_id UUID REFERENCES users(id) NOT NULL,
  checked_out_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for common queries
CREATE INDEX idx_items_item_number ON items(item_number);
CREATE INDEX idx_items_project ON items(project_id);
CREATE INDEX idx_items_lifecycle ON items(lifecycle_state);
CREATE INDEX idx_files_item ON files(item_id);
CREATE INDEX idx_files_type ON files(file_type);
CREATE INDEX idx_bom_parent ON bom(parent_item_id);
CREATE INDEX idx_bom_child ON bom(child_item_id);
CREATE INDEX idx_work_queue_status ON work_queue(status);
```

---

## Architecture

```
pdm-web/
├── frontend/               # Vue 3 + Vite (desktop-first UI)
│   ├── src/
│   │   ├── views/          # Item browser, BOM viewer, file upload
│   │   ├── components/     # Tables, forms, file viewers
│   │   ├── stores/         # Pinia state (items, auth)
│   │   ├── services/       # Supabase client, API helpers
│   │   └── router/
│   └── package.json
├── backend/                # FastAPI Python
│   ├── app/
│   │   ├── routes/         # items, files, bom, auth, tasks
│   │   ├── models/         # Pydantic schemas
│   │   ├── services/       # Business logic
│   │   └── main.py
│   └── requirements.txt
├── worker/                 # FreeCAD Docker (cloud-ready)
│   ├── Dockerfile
│   └── scripts/
├── docker-compose.yml      # Local dev (worker only)
└── Documentation/
```

---

## Migration Phases

### Phase 1: Database Setup ✅ COMPLETED
- [x] Create Supabase project
- [x] Apply database migrations (schema above)
- [x] Set up Supabase Auth (email/password)
- [x] Create initial users (Jack, Dan, Shop)
- [x] Configure Supabase Storage buckets

### Phase 2: Backend API ✅ COMPLETED
- [x] Set up FastAPI project structure
- [x] Configure Supabase client (dual-client pattern: anon + admin)
- [x] Implement CRUD routes:
  - [x] Items (create, read, update, search, upsert)
  - [x] Files (upload, download, list, auto-create items)
  - [x] BOM (create, read, tree query, bulk upload)
  - [x] Projects (CRUD, archived status)
- [x] Implement auth middleware (JWT validation)
- [x] Add work queue endpoints (generate-dxf, generate-svg, nest-parts)

### Phase 3: Frontend Core ✅ COMPLETED
- [x] Initialize Vue 3 + Vite project
- [x] Set up Pinia stores (auth, items, files, projects, mrp)
- [x] Configure Supabase JS client
- [x] Build views:
  - [x] Login page
  - [x] Item browser (table with filters, search, lifecycle state filter)
  - [x] Item detail (metadata, files, BOM tree, where-used, lifecycle history)
  - [x] File upload interface
  - [x] BOM tree viewer (recursive multi-level)
  - [x] MRP Dashboard, Routing Editor, Shop View, Raw Materials, Part Lookup, Project Tracking
- [x] Add search functionality (client-side + server-side)

### Phase 4: File Processing 🔄 PARTIAL
- [x] Verify FreeCAD Docker worker (container built and tested)
- [x] Create API endpoints to queue tasks (`/api/tasks/generate-dxf`, `/api/tasks/generate-svg`)
- [x] Implement job status polling (TasksView.vue)
- [ ] **Connect file uploads to work queue** (STEP uploads don't auto-queue tasks yet)
- [ ] **Worker polling loop** (worker_loop.py exists but not integrated with queue polling)
- [x] Test DXF/SVG generation pipeline (manual docker exec works)

### Phase 5: Data Migration ⏭️ SKIPPED
- Data migration from legacy SQLite was performed manually
- All production data now lives in Supabase
- Legacy vault archived to `Legacy/PDM_Vault/`

### Phase 6: Advanced Features 🔄 PARTIAL
- [x] Lifecycle state transitions (manual via API)
- [ ] Revision management (A → B → C) - **Not yet implemented**
- [ ] Checkout/lock functionality - **Not yet implemented**
- [ ] Release workflow with validation - **Not yet implemented**
- [x] Search improvements (ilike queries, filters by project and lifecycle state)

### Phase 7: Deployment 🔄 PARTIAL
- [x] Deploy backend locally (uvicorn on port 8001)
- [x] Deploy frontend locally (Vite dev server on port 5174)
- [x] Set up FreeCAD worker in Docker (local Docker Compose)
- [x] Set up Nesting worker in Docker (local Docker Compose)
- [x] Configure Supabase (production-ready cloud instance)
- [ ] **Deploy to cloud** (Fly.io config exists in `DEPLOY.md` but not deployed)
- [ ] CI/CD pipeline - **Not yet set up**

---

## Additional Phases Completed (v3.1)

### Phase 8: MRP System ✅ COMPLETED
- [x] MRP Dashboard with project tracking
- [x] Routing Editor with operation definition
- [x] Shop View for work order tracking
- [x] Raw Materials inventory management
- [x] Part Lookup cross-project search
- [x] Project Tracking with status workflows

### Phase 9: Nesting Automation ✅ COMPLETED
- [x] Docker nesting worker with Bottom-Left Fill algorithm
- [x] DXF parser (lines, arcs, circles, LWPOLYLINE)
- [x] Multi-sheet output with utilization tracking
- [x] Frontend configuration modal (NestConfigModal.vue)
- [x] API endpoints for job creation and status
- [x] Database tables: nest_jobs, nest_job_items, nest_results
- [x] Documentation: `29-NESTING-AUTOMATION.md`

### Phase 10: CreoJS Web Integration ✅ COMPLETED
- [x] Moved CreoJS apps from local files to `frontend/public/creojs/`
- [x] Added Vite dev proxy for `/api` requests
- [x] Updated workspace.html with auto-origin detection
- [x] Workspace comparison API endpoint (`POST /api/workspace/compare`)
- [x] Local service for file operations (`PDM-Local-Service.ps1` on port 8083)

---

## FreeCAD Docker Worker

The worker processes STEP files to generate:
- **DXF flat patterns** - For laser/plasma cutting
- **SVG bend drawings** - For brake press operations

### Cloud Deployment Strategy

The FreeCAD Docker container (`amrit3701/freecad-cli`) is cloud-ready:

```bash
# Example cloud usage (Fly.io, Railway, etc.)
docker run -v /files:/data amrit3701/freecad-cli \
  python3 /scripts/flatten_sheetmetal.py input.step output.dxf
```

**Options for cloud worker:**
1. **Fly.io Machine** - Spin up on-demand for jobs
2. **Railway** - Always-on container with job queue
3. **Cloud Run** - Serverless container execution

Files flow: Supabase Storage → Worker → Supabase Storage

---

## Item Numbering (Preserved)

- Format: `ABC####` (3 letters + 4-6 digits)
- Examples: `csp0030`, `wma20120`
- Lowercase normalized
- Prefixes: `mmc` (McMaster), `spn` (supplier), `zzz` (reference)

---

## Key Decisions

| Decision | Choice |
|----------|--------|
| Database | Supabase PostgreSQL |
| Auth | Supabase Auth |
| File Storage | Supabase Storage |
| Multi-tenancy | No (single org) |
| Offline/PWA | No |
| CAD Processing | FreeCAD Docker (cloud) |

---

## Success Criteria (MVP)

- [x] User can log in (Jack, Dan, Shop accounts) ✅
- [x] User can view items list with search/filter ✅
- [x] User can view item details (metadata, files, BOM) ✅
- [x] User can upload STEP files ✅
- [x] System generates DXF/SVG from STEP ✅ (manual docker exec works, auto-queue pending)
- [x] User can download any file type ✅
- [x] User can view/edit BOM relationships ✅
- [x] Basic lifecycle state management ✅

---

## Current Status Summary

**Migration Progress:** ~85% Complete

**Completed:** Core PDM functionality, MRP system, nesting automation, CreoJS web integration, workspace comparison
**In Progress:** FreeCAD worker queue integration (polling loop exists but not connected)
**Pending:** Cloud deployment, automated lifecycle workflows, revision management

**Next Priority:** Connect FreeCAD worker polling loop to work queue for automated DXF/SVG generation

---

**Document Version:** 3.0
**Updated:** 2026-01-30
**Status:** Core Implementation Complete, Advanced Features In Progress
