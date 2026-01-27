# PDM System File Map & Directory Structure

**Quick Reference Guide for AI Models and Users to Locate PDM Components**

---

## Directory Structure Overview

```
D:\
├── PDM_Vault/                    ← Core system data & database
│   ├── CADData/                  ← Ingested CAD files organized by type
│   │   ├── CheckIn/              ← Drop files here for ingestion
│   │   ├── STEP/                 ← 3D models
│   │   ├── DXF/                  ← Flat patterns
│   │   ├── SVG/                  ← Technical drawings
│   │   ├── PDF/                  ← Documentation
│   │   ├── Archive/              ← Other files
│   │   ├── Neutral/              ← Creo neutral files
│   │   ├── ParameterUpdate/      ← Parameter change tracking
│   │   ├── BOM/                  ← Bill of Materials text exports
│   │   ├── Release/              ← Items pending release
│   │   └── [Native CAD]/         ← Creo native files (.prt, .asm)
│   ├── Released/                 ← Locked/released items
│   ├── Transfer/                 ← Remote work staging
│   ├── logs/                     ← System logs (pdm.log)
│   ├── pdm.sqlite                ← Central SQLite database
│   └── schema.sql                ← Database schema definition
│
├── PDM_PowerShell/               ← Automation services
│   ├── CheckIn-Watcher.ps1       ← File ingestion service
│   ├── BOM-Watcher.ps1           ← BOM processing service
│   ├── MLBOM-Watcher.ps1         ← Multi-level BOM processing
│   ├── Worker-Processor.ps1      ← Task execution service
│   ├── Release-Watcher.ps1       ← Release workflow (in development)
│   ├── Revise-Watcher.ps1        ← Revision management (in development)
│   ├── Part-Parameter-Watcher.ps1 ← Parameter sync service
│   ├── PDM-Library.ps1           ← Core shared functions
│   ├── Get-BOMCost.ps1           ← BOM cost rollup tool
│   ├── Get-McMasterPrint.ps1     ← Supplier data retrieval
│   ├── PDM-Database-Cleanup.ps1  ← Database maintenance
│   ├── CompareWorkspace.ps1      ← Creo workspace comparison
│   ├── Restart-PDM-Services.ps1  ← Service management
│   ├── Start-PartNumbersList.ps1 ← Part search web server
│   ├── Clear-PDM-Data.ps1        ← DESTRUCTIVE - data reset
│   ├── README.md                 ← Script index & descriptions
│   ├── Use Guides/               ← Documentation
│   │   └── PDM-DATABASE-CLEANUP-GUIDE.md
│   ├── SQLite/                   ← SQLite libraries & tools
│   ├── Backups/                  ← Previous versions
│   └── logs/                     ← Runtime logs
│
├── PDM_WebServer/                ← Web interface (PDM + MRP)
│   ├── server.js                 ← Node.js backend
│   ├── package.json              ← Dependencies
│   ├── public/                   ← Frontend files
│   │   └── index.html            ← UI
│   ├── README.md                 ← Setup & installation
│   ├── DEPLOYMENT.md             ← Quick deployment guide
│   ├── OVERVIEW.md               ← UI/UX design
│   └── QUICK-REFERENCE.md        ← User guide
│
├── FreeCAD/                      ← CAD automation engine
│   └── Tools/
│       ├── flatten_sheetmetal.bat ← DXF generation wrapper
│       ├── Flatten_sheetmetal_portable.py ← DXF generation script
│       ├── create_bend_drawing.bat ← SVG generation wrapper
│       └── Create_bend_drawing_portable.py ← SVG generation script
│
├── Local_Creo_Files/             ← Creo integration
│   └── Powershell/
│       └── LOCAL_PDM_SERVICES_GUIDE.md
│
├── MRP_System/                   ← Manufacturing resource planning
│
├── PDM_Node/                     ← Node.js application
│
├── PDM_Scripts/                  ← Utility scripts
│
├── PDM-Libraries/                ← External libraries
│
├── Skills/                       ← AI skill definitions & references
│   ├── SKILL.md                  ← Claude AI skill definition
│   ├── database_schema.md        ← Database table structures
│   ├── services.md               ← Service configuration reference
│   ├── freecad_automation.md     ← FreeCAD automation reference
│   └── DEVELOPMENT-NOTES-workspace-comparison.md ← Development session notes
│
├── Google_Drive_Converter/       ← Utility
│
├── PDM_COMPLETE_OVERVIEW.md      ← Master documentation
└── PDM_SYSTEM_MAP.md            ← This file
```

---

## Core Documentation Files

### Master Reference
| File | Location | Purpose |
|------|----------|---------|
| **PDM System Complete Overview** | `D:\PDM_COMPLETE_OVERVIEW.md` | Full system architecture, all services, workflows, database schema |
| **System Map (This File)** | `D:\PDM_SYSTEM_MAP.md` | Directory structure and file locations for quick reference |

### Service Documentation
| Service | Primary Doc | Reference | Status |
|---------|------------|-----------|--------|
| **CheckIn-Watcher** | `D:\PDM_COMPLETE_OVERVIEW.md` | `D:\Skills\services.md` | Production |
| **BOM-Watcher** | `D:\PDM_COMPLETE_OVERVIEW.md` | `D:\Skills\services.md` | Production |
| **Worker-Processor** | `D:\PDM_COMPLETE_OVERVIEW.md` | `D:\Skills\services.md` | Production |
| **Part-Parameter-Watcher** | `D:\PDM_COMPLETE_OVERVIEW.md` | `D:\Skills\services.md` | Production |
| **Release-Watcher** | `D:\PDM_COMPLETE_OVERVIEW.md` | `D:\Skills\services.md` | In Development |
| **Revise-Watcher** | `D:\PDM_COMPLETE_OVERVIEW.md` | `D:\Skills\services.md` | In Development |

### Web Interface Documentation
| Doc | Location | Purpose |
|-----|----------|---------|
| **Setup Guide** | `D:\PDM_WebServer\README.md` | Installation, configuration, service management |
| **Deployment** | `D:\PDM_WebServer\DEPLOYMENT.md` | Quick 5-minute setup checklist |
| **UI Overview** | `D:\PDM_WebServer\OVERVIEW.md` | Visual design, features, architecture |
| **Quick Reference** | `D:\PDM_WebServer\QUICK-REFERENCE.md` | Daily operations, shortcuts, troubleshooting |

### Database Documentation
| Doc | Location | Purpose |
|-----|----------|---------|
| **Schema Reference** | `D:\Skills\database_schema.md` | Table structures, SQL patterns, queries |
| **Database Cleanup** | `D:\PDM_PowerShell\Use Guides\PDM-DATABASE-CLEANUP-GUIDE.md` | Orphaned file cleanup, maintenance |

### Tools Documentation
| Tool | Location | Documentation |
|------|----------|-----------------|
| **BOM Cost Rollup** | `D:\PDM_PowerShell\Get-BOMCost.ps1` | `D:\PDM_PowerShell\README.md` |
| **FreeCAD Automation** | `D:\FreeCAD\Tools\` | `D:\Skills\freecad_automation.md` |
| **Creo Integration** | `D:\Local_Creo_Files\Powershell\` | `D:\Local_Creo_Files\Powershell\LOCAL_PDM_SERVICES_GUIDE.md` |
| **PowerShell Scripts** | `D:\PDM_PowerShell\` | `D:\PDM_PowerShell\README.md` |

### Advanced References
| Doc | Location | Purpose |
|-----|----------|---------|
| **AI Skill Definition** | `D:\Skills\SKILL.md` | Claude AI skill triggers and system info |
| **Development Notes** | `D:\Skills\DEVELOPMENT-NOTES-workspace-comparison.md` | Workspace comparison tool development |

---

## Key Locations Quick Lookup

### Where to Drop Files
- **CAD Files for Ingestion:** `D:\PDM_Vault\CADData\CheckIn\`
- **BOM Exports:** `D:\PDM_Vault\CADData\BOM\`
- **Parameter Updates:** `D:\PDM_Vault\CADData\ParameterUpdate\`
- **Items for Release:** `D:\PDM_Vault\Release\`

### Where to Find Data
- **Database:** `D:\PDM_Vault\pdm.sqlite`
- **Processed Files:** `D:\PDM_Vault\CADData\STEP\`, `DXF\`, `SVG\`, `PDF\`
- **Locked Files:** `D:\PDM_Vault\Released\`
- **System Logs:** `D:\PDM_Vault\logs\pdm.log`

### Where to Run Services
- **Windows Services:** Start from `D:\PDM_PowerShell\` scripts
- **Web Server:** Run from `D:\PDM_WebServer\`
- **Web Server (Part Search):** Run `D:\PDM_PowerShell\Start-PartNumbersList.ps1`

### Where to Find Tools
- **BOM Cost Rollup:** `D:\PDM_PowerShell\Get-BOMCost.ps1`
- **Database Cleanup:** `D:\PDM_PowerShell\PDM-Database-Cleanup.ps1`
- **Workspace Comparison:** `D:\PDM_PowerShell\CompareWorkspace.ps1`
- **FreeCAD Scripts:** `D:\FreeCAD\Tools\`

---

## Web Server (PDM + MRP)

### PDM Browser
- **Served on:** `http://localhost:3000`
- **Location:** `D:\PDM_WebServer\`
- **Database:** `D:\PDM_Vault\pdm.sqlite`
- **Features:** Item browsing, BOM navigation, lifecycle history, file tracking

### MRP System Integration
- **Status:** Shared web server infrastructure
- **Database:** Can connect to MRP system databases
- **Configuration:** `D:\PDM_WebServer\server.js`
- **Scalability:** Node.js backend supports multiple database connections

### Part Numbers List (Search Web)
- **Served on:** `http://localhost:3002`
- **Launcher:** `D:\PDM_PowerShell\Start-PartNumbersList.ps1`
- **Purpose:** Quick searchable part database interface

---

## Database Tables

| Table | Location in DB | Purpose |
|-------|---|---------|
| **items** | `D:\PDM_Vault\pdm.sqlite` | Part metadata, revision/iteration, lifecycle state, pricing |
| **files** | `D:\PDM_Vault\pdm.sqlite` | File paths, types, version info |
| **bom** | `D:\PDM_Vault\pdm.sqlite` | Parent/child relationships, quantities |
| **work_queue** | `D:\PDM_Vault\pdm.sqlite` | Tasks for Worker-Processor (DXF/SVG generation) |
| **lifecycle_history** | `D:\PDM_Vault\pdm.sqlite` | Audit trail of state changes |
| **checkouts** | `D:\PDM_Vault\pdm.sqlite` | Active item checkouts |

---

## Service Startup Commands

### Manual Startup (Development)
```powershell
# Terminal 1: File ingestion
powershell -File "D:\PDM_PowerShell\CheckIn-Watcher.ps1"

# Terminal 2: Task processing
powershell -File "D:\PDM_PowerShell\Worker-Processor.ps1"

# Terminal 3: BOM processing
powershell -File "D:\PDM_PowerShell\BOM-Watcher.ps1"

# Terminal 4: Web server
cd D:\PDM_WebServer
node server.js
```

### Windows Service Installation
See `D:\PDM_COMPLETE_OVERVIEW.md` - Service Management section

### Web Server as Service
See `D:\PDM_WebServer\README.md` - Running the Server section

---

## Documentation Hierarchy for AI Models

### Level 1: System Overview
Start with `D:\PDM_COMPLETE_OVERVIEW.md` for architecture and workflow understanding

### Level 2: Component Details
- Services: `D:\Skills\services.md`
- Database: `D:\Skills\database_schema.md`
- FreeCAD: `D:\Skills\freecad_automation.md`

### Level 3: Operational Guides
- Web Server: `D:\PDM_WebServer\README.md`
- Cleanup: `D:\PDM_PowerShell\Use Guides\PDM-DATABASE-CLEANUP-GUIDE.md`
- Scripts: `D:\PDM_PowerShell\README.md`

### Level 4: Advanced References
- Creo Integration: `D:\Local_Creo_Files\Powershell\LOCAL_PDM_SERVICES_GUIDE.md`
- Development: `D:\Skills\DEVELOPMENT-NOTES-workspace-comparison.md`

---

## File Type Summary

| Type | Quantity | Location |
|------|----------|----------|
| Markdown Documentation | 13 files | Various |
| PowerShell Scripts | 15 active | `D:\PDM_PowerShell\` |
| FreeCAD Python Scripts | 2 | `D:\FreeCAD\Tools\` |
| Batch Files | 2 | `D:\FreeCAD\Tools\` |
| Node.js Web Server | 3 files | `D:\PDM_WebServer\` |
| Database | 1 file | `D:\PDM_Vault\pdm.sqlite` |

---

## Version Information

**System Version:** v2.0 (2025-01-01)
- DXF scaling fix resolved
- Manual DXF generation with explicit units
- Enhanced Worker-Processor logging
- Part-Parameter-Watcher added

**Key Dependencies:**
- PowerShell 5.1+
- Node.js (LTS)
- FreeCAD 0.20+
- SQLite 3.x
- Creo Parametric (optional)

---

## Related Systems

- **MRP System:** `D:\MRP_System\` (integrated via web server)
- **FreeCAD:** CAD automation for DXF/SVG generation
- **Creo Parametric:** Native CAD integration (optional)
- **SQLite:** Core database

---

**Last Updated:** 2025-01-03
**For Quick Navigation:** Use this map to locate any PDM component or documentation
