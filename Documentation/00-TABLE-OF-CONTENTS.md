# PDM-Web Documentation - Table of Contents

**Last Updated:** 2026-01-30
**System:** PDM-Web (Product Data Management)
**Stack:** Vue 3 + FastAPI + Supabase + Docker

---

## Quick Start

New to PDM-Web? Read these in order:

1. `01-PDM-SYSTEM-MAP.md` -- System architecture and project layout
2. `02-PDM-COMPLETE-OVERVIEW.md` -- Full system overview, tech stack, API, database

---

## Documentation Index

### Section 1: System Overview and Architecture

| # | File | Description |
|---|------|-------------|
| 00 | `00-TABLE-OF-CONTENTS.md` | This file. Master index of all documentation. |
| 01 | `01-PDM-SYSTEM-MAP.md` | System architecture diagram, project structure, data flow, technology layers. |
| 02 | `02-PDM-COMPLETE-OVERVIEW.md` | Comprehensive system reference: tech stack, database schema, API endpoints, frontend views, auth, file storage, FreeCAD Docker, upload bridge, item numbering. |

### Section 2: Database and Data Structure

| # | File | Description |
|---|------|-------------|
| 03 | `03-DATABASE-SCHEMA.md` | Supabase PostgreSQL table definitions, field descriptions, relationships, common queries. |

### Section 3: Services and Automation

| # | File | Description |
|---|------|-------------|
| 04 | `04-SERVICES-REFERENCE.md` | Backend API service configuration, Supabase client setup, CORS, environment variables. |
| 05 | `05-POWERSHELL-SCRIPTS-INDEX.md` | Upload bridge scripts: PDM-Upload-Service, PDM-Upload-Functions, PDM-BOM-Parser. |

### Section 4: Tools and Manufacturing

| # | File | Description |
|---|------|-------------|
| 06 | `06-BOM-COST-ROLLUP-GUIDE.md` | BOM cost calculation and rollup procedures. |
| 07 | `07-PDM-DATABASE-CLEANUP-GUIDE.md` | Database maintenance and orphaned record cleanup. |

### Section 5: Frontend Application

| # | File | Description |
|---|------|-------------|
| 08 | `08-PDM-WEBSERVER-README.md` | Vue 3 frontend setup, configuration, and build process. |
| 09 | `09-PDM-WEBSERVER-DEPLOYMENT.md` | Production deployment guide for FastAPI + Vue SPA. |
| 10 | `10-PDM-WEBSERVER-OVERVIEW.md` | Frontend UI design, views, components, and user experience. |
| 11 | `11-PDM-WEBSERVER-QUICK-REFERENCE.md` | Daily operations and common tasks reference. |

### Section 6: CAD Processing and Docker

| # | File | Description |
|---|------|-------------|
| 12 | `12-FREECAD-AUTOMATION.md` | FreeCAD Docker container, DXF flat pattern generation, SVG bend drawing generation. |
| 29 | `29-NESTING-AUTOMATION.md` | DXF nesting worker, Bottom-Left Fill algorithm, project-scoped sheet metal nesting. |

### Section 7: Integration

| # | File | Description |
|---|------|-------------|
| 13 | `13-LOCAL-PDM-SERVICES-GUIDE.md` | Local upload bridge integration with the PDM-Web API. |
| 14 | `14-SKILL-DEFINITION.md` | AI assistant skill definition for PDM-Web context. |

### Section 8: Development and Reference

| # | File | Description |
|---|------|-------------|
| 15 | `15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md` | Development session notes and lessons learned. |

### Section 9: Operations

| # | File | Description |
|---|------|-------------|
| 17 | `17-QUICK-START-CHECKLIST.md` | First-time setup checklist. |
| 18 | `18-GLOSSARY-TERMS.md` | Terminology and acronym reference. |
| 19 | `19-TROUBLESHOOTING-DECISION-TREE.md` | Problem diagnosis and resolution. |
| 20 | `20-COMMON-WORKFLOWS.md` | Step-by-step guides for typical tasks. |
| 21 | `21-BACKUP-RECOVERY-GUIDE.md` | Data protection and recovery. |
| 22 | `22-PERFORMANCE-TUNING-GUIDE.md` | Optimization strategies. |
| 23 | `23-SYSTEM-CONFIGURATION.md` | Configuration reference for all components. |
| 24 | `24-VERSION-HISTORY.md` | Release notes and version history. |
| 25 | `25-INTEGRATION-EXAMPLES.md` | Custom extension and integration examples. |
| 26 | `26-SECURITY-HARDENING.md` | Security configuration guide. |
| 27 | `27-WEB-MIGRATION-PLAN.md` | Web migration planning and phase breakdown. |

---

## Navigation by Use Case

### Understanding the System
1. `01-PDM-SYSTEM-MAP.md` -- architecture and structure
2. `02-PDM-COMPLETE-OVERVIEW.md` -- comprehensive reference
3. `03-DATABASE-SCHEMA.md` -- data model

### Setting Up Development
1. `17-QUICK-START-CHECKLIST.md` -- initial setup
2. `23-SYSTEM-CONFIGURATION.md` -- environment configuration
3. `02-PDM-COMPLETE-OVERVIEW.md` -- development commands

### Working with the API
1. `02-PDM-COMPLETE-OVERVIEW.md` -- API endpoint reference
2. `04-SERVICES-REFERENCE.md` -- backend service details
3. `03-DATABASE-SCHEMA.md` -- data structures

### Frontend Development
1. `08-PDM-WEBSERVER-README.md` -- Vue app setup
2. `10-PDM-WEBSERVER-OVERVIEW.md` -- UI design and views
3. `11-PDM-WEBSERVER-QUICK-REFERENCE.md` -- daily tasks

### Deployment
1. `09-PDM-WEBSERVER-DEPLOYMENT.md` -- production deployment
2. `26-SECURITY-HARDENING.md` -- security configuration
3. `22-PERFORMANCE-TUNING-GUIDE.md` -- optimization

### CAD Processing
1. `12-FREECAD-AUTOMATION.md` -- FreeCAD Docker setup
2. `13-LOCAL-PDM-SERVICES-GUIDE.md` -- upload bridge

### Troubleshooting
1. `19-TROUBLESHOOTING-DECISION-TREE.md` -- diagnosis
2. `04-SERVICES-REFERENCE.md` -- service details
3. `22-PERFORMANCE-TUNING-GUIDE.md` -- performance issues

---

## Quick Reference

**Development URLs:**
- Frontend (dev): `http://localhost:5174`
- Backend API (dev): `http://localhost:8001`
- API docs (Swagger): `http://localhost:8001/docs`
- PDM-Local-Service: `http://localhost:8083`
- Supabase dashboard: Supabase project console

**Development Commands:**
```bash
cd backend && uvicorn app.main:app --reload --port 8001
cd frontend && npm run dev
cd Local_Creo_Files\Powershell && .\PDM-Local-Service.ps1
docker-compose up -d freecad-worker
```

**Key Configuration:**
- Backend environment: `backend/.env`
- Frontend Supabase config: `frontend/src/services/supabase.ts`
- Upload bridge config: `scripts/pdm-upload/PDM-Upload-Config.ps1`
- PDM-Local-Service: `Local_Creo_Files/Powershell/PDM-Local-Service.ps1`

---

**Total Documentation Files:** 30+
**Status:** Current

---

## Project Management

**Global TODO:** `TODO.md` (project root) - Comprehensive task tracking, feature status, and development roadmap
**Planning Docs (Reference):**
- `Update-Compare.md` - Migration gap analysis (workspace comparison completed)
- `Nest_plan.md` - Nesting service implementation plan (completed)
