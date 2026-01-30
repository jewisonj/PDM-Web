# PDM-Web - Complete System Overview

## System Purpose

PDM-Web is a web-based Product Data Management system for managing CAD files, Bills of Materials, lifecycle tracking, and automated manufacturing document generation. The system serves a small engineering team and provides browser-based access to part data, file storage, BOM navigation, and MRP integration.

---

## Architecture

PDM-Web follows a modern three-tier web architecture with cloud-hosted data services:

- **Frontend:** Vue 3 single-page application served via Vite in development or as static files from the FastAPI backend in production.
- **Backend:** FastAPI (Python 3) REST API handling business logic, file uploads, and database operations.
- **Data Layer:** Supabase provides PostgreSQL database, authentication, and file storage as a managed cloud service.
- **CAD Processing:** A FreeCAD Docker container runs headless to generate DXF flat patterns and SVG bend drawings from STEP files.
- **Upload Bridge:** PowerShell scripts running on a local workstation watch a folder for new files and upload them to the API.

---

## Tech Stack

| Component | Technology | Version/Details |
|-----------|-----------|-----------------|
| Frontend framework | Vue 3 | Composition API, TypeScript |
| Build tool | Vite | Hot module replacement in dev |
| State management | Pinia | Stores: `auth.ts`, `items.ts` |
| Routing | Vue Router | Client-side with auth guards |
| Backend framework | FastAPI | Python 3, async, auto-generated OpenAPI docs |
| Data validation | Pydantic | Request/response schema models |
| Database | PostgreSQL | Hosted by Supabase (cloud) |
| Authentication | Supabase Auth | JWT tokens, email/password |
| File storage | Supabase Storage | `pdm-files` bucket, signed URL downloads |
| CAD processing | FreeCAD | Docker container (`amrit3701/freecad-cli`) |
| Container runtime | Docker Compose | FreeCAD worker container |
| Upload bridge | PowerShell 5.1+ | File watcher on local workstation |

---

## Database Schema

All tables use UUID primary keys and are hosted in Supabase PostgreSQL.

### items

Stores part metadata, revision tracking, lifecycle state, and engineering properties.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| item_number | TEXT | Unique part number (e.g., `csp0030`) |
| name | TEXT | Display name |
| revision | TEXT | Revision letter (`A`, `B`, `C`, ...) |
| iteration | INTEGER | Iteration within a revision |
| lifecycle_state | TEXT | `Design`, `Released`, etc. |
| description | TEXT | Part description |
| project_id | UUID (FK) | Reference to projects table |
| material | TEXT | Material designation (e.g., `STEEL_HSLA`) |
| mass | FLOAT | Mass in grams |
| thickness | FLOAT | Material thickness in mm |
| cut_length | FLOAT | Cut length in mm |
| cut_time | FLOAT | Estimated cut time |
| price_est | FLOAT | Estimated price |
| is_supplier_part | BOOLEAN | Whether this is a purchased part |
| supplier_name | TEXT | Supplier company name |
| supplier_pn | TEXT | Supplier part number |
| unit_price | FLOAT | Per-unit cost |
| created_at | TIMESTAMP | Record creation time |
| updated_at | TIMESTAMP | Last modification time |

New items default to revision `A`, iteration `1`, lifecycle state `Design`.

### files

Tracks uploaded files with references to Supabase Storage.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| item_id | UUID (FK) | Reference to items table |
| file_type | TEXT | `STEP`, `CAD`, `DXF`, `SVG`, `PDF`, `IMAGE`, `OTHER` |
| file_name | TEXT | Original filename |
| file_path | TEXT | Supabase Storage path (bucket/key) |
| file_size | INTEGER | Size in bytes |
| revision | TEXT | File revision letter |
| iteration | INTEGER | File iteration (increments on re-upload) |
| uploaded_by | UUID (FK) | Reference to users table |
| created_at | TIMESTAMP | Upload timestamp |

Multiple files per item are supported. File iteration increments independently of item iteration when the same filename is re-uploaded.

### bom

Single-level Bill of Materials relationships.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| parent_item_id | UUID (FK) | Assembly item |
| child_item_id | UUID (FK) | Component item |
| quantity | INTEGER | Number of child items in assembly |
| source_file | TEXT | Audit trail (source BOM file) |
| created_at | TIMESTAMP | Record creation time |

Each row represents a direct parent-child relationship. Full BOM trees are built by recursively querying child assemblies through the API.

### work_queue

Async task queue for background processing.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| item_id | UUID (FK) | Related item |
| file_id | UUID (FK) | Related file |
| task_type | TEXT | `GENERATE_DXF`, `GENERATE_SVG`, `PARAM_SYNC`, `SYNC` |
| status | TEXT | `pending`, `processing`, `completed`, `failed` |
| payload | JSONB | Task-specific parameters |
| error_message | TEXT | Error details on failure |
| created_at | TIMESTAMP | Task creation time |
| started_at | TIMESTAMP | Processing start time |
| completed_at | TIMESTAMP | Completion time |

### lifecycle_history

Audit trail for item lifecycle state changes.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| item_id | UUID (FK) | Reference to items table |
| old_state | TEXT | Previous lifecycle state |
| new_state | TEXT | New lifecycle state |
| old_revision | TEXT | Previous revision |
| new_revision | TEXT | New revision |
| old_iteration | INTEGER | Previous iteration |
| new_iteration | INTEGER | New iteration |
| changed_by | UUID (FK) | User who made the change |
| change_notes | TEXT | Optional notes |
| changed_at | TIMESTAMP | Time of change |

### checkouts

Tracks which items are currently checked out for editing.

| Column | Type | Description |
|--------|------|-------------|
| item_id | UUID (FK) | Checked-out item |
| user_id | UUID (FK) | User holding the checkout |
| checked_out_at | TIMESTAMP | Checkout time |

Row exists only while checked out and is deleted on check-in.

### users

User accounts linked to Supabase Auth.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| auth_id | UUID | Supabase Auth user ID |
| username | TEXT | Display username |
| email | TEXT | Email address |
| role | TEXT | `admin`, `engineer`, `viewer` |
| created_at | TIMESTAMP | Account creation time |
| updated_at | TIMESTAMP | Last update time |

### projects

Project groupings for organizing items.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| name | TEXT | Project name |
| description | TEXT | Project description |
| status | TEXT | `active`, `completed`, `archived` |
| created_at | TIMESTAMP | Creation time |
| updated_at | TIMESTAMP | Last update time |

---

## API Overview

The FastAPI backend exposes a REST API at the `/api` prefix. Interactive documentation is available at `/docs` (Swagger UI) and `/redoc` (ReDoc).

### Authentication -- `/api/auth`

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/login` | Sign in with email and password. Returns JWT access and refresh tokens. |
| POST | `/api/auth/logout` | Sign out the current user. |
| GET | `/api/auth/me` | Get the authenticated user profile (requires Bearer token). Auto-creates user record on first login. |
| GET | `/api/auth/users` | List all users. |

### Items -- `/api/items`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/items` | List items with optional search (`q`), filter by `lifecycle_state`, `project_id`, `is_supplier_part`. Supports `limit` and `offset` pagination. |
| POST | `/api/items` | Create a new item. Item number is validated against pattern `^[a-z]{3}\d{4,6}$`. |
| GET | `/api/items/{item_number}` | Get item details with associated files. |
| PATCH | `/api/items/{item_number}` | Update item fields. Supports `upsert=true` query parameter to create if not found. |
| DELETE | `/api/items/{item_number}` | Delete an item. |
| GET | `/api/items/{item_number}/history` | Get lifecycle history for an item. |

### Files -- `/api/files`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/files` | List files with optional `item_id` and `file_type` filters. |
| POST | `/api/files/upload` | Upload a file (multipart form: `file`, `item_number`, optional `revision`). Stores in Supabase Storage `pdm-files` bucket. |
| GET | `/api/files/{file_id}` | Get file metadata. |
| GET | `/api/files/{file_id}/download` | Get a signed download URL (valid for 1 hour). |
| DELETE | `/api/files/{file_id}` | Delete file from storage and database. |

### BOM -- `/api/bom`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/bom/{item_number}` | Get single-level BOM (direct children). |
| GET | `/api/bom/{item_number}/tree` | Get full recursive BOM tree (configurable `max_depth`, default 10). |
| GET | `/api/bom/{item_number}/where-used` | Get parent assemblies containing this item. |
| POST | `/api/bom` | Add a single BOM relationship. |
| POST | `/api/bom/bulk` | Bulk BOM upload: replaces entire BOM for an assembly. Creates/updates parent and child items, deletes old BOM entries, inserts new relationships. Used by the upload bridge. |
| PATCH | `/api/bom/{bom_id}` | Update BOM quantity. |
| DELETE | `/api/bom/{bom_id}` | Delete a BOM relationship. |

### Tasks -- `/api/tasks`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/tasks` | List tasks with optional `status`, `task_type`, `item_id` filters. |
| GET | `/api/tasks/pending` | Get pending tasks for worker polling. |
| POST | `/api/tasks` | Create a new task. |
| POST | `/api/tasks/generate-dxf/{item_number}` | Queue DXF generation from item's STEP file. |
| POST | `/api/tasks/generate-svg/{item_number}` | Queue SVG generation from item's STEP file. |
| PATCH | `/api/tasks/{task_id}/start` | Mark task as processing (for worker). |
| PATCH | `/api/tasks/{task_id}/complete` | Mark task as completed or failed. |
| DELETE | `/api/tasks/{task_id}` | Delete a task. |

### Projects -- `/api/projects`

Standard CRUD operations for project management.

### MRP -- `/api/mrp`

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/mrp/projects/{project_id}/print-packet` | Generate a combined PDF print packet for a project. |

### Health -- `/health`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Returns `{"status": "healthy"}`. |

---

## Frontend Views

The Vue 3 frontend is a single-page application with the following views, all requiring authentication (except Login):

| Route | View Component | Description |
|-------|---------------|-------------|
| `/login` | LoginView | Email/password authentication form |
| `/` | HomeView | Dashboard and landing page |
| `/pdm-browser` | ItemsView | Item browser with search, filter, and sortable table |
| `/items/:itemNumber` | ItemDetailView | Item detail: metadata, files list, BOM children/parents, lifecycle history |
| `/part-numbers` | PartNumbersView | Quick part number lookup and search |
| `/projects` | ProjectsView | Project listing and management |
| `/tasks` | TasksView | Work queue monitor showing task status |
| `/mrp/dashboard` | MrpDashboardView | MRP system dashboard |
| `/mrp/routing` | MrpRoutingView | Manufacturing routing configuration |
| `/mrp/shop` | MrpShopView | Shop floor view for production |
| `/mrp/parts` | MrpPartLookupView | MRP part search and lookup |
| `/mrp/tracking` | MrpProjectTrackingView | Project progress tracking |
| `/mrp/materials` | MrpRawMaterialsView | Raw materials inventory management |

### Navigation Guards

Vue Router enforces authentication via a `beforeEach` guard. The auth store initializes on first navigation and redirects unauthenticated users to `/login`. Authenticated users accessing `/login` are redirected to the home page.

---

## Authentication

Authentication is handled by Supabase Auth with JWT tokens.

**Login flow:**
1. User enters email and password on LoginView.
2. Frontend calls Supabase Auth `signInWithPassword`.
3. On success, JWT access token and refresh token are stored in the auth Pinia store.
4. All API calls include the JWT in the `Authorization: Bearer <token>` header.
5. The backend `/api/auth/me` endpoint verifies the token, looks up the user in the `users` table, and auto-creates the user record on first login.

**User roles:**
- `admin` -- Full access (Jack, engineer)
- `engineer` -- Create/edit items and files
- `viewer` -- Read-only access (Dan, Shop)

---

## File Storage

Files are stored in Supabase Storage in the `pdm-files` bucket.

**Storage path convention:** `{item_number}/{filename}`
- Example: `pdm-files/csp0030/csp0030.step`

**Upload process:**
1. Client sends multipart form POST to `/api/files/upload` with `file`, `item_number`, and optional `revision`.
2. Backend reads the file content, determines the file type from the extension.
3. File is uploaded to Supabase Storage at `pdm-files/{item_number}/{filename}`.
4. If the file already exists in storage, it is overwritten.
5. A record is created in the `files` table (or existing record iteration is incremented).

**Download process:**
1. Client calls `GET /api/files/{file_id}/download`.
2. Backend generates a signed URL from Supabase Storage (valid for 1 hour).
3. Client uses the signed URL to download or display the file directly.

**Supported file types:**
| Extension | Type Code | Description |
|-----------|-----------|-------------|
| `.stp`, `.step` | STEP | 3D model files |
| `.prt`, `.asm`, `.drw` | CAD | Native Creo CAD files |
| `.dxf` | DXF | Flat pattern files |
| `.svg` | SVG | Technical/bend drawings |
| `.pdf` | PDF | Documentation |
| `.png`, `.jpg`, `.jpeg` | IMAGE | Images |
| Other | OTHER | Miscellaneous files |

---

## FreeCAD Docker Integration

A Docker container running FreeCAD provides headless CAD processing for generating manufacturing documents from STEP files.

**Docker image:** `amrit3701/freecad-cli:latest`

**Container configuration** (from `docker-compose.yml`):
- Container name: `pdm-freecad-worker`
- Volume mounts: `./files` to `/data/files`, `./FreeCAD/Tools` to `/scripts/tools` (read-only), `./worker/scripts` to `/scripts/worker` (read-only), SheetMetal addon
- Runs in keep-alive mode (`tail -f /dev/null`) for on-demand job execution

### DXF Flat Pattern Generation

**Script:** `FreeCAD/Tools/Flatten_sheetmetal_portable.py`

Generates flat pattern DXF files from STEP models:
- Auto-detects sheet metal bodies
- Configurable K-factor (default: 0.35)
- Outputs DXF in millimeter units
- Includes inner wires (holes)

```bash
docker exec pdm-freecad-worker python3 /scripts/tools/Flatten_sheetmetal_portable.py /data/files/part.stp
```

### SVG Bend Drawing Generation

**Script:** `FreeCAD/Tools/Create_bend_drawing_portable.py`

Generates technical SVG drawings with:
- Flat pattern with bend lines
- Automatic dimensioning (inches with fractional equivalents)
- Bounding box dimensions
- 3D isometric preview
- Material thickness and gauge notation
- A4 page layout

```bash
docker exec pdm-freecad-worker python3 /scripts/tools/Create_bend_drawing_portable.py /data/files/part.stp
```

### Task Queue Integration

The work queue system connects the API with FreeCAD processing:
1. Task created via `POST /api/tasks/generate-dxf/{item_number}` or `POST /api/tasks/generate-svg/{item_number}`.
2. Task enters work queue with status `pending`.
3. A worker polls `GET /api/tasks/pending` and picks up the task.
4. Worker calls `PATCH /api/tasks/{task_id}/start`, executes FreeCAD in Docker, then calls `PATCH /api/tasks/{task_id}/complete`.

---

## Upload Bridge Scripts

The upload bridge is a set of PowerShell scripts that run on a local workstation to bridge the gap between the local CAD environment and the PDM-Web API.

**Location:** `scripts/pdm-upload/`

### PDM-Upload-Service.ps1

The main service script that watches `C:\PDM-Upload` for new files:
- Detects file type from extension
- Uploads CAD files (STEP, PDF, DXF, SVG) to `POST /api/files/upload`
- Ensures the item exists first via `PATCH /api/items/{item_number}?upsert=true`
- Routes BOM text files to the BOM parser
- Routes parameter text files to the item update endpoint
- Skips temporary files (starting with `~` or `.`)
- Moves failed files to a `Failed` subfolder

### PDM-Upload-Functions.ps1

Helper functions for HTTP operations:
- File upload via multipart form POST
- Item upsert via PATCH with query parameter
- Logging utilities

### PDM-BOM-Parser.ps1

Parses BOM text files exported from Creo's tree tool:
- Extracts parent assembly item number from the header
- Parses child parts with quantities
- Extracts properties: description, project, material, mass, thickness, cut length
- Submits parsed BOM to `POST /api/bom/bulk`

### Configuration

All scripts load `PDM-Upload-Config.ps1` which defines:
- `ApiUrl` -- Backend API base URL
- `WatchFolder` -- Local folder to monitor (default: `C:\PDM-Upload`)
- `LogPath` -- Log file location

---

## Item Numbering

**Format:** 3 lowercase letters followed by 4 to 6 digits.

**Pattern (regex):** `^[a-z]{3}\d{4,6}$`

**Examples:**
- `csp0030` -- Custom part
- `wma20120` -- Weldment assembly
- `mmc12345` -- McMaster-Carr supplier part
- `spn00100` -- Other supplier part
- `zzz00001` -- Reference/placeholder item

**Conventions:**
- All item numbers are normalized to lowercase in the database.
- Prefix `mmc` or `spn` automatically sets `is_supplier_part = true`.
- Prefix `zzz` items are skipped during BOM bulk upload (reference only).
- File names with suffixes map back to the base item: `csp0030_flat.dxf` links to item `csp0030`.

**Revision and iteration:**
- New items start at revision `A`, iteration `1`.
- Revisions increment as letters: A, B, C, ...
- Iteration increments within a revision for minor changes.
- File iteration increments independently when the same file is re-uploaded.

---

## Users

| User | Role | Access |
|------|------|--------|
| Jack | admin / engineer | Full access: create/edit items, upload files, manage BOMs |
| Dan | viewer | View items, BOMs, files, projects. Approval workflows. |
| Shop | viewer (shared) | View drawings, BOMs, work instructions on the shop floor |

---

## Development

### Prerequisites

- Python 3.10+
- Node.js 18+ (LTS)
- Docker and Docker Compose
- Supabase account with project configured

### Environment Setup

**Backend** (`backend/.env`):
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-key
API_PORT=8080
DEBUG=true
CORS_ALLOW_ALL=true
```

**Frontend** (`frontend/src/services/supabase.ts`):
Configure the Supabase URL and anon key for client-side auth.

### Development Commands

```bash
# Backend (auto-reload on save)
cd backend && uvicorn app.main:app --reload --port 8080

# Frontend (hot module replacement)
cd frontend && npm run dev

# FreeCAD worker
docker-compose up -d freecad-worker

# View API docs
# http://localhost:8080/docs (Swagger UI)
# http://localhost:8080/redoc (ReDoc)
```

### Production

In production, the Vue frontend is built as static files and served directly by the FastAPI backend. The `main.py` detects a `static/` directory and mounts it, serving `index.html` for all non-API routes (SPA routing).

```bash
# Build frontend
cd frontend && npm run build

# Output goes to backend/static/ (or configured build directory)
# FastAPI serves the SPA automatically
```

---

## Performance Notes

- **FastAPI:** Async Python with Pydantic validation. Auto-generated OpenAPI documentation.
- **Supabase queries:** Direct REST API calls via the Python Supabase client. Pagination supported on all list endpoints.
- **File downloads:** Signed URLs bypass the backend for direct client-to-storage downloads.
- **FreeCAD processing:** 5-15 seconds per file depending on complexity. Runs in isolated Docker container.
- **BOM tree queries:** Recursive queries with configurable depth limit (default 10) to prevent circular references.

---

## Security

- **Authentication:** All frontend views (except login) require a valid JWT.
- **API access:** Backend validates Bearer tokens via Supabase Auth.
- **Admin operations:** Bulk BOM upload and file upload use the Supabase service key (admin client) to bypass Row Level Security for trusted internal operations.
- **CORS:** Configured to allow specific origins in production. Development mode supports `CORS_ALLOW_ALL=true`.
- **File access:** Downloads use time-limited signed URLs (1-hour expiry).
- **Secrets:** Supabase keys stored in environment variables, not committed to source control.

---

**Last Updated:** 2026-01-29
