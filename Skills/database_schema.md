# Database Schema Reference

SQLite database: `D:\PDM_Vault\pdm.sqlite`
Accessed via: `sqlite3.exe` command-line tool

## Tables

### items
Stores part metadata, lifecycle state, revision/iteration tracking, and BOM-extracted properties.

```sql
CREATE TABLE items (
    item_id INTEGER PRIMARY KEY,
    item_number TEXT NOT NULL,
    name TEXT,
    revision TEXT,              -- 'A', 'B', 'C', etc.
    iteration INTEGER,          -- 1, 2, 3, etc.
    lifecycle_state TEXT,       -- 'Design', 'Released', etc.
    description TEXT,           -- From BOM tree export
    project TEXT,               -- From BOM tree export
    material TEXT,              -- From BOM tree export (e.g., 'STEEL_HSLA')
    mass REAL,                  -- From BOM tree export
    thickness REAL,             -- From BOM tree export
    cut_length REAL,            -- From BOM tree export
    created_at TEXT,
    modified_at TEXT
);
```

**Key Points:**
- `item_number`: Lowercase normalized, e.g., `csp0030`, `wma20120`
- `revision`: Letter revision (A, B, C...)
- `iteration`: Numeric iteration within revision (1, 2, 3...)
- New items start at `A.1` in `Design` state
- Item iteration increments on major changes, not file overwrites
- `description`, `project`, `material`, `mass`, `thickness`, `cut_length`: Auto-populated by BOM-Watcher from tree exports

### files
Tracks individual files with paths, types, and version info.

```sql
CREATE TABLE files (
    file_id INTEGER PRIMARY KEY,
    item_number TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_type TEXT NOT NULL,    -- 'CAD', 'STEP', 'DXF', 'SVG', 'PDF', etc.
    revision TEXT,
    iteration INTEGER,
    added_at TEXT
);
```

**Key Points:**
- `file_path`: Full absolute path to file
- `file_type`: Determined by extension and classification logic
- File iteration bumps on overwrite (independent of item iteration)
- Multiple files can exist for same item (STEP, DXF, SVG, etc.)

### work_queue
Task queue for automated processing by Worker-Processor.

```sql
CREATE TABLE work_queue (
    task_id INTEGER PRIMARY KEY,
    item_number TEXT NOT NULL,
    file_path TEXT NOT NULL,
    task_type TEXT NOT NULL,    -- 'GENERATE_DXF', 'GENERATE_SVG', 'PARAM_SYNC', 'SYNC'
    created_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    status TEXT                 -- 'Pending', 'Processing', 'Completed', 'Failed'
);
```

**Task Types:**
- `GENERATE_DXF`: Create flat pattern from STEP
- `GENERATE_SVG`: Create technical drawing from STEP
- `PARAM_SYNC`: Sync CAD parameters (future)
- `SYNC`: General sync operations (future)

**Workflow:**
1. CheckIn-Watcher adds tasks as 'Pending'
2. Worker-Processor polls for 'Pending' tasks
3. Marks as 'Processing', executes batch script
4. Updates to 'Completed' or 'Failed'

### bom
Bill of Materials - single-level parent/child relationships.

```sql
CREATE TABLE bom (
    bom_id INTEGER PRIMARY KEY,
    parent_item TEXT NOT NULL,
    child_item TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    source_file TEXT
);
```

**Key Points:**
- Populated by BOM-Watcher from tree export txt files
- `parent_item`: Assembly item number (e.g., `wma20120`)
- `child_item`: Component item number (e.g., `wmp20080`)
- `quantity`: Count of child in parent (duplicates counted automatically)
- `source_file`: Name of txt file that created this entry (audit trail)
- **Single-level BOM**: Each assembly stores only direct children
  - To get full BOM tree, recursively query child assemblies
  - Example: `wma20120` contains `sub_asm`, query `sub_asm` separately for its parts

### lifecycle_history
Audit trail for lifecycle state changes.

```sql
CREATE TABLE lifecycle_history (
    history_id INTEGER PRIMARY KEY,
    item_number TEXT NOT NULL,
    old_state TEXT,
    new_state TEXT,
    old_revision TEXT,
    new_revision TEXT,
    old_iteration INTEGER,
    new_iteration INTEGER,
    changed_by TEXT,
    changed_at TEXT
);
```

**Usage:**
- Tracks every lifecycle transition
- Records revision/iteration changes
- Maintains audit trail for compliance

### checkouts
Tracks which items are currently checked out.

```sql
CREATE TABLE checkouts (
    item_number TEXT NOT NULL,
    username TEXT NOT NULL,
    checked_out_at TEXT
);
```

**Key Points:**
- Prevents concurrent edits
- Row exists only while checked out
- Deleted on check-in

### sqlite_sequence
SQLite internal table for autoincrement tracking.

```sql
CREATE TABLE sqlite_sequence (
    name TEXT,
    seq INTEGER
);
```

## Common Queries

### Get item with latest revision/iteration
```sql
SELECT * FROM items 
WHERE item_number = 'csp0030';
```

### Get all files for an item
```sql
SELECT * FROM files 
WHERE item_number = 'csp0030' 
ORDER BY added_at DESC;
```

### Get pending tasks for Worker-Processor
```sql
SELECT task_id, item_number, file_path, task_type 
FROM work_queue 
WHERE status = 'Pending' 
  AND task_type = 'GENERATE_DXF'
ORDER BY created_at ASC 
LIMIT 1;
```

### Get BOM for assembly
```sql
SELECT child_item, SUM(quantity) as total_qty 
FROM bom 
WHERE parent_item = 'csa0045' 
GROUP BY child_item;
```

### Check if item is checked out
```sql
SELECT username, checked_out_at 
FROM checkouts 
WHERE item_number = 'csp0030';
```

### Get lifecycle history for item
```sql
SELECT * FROM lifecycle_history 
WHERE item_number = 'csp0030' 
ORDER BY changed_at DESC;
```

### Check if DXF/SVG exists for item
```sql
SELECT COUNT(*) FROM files 
WHERE item_number = 'csp0030' 
  AND file_type = 'DXF';
```

## SQL Execution Pattern

All SQL executed via PDM-Library.ps1 functions:

**For INSERT/UPDATE/DELETE:**
```powershell
Exec-SQL "INSERT INTO items (item_number, revision, iteration, lifecycle_state) 
          VALUES ('csp0030', 'A', 1, 'Design');"
```

**For SELECT queries:**
```powershell
$result = Query-SQL "SELECT revision, iteration FROM items WHERE item_number='csp0030';"
# Returns pipe-separated string: "A|1"
```

**Direct sqlite3.exe calls (when needed):**
```powershell
$result = & sqlite3.exe -separator '|' $Global:DBPath "SELECT * FROM items;"
```

## Database Location
- Path: `D:\PDM_Vault\pdm.sqlite`
- Defined in: `PDM-Library.ps1` as `$Global:DBPath`
- Accessed by: All PowerShell services via PDM-Library functions
