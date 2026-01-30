# PDM-Web Documentation

**Product Data Management System -- Technical Documentation**

PDM-Web is a web-based system for managing CAD files, Bills of Materials, lifecycle tracking, and manufacturing document generation. Built with Vue 3, FastAPI, and Supabase.

---

## Quick Start

New to the system? Read these first:

1. [01-PDM-SYSTEM-MAP.md](01-PDM-SYSTEM-MAP.md) -- Architecture, project structure, data flow (5 min)
2. [02-PDM-COMPLETE-OVERVIEW.md](02-PDM-COMPLETE-OVERVIEW.md) -- Full system reference: stack, schema, API, views (20 min)

---

## Documentation Guide

### System Overview

- [00-TABLE-OF-CONTENTS.md](00-TABLE-OF-CONTENTS.md) -- Master index of all documentation files
- [01-PDM-SYSTEM-MAP.md](01-PDM-SYSTEM-MAP.md) -- Architecture diagrams, project layout, data flow, technology layers
- [02-PDM-COMPLETE-OVERVIEW.md](02-PDM-COMPLETE-OVERVIEW.md) -- Comprehensive reference: tech stack, database schema, API endpoints, frontend views, auth, file storage, FreeCAD, upload bridge, item numbering

### Database

- [03-DATABASE-SCHEMA.md](03-DATABASE-SCHEMA.md) -- Table definitions, field descriptions, relationships, SQL queries

### Backend and Services

- [04-SERVICES-REFERENCE.md](04-SERVICES-REFERENCE.md) -- Backend service configuration and details
- [05-POWERSHELL-SCRIPTS-INDEX.md](05-POWERSHELL-SCRIPTS-INDEX.md) -- Upload bridge script inventory

### Tools

- [06-BOM-COST-ROLLUP-GUIDE.md](06-BOM-COST-ROLLUP-GUIDE.md) -- BOM cost calculation
- [07-PDM-DATABASE-CLEANUP-GUIDE.md](07-PDM-DATABASE-CLEANUP-GUIDE.md) -- Database maintenance

### Frontend

- [08-PDM-WEBSERVER-README.md](08-PDM-WEBSERVER-README.md) -- Vue 3 application setup
- [09-PDM-WEBSERVER-DEPLOYMENT.md](09-PDM-WEBSERVER-DEPLOYMENT.md) -- Production deployment
- [10-PDM-WEBSERVER-OVERVIEW.md](10-PDM-WEBSERVER-OVERVIEW.md) -- UI design and views
- [11-PDM-WEBSERVER-QUICK-REFERENCE.md](11-PDM-WEBSERVER-QUICK-REFERENCE.md) -- Daily operations

### CAD Processing and Integration

- [12-FREECAD-AUTOMATION.md](12-FREECAD-AUTOMATION.md) -- FreeCAD Docker for DXF/SVG generation
- [13-LOCAL-PDM-SERVICES-GUIDE.md](13-LOCAL-PDM-SERVICES-GUIDE.md) -- Local upload bridge integration

### Operations

- [17-QUICK-START-CHECKLIST.md](17-QUICK-START-CHECKLIST.md) -- First-time setup
- [19-TROUBLESHOOTING-DECISION-TREE.md](19-TROUBLESHOOTING-DECISION-TREE.md) -- Problem diagnosis
- [20-COMMON-WORKFLOWS.md](20-COMMON-WORKFLOWS.md) -- Step-by-step task guides
- [23-SYSTEM-CONFIGURATION.md](23-SYSTEM-CONFIGURATION.md) -- Configuration reference

### Reference

- [18-GLOSSARY-TERMS.md](18-GLOSSARY-TERMS.md) -- Terminology
- [24-VERSION-HISTORY.md](24-VERSION-HISTORY.md) -- Release notes
- [27-WEB-MIGRATION-PLAN.md](27-WEB-MIGRATION-PLAN.md) -- Migration planning

---

## System at a Glance

| Component | Technology |
|-----------|-----------|
| Frontend | Vue 3 + Vite + Pinia |
| Backend | FastAPI (Python 3) |
| Database | Supabase PostgreSQL |
| Auth | Supabase Auth (JWT) |
| Storage | Supabase Storage (`pdm-files` bucket) |
| CAD Processing | FreeCAD Docker container |
| Upload Bridge | PowerShell scripts (local workstation) |

**Users:** Jack (engineer/admin), Dan (PM/viewer), Shop (shared viewer)

**Development:**
```bash
cd backend && uvicorn app.main:app --reload --port 8080
cd frontend && npm run dev
```

**API docs:** `http://localhost:8080/docs`

---

**Last Updated:** 2026-01-29
