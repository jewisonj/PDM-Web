# PDM System - Product Data Management

A folder-based Product Data Management system for managing CAD files, BOM tracking, lifecycle management, and automated manufacturing document generation.

## System Overview

- **Database:** SQLite-based with PowerShell automation services
- **CAD Integration:** FreeCAD automation for DXF/SVG generation
- **Web Interface:** Node.js-based browser for item/BOM navigation
- **Creo Integration:** Optional native CAD file support

## Quick Start

See `PDM_COMPLETE_OVERVIEW.md` for full system architecture and setup instructions.

## Directory Structure

- `frontend/` - Vue 3 + Vite web frontend
- `backend/` - FastAPI Python backend
- `worker/` - FreeCAD Docker worker
- `scripts/` - Migration and deployment scripts
- `FreeCAD/Tools/` - CAD automation scripts
- `Documentation/` - System documentation
- `PDM_Vault/` - Legacy data storage (migration pending)
- `Legacy/` - Archived legacy system folders (PDM_PowerShell, PDM_WebServer, etc.)

## Documentation

- **Migration Plan:** `Documentation/27-WEB-MIGRATION-PLAN.md`
- **Legacy Overview:** `Documentation/02-PDM-COMPLETE-OVERVIEW.md`
- **Database Schema:** `Documentation/03-DATABASE-SCHEMA.md`

## Requirements

- Windows 10/11 or Windows Server 2016+
- PowerShell 5.1+
- SQLite 3.x
- FreeCAD 0.20+ (for CAD automation)
- Node.js LTS (for web interface)

## License

NONE

## Version

Current: v2.0 (2025-01-01)