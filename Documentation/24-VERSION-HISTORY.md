# PDM System - Version History and Release Notes

**Track changes, updates, and system evolution across all versions**
**Related Docs:** [27-WEB-MIGRATION-PLAN.md](27-WEB-MIGRATION-PLAN.md), [15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md](15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md)

---

## Current Version

### v3.0 -- Web Migration (2025)

**Status:** Current Production Release

This release is a complete architecture rewrite from the legacy Windows/PowerShell/SQLite system to a modern web stack. The core domain (items, files, BOMs, lifecycle states, item numbering) is preserved, but the technology platform is entirely new.

#### Architecture Changes

| Component | v2.0 (Legacy) | v3.0 (Current) |
|-----------|---------------|-----------------|
| Frontend | Node.js Express + HTML templates | Vue 3 + Vite + Pinia |
| Backend | PowerShell services + Node.js server | FastAPI (Python 3) |
| Database | SQLite file (`pdm.sqlite`) | Supabase PostgreSQL (cloud) |
| Auth | None (local access only) | Supabase Auth (JWT) |
| File Storage | Local filesystem (`D:\PDM_Vault\`) | Supabase Storage (cloud) |
| File Processing | PowerShell FileSystemWatcher services | Upload bridge scripts + FastAPI endpoints |
| BOM Processing | BOM-Watcher PowerShell service | PDM-BOM-Parser.ps1 + FastAPI bulk endpoint |
| DXF/SVG Generation | FreeCAD local + batch files | FreeCAD Docker container |
| Service Management | NSSM Windows Services | uvicorn (backend) + npm (frontend) |
| API Documentation | None | OpenAPI auto-generated (`/docs`) |

#### New Features

- **Vue 3 frontend** with desktop-first UI inspired by PLM systems (Windchill/Teamcenter)
- **FastAPI backend** with automatic request validation via Pydantic and OpenAPI docs
- **Supabase PostgreSQL** cloud database with Row Level Security
- **JWT authentication** via Supabase Auth with role-based access
- **Cloud file storage** via Supabase Storage with signed URLs for secure access
- **Item browser** with search, filtering by lifecycle state and project, sortable columns, and detail panel with BOM tree and where-used data
- **BOM tree view** with recursive multi-level hierarchy
- **Where-used lookup** showing all parent assemblies for a given part
- **Bulk BOM upload** endpoint for batch processing from Creo exports
- **Upsert pattern** for item creation/update from upload bridge
- **MRP views** including dashboard, routing, shop, parts lookup, project tracking, and raw materials
- **Upload bridge** PowerShell scripts bridging local CAD files to the web API
- **Interactive API documentation** at `/docs` (Swagger UI) and `/redoc`
- **Health check endpoint** at `/health`
- **SPA routing** with Vue Router and navigation guards for auth

#### Breaking Changes

This is a complete platform rewrite. There is no in-place upgrade path from v2.0 to v3.0.

- **Database:** SQLite replaced by Supabase PostgreSQL. Data must be migrated.
- **File storage:** Local filesystem replaced by Supabase Storage. Files must be re-uploaded.
- **Services:** PowerShell Windows services replaced by web processes. NSSM is no longer used.
- **Web server:** Node.js Express replaced by Vue 3 (frontend) + FastAPI (backend). Port 3000 is no longer used; the system now uses port 5173 (Vite dev) and port 8000/8080 (FastAPI).
- **API:** All endpoints have changed. The legacy Node.js API is replaced by the FastAPI API under `/api/`.
- **Authentication:** Access now requires Supabase Auth credentials (email/password).

#### Migration Path from v2.0

1. **Set up Supabase project** -- Create tables matching the schema in [27-WEB-MIGRATION-PLAN.md](27-WEB-MIGRATION-PLAN.md)
2. **Export legacy data** -- Extract items, files, and BOM records from SQLite
3. **Import to Supabase** -- Use the SQL Editor or migration scripts to load data
4. **Upload files** -- Re-upload files from the local vault to Supabase Storage
5. **Configure environment** -- Set up `.env` with Supabase credentials
6. **Deploy backend** -- Run FastAPI with uvicorn
7. **Deploy frontend** -- Build and serve Vue application
8. **Set up upload bridge** -- Configure `scripts/pdm-upload/` to point to the new API

#### Known Limitations

- Release and revision workflows are not yet fully automated (manual state changes via API)
- FreeCAD Docker worker integration for automatic DXF/SVG generation is in progress
- No offline mode -- requires internet access to reach Supabase
- Upload bridge still uses PowerShell (requires Windows for local CAD file processing)

---

## Previous Versions

### v2.0 (2025-01-03) -- Documentation and BOM Cost Tools

**Status:** Legacy (superseded by v3.0)

#### Features

- Unified PDM web browser (Node.js Express on port 3000)
- Multi-file DXF/SVG generation with corrected scaling
- BOM cost rollup with hierarchical analysis (`Get-BOMCost.ps1`)
- Creo workspace comparison tool (port 8082)
- Database cleanup and maintenance utilities
- Complete PowerShell automation suite

#### Key Improvements Over v1.0

- DXF scaling fixed (was 645.16x too large)
- Explicit millimeter units in DXF headers
- Enhanced Worker-Processor logging
- Added Part-Parameter-Watcher service
- Improved item number extraction logic (suffix stripping, longest-match-first regex)
- Comprehensive documentation (21 files)

#### Services (5 Production)

1. CheckIn-Watcher -- File ingestion from check-in folder
2. BOM-Watcher -- BOM file processing
3. Worker-Processor -- Task execution (DXF/SVG generation)
4. Part-Parameter-Watcher -- Parameter synchronization
5. MLBOM-Watcher -- Multi-level BOM support

#### Technology Stack

- Backend: PowerShell 5.1+ services managed by NSSM
- Web server: Node.js Express on port 3000
- Database: SQLite (`D:\PDM_Vault\pdm.sqlite`)
- File storage: Local filesystem (`D:\PDM_Vault\CADData\`)
- FreeCAD: Local installation with batch scripts

---

### v1.0 (~2024) -- Initial System

**Status:** Legacy (superseded by v2.0)

#### Features

- Core PDM functionality (check-in, file classification, database registration)
- CheckIn-Watcher service for file ingestion
- BOM-Watcher service for BOM processing
- Worker-Processor for DXF/SVG generation
- SQLite database with 6 main tables
- Basic web interface (PowerShell-generated HTML)
- FreeCAD automation for document generation

#### Known Issues (Fixed in v2.0)

- DXF files were 645.16x too large (scaling error)
- Unit specifications missing in DXF headers
- Item number extraction did not handle `_prt`, `_asm`, `_drw` suffixes
- No proper logging for Worker-Processor
- Limited multi-level BOM support
- No Part-Parameter-Watcher

---

## Version Comparison

| Feature | v1.0 | v2.0 | v3.0 |
|---------|------|------|------|
| **Frontend** | PowerShell HTML | Node.js Express | Vue 3 + Vite |
| **Backend** | PowerShell services | PowerShell + Node.js | FastAPI (Python) |
| **Database** | SQLite | SQLite | Supabase PostgreSQL |
| **Auth** | None | None | JWT (Supabase Auth) |
| **File Storage** | Local filesystem | Local filesystem | Supabase Storage (cloud) |
| **File Ingestion** | CheckIn-Watcher | CheckIn-Watcher | Upload bridge + API |
| **BOM Processing** | BOM-Watcher | BOM-Watcher | BOM parser + bulk API |
| **DXF/SVG Generation** | FreeCAD local | FreeCAD local (fixed) | FreeCAD Docker |
| **API Documentation** | None | None | OpenAPI auto-generated |
| **Service Manager** | NSSM | NSSM | uvicorn / npm |
| **Multi-User** | No | No | Yes (auth + roles) |
| **Cloud Deployment** | No | No | Yes |
| **Item Browser** | Basic HTML | Node.js web app | Vue SPA with detail panel |
| **BOM Tree View** | Manual query | Manual query | Interactive recursive tree |
| **Where-Used** | Manual query | Manual query | Built-in endpoint + UI |
| **MRP Views** | No | Basic | Dashboard + 5 views |
| **Documentation** | Minimal | Comprehensive | Updated for web stack |

---

## Version Support Timeline

| Version | Released | Status | Notes |
|---------|----------|--------|-------|
| v1.0 | ~2024 | Archived | No longer maintained |
| v2.0 | 2025-01-03 | Legacy | Superseded by v3.0, documentation preserved for reference |
| v3.0 | 2025 | Current | Active development and production use |

---

## Checking Your Version

**v3.0 indicators:**
- Backend runs with `uvicorn` (not Node.js or PowerShell services)
- Frontend uses Vue 3 (check `frontend/package.json` for `vue` dependency)
- Database is Supabase PostgreSQL (check `backend/.env` for `SUPABASE_URL`)
- API available at `http://localhost:8000/docs`

**v2.0 indicators:**
- Node.js Express server on port 3000
- SQLite database at `D:\PDM_Vault\pdm.sqlite`
- PowerShell services managed by NSSM
- No authentication required

**v1.0 indicators:**
- Same as v2.0 but with DXF scaling issues and limited documentation

---

## Changelog Format

All future releases follow this format:

```
### vX.Y (YYYY-MM-DD) -- Release Title

**Status:** [Stable | Beta | In Development]

#### New Features
- Description of new functionality

#### Improvements
- Description of enhancements to existing features

#### Bug Fixes
- Description: Solution applied

#### Breaking Changes
- Description of changes requiring migration

#### Migration Path
- Steps to upgrade from previous version
```

---

**Last Updated:** 2025-01-29
**Current Version:** v3.0
**Related:** [27-WEB-MIGRATION-PLAN.md](27-WEB-MIGRATION-PLAN.md), [15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md](15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md)
