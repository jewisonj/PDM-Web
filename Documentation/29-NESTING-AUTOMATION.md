# DXF Nesting Automation Reference

## Overview

The DXF nesting system automatically arranges sheet metal flat patterns (DXF files) onto stock sheets to minimize material waste and optimize cutting. Nesting jobs are project-scoped and integrated with the MRP workflow.

**Key Features:**
- Project-scoped nesting linked to MRP jobs
- Automatic part grouping by material and thickness
- Bottom-Left Fill nesting algorithm with rotation support
- Docker-based worker for cloud deployment
- Parameterized sheet sizes and spacing
- Multi-sheet output with utilization tracking

**Architecture:** The nesting worker runs in a separate Docker container from the FreeCAD worker, polls the work queue for `NEST_PARTS` tasks, and uses pure Python libraries (ezdxf, Shapely) for DXF parsing and geometric operations.

---

## System Architecture

### Nesting Pipeline Flow

```
1. User selects parts from MRP project
   (Frontend: NestConfigModal.vue)
         |
2. API creates nest job and work queue task
   (Backend: POST /api/nesting/projects/{id}/nest)
         |
3. Nest job record created with status 'pending'
   (Database: nest_jobs, nest_job_items, work_queue)
         |
4. Worker polls for pending NEST_PARTS tasks
   (Worker: nest_worker.py)
         |
5. Worker downloads DXF files from Supabase Storage
   (Worker: dxf_parser.py parses to polygons)
         |
6. Nesting algorithm arranges parts on sheets
   (Worker: nester.py - Bottom-Left Fill)
         |
7. Output DXF sheets generated with layers
   (Worker: dxf_writer.py creates SHEET/PARTS/LABELS)
         |
8. Results uploaded to Supabase Storage
   (Storage path: pdm-files/projects/{code}/nests/{job_id}/)
         |
9. Nest job marked complete with utilization stats
   (Database: nest_jobs.status = 'completed', nest_results created)
         |
10. Frontend polls job status and displays results
    (Frontend: MrpDashboardView.vue, downloadable sheets)
```

---

## Docker Worker Configuration

### Docker Image

**Base Image:** `python:3.11-slim`

Custom nesting worker runs lightweight Python without FreeCAD dependencies.

### Dockerfile

Located at `worker/nesting/Dockerfile`:

```dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY worker/nesting/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY worker/nesting/*.py /app/

CMD ["python", "nest_worker.py"]
```

### Dependencies (requirements.txt)

```
ezdxf==1.3.0        # DXF parsing and generation
Shapely==2.0.6      # 2D polygon operations
supabase==2.10.0    # Database and storage access
python-dotenv==1.0.0
```

### Docker Compose Configuration

Defined in `docker-compose.yml`:

```yaml
services:
  nesting-worker:
    build:
      context: .
      dockerfile: worker/nesting/Dockerfile
    container_name: pdm-nesting-worker
    environment:
      - SUPABASE_URL=${SUPABASE_URL}
      - SUPABASE_SERVICE_KEY=${SUPABASE_SERVICE_KEY}
      - POLL_INTERVAL=5
      - LOG_LEVEL=INFO
    restart: unless-stopped
    depends_on:
      - freecad-worker
```

**Environment Variables:**

| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Yes | Service role key (bypasses RLS) |
| `POLL_INTERVAL` | No | Seconds between queue polls (default: 5) |
| `LOG_LEVEL` | No | Logging verbosity (default: INFO) |

---

## Worker Components

### nest_worker.py

**Purpose:** Main worker process that polls the work queue and orchestrates nesting jobs.

**Process:**

1. Polls `work_queue` for pending `NEST_PARTS` tasks
2. Marks task as `processing`
3. Fetches nest job details from `nest_jobs` and `nest_job_items`
4. Downloads DXF files from Supabase Storage
5. Parses DXF files to polygons using `dxf_parser.py`
6. Runs nesting algorithm using `nester.py`
7. Generates output DXF sheets using `dxf_writer.py`
8. Uploads output DXFs and manifest to Supabase Storage
9. Creates `nest_results` records in database
10. Marks nest job and task as `completed` (or `failed` on error)

**Error Handling:**
- All exceptions are caught and logged
- Failed tasks are marked with `status='failed'` and `error_message`
- Worker continues polling after errors (resilient to individual job failures)

**Logging:**
- Task start/completion timestamps
- DXF file counts and polygon counts
- Nesting results (sheets, utilization, placement counts)
- Errors with full stack traces

### dxf_parser.py

**Purpose:** Parse DXF files into Shapely polygon objects for nesting.

**Supported DXF Entities:**
- `LINE` -- Straight line segments
- `ARC` -- Circular arcs (tessellated to polyline)
- `CIRCLE` -- Full circles (holes or small parts)
- `LWPOLYLINE` -- Lightweight polylines with optional bulge (arc segments)

**Process:**

1. Opens DXF file using `ezdxf`
2. Iterates through modelspace entities
3. Converts each entity to line segments
4. Builds closed polygons from connected segments
5. Handles bulge values in LWPOLYLINE for arc interpolation
6. Returns Shapely `Polygon` object with outer boundary and holes

**Arc Tessellation:**
- Arcs are divided into 16 segments by default
- Bulge values in polylines define arc curvature
- Three-point arc calculation: start, midpoint (from bulge), end

**Coordinate System:**
- All coordinates are in millimeters (DXF native units)
- No scaling is applied during parsing (handled by DXF export process)

### nester.py

**Purpose:** Bottom-Left Fill nesting algorithm with rotation support.

**Algorithm:** Bottom-Left Fill (BLF)

1. Sort parts by area (largest first)
2. For each part:
   - Try placing at bottom-left corner (0, 0)
   - If rotation enabled, try both 0° and 90° orientations
   - Move part up/right until no collision with existing parts or sheet boundary
   - Place part at lowest, then leftmost valid position
3. When sheet is full, start a new sheet
4. Continue until all parts are placed

**Collision Detection:**
- Uses Shapely `intersects()` for polygon-polygon collision
- Checks against all previously placed parts on current sheet
- Checks against sheet boundary polygon

**Rotation Handling:**
- Parts can be rotated 90° if `allow_rotation=true`
- Both orientations are tested for each placement
- Chooses orientation with lower Y position (bottom-left preference)

**Sheet Management:**
- Unlimited sheets (continues until all parts placed)
- Each sheet starts fresh at (0, 0)
- Sheet boundary defined by `sheet_width` and `sheet_height`

**Spacing:**
- Minimum gap between parts (default 5mm)
- Applied by buffering part polygons before collision check
- Also applied as margin from sheet edges

**Output:**
```python
{
    "sheets": [
        {
            "sheet_index": 1,
            "placements": [
                {
                    "item_id": "uuid",
                    "item_number": "csp0030",
                    "x": 10.0,
                    "y": 10.0,
                    "rotation": 0,
                    "polygon": <Shapely Polygon>
                }
            ],
            "utilization_pct": 82.3
        }
    ],
    "total_sheets": 2,
    "overall_utilization_pct": 78.5
}
```

**Performance:**
- O(n²) time complexity (n = number of parts)
- Typical nesting of 20-50 parts completes in 1-5 seconds
- No optimization pass (greedy single-pass algorithm)

### dxf_writer.py

**Purpose:** Generate output DXF files with nested parts organized in layers.

**Layer Structure:**

| Layer Name | Color | Contents |
|------------|-------|----------|
| `SHEET` | Cyan (4) | Sheet boundary rectangle |
| `PARTS` | White (7) | All part outlines at placed positions |
| `LABELS` | Yellow (2) | Part labels (item number + quantity) |

**Process:**

1. Creates new DXF document using `ezdxf`
2. Adds `SHEET` layer with boundary rectangle
3. For each placed part:
   - Translates polygon coordinates to placement position
   - Rotates polygon if `rotation=90`
   - Adds polygon outline to `PARTS` layer
   - Adds text label at part centroid to `LABELS` layer
4. Saves DXF to file

**Text Labels:**
- Format: `{item_number} (x{quantity})`
- Height: 10mm
- Color: Yellow
- Positioned at polygon centroid

**Coordinate Units:**
- Output DXF coordinates are in millimeters
- No scaling applied (matches input DXF units)

**DXF Version:** AutoCAD 2018 (R2018) format for maximum compatibility

---

## Database Schema

### nest_jobs

Stores nesting job configuration and results.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| project_id | UUID (FK) | MRP project reference |
| material | TEXT | Material designation (e.g., STEEL_HSLA) |
| thickness | NUMERIC | Material thickness in mm |
| sheet_width | NUMERIC | Stock sheet width in mm |
| sheet_height | NUMERIC | Stock sheet height in mm |
| spacing | NUMERIC | Minimum gap between parts in mm |
| allow_rotation | BOOLEAN | Allow 90° rotation |
| status | TEXT | pending, processing, completed, failed |
| utilization_pct | NUMERIC | Overall material utilization percentage |
| total_sheets | INTEGER | Number of output sheets |
| error_message | TEXT | Populated on failure |
| created_at | TIMESTAMPTZ | Job creation time |
| completed_at | TIMESTAMPTZ | Job completion time |

### nest_job_items

Links parts to nesting jobs with quantities.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| job_id | UUID (FK) | Nest job reference |
| item_id | UUID (FK) | Item reference |
| dxf_path | TEXT | Supabase Storage path to flat pattern DXF |
| quantity | INTEGER | Number of copies to nest |
| created_at | TIMESTAMPTZ | Record creation time |

### nest_results

One row per output sheet with placement details.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| job_id | UUID (FK) | Nest job reference |
| sheet_index | INTEGER | Sheet number (1, 2, 3...) |
| dxf_path | TEXT | Supabase Storage path to nested sheet DXF |
| utilization_pct | NUMERIC | Sheet utilization percentage |
| placement_count | INTEGER | Total parts on this sheet |
| placement_data | JSONB | Array of placement records (item, position, rotation) |
| created_at | TIMESTAMPTZ | Record creation time |

**placement_data JSONB structure:**
```json
[
  {
    "item_id": "uuid",
    "item_number": "csp0030",
    "x": 10.0,
    "y": 10.0,
    "rotation": 0,
    "width": 100.0,
    "height": 50.0
  }
]
```

---

## API Endpoints

See `04-SERVICES-REFERENCE.md` for complete API documentation.

**Key Endpoints:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/nesting/projects/{id}/groups` | GET | Get parts grouped by material/thickness |
| `/api/nesting/projects/{id}/nest` | POST | Create nesting job |
| `/api/nesting/jobs/{id}` | GET | Get job details and results |
| `/api/nesting/projects/{id}/jobs` | GET | List all jobs for project |
| `/api/nesting/jobs/{id}/sheets/{n}/download` | GET | Download nested sheet DXF |

---

## Frontend Integration

### NestConfigModal.vue

Modal dialog for configuring a nesting job.

**Features:**
- Displays material groups from API
- Part selection checkboxes (pre-selected based on BOM quantities)
- Sheet size dropdown (48x96, 60x120, custom)
- Advanced parameters (spacing, rotation toggle)
- "Start Nesting" button creates job and queues task

**Workflow:**
1. User clicks "Nest DXF" in MRP project dashboard
2. Modal fetches material groups via `GET /api/nesting/projects/{id}/groups`
3. User selects material group and parts
4. User chooses sheet size and parameters
5. User clicks "Start Nesting"
6. Modal calls `POST /api/nesting/projects/{id}/nest`
7. Modal closes and dashboard begins polling for job completion

### MrpDashboardView.vue

MRP project detail view with nesting results section.

**Nesting Results Section:**
- Displays all nest jobs for the project
- Shows job status (pending, processing, completed, failed)
- Displays utilization percentage and sheet count on completion
- Lists downloadable output sheets with download buttons
- Polls for job updates every 5 seconds while jobs are active

**Job Status Display:**
- Pending: Spinner + "Queued..."
- Processing: Spinner + "Nesting parts..."
- Completed: Green checkmark + utilization stats + sheet downloads
- Failed: Red X + error message

**Sheet Download:**
- Each sheet has a download button
- Calls `GET /api/nesting/jobs/{id}/sheets/{n}/download` for signed URL
- Opens DXF in new tab (browser triggers download)

---

## Nesting Algorithm Details

### Bottom-Left Fill (BLF)

**Why BLF?**
- Simple and predictable
- Good utilization for rectangular parts
- Fast execution (no optimization iterations)
- Deterministic output (same inputs = same result)

**Limitations:**
- Not optimal (greedy algorithm)
- Rotation only at 90° (no arbitrary angles)
- No part clustering or grouping optimization
- No multi-sheet optimization (each sheet filled independently)

**Future Enhancements:**
- Genetic algorithm for better packing
- Arbitrary rotation angles
- Multi-sheet lookahead
- Part clustering by size/shape
- Manual placement adjustments

### Coordinate System

```
Sheet Coordinate System (origin at bottom-left):

  ^  Y
  |
  |  +-----------------------+
  |  |                       |  sheet_height
  |  |   Nested Parts        |
  |  |                       |
  |  +-----------------------+
  +-------------------------> X
  (0,0)    sheet_width
```

**Placement Strategy:**
1. Start at (0, 0)
2. Move right until collision or edge
3. If collision, move up and retry
4. Continue until valid position found
5. Place part and repeat for next part

### Utilization Calculation

```python
sheet_area = sheet_width * sheet_height
parts_area = sum(polygon.area for polygon in placements)
utilization_pct = (parts_area / sheet_area) * 100
```

**Note:** Utilization is based on raw polygon area, not including spacing gaps. Typical utilization ranges from 60-85% depending on part shapes and sheet size.

---

## Storage Paths

Nested DXF outputs are stored in Supabase Storage under the `pdm-files` bucket.

**Path Structure:**
```
pdm-files/
  projects/
    {project_code}/
      nests/
        {job_id}/
          sheet_01.dxf
          sheet_02.dxf
          ...
          manifest.json
```

**Example:**
```
pdm-files/projects/WMA2025/nests/a1b2c3d4-uuid/sheet_01.dxf
pdm-files/projects/WMA2025/nests/a1b2c3d4-uuid/manifest.json
```

**manifest.json:**
```json
{
  "job_id": "a1b2c3d4-uuid",
  "project_code": "WMA2025",
  "material": "STEEL_HSLA",
  "thickness": 3.0,
  "total_sheets": 2,
  "utilization_pct": 78.5,
  "created_at": "2026-01-30T10:00:00Z",
  "sheets": [
    {
      "sheet_index": 1,
      "filename": "sheet_01.dxf",
      "utilization_pct": 82.3,
      "placement_count": 5
    },
    {
      "sheet_index": 2,
      "filename": "sheet_02.dxf",
      "utilization_pct": 74.7,
      "placement_count": 4
    }
  ]
}
```

---

## Running the Nesting Worker

### Start the worker container

```bash
docker-compose up -d nesting-worker
```

### Verify the container is running

```bash
docker ps | grep pdm-nesting
```

### View container logs

```bash
docker logs pdm-nesting-worker -f
```

Example log output:
```
INFO:root:Starting nesting worker...
INFO:root:Polling for NEST_PARTS tasks every 5 seconds
INFO:root:Picked up task: a1b2c3d4-uuid
INFO:root:Processing nest job: job-uuid
INFO:root:Downloaded 5 DXF files
INFO:root:Parsed 5 polygons
INFO:root:Nesting completed: 2 sheets, 78.5% utilization
INFO:root:Uploaded 2 output sheets to storage
INFO:root:Task a1b2c3d4-uuid completed
```

### Rebuild after code changes

```bash
docker-compose build nesting-worker
docker-compose up -d nesting-worker
```

### Environment Variables

Set in `docker-compose.yml` or `.env` file:

```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key
POLL_INTERVAL=5
LOG_LEVEL=INFO
```

---

## Debugging

### Test nesting manually via API

```bash
# Get material groups for a project
curl "http://localhost:8000/api/nesting/projects/<project-uuid>/groups"

# Create a nesting job
curl -X POST "http://localhost:8000/api/nesting/projects/<project-uuid>/nest" \
  -H "Content-Type: application/json" \
  -d '{
    "material": "STEEL_HSLA",
    "thickness": 3.0,
    "item_ids": ["uuid1", "uuid2"],
    "sheet_width": 1220.0,
    "sheet_height": 2440.0,
    "spacing": 5.0,
    "allow_rotation": true
  }'

# Check job status
curl "http://localhost:8000/api/nesting/jobs/<job-uuid>"
```

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| DXF parsing errors | Invalid/corrupt DXF file | Regenerate DXF from STEP using FreeCAD worker |
| Empty polygon returned | DXF has no closed boundaries | Check DXF in CAD software; verify geometry is closed |
| "No space for part" error | Sheet too small or part too large | Increase sheet size or exclude oversized parts |
| Worker not picking up tasks | Container not running or wrong env vars | Check `docker ps` and verify `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` |
| Low utilization | Large spacing or inefficient part shapes | Reduce spacing parameter; consider manual layout |
| Task stuck in 'processing' | Worker crashed mid-job | Restart worker; task will be retried or marked failed |

### Manual DXF Parsing Test

```python
# Test DXF parsing outside the worker
from dxf_parser import parse_dxf_to_polygon

polygon = parse_dxf_to_polygon("path/to/flat_pattern.dxf")
print(f"Polygon area: {polygon.area} mm²")
print(f"Polygon bounds: {polygon.bounds}")
```

### Manual Nesting Test

```python
# Test nesting algorithm outside the worker
from nester import nest_parts
from shapely.geometry import box

# Create test parts
parts = [
    {"id": "1", "polygon": box(0, 0, 100, 50)},
    {"id": "2", "polygon": box(0, 0, 80, 60)},
]

result = nest_parts(
    parts=parts,
    sheet_width=1220.0,
    sheet_height=2440.0,
    spacing=5.0,
    allow_rotation=True
)

print(f"Total sheets: {result['total_sheets']}")
print(f"Utilization: {result['overall_utilization_pct']:.1f}%")
```

---

## Performance Considerations

- **Typical nesting times:**
  - 1-10 parts: <1 second
  - 10-50 parts: 1-5 seconds
  - 50-100 parts: 5-15 seconds
  - 100+ parts: 15-60 seconds

- **Memory usage:** Scales linearly with number of parts and polygon complexity

- **Worker scalability:** Single-threaded (processes one job at a time)

- **Database load:** Minimal (one poll query every 5 seconds, one write on completion)

- **Storage bandwidth:** DXF files are small (typically 10-100 KB per file)

---

## Future Enhancements

### Algorithm Improvements
- Implement genetic algorithm for better packing
- Support arbitrary rotation angles (not just 90°)
- Add multi-sheet lookahead optimization
- Implement part clustering by size/shape
- Add manual placement adjustment UI

### Feature Additions
- Nest scheduling (priority queue, batch processing)
- Material remnant tracking (save leftover sheet pieces)
- Cost estimation (material cost per sheet)
- Grain direction constraints (for materials with grain)
- Common cut line optimization (shared edges between parts)

### Integration
- Auto-nest on MRP project release
- Integration with laser cutter software (G-code export)
- Print labels for parts (QR codes, barcodes)
- Nesting history and analytics (utilization trends over time)

---

**Last Updated:** 2026-01-30
