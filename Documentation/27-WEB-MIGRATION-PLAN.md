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

### Phase 1: Database Setup
- [x] Create Supabase project
- [ ] Apply database migrations (schema above)
- [ ] Set up Supabase Auth (email/password)
- [ ] Create initial users (Jack, Dan, Shop)
- [ ] Configure Supabase Storage buckets

### Phase 2: Backend API
- [ ] Set up FastAPI project structure
- [ ] Configure Supabase client
- [ ] Implement CRUD routes:
  - [ ] Items (create, read, update, search)
  - [ ] Files (upload, download, list)
  - [ ] BOM (create, read, tree query)
  - [ ] Projects (CRUD)
- [ ] Implement auth middleware (JWT validation)
- [ ] Add work queue endpoints

### Phase 3: Frontend Core
- [ ] Initialize Vue 3 + Vite project
- [ ] Set up Pinia stores (auth, items, files)
- [ ] Configure Supabase JS client
- [ ] Build views:
  - [ ] Login page
  - [ ] Item browser (table with filters)
  - [ ] Item detail (metadata, files, BOM, history)
  - [ ] File upload interface
  - [ ] BOM tree viewer
- [ ] Add search functionality

### Phase 4: File Processing
- [ ] Verify FreeCAD Docker worker
- [ ] Create API endpoint to trigger processing
- [ ] Implement job status polling
- [ ] Connect file uploads to work queue
- [ ] Test DXF/SVG generation pipeline

### Phase 5: Data Migration
- [ ] Write SQLite → Supabase migration script
- [ ] Migrate items table
- [ ] Migrate files (upload to Supabase Storage)
- [ ] Migrate BOM relationships
- [ ] Verify data integrity

### Phase 6: Advanced Features
- [ ] Lifecycle state transitions
- [ ] Revision management (A → B → C)
- [ ] Checkout/lock functionality
- [ ] Release workflow
- [ ] Search improvements (full-text)

### Phase 7: Deployment
- [ ] Deploy backend to cloud (Fly.io or similar)
- [ ] Deploy frontend (Vercel/Netlify)
- [ ] Set up FreeCAD worker in cloud
- [ ] Configure production Supabase
- [ ] CI/CD pipeline

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

- [ ] User can log in (Jack, Dan, Shop accounts)
- [ ] User can view items list with search/filter
- [ ] User can view item details (metadata, files, BOM)
- [ ] User can upload STEP files
- [ ] System generates DXF/SVG from STEP
- [ ] User can download any file type
- [ ] User can view/edit BOM relationships
- [ ] Basic lifecycle state management

---

**Document Version:** 2.0
**Updated:** 2025-01-27
**Status:** Ready for Implementation
