# PDM-Web System - Glossary of Terms

**Quick reference for PDM-Web terminology and technology stack**
**Related Docs:** [15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md](15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md), [27-WEB-MIGRATION-PLAN.md](27-WEB-MIGRATION-PLAN.md)

---

## Complete Glossary

### A

**Anon Key**
- Supabase public API key used for client-side operations
- Respects Row Level Security (RLS) policies
- Safe to expose in frontend code
- Configured via `SUPABASE_ANON_KEY` environment variable
- See also: Service Key, RLS

**APIRouter**
- FastAPI class for defining route groups
- Each module (items, files, bom) uses its own router with a prefix
- Registered in `main.py` via `app.include_router()`
- Example: `APIRouter(prefix="/items", tags=["items"])`

**Assembly**
- A product made up of multiple component parts
- Has children in the BOM (Bill of Materials)
- Example: `wma20120` (a motor assembly containing bearings, shafts, etc.)
- Opposite: Part

**Audit Trail**
- Complete record of all changes to an item
- Stored in `lifecycle_history` table in Supabase PostgreSQL
- Shows who changed what, when, and from/to what state
- Queried via `GET /api/items/{item_number}/history`

### B

**BaseModel**
- Pydantic base class for data validation and serialization
- All API request/response schemas inherit from `BaseModel`
- Provides automatic validation, JSON serialization, and OpenAPI schema generation
- See also: Pydantic

**BOM** (Bill of Materials)
- List of all parts and assemblies that make up a product
- Stored in `bom` table with `parent_item_id` and `child_item_id` foreign keys
- Single-level: Direct children only (`GET /api/bom/{item_number}`)
- Multi-level (tree): Full hierarchy (`GET /api/bom/{item_number}/tree`)
- Created from Creo BOM text file exports, uploaded via the BOM upload endpoint

**BOM Upload**
- Process of sending a parsed BOM file to the API
- Endpoint: `POST /api/bom/bulk`
- Accepts parent item number and list of children with quantities and properties
- Replaces the entire BOM for the parent assembly (delete-then-insert)
- Handled by `PDM-BOM-Parser.ps1` in the upload bridge

**Bucket**
- Supabase Storage container for files
- PDM uses the `pdm-files` bucket
- Files are organized by item number: `pdm-files/{item_number}/{filename}`
- See also: Signed URL, Supabase Storage

### C

**CAD** (Computer-Aided Design)
- Digital design files created in Creo or similar software
- PDM supports: `.prt` (part), `.asm` (assembly), `.drw` (drawing)
- Stored in Supabase Storage under the `pdm-files` bucket

**Checkout** (or Check-Out)
- Locks an item for editing to prevent concurrent modification
- Stored in `checkouts` table
- Row deleted when item is checked back in

**Circular Reference**
- When an item contains itself (directly or indirectly) in its BOM
- Causes infinite loops in tree traversal and cost calculations
- The BOM tree endpoint guards against this with a `max_depth` parameter
- Example: Assembly A contains Assembly B which contains Assembly A (invalid)

**Composition API**
- Vue 3 programming model used throughout the frontend
- Uses `setup()` function (or `<script setup>`) instead of Options API
- Provides `ref()`, `computed()`, `watch()`, `onMounted()` for reactive programming
- See also: Vue 3

**CORS** (Cross-Origin Resource Sharing)
- HTTP mechanism allowing the frontend (port 5173) to call the backend (port 8000)
- Configured in FastAPI middleware in `main.py`
- Development allows `localhost` origins; production is configurable via environment

**Computed Property**
- Vue 3 reactive value derived from other reactive state
- Created with `computed()` from the Composition API
- Automatically recalculates when dependencies change
- Example: `filteredItems` computed from `items` and `searchInput`

### D

**Design** (Lifecycle State)
- Initial state when an item is created
- Item is under active development and can be modified
- Transition: Design -> Released -> Obsolete

**DXF** (Drawing Exchange Format)
- 2D flat pattern file for sheet metal parts
- Generated from STEP files via FreeCAD Docker container
- Contains outline, holes, bend lines for manufacturing
- Classified as file type `DXF` in the files table

### E

**Endpoint**
- A specific URL path that the FastAPI backend responds to
- Examples: `GET /api/items`, `POST /api/files/upload`, `GET /api/bom/{item_number}/tree`
- Documented automatically at `/docs` (Swagger UI) and `/redoc`

**Environment Variables**
- Configuration values loaded from `.env` file or deployment platform
- Required: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`
- Optional: `API_HOST`, `API_PORT`, `DEBUG`, `CORS_ALLOW_ALL`
- Managed via Pydantic Settings in `backend/app/config.py`

### F

**FastAPI**
- Python web framework used for the backend API
- Provides automatic OpenAPI documentation, request validation via Pydantic, and async support
- Application entry point: `backend/app/main.py`
- Run with: `uvicorn app.main:app --reload`

**File Type**
- Classification of uploaded files in the `files` table
- Values: `CAD`, `STEP`, `DXF`, `SVG`, `PDF`, `IMAGE`, `OTHER`
- Determined automatically from file extension during upload

**FreeCAD**
- Open-source 3D CAD software used for DXF/SVG generation
- Runs headless in a Docker container (`amrit3701/freecad-cli:latest`)
- Custom scripts in `FreeCAD/Tools/` handle sheet metal flattening and bend drawings
- See also: SheetMetal Workbench, TechDraw Workbench

### G

**Gauge**
- Standard thickness measurement for sheet metal
- Noted on manufacturing documents (SVG bend drawings)
- Stored as `thickness` (numeric mm value) in the items table

### H

**HMR** (Hot Module Replacement)
- Vite development feature that updates the browser instantly when source files change
- No full page reload needed -- preserves application state during development
- Enabled by default with `npm run dev`
- See also: Vite

### I

**Item**
- Single product component or assembly in the PDM system
- Identified by item number (e.g., `csp0030`)
- Stored in `items` table in Supabase PostgreSQL
- Can have multiple associated files (STEP, DXF, SVG, PDF, CAD)
- Retrieved via `GET /api/items/{item_number}`

**Item Number**
- Unique identifier for a part or assembly
- Format: 3 lowercase letters + 4 to 6 digits
- Pattern: `[a-z]{3}\d{4,6}`
- Examples: `csp0030`, `wma20120`, `stp01000`
- Always normalized to lowercase throughout the system
- Special prefixes: `mmc` (McMaster-Carr), `spn` (supplier), `zzz` (reference only)

**Iteration**
- Version number within a revision
- Format: Revision.Iteration (e.g., A.1, A.2, B.1)
- Item iteration stored in `items.iteration`
- File iteration stored in `files.iteration` (increments on file re-upload)

### J

**JWT** (JSON Web Token)
- Authentication token issued by Supabase Auth on login
- Sent in the `Authorization: Bearer <token>` header for API requests
- Contains user identity and expiration time
- Frontend stores the session via Supabase client library
- See also: Supabase Auth

### K

**K-Factor**
- Bend compensation value for sheet metal flat pattern generation
- Accounts for material springback during bending
- Default: 0.35
- Configured in FreeCAD DXF generation scripts

### L

**Lifecycle History**
- Audit trail table (`lifecycle_history`) in Supabase PostgreSQL
- Records every state transition with old/new values
- Fields: `old_state`, `new_state`, `old_revision`, `new_revision`, `changed_by`, `changed_at`
- Queried via `GET /api/items/{item_number}/history`

**Lifecycle State**
- Current status of an item in the PDM workflow
- Values: `Design`, `Review`, `Released`, `Obsolete`
- Stored in `items.lifecycle_state`
- Displayed as color-coded badges in the frontend

### M

**MLBOM** (Multi-Level BOM)
- BOM with nested subassembly hierarchy showing all levels
- Retrieved via `GET /api/bom/{item_number}/tree`
- Rendered recursively in the frontend BOM tree view

**MRP** (Manufacturing Resource Planning)
- System for managing manufacturing operations
- PDM-Web includes MRP views: dashboard, routing, shop, parts lookup, tracking, materials
- API endpoints under `/api/mrp/`
- Frontend routes under `/mrp/`

### O

**Obsolete** (Lifecycle State)
- Final state for deprecated items no longer manufactured
- Kept for historical records and traceability
- Transition: Design -> Released -> Obsolete

**OpenAPI**
- API specification standard automatically generated by FastAPI
- Interactive documentation at `/docs` (Swagger UI)
- Alternative documentation at `/redoc` (ReDoc)
- Generated from route definitions and Pydantic models

### P

**Part** (vs Assembly)
- Single manufactured component with no children in BOM
- Examples: bolt, bearing, flat sheet metal piece
- Opposite: Assembly

**PDF**
- Portable Document Format used for documentation and specifications
- Classified as file type `PDF` in the files table
- Viewed via signed URLs from Supabase Storage

**Pinia**
- State management library for Vue 3
- Used for shared application state (items, auth, etc.)
- Stores defined in `frontend/src/stores/`
- Accessed in components via composable functions: `useItemsStore()`, `useAuthStore()`

**Pydantic**
- Python library for data validation and settings management
- All API schemas are Pydantic `BaseModel` subclasses
- Provides automatic JSON serialization, validation, and OpenAPI schema generation
- Settings loaded from environment via `pydantic_settings.BaseSettings`
- See also: BaseModel

### R

**Ref**
- Vue 3 Composition API function for creating reactive mutable state
- Created with `ref()`: `const searchInput = ref('')`
- Accessed with `.value` in script, directly in template
- See also: Composition API, Computed Property

**Released** (Lifecycle State)
- Item has been approved for production
- Represents a stable, locked version
- Transition: Design -> Released -> Obsolete

**Revision**
- Letter designation for major changes (A, B, C, etc.)
- Different from iteration (which tracks minor changes within a revision)
- Format: Revision.Iteration (e.g., A.2, B.1)
- Starts at `A` for new items

**RLS** (Row Level Security)
- Supabase/PostgreSQL feature that restricts data access based on user identity
- Policies defined at the database level control which rows users can read/write
- The anon client respects RLS; the service (admin) client bypasses it
- Important: Internal service endpoints must use the admin client to bypass RLS

**Router** (Vue Router)
- Client-side routing library for Vue 3 single-page applications
- Defines URL paths and their corresponding Vue components
- Configuration in `frontend/src/router/index.ts`
- Uses `createWebHistory()` for clean URLs (no hash)
- Navigation guards enforce authentication requirements

### S

**Service Key**
- Supabase secret API key with full database access
- Bypasses all Row Level Security policies
- Must never be exposed to frontend code or client-side JavaScript
- Used only in backend for trusted internal operations
- Configured via `SUPABASE_SERVICE_KEY` environment variable
- See also: Anon Key, RLS

**SheetMetal Workbench**
- FreeCAD module for sheet metal operations
- Handles unfolding 3D parts into 2D flat patterns
- Used in DXF generation via Docker container
- Generates cutting profiles for manufacturing

**Signed URL**
- Time-limited URL for accessing files in Supabase Storage
- Generated via `supabase.storage.from_(bucket).create_signed_url(path, expiry_seconds)`
- Default expiry: 3600 seconds (1 hour)
- Used for file downloads and PDF/image viewing in the frontend
- Endpoint: `GET /api/files/{file_id}/download`

**SPA** (Single-Page Application)
- Frontend architecture where Vue Router handles navigation without full page reloads
- FastAPI serves `index.html` for all non-API routes in production
- Catch-all route in `main.py` enables SPA routing

**STEP** (Standard for the Exchange of Product Data)
- 3D model file format (`.step`, `.stp`)
- Universal CAD interchange format containing geometry and metadata
- Source for DXF and SVG generation via FreeCAD
- Classified as file type `STEP` in the files table

**Supabase**
- Open-source Backend-as-a-Service platform built on PostgreSQL
- Provides: PostgreSQL database, authentication (JWT), file storage, and real-time subscriptions
- PDM-Web uses Supabase for all data persistence, auth, and file storage
- Project URL and keys configured via environment variables
- Dashboard available at `https://supabase.com/dashboard`

**Supabase Auth**
- Authentication service providing JWT-based login
- Supports email/password authentication
- Frontend uses `supabase.auth.signInWithPassword()` for login
- Session tokens managed automatically by the Supabase client library
- Login endpoint: `POST /api/auth/login`

**Supabase Storage**
- File storage service with bucket-based organization
- PDM uses the `pdm-files` bucket
- Files accessed via signed URLs (time-limited)
- Upload via `POST /api/files/upload` (multipart form data)

**SVG** (Scalable Vector Graphics)
- 2D vector drawing format used for technical/bend drawings
- Contains dimensions, annotations, bend lines, material callouts
- Generated from STEP files via FreeCAD TechDraw workbench
- Classified as file type `SVG` in the files table

### T

**Task** (Work Queue)
- Automated job queued for processing
- Types: `GENERATE_DXF`, `GENERATE_SVG`, `PARAM_SYNC`
- States: `pending`, `processing`, `completed`, `failed`
- Stored in `work_queue` table
- Viewed via `GET /api/tasks`

**TechDraw Workbench**
- FreeCAD module for creating technical drawings
- Generates 2D views from 3D models with dimensions and annotations
- Used for SVG bend drawing generation

### U

**Upload Bridge**
- PowerShell scripts in `scripts/pdm-upload/` that bridge local files to the web API
- `PDM-Upload-Service.ps1` -- Watches local folders and uploads files to the API
- `PDM-BOM-Parser.ps1` -- Parses BOM text files and uploads via bulk BOM endpoint
- `PDM-Upload-Functions.ps1` -- Shared functions (item number extraction, API calls)
- `PDM-Upload-Config.ps1` -- Configuration (API URL, watched folders)
- Replaces the legacy CheckIn-Watcher and BOM-Watcher Windows services

**Upsert**
- Database operation that inserts a new row or updates an existing one
- PDM implements this as a try-update-then-insert pattern
- Triggered via `PATCH /api/items/{item_number}?upsert=true`
- Used by the upload bridge to create items on first encounter and update on subsequent uploads

**Uvicorn**
- ASGI server that runs the FastAPI application
- Development: `uvicorn app.main:app --reload` (auto-restart on file changes)
- Production: runs without `--reload` flag
- Default port: 8000 (dev) or 8080 (production)

### V

**Vite**
- Frontend build tool and development server for Vue 3
- Provides instant HMR (Hot Module Replacement) during development
- Builds optimized static assets for production
- Development server: `npm run dev` (default port 5173)
- Production build: `npm run build`

**Vue 3**
- JavaScript framework for building the frontend user interface
- Uses Composition API with `<script setup>` syntax
- TypeScript enabled for type safety
- Components in `frontend/src/views/` and `frontend/src/components/`
- State management via Pinia stores

**Vue Router**
- See: Router (Vue Router)

### W

**Where-Used**
- Reverse BOM lookup: which assemblies contain a given part?
- Endpoint: `GET /api/bom/{item_number}/where-used`
- Displayed in the item detail panel in the frontend
- Queries `bom` table for rows where `child_item_id` matches the item

**Work Queue**
- Task queue table (`work_queue`) in Supabase PostgreSQL
- Stores tasks for asynchronous processing (DXF/SVG generation, parameter sync)
- Fields: `id`, `item_id`, `file_id`, `task_type`, `status`, `payload`, `error_message`
- Viewed in the frontend at `/tasks`

---

## Quick Reference Tables

### File Type Classifications

| Extension | File Type | Description |
|-----------|-----------|-------------|
| .prt, .asm, .drw | CAD | Creo native files |
| .step, .stp | STEP | 3D interchange format |
| .dxf | DXF | Flat pattern for manufacturing |
| .svg | SVG | Technical/bend drawings |
| .pdf | PDF | Documentation, specifications |
| .png, .jpg, .jpeg | IMAGE | Images and screenshots |
| other | OTHER | Miscellaneous files |

### Lifecycle State Progression

```
Design (Initial) -> Released (Approved) -> Obsolete (Deprecated)
```

### Item Number Format

```
csp0030    = 3 letters + 4-6 digits
wma20120   = Pattern: [a-z]{3}\d{4,6}
stp01000   = Always normalized to lowercase
mmc00100   = McMaster-Carr supplier part
spn00200   = Other supplier part
zzz00001   = Reference only (not created as real items)
```

### API Endpoints Summary

| Method | Path | Purpose |
|--------|------|---------|
| POST | /api/auth/login | User authentication |
| GET | /api/items | List items with filtering |
| POST | /api/items | Create item |
| GET | /api/items/{item_number} | Get item with files |
| PATCH | /api/items/{item_number} | Update or upsert item |
| DELETE | /api/items/{item_number} | Delete item |
| POST | /api/files/upload | Upload file to storage |
| GET | /api/files/{file_id}/download | Get signed download URL |
| GET | /api/bom/{item_number} | Single-level BOM |
| GET | /api/bom/{item_number}/tree | Multi-level BOM tree |
| GET | /api/bom/{item_number}/where-used | Reverse BOM lookup |
| POST | /api/bom/bulk | Bulk BOM upload |
| GET | /api/tasks | List work queue tasks |

### Frontend Routes

| Path | View | Purpose |
|------|------|---------|
| /login | LoginView | Authentication |
| / | HomeView | Dashboard/landing page |
| /pdm-browser | ItemsView | Main item browser table |
| /items/:itemNumber | ItemDetailView | Item detail page |
| /part-numbers | PartNumbersView | Part number listing |
| /projects | ProjectsView | Project management |
| /tasks | TasksView | Work queue viewer |
| /mrp/dashboard | MrpDashboardView | MRP overview |
| /mrp/routing | MrpRoutingView | Manufacturing routing |
| /mrp/shop | MrpShopView | Shop floor view |
| /mrp/parts | MrpPartLookupView | MRP part lookup |
| /mrp/tracking | MrpProjectTrackingView | Project tracking |
| /mrp/materials | MrpRawMaterialsView | Raw materials |

### Database Tables Summary

| Table | Purpose |
|-------|---------|
| items | Part/assembly metadata |
| files | File tracking (linked to items via item_id) |
| bom | Parent/child relationships |
| work_queue | Task queue for async processing |
| lifecycle_history | State change audit trail |
| checkouts | Active item checkouts |
| projects | Project grouping |
| users | User accounts (linked to Supabase Auth) |

### Development Ports

| Port | Service | Context |
|------|---------|---------|
| 5173 | Vite dev server | Frontend development |
| 8000 | Uvicorn | Backend development |
| 8080 | Uvicorn | Production (default) |

---

## Finding Definitions

**By Category:**
- **File Types:** See "File Type Classifications" table
- **API:** See "API Endpoints Summary" table
- **Frontend:** See "Frontend Routes" table
- **Database:** See "Database Tables Summary" table
- **States:** See "Lifecycle State Progression"

**By Task:**
- Development setup: [15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md](15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md)
- Troubleshooting: [19-TROUBLESHOOTING-DECISION-TREE.md](19-TROUBLESHOOTING-DECISION-TREE.md)
- Architecture: [27-WEB-MIGRATION-PLAN.md](27-WEB-MIGRATION-PLAN.md)

---

**Last Updated:** 2025-01-29
**Version:** 3.0
**Related:** [15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md](15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md), [27-WEB-MIGRATION-PLAN.md](27-WEB-MIGRATION-PLAN.md)
