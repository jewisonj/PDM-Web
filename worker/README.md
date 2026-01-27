# FreeCAD Worker

Docker-based FreeCAD processing for PDM-Web. Handles sheet metal unfolding, DXF generation, and bend drawing creation.

## Setup

1. **Build the container:**
   ```bash
   docker-compose build freecad-worker
   ```

2. **Start the worker:**
   ```bash
   docker-compose up -d freecad-worker
   ```

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
