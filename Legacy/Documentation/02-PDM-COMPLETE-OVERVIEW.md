# PDM System - Complete Overview

## System Purpose
Folder-based Product Data Management system for managing CAD files, BOM tracking, lifecycle management, and automated manufacturing document generation.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      D:\PDM_Vault                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  CADData/                                                         │
│  ├── CheckIn/          ← Files dropped here for ingestion        │
│  ├── BOM/              ← Tree exports from Creo (.txt)           │
│  ├── STEP/             ← 3D models (.step, .stp)                │
│  ├── DXF/              ← Flat patterns (.dxf)                    │
│  ├── SVG/              ← Technical drawings (.svg)               │
│  ├── PDF/              ← Documentation (.pdf)                    │
│  ├── Archive/          ← Other files                             │
│  └── [Native CAD]      ← Creo files (.prt, .asm, .drw)          │
│                                                                   │
│  Release/              ← In-progress release operations          │
│  Released/             ← Locked/released items                   │
│  Transfer/             ← Remote work staging (temporary)         │
│  logs/                 ← System logs (pdm.log)                   │
│  pdm.sqlite            ← Central database                        │
│  schema.sql            ← Database schema                         │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                  D:\PDM_PowerShell                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  PDM-Library.ps1            ← Core functions (all services use)  │
│  CheckIn-Watcher.ps1        ← File ingestion service            │
│  BOM-Watcher.ps1            ← BOM processing service            │
│  Worker-Processor.ps1       ← Task execution service            │
│  Release-Watcher.ps1        ← Release workflow service          │
│  Revise-Watcher.ps1         ← Revision management service       │
│  Part-Parameter-Watcher.ps1 ← Parameter sync service            │
│  Restart-PDM-Services.ps1   ← Service restart utility           │
│  CompareWorkspace.ps1       ← Workspace comparison tool         │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                   D:\FreeCAD\Tools                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  flatten_sheetmetal.bat              ← DXF generation wrapper    │
│  Flatten_sheetmetal_portable.py      ← DXF generation script    │
│  create_bend_drawing.bat             ← SVG generation wrapper   │
│  Create_bend_drawing_portable.py     ← SVG generation script    │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Database Schema

### Core Tables

#### items
Stores part metadata, lifecycle state, revision/iteration tracking, and BOM-extracted properties.

```sql
CREATE TABLE items (
    item_id INTEGER PRIMARY KEY,
    item_number TEXT NOT NULL,      -- e.g., 'csp0030'
    name TEXT,
    revision TEXT,                  -- 'A', 'B', 'C'
    iteration INTEGER,              -- 1, 2, 3
    lifecycle_state TEXT,           -- 'Design', 'Released'
    description TEXT,               -- From BOM tree
    project TEXT,                   -- From BOM tree
    material TEXT,                  -- From BOM tree (e.g., 'STEEL_HSLA')
    mass REAL,                      -- From BOM tree (grams)
    thickness REAL,                 -- From BOM tree (mm)
    cut_length REAL,                -- From BOM tree (mm)
    created_at TEXT,
    modified_at TEXT
);
```

**Key Points:**
- New items start at `A.1` in `Design` state
- Item iteration increments on major changes
- File overwrites don't increment item iteration
- BOM properties auto-populated by BOM-Watcher

#### files
Tracks individual files with paths, types, and version info.

```sql
CREATE TABLE files (
    file_id INTEGER PRIMARY KEY,
    item_number TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_type TEXT NOT NULL,        -- 'CAD', 'STEP', 'DXF', 'SVG', 'PDF'
    revision TEXT,
    iteration INTEGER,
    added_at TEXT
);
```

**Key Points:**
- Multiple files per item allowed
- File iteration bumps independently of item iteration
- Full absolute paths stored

#### work_queue
Task queue for automated processing by Worker-Processor.

```sql
CREATE TABLE work_queue (
    task_id INTEGER PRIMARY KEY,
    item_number TEXT NOT NULL,
    file_path TEXT NOT NULL,
    task_type TEXT NOT NULL,        -- 'GENERATE_DXF', 'GENERATE_SVG', 'PARAM_SYNC', 'SYNC'
    created_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    status TEXT                     -- 'Pending', 'Processing', 'Completed', 'Failed'
);
```

**Task Types:**
- `GENERATE_DXF`: Create flat pattern from STEP
- `GENERATE_SVG`: Create technical drawing from STEP
- `PARAM_SYNC`: Sync CAD parameters
- `SYNC`: General sync operations

#### bom
Bill of Materials - single-level parent/child relationships.

```sql
CREATE TABLE bom (
    bom_id INTEGER PRIMARY KEY,
    parent_item TEXT NOT NULL,      -- Assembly item
    child_item TEXT NOT NULL,       -- Component item
    quantity INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    source_file TEXT               -- Audit trail
);
```

**Important:** Single-level BOM only
- Each assembly stores direct children
- For full BOM tree, recursively query child assemblies
- Quantities automatically counted for duplicates

#### lifecycle_history
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

#### checkouts
Tracks which items are currently checked out.

```sql
CREATE TABLE checkouts (
    item_number TEXT NOT NULL,
    username TEXT NOT NULL,
    checked_out_at TEXT
);
```

Row exists only while checked out, deleted on check-in.

## PowerShell Services

### 1. CheckIn-Watcher.ps1
**Purpose:** File ingestion engine

**Monitors:** `D:\PDM_Vault\CADData\CheckIn\`

**File Classification:**
- **Ignored:** Files starting with `~`, `.tmp`, part NEU files
- **Assembly NEU:** `itemnum_asm.neu` → `Neutral\` + BOM extraction
- **CAD:** `.prt`, `.asm`, `.drw` → CADData root + queues PARAM_SYNC/SYNC
- **STEP:** `.step`, `.stp` → `STEP\` + queues DXF/SVG regeneration if exist
- **DXF:** `.dxf` → `DXF\` (filename parsed to extract base item)
- **SVG:** `.svg` → `SVG\` (filename parsed to extract base item)
- **PDF:** `.pdf` → `PDF\`
- **Other:** → `Archive\`

**Item Management:**
- Auto-creates items if not exist (A.1, Design)
- Preserves existing revision/iteration
- File overwrites bump file iteration only

**Key Functions:**
- `Get-FileClassification`
- `Ensure-ItemExists`
- `Register-FileRecord`
- `Extract-ItemNumber`
- `Queue-ExportGeneration`

### 2. BOM-Watcher.ps1
**Purpose:** Processes BOM tree exports from Creo

**Monitors:** `D:\PDM_Vault\CADData\BOM\`

**Process:**
1. Detects .txt file (tree tool export)
2. Parses header for parent assembly
3. Extracts child parts (3+ leading spaces)
4. Parses columns: Description, Project, Material, Mass, Thickness, Cut Length
5. Auto-creates items if needed
6. Deletes old BOM entries for assembly
7. Inserts new BOM relationships with quantities
8. Updates item properties
9. Deletes processed txt file

**Column Parsing:** Fixed positions based on header alignment

### 3. Worker-Processor.ps1
**Purpose:** Task execution engine

**Poll Interval:** 5 seconds (configurable)

**Task Processing:**
1. Query work_queue for `Pending` tasks
2. Mark as `Processing`, set `started_at`
3. Execute task-specific function
4. Update status to `Completed` or `Failed`

**Task Handlers:**

**GENERATE_DXF:**
- Calls `D:\FreeCAD\Tools\flatten_sheetmetal.bat`
- Input: STEP file
- Output: DXF placed in CheckIn folder
- CheckIn-Watcher auto-registers output

**GENERATE_SVG:**
- Calls `D:\FreeCAD\Tools\create_bend_drawing.bat`
- Input: STEP file
- Output: SVG placed in CheckIn folder
- CheckIn-Watcher auto-registers output

**Key Features:**
- For native Creo files, looks for STEP in `STEP\` folder first
- stdout/stderr captured to temp files
- Exit code determines success/failure

### 4. Release-Watcher.ps1
**Purpose:** Manages release workflow

**Monitors:** `D:\PDM_Vault\Release\`

**Functions:**
- Lifecycle transition to "Released"
- File locking
- Move to Released folder
- Audit trail creation

### 5. Revise-Watcher.ps1
**Purpose:** Handles revision management

**Monitors:** TBD

**Functions:**
- Revision letter increment (A → B → C)
- Iteration reset to 1
- File archival

### 6. Part-Parameter-Watcher.ps1
**Purpose:** Updates parameters for single parts

**Monitors:** Similar to BOM-Watcher but for individual part parameters

**Input:** .txt files with parameter data

**Updates:** Item properties from parameter exports

### Core Library: PDM-Library.ps1

Shared functions used by all services:

```powershell
Write-Log "Message"                    # Logs to pdm.log
Exec-SQL "INSERT INTO..."              # Execute INSERT/UPDATE/DELETE
$result = Query-SQL "SELECT..."        # Execute SELECT, returns array

$Global:SQLiteExe = "sqlite3.exe"
$Global:PDMRoot   = "D:\PDM_Vault"
$Global:DBPath    = "D:\PDM_Vault\pdm.sqlite"
$Global:LogPath   = "D:\PDM_Vault\logs\pdm.log"
```

## FreeCAD Automation

### flatten_sheetmetal.bat + Flatten_sheetmetal_portable.py

**Purpose:** Generate flat pattern DXF from STEP file

**Features:**
- Auto-detects FreeCAD location
- K-factor configurable (default: 0.35)
- Manual DXF generation with correct units (mm)
- Headless operation

**Fixed Issues:**
- ✅ DXF scaling issue resolved (was 645.16x too large)
- ✅ Explicit millimeter units in DXF header
- ✅ Bounding box verification output

**Usage:**
```batch
flatten_sheetmetal.bat input.step [output.dxf] [k_factor]
```

**Output:**
- DXF with flat pattern outline
- Inner wires (holes) included
- Millimeter units

### create_bend_drawing.bat + Create_bend_drawing_portable.py

**Purpose:** Generate technical drawing SVG from STEP file

**Features:**
- Flat pattern with bend lines
- Automatic dimensioning
- Bounding box dimensions
- Bend line dimensions
- 3D isometric preview
- K-factor and thickness notes
- Gauge notation for standard thicknesses

**Usage:**
```batch
create_bend_drawing.bat input.step [output.svg] [k_factor]
```

**Output:**
- SVG with A4 page layout
- Dimensions in inches with fractional equivalents
- Bend line annotations
- Material thickness info

## Web Interface

**Status:** In Development (D:\PDM_WebServer)

A modern Node.js-based web browser for the PDM system is currently being implemented.

**Planned Features:**
- Real-time database queries via REST API
- Item search and filtering
- File listing and preview
- BOM tree navigation
- Lifecycle history tracking
- Where-used analysis

**Legacy Implementation:**
The previous PowerShell-based static HTML generator (PDM-HTMLBrowser.ps1) has been archived to Backups folder.

## Workspace Comparison

### CompareWorkspace.ps1

**Purpose:** Compare Creo workspace with PDM vault via CreoJS integration

**How It Works:**
- PowerShell script listens for requests from Creo
- CreoJS webpage embedded in Creo browser calls the script
- Real-time workspace analysis and comparison
- Provides vault sync recommendations

**Features:**
- Workspace file scanning
- PDM database comparison
- Missing/extra file detection
- Action recommendations
- Creo browser integration via CreoJS

## Item Numbering Convention

**Format:** `ABC####` or `ABC#####`
- 3 letters + 4-6 digits
- Examples: `csp0030`, `wma20120`
- Lowercase normalized in database
- Base filename determines item linkage

**File Suffixes:**
- `csp0030_flat.dxf` → Links to item `csp0030`
- `csp0030_drawing.svg` → Links to item `csp0030`
- `wma20120_asm.neu` → Assembly neutral file

## Workflow Examples

### Check in New STEP File
```
1. Copy file to CheckIn\: csp0030.step
2. CheckIn-Watcher detects
3. Item csp0030 created (A.1, Design) if new
4. File moved to STEP\
5. File registered in database
6. If DXF/SVG exist, regeneration tasks queued
```

### Update STEP (Auto-Regenerate DXF/SVG)
```
1. Item csp0030 has existing DXF and SVG
2. Copy updated STEP to CheckIn\: csp0030.step
3. CheckIn-Watcher moves to STEP\
4. Sees existing DXF/SVG
5. Queues GENERATE_DXF and GENERATE_SVG tasks
6. Worker-Processor executes tasks
7. New DXF/SVG appear in CheckIn\
8. CheckIn-Watcher registers new versions
```

### Process BOM Tree Export
```
1. In Creo, run mapkey to export tree
2. File saved to BOM\: wma20120.txt
3. BOM-Watcher detects file
4. Parses parent assembly from header
5. Extracts child parts with quantities
6. Updates bom table
7. Updates item properties (material, mass, etc.)
8. Deletes txt file
```

### Release Item
```
1. Copy item files to Release\
2. Release-Watcher detects
3. Updates lifecycle_state to "Released"
4. Moves files to Released\
5. Locks files (read-only)
6. Creates lifecycle_history entry
```

## Service Management

### Start Services Manually (Development)
```powershell
# Window 1
powershell -File "D:\PDM_PowerShell\CheckIn-Watcher.ps1"

# Window 2
powershell -File "D:\PDM_PowerShell\Worker-Processor.ps1"

# Window 3
powershell -File "D:\PDM_PowerShell\BOM-Watcher.ps1"
```

### Windows Service Installation (NSSM)
```powershell
nssm install PDM_CheckInWatcher "powershell.exe" "-ExecutionPolicy Bypass -File D:\PDM_PowerShell\CheckIn-Watcher.ps1"
nssm install PDM_WorkerProcessor "powershell.exe" "-ExecutionPolicy Bypass -File D:\PDM_PowerShell\Worker-Processor.ps1"
nssm install PDM_BOMWatcher "powershell.exe" "-ExecutionPolicy Bypass -File D:\PDM_PowerShell\BOM-Watcher.ps1"

nssm start PDM_CheckInWatcher
nssm start PDM_WorkerProcessor
nssm start PDM_BOMWatcher
```

### Restart Services
```powershell
.\Restart-PDM-Services.ps1

# Or manually
Restart-Service PDM_CheckInWatcher
Restart-Service PDM_WorkerProcessor
```

### View Logs
```powershell
# Live tail
Get-Content "D:\PDM_Vault\logs\pdm.log" -Wait -Tail 50

# Search errors
Select-String -Path "D:\PDM_Vault\logs\pdm.log" -Pattern "ERROR" | Select -Last 10

# Search specific item
Select-String -Path "D:\PDM_Vault\logs\pdm.log" -Pattern "csp0030" | Select -Last 20
```

## Monitoring & Troubleshooting

### Check Service Status
```powershell
Get-Service | Where-Object {$_.Name -like "PDM_*"}
```

### View Work Queue
```powershell
sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT * FROM work_queue WHERE status='Pending';"
```

### Check Database Lock
```powershell
Get-Process powershell  # Look for zombie processes
Get-Process sqlite3     # Check for manual sessions
```

### Failed Tasks
```sql
SELECT item_number, task_type, started_at, completed_at 
FROM work_queue 
WHERE status='Failed' 
ORDER BY completed_at DESC 
LIMIT 10;
```

### Database Queries

```sql
-- All items with files
SELECT i.item_number, i.revision, i.iteration, i.lifecycle_state,
       COUNT(f.file_id) as file_count
FROM items i
LEFT JOIN files f ON i.item_number = f.item_number
GROUP BY i.item_number;

-- BOM for assembly
SELECT b.child_item, b.quantity, i.description, i.material
FROM bom b
LEFT JOIN items i ON b.child_item = i.item_number
WHERE b.parent_item = 'wma20120';

-- Lifecycle history
SELECT item_number, old_state, new_state, 
       old_revision || '.' || old_iteration as old_ver,
       new_revision || '.' || new_iteration as new_ver,
       changed_at
FROM lifecycle_history
WHERE item_number = 'csp0030'
ORDER BY changed_at DESC;
```

## Performance Considerations

**File Processing:**
- CheckIn-Watcher: 800ms delay before processing (file write completion)
- Worker-Processor: 5 second poll interval
- FreeCAD startup: ~2-5 seconds per operation

**Database:**
- SQLite single-writer limitation
- Services coordinate via short transactions
- Avoid long-running queries in services

**FreeCAD Automation:**
- Simple bracket (50 edges): ~5 seconds
- Complex housing (200 edges): ~15 seconds
- Large assemblies may timeout

## Security Considerations

**File System:**
- Services run as local system account
- PDM_Vault requires write access
- Logs contain file paths (no sensitive data)

**Database:**
- No encryption at rest
- No user authentication
- Local file access only

**Recommendations for Production:**
- Add user authentication
- Encrypt pdm.sqlite
- Implement audit logging
- Add file integrity checks

## Future Enhancements

### High Priority
1. Service monitoring dashboard
2. Enhanced error handling & recovery
3. User management system
4. Automated backups
5. Email/Slack notifications

### Medium Priority
1. Real-time web API (Python/Node.js)
2. Batch operations toolkit
3. ERP/MRP integration
4. Mobile app/PWA
5. Advanced analytics

### Low Priority
1. Multi-user checkout system
2. Change management workflows
3. Document templates
4. Manufacturing packet generation
5. QR code part lookup

## System Requirements

**Software:**
- Windows Server 2016+ or Windows 10/11
- PowerShell 5.1+
- SQLite 3.x
- FreeCAD 0.20 or 0.21
- Creo Parametric (optional, for native file support)

**Hardware:**
- 8GB RAM minimum
- 500GB disk space
- SSD recommended for database

**Network:**
- Local network access for remote work (Transfer folder)
- No internet required for core functionality

## Backup Strategy

### Daily Automated Backup
```powershell
# Pre-Migration-Backup.ps1
$backupPath = "D:\PDM_Backups\$(Get-Date -Format 'yyyy-MM-dd')"
Copy-Item "D:\PDM_Vault\pdm.sqlite" "$backupPath\pdm.sqlite"
```

### What to Backup
- `pdm.sqlite` (critical)
- `CADData\` folder (large, incremental backup)
- `logs\` (optional, for troubleshooting)
- PowerShell scripts (version control)

## Documentation Files

1. **SKILL.md** - Skill definition for Claude
2. **database_schema.md** - Detailed table structures
3. **services.md** - Service configuration and troubleshooting
4. **freecad_automation.md** - FreeCAD script details
5. **Setup_Guide.md** - Initial installation guide
6. **DXF_SCALING_FIX.md** - DXF unit issue resolution
7. **workspace-comparison-session-notes.md** - Workspace tool notes

## Version History

### v2.0 (2025-01-01)
- Fixed DXF scaling issue
- Manual DXF generation with explicit units
- Enhanced Worker-Processor logging
- Added Part-Parameter-Watcher

### v1.0 (Initial)
- Core PDM functionality
- CheckIn-Watcher, BOM-Watcher, Worker-Processor
- FreeCAD automation (DXF/SVG generation)
- Basic web interface
