# Headless DXF Nesting Service on Fly.io
## Supabase-Integrated API Architecture & Implementation Plan

**STATUS:** REFERENCE DOCUMENT (Nesting Service COMPLETED)

**Current Status:** Nesting automation fully implemented in v3.1
- Docker worker running Bottom-Left Fill algorithm
- Full API integration with MRP system
- See active documentation: `Documentation/29-NESTING-AUTOMATION.md`
- Last updated: 2026-01-30

---

## 1. Overview

This document defines a complete, headless implementation plan for a DXF nesting service designed to run on Fly.io and integrate with an existing PDM/MRP system.

The service is intended to operate without any GUI and will support fully automated operation. It will accept DXF inputs (either uploaded directly or referenced from Supabase Storage), perform 2D nesting on standard sheet sizes, and write the resulting nested DXF files back to Supabase Storage along with a machine-readable manifest.

The primary use case involves DXF files composed mostly of lines and arcs, with rotations allowed and sheet sizes typically 4×8 ft or 5×10 ft.

---

## 2. Functional Requirements

The system must:

- Accept a list of DXF files with associated quantities
- Support DXF inputs sourced directly from Supabase Storage
- Allow arbitrary part rotation (configurable step size)
- Support sheet sizes:
  - 4×8 ft (48 × 96 inches)
  - 5×10 ft (60 × 120 inches)
  - Optional custom dimensions
- Handle geometry consisting primarily of:
  - LINE
  - ARC
  - CIRCLE
  - LWPOLYLINE (with bulge)
- Perform headless nesting without any GUI dependencies
- Output one or more nested DXF files
- Persist outputs and metadata back to Supabase Storage
- Expose a stable API suitable for PDM/MRP integration
- Execute asynchronously (non-blocking API calls)

---

## 3. Non-Functional Requirements

- Stateless execution (no persistent local state)
- Deterministic and reproducible outputs where possible
- Suitable for containerized deployment
- Safe handling of malformed or imperfect DXF inputs
- Isolation between API handling and CPU-intensive nesting work
- Secure access to Supabase resources using server-side credentials only

---

## 4. System Architecture

### 4.1 High-Level Components

1. **API Service**
   - Accepts job submissions
   - Validates inputs
   - Creates job records
   - Provides job status and output references

2. **Worker Service**
   - Executes nesting jobs
   - Downloads DXF inputs from Supabase Storage
   - Converts DXF geometry to polygon representations
   - Performs nesting
   - Writes nested DXF outputs
   - Uploads outputs and manifests
   - Updates job state

3. **Supabase**
   - PostgreSQL for job metadata
   - Storage buckets for DXF inputs and outputs

4. **Fly.io**
   - Hosts the API and worker processes
   - Provides scaling and isolation

---

## 5. Technology Stack

### 5.1 Language & Runtime
- Python 3.11+

### 5.2 Core Libraries
- FastAPI – HTTP API layer
- ezdxf – DXF parsing and DXF generation
- Shapely – polygon operations, offsets, validation
- libnest2d – 2D irregular nesting engine
  - Used via Python bindings or a compiled helper binary

### 5.3 Infrastructure
- Fly.io (container hosting)
- Supabase (PostgreSQL + Storage)

---

## 6. Supabase Data Model

### 6.1 Table: `nest_jobs`

| Column | Type | Description |
|------|------|-------------|
| id | uuid (PK) | Job identifier |
| created_at | timestamptz | Creation timestamp |
| created_by | text / uuid | User or service identifier |
| status | text | queued / running / succeeded / failed / canceled |
| sheet_type | text | 4x8, 5x10, or custom |
| sheet_width_in | numeric | Sheet width (inches) |
| sheet_height_in | numeric | Sheet height (inches) |
| units | text | inch (default) |
| rotation_step_deg | int | Rotation increment |
| spacing_in | numeric | Part-to-part spacing |
| margin_in | numeric | Sheet margin |
| kerf_in | numeric | Optional kerf compensation |
| chord_tol_in | numeric | Arc discretization tolerance |
| allow_mirror | boolean | Default false |
| input_bucket | text | Supabase input bucket |
| input_prefix | text | Storage prefix for inputs |
| output_bucket | text | Supabase output bucket |
| output_prefix | text | Storage prefix for outputs |
| manifest_path | text | Output manifest location |
| error_message | text | Failure reason |
| run_metrics | jsonb | Runtime statistics |

---

### 6.2 Table: `nest_job_items`

| Column | Type | Description |
|------|------|-------------|
| id | uuid (PK) | Item identifier |
| job_id | uuid (FK) | Parent job |
| source_path | text | Storage path to DXF |
| qty | int | Quantity |
| part_name | text | Optional label |
| constraints | jsonb | Per-part constraints |
| extracted_meta | jsonb | Geometry metadata |

---

## 7. Supabase Storage Layout

### 7.1 Input Files

- Bucket: `nest-input`
- Path: `jobs/{job_ref}/parts/{filename}.dxf`

### 7.2 Output Files

- Bucket: `nest-output`
- Path:
  - `jobs/{job_ref}/nested/sheet_01.dxf`
  - `jobs/{job_ref}/nested/sheet_02.dxf`
  - `jobs/{job_ref}/nested/manifest.json`

---

## 8. API Design

### 8.1 Authentication

- Server-to-server API key and/or JWT
- Supabase Service Role key stored only as Fly.io secrets
- Clients never receive direct storage credentials

---

### 8.2 Endpoints

#### POST /jobs

Creates a new nesting job using DXFs already stored in Supabase.

Request body (JSON):

{
  "job_ref": "JOB-042",
  "sheet_type": "4x8",
  "rotation_step_deg": 5,
  "spacing_in": 0.125,
  "margin_in": 0.5,
  "chord_tol_in": 0.01,
  "input_bucket": "cut-parts",
  "input_prefix": "jobs/JOB-042/parts/",
  "output_bucket": "cut-nested",
  "output_prefix": "jobs/JOB-042/nested/",
  "items": [
    { "source_path": "jobs/JOB-042/parts/a_revB.dxf", "qty": 4 },
    { "source_path": "jobs/JOB-042/parts/b_revA.dxf", "qty": 2 }
  ]
}

Response:

{
  "job_id": "uuid",
  "status": "queued"
}

---

#### GET /jobs/{job_id}

Returns job status and output references.

{
  "job_id": "uuid",
  "status": "succeeded",
  "outputs": [
    {
      "sheet_index": 1,
      "dxf_path": "jobs/JOB-042/nested/sheet_01.dxf",
      "utilization": 0.72
    }
  ],
  "manifest_path": "jobs/JOB-042/nested/manifest.json",
  "metrics": {
    "runtime_s": 12.3,
    "parts": 42,
    "sheets": 2
  }
}

---

## 9. Nesting Pipeline

### 9.1 DXF Parsing Rules

- Read modelspace only
- Allowed entities:
  - LINE
  - ARC
  - CIRCLE
  - LWPOLYLINE (bulge)
- Ignored entities:
  - TEXT
  - DIMENSION
  - HATCH
- Configurable layer allow-list (default: CUT, 0)

---

### 9.2 Geometry Conversion

1. Convert arcs and circles to polylines using chord tolerance
2. Snap endpoints within tolerance
3. Stitch segments into closed loops
4. Classify outer contours and holes
5. Produce polygon sets for nesting

---

### 9.3 Spacing, Margins, Kerf

- Spacing applied via polygon offset
- Margins enforced by shrinking usable sheet area
- Kerf handled either directly or absorbed into spacing

---

### 9.4 Nesting Execution

- Bin size equals sheet dimensions minus margins
- Rotation allowed in configurable increments
- Multiple sheets generated as needed
- Stable part ordering for reproducibility

---

### 9.5 DXF Output Generation

For each sheet:

- Create new DXF document
- Optional sheet boundary on SHEET layer
- Insert parts as:
  - BLOCK references (preferred) or
  - Transformed geometry
- Layer naming based on source file or part name
- Save and upload to Supabase Storage

---

## 10. Output Manifest Format

The manifest provides full traceability and machine-readable placement data.

{
  "job_id": "uuid",
  "job_ref": "JOB-042",
  "sheet": {
    "type": "4x8",
    "width_in": 48,
    "height_in": 96,
    "margin_in": 0.5
  },
  "params": {
    "rotation_step_deg": 5,
    "spacing_in": 0.125,
    "chord_tol_in": 0.01
  },
  "outputs": [
    {
      "sheet_index": 1,
      "dxf_path": "jobs/JOB-042/nested/sheet_01.dxf",
      "utilization": 0.72,
      "placements": [
        {
          "instance_id": "a_revB#1",
          "source_path": "jobs/JOB-042/parts/a_revB.dxf",
          "x_in": 12.34,
          "y_in": 55.67,
          "rotation_deg": 90
        }
      ]
    }
  ],
  "metrics": {
    "runtime_s": 12.3,
    "parts": 42,
    "sheets": 2
  }
}

---

## 11. Fly.io Deployment Strategy

### 11.1 Process Groups

- web: FastAPI service
- worker: background nesting worker

This separation prevents HTTP timeouts and isolates CPU-heavy work.

---

### 11.2 Container Behavior

- Stateless containers
- Temporary files stored in /tmp
- No reliance on persistent volumes
- All authoritative state stored in Supabase

---

## 12. Job Execution & Concurrency

- Jobs claimed via atomic DB update
- Status transitions:
  - queued → running → succeeded / failed
- Optional heartbeat fields to recover from crashes
- Configurable concurrency per worker

---

## 13. Security Considerations

- Supabase Service Role key stored as Fly secret
- Input validation:
  - file size limits
  - maximum part count
- Storage path allow-list enforcement
- Authentication required for all endpoints
- Rate limiting recommended

---

## 14. Operational Considerations

### 14.1 Logging
- Structured logs
- Job lifecycle events
- Geometry extraction and nesting duration

### 14.2 Metrics
- Runtime per job
- Parts per sheet
- Utilization
- Failure rates

---

## 15. Implementation Phases

### Phase 0: Pipeline Validation
- DXF download from Supabase
- Geometry extraction (lines + arcs)
- Write DXF back to storage

### Phase 1: Nesting Integration
- Integrate libnest2d
- Multi-sheet handling
- Rotation support

### Phase 2: Production Hardening
- Input repair heuristics
- Deterministic output
- Observability
- Error recovery

---

## 16. Future Enhancements

- Grain direction constraints
- Per-part rotation limits
- SVG previews
- Cost optimization metrics
- CAM post-processor hooks

---

## 17. Summary

This design provides a robust, headless, and production-ready DXF nesting service suitable for integration with a PDM/MRP system. It avoids GUI dependencies, supports real-world DXF geometry, and aligns with Fly.io’s stateless deployment model while leveraging Supabase for persistence and storage.

The architecture is intentionally modular, allowing the nesting engine, geometry handling, and API layers to evolve independently.
