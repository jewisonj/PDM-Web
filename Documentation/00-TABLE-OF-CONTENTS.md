# PDM-Web Documentation - Table of Contents

**Last Updated:** 2026-07-22
**System:** PDM-Web (Product Data Management)
**Stack:** Vue 3 + FastAPI + Supabase + Docker
**Current Version:** v3.9.7

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
| 30 | `waterjet-cutting-speeds.md` | Waterjet cutting speed reference tables, machinability indices, material-specific speeds, quality multipliers. |
| 31 | `31-BUILD-TRACKER-SHEET.md` | Shop-floor Build Tracker print sheet: item classification, station columns, pre-fill/completion semantics, milestones, pagination, photo-capture readiness. |
| 32 | `32-BUILD-BOOK.md` | Manufacturing Build Book: day-by-day work packages, kit/weld chapters, sequence-first design rationale, station abbreviations, section print sets (v3.9.1), document items, purchased-item display, full-book PDF endpoint. |
| 37 | `37-KIT-BUNDLE-PRICING.md` | Kit/bundle pricing system: vendor bundles, per-project part sourcing (make vs kit), cost comparison, kit management slideout UI, routing page integration, cost estimate calculation. |
| 38 | `38-KIT-SOURCING-IN-BUILD-DOCS.md` | Kit sourcing in Build Book and Design Book: STAGE SET renderer, per-project kit documentation sections, purchased parts tracking. |
| 39 | `39-KIT-SOURCING-STEP-EXPORT.md` | Kit sourcing STEP export guide: BOM queries, part categorization, STEP file downloads, export folder structure, CSV generation, handling updated files from vendors. |
| 43 | `43-DESIGN-BOOK-IMAGE-MANAGEMENT.md` | Design Book image management system: image hash detection for auto re-rendering, FastAPI route ordering fix, upload form state preservation, image library integration with Master Design Book III-00 section. |
| 44 | `44-SUPPLIER-PORTAL.md` | Supplier Portal: external vendor access to approved files, separate JWT auth, file type restrictions, two-way comments, admin management, item access control. |

### Section 5: Frontend Application

| # | File | Description |
|---|------|-------------|
| 08 | `08-PDM-WEBSERVER-README.md` | Vue 3 frontend setup, configuration, and build process. |
| 09 | `09-PDM-WEBSERVER-DEPLOYMENT.md` | Production deployment guide for FastAPI + Vue SPA. |
| 10 | `10-PDM-WEBSERVER-OVERVIEW.md` | Frontend UI design, views, components, and user experience. |
| 11 | `11-PDM-WEBSERVER-QUICK-REFERENCE.md` | Daily operations and common tasks reference. |
| 35 | `35-UI-DESIGN-STANDARDS.md` | UI/UX design standards: part number display formatting (prefix stripping for MMC/SPN), code patterns, implementation locations. |
| 36 | `36-MASTER-DESIGN-BOOK-PLAN.md` | Master Design Book (Spa): product-level, date-free (D1..Dn), rev-controlled section booklets with auto change notices. Architecture + phased plan. |

### Section 6: CAD Processing and Docker

| # | File | Description |
|---|------|-------------|
| 12 | `12-FREECAD-AUTOMATION.md` | FreeCAD Docker container, DXF flat pattern generation, SVG bend drawing generation. |
| 29 | `29-NESTING-AUTOMATION.md` | DXF nesting worker, Bottom-Left Fill algorithm, project-scoped sheet metal nesting. |

### Section 7: Integration and AI

| # | File | Description |
|---|------|-------------|
| 13 | `13-LOCAL-PDM-SERVICES-GUIDE.md` | Local upload bridge integration with the PDM-Web API. |
| 14 | `14-SKILL-DEFINITION.md` | AI assistant skill definition for PDM-Web context (Claude Code agent). |
| 33 | `33-AI-ASSISTANT.md` | PDM AI Assistant: Claude-powered conversational interface for querying parts, BOMs, files, MRP projects, costs, and tasks. SSE streaming chat, 17 read-only tools, approval-gated write actions, guarded SQL, persistent conversations. |
| 34 | `34-AI-ASSISTANT-ROADMAP.md` | Future assistant work: McMaster-Carr price lookups (API + cache + sync actions) and print content extraction (PDF text + search + vision fallback). |

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
3. `35-UI-DESIGN-STANDARDS.md` -- UI/UX standards and formatting conventions
4. `11-PDM-WEBSERVER-QUICK-REFERENCE.md` -- daily tasks

### Deployment
1. `09-PDM-WEBSERVER-DEPLOYMENT.md` -- production deployment
2. `26-SECURITY-HARDENING.md` -- security configuration
3. `22-PERFORMANCE-TUNING-GUIDE.md` -- optimization

### CAD Processing
1. `12-FREECAD-AUTOMATION.md` -- FreeCAD Docker setup
2. `13-LOCAL-PDM-SERVICES-GUIDE.md` -- upload bridge

### MRP / Shop Floor
1. `20-COMMON-WORKFLOWS.md` (sections 13-17) -- Part Lookup, Routing Editor, Project Scheduling, Build Tracker Sheet, Build Book
2. `29-NESTING-AUTOMATION.md` -- DXF nesting worker
3. `31-BUILD-TRACKER-SHEET.md` -- printable shop-floor Build Tracker sheet
4. `32-BUILD-BOOK.md` -- day-by-day manufacturing Build Book (work packages + kit/weld sheets + section print sets)
5. `06-BOM-COST-ROLLUP-GUIDE.md` -- BOM cost rollup
6. `37-KIT-BUNDLE-PRICING.md` -- Kit/bundle pricing and vendor cost comparison
7. `38-KIT-SOURCING-IN-BUILD-DOCS.md` -- Kit sourcing in Build Book and Design Book
8. `39-KIT-SOURCING-STEP-EXPORT.md` -- Exporting STEP files and BOMs for kit orders
9. `33-AI-ASSISTANT.md` -- AI-powered chat for part lookup, BOM expansion, file downloads

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

**Total Documentation Files:** 39
**Status:** Current

---

## Project Management

**Global TODO:** `TODO.md` (project root) - Comprehensive task tracking, feature status, and development roadmap
**Tech Debt:** `TECHNICAL-DEBT-AUDIT.md` (project root) - 40+ tracked debt items from Jan 2026 audit, reviewed Jul 2026 (1 resolved, 2 partial, 37 open, 4 new)
**Documentation Audit:** `DOCUMENTATION-AUDIT-2026-07-09.md` - Comprehensive documentation audit (14 files fixed for port 8001, README.md updated, health score 7/10)
**Planning Docs (Reference):**
- `Update-Compare.md` - Migration gap analysis (workspace comparison completed)
- `Nest_plan.md` - Nesting service implementation plan (completed)
