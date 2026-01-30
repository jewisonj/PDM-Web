# Database Schema Reference

Supabase PostgreSQL (cloud-hosted, managed)
Accessed via: Supabase Python client (`supabase-py`) in FastAPI backend

---

## Overview

All tables reside in the `public` schema on Supabase PostgreSQL. Every table uses UUID primary keys generated with `gen_random_uuid()` and `timestamptz` columns for timestamps. Row Level Security (RLS) is enabled on all tables.

The backend uses two Supabase client instances:

- **Anon client** (`supabase_anon_key`) -- standard user-level operations subject to RLS policies.
- **Admin client** (`supabase_service_key`) -- bypasses RLS for trusted internal operations such as bulk BOM upload and the file upload service.

---

## Tables

### users

Stores PDM user profiles. Linked to Supabase Auth via `auth_id`.

```sql
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_id     UUID UNIQUE,                        -- Links to Supabase Auth user
    username    TEXT NOT NULL UNIQUE,
    email       TEXT UNIQUE,
    role        TEXT DEFAULT 'viewer'
                CHECK (role IN ('admin', 'engineer', 'viewer')),
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);
```

**Key Points:**
- `auth_id` links to `auth.users.id` in Supabase Auth.
- `role` controls application-level permissions: `admin`, `engineer`, or `viewer`.
- Three users exist: Jack (engineer), Dan (admin/viewer), Shop (viewer).

**RLS:** Enabled. Authenticated users can read all users. A helper function avoids infinite recursion when RLS policies reference this table.

---

### projects

Groups items into logical projects.

```sql
CREATE TABLE projects (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    description TEXT,
    status      TEXT DEFAULT 'active'
                CHECK (status IN ('active', 'archived', 'completed')),
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);
```

**Key Points:**
- Items reference `projects.id` via foreign key (`items.project_id`).
- Status values: `active`, `archived`, `completed`.

**RLS:** Enabled. Authenticated users can read all projects.

---

### items

Core table storing part and assembly metadata, lifecycle state, revision/iteration tracking, and properties extracted from BOM data.

```sql
CREATE TABLE items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_number     TEXT NOT NULL UNIQUE,
    name            TEXT,
    revision        TEXT DEFAULT 'A',
    iteration       INTEGER DEFAULT 1,
    lifecycle_state TEXT DEFAULT 'Design'
                    CHECK (lifecycle_state IN ('Design', 'Review', 'Released', 'Obsolete')),
    description     TEXT,
    project_id      UUID REFERENCES projects(id),
    material        TEXT,
    mass            NUMERIC,
    thickness       NUMERIC,
    cut_length      NUMERIC,
    cut_time        NUMERIC,
    price_est       NUMERIC,
    is_supplier_part BOOLEAN DEFAULT false,
    supplier_name   TEXT,
    supplier_pn     TEXT,
    unit_price      NUMERIC,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
```

**Key Points:**
- `item_number` is lowercase-normalized (e.g., `csp0030`, `wma20120`). Pattern: 3 letters + 4-6 digits.
- Special prefixes: `mmc` (McMaster-Carr), `spn` (supplier), `zzz` (reference/skip).
- `revision` is a letter (A, B, C...). `iteration` is numeric within a revision (1, 2, 3...).
- New items start at revision `A`, iteration `1`, lifecycle state `Design`.
- Properties like `material`, `mass`, `thickness`, `cut_length`, `cut_time`, and `price_est` are populated automatically when BOM text files are uploaded via the bulk BOM API.
- `is_supplier_part` is set automatically for `mmc` and `spn` prefixed items.
- `updated_at` is maintained by a database trigger (`update_updated_at_column`).

**Foreign Keys Referenced By:**
- `files.item_id`
- `bom.parent_item_id`, `bom.child_item_id`
- `work_queue.item_id`
- `checkouts.item_id`
- `lifecycle_history.item_id`
- `mrp_projects.top_assembly_id`
- `mrp_project_parts.item_id`
- `routing.item_id`
- `routing_materials.item_id`
- `time_logs.item_id`
- `part_completion.item_id`

**RLS:** Enabled. Authenticated users can read all items. The admin client (service role key) is used for write operations from the upload service.

---

### files

Tracks individual files stored in Supabase Storage, with type classification and version info.

```sql
CREATE TABLE files (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id     UUID NOT NULL REFERENCES items(id),
    file_type   TEXT NOT NULL
                CHECK (file_type IN ('CAD', 'STEP', 'DXF', 'SVG', 'PDF', 'IMAGE', 'OTHER')),
    file_name   TEXT NOT NULL,
    file_path   TEXT,                               -- Supabase Storage path (bucket/item_number/filename)
    file_size   INTEGER,
    revision    TEXT,
    iteration   INTEGER DEFAULT 1,
    uploaded_by UUID REFERENCES users(id),
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);
```

**Key Points:**
- `file_path` is a Supabase Storage path in the format `pdm-files/item_number/filename` (e.g., `pdm-files/csp0030/csp0030.step`).
- `file_type` is determined from the file extension during upload: `.stp`/`.step` -> `STEP`, `.prt`/`.asm`/`.drw` -> `CAD`, `.dxf` -> `DXF`, `.svg` -> `SVG`, `.pdf` -> `PDF`, `.png`/`.jpg` -> `IMAGE`.
- `iteration` increments each time the same filename is re-uploaded for the same item.
- Multiple files can exist per item (STEP, DXF, SVG, PDF, etc.).
- Downloads use Supabase Storage signed URLs (valid for 1 hour).
- `updated_at` is maintained by a database trigger (`files_updated_at_trigger`). Used by workspace comparison to determine when a file was last modified in the vault.

**RLS:** Enabled. Authenticated users can read all files. The admin client handles uploads.

---

### bom

Bill of Materials -- single-level parent/child relationships between items.

```sql
CREATE TABLE bom (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_item_id  UUID NOT NULL REFERENCES items(id),
    child_item_id   UUID NOT NULL REFERENCES items(id),
    quantity        INTEGER DEFAULT 1,
    source_file     TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(parent_item_id, child_item_id)
);
```

**Key Points:**
- **Single-level BOM**: Each row represents one direct parent-child relationship.
- To get a full BOM tree, recursively query child assemblies via the `/api/bom/{item_number}/tree` endpoint.
- `source_file` records the original BOM text file name for audit purposes (e.g., `BOM.txt`).
- The `UNIQUE(parent_item_id, child_item_id)` constraint prevents duplicate relationships.
- Quantity represents how many of the child item are used in the parent assembly.
- Bulk BOM upload (`POST /api/bom/bulk`) replaces all existing BOM entries for the parent before inserting new ones.

**RLS:** Enabled. Authenticated users can read all BOM entries.

---

### work_queue

Task queue for automated processing (DXF flat pattern generation, SVG bend drawing generation).

```sql
CREATE TABLE work_queue (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id       UUID REFERENCES items(id),
    file_id       UUID REFERENCES files(id),
    task_type     TEXT NOT NULL
                  CHECK (task_type IN ('GENERATE_DXF', 'GENERATE_SVG', 'PARAM_SYNC', 'SYNC', 'NEST_PARTS')),
    status        TEXT DEFAULT 'pending'
                  CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    payload       JSONB,
    error_message TEXT,
    created_at    TIMESTAMPTZ DEFAULT now(),
    started_at    TIMESTAMPTZ,
    completed_at  TIMESTAMPTZ
);
```

**Key Points:**
- `task_type` values:
  - `GENERATE_DXF` -- Create DXF flat pattern from a STEP file (uses FreeCAD Docker worker).
  - `GENERATE_SVG` -- Create SVG bend drawing from a STEP file (uses FreeCAD Docker worker).
  - `NEST_PARTS` -- Nest DXF flat patterns onto stock sheets (uses nesting Docker worker).
  - `PARAM_SYNC` -- Reserved for future CAD parameter synchronization.
  - `SYNC` -- Reserved for future general sync operations.
- `status` lifecycle: `pending` -> `processing` -> `completed` or `failed`.
- `payload` is a JSONB field storing task-specific data (e.g., `{"file_path": "pdm-files/csp0030/csp0030.step"}`).
- `error_message` is populated only when `status` is `failed`.

**Workflow:**
1. API creates a task with status `pending` (via `POST /api/tasks/generate-dxf/{item_number}` or `POST /api/tasks/generate-svg/{item_number}`).
2. Worker polls for pending tasks via `GET /api/tasks/pending`.
3. Worker marks task as `processing` via `PATCH /api/tasks/{id}/start`.
4. Worker executes FreeCAD script in Docker container.
5. Worker marks task as `completed` or `failed` via `PATCH /api/tasks/{id}/complete`.

**RLS:** Enabled. Authenticated users can read and create tasks.

---

### lifecycle_history

Audit trail for lifecycle state, revision, and iteration changes on items.

```sql
CREATE TABLE lifecycle_history (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id       UUID NOT NULL REFERENCES items(id),
    old_state     TEXT,
    new_state     TEXT,
    old_revision  TEXT,
    new_revision  TEXT,
    old_iteration INTEGER,
    new_iteration INTEGER,
    changed_by    UUID REFERENCES users(id),
    change_notes  TEXT,
    changed_at    TIMESTAMPTZ DEFAULT now()
);
```

**Key Points:**
- Records every lifecycle state transition (e.g., Design -> Review -> Released).
- Also tracks revision and iteration changes.
- `changed_by` references the user who made the change.
- `change_notes` allows free-text explanation of why the change was made.
- Queryable via `GET /api/items/{item_number}/history`.

**RLS:** Enabled.

---

### checkouts

Tracks which items are currently checked out for editing. Prevents concurrent edits.

```sql
CREATE TABLE checkouts (
    item_id        UUID PRIMARY KEY REFERENCES items(id),
    user_id        UUID NOT NULL REFERENCES users(id),
    checked_out_at TIMESTAMPTZ DEFAULT now()
);
```

**Key Points:**
- `item_id` is the primary key -- an item can only be checked out by one user at a time.
- A row exists only while the item is checked out; it is deleted on check-in.
- Prevents concurrent editing conflicts.

**RLS:** Enabled.

---

### mrp_projects

Manufacturing Resource Planning projects, linking to a top-level assembly for production tracking.

```sql
CREATE TABLE mrp_projects (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_code            TEXT NOT NULL UNIQUE,
    description             TEXT,
    customer                TEXT,
    due_date                DATE,
    start_date              DATE,
    status                  TEXT DEFAULT 'Setup'
                            CHECK (status IN ('Setup', 'Released', 'On Hold', 'Complete')),
    top_assembly_id         UUID REFERENCES items(id),
    print_packet_path       TEXT,
    print_packet_generated_at TIMESTAMPTZ,
    created_at              TIMESTAMPTZ DEFAULT now(),
    updated_at              TIMESTAMPTZ DEFAULT now()
);
```

**Key Points:**
- `top_assembly_id` references the main assembly item for BOM explosion.
- `print_packet_path` stores the Supabase Storage path of a generated print packet PDF.
- Status values: `Setup`, `Released`, `On Hold`, `Complete`.

---

### workstations

Manufacturing workstations used in routing and time tracking.

```sql
CREATE TABLE workstations (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    station_code TEXT NOT NULL UNIQUE,
    station_name TEXT NOT NULL,
    sort_order   INTEGER DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT now()
);
```

**Key Points:**
- `station_code` is a short code (e.g., `LASER`, `BRAKE`, `WELD`, `PAINT`).
- `sort_order` controls display ordering in the UI.

---

### routing

Manufacturing routing steps for items through workstations.

```sql
CREATE TABLE routing (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id      UUID NOT NULL REFERENCES items(id),
    station_id   UUID NOT NULL REFERENCES workstations(id),
    sequence     INTEGER DEFAULT 10,
    est_time_min INTEGER DEFAULT 0,
    notes        TEXT,
    created_at   TIMESTAMPTZ DEFAULT now()
);
```

**Key Points:**
- Defines the sequence of workstations an item passes through during manufacturing.
- `sequence` determines the processing order (10, 20, 30...).
- `est_time_min` is the estimated time in minutes for the operation.

---

### mrp_project_parts

Links items to MRP projects with required quantities.

```sql
CREATE TABLE mrp_project_parts (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES mrp_projects(id),
    item_id    UUID NOT NULL REFERENCES items(id),
    quantity   INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

---

### raw_materials

Inventory of raw materials (sheet metal, structural tubing, other stock).

```sql
CREATE TABLE raw_materials (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    material_code   TEXT NOT NULL,
    material_type   TEXT CHECK (material_type IN ('SQ', 'OT', 'SM')),
    part_number     TEXT,
    description     TEXT,
    profile         TEXT,
    dim1_in         NUMERIC,
    dim2_in         NUMERIC,
    wall_or_thk_in  NUMERIC,
    stock_length_ft NUMERIC,
    weight_lb_per_ft NUMERIC,
    qty_on_hand     INTEGER DEFAULT 0,
    qty_on_order    INTEGER DEFAULT 0,
    reorder_point   INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
```

**Key Points:**
- `material_type` codes: `SM` (sheet metal), `SQ` (square/rectangular tubing), `OT` (other/round tubing).
- Dimensions are in inches; stock length in feet.
- `qty_on_hand`, `qty_on_order`, `reorder_point` support inventory management.

---

### routing_materials

Links items to the raw materials they require.

```sql
CREATE TABLE routing_materials (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id      UUID NOT NULL REFERENCES items(id),
    material_id  UUID NOT NULL REFERENCES raw_materials(id),
    qty_required NUMERIC DEFAULT 1,
    created_at   TIMESTAMPTZ DEFAULT now()
);
```

---

### time_logs

Records actual time spent on items at workstations.

```sql
CREATE TABLE time_logs (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES mrp_projects(id),
    item_id    UUID NOT NULL REFERENCES items(id),
    station_id UUID NOT NULL REFERENCES workstations(id),
    worker     TEXT,
    time_min   INTEGER NOT NULL,
    logged_at  TIMESTAMPTZ DEFAULT now()
);
```

---

### part_completion

Tracks completion of parts at each workstation within an MRP project.

```sql
CREATE TABLE part_completion (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   UUID NOT NULL REFERENCES mrp_projects(id),
    item_id      UUID NOT NULL REFERENCES items(id),
    station_id   UUID NOT NULL REFERENCES workstations(id),
    qty_complete INTEGER DEFAULT 0,
    completed_by TEXT,
    completed_at TIMESTAMPTZ DEFAULT now()
);
```

---

### nest_jobs

DXF nesting job records linked to MRP projects.

```sql
CREATE TABLE nest_jobs (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id           UUID NOT NULL REFERENCES mrp_projects(id),
    material             TEXT NOT NULL,
    thickness            NUMERIC NOT NULL,
    sheet_width          NUMERIC NOT NULL,
    sheet_height         NUMERIC NOT NULL,
    spacing              NUMERIC DEFAULT 5.0,
    allow_rotation       BOOLEAN DEFAULT true,
    status               TEXT DEFAULT 'pending'
                         CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    utilization_pct      NUMERIC,
    total_sheets         INTEGER,
    error_message        TEXT,
    created_at           TIMESTAMPTZ DEFAULT now(),
    completed_at         TIMESTAMPTZ
);
```

**Key Points:**
- Links nesting jobs to MRP projects for project-scoped nesting.
- `material` and `thickness` define the material group being nested.
- `sheet_width` and `sheet_height` are the stock sheet dimensions in mm.
- `spacing` is the minimum gap between parts in mm.
- `allow_rotation` enables 90-degree rotation of parts during nesting.
- `status` follows the same lifecycle as `work_queue`: `pending` -> `processing` -> `completed` or `failed`.
- `utilization_pct` and `total_sheets` are populated on completion.

---

### nest_job_items

Individual parts included in a nesting job.

```sql
CREATE TABLE nest_job_items (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id     UUID NOT NULL REFERENCES nest_jobs(id),
    item_id    UUID NOT NULL REFERENCES items(id),
    dxf_path   TEXT NOT NULL,
    quantity   INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

**Key Points:**
- Links nest jobs to specific items and their DXF files.
- `dxf_path` is the Supabase Storage path to the flat pattern DXF.
- `quantity` specifies how many copies of this part to nest.

---

### nest_results

Nesting output sheets with placement data.

```sql
CREATE TABLE nest_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID NOT NULL REFERENCES nest_jobs(id),
    sheet_index     INTEGER NOT NULL,
    dxf_path        TEXT NOT NULL,
    utilization_pct NUMERIC,
    placement_count INTEGER,
    placement_data  JSONB,
    created_at      TIMESTAMPTZ DEFAULT now()
);
```

**Key Points:**
- One row per output sheet in the nesting job.
- `sheet_index` is the sheet number (1, 2, 3...).
- `dxf_path` is the Supabase Storage path to the nested output DXF.
- `utilization_pct` is the percentage of the sheet area used by parts.
- `placement_count` is the total number of parts on this sheet.
- `placement_data` is a JSONB array of placed parts with positions and rotations.

---

## Indexes

The following indexes exist for query performance:

| Index Name | Table | Column(s) | Purpose |
|---|---|---|---|
| `idx_items_item_number` | items | item_number | Fast item lookup by number |
| `idx_items_project` | items | project_id | Filter items by project |
| `idx_items_lifecycle` | items | lifecycle_state | Filter items by state |
| `idx_files_item` | files | item_id | Get all files for an item |
| `idx_files_type` | files | file_type | Filter files by type |
| `idx_bom_parent` | bom | parent_item_id | Get BOM children |
| `idx_bom_child` | bom | child_item_id | Where-used queries |
| `idx_work_queue_status` | work_queue | status | Find pending tasks |

Additionally, all `UNIQUE` constraints and primary keys automatically create indexes.

---

## Entity Relationship Diagram

```
projects  1--*  items  1--*  files
                  |
                  |--1--*  bom (as parent_item_id)
                  |--*--1  bom (as child_item_id)
                  |--1--*  work_queue
                  |--1--*  lifecycle_history
                  |--1--0..1  checkouts
                  |--1--*  routing
                  |--1--*  routing_materials
                  |--1--*  mrp_project_parts
                  |--1--*  time_logs
                  |--1--*  part_completion
                  |
users  -------->  lifecycle_history.changed_by
       -------->  files.uploaded_by
       -------->  checkouts.user_id

workstations  1--*  routing
              1--*  time_logs
              1--*  part_completion

raw_materials  1--*  routing_materials

mrp_projects  1--*  mrp_project_parts
              1--*  time_logs
              1--*  part_completion
```

---

## Row Level Security (RLS)

RLS is enabled on all tables. The general policy pattern is:

- **SELECT**: Authenticated users can read all rows.
- **INSERT/UPDATE/DELETE**: Authenticated users can modify rows (some tables use permissive `true` policies for shop floor operations).

The backend uses the **service role key** (admin client) for trusted internal operations that need to bypass RLS, such as:
- Bulk BOM upload from the PDM Upload Service
- File uploads from the PDM Upload Service
- Item upsert operations

The anon key client is used for standard user-facing API calls, which are subject to RLS policies.

**Note:** The `update_updated_at_column()` trigger function should have its `search_path` set explicitly for security hardening.

---

## Database Triggers

### update_updated_at_column

Automatically sets `updated_at` to `now()` on UPDATE for tables that have this column:
- `items`
- `projects`
- `users`
- `mrp_projects`
- `raw_materials`

### files_updated_at_trigger

Automatically sets `updated_at` to `now()` on UPDATE for the `files` table. Uses a separate trigger function (`update_files_updated_at`) because it was added later via migration `add_updated_at_to_files`.

```sql
CREATE OR REPLACE FUNCTION update_files_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER files_updated_at_trigger
BEFORE UPDATE ON files
FOR EACH ROW EXECUTE FUNCTION update_files_updated_at();
```

---

## Supabase Storage

Files are stored in the `pdm-files` Supabase Storage bucket.

**Path Convention:** `{item_number}/{filename}`
- Example: `csp0030/csp0030.step`
- Example: `csp0030/csp0030_flat.dxf`
- Example: `csp0030/csp0030.pdf`

**Access:** Signed URLs are generated by the API with a 1-hour expiry for file downloads.

---

## Common Queries

### Get item by item_number

```python
# Python (Supabase client)
result = supabase.table("items").select("*").eq("item_number", "csp0030").single().execute()
```

```sql
-- SQL
SELECT * FROM items WHERE item_number = 'csp0030';
```

### Get all files for an item

```python
result = supabase.table("files").select("*").eq("item_id", item_id).execute()
```

```sql
SELECT f.* FROM files f
JOIN items i ON f.item_id = i.id
WHERE i.item_number = 'csp0030'
ORDER BY f.created_at DESC;
```

### Get BOM children for an assembly

```python
bom_result = supabase.table("bom").select("child_item_id, quantity").eq("parent_item_id", parent_id).execute()
```

```sql
SELECT i.item_number, i.name, i.material, b.quantity
FROM bom b
JOIN items i ON b.child_item_id = i.id
WHERE b.parent_item_id = (SELECT id FROM items WHERE item_number = 'wma20120');
```

### Where-used query (find parents of a part)

```sql
SELECT i.item_number, i.name, b.quantity
FROM bom b
JOIN items i ON b.parent_item_id = i.id
WHERE b.child_item_id = (SELECT id FROM items WHERE item_number = 'csp0030');
```

### Get pending tasks for worker

```python
result = supabase.table("work_queue").select("*").eq("status", "pending").order("created_at").limit(10).execute()
```

```sql
SELECT * FROM work_queue
WHERE status = 'pending'
ORDER BY created_at ASC
LIMIT 10;
```

### Get lifecycle history for an item

```python
history = supabase.table("lifecycle_history").select("*").eq("item_id", item_id).order("changed_at", desc=True).execute()
```

```sql
SELECT lh.* FROM lifecycle_history lh
JOIN items i ON lh.item_id = i.id
WHERE i.item_number = 'csp0030'
ORDER BY lh.changed_at DESC;
```

### Check if an item is checked out

```sql
SELECT u.username, c.checked_out_at
FROM checkouts c
JOIN users u ON c.user_id = u.id
WHERE c.item_id = (SELECT id FROM items WHERE item_number = 'csp0030');
```

### Search items with filtering

```python
query = supabase.table("items").select("*, projects(name)")
query = query.or_("item_number.ilike.%csp%,name.ilike.%bracket%")
query = query.eq("lifecycle_state", "Design")
query = query.order("item_number").range(0, 49)
result = query.execute()
```

### Recursive BOM tree (SQL)

```sql
WITH RECURSIVE bom_tree AS (
    -- Base case: direct children
    SELECT b.child_item_id, b.quantity, 1 AS depth
    FROM bom b
    WHERE b.parent_item_id = (SELECT id FROM items WHERE item_number = 'wma20120')

    UNION ALL

    -- Recursive case: children of children
    SELECT b.child_item_id, b.quantity, bt.depth + 1
    FROM bom b
    JOIN bom_tree bt ON b.parent_item_id = bt.child_item_id
    WHERE bt.depth < 10
)
SELECT i.item_number, i.name, bt.quantity, bt.depth
FROM bom_tree bt
JOIN items i ON bt.child_item_id = i.id
ORDER BY bt.depth, i.item_number;
```

---

## Migration History

Migrations are managed through Supabase and applied in order:

| Version | Name | Description |
|---|---|---|
| 20260127062455 | create_users_table | Users table with role check constraint |
| 20260127062500 | create_projects_table | Projects table |
| 20260127062508 | create_items_table | Items table with all property columns |
| 20260127062513 | create_files_table | Files table with type check constraint |
| 20260127062519 | create_bom_table | BOM table with unique constraint |
| 20260127062525 | create_work_queue_table | Work queue with status and type constraints |
| 20260127062531 | create_lifecycle_and_checkouts | Lifecycle history and checkouts tables |
| 20260127062558 | enable_rls_and_policies | RLS policies for all tables |
| 20260127062615 | create_storage_bucket | Supabase Storage bucket for files |
| 20260127153141 | fix_users_rls_infinite_recursion | Fix recursive RLS on users table |
| 20260127153203 | fix_rls_recursion_with_helper_function | Helper function for RLS |
| 20260127153728 | create_mrp_tables | MRP projects, workstations, routing, materials, time logs, completion |
| 20260127160309 | add_start_date_to_mrp_projects | Start date column |
| 20260127160534 | add_tube_workstations | Additional workstation records |
| 20260127160713 | create_storage_buckets | Additional storage configuration |
| 20260127160723 | storage_rls_policies | Storage bucket RLS policies |
| 20260128013100 | replace_workstations_with_legacy_codes | Workstation code standardization |
| 20260128013150 | import_raw_materials_from_csv | Seed raw materials data |
| 20260128022035 | add_print_packet_columns | Print packet path and timestamp |
| 20260129140530 | add_cut_time_and_price_est_to_items | Cut time and price estimate fields |
| 20260130010000 | create_nest_jobs_table | Nesting job records linked to MRP projects |
| 20260130010001 | create_nest_job_items_table | Individual parts in nesting jobs |
| 20260130010002 | create_nest_results_table | Nesting output sheets with placement data |
| 20260130010003 | update_work_queue_task_types | Add NEST_PARTS to work_queue task_type constraint |
| 20260130010004 | add_nest_rls_policies | RLS policies for nest tables |
| 20260130020000 | add_updated_at_to_files | Added `updated_at` column to files table with auto-update trigger |

---

## API Access Patterns

The FastAPI backend registers routers at these prefixes:

| Prefix | Module | Purpose |
|---|---|---|
| `/api/items` | `routes/items.py` | Item CRUD, search, lifecycle history |
| `/api/files` | `routes/files.py` | File upload, download (signed URLs), metadata |
| `/api/bom` | `routes/bom.py` | BOM queries, bulk upload, where-used |
| `/api/projects` | `routes/projects.py` | Project CRUD |
| `/api/auth` | `routes/auth.py` | Authentication via Supabase Auth |
| `/api/tasks` | `routes/tasks.py` | Work queue management |
| `/api/mrp` | `routes/mrp.py` | MRP projects, routing, materials, tracking |
| `/api/nesting` | `routes/nesting.py` | DXF nesting jobs, material groups, sheet downloads |
| `/api/workspace` | `routes/workspace.py` | Workspace comparison (local files vs. vault) |

---

**Last Updated:** 2026-01-30
