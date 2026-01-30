# Backend Services Reference

Complete reference for all backend services in the PDM-Web system.

---

## Architecture Overview

The PDM-Web backend is a FastAPI (Python 3) application that provides a REST API for managing items, files, BOMs, projects, tasks, and authentication. All persistent data lives in Supabase (PostgreSQL), authentication is handled by Supabase Auth, and file storage uses Supabase Storage.

```
                          +------------------+
                          |  Supabase Cloud  |
  Vue Frontend  --------> |  - PostgreSQL    |
       |                  |  - Auth (JWT)    |
       v                  |  - Storage       |
  FastAPI Backend ------> +------------------+
       ^                         ^
       |                         |
  Upload Bridge (PowerShell)     |
       |                         |
  PDM-Local-Service ------------>+
  (localhost:8083)
       |
  Creo Workspace (local files)
```

The PDM-Local-Service is a PowerShell HTTP server running on `localhost:8083` that bridges Creo's embedded browser with local file operations (timestamps, uploads, downloads). It communicates with both the FastAPI backend and local filesystem.

### Key Components

| Component | Technology | Purpose |
|-----------|-----------|---------|
| API Server | FastAPI + Uvicorn | REST API for all data operations |
| Database | Supabase PostgreSQL | Items, files, BOMs, projects, users, work queue |
| Authentication | Supabase Auth | JWT-based email/password login |
| File Storage | Supabase Storage | CAD files, PDFs, DXFs, SVGs in `pdm-files` bucket |
| Upload Bridge | PowerShell scripts | Local folder watcher that uploads to the API |
| PDM-Local-Service | PowerShell HTTP server | Bridges Creo browser with local files (localhost:8083) |
| FreeCAD Worker | Docker container | DXF/SVG generation from STEP files (planned) |

---

## FastAPI Backend

### Application Entry Point

**File:** `backend/app/main.py`

The FastAPI app registers all route modules under the `/api` prefix and configures CORS middleware. In production, it also serves the built Vue frontend as static files.

**Interactive API docs** are available at `/docs` (Swagger UI) and `/redoc` (ReDoc) when the server is running.

### Configuration

**File:** `backend/app/config.py`

Settings are loaded from environment variables (with `.env` file support via Pydantic Settings).

| Variable | Default | Description |
|----------|---------|-------------|
| `SUPABASE_URL` | (project URL) | Supabase project URL |
| `SUPABASE_ANON_KEY` | `""` | Supabase anonymous/public key |
| `SUPABASE_SERVICE_KEY` | `""` | Supabase service role key (admin operations) |
| `API_HOST` | `0.0.0.0` | Server bind address |
| `API_PORT` | `8080` | Server port (8080 for production, 8000 for local dev) |
| `DEBUG` | `false` | Enable debug mode and auto-reload |
| `CORS_ALLOW_ALL` | `false` | Allow all CORS origins (set `true` for development) |

### Supabase Clients

**File:** `backend/app/services/supabase.py`

Two cached Supabase clients are available:

- **`get_supabase_client()`** -- Uses the anonymous key. Respects Row Level Security (RLS) policies. Used for standard user-facing queries.
- **`get_supabase_admin()`** -- Uses the service role key. Bypasses RLS. Used for trusted internal operations such as file uploads from the bridge service and bulk BOM imports.

---

## API Endpoints

All endpoints are prefixed with `/api`. Responses use JSON format unless otherwise noted.

### Health Check

```
GET /health
```

Returns server health status. Not prefixed with `/api`.

**Response:**
```json
{
  "status": "healthy"
}
```

---

### Authentication (`/api/auth`)

**File:** `backend/app/routes/auth.py`

#### POST /api/auth/login

Login with email and password via Supabase Auth.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `email` | string | Yes | User email address |
| `password` | string | Yes | User password |

**Example (curl):**
```bash
curl -X POST "http://localhost:8000/api/auth/login?email=jack@example.com&password=secret"
```

**Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "v1.abc123...",
  "user": {
    "id": "a1b2c3d4-...",
    "email": "jack@example.com"
  }
}
```

**Response (401):** Login failed.

#### GET /api/auth/me

Get the current authenticated user profile. Requires a valid JWT in the `Authorization` header.

If the authenticated Supabase Auth user does not yet have a record in the `users` table, one is created automatically (with role `viewer`). If a user record exists by email but lacks the `auth_id` link, the link is established on first call.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response (200):**
```json
{
  "id": "uuid",
  "auth_id": "uuid",
  "username": "jack",
  "email": "jack@example.com",
  "role": "engineer",
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "2025-01-01T00:00:00Z"
}
```

#### POST /api/auth/logout

Sign out the current user session.

**Headers:**
```
Authorization: Bearer <access_token>
```

#### GET /api/auth/users

List all users in the system.

**Response (200):** Array of user objects ordered by username.

---

### Items (`/api/items`)

**File:** `backend/app/routes/items.py`

Items are the core data objects representing parts, assemblies, and purchased components. Each item has a unique `item_number` following the pattern `abc####` (3 lowercase letters + 4-6 digits).

#### GET /api/items

List items with optional filtering and pagination.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `q` | string | No | Search term (matches item_number and name, case-insensitive) |
| `lifecycle_state` | string | No | Filter by state: `Design`, `Released`, `Obsolete` |
| `project_id` | UUID | No | Filter by project |
| `is_supplier_part` | boolean | No | Filter supplier vs. in-house parts |
| `limit` | integer | No | Max results (default 50, max 1000) |
| `offset` | integer | No | Pagination offset (default 0) |

**Example (curl):**
```bash
curl "http://localhost:8000/api/items?q=csp&lifecycle_state=Design&limit=20"
```

**Example (Python):**
```python
import requests

response = requests.get("http://localhost:8000/api/items", params={
    "q": "csp",
    "lifecycle_state": "Design",
    "limit": 20
})
items = response.json()
```

**Response (200):** Array of item objects with joined `project_name`.

#### GET /api/items/{item_number}

Get a single item by item number, including associated file records.

**Example:**
```bash
curl "http://localhost:8000/api/items/csp0030"
```

**Response (200):**
```json
{
  "id": "uuid",
  "item_number": "csp0030",
  "name": "Bracket",
  "revision": "A",
  "iteration": 1,
  "lifecycle_state": "Design",
  "description": null,
  "project_id": "uuid",
  "project_name": "Project Alpha",
  "material": "Steel",
  "mass": 2.5,
  "thickness": 3.0,
  "cut_length": 500.0,
  "cut_time": null,
  "price_est": null,
  "is_supplier_part": false,
  "supplier_name": null,
  "supplier_pn": null,
  "unit_price": null,
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "2025-01-15T10:30:00Z",
  "files": [
    {
      "id": "uuid",
      "item_id": "uuid",
      "file_type": "STEP",
      "file_name": "csp0030.step",
      "file_path": "pdm-files/csp0030/csp0030.step",
      "file_size": 123456,
      "revision": "A",
      "iteration": 1,
      "uploaded_by": null,
      "created_at": "2025-01-01T00:00:00Z"
    }
  ]
}
```

**Response (404):** Item not found.

#### POST /api/items

Create a new item.

**Request Body (JSON):**
```json
{
  "item_number": "csp0050",
  "name": "New Bracket",
  "revision": "A",
  "iteration": 1,
  "lifecycle_state": "Design",
  "material": "Aluminum",
  "mass": 1.2
}
```

Required field: `item_number` (must match pattern `^[a-z]{3}\d{4,6}$`).

**Response (200):** Created item object.
**Response (409):** Item already exists (duplicate `item_number`).

#### PATCH /api/items/{item_number}

Update item fields. Only provided fields are modified; omitted fields are unchanged.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `upsert` | boolean | No | If `true`, create the item when it does not exist (default `false`) |

When `upsert=true`, the admin client is used (bypasses RLS). If the item does not exist, it is created with sensible defaults: revision `A`, iteration `1`, lifecycle state `Design`. Items with `mmc` or `spn` prefixes are automatically marked as supplier parts.

**Example (curl):**
```bash
curl -X PATCH "http://localhost:8000/api/items/csp0030" \
  -H "Content-Type: application/json" \
  -d '{"material": "Stainless Steel", "mass": 3.1}'
```

**Example (upsert from upload bridge):**
```bash
curl -X PATCH "http://localhost:8000/api/items/wmp20080?upsert=true" \
  -H "Content-Type: application/json" \
  -d '{"name": "Shaft", "material": "Aluminum", "thickness": 2.5}'
```

**Response (200):** Updated or created item object.
**Response (404):** Item not found (when `upsert=false`).

#### DELETE /api/items/{item_number}

Delete an item.

**Response (200):** `{"message": "Item csp0030 deleted"}`

#### GET /api/items/{item_number}/history

Get lifecycle history entries for an item, ordered newest first.

**Response (200):** Array of lifecycle history records with `old_state`, `new_state`, `old_revision`, `new_revision`, `changed_by`, `changed_at`, etc.

---

### Files (`/api/files`)

**File:** `backend/app/routes/files.py`

Files are stored in the Supabase Storage `pdm-files` bucket, organized by item number (e.g., `pdm-files/csp0030/csp0030.step`). Metadata is tracked in the `files` database table.

**File type classification** is automatic based on extension:

| Extension | Type |
|-----------|------|
| `.stp`, `.step` | STEP |
| `.prt`, `.asm`, `.drw` | CAD |
| `.dxf` | DXF |
| `.svg` | SVG |
| `.pdf` | PDF |
| `.png`, `.jpg`, `.jpeg` | IMAGE |
| Other | OTHER |

#### GET /api/files

List file records with optional filtering.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `item_id` | UUID | No | Filter by item |
| `file_type` | string | No | Filter by type (STEP, CAD, DXF, SVG, PDF, IMAGE, OTHER) |
| `limit` | integer | No | Max results (default 50) |
| `offset` | integer | No | Pagination offset |

#### GET /api/files/{file_id}

Get file metadata by database ID.

#### POST /api/files/upload

Upload a file and associate it with an item. Uses multipart form data. The admin client is used to bypass RLS for trusted upload operations.

If the item already has a file with the same filename, the existing record is updated (iteration incremented, storage file overwritten). Otherwise, a new file record is created.

**Auto-create items:** If the specified `item_number` does not exist in the database, the endpoint will automatically create the item provided the item number matches one of the recognized naming conventions:
- Standard: `[a-z]{3}\d{4,6}` (e.g., `csp0030`)
- McMaster: `mmc\d+[a-z]*\d*` (e.g., `mmc12555k88`)
- Supplier: `spn\d+[a-z]*\d*` (e.g., `spn40021`)
- Reference: `zzz\d+[a-z]*\d*` (e.g., `zzz0001`)

Items with `mmc` or `spn` prefixes are automatically marked as supplier parts (`is_supplier_part = true`). The item number is extracted from the filename using prefix-first regex ordering (mmc/spn/zzz checked before the standard pattern to avoid truncation).

**Form Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | Yes | The file to upload |
| `item_number` | string | Yes | Item number to associate with |
| `revision` | string | No | Override revision (defaults to item's current revision) |

**Example (curl):**
```bash
curl -X POST "http://localhost:8001/api/files/upload" \
  -F "file=@csp0030.step" \
  -F "item_number=csp0030"
```

**Example (Python):**
```python
import requests

with open("csp0030.step", "rb") as f:
    response = requests.post(
        "http://localhost:8001/api/files/upload",
        files={"file": ("csp0030.step", f, "application/step")},
        data={"item_number": "csp0030"}
    )
print(response.json())
```

**Response (200):** File record object (includes `updated_at` timestamp).
**Response (404):** Item not found and item number does not match any recognized naming convention.

#### GET /api/files/{file_id}/download

Get a signed download URL for a file. The URL is valid for 1 hour (3600 seconds).

**Example (curl):**
```bash
curl "http://localhost:8000/api/files/<file-uuid>/download"
```

**Response (200):**
```json
{
  "url": "https://lnytnxmmemdzwqburtgf.supabase.co/storage/v1/object/sign/pdm-files/...",
  "filename": "csp0030.step",
  "expires_in": 3600
}
```

#### DELETE /api/files/{file_id}

Delete a file record and its corresponding storage object.

---

### BOM (`/api/bom`)

**File:** `backend/app/routes/bom.py`

Bill of Materials management. Supports single-level queries, recursive tree traversal, where-used lookups, and bulk upload/replace operations.

#### GET /api/bom/{item_number}

Get single-level BOM for an item (direct children only). Returns raw BOM entry records with UUIDs.

**Response (200):** Array of BOM entry objects.

#### GET /api/bom/{item_number}/tree

Get full recursive BOM tree. Returns a nested structure with item details at each level.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `max_depth` | integer | No | Maximum recursion depth (default 10) |

**Example (curl):**
```bash
curl "http://localhost:8000/api/bom/wma20120/tree?max_depth=5"
```

**Response (200):**
```json
{
  "item": { "item_number": "wma20120", "name": "Main Assembly", ... },
  "quantity": 1,
  "children": [
    {
      "item": { "item_number": "wmp20080", "name": "Bracket", ... },
      "quantity": 2,
      "children": []
    },
    {
      "item": { "item_number": "wmp20090", "name": "Shaft", ... },
      "quantity": 1,
      "children": []
    }
  ]
}
```

#### GET /api/bom/{item_number}/where-used

Get parent assemblies that contain this item (reverse BOM lookup).

**Response (200):** Array of `{ "item": {...}, "quantity": N }` objects.

#### POST /api/bom

Add a single BOM relationship using item UUIDs.

**Request Body (JSON):**
```json
{
  "parent_item_id": "uuid",
  "child_item_id": "uuid",
  "quantity": 2,
  "source_file": "bom.txt"
}
```

**Response (409):** Duplicate relationship.

#### POST /api/bom/bulk

Bulk upload BOM -- replaces the entire BOM for an assembly. This is the primary endpoint used by the upload bridge when processing Creo BOM exports.

This endpoint uses the admin client (bypasses RLS) and performs the following operations atomically:

1. Creates the parent assembly item if it does not exist.
2. Deletes all existing BOM entries for the parent.
3. For each child: creates or updates the child item record with properties (material, mass, thickness, etc.).
4. Creates new BOM entries linking parent to children.
5. Skips `zzz`-prefixed reference items.
6. Auto-detects supplier parts (`mmc`/`spn` prefixes).

**Request Body (JSON):**
```json
{
  "parent_item_number": "wma20120",
  "children": [
    {
      "item_number": "wmp20080",
      "quantity": 2,
      "name": "Bracket",
      "material": "Steel",
      "mass": 2.5,
      "thickness": 3.0,
      "cut_length": 500.0,
      "cut_time": null,
      "price_est": null
    },
    {
      "item_number": "wmp20090",
      "quantity": 1,
      "name": "Shaft",
      "material": "Aluminum",
      "mass": 1.2
    }
  ],
  "source_file": "bom.txt"
}
```

**Response (200):**
```json
{
  "parent_item_number": "wma20120",
  "parent_item_id": "uuid",
  "items_created": 2,
  "items_updated": 0,
  "bom_entries_created": 2,
  "children": ["wmp20080", "wmp20090"]
}
```

#### PATCH /api/bom/{bom_id}

Update the quantity on an existing BOM entry.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `quantity` | integer | Yes | New quantity |

#### DELETE /api/bom/{bom_id}

Delete a single BOM relationship.

---

### Projects (`/api/projects`)

**File:** `backend/app/routes/projects.py`

Projects group related items together for organizational purposes.

#### GET /api/projects

List projects with optional status filter and pagination.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `status` | string | No | Filter by status (e.g., `active`) |
| `limit` | integer | No | Max results (default 50, max 100) |
| `offset` | integer | No | Pagination offset |

#### GET /api/projects/{project_id}

Get a single project by ID.

#### GET /api/projects/{project_id}/items

Get all items belonging to a project.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | No | Max results (default 100) |
| `offset` | integer | No | Pagination offset |

#### POST /api/projects

Create a new project.

**Request Body (JSON):**
```json
{
  "name": "Project Alpha",
  "description": "Main product assembly",
  "status": "active"
}
```

#### PATCH /api/projects/{project_id}

Update project fields.

#### DELETE /api/projects/{project_id}

Delete a project. Items belonging to the project will have their `project_id` set to null.

---

### Tasks / Work Queue (`/api/tasks`)

**File:** `backend/app/routes/tasks.py`

The work queue manages asynchronous processing tasks such as DXF and SVG generation from STEP files. Tasks are created by the API and polled/executed by worker processes.

**Task statuses:** `pending`, `processing`, `completed`, `failed`

**Task types:** `GENERATE_DXF`, `GENERATE_SVG`

#### GET /api/tasks

List tasks with optional filtering.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `status` | string | No | Filter by status |
| `task_type` | string | No | Filter by type |
| `item_id` | UUID | No | Filter by item |
| `limit` | integer | No | Max results (default 50, max 100) |
| `offset` | integer | No | Pagination offset |

#### GET /api/tasks/pending

Get pending tasks for worker processing. Returns oldest tasks first.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_type` | string | No | Filter by type |
| `limit` | integer | No | Max results (default 10) |

#### GET /api/tasks/{task_id}

Get a single task by ID.

#### POST /api/tasks

Create a task manually.

**Request Body (JSON):**
```json
{
  "item_id": "uuid",
  "file_id": "uuid",
  "task_type": "GENERATE_DXF",
  "payload": {"file_path": "pdm-files/csp0030/csp0030.step"}
}
```

#### POST /api/tasks/generate-dxf/{item_number}

Queue DXF flat pattern generation for an item. Automatically finds the item's latest STEP file.

**Example:**
```bash
curl -X POST "http://localhost:8000/api/tasks/generate-dxf/csp0030"
```

**Response (404):** Item not found, or no STEP file found for item.

#### POST /api/tasks/generate-svg/{item_number}

Queue SVG bend drawing generation for an item. Automatically finds the item's latest STEP file.

#### PATCH /api/tasks/{task_id}/start

Mark a task as processing (used by worker). Only transitions tasks with `pending` status.

#### PATCH /api/tasks/{task_id}/complete

Mark a task as completed or failed.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `error_message` | string | No | If provided, task status is set to `failed` |

#### DELETE /api/tasks/{task_id}

Delete a task record.

---

### MRP (`/api/mrp`)

**File:** `backend/app/routes/mrp.py`

Manufacturing Resource Planning endpoints for print packet generation.

#### POST /api/mrp/projects/{project_id}/print-packet

Generate a new print packet PDF for a project. The packet includes a cover sheet with categorized parts lists and individual part PDFs with routing stamp overlays.

**Response (200):** Download URL, storage path, and generation timestamp.

#### GET /api/mrp/projects/{project_id}/print-packet

Get the existing print packet for a project, if one has been generated.

**Response (404):** No packet exists.

---

### Nesting (`/api/nesting`)

**File:** `backend/app/routes/nesting.py`

DXF nesting endpoints for project-scoped sheet metal flat pattern nesting. Nesting jobs are linked to MRP projects and parts are automatically grouped by material and thickness.

#### GET /api/nesting/projects/{project_id}/groups

Get parts grouped by material and thickness for nesting. Analyzes the MRP project's BOM to find all sheet metal parts with DXF flat patterns.

**Response (200):**
```json
[
  {
    "material": "STEEL_HSLA",
    "thickness": 3.0,
    "parts": [
      {
        "item_id": "uuid",
        "item_number": "csp0030",
        "name": "Bracket",
        "dxf_path": "pdm-files/csp0030/csp0030_flat.dxf",
        "quantity": 4
      }
    ]
  }
]
```

#### POST /api/nesting/projects/{project_id}/nest

Create a new nesting job and queue it for processing.

**Request Body (JSON):**
```json
{
  "material": "STEEL_HSLA",
  "thickness": 3.0,
  "item_ids": ["uuid1", "uuid2"],
  "sheet_width": 1220.0,
  "sheet_height": 2440.0,
  "spacing": 5.0,
  "allow_rotation": true
}
```

**Response (200):** Created nest job with status `pending`.

#### GET /api/nesting/jobs/{job_id}

Get nesting job details including items, results, and status.

**Response (200):**
```json
{
  "id": "uuid",
  "project_id": "uuid",
  "material": "STEEL_HSLA",
  "thickness": 3.0,
  "sheet_width": 1220.0,
  "sheet_height": 2440.0,
  "spacing": 5.0,
  "allow_rotation": true,
  "status": "completed",
  "utilization_pct": 78.5,
  "total_sheets": 2,
  "created_at": "2026-01-30T10:00:00Z",
  "completed_at": "2026-01-30T10:05:00Z",
  "items": [
    {"item_id": "uuid", "item_number": "csp0030", "quantity": 4, "dxf_path": "..."}
  ],
  "results": [
    {
      "sheet_index": 1,
      "dxf_path": "pdm-files/projects/WMA2025/nests/job-uuid/sheet_01.dxf",
      "utilization_pct": 82.3,
      "placement_count": 5
    }
  ]
}
```

#### GET /api/nesting/projects/{project_id}/jobs

List all nesting jobs for a project, ordered newest first.

**Response (200):** Array of nest job summary objects.

#### GET /api/nesting/jobs/{job_id}/sheets/{sheet_index}/download

Get a signed download URL for a nested output sheet DXF.

**Example:**
```bash
curl "http://localhost:8000/api/nesting/jobs/<job-uuid>/sheets/1/download"
```

**Response (200):**
```json
{
  "url": "https://...supabase.co/storage/v1/object/sign/pdm-files/...",
  "filename": "sheet_01.dxf",
  "expires_in": 3600
}
```

**Response (404):** Sheet not found or job not completed.

---

### Workspace Comparison (`/api/workspace`)

**File:** `backend/app/routes/workspace.py`

Compares local Creo workspace files against the Supabase vault to determine which files are in sync, out of date, or not yet checked in. Uses `get_supabase_admin()` to bypass RLS since this is an internal service endpoint called from Creo's embedded browser (no user JWT).

**IMPORTANT:** All vault timestamps are converted from UTC to local time before comparison and display, since PowerShell reports local file times. See lesson #11 in Dev Notes.

#### POST /api/workspace/compare

Compare a list of local files against the vault.

**Request Body (JSON):**
```json
{
  "files": [
    {
      "filename": "csp0030.prt",
      "timestamp": "1/29/2026, 2:30:15 PM"
    },
    {
      "filename": "wma20120.asm",
      "timestamp": "1/28/2026, 10:15:00 AM"
    }
  ]
}
```

**Response (200):**
```json
{
  "results": [
    {
      "filename": "csp0030.prt",
      "item_number": "csp0030",
      "status": "Current",
      "local_time": "1/29/2026, 2:30:15 PM",
      "vault_time": "1/29/2026, 2:30:15 PM"
    },
    {
      "filename": "wma20120.asm",
      "item_number": "wma20120",
      "status": "Out of Date",
      "local_time": "1/28/2026, 10:15:00 AM",
      "vault_time": "1/29/2026, 3:45:00 PM"
    }
  ]
}
```

**Status values:**
- `Current` -- Local file timestamp matches vault timestamp.
- `Out of Date` -- Vault has a newer version than the local file.
- `Not In Vault` -- No matching item or file record exists in the vault.

**Architecture notes:**
- Item numbers are extracted from filenames using prefix-first regex ordering (mmc/spn/zzz before standard pattern).
- Suffixes (`_prt`, `_asm`, `_drw`, `_flat`) are stripped before item number extraction.
- Admin client is required because the endpoint runs without user authentication (Creo's embedded browser does not send JWTs).

---

### PDM-Local-Service (localhost:8083)

**File:** `Local_Creo_Files/Powershell/PDM-Local-Service.ps1`

A PowerShell HTTP server running on `localhost:8083` that provides local file system access for Creo's embedded browser. Creo's browser cannot access local files directly, so this service bridges the gap.

**Why a local service is needed:** Creo's embedded Chromium browser runs in a sandbox that prevents direct file system access. JavaScript in workspace.html cannot read local file timestamps, upload files, or download files without a local HTTP bridge.

#### GET /health

Health check endpoint.

**Response (200):**
```json
{
  "status": "running",
  "service": "PDM-Local-Service"
}
```

#### POST /api/file-timestamps

Get `LastWriteTime` timestamps for a list of local files. Used by workspace comparison to get local file modification times.

**Request Body (JSON):**
```json
{
  "directory": "C:\\Users\\Jack\\Creo\\Workspace",
  "files": ["csp0030.prt", "wma20120.asm"]
}
```

**Response (200):**
```json
{
  "timestamps": {
    "csp0030.prt": "1/29/2026 2:30:15 PM",
    "wma20120.asm": "1/28/2026 10:15:00 AM"
  }
}
```

#### POST /api/checkin

Upload a local file to the FastAPI backend (which stores it in Supabase Storage). After successful upload, the service touches the local file's `LastWriteTime` to the current time so it stays in sync with the vault.

**Request Body (JSON):**
```json
{
  "filePath": "C:\\Users\\Jack\\Creo\\Workspace\\csp0030.prt",
  "itemNumber": "csp0030"
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "File uploaded successfully"
}
```

**IMPORTANT:** After successful upload, the service updates the local file's `LastWriteTime` to `Get-Date` to prevent the "Out of Date" false positive (see lesson #13 in Dev Notes).

#### POST /api/download

Download a file from the vault (via FastAPI signed URL) to a local directory.

**Request Body (JSON):**
```json
{
  "itemNumber": "csp0030",
  "fileName": "csp0030.prt",
  "targetDirectory": "C:\\Users\\Jack\\Creo\\Workspace"
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "File downloaded to C:\\Users\\Jack\\Creo\\Workspace\\csp0030.prt"
}
```

#### Configuration

The service is started manually in a PowerShell window:

```powershell
cd Local_Creo_Files\Powershell
.\PDM-Local-Service.ps1
```

**Default port:** 8083 (hardcoded in the script).

**Note:** The legacy `Local-FileTimestamp-Service.ps1` has been deleted. All functionality is now in `PDM-Local-Service.ps1`.

---

## Pydantic Schemas

**File:** `backend/app/models/schemas.py`

### Item Schemas

**ItemBase** -- Core item fields:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `item_number` | string | (required) | Must match `^[a-z]{3}\d{4,6}$` |
| `name` | string | null | Display name / description |
| `revision` | string | `"A"` | Revision letter |
| `iteration` | integer | `1` | Iteration within revision |
| `lifecycle_state` | string | `"Design"` | `Design`, `Released`, or `Obsolete` |
| `description` | string | null | Extended description |
| `project_id` | UUID | null | Associated project |
| `material` | string | null | Material specification |
| `mass` | float | null | Part mass |
| `thickness` | float | null | Sheet metal thickness |
| `cut_length` | float | null | Cut length for flat patterns |
| `cut_time` | float | null | Estimated cut time |
| `price_est` | float | null | Estimated price |
| `is_supplier_part` | boolean | `false` | Purchased vs. manufactured |
| `supplier_name` | string | null | Supplier company name |
| `supplier_pn` | string | null | Supplier part number |
| `unit_price` | float | null | Purchase unit price |

**ItemCreate(ItemBase)** -- Same fields, used for POST.

**ItemUpdate** -- All fields optional, used for PATCH.

**Item(ItemBase)** -- Full item with `id`, `project_name`, `created_at`, `updated_at`.

**ItemWithFiles(Item)** -- Item with embedded `files` array.

### BOM Schemas

**BOMChildItem** -- Child item data in bulk BOM upload:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `item_number` | string | (required) | Child item number |
| `quantity` | integer | `1` | Quantity in assembly |
| `name` | string | null | Part name |
| `material` | string | null | Material |
| `mass` | float | null | Mass |
| `thickness` | float | null | Sheet metal thickness |
| `cut_length` | float | null | Cut length |
| `cut_time` | float | null | Cut time |
| `price_est` | float | null | Estimated price |

**BOMBulkCreate** -- Bulk BOM upload request:

| Field | Type | Description |
|-------|------|-------------|
| `parent_item_number` | string | Parent assembly item number |
| `children` | list[BOMChildItem] | Array of child items |
| `source_file` | string (optional) | Source file name for tracking |

**BOMBulkResponse** -- Response from bulk upload with counts of items created/updated and BOM entries created.

### Task Schemas

**Task** -- Work queue entry:

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Task ID |
| `item_id` | UUID (optional) | Related item |
| `file_id` | UUID (optional) | Related file |
| `task_type` | string | Task type (e.g., `GENERATE_DXF`) |
| `status` | string | `pending`, `processing`, `completed`, `failed` |
| `payload` | dict (optional) | Task-specific data |
| `error_message` | string (optional) | Error details if failed |
| `created_at` | datetime | Creation timestamp |
| `started_at` | datetime (optional) | Processing start time |
| `completed_at` | datetime (optional) | Completion time |

---

## Supabase Services

### Database (PostgreSQL)

All database access goes through the `supabase-py` client. The backend does not use an ORM; it uses the Supabase client's builder pattern for queries:

```python
# Query example
result = supabase.table("items").select("*").eq("lifecycle_state", "Design").order("item_number").execute()

# Insert example
result = supabase.table("items").insert({"item_number": "csp0050", "name": "Bracket"}).execute()

# Update example
result = supabase.table("items").update({"material": "Steel"}).eq("item_number", "csp0030").execute()
```

### Authentication

Supabase Auth provides email/password authentication. The backend validates JWT tokens and manages user records:

- **Login:** Calls `supabase.auth.sign_in_with_password()` and returns access + refresh tokens.
- **Token validation:** Calls `supabase.auth.get_user(token)` to verify JWT and retrieve the auth user.
- **User linking:** On first login, the backend links the Supabase Auth user to the `users` table record (by email match or new creation).

### Storage

Files are stored in the `pdm-files` Supabase Storage bucket. The storage path convention is:

```
pdm-files/{item_number}/{filename}
```

For example: `pdm-files/csp0030/csp0030.step`

**Operations used:**
- `storage.from_("pdm-files").upload(path, content, file_options)` -- Upload new file
- `storage.from_("pdm-files").update(path, content, file_options)` -- Overwrite existing file
- `storage.from_("pdm-files").create_signed_url(path, expires_in)` -- Generate download URL
- `storage.from_("pdm-files").remove([path])` -- Delete file

---

## Production Deployment

The application deploys to Fly.io as a single Docker container that includes both the FastAPI backend and the built Vue frontend (served as static files).

**Dockerfile:** Multi-stage build:
1. **Stage 1 (Node.js):** Builds the Vue frontend with `vite build`.
2. **Stage 2 (Python):** Installs backend dependencies, copies backend code, copies built frontend to `static/` directory.

**Deploy command:**
```bash
.\deploy.ps1
```

The deploy script reads Supabase credentials from `backend/.env` and passes them as build arguments to `flyctl deploy`.

**Production port:** 8080 (configured in Dockerfile CMD and Fly.io).

---

## Error Handling

All API endpoints return standard HTTP status codes:

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad request (validation error, no fields to update) |
| 401 | Not authenticated / invalid token |
| 404 | Resource not found |
| 409 | Conflict (duplicate item_number, duplicate BOM entry) |
| 500 | Server error (storage failure, etc.) |

Error responses follow the format:
```json
{
  "detail": "Description of the error"
}
```

---

**Last Updated:** 2026-01-30

