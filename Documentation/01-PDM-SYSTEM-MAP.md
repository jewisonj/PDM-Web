# PDM-Web System Architecture Map

**Quick reference for system layout, data flow, and component locations.**

---

## Architecture Overview

```
                        +---------------------------+
                        |       Users / Browser     |
                        |  (Jack, Dan, Shop)        |
                        +------------+--------------+
                                     |
                                     | HTTPS
                                     v
                        +---------------------------+
                        |    Vue 3 Frontend (SPA)   |
                        |   Vite dev / static build |
                        |   Pinia state management  |
                        |   Vue Router navigation   |
                        +------------+--------------+
                                     |
                       +-------------+-------------+
                       |                           |
                       v                           v
          +---------------------+     +------------------------+
          |   FastAPI Backend   |     |   Supabase Auth        |
          |   Python 3 / REST  |     |   JWT tokens           |
          |   Port 8080        |     |   Email/password login |
          +----------+----------+     +------------------------+
                     |
          +----------+----------+
          |                     |
          v                     v
+-------------------+  +-------------------+
| Supabase Database |  | Supabase Storage  |
| PostgreSQL (cloud)|  | File buckets      |
| Tables: items,    |  | Bucket: pdm-files |
| files, bom,       |  | Signed URLs for   |
| work_queue, etc.  |  | downloads         |
+-------------------+  +-------------------+

          +---------------------------+
          |   Upload Bridge           |
          |   (Local workstation)     |
          |   PowerShell scripts      |
          |   Watches C:\PDM-Upload   |
          |   POSTs to FastAPI API    |
          +---------------------------+

          +---------------------------+
          |   FreeCAD Docker Worker   |
          |   Container: pdm-freecad  |
          |   DXF flat patterns       |
          |   SVG bend drawings       |
          +---------------------------+
```

---

## Technology Layers

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | Vue 3 + Vite + TypeScript | Single-page application, desktop-first UI |
| **State Management** | Pinia | Reactive stores for auth and items |
| **Routing** | Vue Router | Client-side navigation with auth guards |
| **Backend API** | FastAPI (Python 3) | REST API, business logic, file upload handling |
| **Database** | Supabase PostgreSQL | Cloud-hosted relational database |
| **Authentication** | Supabase Auth | JWT-based email/password authentication |
| **File Storage** | Supabase Storage | Cloud file storage with signed URL access |
| **CAD Processing** | FreeCAD Docker | Headless FreeCAD for DXF/SVG generation |
| **Upload Bridge** | PowerShell scripts | Local file watcher that uploads to the API |

---

## Project Structure

```
pdm-web/
|
+-- frontend/                        Vue 3 + Vite application
|   +-- src/
|   |   +-- views/                   Page-level components
|   |   |   +-- HomeView.vue             Dashboard / landing page
|   |   |   +-- LoginView.vue            Authentication page
|   |   |   +-- ItemsView.vue            PDM item browser (search, filter, table)
|   |   |   +-- ItemDetailView.vue       Single item: metadata, files, BOM, history
|   |   |   +-- PartNumbersView.vue      Quick part number lookup list
|   |   |   +-- ProjectsView.vue         Project management
|   |   |   +-- TasksView.vue            Work queue / task monitor
|   |   |   +-- MrpDashboardView.vue     MRP dashboard overview
|   |   |   +-- MrpRoutingView.vue       Manufacturing routing
|   |   |   +-- MrpShopView.vue          Shop floor view
|   |   |   +-- MrpPartLookupView.vue    MRP part search
|   |   |   +-- MrpProjectTrackingView.vue  Project tracking
|   |   |   +-- MrpRawMaterialsView.vue  Raw materials inventory
|   |   |
|   |   +-- components/              Reusable UI components
|   |   +-- stores/                  Pinia state management
|   |   |   +-- auth.ts                 Authentication state, JWT handling
|   |   |   +-- items.ts                Item data caching and operations
|   |   +-- services/                External service clients
|   |   |   +-- supabase.ts             Supabase client configuration
|   |   |   +-- storage.ts              Storage helper utilities
|   |   +-- router/
|   |       +-- index.ts                Route definitions and auth guards
|   +-- package.json
|   +-- vite.config.ts
|
+-- backend/                         FastAPI Python application
|   +-- app/
|   |   +-- main.py                  FastAPI app, CORS, router registration, static serving
|   |   +-- config.py                Pydantic settings (env vars, Supabase keys, CORS)
|   |   +-- routes/                  API route modules
|   |   |   +-- items.py                Item CRUD, search, filtering, upsert
|   |   |   +-- files.py                File upload, download (signed URLs), metadata
|   |   |   +-- bom.py                  BOM CRUD, tree traversal, where-used, bulk upload
|   |   |   +-- auth.py                 Login, logout, current user, user listing
|   |   |   +-- tasks.py                Work queue: list, create, start, complete tasks
|   |   |   +-- projects.py             Project management
|   |   |   +-- mrp.py                  MRP endpoints (print packets)
|   |   +-- models/
|   |   |   +-- schemas.py              Pydantic request/response models
|   |   +-- services/
|   |       +-- supabase.py             Supabase client (anon + admin/service key)
|   |       +-- print_packet.py         MRP print packet generation
|   +-- requirements.txt
|   +-- .env                         Environment variables (not committed)
|
+-- scripts/                         Local upload bridge
|   +-- pdm-upload/
|       +-- PDM-Upload-Service.ps1   File watcher: monitors folder, uploads to API
|       +-- PDM-Upload-Functions.ps1 Helper functions for HTTP upload, item upsert
|       +-- PDM-BOM-Parser.ps1       BOM text file parser (Creo tree exports)
|       +-- PDM-Upload-Config.ps1    Configuration: API URL, watch folder, log path
|
+-- worker/                          FreeCAD Docker worker
|   +-- Dockerfile                   Based on amrit3701/freecad-cli:latest
|   +-- scripts/                     Worker helper scripts
|
+-- FreeCAD/                         FreeCAD processing scripts
|   +-- Tools/
|   |   +-- Flatten_sheetmetal_portable.py    DXF flat pattern generation
|   |   +-- Create_bend_drawing_portable.py   SVG bend drawing generation
|   +-- Mod/
|       +-- sheetmetal/              SheetMetal workbench addon
|
+-- files/                           Local file staging (Docker volume mount)
+-- docker-compose.yml               FreeCAD worker container definition
+-- Documentation/                   System documentation
+-- Legacy/                          Archived previous system (reference only)
+-- CLAUDE.md                        AI assistant project context
```

---

## Data Flow

### File Upload Flow (via Upload Bridge)

```
Local Workstation                    PDM-Web Backend              Supabase
+------------------+                +------------------+         +----------------+
| C:\PDM-Upload\   |   HTTP POST   | POST /api/files/ |         |                |
| file dropped     | ------------> | upload           | ------> | Storage bucket |
| (STEP, PDF, etc) |               |                  |         | pdm-files/     |
+------------------+               | POST /api/items/ |         |                |
                                   | (upsert item)    | ------> | items table    |
                                   +------------------+         | files table    |
                                                                +----------------+
```

### BOM Upload Flow

```
Local Workstation                    PDM-Web Backend              Supabase
+------------------+                +------------------+         +----------------+
| C:\PDM-Upload\   |   HTTP POST   | POST /api/bom/   |         |                |
| BOM.txt dropped  | ------------> | bulk             | ------> | items table    |
| (Creo tree       |               |                  |         | bom table      |
|  export)         |               | Creates/updates  |         |                |
+------------------+               | parent + children|         +----------------+
                                   +------------------+
```

### User Browsing Flow

```
Browser                Vue Frontend          FastAPI Backend        Supabase
+--------+            +-------------+       +----------------+    +----------+
| User   | ---------> | ItemsView   | ----> | GET /api/items | -> | items    |
| clicks |            |             | <---- | JSON response  | <- | table    |
| item   | ---------> | ItemDetail  | ----> | GET /api/items | -> | items +  |
|        |            | View        | <---- | /{item_number} | <- | files +  |
|        |            |             |       |                |    | bom      |
| views  | ---------> | PDF viewer  | ----> | GET /api/files | -> | Storage  |
| file   |            |             | <---- | /{id}/download | <- | signed   |
+--------+            +-------------+       +----------------+    | URL      |
                                                                  +----------+
```

---

## Database Tables

| Table | Primary Key | Purpose |
|-------|-------------|---------|
| **users** | id (UUID) | User accounts linked to Supabase Auth |
| **projects** | id (UUID) | Project groupings for items |
| **items** | id (UUID) | Part metadata, revision, lifecycle, properties |
| **files** | id (UUID) | File records with Supabase Storage paths |
| **bom** | id (UUID) | Parent-child assembly relationships with quantities |
| **work_queue** | id (UUID) | Async task queue (DXF/SVG generation, sync) |
| **lifecycle_history** | id (UUID) | Audit trail for item state changes |
| **checkouts** | item_id + user_id | Active item checkout tracking |

---

## API Route Map

All routes are prefixed with `/api`.

| Module | Prefix | Key Endpoints |
|--------|--------|---------------|
| **auth** | `/api/auth` | `POST /login`, `POST /logout`, `GET /me`, `GET /users` |
| **items** | `/api/items` | `GET /`, `POST /`, `GET /{item_number}`, `PATCH /{item_number}`, `DELETE /{item_number}`, `GET /{item_number}/history` |
| **files** | `/api/files` | `GET /`, `POST /upload`, `GET /{file_id}`, `GET /{file_id}/download`, `DELETE /{file_id}` |
| **bom** | `/api/bom` | `GET /{item_number}`, `GET /{item_number}/tree`, `GET /{item_number}/where-used`, `POST /`, `POST /bulk`, `PATCH /{bom_id}`, `DELETE /{bom_id}` |
| **projects** | `/api/projects` | Project CRUD |
| **tasks** | `/api/tasks` | `GET /`, `GET /pending`, `POST /`, `POST /generate-dxf/{item_number}`, `POST /generate-svg/{item_number}`, `PATCH /{task_id}/start`, `PATCH /{task_id}/complete` |
| **mrp** | `/api/mrp` | `POST /projects/{project_id}/print-packet` |
| **health** | `/health` | `GET /` -- health check |

---

## Configuration Reference

| Component | Config Location | Key Settings |
|-----------|----------------|-------------|
| Backend | `backend/.env` | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`, `API_PORT`, `CORS_ALLOW_ALL` |
| Frontend | `frontend/src/services/supabase.ts` | Supabase URL and anon key |
| Upload Bridge | `scripts/pdm-upload/PDM-Upload-Config.ps1` | API URL, watch folder path, log path |
| Docker | `docker-compose.yml` | Volume mounts, container name |

---

## Development Commands

```bash
# Start backend (development with auto-reload)
cd backend && uvicorn app.main:app --reload --port 8080

# Start frontend (development with hot-reload)
cd frontend && npm run dev

# Start FreeCAD Docker worker
docker-compose up -d freecad-worker

# Run FreeCAD processing manually
docker exec pdm-freecad-worker python3 /scripts/tools/Flatten_sheetmetal_portable.py /data/files/part.stp

# View API documentation
# Navigate to http://localhost:8080/docs (Swagger UI)
# Navigate to http://localhost:8080/redoc (ReDoc)
```

---

**Last Updated:** 2026-01-29
