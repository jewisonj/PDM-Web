# PDM-Web - Product Data Management System

A modern web-based Product Data Management system for managing CAD files, BOMs, lifecycle management, MRP/manufacturing workflows, and automated sheet metal processing.

## System Overview

**Current Version:** v3.9.2 (2026-07-09)

- **Frontend:** Vue 3 + TypeScript + Vite (desktop-first SPA)
- **Backend:** FastAPI (Python 3) REST API
- **Database:** Supabase PostgreSQL (cloud-hosted)
- **Authentication:** Supabase Auth (JWT-based)
- **File Storage:** Supabase Storage (CAD files, PDFs, DXFs)
- **CAD Processing:** FreeCAD Docker container for DXF/SVG generation
- **AI Assistant:** Claude Sonnet 4.5 for natural-language PDM queries

## Quick Start

**See `PORTS.md` first** - Critical port configuration (frontend 5174, backend 8001)

```bash
# 1. Clone repository
git clone <repo-url> pdm-web
cd pdm-web

# 2. Backend setup
cd backend
pip install -r requirements.txt
# Create .env from .env.example and add your Supabase keys
uvicorn app.main:app --reload --port 8001

# 3. Frontend setup (in new terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:5174 and log in with your Supabase Auth credentials.

**Full setup guide:** `Documentation/17-QUICK-START-CHECKLIST.md`

## Directory Structure

```
pdm-web/
├── frontend/               # Vue 3 + Vite web application
├── backend/                # FastAPI Python REST API
├── worker/                 # FreeCAD Docker worker (DXF/SVG generation)
├── FreeCAD/Tools/          # Custom FreeCAD automation scripts
├── Local_Creo_Files/       # Creo workspace integration
├── Documentation/          # Complete system documentation (34 files)
├── Legacy/                 # Archived legacy components
│   ├── PDM_Vault/          # Old SQLite database (migrated)
│   ├── PDM_PowerShell/     # Old PowerShell services (replaced)
│   └── PDM_WebServer/      # Old Node.js server (replaced)
├── docker-compose.yml      # FreeCAD worker container
├── PORTS.md                # Port configuration reference
└── CLAUDE.md               # AI assistant project instructions
```

## Key Features

**PDM Core:**
- Item/part database with revision/iteration tracking
- Multi-level BOM management with circular reference detection
- CAD file storage (STEP, PDF, DXF, SVG, images)
- Lifecycle states (Design → Review → Released → Obsolete)
- Automatic DXF flat pattern generation from STEP files
- Part number generator with prefix system

**MRP/Manufacturing:**
- Project scheduling with critical path and resource loading
- Build Tracker printable sheet (shop floor checklists)
- Build Book (day-by-day manufacturing work packages)
- Section print sets (task-sized PDF bundles with QR codes)
- Routing/operations management
- Material cost estimation and BOM cost rollup
- Raw material pricing database

**AI Assistant:**
- Natural language queries ("How many parts in csa00010?")
- BOM expansion and part counting
- File download link generation
- MRP project and cost queries
- SSE streaming responses with tool status

## Documentation

**Start here:**
- `PORTS.md` - Port configuration (MUST READ)
- `Documentation/00-TABLE-OF-CONTENTS.md` - Master index (34 docs)
- `Documentation/01-PDM-SYSTEM-MAP.md` - Architecture diagram
- `Documentation/02-PDM-COMPLETE-OVERVIEW.md` - Complete reference

**Common tasks:**
- `Documentation/17-QUICK-START-CHECKLIST.md` - First-time setup
- `Documentation/20-COMMON-WORKFLOWS.md` - Daily operations
- `Documentation/19-TROUBLESHOOTING-DECISION-TREE.md` - Problem diagnosis

**Recent features:**
- `Documentation/33-AI-ASSISTANT.md` - AI Assistant (v3.9.2)
- `Documentation/32-BUILD-BOOK.md` - Build Book (v3.9.1)
- `Documentation/31-BUILD-TRACKER-SHEET.md` - Build Tracker (v3.8)
- `Documentation/29-NESTING-AUTOMATION.md` - DXF nesting (v3.6)

## Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Frontend | Vue 3 | Composition API, TypeScript |
| Build Tool | Vite | Dev server + HMR |
| Backend | FastAPI | Python 3.14+ |
| Database | PostgreSQL | Supabase (cloud) |
| Auth | Supabase Auth | JWT tokens |
| Storage | Supabase Storage | CAD files, PDFs |
| CAD Worker | FreeCAD | Docker (amrit3701/freecad-cli) |
| AI | Claude Sonnet 4.5 | Anthropic API |

## Development Ports

**CRITICAL:** Always check `PORTS.md` before starting services!

- **Frontend:** http://localhost:5174 (Vite dev server)
- **Backend:** http://localhost:8001 (FastAPI + Uvicorn)
- **API Docs:** http://localhost:8001/docs (Swagger UI)

**Never assume default ports!** Backend is 8001, not 8000.

## Requirements

**Development:**
- Python 3.10+ (tested on 3.14.2)
- Node.js LTS (v18+)
- Docker Desktop (for FreeCAD worker)
- Git
- Supabase account (cloud database + auth + storage)

**Optional:**
- PowerShell 5.1+ (for Creo upload bridge)
- Creo Parametric (for local CAD integration)

## License

Internal use only - no license specified

## Support

For issues, questions, or feature requests, see:
- `Documentation/19-TROUBLESHOOTING-DECISION-TREE.md`
- `TODO.md` - Known issues and roadmap
- `TECHNICAL-DEBT-AUDIT.md` - Tracked technical debt