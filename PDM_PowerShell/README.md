# PDM PowerShell Scripts - Index & Guide

Quick reference guide for all PowerShell scripts in the PDM system.

**Location:** `D:\PDM_PowerShell\`

---

## Script Overview

The PDM system is powered by 15 PowerShell scripts that handle automation, data processing, and system management. All scripts use the shared library **PDM-Library.ps1** for common functions.

---

## Core Services (Windows Services / Watchers)

These scripts run continuously as Windows services or manual processes, monitoring folders and executing automated workflows.

### ✅ Production Services

#### 1. CheckIn-Watcher.ps1
**Purpose:** File ingestion and classification engine

**What It Does:**
- Monitors `D:\PDM_Vault\CADData\CheckIn\` for new files
- Classifies files by type (CAD, STEP, DXF, SVG, PDF, etc.)
- Moves files to appropriate folders (STEP\, DXF\, SVG\, PDF\, etc.)
- Auto-creates items if not exist
- Registers files in database
- Queues DXF/SVG regeneration if applicable

**File Types:**
- `.prt`, `.asm`, `.drw` → CAD files
- `.step`, `.stp` → 3D models
- `.dxf` → Flat patterns
- `.svg` → Technical drawings
- `.pdf` → Documentation
- `_asm.neu` → Assembly neutral files (triggers BOM extraction)

**Key Functions:**
- `Get-FileClassification` - Determines file type
- `Extract-ItemNumber` - Parses item number from filename
- `Queue-ExportGeneration` - Queues DXF/SVG generation

**Configuration:**
```powershell
$Global:CheckInPath  = "D:\PDM_Vault\CADData\CheckIn"
$Global:FreeCADExe   = "C:\Program Files\FreeCAD 0.21\bin\FreeCAD.exe"
```

**Documentation:** See `D:\PDM_COMPLETE_OVERVIEW.md` - CheckIn-Watcher section

---

#### 2. BOM-Watcher.ps1
**Purpose:** Bill of Materials processing

**What It Does:**
- Monitors `D:\PDM_Vault\CADData\BOM\` for `.txt` files
- Parses Creo BOM tree exports
- Extracts parent assembly and child components
- Populates `bom` table with parent/child relationships
- Updates item properties (material, mass, thickness, cost, etc.)
- Auto-creates missing items

**Process:**
1. Detects new BOM text file
2. Parses header for parent assembly
3. Extracts child items and quantities
4. Parses columns: Description, Project, Material, Mass, Thickness
5. Updates database with relationships and properties
6. Deletes processed file

**File Format:**
BOM files are text exports from Creo with fixed-column format. Header identifies parent assembly, subsequent lines with indent are children.

**Configuration:**
```powershell
$Global:BOMPath = "D:\PDM_Vault\CADData\BOM"
```

**Documentation:** See `D:\PDM_COMPLETE_OVERVIEW.md` - BOM-Watcher section

---

#### 3. MLBOM-Watcher.ps1
**Purpose:** Multi-level BOM processing with hierarchical indent support

**What It Does:**
- Monitors `D:\PDM_Vault\CADData\BOM\MLBOM*.txt` for multi-level BOMs
- Supports nested assembly hierarchies via indentation levels
- Extracts pricing information from BOM data
- Better handling of complex assembly structures

**When to Use:**
Use when BOM exports include nested subassembly hierarchies with indentation showing relationships.

**Configuration:**
```powershell
$Global:BOMPath = "D:\PDM_Vault\CADData\BOM"
```

**Documentation:** See `D:\PDM_COMPLETE_OVERVIEW.md` - Services section

---

#### 4. Worker-Processor.ps1
**Purpose:** Task execution engine for automated manufacturing document generation

**What It Does:**
- Polls `work_queue` table for pending tasks
- Executes tasks: GENERATE_DXF, GENERATE_SVG
- Calls FreeCAD batch scripts for document generation
- Updates task status (Pending → Processing → Completed/Failed)
- Handles error logging and cleanup

**Supported Tasks:**
| Task | Purpose | Input | Output |
|------|---------|-------|--------|
| `GENERATE_DXF` | Flatten sheet metal | STEP file | DXF pattern |
| `GENERATE_SVG` | Create technical drawing | STEP file | SVG with dimensions |

**Execution Pattern:**
1. Fetch oldest pending task
2. Mark as Processing, set start time
3. Execute task-specific function
4. Call appropriate batch file from `D:\FreeCAD\Tools\`
5. Mark Completed/Failed, set end time

**Configuration:**
```powershell
$Global:ToolsPath    = "D:\FreeCAD\Tools"
$Global:FlattenBat   = "D:\FreeCAD\Tools\flatten_sheetmetal.bat"
$Global:BendDrawBat  = "D:\FreeCAD\Tools\create_bend_drawing.bat"
$Global:PollInterval = 5  # seconds
```

**Documentation:** See `D:\PDM_COMPLETE_OVERVIEW.md` - Worker-Processor section

---

#### 5. Part-Parameter-Watcher.ps1
**Purpose:** Parameter synchronization for individual parts

**What It Does:**
- Monitors `D:\PDM_Vault\CADData\ParameterUpdate\` for parameter files
- Updates item properties from parameter exports
- Syncs CAD parameters with database
- Similar to BOM-Watcher but for single-item parameters

**Use Case:**
When you need to update properties (thickness, material, cost) for a specific part without a full BOM.

**Configuration:**
```powershell
$Global:ParameterPath = "D:\PDM_Vault\CADData\ParameterUpdate"
```

**Documentation:** See `D:\PDM_COMPLETE_OVERVIEW.md` - Services section

---

### 🚧 In Development (Not Yet Production)

#### 6. Release-Watcher.ps1
**Purpose:** Release workflow and lifecycle state management (IN DEVELOPMENT)

**Current Status:** Stub implementation - handles basic release folder monitoring

**Expected Features:**
- Lifecycle state transitions (Design → Released → Obsolete)
- File locking for released items
- Move to Released\ folder
- Audit trail creation
- Revision management

**Note:** Designed for future multi-user support. Currently not used in single-user system.

**Configuration:**
```powershell
$Global:ReleasePath = "D:\PDM_Vault\CADData\Release"
```

**Documentation:** See `D:\PDM_COMPLETE_OVERVIEW.md` - Release-Watcher section

---

#### 7. Revise-Watcher.ps1
**Purpose:** Revision management and item iteration (IN DEVELOPMENT)

**Current Status:** Stub implementation - monitors for revision changes

**Expected Features:**
- Revision letter increment (A → B → C)
- Iteration reset to 1 on revision change
- File archival and versioning
- Revision history tracking

**Note:** Designed for future multi-user support. Currently not used in single-user system.

**Documentation:** See `D:\PDM_COMPLETE_OVERVIEW.md` - Revise-Watcher section

---

## Utility Scripts (Ad-Hoc / Manual Use)

These scripts are run manually when needed for maintenance, analysis, or support tasks.

### 📊 Analysis & Reporting

#### 8. Get-BOMCost.ps1
**Purpose:** BOM cost rollup and pricing analysis

**What It Does:**
- Recursively calculates total cost of an assembly
- Traverses BOM tree summing component costs
- Detects circular references
- Displays hierarchical cost breakdown

**Usage:**
```powershell
.\Get-BOMCost.ps1 -Assembly "wma20120"
.\Get-BOMCost.ps1 -Assembly "csp0030" -Quantity 5
```

**Output:**
- Color-coded hierarchical display
- Assembly cost vs. component cost breakdown
- Total estimated cost

**Features:**
- Recursive BOM traversal
- Circular reference detection
- Cost aggregation by level
- Multi-quantity cost calculation

**Documentation:** See `D:\PDM_PowerShell\BOM-COST-ROLLUP-GUIDE.md`

---

#### 9. Get-McMasterPrint.ps1
**Purpose:** Supplier documentation and part number retrieval

**What It Does:**
- Fetches supplier data and documentation
- Links to McMaster-Carr or other supplier catalogs
- Helps with procurement and sourcing

**Usage:**
```powershell
.\Get-McMasterPrint.ps1 -PartNumber "12345"
```

**Note:** Specific to McMaster-Carr integration; may need customization for your suppliers

---

### 🧹 Maintenance & Cleanup

#### 10. PDM-Database-Cleanup.ps1
**Purpose:** Database maintenance and orphaned file detection

**What It Does:**
- Scans database for missing or orphaned files
- Reports files in database but not on disk
- Offers cleanup options with safety checks
- Supports file type filtering
- Provides dry-run mode for preview

**Usage:**
```powershell
# Dry-run: Show what would be cleaned
.\PDM-Database-Cleanup.ps1 -DryRun

# Clean specific file type
.\PDM-Database-Cleanup.ps1 -FileType "DXF" -Confirm

# Clean all orphaned entries
.\PDM-Database-Cleanup.ps1 -All
```

**Features:**
- Dry-run mode (preview changes)
- File type filtering (CAD, STEP, DXF, SVG, PDF, etc.)
- Confirmation prompts for safety
- Detailed reporting

**Documentation:** See `D:\PDM_PowerShell\Use Guides\PDM-DATABASE-CLEANUP-GUIDE.md`

---

#### 11. Clear-PDM-Data.ps1
**Purpose:** DESTRUCTIVE - Complete PDM database and file reset

**⚠️ WARNING:** This script deletes all PDM data. Use with extreme caution.

**What It Does:**
- Empties `D:\PDM_Vault\CADData\` folders
- Resets `pdm.sqlite` database
- Clears all items, files, BOMs, and history

**Usage:**
```powershell
# Preview what would be deleted
.\Clear-PDM-Data.ps1 -WhatIf

# Actually delete (with confirmation)
.\Clear-PDM-Data.ps1 -Confirm
```

**Safety Features:**
- `-WhatIf` mode for preview
- `-Confirm` prompt before execution
- Requires explicit confirmation

**When to Use:**
- Development environment reset
- Complete system reinitialization
- Testing and validation
- Clean database restart

**When NOT to Use:**
- Production systems with important data
- Without backup
- By mistake (requires confirmation)

---

### 🔍 Comparison & Analysis

#### 12. CompareWorkspace.ps1
**Purpose:** Creo workspace vs. PDM vault comparison

**What It Does:**
- Runs as HTTP service on port 8082
- Compares local Creo workspace with PDM vault
- Identifies missing or extra files
- Provides sync recommendations
- Integrates with Creo browser (CreoJS)

**Usage:**
```powershell
# Start comparison service
.\CompareWorkspace.ps1

# Access via CreoJS in Creo browser
# Service listens at http://localhost:8082
```

**Features:**
- Real-time workspace scanning
- PDM database comparison
- Discrepancy reporting
- Creo integration via web API

**Documentation:** See `D:\Skills\DEVELOPMENT-NOTES-workspace-comparison.md`

---

### 🌐 Web Services

#### 13. Start-PartNumbersList.ps1
**Purpose:** Launch searchable part database web server

**What It Does:**
- Starts Node.js web server on port 3002
- Provides searchable interface to part database
- Quick lookup of item numbers and properties

**Usage:**
```powershell
.\Start-PartNumbersList.ps1
# Access at http://localhost:3002
```

**Note:** Separate from main PDM Browser on port 3000

---

## Service Management Scripts

#### 14. Restart-PDM-Services.ps1
**Purpose:** Service restart utility for Windows services

**What It Does:**
- Stops all PDM Windows services
- Waits for clean shutdown
- Restarts all services

**Usage:**
```powershell
.\Restart-PDM-Services.ps1
```

**Affected Services:**
- PDM_CheckInWatcher
- PDM_BOMWatcher
- PDM_WorkerProcessor
- PDM_PartParameterWatcher

**When to Use:**
- After configuration changes
- When services hang or become unresponsive
- For system recovery
- During maintenance windows

---

## Core Library

#### 15. PDM-Library.ps1
**Purpose:** Shared functions used by all scripts

**Never Run Directly** - This is a library, not a standalone script.

**What It Provides:**
- Logging functions (`Write-Log`)
- Database functions (`Exec-SQL`, `Query-SQL`)
- Configuration variables
- Error handling helpers

**Key Functions:**

```powershell
# Logging
Write-Log "Message text"
# Logs to: D:\PDM_Vault\logs\pdm.log

# Database operations (INSERT/UPDATE/DELETE)
Exec-SQL "INSERT INTO items (item_number, revision) VALUES ('csp0030', 'A');"

# Database queries (SELECT)
$result = Query-SQL "SELECT revision FROM items WHERE item_number='csp0030';"

# Configuration
$Global:DBPath    = "D:\PDM_Vault\pdm.sqlite"
$Global:PDMRoot   = "D:\PDM_Vault"
$Global:LogPath   = "D:\PDM_Vault\logs\pdm.log"
```

**Dot-Source Usage:**
All service scripts include:
```powershell
. "$PSScriptRoot\..\PDM-Library.ps1"
```

**Documentation:** See function comments in PDM-Library.ps1

---

## Quick Start Guide

### For Development / Testing

**Terminal 1: File Ingestion**
```powershell
cd D:\PDM_PowerShell
.\CheckIn-Watcher.ps1
```

**Terminal 2: Task Processing**
```powershell
cd D:\PDM_PowerShell
.\Worker-Processor.ps1
```

**Terminal 3: BOM Processing**
```powershell
cd D:\PDM_PowerShell
.\BOM-Watcher.ps1
```

**Terminal 4: Web Server**
```powershell
cd D:\PDM_WebServer
node server.js
```

Then access PDM Browser at: `http://localhost:3000`

---

### For Production / Windows Services

See `D:\PDM_COMPLETE_OVERVIEW.md` - Service Management section for Windows Service installation with NSSM.

---

## Configuration Reference

All scripts use configuration from PDM-Library.ps1:

```powershell
# Database
$Global:DBPath    = "D:\PDM_Vault\pdm.sqlite"
$Global:SQLiteExe = "sqlite3.exe"

# File system paths
$Global:PDMRoot      = "D:\PDM_Vault"
$Global:CADDataRoot  = "D:\PDM_Vault\CADData"
$Global:CheckInPath  = "D:\PDM_Vault\CADData\CheckIn"
$Global:BOMPath      = "D:\PDM_Vault\CADData\BOM"
$Global:ReleasePath  = "D:\PDM_Vault\Release"

# Logging
$Global:LogPath      = "D:\PDM_Vault\logs\pdm.log"

# Tools
$Global:FreeCADExe   = "C:\Program Files\FreeCAD 0.21\bin\FreeCAD.exe"
$Global:ToolsPath    = "D:\FreeCAD\Tools"

# Service timing
$Global:PollInterval = 5  # seconds (Worker-Processor)
$Global:FileWatcherDelay = 800  # milliseconds (CheckIn-Watcher)
```

---

## Troubleshooting

### Service Won't Start
1. Verify path exists: `Test-Path "D:\PDM_Vault\CADData\CheckIn"`
2. Check logs: `Get-Content "D:\PDM_Vault\logs\pdm.log" -Tail 20`
3. Verify permissions on folders

### Database Locked
1. Check for zombie processes: `Get-Process powershell`
2. Verify no manual sqlite3.exe sessions open
3. Restart services: `.\Restart-PDM-Services.ps1`

### File Not Being Processed
1. Check CheckIn-Watcher is running
2. Monitor logs in real-time: `Get-Content "D:\PDM_Vault\logs\pdm.log" -Wait -Tail 50`
3. Verify file naming convention (must start with item number)

### DXF/SVG Not Generating
1. Check Worker-Processor is running
2. Verify FreeCAD path is correct
3. Check task status: `sqlite3.exe "D:\PDM_Vault\pdm.sqlite" "SELECT * FROM work_queue WHERE status='Failed';"`

---

## Related Documentation

- **Complete System Overview:** `D:\PDM_COMPLETE_OVERVIEW.md`
- **Database Schema:** `D:\Skills\database_schema.md`
- **Services Reference:** `D:\Skills\services.md`
- **FreeCAD Automation:** `D:\Skills\freecad_automation.md`
- **Web Server:** `D:\PDM_WebServer\README.md`
- **System Map:** `D:\PDM_SYSTEM_MAP.md`

---

## Script Statistics

| Category | Count | Status |
|----------|-------|--------|
| Production Services | 5 | ✅ Active |
| Development Services | 2 | 🚧 In Development |
| Utility Scripts | 6 | ✅ Active |
| Management Scripts | 1 | ✅ Active |
| Core Library | 1 | ✅ Essential |
| **Total** | **15** | |

---

**Last Updated:** 2025-01-03
**For individual script documentation, see the "Documentation" column in each script section**
