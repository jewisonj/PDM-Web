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

- `PDM_PowerShell/` - Automation services and scripts
- `PDM_WebServer/` - Web-based PDM browser
- `FreeCAD/Tools/` - CAD automation scripts
- `PDM_Vault/` - Data storage (not tracked in Git)
- `Skills/` - AI assistant skill definitions

## Documentation

- **Master Documentation:** `PDM_COMPLETE_OVERVIEW.md`
- **System Map:** `PDM_SYSTEM_MAP.md`
- **Web Server Setup:** `PDM_WebServer/README.md`
- **Database Schema:** `Skills/database_schema.md`

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