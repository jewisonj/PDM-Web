# PowerShell Services Reference

## Service Overview

Three main Windows services monitor folders and process tasks in the PDM system.

## CheckIn-Watcher.ps1

**Purpose:** File ingestion engine - monitors CheckIn folder, classifies files, moves to appropriate locations, and triggers processing.

**Location:** `D:\PDM_PowerShell\CheckIn-Watcher.ps1`

**Dependencies:**
- PDM-Library.ps1 (dot-sourced)
- sqlite3.exe
- FreeCAD (path configured in script)

**Monitoring:**
- Watches: `D:\PDM_Vault\CADData\CheckIn\`
- Triggers: FileSystemWatcher on Created events
- Delay: 800ms before processing (file write completion)

**File Classification Logic:**

1. **Ignored files:**
   - Files starting with `~` (temp files)
   - Files with no extension or `.tmp`
   - Part NEU files (`itemnum.neu`) - auto-deleted

2. **Assembly NEU** (`itemnum_asm.neu`):
   - Type: `NEUTRAL_ASM`
   - Destination: `Neutral\`
   - Triggers: BOM extraction via Parse-Neu-BOM.ps1 (background job)

3. **CAD files** (`.prt`, `.asm`, `.drw`):
   - Type: `CAD`
   - Destination: `CADData\` root
   - Triggers: `PARAM_SYNC` and `SYNC` tasks queued

4. **STEP files** (`.step`, `.stp`):
   - Type: `STEP`
   - Destination: `STEP\`
   - If DXF exists: Queues `GENERATE_DXF` task
   - If SVG exists: Queues `GENERATE_SVG` task

5. **DXF files** (`.dxf`):
   - Type: `DXF`
   - Destination: `DXF\`
   - Filename parsed to extract base item number
   - Example: `csp0030_flat.dxf` → linked to `csp0030`

6. **SVG files** (`.svg`):
   - Type: `SVG`
   - Destination: `SVG\`
   - Filename parsed to extract base item number
   - Example: `csp0030_drawing.svg` → linked to `csp0030`

7. **PDF files** (`.pdf`):
   - Type: `PDF`
   - Destination: `PDF\`

8. **Other files:**
   - Type: `OTHER`
   - Destination: `Archive\`

**Item Management:**
- Auto-creates item records if not exist
- Starts at: Revision `A`, Iteration `1`, State `Design`
- Preserves existing revision/iteration on new files

**File Registration:**
- New files: Inserted into `files` table
- File overwrites: Iteration bumped, timestamp updated
- Item iteration unchanged (only bumps on item-level changes)

**Key Functions:**
- `Get-FileClassification`: Determines file type and destination
- `Ensure-ItemExists`: Creates item record if needed
- `Register-FileRecord`: Adds/updates file in database
- `Check-ExistingExports`: Checks if DXF/SVG exist for regeneration
- `Queue-ExportGeneration`: Adds tasks to work_queue
- `Extract-ItemNumber`: Parses item number from filename

**Configuration:**
```powershell
$Global:PDMRoot      = "D:\PDM_Vault"
$Global:CADDataRoot  = "D:\PDM_Vault\CADData"
$Global:CheckInPath  = "D:\PDM_Vault\CADData\CheckIn"
$Global:FreeCADExe   = "C:\Program Files\FreeCAD 0.21\bin\FreeCAD.exe"
$Global:ScriptsPath  = "D:\PDM_Scripts"
```

## Worker-Processor.ps1

**Purpose:** Task execution engine - polls work_queue table and executes automated processing tasks.

**Location:** `D:\PDM_PowerShell\Worker-Processor.ps1`

**Dependencies:**
- PDM-Library.ps1 (dot-sourced)
- sqlite3.exe
- FreeCAD batch scripts in `D:\FreeCAD\Tools\`

**Processing Loop:**
1. Poll work_queue for `Pending` tasks
2. Process each task type in order: `GENERATE_DXF`, `GENERATE_SVG`
3. Sleep for `$PollInterval` seconds (default: 5s)
4. Repeat

**Task Execution:**
1. Fetch task from work_queue (oldest first)
2. Mark status as `Processing`, set `started_at`
3. Execute appropriate function
4. Mark status as `Completed` or `Failed`, set `completed_at`

**Task Types:**

### GENERATE_DXF
- **Purpose:** Create flat pattern from STEP file
- **Batch File:** `flatten_sheetmetal.bat`
- **Input:** STEP file path from task
- **Output:** DXF placed in `CheckIn\` folder (e.g., `csp0030.dxf`)
- **Process:**
  1. Verify STEP file exists
  2. Call batch file: `flatten_sheetmetal.bat "input.step" "output.dxf"`
  3. Batch runs FreeCAD script for sheet metal unfolding
  4. Check exit code (0 = success)
  5. Generated DXF detected by CheckIn-Watcher and registered

**Note:** For native Creo files (.prt, .asm), script looks for STEP file in `STEP\` folder first

### GENERATE_SVG
- **Purpose:** Create technical drawing from STEP file
- **Batch File:** `create_bend_drawing.bat`
- **Input:** STEP file path from task
- **Output:** SVG placed in `CheckIn\` folder (e.g., `csp0030.svg`)
- **Process:**
  1. Verify STEP file exists
  2. Call batch file: `create_bend_drawing.bat "input.step" "output.svg"`
  3. Batch runs FreeCAD script for technical drawing generation
  4. Check exit code (0 = success)
  5. Generated SVG detected by CheckIn-Watcher and registered

**Key Functions:**
- `Get-PendingTasks`: Queries work_queue for next task
- `Update-TaskStatus`: Updates task status and timestamps
- `Generate-DXF`: Executes DXF generation workflow
- `Generate-SVG`: Executes SVG generation workflow
- `Process-Task`: Main task dispatcher

**Configuration:**
```powershell
$Global:ToolsPath    = "D:\FreeCAD\Tools"
$Global:FlattenBat   = "D:\FreeCAD\Tools\flatten_sheetmetal.bat"
$Global:BendDrawBat  = "D:\FreeCAD\Tools\create_bend_drawing.bat"
$Global:PollInterval = 5  # seconds
```

**Logging:**
- stdout/stderr redirected to temp files
- Logged via Write-Log to `D:\PDM_Vault\logs\pdm.log`
- Exit codes captured for success/failure determination

## Release-Watcher.ps1

**Purpose:** Manages release workflow and lifecycle transitions.

**Location:** `D:\PDM_PowerShell\Release-Watcher.ps1`

**Status:** 🚧 **In Development** - Designed for future multi-user support

**Current Implementation:**
- Stub implementation for monitoring release folder
- Not actively used in single-user system
- Requires completion for lifecycle state management

**Planned Features (Not Yet Implemented):**
- Lifecycle state transitions (Design → Released → Obsolete)
- File locking for released items
- Move to Released\ folder on release trigger
- Audit trail creation with user/timestamp
- Revision number management

**Future Work:**
Completion requires implementation of:
- State transition validation rules
- File locking mechanisms
- Multi-user access coordination
- Comprehensive testing

---

## Revise-Watcher.ps1

**Purpose:** Handles revision management and item iteration.

**Location:** `D:\PDM_PowerShell\Revise-Watcher.ps1`

**Status:** 🚧 **In Development** - Designed for future multi-user support

**Current Implementation:**
- Stub implementation for monitoring revision changes
- Not actively used in single-user system
- Requires completion for revision workflows

**Planned Features (Not Yet Implemented):**
- Revision letter increment (A → B → C)
- Iteration reset to 1 on revision change
- File archival and versioning
- Revision history tracking and audit trail
- Backwards compatibility with previous revisions

**Future Work:**
Completion requires implementation of:
- Revision increment logic and rules
- File archive structure design
- Version compatibility matrix
- User permission checks for revisions
- Comprehensive testing

## Service Management

### Running Services Manually (Development/Testing)
```powershell
# Start CheckIn-Watcher
powershell -File "D:\PDM_PowerShell\CheckIn-Watcher.ps1"

# Start Worker-Processor
powershell -File "D:\PDM_PowerShell\Worker-Processor.ps1"
```

### Service Installation (Windows Service)
```powershell
# Install as Windows Service using NSSM or similar
nssm install "CheckIn-Watcher" "powershell.exe" "-ExecutionPolicy Bypass -File D:\PDM_PowerShell\CheckIn-Watcher.ps1"
nssm set "CheckIn-Watcher" AppDirectory "D:\PDM_PowerShell"
nssm start "CheckIn-Watcher"
```

### Check Service Status
```powershell
Get-Service -Name "CheckIn-Watcher" | Format-List *
Get-Service -Name "Worker-Processor" | Format-List *
```

### Restart Services
```powershell
# Use included utility
powershell -File "D:\PDM_PowerShell\Restart-PDM-Services.ps1"

# Or manually
Restart-Service -Name "CheckIn-Watcher"
Restart-Service -Name "Worker-Processor"
```

### View Logs
```powershell
# Tail the log file
Get-Content "D:\PDM_Vault\logs\pdm.log" -Tail 50 -Wait

# Search for errors
Select-String -Path "D:\PDM_Vault\logs\pdm.log" -Pattern "ERROR"
```

## Troubleshooting

### CheckIn-Watcher not detecting files
1. Check service is running: `Get-Service CheckIn-Watcher`
2. Verify folder exists: `Test-Path "D:\PDM_Vault\CADData\CheckIn"`
3. Check log for errors: `Get-Content D:\PDM_Vault\logs\pdm.log -Tail 20`
4. Verify FileSystemWatcher is active (check for "running" log message)

### Worker-Processor not processing tasks
1. Check service status
2. Query pending tasks: `sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT * FROM work_queue WHERE status='Pending';"`
3. Verify batch files exist:
   - `Test-Path D:\FreeCAD\Tools\flatten_sheetmetal.bat`
   - `Test-Path D:\FreeCAD\Tools\create_bend_drawing.bat`
4. Check temp output files: `$env:TEMP\dxf_stdout.txt`, `$env:TEMP\svg_stderr.txt`
5. Test batch file manually: `& "D:\FreeCAD\Tools\flatten_sheetmetal.bat" "test.step" "test.dxf"`

### Database lock errors
- Only one service can write at a time
- Check for zombie PowerShell processes: `Get-Process powershell`
- Verify no manual sqlite3.exe sessions open
- Restart services: `Restart-PDM-Services.ps1`

### FreeCAD batch scripts failing
1. Verify FreeCAD installation path in CheckIn-Watcher.ps1
2. Test FreeCAD can run headless: `FreeCADCmd.exe --version`
3. Check batch script paths in Worker-Processor.ps1
4. Review batch script logs in `$env:TEMP`
5. Test with simple STEP file to isolate issue

### Files not linking to correct items
- Check filename convention: Should start with `ABC####` pattern
- Verify `Extract-ItemNumber` function logic
- For DXF/SVG: Filename must contain base item number (e.g., `csp0030_flat.dxf`)
- Check database: `sqlite3.exe pdm.sqlite "SELECT * FROM files WHERE item_number='csp0030';"`

## PDM-Library.ps1 Functions

Core utility functions used by all services:

### Write-Log
```powershell
Write-Log "Message text"
# Logs to: D:\PDM_Vault\logs\pdm.log
# Format: yyyy-MM-dd HH:mm:ss Message
```

### Exec-SQL
```powershell
Exec-SQL "INSERT INTO items (item_number, revision, iteration, lifecycle_state) VALUES ('csp0030', 'A', 1, 'Design');"
# For INSERT, UPDATE, DELETE operations
```

### Query-SQL
```powershell
$result = Query-SQL "SELECT revision, iteration FROM items WHERE item_number='csp0030';"
# Returns: Array of pipe-separated strings
# Example: "A|1"
```

### Configuration Variables
```powershell
$Global:SQLiteExe = "sqlite3.exe"
$Global:PDMRoot   = "D:\PDM_Vault"
$Global:DBPath    = "D:\PDM_Vault\pdm.sqlite"
$Global:LogPath   = "D:\PDM_Vault\logs\pdm.log"
```
