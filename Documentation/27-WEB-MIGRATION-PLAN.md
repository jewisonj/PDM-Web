# PDM System Web Migration Plan

## Overview

This document outlines the migration plan for converting the current PowerShell/Windows-based PDM system to a modern web-based architecture similar to VetBox-Pro.

**Current State:** Windows-native, PowerShell services, SQLite, Node.js simple web browser
**Target State:** Web-based, Vue 3 frontend, FastAPI backend, PostgreSQL, multi-user capable

---

## Technology Stack Comparison

| Component | Current (v2.0) | Target (v3.0+) |
|-----------|---------------|----------------|
| Frontend | Vanilla HTML/JS | Vue 3 + Vite |
| Backend | Node.js (simple) + PowerShell | FastAPI (Python) |
| Database | SQLite | PostgreSQL + Supabase |
| File Watchers | PowerShell FileSystemWatcher | WebSocket + API polling |
| Authentication | None | JWT + OAuth (Supabase Auth) |
| Deployment | Windows Services (NSSM) | Docker + Fly.io |
| Offline Support | N/A | PWA + IndexedDB (Dexie.js) |
| State Management | None | Pinia |

---

## Architecture Vision

### Domain Model Mapping

| PDM Concept | VetBox Equivalent | Web Implementation |
|-------------|-------------------|-------------------|
| Organization | Clinic | Multi-tenant with RLS |
| Project | Truck | Top-level container |
| Assembly | Compartment (hierarchical) | Self-referencing FK |
| Component/Part | Item | Core data entity |
| Document/File | Stock Location | Versioned attachments |
| User | User | Profiles with roles |
| Team | Clinic Users | Organization membership |

### Database Schema (PostgreSQL)

```sql
-- Organizations (multi-tenant root)
CREATE TABLE organizations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  owner_id UUID REFERENCES auth.users,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Projects (similar to VetBox Trucks)
CREATE TABLE projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID REFERENCES organizations NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  status TEXT DEFAULT 'active', -- active, archived, completed
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Items (parts/components)
CREATE TABLE items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID REFERENCES organizations NOT NULL,
  item_number TEXT NOT NULL,
  name TEXT,
  revision TEXT DEFAULT 'A',
  iteration INTEGER DEFAULT 1,
  lifecycle_state TEXT DEFAULT 'Design', -- Design, Released, Obsolete
  description TEXT,
  project_id UUID REFERENCES projects,
  material TEXT,
  mass NUMERIC,
  thickness NUMERIC,
  is_supplier_part BOOLEAN DEFAULT false,
  supplier_name TEXT,
  supplier_pn TEXT,
  unit_price NUMERIC,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(org_id, item_number)
);

-- Files/Documents (versioned)
CREATE TABLE documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id UUID REFERENCES items NOT NULL,
  file_type TEXT NOT NULL, -- CAD, STEP, DXF, SVG, PDF
  file_name TEXT NOT NULL,
  file_url TEXT, -- Supabase Storage URL
  file_size INTEGER,
  revision TEXT,
  iteration INTEGER,
  uploaded_by UUID REFERENCES auth.users,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- BOM (Bill of Materials)
CREATE TABLE bom (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_item_id UUID REFERENCES items NOT NULL,
  child_item_id UUID REFERENCES items NOT NULL,
  quantity INTEGER DEFAULT 1,
  created_at TIMESTAMPTZ DEFAULT now(),
  source_file TEXT, -- audit trail
  UNIQUE(parent_item_id, child_item_id)
);

-- Work Queue (task processing)
CREATE TABLE work_queue (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id UUID REFERENCES items,
  task_type TEXT NOT NULL, -- GENERATE_DXF, GENERATE_SVG, SYNC
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
  item_id UUID REFERENCES items NOT NULL,
  old_state TEXT,
  new_state TEXT,
  old_revision TEXT,
  new_revision TEXT,
  changed_by UUID REFERENCES auth.users,
  change_notes TEXT,
  changed_at TIMESTAMPTZ DEFAULT now()
);

-- Checkouts (file locking)
CREATE TABLE checkouts (
  item_id UUID REFERENCES items PRIMARY KEY,
  user_id UUID REFERENCES auth.users NOT NULL,
  checked_out_at TIMESTAMPTZ DEFAULT now()
);

-- Organization Memberships
CREATE TABLE org_members (
  org_id UUID REFERENCES organizations NOT NULL,
  user_id UUID REFERENCES auth.users NOT NULL,
  role TEXT DEFAULT 'member', -- owner, admin, engineer, viewer
  joined_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (org_id, user_id)
);
```

### Row-Level Security (RLS)

```sql
-- Enable RLS on all tables
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE items ENABLE ROW LEVEL SECURITY;
-- ... etc

-- Users can only access their organization's data
CREATE POLICY "org_member_access" ON items
  FOR ALL USING (
    org_id IN (
      SELECT org_id FROM org_members
      WHERE user_id = auth.uid()
    )
  );
```

---

## Migration Phases

### Phase 1: Infrastructure Setup (Week 1-2)

**Goals:** Set up new project, basic infrastructure, development environment

**Tasks:**
- [ ] Create new Git repository (PDM-Web or similar name)
- [ ] Set up Docker Compose for local development
  - PostgreSQL 15
  - FastAPI backend
  - Vue 3 frontend (Vite dev server)
- [ ] Configure Supabase project for auth and database
- [ ] Create initial database migrations
- [ ] Set up basic FastAPI app structure
- [ ] Initialize Vue 3 + Vite frontend with Pinia

**Directory Structure:**
```
pdm-web/
├── frontend/
│   ├── src/
│   │   ├── views/
│   │   ├── components/
│   │   ├── stores/
│   │   ├── services/
│   │   ├── router/
│   │   └── lib/
│   ├── public/
│   ├── package.json
│   └── vite.config.js
├── backend/
│   ├── app/
│   │   ├── routes/
│   │   ├── models/
│   │   ├── services/
│   │   ├── database.py
│   │   └── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── migrations/
├── docker-compose.yml
├── fly.toml
└── README.md
```

### Phase 2: Core Data Model (Week 2-3)

**Goals:** Implement core entities and API endpoints

**Tasks:**
- [ ] Create SQLAlchemy models for all entities
- [ ] Implement CRUD routes for:
  - [ ] Organizations
  - [ ] Projects
  - [ ] Items
  - [ ] Documents
  - [ ] BOM
- [ ] Write Supabase migrations
- [ ] Set up RLS policies
- [ ] Create Pydantic schemas for API validation
- [ ] Write basic unit tests

### Phase 3: Authentication & Authorization (Week 3-4)

**Goals:** Secure multi-tenant access

**Tasks:**
- [ ] Integrate Supabase Auth
- [ ] Implement JWT token validation in FastAPI
- [ ] Create user registration flow
- [ ] Implement organization creation/invitation
- [ ] Add role-based access control
- [ ] Create protected route middleware
- [ ] Frontend auth store (Pinia)

### Phase 4: Frontend Core (Week 4-6)

**Goals:** Build main UI components

**Tasks:**
- [ ] Project/Item browser (table view with filters)
- [ ] Item detail panel (metadata, files, BOM, history)
- [ ] Search and filter components
- [ ] File upload/download interface
- [ ] BOM tree visualization
- [ ] Lifecycle state management UI
- [ ] Toast notifications (vue-sonner)

### Phase 5: Data Migration (Week 6-7)

**Goals:** Migrate existing SQLite data to PostgreSQL

**Tasks:**
- [ ] Write migration script (Python)
- [ ] Map SQLite item_number to UUID + item_number
- [ ] Migrate items table
- [ ] Migrate files/documents
- [ ] Migrate BOM relationships
- [ ] Migrate work_queue history
- [ ] Verify data integrity
- [ ] Document migration process

### Phase 6: File Processing Services (Week 7-9)

**Goals:** Replace PowerShell watchers with web services

**Tasks:**
- [ ] Design file upload workflow
  - Frontend uploads to Supabase Storage
  - Backend processes and classifies
  - Creates database records
- [ ] Implement task queue (Celery or background tasks)
  - GENERATE_DXF tasks
  - GENERATE_SVG tasks
  - BOM parsing tasks
- [ ] FreeCAD automation integration
  - Option A: Keep local FreeCAD runner, API triggers
  - Option B: FreeCAD in Docker container
  - Option C: Cloud-based CAD conversion service
- [ ] BOM file parsing (replace BOM-Watcher)
- [ ] Webhook notifications for task completion

### Phase 7: Offline & Sync (Week 9-10)

**Goals:** PWA with offline capability (like VetBox)

**Tasks:**
- [ ] Set up Dexie.js for IndexedDB
- [ ] Implement sync service pattern
- [ ] Create offline store (Pinia)
- [ ] Configure Service Worker (vite-plugin-pwa)
- [ ] Handle conflict resolution
- [ ] Offline indicator UI

### Phase 8: Advanced Features (Week 10-12)

**Goals:** Release workflows, approvals, advanced features

**Tasks:**
- [ ] Implement Release workflow
  - Design review process
  - Approval chain
  - State transitions with validation
- [ ] Implement Revision management
  - Revision increment (A → B → C)
  - Iteration reset
  - Historical archive
- [ ] Full-text search (PostgreSQL FTS)
- [ ] PDF report generation (BOM, release notes)
- [ ] Checkout/lock functionality

### Phase 9: Production Deployment (Week 12-14)

**Goals:** Deploy to production environment

**Tasks:**
- [ ] Set up Fly.io deployment
- [ ] Configure production Supabase
- [ ] Set up CI/CD pipeline (GitHub Actions)
- [ ] Configure error tracking (Sentry)
- [ ] Set up monitoring and alerts
- [ ] SSL/TLS configuration
- [ ] Performance testing
- [ ] Security audit

### Phase 10: Creo Integration (Ongoing)

**Goals:** Maintain CAD integration capability

**Options:**
1. **Local Companion App** (Keep existing approach)
   - Windows service on Creo machine
   - Pushes files to web API
   - Receives tasks via polling

2. **Browser Extension**
   - Creo has web integration capabilities
   - Extension communicates with web API

3. **File Drop Zone**
   - Monitored folder synced to cloud
   - Web service processes uploads

---

## Key Decisions Required

### 1. FreeCAD Processing Location

**Option A: Keep Local** (Recommended for initial migration)
- FreeCAD stays on Windows machine
- API endpoint triggers processing
- Results uploaded via API
- Pros: Minimal change to CAD automation
- Cons: Requires local Windows service

**Option B: Docker Container**
- FreeCAD in headless Docker container
- Pros: Fully cloud-native
- Cons: Complex setup, GPU considerations

**Option C: Cloud CAD Service**
- Use third-party CAD conversion API
- Pros: No infrastructure to manage
- Cons: Cost, dependency on external service

### 2. File Storage

**Option A: Supabase Storage** (Recommended)
- Integrated with auth
- CDN distribution
- Direct uploads from frontend

**Option B: S3/R2**
- More control
- Better for large files
- Requires signed URL management

### 3. Real-time Updates

**Option A: Supabase Realtime** (Recommended)
- Built-in with Supabase
- WebSocket subscriptions

**Option B: Custom WebSocket**
- More control
- More maintenance

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Data loss during migration | Low | High | Multiple backups, staged migration |
| FreeCAD integration breaks | Medium | High | Keep parallel systems during transition |
| Performance issues | Medium | Medium | Load testing, indexing, caching |
| Authentication complexity | Low | Medium | Use proven Supabase Auth patterns |
| Scope creep | High | Medium | Strict phase gates, MVP focus |

---

## Success Criteria

### Minimum Viable Product (MVP)

- [ ] User can log in and see their organization's items
- [ ] User can upload files and create items
- [ ] User can view and edit BOM relationships
- [ ] User can search and filter items
- [ ] Basic lifecycle state management (Design → Released)
- [ ] File download functionality
- [ ] Mobile-responsive interface

### Full Feature Parity

- [ ] All current functionality migrated
- [ ] Multi-user access with proper permissions
- [ ] Release and revision workflows
- [ ] Task queue for DXF/SVG generation
- [ ] Offline capability
- [ ] Creo integration maintained

---

## Timeline Summary

| Phase | Duration | Milestone |
|-------|----------|-----------|
| 1. Infrastructure | 2 weeks | Dev environment running |
| 2. Core Data Model | 1-2 weeks | CRUD API complete |
| 3. Auth | 1 week | Multi-tenant access |
| 4. Frontend Core | 2 weeks | Basic UI functional |
| 5. Data Migration | 1 week | Data migrated |
| 6. File Processing | 2 weeks | Upload/process working |
| 7. Offline/Sync | 1 week | PWA functional |
| 8. Advanced Features | 2 weeks | Full features |
| 9. Production | 2 weeks | Deployed |
| 10. Creo Integration | Ongoing | CAD workflow |

**Total Estimated Duration:** 14-16 weeks for full migration

---

## References

- VetBox-Pro codebase (`J:\VetBox-Pro`) - Reference architecture
- Current PDM Documentation (`D:\Documentation\`)
- Supabase Docs: https://supabase.com/docs
- FastAPI Docs: https://fastapi.tiangolo.com
- Vue 3 Docs: https://vuejs.org/guide
- Pinia Docs: https://pinia.vuejs.org

---

**Document Version:** 1.0
**Created:** 2026-01-26
**Author:** Claude (AI Assistant)
**Status:** Planning Draft
