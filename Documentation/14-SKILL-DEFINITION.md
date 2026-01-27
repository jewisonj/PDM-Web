---
name: pdm-system
description: Folder-based Product Data Management system with SQLite tracking, automated PowerShell services, and FreeCAD/CAD integration. Use when working with Jack's PDM system for tasks involving part numbers, revisions, file processing workflows, database queries, service management, or CAD automation scripts. Triggers include references to items, lifecycle states, CheckIn folder, CADData folders (STEP/DXF/SVG/PDF/BOM), work_queue, CheckIn-Watcher/BOM-Watcher/Release-Watcher/Worker-Processor services, FreeCAD batch processing, or BOM extraction from tree tool exports.
---

# PDM System

Jack's custom folder-based Product Data Management (PDM) system for managing CAD files, lifecycle tracking, and automated manufacturing document generation.

## System Architecture

### Folder Structure
```
D:\PDM_Vault\
├── CADData\
│   ├── CheckIn\         (monitored by CheckIn-Watcher)
│   ├── BOM\             (monitored by BOM-Watcher - tree exports)
│   ├── STEP\           (3D models)
│   ├── DXF\            (flattened patterns)
│   ├── SVG\            (technical drawings)
│   ├── PDF\            (documentation)
│   ├── Archive\        (other files)
│   └── [CAD native files - .prt, .asm, .drw]
├── logs\
│   └── pdm.log
└── pdm.sqlite          (database)

D:\PDM_PowerShell\      (service scripts)
D:\FreeCAD\Tools\       (batch automation scripts)
```

### File Types Tracked
- **CAD**: .prt, .asm, .drw (Creo Parametric native)
- **STEP**: .step, .stp (3D interchange format)
- **DXF**: .dxf (2D flat patterns for manufacturing)
- **SVG**: .svg (technical drawings with dimensions)
- **PDF**: .pdf (documentation)

### Item Numbering Convention
Format: `ABC####` or `ABC#####` (3 letters + 4-6 digits, e.g., `csp0030`, `wma20120`)
- Lowercase normalized in database
- Base filename determines item linkage

## Database Schema

See `references/database_schema.md` for complete table structure. Key tables:
- **items**: Part metadata, lifecycle state, revision/iteration
- **files**: File tracking with paths, types, timestamps
- **work_queue**: Task queue for automated processing
- **bom**: Bill of Materials relationships
- **lifecycle_history**: State change audit trail
- **checkouts**: File checkout tracking

## PowerShell Services

Four Windows services handle automation:

### CheckIn-Watcher
**Purpose:** Monitors CheckIn folder, classifies files, triggers processing

**Key Functions:**
- File classification by extension and naming
- Auto-creates item records (starts at A.1, Design state)
- Moves files to appropriate folders (STEP/, DXF/, SVG/, etc.)
- Registers files in database
- Queues DXF/SVG regeneration when STEP files update

**Special Handling:**
- **DXF/SVG**: Filename parsed to link to base item (e.g., `csp0030_flat.dxf` → `csp0030`)
- **File overwrites**: Bumps file iteration, not item iteration

### BOM-Watcher
**Purpose:** Processes BOM tree exports from Creo mapkey

**Process:**
1. Monitors `BOM\` folder for .txt files (tree tool exports)
2. Parses header for parent assembly
3. Extracts child parts (3+ leading spaces to exclude parent)
4. Parses columns by fixed positions: Description, Project, Material, Mass, Thickness, Cut Length
5. Auto-creates items if they don't exist
6. Deletes old BOM entries for assembly
7. Inserts new BOM relationships with quantities
8. Updates item properties (description, material, mass, thickness, project, cut_length)
9. Deletes processed txt file

**Column Parsing:**
- Fixed positions based on header alignment
- Handles missing/empty columns correctly
- Material, mass, thickness extracted from tree export

### Worker-Processor
**Purpose:** Executes queued tasks from work_queue table

**Task Types:**
- `GENERATE_DXF`: Calls `flatten_sheetmetal.bat` to create flat patterns from STEP
- `GENERATE_SVG`: Calls `create_bend_drawing.bat` to create technical drawings from STEP
- `PARAM_SYNC`: Syncs parameters from CAD files (future)
- `SYNC`: General sync operations (future)

**Process:**
1. Polls work_queue for pending tasks
2. Marks task as 'Processing'
3. Executes batch file (FreeCAD automation)
4. Generated files placed in CheckIn folder
5. CheckIn-Watcher detects and registers them
6. Task marked 'Completed' or 'Failed'

### Release-Watcher & Revise-Watcher
**Purpose:** Manage lifecycle transitions and revisions

See `references/services.md` for configuration, management commands, and troubleshooting.

## FreeCAD Automation

Batch files in `D:\FreeCAD\Tools\`:
- **flatten_sheetmetal.bat**: STEP → DXF (sheet metal unfolding)
- **create_bend_drawing.bat**: STEP → SVG (technical drawings)

Both called by Worker-Processor, output to CheckIn folder for automatic registration.

See `references/freecad_automation.md` for script details and current development work.

## PDM Browser

**Status:** In Development (D:\PDM_WebServer)

Modern Node.js-based web browser for PDM system currently being implemented. Features will include:
- Real-time REST API
- Item search and filtering
- BOM tree navigation
- File preview and management
- Lifecycle history tracking

**Note:** Legacy PowerShell-based static HTML generator has been archived.

## Common Workflows

**Check in a new STEP file:**
1. Copy file to `CheckIn\` folder (e.g., `csp0030.step`)
2. CheckIn-Watcher detects file
3. Item `csp0030` created (A.1, Design) if new
4. File moved to `STEP\` folder
5. File registered in database
6. If DXF/SVG exist for this item, regeneration tasks queued

**Generate manufacturing documents:**
1. STEP file exists for item
2. Worker-Processor picks up `GENERATE_DXF` task
3. Calls `flatten_sheetmetal.bat` with STEP input
4. DXF created in `CheckIn\`
5. CheckIn-Watcher detects and moves to `DXF\`
6. Same process for SVG via `GENERATE_SVG` task

**BOM update from tree export:**
1. In Creo, run mapkey to export assembly tree to txt file
2. File saved to `BOM\` folder (e.g., `wma20120.txt`)
3. BOM-Watcher detects file
4. Parses parent assembly from header
5. Extracts child parts with quantities
6. Updates `bom` table and item properties
7. Deletes txt file

## Key Scripts

- **PDM-Library.ps1**: Core functions (Exec-SQL, Query-SQL, Write-Log)
- **CheckIn-Watcher.ps1**: File monitoring and classification
- **BOM-Watcher.ps1**: BOM tree export processor
- **Worker-Processor.ps1**: Task execution engine
- **Release-Watcher.ps1**: Release workflow automation
- **Revise-Watcher.ps1**: Revision management
- **Restart-PDM-Services.ps1**: Service restart utility
- **CompareWorkspace.ps1**: Workspace comparison via CreoJS
- **Part-Parameter-Watcher.ps1**: Parameter sync from CAD files

## Configuration

**Paths** (in PDM-Library.ps1):
- `$Global:PDMRoot = "D:\PDM_Vault"`
- `$Global:DBPath = "D:\PDM_Vault\pdm.sqlite"`
- SQLite accessed via `sqlite3.exe` command-line tool

**FreeCAD** (in CheckIn-Watcher.ps1):
- `$Global:FreeCADExe = "C:\Program Files\FreeCAD 0.21\bin\FreeCAD.exe"`
- Batch scripts in `D:\FreeCAD\Tools\`
