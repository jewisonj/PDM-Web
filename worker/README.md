# FreeCAD Worker

Docker-based FreeCAD processing for PDM-Web. Handles sheet metal unfolding, DXF generation, and bend drawing creation.

## Setup

1. **Build the container:**
   ```bash
   docker-compose build freecad-worker
   ```

2. **Start the container:**
   ```bash
   docker-compose up -d freecad-worker
   ```

3. **Install worker dependencies:**
   ```bash
   cd worker
   pip install -r requirements.txt
   ```

4. **Start the queue processor:**
   ```bash
   python worker_loop.py
   ```

## Queue Processor (`worker_loop.py`)

Standalone Python script that polls the `work_queue` table and processes tasks automatically. When a STEP file is uploaded, DXF and SVG generation tasks are auto-queued and picked up by this processor.

### How It Works

```
STEP Upload → work_queue: GENERATE_DXF + GENERATE_SVG (pending)
                    ↓
worker_loop.py (polls every 5s)
  1. Query work_queue for pending tasks
  2. Claim task (status → processing)
  3. Download STEP from Supabase Storage → ./files/temp/{item}/
  4. docker exec pdm-freecad-worker python3 /scripts/run_job.py ...
  5. Upload output DXF/SVG → Supabase Storage
  6. Upsert file record in files table
  7. Mark task completed (or failed with error)
  8. Clean up temp files
```

### Environment Variables

Reads from `backend/.env` (shared config):

| Variable | Default | Description |
|----------|---------|-------------|
| `SUPABASE_URL` | (required) | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | (required) | Service role key (admin access) |
| `DOCKER_CONTAINER` | `pdm-freecad-worker` | FreeCAD container name |
| `POLL_INTERVAL` | `5` | Seconds between polls |
| `TEMP_DIR` | `./files/temp` | Local temp directory for file I/O |

### Task Types

| Task Type | FreeCAD Job | Output |
|-----------|-------------|--------|
| `GENERATE_DXF` | `flatten` | `{item}_flat.dxf` |
| `GENERATE_SVG` | `bend_drawing` | `{item}_bends.svg` |

## Usage

### Run Jobs Directly

```bash
# Flatten sheet metal to DXF
docker exec pdm-freecad-worker python3 /scripts/worker/flatten_sheetmetal.py /data/files/ccp0871.stp

# Create bend drawing SVG
docker exec pdm-freecad-worker python3 /scripts/worker/bend_drawing.py /data/files/ccp0871.stp

# With custom output path and K-factor
docker exec pdm-freecad-worker python3 /scripts/worker/flatten_sheetmetal.py /data/files/part.stp /data/files/output.dxf 0.4
```

### Using docker-compose

```bash
# Flatten sheet metal to DXF (Windows - use MSYS_NO_PATHCONV=1 prefix in Git Bash)
docker-compose exec freecad-worker python3 /scripts/worker/flatten_sheetmetal.py /data/files/ccp0871.stp

# Create bend drawing SVG
docker-compose exec freecad-worker python3 /scripts/worker/bend_drawing.py /data/files/ccp0871.stp
```

## Job Types

| Job Type | Script | Output |
|----------|--------|--------|
| Flatten | `flatten_sheetmetal.py` | `*_flat.dxf` |
| Bend Drawing | `bend_drawing.py` | `*_bends.svg` |

## K-Factor

The K-factor determines bend allowance calculation. Default is 0.35.

```bash
# Custom K-factor (third argument)
docker exec pdm-freecad-worker python3 /scripts/worker/flatten_sheetmetal.py /data/files/part.stp /data/files/output.dxf 0.4
```

## File Locations

| Host | Container | Purpose |
|------|-----------|---------|
| `./files/` | `/data/files/` | Input/output files |
| `./FreeCAD/Tools/` | `/scripts/tools/` | Original FreeCAD scripts |
| `./worker/scripts/` | `/scripts/worker/` | Docker-compatible wrappers |
| `./FreeCAD/Mod/sheetmetal/` | `/root/.FreeCAD/Mod/sheetmetal/` | SheetMetal addon |

## Troubleshooting

**Container not starting:**
```bash
docker-compose logs freecad-worker
```

**Script errors:**
```bash
# Run interactively
docker exec -it pdm-freecad-worker bash
python3 /scripts/worker/flatten_sheetmetal.py /data/files/test.stp
```

**Check FreeCAD version:**
```bash
docker exec pdm-freecad-worker python3 -c "import FreeCAD; print(FreeCAD.Version())"
```

**Windows Git Bash path issues:**
If paths get mangled on Windows Git Bash, prefix commands with:
```bash
MSYS_NO_PATHCONV=1 docker exec ...
```
