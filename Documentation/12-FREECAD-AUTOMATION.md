# FreeCAD Automation Reference

## Overview

FreeCAD automation scripts run headless inside a Docker container to convert STEP files into manufacturing documents. The system produces two output types:

- **DXF flat patterns** -- 2D sheet metal unfolded geometry for laser/plasma cutting
- **SVG bend drawings** -- Technical drawings with bend line annotations and dimensions

The Docker-based approach replaces the previous local FreeCAD installation, providing a consistent and reproducible environment regardless of the host machine.

## Docker Architecture

### Docker Image

**Base Image:** `amrit3701/freecad-cli:latest`

This image provides a headless FreeCAD installation (`freecadcmd`) suitable for automated processing without a GUI. The PDM-Web project extends this with custom scripts and the SheetMetal addon.

### Dockerfile

Located at `worker/Dockerfile`:

```dockerfile
FROM amrit3701/freecad-cli:latest

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/root/.FreeCAD/Mod/sheetmetal:${PYTHONPATH}"

RUN mkdir -p /data/input /data/output /scripts

# SheetMetal addon for unfold/flatten operations
COPY FreeCAD/Mod/sheetmetal /root/.FreeCAD/Mod/sheetmetal

# Processing scripts
COPY FreeCAD/Tools/*.py /scripts/
COPY worker/scripts/*.py /scripts/

WORKDIR /data
CMD ["tail", "-f", "/dev/null"]
```

The container runs indefinitely (`tail -f /dev/null`), waiting for jobs to be executed via `docker exec`.

### Docker Compose Configuration

Defined in `docker-compose.yml` at the project root:

```yaml
services:
  freecad-worker:
    build:
      context: .
      dockerfile: worker/Dockerfile
    container_name: pdm-freecad-worker
    volumes:
      - ./files:/data/files
      - ./FreeCAD/Tools:/scripts/tools:ro
      - ./worker/scripts:/scripts/worker:ro
      - ./FreeCAD/Mod/sheetmetal:/root/.FreeCAD/Mod/sheetmetal:ro
    environment:
      - PYTHONPATH=/usr/local/lib:/root/.FreeCAD/Mod/sheetmetal:/scripts/worker
    working_dir: /data
    command: ["tail", "-f", "/dev/null"]
```

**Volume mounts:**

| Host Path | Container Path | Purpose |
|---|---|---|
| `./files` | `/data/files` | Input/output file staging area |
| `./FreeCAD/Tools` | `/scripts/tools` | FreeCAD Python automation scripts (read-only) |
| `./worker/scripts` | `/scripts/worker` | Worker helper scripts (read-only) |
| `./FreeCAD/Mod/sheetmetal` | `/root/.FreeCAD/Mod/sheetmetal` | SheetMetal workbench addon (read-only) |

## Available Scripts

### flatten_sheetmetal.py

**Location:** `worker/scripts/flatten_sheetmetal.py`

**Purpose:** Convert a 3D sheet metal STEP file into a flattened 2D DXF pattern for manufacturing (laser/plasma cutting).

**Process:**

1. Imports STEP file into FreeCAD
2. Identifies the largest face as the base face for unfolding
3. Uses the SheetMetal workbench `SheetMetalUnfolder.getUnfold()` to unfold the part
4. Extracts the outer wire and inner wires (holes) from the flat face
5. Projects 3D geometry to 2D based on face orientation (XY, XZ, or YZ plane)
6. Handles lines, arcs, and circles in the outline
7. Scales geometry for DXF export (mm to inches compensation)
8. Exports the 2D compound to DXF format

**Usage:**

```bash
docker exec pdm-freecad-worker freecadcmd /scripts/flatten_sheetmetal.py \
  /data/files/csp0030.stp /data/files/csp0030_flat.dxf
```

**Arguments:**

| Argument | Required | Description |
|---|---|---|
| `input.step` | Yes | Path to input STEP file (inside container) |
| `output.dxf` | No | Path for output DXF (defaults to `{input}_flat.dxf`) |
| `k_factor` | No | Bend K-factor (default: 0.35) |

### bend_drawing.py (Create bend drawing portable.py)

**Location:** `worker/scripts/bend_drawing.py` (wrapper), `FreeCAD/Tools/Create bend drawing portable.py` (core logic)

**Purpose:** Generate a technical SVG drawing from a STEP file showing bend lines, dimensions, and annotations for shop floor reference.

**Process:**

1. Imports STEP file into FreeCAD
2. Creates a TechDraw page with views (front, top, side as needed)
3. Generates dimensions and annotations programmatically
4. Handles arc direction for proper SVG rendering
5. Applies iterative scale reduction to fit drawings on page
6. Exports the page as SVG

**Usage:**

```bash
docker exec pdm-freecad-worker freecadcmd /scripts/bend_drawing.py \
  /data/files/csp0030.stp /data/files/csp0030_bends.svg
```

**Arguments:**

| Argument | Required | Description |
|---|---|---|
| `input.step` | Yes | Path to input STEP file (inside container) |
| `output.svg` | No | Path for output SVG (defaults to `{input}_bends.svg`) |
| `k_factor` | No | Bend K-factor (default: 0.35) |

### run_job.py

**Location:** `worker/scripts/run_job.py`

**Purpose:** General-purpose job dispatcher that routes processing requests to the appropriate script.

**Supported job types:**

| Job Type | Script Called | Output |
|---|---|---|
| `flatten` | `Flatten sheetmetal portable.py` | DXF flat pattern |
| `bend_drawing` | `Create bend drawing portable.py` | SVG bend drawing |
| `convert_stl` | `convert_to_stl.py` | STL mesh |
| `convert_obj` | `convert_to_obj.py` | OBJ mesh |

**Usage:**

```bash
docker exec pdm-freecad-worker python3 /scripts/run_job.py flatten /data/files/part.step
docker exec pdm-freecad-worker python3 /scripts/run_job.py bend_drawing /data/files/part.step /data/files/part_bends.svg 0.4
```

## Work Queue Integration

The FreeCAD worker integrates with the PDM-Web backend through the `work_queue` database table and the Tasks API.

### Task Types

| Task Type | Description | Input | Output |
|---|---|---|---|
| `GENERATE_DXF` | Create DXF flat pattern | STEP file in Supabase Storage | DXF uploaded to Supabase Storage |
| `GENERATE_SVG` | Create SVG bend drawing | STEP file in Supabase Storage | SVG uploaded to Supabase Storage |

### Queueing Tasks via API

**Queue DXF generation:**

```
POST /api/tasks/generate-dxf/{item_number}
```

**Queue SVG generation:**

```
POST /api/tasks/generate-svg/{item_number}
```

These endpoints automatically look up the item's STEP file and create a pending task in the `work_queue` table.

### Task Lifecycle

1. **Pending** -- Task created in `work_queue` with `status: "pending"`
2. **Processing** -- Worker picks up task, marks `status: "processing"` via `PATCH /api/tasks/{id}/start`
3. **Completed** or **Failed** -- Worker marks final status via `PATCH /api/tasks/{id}/complete`

### Monitoring Tasks

View pending tasks:

```
GET /api/tasks/pending
GET /api/tasks/pending?task_type=GENERATE_DXF
```

View all tasks with filtering:

```
GET /api/tasks?status=failed
GET /api/tasks?task_type=GENERATE_SVG
```

The frontend Work Queue view (`/tasks`) provides a visual interface for monitoring task status and errors.

## DXF/SVG Generation Pipeline

The complete file processing pipeline:

```
1. STEP file uploaded to Supabase Storage
   (via web UI or PDM Upload Service)
         |
2. Task created in work_queue
   (via API endpoint or automatic trigger)
         |
3. STEP file downloaded from Supabase Storage
   to Docker container's /data/files/ volume
         |
4. FreeCAD script processes STEP file
   (flatten_sheetmetal.py or bend_drawing.py)
         |
5. Output file (DXF/SVG) written to /data/files/
         |
6. Output file uploaded to Supabase Storage
   and file record created/updated in database
         |
7. Task marked as completed (or failed with error)
```

## Running the FreeCAD Worker

### Start the worker container

```bash
docker-compose up -d freecad-worker
```

### Verify the container is running

```bash
docker ps | grep pdm-freecad
```

### Run a test job manually

```bash
# Flatten a STEP file to DXF
docker exec pdm-freecad-worker freecadcmd /scripts/flatten_sheetmetal.py \
  /data/files/test_part.stp /data/files/test_part_flat.dxf

# Create a bend drawing SVG
docker exec pdm-freecad-worker freecadcmd /scripts/bend_drawing.py \
  /data/files/test_part.stp /data/files/test_part_bends.svg

# Use the job runner
docker exec pdm-freecad-worker python3 /scripts/run_job.py flatten \
  /data/files/test_part.stp
```

### View container logs

```bash
docker logs pdm-freecad-worker
```

### Rebuild after script changes

```bash
docker-compose build freecad-worker
docker-compose up -d freecad-worker
```

## FreeCAD Python API Reference

### Importing Modules

```python
import FreeCAD
import Part
import Import
import importDXF

# SheetMetal workbench (must be on PYTHONPATH)
import SheetMetalUnfolder
```

### Opening STEP Files

```python
doc = FreeCAD.newDocument("ProcessingDoc")
Import.insert(step_file_path, doc.Name)
imported_obj = doc.Objects[0]
```

### Sheet Metal Unfolding

```python
import SheetMetalUnfolder

# Identify the base face (typically the largest)
faces = imported_obj.Shape.Faces
largest_face = max(faces, key=lambda f: f.Area)
face_index = faces.index(largest_face)
face_name = f"Face{face_index + 1}"

# Build K-factor lookup and unfold
k_factor_lookup = {0.0: 0.35, 1.0: 0.35, 10.0: 0.35}
unfold_result = SheetMetalUnfolder.getUnfold(
    k_factor_lookup, imported_obj, face_name, 0.35
)
```

### DXF Export

```python
import importDXF

export_obj = doc.addObject("Part::Feature", "FlatPattern2D")
export_obj.Shape = compound_shape
doc.recompute()

importDXF.export([export_obj], output_dxf_path)
```

### Cleanup

```python
FreeCAD.closeDocument(doc.Name)
```

## Technical Details

### Coordinate System Handling

The flattening script detects the face orientation and projects 3D coordinates to 2D accordingly:

- **XY plane** (face normal along Z): uses X and Y coordinates
- **XZ plane** (face normal along Y): uses X and Z coordinates
- **YZ plane** (face normal along X): uses Y and Z coordinates

### DXF Scaling

DXF files are scaled by `1/25.4` before export to compensate for DXF importers that assume inch units. When opened in CAD or cutting software that reads in inches, the geometry will display at the correct millimeter dimensions.

### Geometry Types Handled

- **Lines** -- Straight edges between vertices
- **Arcs** -- Circular arc segments, constructed via three-point method (start, midpoint, end)
- **Circles** -- Full circles (typically holes)
- **Inner wires** -- Hole outlines are included in the DXF output

## Debugging

### Test with a known-good part

Test parts are available in `FreeCAD/Tools/Test Parts/`:

```bash
docker exec pdm-freecad-worker freecadcmd /scripts/flatten_sheetmetal.py \
  /scripts/tools/Test\ Parts/ccp0871.stp /data/files/test_output.dxf
```

### Capture full output

```bash
docker exec pdm-freecad-worker freecadcmd /scripts/flatten_sheetmetal.py \
  /data/files/input.stp /data/files/output.dxf 2>&1 | tee freecad_output.log
```

### Interactive debugging

```bash
docker exec -it pdm-freecad-worker bash
freecadcmd
# Then type Python commands interactively
```

### Common Issues

| Issue | Cause | Solution |
|---|---|---|
| `ModuleNotFoundError: SheetMetalUnfolder` | SheetMetal addon not on path | Verify `PYTHONPATH` includes `/root/.FreeCAD/Mod/sheetmetal` |
| `FileNotFoundError` | Input file not in mounted volume | Ensure file is in `./files/` on host (maps to `/data/files/` in container) |
| Empty DXF output | Face orientation not detected | Check face normal in script output; may need geometry adjustment |
| Large memory usage | Complex STEP assembly | Process individual parts rather than full assemblies |
| Script timeout | Very complex geometry | Increase timeout; consider simpler geometry |

## Performance Considerations

- FreeCAD startup overhead is approximately 2-5 seconds per invocation
- Complex STEP files (>10MB) may take 30+ seconds to process
- The container runs persistently to avoid repeated Docker startup overhead
- FreeCAD is not thread-safe; process one file at a time
- Memory usage scales with STEP file complexity; monitor container memory for large files

## Test Parts

Test STEP files are included in `FreeCAD/Tools/Test Parts/` for development and validation:

- `ccp0871.stp`, `ccp0890.stp` -- Standalone STEP files
- `ccp0840_prt.stp` through `ccp0910_prt.stp` -- Part-level STEP exports

These can be used to verify that the Docker container and scripts are working correctly after any changes.
