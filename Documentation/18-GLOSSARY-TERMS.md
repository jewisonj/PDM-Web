# PDM System - Glossary of Terms

**Quick Reference for PDM Terminology**
**Related Docs:** [01-PDM-SYSTEM-MAP.md](01-PDM-SYSTEM-MAP.md), [02-PDM-COMPLETE-OVERVIEW.md](02-PDM-COMPLETE-OVERVIEW.md)

---

## 📖 Complete Glossary

### A

**Assembly**
- A product made up of multiple component parts
- Has children in the BOM (Bill of Materials)
- Example: `wma20120` (a motor assembly containing bearings, shafts, etc.)
- Opposite: Part

**Audit Trail**
- Complete record of all changes to an item
- Stored in `lifecycle_history` table
- Shows who changed what, when, and from/to what state
- Used for compliance and traceability

### B

**BOM** (Bill of Materials)
- List of all parts and assemblies that make up a product
- Stored in `bom` table
- Single-level: Only direct children of assembly (not grandchildren)
- Multi-level: Shows full hierarchy including subassemblies
- Created from Creo tree exports

**BOM-Watcher**
- PowerShell service that processes BOM files
- Monitors: `D:\PDM_Vault\CADData\BOM\` folder
- Extracts parent/child relationships
- Updates item properties (material, mass, cost, etc.)

**Batch File**
- Windows script file (.bat) that executes commands
- Example: `flatten_sheetmetal.bat` (calls FreeCAD for DXF generation)

### C

**CAD** (Computer-Aided Design)
- Digital design files (Creo, AutoCAD, etc.)
- PDM supports: Creo `.prt`, `.asm`, `.drw` files
- Stored in: `D:\PDM_Vault\CADData\`

**CheckIn** (or Check-In)
- Process of submitting a new file to PDM
- Files placed in: `D:\PDM_Vault\CADData\CheckIn\`
- CheckIn-Watcher automatically processes them
- Creates or updates items in database

**CheckIn-Watcher**
- PowerShell service that monitors check-in folder
- Monitors: `D:\PDM_Vault\CADData\CheckIn\`
- Classifies files by type
- Registers files in database
- Queues DXF/SVG generation if needed

**Circular Reference**
- When an item contains itself (directly or indirectly) in its BOM
- Causes infinite loops in cost calculations
- Example: Assembly A contains Assembly A (invalid)
- PDM detects and skips circular references

**Checkout** (or Check-Out)
- Locks an item for editing
- Prevents concurrent access by multiple users
- Stored in `checkouts` table
- Row deleted when item checked back in

**CreoJS**
- JavaScript interface for Creo applications
- Allows web-based interaction with Creo
- Used in workspace comparison tool

### D

**Design** (Lifecycle State)
- Initial state when item is created
- Item is under active development
- Can be modified, revised, iterated
- Transition: Design → Released → Obsolete

**DXF** (Drawing Exchange Format)
- 2D flat pattern file for sheet metal parts
- Generated from STEP files via FreeCAD
- Contains outline, holes, bend lines
- Sent to manufacturing for cutting/bending

**DXF Generation**
- Automated process creating flat patterns from 3D STEP files
- Handles sheet metal unfolding
- Uses FreeCAD SheetMetal workbench
- Task: `GENERATE_DXF` in work_queue

### E

**Execution Policy**
- PowerShell security setting
- Controls which scripts can run
- PDM requires: `RemoteSigned` or `Unrestricted`
- Set with: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned`

### F

**FreeCAD**
- Open-source 3D CAD software
- Used for DXF/SVG generation from STEP files
- Runs headless (no GUI) for automation
- Located: `C:\Program Files\FreeCAD 0.21\bin\`

**File Iteration**
- Version number for individual files
- Increments each time file is overwritten
- Example: File 1.1, 1.2, 1.3 (file version 1, iterations 1-3)
- Different from: Item iteration

**File Type**
- Classification of file
- Values: CAD, STEP, DXF, SVG, PDF, NEUTRAL_ASM, ARCHIVE, OTHER
- Determines destination folder
- Example: `.step` → STEP folder

**FileSystemWatcher**
- PowerShell object that monitors folders
- Triggers on file creation, deletion, modification
- Used by CheckIn-Watcher, BOM-Watcher, etc.
- Provides real-time file monitoring

### G

**Gauge**
- Standard thickness measurement for sheet metal
- Example: 16 gauge steel
- Noted on manufacturing documents (SVG)

### H

**Headless Mode**
- Running application without GUI (graphical interface)
- FreeCAD runs headless via `FreeCADCmd.exe`
- Enables batch processing and automation
- No visual feedback; output via console

### I

**Iteration**
- Version number within a revision
- Format: Revision.Iteration (e.g., A.1, A.2, B.1)
- Item iteration increments on major changes
- File iteration increments on file overwrites
- Example: Item csp0030 A.1 has file csp0030_flat.dxf version 1

**Item**
- Single product component or assembly
- Identified by item number (e.g., csp0030)
- Stored in `items` table
- Can have multiple files (STEP, DXF, SVG, PDF, etc.)

**Item Number**
- Unique identifier for a part or assembly
- Format: 3 letters + 4-6 digits
- Examples: csp0030, wma20120, stp00100
- Normalized to lowercase in database
- Must match filename pattern for auto-linking

**Item Iteration**
- Version number within an item revision
- Increments when item significantly changes
- Stored in `items.iteration` field
- Example: Item A.1, A.2, A.3 (revision A, iterations 1-3)
- Different from: File iteration

### K

**K-Factor**
- Bend compensation value for sheet metal
- Accounts for material springback
- Default: 0.35
- Affects flat pattern accuracy
- Configurable in DXF generation scripts

### L

**Lifecycle History**
- Audit trail table (`lifecycle_history`)
- Records every state transition
- Fields: old_state, new_state, old_revision, new_revision, changed_by, changed_at
- Used for compliance and traceability

**Lifecycle State**
- Current status of an item
- Values: Design, Released, Obsolete (extensible)
- Stored in `items.lifecycle_state`
- Controls access and modification rights
- Transitions: Design → Released → Obsolete

### M

**Manufacturing Document**
- Drawings and specifications for production
- Examples: DXF (flat patterns), SVG (technical drawings), PDF (specs)
- Generated automatically from CAD files
- Contains dimensions, materials, notes

**McMaster-Carr**
- Online supplier of standard parts
- PDM can fetch supplier info via Get-McMasterPrint.ps1
- Used for sourcing fasteners, stock parts
- Integration optional

**MLBOM** (Multi-Level BOM)
- BOM with nested subassembly hierarchy
- Shows all levels of assembly tree
- Processed by MLBOM-Watcher.ps1
- More complex than single-level BOM

**MRP** (Manufacturing Resource Planning)
- System for managing manufacturing operations
- PDM web server can serve MRP data
- Integrates with PDM for inventory, BOM, costing
- Related: ERP (Enterprise Resource Planning)

### N

**NEU** (Neutral File)
- Creo neutral format file
- Extensions: `.neu` (part), `_asm.neu` (assembly)
- Contains BOM data from Creo
- Processed by CheckIn-Watcher for BOM extraction
- Automatically deleted after processing

**Node.js**
- JavaScript runtime for server applications
- Used for PDM web server backend
- LTS (Long-Term Support) version recommended
- Installation: `https://nodejs.org/`

**NSSM** (Non-Sucking Service Manager)
- Windows utility for managing services
- Converts scripts/applications to Windows services
- Used to install PDM services to run on boot
- Download: `https://nssm.cc/`

### O

**Obsolete** (Lifecycle State)
- Final state for deprecated items
- Item no longer manufactured
- Kept for historical records
- Read-only in many systems
- Transition: Designed → Released → Obsolete

### P

**PARAM_SYNC** (Task Type)
- Work queue task for parameter synchronization
- Updates item properties from CAD parameters
- Queued by CheckIn-Watcher when CAD files checked in
- Processed by Worker-Processor

**Part-Parameter-Watcher**
- PowerShell service for parameter updates
- Monitors: `D:\PDM_Vault\CADData\ParameterUpdate\`
- Updates individual item properties
- Similar to BOM-Watcher but for single items

**Part** (vs Assembly)
- Single manufactured component
- No children in BOM
- Examples: bolt, bearing, flat sheet metal
- Opposite: Assembly

**PDF**
- Portable Document Format
- Used for documentation, specs, drawings
- PDM stores in: `D:\PDM_Vault\CADData\PDF\`

**PowerShell**
- Windows command-line scripting language
- Used for all PDM automation
- Version 5.1+ required
- Script extension: `.ps1`

### Q

**Query** (SQL)
- Database request to retrieve, insert, update, or delete data
- Example: `SELECT * FROM items WHERE item_number='csp0030'`
- PDM uses SQLite queries
- Executed via `Query-SQL` or `sqlite3.exe`

### R

**Released** (Lifecycle State)
- Item has been approved for production
- Files are locked/read-only
- Cannot be modified without revision
- Stored in: `D:\PDM_Vault\Released\`

**Release-Watcher**
- PowerShell service for release workflows (IN DEVELOPMENT)
- Will handle Design → Released transitions
- Not yet used in single-user systems
- Planned for multi-user support

**Revision**
- Letter designation for major changes (A, B, C, etc.)
- Different from iteration
- Format: Revision.Iteration (e.g., A.2, B.1)
- Incremented by Revise-Watcher (in development)
- Starts at A for new items

**Revise-Watcher**
- PowerShell service for revision management (IN DEVELOPMENT)
- Will increment revision letters (A → B → C)
- Not yet used in single-user systems
- Planned for multi-user support

### S

**Service** (Windows Service)
- Background process running on Windows
- Starts automatically on boot
- PDM services: CheckIn-Watcher, Worker-Processor, BOM-Watcher, etc.
- Managed via `Get-Service`, `Start-Service`, `Stop-Service`

**SheetMetal Workbench**
- FreeCAD module for sheet metal operations
- Handles unfolding 3D parts into 2D patterns
- Used in `flatten_sheetmetal.bat`
- Generates DXF output

**SQLite** (or SQLite3)
- Lightweight SQL database engine
- File-based (single file: `pdm.sqlite`)
- No server required
- Tool: `sqlite3.exe`

**SQL** (Structured Query Language)
- Language for database queries
- PDM uses: SELECT, INSERT, UPDATE, DELETE
- Syntax: `SELECT * FROM table_name WHERE condition`

**STEP** (Standard for the Exchange of Product Data)
- 3D model file format (.step, .stp)
- Universal CAD format
- Contains 3D geometry and metadata
- Source for DXF and SVG generation

**SVG** (Scalable Vector Graphics)
- 2D vector drawing format
- Used for technical drawings
- Contains dimensions, annotations, bend lines
- Generated from STEP files via FreeCAD

**SVG Generation**
- Automated process creating technical drawings from STEP files
- Includes dimensions, material callouts, bend annotations
- Task: `GENERATE_SVG` in work_queue
- Uses FreeCAD TechDraw workbench

### T

**Task** (Work Queue)
- Automated job queued for processing
- Types: GENERATE_DXF, GENERATE_SVG, PARAM_SYNC, SYNC
- States: Pending, Processing, Completed, Failed
- Processed by Worker-Processor service

**TechDraw Workbench**
- FreeCAD module for creating technical drawings
- Generates 2D views from 3D models
- Creates dimensions and annotations
- Used in `create_bend_drawing.bat`

### U

**Unit**
- Measurement unit for dimensions
- PDM uses: millimeters (mm) for DXF, mixed for SVG
- Specified in DXF header
- Important for manufacturing accuracy

### W

**Watcher** (Service)
- PowerShell service that monitors a folder
- Triggers on file events (create, modify, delete)
- Examples: CheckIn-Watcher, BOM-Watcher, Release-Watcher
- Real-time automation

**Where-Used**
- Reverse BOM lookup: which assemblies contain this part?
- Example: Part X is used in Assembly A, Assembly B, Assembly C
- Stored in `bom` table (query child_item)
- Displayed in web interface

**Worker-Processor**
- PowerShell service for task execution
- Monitors: `work_queue` table
- Executes: GENERATE_DXF, GENERATE_SVG tasks
- Calls: FreeCAD batch scripts for document generation

**Workflow**
- Series of steps to accomplish a task
- Example: Check-in → Classify → Register → Queue → Generate → Register
- Examples: [COMMON-WORKFLOWS.md](COMMON-WORKFLOWS.md)

**Work Queue**
- Task queue table in database
- Stores tasks to be processed: `work_queue` table
- Fields: task_id, item_number, file_path, task_type, status
- Populated by CheckIn-Watcher, processed by Worker-Processor

### Z

**Zone** (Time Zone)
- Relevant for timestamps in logs
- PDM logs stored with timestamps
- Important for troubleshooting and auditing

---

## 📊 Quick Reference Tables

### File Type Classifications

| Extension | File Type | Destination |
|-----------|-----------|-------------|
| .prt, .asm, .drw | CAD | CADData\ |
| .step, .stp | STEP | STEP\ |
| .dxf | DXF | DXF\ |
| .svg | SVG | SVG\ |
| .pdf | PDF | PDF\ |
| .neu | NEUTRAL_ASM | Neutral\ |
| _asm.neu | NEUTRAL_ASM | Neutral\ |
| other | ARCHIVE | Archive\ |

### Lifecycle State Progression

```
Design (Initial) → Released (Approved) → Obsolete (Deprecated)
```

### Item Number Format

```
csp0030    = 3 letters + 4-6 digits
wma20120   = Pattern: [a-z]{3}\d{4,6}
stp01000   = Normalized to lowercase
```

### Revision & Iteration Format

```
A.1 = Revision A, Iteration 1
B.3 = Revision B, Iteration 3
C.2 = Revision C, Iteration 2
```

### Database Tables Summary

| Table | Purpose |
|-------|---------|
| items | Part/assembly metadata |
| files | File tracking |
| bom | Parent/child relationships |
| work_queue | Task queue |
| lifecycle_history | State change audit trail |
| checkouts | Active checkouts |

### Service Names & Purpose

| Service | Purpose |
|---------|---------|
| CheckIn-Watcher | File ingestion |
| BOM-Watcher | BOM processing |
| Worker-Processor | Task execution |
| Part-Parameter-Watcher | Parameter updates |
| Release-Watcher | Release workflow (in dev) |
| Revise-Watcher | Revision management (in dev) |

### Web Server Ports

| Port | Service |
|------|---------|
| 3000 | PDM Browser |
| 3002 | Part Numbers List |
| 8082 | Workspace Comparison |

---

## 🔍 Finding Definitions

**By Category:**
- **File Types:** See "File Type Classifications" table
- **Services:** See "Service Names & Purpose" table
- **States:** See "Lifecycle State Progression"
- **Database:** See "Database Tables Summary"

**Alphabetically:** Use Ctrl+F to search this document

**By Task:** See related guides
- Check-in operations: [COMMON-WORKFLOWS.md](COMMON-WORKFLOWS.md)
- Service management: [05-POWERSHELL-SCRIPTS-INDEX.md](05-POWERSHELL-SCRIPTS-INDEX.md)
- Web server: [08-PDM-WEBSERVER-README.md](08-PDM-WEBSERVER-README.md)

---

**Last Updated:** 2025-01-03
**Version:** 2.0
**Related:** [02-PDM-COMPLETE-OVERVIEW.md](02-PDM-COMPLETE-OVERVIEW.md), [01-PDM-SYSTEM-MAP.md](01-PDM-SYSTEM-MAP.md)
