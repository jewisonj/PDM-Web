# System Capabilities Reference

PDM-Web is a web-based Product Data Management system for managing CAD files, Bills of Materials, lifecycle tracking, and manufacturing document generation. This document describes the system's capabilities organized by functional area.

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend | Vue 3 + Vite + Pinia + PrimeVue |
| Backend | FastAPI (Python) |
| Database | Supabase PostgreSQL |
| Authentication | Supabase Auth (JWT) |
| File Storage | Supabase Storage |
| CAD Processing | FreeCAD Docker container (`amrit3701/freecad-cli:latest`) |
| Upload Bridge | PowerShell scripts (`scripts/pdm-upload/`) |

---

## Item Management

Items are the core entity in the PDM system. Each item represents a part, assembly, or purchased component.

### Capabilities

- **Create items** with item number, name, description, revision, lifecycle state, project assignment, and material properties
- **Edit items** including all metadata fields: material, mass, thickness, cut length, cut time, price estimate, supplier info
- **Delete items** and cascade removal of associated records
- **Search and filter** by item number, name, lifecycle state, project, and supplier status
- **Sort items** by any column in the items table (item number, description, project, revision, state, material, date, mass)
- **Upsert items** -- create or update in a single operation (used by the upload bridge for bulk data import)
- **Supplier parts** -- items with `mmc` or `spn` prefixes are automatically flagged as supplier parts with optional supplier name and part number fields

### Item Numbering

- Format: 3 lowercase letters + 4-6 digits (e.g., `csp0030`, `wma20120`)
- Normalized to lowercase on creation
- Special prefixes: `mmc` (McMaster-Carr), `spn` (supplier), `zzz` (reference/excluded)
- Part Number Generator view shows next available numbers for each prefix

### Lifecycle States

Items progress through defined lifecycle states:

| State | Description |
|---|---|
| Design | Active engineering work |
| Review | Pending approval |
| Released | Approved for production |
| Obsolete | No longer active |

Lifecycle transitions are tracked in the `lifecycle_history` table with timestamps and user attribution.

### API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/items` | List items with optional search, filter, pagination |
| GET | `/api/items/{item_number}` | Get item with associated files |
| POST | `/api/items` | Create a new item |
| PATCH | `/api/items/{item_number}` | Update item (supports `?upsert=true`) |
| DELETE | `/api/items/{item_number}` | Delete an item |
| GET | `/api/items/{item_number}/history` | Get lifecycle history |

### Frontend Views

- **PDM Browser** (`/pdm-browser`) -- Full item table with search, filter, sort, and detail panel
- **Item Detail** (`/items/{itemNumber}`) -- Dedicated detail page with files, BOM, where-used
- **Part Number Generator** (`/part-numbers`) -- Shows next available numbers per prefix

---

## File Management

Files are associated with items and stored in Supabase Storage. The system tracks file metadata in the database and serves files via signed URLs.

### Capabilities

- **Upload files** via web UI or the PDM Upload Service (PowerShell bridge)
- **Download files** through time-limited signed URLs (1-hour expiry)
- **Preview files** in the browser -- PDFs, images (PNG, JPG), and SVGs open in new tabs
- **Track file metadata** including type, size, revision, iteration, and upload timestamp
- **Automatic iteration bumping** -- re-uploading a file with the same name increments the iteration counter
- **File type classification** -- automatic detection from extension (STEP, DXF, SVG, PDF, CAD, IMAGE, OTHER)

### Supported File Types

| Extension | Type Classification | Description |
|---|---|---|
| `.stp`, `.step` | STEP | 3D model interchange format |
| `.prt`, `.asm`, `.drw` | CAD | Creo Parametric native files |
| `.dxf` | DXF | 2D flat patterns for manufacturing |
| `.svg` | SVG | Technical drawings |
| `.pdf` | PDF | Documentation |
| `.png`, `.jpg`, `.jpeg` | IMAGE | Images |

### Storage Architecture

- **Bucket:** `pdm-files` in Supabase Storage
- **Path format:** `{item_number}/{filename}` (e.g., `csp0030/csp0030.step`)
- **Access:** Signed URLs generated server-side for authorized download

### API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/files` | List files with optional filtering by item or type |
| GET | `/api/files/{file_id}` | Get file metadata |
| POST | `/api/files/upload` | Upload file (multipart form: file + item_number) |
| GET | `/api/files/{file_id}/download` | Get signed download URL |
| DELETE | `/api/files/{file_id}` | Delete file from storage and database |

---

## BOM Management

Bill of Materials (BOM) tracks parent-child relationships between assemblies and their component parts.

### Capabilities

- **Single-level BOM** -- view direct children of an assembly
- **Multi-level BOM tree** -- recursive tree with configurable depth (default: 10 levels)
- **Where-used queries** -- find all assemblies that contain a given part
- **Bulk BOM upload** -- replace an entire assembly's BOM in one operation (used by the Creo BOM export pipeline)
- **Individual BOM entry management** -- add, update quantity, or delete individual parent-child relationships
- **Auto-create items** -- bulk BOM upload creates new item records for any child parts not yet in the system
- **Property sync** -- BOM upload updates child item properties (name, material, mass, thickness, cut length, price estimate)

### BOM Upload Pipeline

The BOM upload pipeline bridges Creo Parametric to the web system:

1. Export assembly tree from Creo as a fixed-width text file
2. Place `BOM.txt` or `MLBOM.txt` in the `C:\PDM-Upload` watch folder
3. `PDM-BOM-Parser.ps1` parses the file, extracting parent/child relationships and item properties
4. Parsed data is sent to `POST /api/bom/bulk` which replaces the assembly's BOM
5. New items are auto-created; existing items have their properties updated

### API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/bom/{item_number}` | Get single-level BOM (direct children) |
| GET | `/api/bom/{item_number}/tree` | Get recursive BOM tree |
| GET | `/api/bom/{item_number}/where-used` | Get parent assemblies |
| POST | `/api/bom` | Add a single BOM entry |
| POST | `/api/bom/bulk` | Bulk replace BOM for an assembly |
| PATCH | `/api/bom/{bom_id}` | Update BOM entry quantity |
| DELETE | `/api/bom/{bom_id}` | Delete a BOM entry |

### Frontend Views

- **PDM Browser detail panel** -- shows BOM children and where-used for selected item
- **Item Detail view** -- full BOM tree and where-used display

---

## Authentication

User authentication is handled by Supabase Auth with JWT tokens.

### Capabilities

- **Email/password login** via the Login view
- **JWT-based sessions** stored in the browser (Supabase client SDK)
- **Automatic token refresh** handled by the Supabase client library
- **User profile sync** -- on first login, the system creates or links a user record in the `users` table
- **Role-based display** -- user role shown in the UI (admin, engineer, viewer)
- **Route protection** -- all views except Login require authentication; unauthenticated requests redirect to Login

### User Roles

| Role | Description |
|---|---|
| admin | Full system access |
| engineer | Standard user for CAD and BOM work |
| viewer | Read-only access (shop floor, project managers) |

### API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/login` | Email/password login |
| POST | `/api/auth/logout` | Sign out |
| GET | `/api/auth/me` | Get current user profile (requires Bearer token) |
| GET | `/api/auth/users` | List all users |

---

## FreeCAD Automation

Headless FreeCAD runs inside a Docker container to generate manufacturing documents from STEP files.

### Capabilities

- **DXF flat pattern generation** -- unfold sheet metal STEP files into 2D cutting patterns
- **SVG bend drawing generation** -- create technical drawings with bend lines and dimensions
- **STL/OBJ conversion** -- convert STEP files to mesh formats
- **Work queue integration** -- tasks are queued via the API and processed by the Docker worker
- **Job runner** -- general-purpose dispatcher supports multiple job types

### Task Types

| Task | API Endpoint | Output |
|---|---|---|
| Generate DXF | `POST /api/tasks/generate-dxf/{item_number}` | DXF flat pattern |
| Generate SVG | `POST /api/tasks/generate-svg/{item_number}` | SVG bend drawing |

See [12-FREECAD-AUTOMATION.md](12-FREECAD-AUTOMATION.md) for full details on scripts, Docker configuration, and the processing pipeline.

---

## Work Queue / Task Management

Background tasks are tracked in the `work_queue` table and managed through the Tasks API.

### Capabilities

- **Create tasks** for any supported task type
- **Queue DXF/SVG generation** by item number (automatically finds the STEP file)
- **Track task status** -- pending, processing, completed, failed
- **Error tracking** -- failed tasks store error messages for debugging
- **Filter and browse** tasks by status, type, or item
- **Task lifecycle management** -- start, complete, and delete tasks via API

### API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/tasks` | List tasks with optional filters |
| GET | `/api/tasks/pending` | Get pending tasks for worker |
| GET | `/api/tasks/{task_id}` | Get task details |
| POST | `/api/tasks` | Create a generic task |
| POST | `/api/tasks/generate-dxf/{item_number}` | Queue DXF generation |
| POST | `/api/tasks/generate-svg/{item_number}` | Queue SVG generation |
| PATCH | `/api/tasks/{task_id}/start` | Mark task as processing |
| PATCH | `/api/tasks/{task_id}/complete` | Mark task as completed/failed |
| DELETE | `/api/tasks/{task_id}` | Delete a task |

### Frontend View

- **Work Queue** (`/tasks`) -- table of tasks with status indicators, error details, and filtering

---

## Project Management

Projects group related items together for organizational and tracking purposes.

### Capabilities

- **Create and manage projects** with name, description, and status
- **Associate items with projects** via the `project_id` field on items
- **Filter items by project** in the PDM Browser
- **View project overview** with associated item counts

### API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/projects` | List all projects |
| GET | `/api/projects/{id}` | Get project details |
| POST | `/api/projects` | Create a project |
| PATCH | `/api/projects/{id}` | Update a project |
| DELETE | `/api/projects/{id}` | Delete a project |

### Frontend View

- **Projects** (`/projects`) -- project listing with item associations

---

## MRP (Manufacturing Resource Planning)

MRP tools support production planning, shop floor operations, and materials management.

### Capabilities

- **MRP Dashboard** -- overview of production orders, work packets, and shop floor status
- **Routing Editor** -- define production routings with workstation assignments and operation sequencing
- **Shop Terminal** -- shop floor interface for operators to view assignments and update job status
- **Part Lookup** -- search parts by project, view routing operations, enter time, and mark complete; includes inline PDF drawing viewer
- **Project Tracking** -- Gantt chart visualization of project progress with part hierarchy
- **Raw Materials** -- inventory management with stock levels, reorder points, and inline editing
- **Print Packets** -- generate combined PDF packets with cover sheets and stamped part drawings

### API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/mrp/projects/{project_id}/print-packet` | Generate print packet PDF |
| GET | `/api/mrp/projects/{project_id}/print-packet` | Get existing print packet |

### Frontend Views

| Route | View | Description |
|---|---|---|
| `/mrp/dashboard` | MRP Dashboard | Production overview |
| `/mrp/routing` | Routing Editor | Production routing management |
| `/mrp/shop` | Shop Terminal | Operator work interface |
| `/mrp/parts` | Part Lookup | Part search with routing and time entry |
| `/mrp/tracking` | Project Tracking | Gantt chart progress view |
| `/mrp/materials` | Raw Materials | Inventory management |

---

## PDM Upload Bridge

The PDM Upload Service is a PowerShell-based bridge that runs on the local workstation to automatically upload files and data from Creo Parametric to the web API.

### Capabilities

- **Watch folder monitoring** -- monitors `C:\PDM-Upload` for new files using `FileSystemWatcher`
- **Automatic file upload** -- STEP, PDF, DXF, SVG, and CAD files are uploaded to the API with item number extraction from the filename
- **BOM parsing and upload** -- Creo tree export text files (`BOM.txt`, `MLBOM.txt`) are parsed and uploaded as bulk BOM data
- **Parameter sync** -- single-item parameter files (`param.txt`) update item properties via the API
- **Item number extraction** -- supports standard patterns (ABC####), McMaster (mmc...), and supplier (spn...) prefixes
- **Error handling** -- failed files are moved to a `Failed/` subfolder with error logging
- **Log rotation** -- automatic log file rotation when size exceeds 10MB

### Scripts

| Script | Purpose |
|---|---|
| `PDM-Upload-Service.ps1` | Main service -- watches folder and dispatches files |
| `PDM-Upload-Functions.ps1` | API client functions (upload file, upload BOM, update parameters) |
| `PDM-BOM-Parser.ps1` | Parses Creo fixed-width BOM text exports |
| `PDM-Upload-Config.ps1` | Configuration (API URL, watch folder, log settings) |
| `Start-PDMUpload.bat` | Batch launcher for the service |
| `Install-PDMUpload.ps1` | Installation helper |

### File Action Routing

| File | Action |
|---|---|
| `.step`, `.stp`, `.pdf`, `.dxf`, `.svg`, `.prt`, `.asm`, `.drw` | Upload to API as file |
| `BOM.txt` | Parse as single-level BOM, upload to `/api/bom/bulk` |
| `MLBOM.txt` | Parse as multi-level BOM, upload to `/api/bom/bulk` |
| `param.txt` | Parse as parameter file, update item via `/api/items/{item_number}?upsert=true` |

---

## Search and Filtering

### Capabilities

- **Text search** across item number, name, and description (case-insensitive)
- **Lifecycle state filter** -- filter by Design, Review, Released, or Obsolete
- **Project filter** -- filter by project assignment
- **Supplier part filter** -- filter by `is_supplier_part` flag
- **Client-side sorting** -- click column headers to sort ascending/descending
- **Pagination** -- server-side limit/offset support for large datasets
- **Item count display** -- shows filtered count vs. total count

---

## API Documentation

The FastAPI backend provides auto-generated interactive API documentation:

- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **Health check:** `GET /health`

All API routes are prefixed with `/api/` and organized by resource:

| Prefix | Tag | Description |
|---|---|---|
| `/api/auth` | auth | Authentication and user management |
| `/api/items` | items | Item CRUD and search |
| `/api/files` | files | File upload, download, metadata |
| `/api/bom` | bom | BOM relationships and tree queries |
| `/api/projects` | projects | Project management |
| `/api/tasks` | tasks | Work queue and task management |
| `/api/mrp` | mrp | Manufacturing resource planning |
