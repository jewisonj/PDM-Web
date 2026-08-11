# PDM-Web -- Common Workflows and Procedures

Step-by-step guides for daily operations in the PDM-Web system.

**Related Docs:** [17-QUICK-START-CHECKLIST.md](17-QUICK-START-CHECKLIST.md), [14-SKILL-DEFINITION.md](14-SKILL-DEFINITION.md)

---

## 1. Browsing and Searching Items

**Where:** PDM Browser (`/pdm-browser`)

### Steps

1. Log in and click **PDM Browser** on the Home page
2. The items table loads with all items from the database
3. Use the **search bar** to filter by item number, name, or description
4. Use the **State** dropdown to filter by lifecycle state (Design, Review, Released, Obsolete)
5. Use the **Project** dropdown to filter by project
6. Click any **column header** to sort ascending; click again to sort descending
7. The item count indicator shows how many items match your filters (e.g., "42 of 350 items")

### Viewing Item Details

1. Click any row in the items table
2. The **detail panel** slides open on the right side
3. The panel shows:
   - **Item Information** -- item number, name, revision, state, project, material, mass, thickness, cut length, dates
   - **Files** -- list of associated files with type badges; click a file to open it
   - **Bill of Materials** -- direct children (if the item is an assembly)
   - **Where Used** -- parent assemblies that contain this item
4. Click a BOM child or where-used entry to navigate to that item
5. Press **Escape** or click the **X** button to close the panel

---

## 2. Creating a New Item

**Where:** API (items are typically created via BOM upload or the PDM Upload Service)

### Via the API (Swagger UI)

1. Open `http://localhost:8001/docs`
2. Expand **POST /api/items**
3. Click **Try it out**
4. Enter the item data in JSON format:

```json
{
  "item_number": "csp0045",
  "name": "Bracket, Side Mount",
  "revision": "A",
  "iteration": 1,
  "lifecycle_state": "Design",
  "material": "Steel, 1018",
  "thickness": 3.0
}
```

5. Click **Execute**
6. Verify the response shows the created item with an `id`

### Via BOM Upload (Automatic)

Items are automatically created when they appear in a BOM upload and do not yet exist in the database. See the "Uploading a BOM" workflow below.

### Item Number Rules

- Must follow the pattern: 3 lowercase letters + 4-6 digits (e.g., `csp0045`)
- The system normalizes to lowercase automatically
- Use the **Part Number Generator** (`/part-numbers`) to find the next available number for each prefix
- Items with `mmc` or `spn` prefixes are flagged as supplier parts

---

## 3. Uploading a File

Files can be uploaded through the API, the Swagger UI, or the PDM Upload Service.

### Via the API (curl)

```bash
curl -X POST http://localhost:8001/api/files/upload \
  -F "file=@csp0030.step" \
  -F "item_number=csp0030"
```

### Via Swagger UI

1. Open `http://localhost:8001/docs`
2. Expand **POST /api/files/upload**
3. Click **Try it out**
4. Select a file using the file chooser
5. Enter the `item_number` in the form field
6. Click **Execute**
7. The response shows the file record including storage path and iteration number

### Via PDM Upload Service

1. Ensure the PDM Upload Service is running (`scripts/pdm-upload/Start-PDMUpload.bat`)
2. Copy the file to `C:\PDM-Upload`
3. The service automatically:
   - Extracts the item number from the filename (e.g., `csp0030.step` maps to item `csp0030`)
   - Uploads the file to the API
   - Deletes the local file on success (or moves it to `Failed/` on error)
4. Check the log at `C:\PDM-Upload\pdm-upload.log` for confirmation

### Notes

- The item must exist before uploading a file. If the item does not exist, the upload returns a 404 error.
- Re-uploading a file with the same name for the same item increments the file iteration.
- Files are stored in Supabase Storage under the `pdm-files` bucket at `{item_number}/{filename}`.
- Supported file types: STEP, DXF, SVG, PDF, PRT, ASM, DRW, PNG, JPG.

### PDF Upload Date Stamping

**Automatic Feature:** All uploaded PDF files are automatically stamped with "Upload - MM/DD/YYYY" on each page.

- **Position:** Lower-left corner at x=82pt, y=8pt (~1.1" from left edge, just past corner hash marks)
- **Font:** Helvetica 12pt, black text, no background box
- **Purpose:** Provides visual confirmation of upload date without obscuring title block information (revision letters, engineer names, approval signatures)
- **No User Action Required:** Stamping happens automatically during upload

**Technical Details:**
- Uses ReportLab Canvas to overlay text on existing PDF pages
- Processes all pages in multi-page PDFs
- Original PDF content is preserved; stamp is non-destructive
- Stamp position chosen to avoid common title block locations

---

## 4. Uploading a BOM

BOM data flows from Creo Parametric into PDM-Web through the BOM upload pipeline.

### Export from Creo

1. Open the assembly in Creo Parametric
2. Use the tree tool (Tools > Table > Tree) to export the assembly structure
3. Include the following columns in the export: Model Name, DESCRIPTION, PROJECT, PRO_MP_MASS, PTC_MASTER_MATERIAL, CUT_LENGTH, SMT_THICKNESS, CUT_TIME, PRICE_EST
4. Save as a text file

### Upload via PDM Upload Service

1. Ensure the PDM Upload Service is running
2. Rename the exported file to:
   - `BOM.txt` for a single-level BOM
   - `MLBOM.txt` for a multi-level BOM
3. Copy the file to `C:\PDM-Upload`
4. The service automatically:
   - Parses the fixed-width text file to extract parent assembly and child parts
   - Detects quantities by counting duplicate child entries
   - Sends the parsed data to `POST /api/bom/bulk`
   - The API creates any items that do not yet exist
   - The API updates item properties (name, material, mass, thickness, etc.) from the BOM data
   - The API replaces the entire BOM for the parent assembly
5. Check the log for confirmation: `SUCCESS: Uploaded BOM - Parent: wma20120, Children: 15`

### Upload via API Directly

```bash
curl -X POST http://localhost:8001/api/bom/bulk \
  -H "Content-Type: application/json" \
  -d '{
    "parent_item_number": "wma20120",
    "children": [
      {"item_number": "wmp20080", "quantity": 2, "name": "Bracket", "material": "Steel", "mass": 2.5, "thickness": 3.0},
      {"item_number": "wmp20090", "quantity": 1, "name": "Shaft", "material": "Aluminum", "mass": 1.2}
    ],
    "source_file": "BOM.txt"
  }'
```

### What the Bulk BOM Upload Does

1. Creates the parent assembly item if it does not exist
2. Deletes all existing BOM entries for the parent (full replacement)
3. For each child: creates the item if new, or updates its properties if it already exists
4. Creates new BOM relationships with quantities
5. Returns a summary: items created, items updated, BOM entries created

---

## 5. Viewing BOM Tree and Cost Data

### Viewing the BOM Tree

**Where:** PDM Browser detail panel or Item Detail view

1. Navigate to the PDM Browser
2. Click an assembly item to open the detail panel
3. The **Bill of Materials** section shows direct children with quantities
4. Click a child item to navigate to its detail (and see its own BOM if it is a sub-assembly)

### Via the API

**Single-level BOM (direct children only):**

```
GET /api/bom/{item_number}
```

**Full recursive BOM tree:**

```
GET /api/bom/{item_number}/tree
```

Returns a nested JSON structure:

```json
{
  "item": { "item_number": "wma20120", "name": "Assembly", ... },
  "quantity": 1,
  "children": [
    {
      "item": { "item_number": "wmp20080", "name": "Bracket", "price_est": 12.50, ... },
      "quantity": 2,
      "children": []
    }
  ]
}
```

### Where-Used Query

To find all assemblies that contain a given part:

```
GET /api/bom/{item_number}/where-used
```

This is also shown in the detail panel under the **Where Used** section.

### Cost Data

Item cost data is stored in the `price_est` and `unit_price` fields on each item. When viewing a BOM tree, multiply each child's price by its quantity to calculate the assembly cost. Price data is populated through:

- BOM uploads (the `PRICE_EST` column from Creo exports)
- Manual item updates via the API
- The `unit_price` field for supplier parts

---

## 6. Generating DXF and SVG Files

DXF flat patterns and SVG bend drawings are generated from STEP files using the FreeCAD Docker worker.

### Prerequisites

- The FreeCAD Docker container must be running: `docker-compose up -d freecad-worker`
- The item must have a STEP file uploaded to Supabase Storage

### Queue Generation via API

**Generate DXF flat pattern:**

```
POST /api/tasks/generate-dxf/{item_number}
```

**Generate SVG bend drawing:**

```
POST /api/tasks/generate-svg/{item_number}
```

Example using curl:

```bash
curl -X POST http://localhost:8001/api/tasks/generate-dxf/csp0030
curl -X POST http://localhost:8001/api/tasks/generate-svg/csp0030
```

### Monitor Progress

1. Open the **Work Queue** view (`/tasks`)
2. Find the task by item number
3. Status progresses: pending > processing > completed (or failed)
4. Failed tasks show error messages for debugging

Or via API:

```
GET /api/tasks?status=pending
GET /api/tasks?task_type=GENERATE_DXF
```

### Manual Processing via Docker

For testing or one-off generation:

```bash
# Flatten sheet metal to DXF
docker exec pdm-freecad-worker freecadcmd /scripts/flatten_sheetmetal.py \
  /data/files/csp0030.stp /data/files/csp0030_flat.dxf

# Create bend drawing SVG
docker exec pdm-freecad-worker freecadcmd /scripts/bend_drawing.py \
  /data/files/csp0030.stp /data/files/csp0030_bends.svg
```

---

## 7. Downloading Files

### From the PDM Browser

1. Open the PDM Browser and click an item
2. In the detail panel, find the **Files** section
3. Click any file with a type badge (STEP, DXF, SVG, PDF, etc.)
4. Files with storage paths open in a new browser tab via a signed URL
5. PDFs and images render directly in the browser
6. Other file types trigger a download

### Via the API

1. Get the file ID from the item detail:

```
GET /api/items/{item_number}
```

2. Request a signed download URL:

```
GET /api/files/{file_id}/download
```

3. The response contains a time-limited URL (1-hour expiry):

```json
{
  "url": "https://...supabase.co/storage/v1/object/sign/pdm-files/...",
  "filename": "csp0030.step",
  "expires_in": 3600
}
```

4. Open or download using the signed URL

---

## 8. Updating Item Properties

### Via the API

Update specific fields on an existing item:

```bash
curl -X PATCH http://localhost:8001/api/items/csp0030 \
  -H "Content-Type: application/json" \
  -d '{
    "material": "Steel, 304 SS",
    "thickness": 2.5,
    "mass": 1.8,
    "description": "Side bracket, stainless"
  }'
```

Only the fields you include are updated; all other fields remain unchanged.

### Via Parameter File Upload

1. Export a parameter file from Creo (single item, same column format as BOM)
2. Save as `param.txt`
3. Drop into `C:\PDM-Upload`
4. The PDM Upload Service parses the file and calls:

```
PATCH /api/items/{item_number}?upsert=true
```

The `upsert=true` flag creates the item if it does not exist, or updates it if it does.

### Via BOM Upload

When a BOM is uploaded, all child item properties (name, material, mass, thickness, cut length, cut time, price estimate) are updated from the BOM data. This is the most common way properties are populated in bulk.

---

## 9. Managing Lifecycle States

Items have a lifecycle state that controls their status in the engineering process.

### Available States

| State | Meaning |
|---|---|
| Design | Active engineering work; item is editable |
| Review | Pending review or approval |
| Released | Approved for production; should not be modified |
| Obsolete | No longer active; retained for historical reference |

### Changing State via API

```bash
curl -X PATCH http://localhost:8001/api/items/csp0030 \
  -H "Content-Type: application/json" \
  -d '{"lifecycle_state": "Released"}'
```

### Viewing Lifecycle History

Each state change is recorded in the `lifecycle_history` table:

```
GET /api/items/{item_number}/history
```

Returns a list of transitions with old state, new state, timestamp, and the user who made the change.

### Filtering by State

In the PDM Browser, use the **State** dropdown to show only items in a specific lifecycle state. This is useful for finding all items still in Design, or all Released items.

---

## 10. Using the Part Number Generator

**Where:** Part Number Generator (`/part-numbers`)

1. Click **Part Number Generator** on the Home page
2. The view shows all item number prefixes (CS, XX, WM, CC, etc.) with the next available number
3. Click any number to **copy it to your clipboard**
4. Use the copied number when creating a new part in Creo or the PDM system
5. The numbers update in real-time from the database, so they always reflect the latest available

---

## 11. Monitoring the Work Queue

**Where:** Work Queue (`/tasks`)

1. Click **Work Queue** on the Home page
2. The table shows all background tasks with:
   - Task type (GENERATE_DXF, GENERATE_SVG, etc.)
   - Status (pending, processing, completed, failed)
   - Associated item
   - Created and completed timestamps
   - Error messages for failed tasks
3. Use this view to:
   - Verify that DXF/SVG generation tasks completed successfully
   - Identify and debug failed tasks
   - Monitor processing throughput

---

## 12. Using the PDM Upload Service for Bulk Operations

The PDM Upload Service enables bulk file and data upload from a local workstation.

### Starting the Service

```powershell
cd scripts\pdm-upload
.\Start-PDMUpload.bat
```

The service watches `C:\PDM-Upload` and processes files as they appear.

### Bulk File Upload

1. Copy multiple STEP/PDF/DXF/SVG files into `C:\PDM-Upload`
2. The service processes them one at a time in order of arrival
3. Each file is uploaded to the API and then deleted from the watch folder
4. Failed files are moved to `C:\PDM-Upload\Failed\` with an error log entry

### Bulk BOM Update

1. Export BOM from Creo and save as `BOM.txt`
2. Copy to `C:\PDM-Upload`
3. The service parses and uploads the BOM, creating/updating all items

### Bulk Parameter Update

1. Export parameters from Creo and save as `param.txt`
2. Copy to `C:\PDM-Upload`
3. The service parses and updates the item properties

### Monitoring

Check the service log for activity and errors:

```powershell
Get-Content C:\PDM-Upload\pdm-upload.log -Tail 20
```

---

## 13. Working with MRP Tools

### MRP Part Lookup

**Where:** Part Lookup (`/mrp/parts`)

The unified Part Lookup view provides shop floor access to PDFs and part information across all projects.

#### Layout and Features

- **Sidebar:** Left sidebar with search bar, project filter, and parts list (matches Routing Editor design)
- **Project Filter:** Select specific project or "All Parts" to view all items system-wide
- **File Badges:**
  - Red PDF icon (🔴) for parts with PDFs
  - Material badge showing material type (e.g., STEEL, ALUMINUM)
  - Operations badge showing routing operation count
- **Main Panel:** PDF viewer and part details tabs

#### Using Part Lookup

1. **Search for parts:** Type item number or description in search bar
2. **Filter by project:** Select project from dropdown or choose "All Parts" for cross-project search
3. **View PDFs:** Click part with red PDF icon to view drawing in main panel
4. **Check details:** Switch to Details tab to see material, thickness, operations count
5. **Cross-reference:** Material and operations badges help identify part type at a glance

#### PDF Viewing

- PDFs served directly from Supabase Storage buckets
- Signed URLs generated with 1-hour expiry for security
- PDFs open in embedded viewer (no separate browser tab)
- Full-size PDF with zoom controls

#### Notes

- **Replaced Print Lookup:** Part Lookup now serves all PDF viewing needs (Print Lookup page removed in v3.7)
- **All Parts Option:** "All Parts" filter shows items across all projects, not just selected project
- **Storage Architecture:** PDFs stored in `pdm-drawings` bucket, organized by item/revision/iteration

### MRP Routing Editor

**Where:** Routing Editor (`/mrp/routing`)

Assign manufacturing operations to parts and configure operation parameters.

#### Auto-Calculate Waterjet Time

When a part has `cut_length` data from Creo, the routing editor can automatically calculate waterjet cutting time:

1. Navigate to Routing Editor and select a sheet metal part with `cut_length` populated
2. Add a new operation or edit an existing operation
3. In the Station dropdown, select **"012 - Waterjet"**
4. The Time field automatically fills with calculated cut time in minutes
5. Calculation uses material-specific parameters from `cutting_parameters` table:
   - Formula: `speed = ref_speed × (0.25/thickness)^exponent × machinability`
   - Cut time = (cut_length / speed) + handling_time
   - Material codes map as: STEEL/STEEL_HSLA → CS, ALUMINUM/AL → AL, STAINLESS/304SS → SS
6. You can override the calculated time by manually entering a different value

**When Auto-Calculation Happens:**
- Selecting "Waterjet" station in the dropdown
- Applying a routing template that includes Waterjet (Formed SM, Flat SM)
- Only if `cut_length > 0` and valid material/thickness exist

#### Apply Routing Templates

Quick-start routing configurations for common part types:

1. Select an item from the item list (left panel)
2. Click one of the template buttons:
   - **Formed SM** - Sheet metal with forming operations (Waterjet, Press Brake, Deburr, Clean, Weld, Grind, QC)
   - **Flat SM** - Flat sheet metal (Waterjet, Deburr, Clean, QC)
   - **Tube** - Tube cutting and processing (Saw, Deburr, Clean, QC)
   - **Purchased** - Supplier parts (Receiving 10min, Staging 5min, Inspection 5min)
3. Template operations are added to the routing automatically
4. Default times are pre-filled per station:
   - Waterjet: auto-calculated from cut_length (if available)
   - Press Brake: 15 min
   - Deburr: 10 min
   - Clean: 5 min
   - Weld: 30 min
   - Receiving: 10 min
   - Staging: 5 min
   - Inspection: 5 min
5. Edit individual operations to adjust times or sequence

#### Purchased Part Information

For supplier parts (item numbers starting with `mmc` or `spn`):

1. Select the item in the routing editor
2. The "Purchased Part Information" section appears below routing operations
3. Fields available:
   - **Supplier Name** (auto-filled as "McMaster-Carr" for `mmc` items)
   - **Supplier Part Number**
   - **Unit Price** ($/unit)
4. Enter or update values and they save automatically
5. For McMaster parts, a product page link is generated automatically
6. Items with `unit_price` set show a green "$" badge in the item list

### Project Tracking

**Where:** Project Tracking (`/mrp/tracking`)

1. View a Gantt chart of project progress
2. See part hierarchy and completion status
3. Track overall project timeline

### Raw Materials

**Where:** Raw Materials (`/mrp/materials`)

1. View current raw materials inventory
2. Edit stock levels and reorder points inline
3. Track material usage across projects

### Print Packets

Generate a combined PDF print packet for shop floor use:

```bash
curl -X POST http://localhost:8001/api/mrp/projects/{project_id}/print-packet
```

The packet includes a cover sheet with categorized parts lists and individual part PDFs with routing stamp overlays.

**Routing Stamp Design:**
- **Position:** Right edge, vertically centered on each part PDF page
- **Content:** Project code, start/due dates, item number, quantity, routing operations
- **Transparency:** Stamp box uses transparent background (`fill=0`) so underlying drawing content remains visible
- **Border:** Thin (0.5pt) dark gray border for subtle visual separation
- **Text:** Black text for maximum readability on white PDF background
- **Purpose:** Provides routing information without obscuring critical drawing details, dimensions, or notes

### Downloading DXF Bundle for Project

**Where:** MRP Dashboard (`/mrp/dashboard/{project_id}`)

Download all DXF flat patterns for a project as a single ZIP file with descriptive filenames for waterjet programming.

#### Prerequisites

- Project must have sheet metal parts with `needs_dxf=true` flag
- DXF files must be generated (via FreeCAD worker or manual upload)
- Parts must have `thickness` property populated in database

#### Steps

1. Navigate to MRP Dashboard for your project
2. Click the **Download DXF Bundle** button
3. Browser downloads a ZIP file named `project-{project_code}-dxfs.zip`
4. Extract the ZIP to access individual DXF files

#### DXF Filename Format

Each DXF file in the bundle uses a descriptive filename that includes critical manufacturing information:

**Format:** `{item_number}_thk-{thickness}_qty-{quantity}.dxf`

**Examples:**
- `csp0030_thk-0250_qty-2.dxf` - Item csp0030, 0.250" thick, quantity 2
- `xxp1234_thk-0125_qty-1.dxf` - Item xxp1234, 0.125" thick, quantity 1
- `wmp2050_thk-0063_qty-4.dxf` - Item wmp2050, 0.0625" thick (1/16"), quantity 4

**Thickness Encoding:**
- Formatted as 4-digit thousandths of inch (industry standard)
- 0.25" → `0250` (250 thousandths)
- 0.125" → `0125` (125 thousandths, 1/8")
- 0.0625" → `0063` (62.5 thousandths, 1/16")
- 0.1875" → `0188` (187.5 thousandths, 3/16")

**Quantity:**
- Taken from BOM (bill of materials)
- Indicates how many copies of this part are needed for the project

#### Benefits

- **Verify material before cutting:** Operator can see thickness in filename without opening file
- **Batch sorting:** CAM software can sort by thickness for efficient nesting
- **Prevent errors:** Reduces risk of cutting 0.125" part from 0.25" stock by mistake
- **Self-documenting:** Filenames serve as manufacturing documentation
- **Industry standard format:** Matches common sheet metal shop filename conventions

#### Via API Directly

```bash
# Download DXF bundle for a project
curl "http://localhost:8001/api/mrp/projects/<project-uuid>/dxfs" -o dxfs.zip
```

#### Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| No DXF files in bundle | No parts have `needs_dxf=true` | Mark sheet metal parts as needing DXF in item properties |
| Missing thickness in filename | Item `thickness` field is NULL | Update item properties with material thickness |
| Thickness shows "0000" | Same as above | Populate thickness field in items table |
| Generic filename (no metadata) | Old version or item lookup failed | Check backend logs for UUID conversion issues |

---

### Nesting DXF Flat Patterns

**Where:** MRP Dashboard (`/mrp/dashboard/{project_id}`)

Nest sheet metal flat patterns onto stock sheets to optimize material usage.

#### Prerequisites

- MRP project must have parts with DXF flat patterns
- Parts must have `material` and `thickness` properties populated
- DXF files must be in Supabase Storage (generated via FreeCAD worker)
- Nesting worker container must be running: `docker-compose up -d nesting-worker`

#### Steps

1. Navigate to MRP Dashboard for your project
2. Scroll to the **Nesting** section
3. Click **Nest DXF** button
4. The Nest Configuration modal opens and loads material groups
5. Select a material group (e.g., "STEEL_HSLA - 3.0mm")
6. Review the parts list (pre-checked based on BOM quantities)
7. Choose a stock sheet size:
   - 48" x 96" (1220mm x 2440mm)
   - 60" x 120" (1524mm x 3048mm)
   - Custom dimensions
8. Adjust advanced parameters if needed:
   - Spacing: minimum gap between parts (default 5mm)
   - Allow rotation: enable 90-degree rotation (default: on)
9. Click **Start Nesting**
10. The modal closes and the job appears in the Nesting section with status "Queued..."
11. The dashboard automatically polls for updates every 5 seconds
12. When complete, the job shows:
    - Green checkmark
    - Overall utilization percentage
    - Number of sheets generated
    - Download buttons for each output sheet

#### Downloading Nested Sheets

1. Find the completed nest job in the Nesting section
2. Click the download icon next to any sheet (e.g., "Sheet 1")
3. The nested DXF opens in a new browser tab
4. Save or open in CAD software for cutting

#### Via API Directly

```bash
# Get material groups for a project
curl "http://localhost:8001/api/nesting/projects/<project-uuid>/groups"

# Create a nesting job
curl -X POST "http://localhost:8001/api/nesting/projects/<project-uuid>/nest" \
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
curl "http://localhost:8001/api/nesting/jobs/<job-uuid>"

# Download a nested sheet
curl "http://localhost:8001/api/nesting/jobs/<job-uuid>/sheets/1/download"
```

#### Understanding Nesting Results

**Utilization Percentage:**
- Percentage of sheet area covered by parts (not including spacing gaps)
- Typical range: 60-85%
- Lower utilization may indicate inefficient part shapes or oversized sheets

**Sheet Count:**
- Number of stock sheets required to fit all parts
- Depends on part sizes, quantities, and sheet dimensions

**DXF Layers:**
- `SHEET`: Sheet boundary rectangle (cyan)
- `PARTS`: All part outlines at nested positions (white)
- `LABELS`: Part labels with item numbers and quantities (yellow)

#### Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| No material groups shown | No parts with DXF files in project BOM | Generate DXF flat patterns first via FreeCAD worker |
| "No space for part" error | Sheet too small for part size | Select larger sheet size or exclude oversized parts |
| Job stuck in "Processing" | Nesting worker not running | Check `docker ps` and restart worker if needed |
| Low utilization (<50%) | Large spacing or inefficient shapes | Reduce spacing parameter or choose smaller sheet size |
| Job failed | DXF parsing error or worker crash | Check worker logs: `docker logs pdm-nesting-worker` |

---

## 14. Generating a Project Cost Report

**Where:** MRP Cost Report (`/mrp/cost-report`)

Generate a comprehensive cost breakdown for a manufacturing project with interactive station grouping and nested pie chart visualization.

### Steps

1. Navigate to the MRP Dashboard (`/mrp/dashboard`)
2. Select a project from the project dropdown
3. Click the **Cost Report** button in the navigation bar (pink dot badge)
4. The Cost Report view loads with complete project cost analysis

### Cost Report Contents

**Project Info Bar:**
- Project code, customer name, description
- Total project cost (all labor, materials, outsourced ops, and purchased parts)

**Nested Pie Chart (ECharts):**

The cost report uses an interactive nested pie chart showing both high-level cost categories and detailed station breakdown:

- **Outer Ring (Groups):** Station groups with bold colors
  - Weld (Red #ef4444) -- Stations 014-017
  - Assembly (Purple #8b5cf6) -- Stations 020, 025, 035, 045
  - Fabrication (Blue #3b82f6) -- Stations 005, 010
  - QC (Green #10b981) -- Station 050
  - Outsourced (Orange #f97316) -- Stations 060-080
  - Raw Material (Amber #f59e0b)
  - Purchased Parts (Purple #a855f7)
- **Inner Ring (Stations):** Individual workstations color-coded by group (lighter shades)
  - Each station slice uses a lighter shade of its group color
  - Hover to see station name, cost, and percentage
- **Legend Toggle:** Button switches between two legend modes:
  - **Show Groups** (default): Legend shows only outer ring (Weld, Assembly, etc.) for cleaner view
  - **Show Stations**: Legend shows all individual stations for detailed reference
- **Chart Size:** 50% larger than previous Chart.js version for better readability
- **Interactivity:** Click legend items to toggle visibility of slices

**Operations Summary Table:**

The operations table shows labor cost breakdown with two view modes:

- **Grouped View (Default):**
  - Groups displayed with color badges matching chart (e.g., "Weld" in red, "Assembly" in purple)
  - Shows group-level totals: time, cost, station count
  - Click any group row to expand and see individual stations
  - Stations appear indented with detailed breakdown
- **Flat View:**
  - Uncheck "Group By Station" to see all stations listed individually
  - No grouping, sorted by total cost descending
- **Columns:**
  - Station/Group name
  - Total time (minutes)
  - Total cost (USD)
  - Item count (number of parts using this station)
  - Items list (part numbers, comma-separated)

**Summary Cards:**
- Labor: Total labor cost across all operations
- Material: Total raw material cost (SM, tube, bar stock)
- Outsourced: Total cost for outsourced operations (powder coating, anodizing, etc.)
- Purchased: Total cost for purchased components (McMaster, supplier parts)
- Overhead: Overhead multiplier (markup percentage)
- Total: Grand total project cost

**Manufactured Items Table:**
- Each manufactured item (non-purchased) with:
  - Item number and name
  - Material cost (raw material for this part)
  - Labor cost (sum of all operations for this part)
  - Outsourced cost (sum of outsourced operations for this part)
  - Unit cost (material + labor + outsourced for one unit)
  - Extended cost (unit cost × BOM quantity)
- Click the expand arrow to show detailed operations breakdown:
  - Operation name, workstation, time (minutes), cost per operation

**Operations Summary Table:**
- Per-workstation totals across entire project:
  - Workstation name (Laser, Press Brake, Weld, etc.)
  - Total time (minutes across all parts using this workstation)
  - Total cost (labor cost for this workstation across all parts)
  - Item count (number of unique parts using this workstation)

**Purchased Parts Table:**
- All purchased components (`mmc`, `spn` prefixed items):
  - Item number and name
  - Supplier name (e.g., "McMaster-Carr")
  - Supplier part number
  - Quantity (from BOM)
  - Unit price
  - Extended cost (unit price × quantity)

### Printing the Cost Report

1. Click the browser **Print** button (or Ctrl+P / Cmd+P)
2. The print stylesheet automatically:
   - Switches to white background for ink savings
   - Hides navigation bar and unnecessary UI elements
   - Optimizes table layouts for paper
   - Preserves all cost data and formatting
3. Save as PDF or print to paper for customer quotes or internal review

### Via API Directly

```bash
# Get cost report data for a project
curl "http://localhost:8001/api/mrp/projects/<project-uuid>/cost-report"
```

Response includes:
- `project_info`: Project metadata and totals
- `summary`: Labor, material, outsourced, purchased, overhead, total
- `manufactured_items`: Array of items with operations and costs
- `operations_summary`: Per-workstation aggregates
- `purchased_parts`: Purchased items with supplier info
- `chart_data`: Pre-formatted data for pie chart (labels, values, colors)

### Use Cases

- **Estimating:** Calculate total project cost before committing to a customer order
- **Quoting:** Generate professional cost breakdown for customer proposals
- **Budgeting:** Track estimated vs. actual costs (when integrated with time tracking)
- **Analysis:** Identify high-cost operations or workstations for optimization opportunities
- **Planning:** Determine material and labor resource requirements

### Notes

- Cost report uses current pricing from `mrp_cost_settings` (labor rates, material prices, overhead)
- Labor costs are based on routing operation times and workstation rates
- Material costs use per-alloy defaults unless custom prices are set
- Purchased part prices come from `unit_price` field on items
- Report reflects BOM quantities (extended costs = unit cost × quantity)
- Outsourced operations are aggregated into a single category for chart simplicity

---

## 15. Project Scheduling and Capacity Planning

**Where:** MRP Project Tracking (`/mrp/tracking`)

The scheduling system calculates realistic shop floor schedules by considering BOM dependencies, per-station capacity limits, and operation sequencing. This enables accurate project timeline estimates and workload planning.

### How the Scheduling Algorithm Works

The scheduler operates in four phases:

#### Phase 1: Build Dependency Graph

The system analyzes the BOM structure to understand part relationships:

1. **Identify Assemblies:** Parts with children in the BOM are marked as assemblies
2. **Calculate BOM Depth:** Leaf parts have depth 0, sub-assemblies have depth 1, top-level assemblies have depth 2+
3. **Map All Descendants:** For each assembly, recursively collect all child parts and sub-assemblies

This dependency graph ensures that assemblies cannot start until all their child parts are completed.

#### Phase 2: Create Scheduled Tasks

For each part, the scheduler creates individual tasks for each routing operation:

1. **Load Routing:** Fetch all operations for each part (sequence, station, estimated time)
2. **Add Predecessors:** Each task gets two types of dependencies:
   - **Sequential:** Previous operation in the same part's routing must finish first
   - **Assembly:** For assembly first operations, all descendant parts' LAST operations must finish first
3. **Check Completion:** Mark tasks as complete if they exist in the `part_completion` table
4. **Calculate Duration:** Task duration = operation time × part quantity

Example: If `wma20120` (assembly) has child parts `wmp20080` and `wmp20090`, the first operation of `wma20120` cannot start until the last operations of both `wmp20080` and `wmp20090` are complete.

#### Phase 3: Priority Scoring

Tasks are prioritized to optimize schedule efficiency:

1. **Completed tasks first** (+10,000 points): Lock completed work in place
2. **Leaf parts before assemblies** (+100 × (10 - bom_depth)): Schedule foundational parts early
3. **Smaller assemblies first** (+50 - descendant_count): Prioritize simpler assemblies
4. **Earlier routing sequence** (+1000 - sequence): Respect operation order
5. **Thickness grouping** (tie-breaker): Group similar thicknesses for efficient station setup

#### Phase 4: Capacity-Constrained Scheduling

The scheduler allocates tasks to days while respecting station capacity limits:

1. **Check Predecessors:** Only schedule tasks whose dependencies are complete
2. **Find Earliest Start:** Based on predecessor end times
3. **Check Station Capacity:** Ensure the station has available time on the target day
4. **Split Across Days:** If a task exceeds daily capacity, split it across multiple days
5. **Track Utilization:** Update station day slots with used time

### Station Capacity Configuration

Station capacities are hardcoded in the `STATION_CAPACITIES` constant in `frontend/src/utils/scheduling.ts` (lines 108-119):

```typescript
const STATION_CAPACITIES: Record<string, StationCapacityConfig> = {
  '012': { daily_minutes: 12 * 60, max_parallel: 1 },  // Waterjet - runs overnight, 1 machine
  '013': { daily_minutes: 8 * 60, max_parallel: 1 },   // Press Brake - 1 machine
  '010': { daily_minutes: 8 * 60, max_parallel: 1 },   // Saw - 1 machine
  '014': { daily_minutes: 8 * 60, max_parallel: 3 },   // Weld Jigging/Pre-assembly - 3 stations
  '025': { daily_minutes: 8 * 60, max_parallel: 3 },   // Mech Assembly - 3 stations
}
```

**Default Capacity** (for stations not listed above):
- Daily minutes: 1440 (24 hours)
- Max parallel: 3 workers (shared pool)

**Key Constraints:**

| Station Code | Station Name | Daily Hours | Parallel Capacity | Notes |
|--------------|--------------|-------------|-------------------|-------|
| 012 | Waterjet | 12 | 1 machine | Can run overnight shifts |
| 013 | Press Brake | 8 | 1 machine | Single-shift operation |
| 010 | Saw | 8 | 1 machine | Single-shift operation |
| 014 | Weld Jigging | 8 | 3 stations | Multiple welding bays |
| 025 | Mech Assembly | 8 | 3 stations | Multiple assembly tables |
| Others | (Default) | 24 | 3 workers | Shared labor pool across low-volume stations |

**Parallel Capacity:** The `max_parallel` setting models multiple machines or workers operating simultaneously. For example:
- Press Brake with `max_parallel: 1` can process 480 minutes (8 hours) per day
- Weld Jigging with `max_parallel: 3` can process 1440 minutes (8 hours × 3 bays) per day

### Modifying Station Capacities

To add or update station capacities:

1. Open `frontend/src/utils/scheduling.ts`
2. Locate the `STATION_CAPACITIES` constant (line 108)
3. Add or modify entries using this format:

```typescript
'<station_code>': { daily_minutes: <hours> * 60, max_parallel: <count> },
```

**Example:** Add a new laser cutter station (code `015`) running 10 hours/day with 2 machines:

```typescript
const STATION_CAPACITIES: Record<string, StationCapacityConfig> = {
  '012': { daily_minutes: 12 * 60, max_parallel: 1 },
  '013': { daily_minutes: 8 * 60, max_parallel: 1 },
  '010': { daily_minutes: 8 * 60, max_parallel: 1 },
  '014': { daily_minutes: 8 * 60, max_parallel: 3 },
  '025': { daily_minutes: 8 * 60, max_parallel: 3 },
  '015': { daily_minutes: 10 * 60, max_parallel: 2 },  // NEW: Laser - 10 hrs, 2 machines
}
```

4. Rebuild the frontend: `npm run build` (for production) or the dev server will hot-reload
5. Schedule recalculation happens automatically when a project is loaded

**IMPORTANT:** Station codes must match the `station_code` field in the `workstations` table. Use the exact code from your routing operations.

### Real-Time Updates with Live Completion Tracking

The Project Tracking view subscribes to `part_completion` table changes in real-time:

1. **Initial Load:** When a project is selected, the schedule is calculated using current completion data
2. **Subscription:** The view subscribes to Supabase Realtime changes on the `part_completion` table filtered by project ID
3. **Automatic Refresh:** When a shop worker marks an operation complete (via the MRP Part Lookup view):
   - The `part_completion` record is inserted
   - The Realtime subscription triggers in Project Tracking
   - `refreshSchedule()` is called automatically
   - The schedule is recalculated with the new completion status
   - Gantt bars update to reflect completed work and new start dates for dependent tasks

**Technical Implementation:**

```typescript
// Subscribe to completion changes (MrpProjectTrackingView.vue, line 319)
completionChannel.value = supabase
  .channel(`completion-${currentProject.value.id}`)
  .on('postgres_changes', {
    event: '*',
    schema: 'public',
    table: 'part_completion',
    filter: `project_id=eq.${currentProject.value.id}`
  }, () => {
    refreshSchedule()  // Recalculate schedule with new completion data
  })
  .subscribe()
```

**Benefits:**
- Project managers see live progress updates without manual refresh
- Schedule automatically adjusts when bottlenecks are cleared
- Dependent tasks update to show new available start dates
- Accurate "days remaining" calculation based on current status

### Using the Schedule in the UI

**Project Info Display:**
- **Scheduled Days:** Total project duration in working days (includes weekends in count)
- **Start Date:** Calculated by subtracting scheduled days from due date
- **Due Date:** User-provided project deadline

**Gantt Chart:**
- Each part displays as a horizontal bar spanning its scheduled operations
- Bar position is based on the first task's `start_day` and last task's `end_day`
- Bar color indicates status:
  - Gray: Not started (no completed operations)
  - Blue/Green gradient: In progress (partial completion shown as percentage)
  - Green: Complete (all operations finished)
- Hover over bars to see time details: "Qty × Total Minutes"

**Overall Progress Bar:**
- Shows part count breakdown: Complete / In Progress / Not Started
- Automatically updates when completion data changes

### Scheduling Limitations and Future Improvements

**Current Limitations:**
1. Station capacities are hardcoded (not configurable via UI)
2. Schedule assumes operations can be split across days (no "atomic operation" constraint)
3. No resource contention modeling (assumes infinite material availability)
4. Weekends are shown in the Gantt but not excluded from capacity calculations
5. No holiday calendar support

**Future Enhancements:**
1. Move station capacities to database (`workstations` table with `daily_capacity` and `parallel_capacity` columns)
2. Add UI for editing station capacities in the MRP Settings view
3. Implement "non-splittable" operation flag for tasks that must complete in one day
4. Add material lead time and availability tracking
5. Exclude weekends/holidays from capacity allocation
6. Support shift-based scheduling (first shift, second shift, overnight)
7. Add "what-if" scenario comparison (schedule with/without expediting)

### Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Schedule shows 0 days | No routing operations defined | Add routing to parts via MRP Dashboard |
| Assembly starts before parts | Circular BOM reference | Check BOM structure for loops (part is its own ancestor) |
| Bars overlap | Missing predecessor relationships | Verify routing sequence numbers are correct |
| Waterjet shows 24 hrs/day | Station code mismatch | Ensure routing uses code `012` (not `12` or `Waterjet`) |
| Schedule not updating | Supabase Realtime not connected | Check browser console for subscription errors |
| Gantt bars off-screen | Due date too far in future | Adjust `days` computed property buffer (line 106) |

---

## 16. Printing a Shop-Floor Build Tracker Sheet

**Where:** MRP Project Tracking (`/mrp/tracking`) -> **Print Build Tracker Sheet** button -> `/mrp/tracker/:projectCode`

**Full reference:** [31-BUILD-TRACKER-SHEET.md](31-BUILD-TRACKER-SHEET.md)

The Build Tracker Sheet is a printable, whole-project progress sheet for the shop floor -- fab parts grouped under their parent weldment with a checkbox per station, a weldments/assemblies matrix, derived build milestones with plan dates, a purchased-parts receive checklist, a daily log, and a shortages block.

### Steps

1. Open **MRP Project Tracking** and select a project.
2. Click **Print Build Tracker Sheet**. This opens `/mrp/tracker/{projectCode}` in the tracker view.
3. Choose a format in the toolbar:
   - **11x17 (tabloid):** whole project on one page when it fits
   - **Letter (8.5x11 landscape):** parts pages followed by a dedicated "Assemblies & Status" page
4. Toggle **Pre-fill recorded progress**:
   - **On** (default): stations already recorded complete in `part_completion` print as solid boxes, so a reprint mid-project resumes where the shop left off
   - **Off:** prints a fully blank sheet, useful for a first run or a fresh copy
5. Click **Print** (or use the browser's print command). The page's `@page` size is set automatically to match the selected format -- the browser print dialog does the rest.

### Marking Convention

- Mark a completed box with a heavy X in pen.
- For a partial completion, write the completed quantity next to/inside the box instead of an X.
- The shaded ▸STG (Part Staging) column is a gate marking "ready to move to fab/weld" -- it always shows a box even if Part Staging isn't explicitly in the item's routing.

### Sharing the Tracker Sheet (v3.9.10+)

**Use Case:** Create a permanent public link to share tracker status with external stakeholders (customers, vendors, subcontractors) without requiring login access.

**Steps:**

1. Open the Build Tracker Sheet (`/mrp/tracker/{projectCode}`)
2. Select desired format (tabloid or letter)
3. Toggle "Pre-fill recorded progress" as desired (on to show current status, off for blank sheet)
4. Click the **Share** button in the toolbar
5. Wait 3-5 seconds while the system:
   - Captures each tracker page as a high-resolution canvas
   - Generates a multi-page PDF with correct paper size
   - Uploads PDF to the public `shared` bucket
   - Creates a permanent public link
6. Success banner appears with the shareable URL (automatically copied to clipboard)
7. Paste link to recipient (email, Slack, etc.)

**Link Format:** `https://{your-domain}/shared/tracker/{uuid}`

**Benefits:**
- **No login required** - Anyone with the link can view the PDF
- **Snapshot in time** - Captured state shows completed work as of sharing date
- **One-click process** - No manual printing to PDF or file upload needed
- **Automatic clipboard** - Link is ready to paste immediately
- **Permanent link** - URL remains valid indefinitely (until manually revoked)

**Filename Convention:**
- Tabloid: `TRK_{PROJECT_CODE}_{date}.pdf` (e.g., `TRK_WM_0513_2026-08-11.pdf`)
- Letter: `TRK_{PROJECT_CODE}_{date}_LTR.pdf` (e.g., `TRK_SPA0030_2026-08-11_LTR.pdf`)

**Technical Notes:**
- PDF is generated client-side using html2canvas + jsPDF
- Each page captured at 2x resolution for print clarity
- JPEG compression at 0.95 quality for reasonable file size
- Multi-page letter format supported (each page captured independently)
- Uploaded to Supabase Storage `shared` bucket with public read access
- Link metadata stored in `shared_links` table with kind='tracker'

**Managing Shared Links:**

To view or revoke shared links, navigate to the Shares management page (link in MRP Dashboard or `/shares`). You can:
- View all shared links for a project
- See file size and creation date
- Revoke links (deletes from storage and database)
- Re-share to generate fresh snapshot

### Notes

- The sheet regenerates from live data every time it's printed -- there is no saved/stale version to worry about.
- Completion semantics match `MrpShopView` exactly: one `part_completion` row per (project, item, station); a box reads "done" when the recorded quantity covers the item's full project quantity.
- Purchased items (`mmc`/`spn` prefixes, or receive-only routing) get a compact ORD/RCV receive checklist instead of per-station boxes.
- See [31-BUILD-TRACKER-SHEET.md](31-BUILD-TRACKER-SHEET.md) for item classification rules, station-column definitions, milestone derivation, pagination behavior, and known limitations (part-level weld ops, Plumbing/Wiring folded into ASM, BOM flat-quantity vs. tree-rollup).

---

## 17. Printing a Manufacturing Build Book

**Where:** MRP Project Tracking (`/mrp/tracking`) -> **📖 Build Book** button -> `/mrp/book/:projectCode` (also reachable from the **📖 Build Book** cross-link in the Build Tracker Sheet toolbar)

**Full reference:** [32-BUILD-BOOK.md](32-BUILD-BOOK.md)

The Build Book is a day-by-day manufacturing work-order packet for the whole project: a cover/plan page, a station-loading calendar, sequence-numbered work packages for every part operation in dependency order, and one kit/weld sheet per assembly with a stock-pull list, weld sequence, and print-availability status. It is the sibling deliverable to the Build Tracker Sheet (workflow 16) -- the Tracker is a checkbox grid the shop marks up over time, the Book is a work packet you hand to the floor to work through in order.

### Steps

1. Open **MRP Project Tracking** and select a project.
2. Click **📖 Build Book**. This opens `/mrp/book/{projectCode}` in the book view (or click the same button from an already-open Build Tracker Sheet to cross over without reselecting the project).
3. Read the cover page first: est hours, work days, package count, milestones with plan dates, a **REFERENCE PRINTS -- READ FIRST** table of any controlled documents in the project (see below), hours by station area, and the project-wide stock pull summary.
4. Work **Part I -- Work Packages** in `PKG NN` order. Each package card tells you: what stock to pull (only listed at the part's first operation), which parts to run, how many minutes each should take, where each part goes next (`NEXT ->`), and which kit(s) it feeds (`FOR KIT`).
5. When a package's parts are finished, check the line boxes and sign the **COMPLETED BY** line at the bottom of the card. If the package produces a part in its final routed state, it also lists **STAGE KITS** -- move that stock to staging for the named assembly.
6. Move to **Part II -- Kit & Weld Sheets** once a kit's parts are ready. Each kit card lists required sub-assemblies, a kit parts table with **READY BY** (which package + day produced each part), the weld/assembly sequence with estimated minutes (with any assembly-method notes from the Routing Editor printed inline under the relevant step), a **PULL PRINTS** line listing which drawing numbers + revisions to physically go get, and an **INSPECTED BY** sign-off line.
7. Click **Print (8.5x11 portrait)** in the toolbar (or use the browser's print command) for the whole book on-screen/on-paper. The page is letter portrait only -- there is no format toggle like the Build Tracker has.

### Downloading a Section Print Set (v3.9.1)

**Where:** Build Book toolbar -> **"— Print set —"** dropdown -> select a set -> **"⬇ Download prints"**

Rather than dealing with the whole project's drawings, pull just the prints for what you're about to work:

1. Open the dropdown. It's grouped into three sections:
   - **Reference** -- one entry covering every controlled document (`csd*`/`??d*` items) in the project
   - **Work packages** -- one entry per `PKG NN`
   - **Kits** -- one entry per assembly/weldment
2. Pick a set and click **⬇ Download prints**. The button shows "Gathering…" while the backend pulls, stamps, and merges the prints (a work package or kit set generates in roughly 10-15 seconds; times scale with prints in the set).
3. The browser downloads a PDF named `{PROJECT_CODE}_{set label}.pdf`. It opens with:
   - A cover page listing every part in the set, its quantity, and whether a print was found (`MISSING` if not -- check this before heading to the machine)
   - Each print that *was* found, with a white-backed **QTY N** box stamped in the top-right corner of its first page (skipped for the reference set, since quantity doesn't apply to a document)
4. A status message appears next to the button after generation (e.g. "26 prints" or "24 prints · 2 missing") so you know immediately if something's not on file.

This supersedes the old "download the whole book as one bound PDF" workflow for day-to-day shop use -- that full-book PDF endpoint still exists (`POST /api/mrp/projects/{id}/build-book`) and can produce a complete archival copy with every print bound in, but it has no button in the UI: a full book with prints can run 100+ pages and exceed Supabase's storage upload limit (~50 MB), and it's unwieldy to carry to a single station for one operation. Section print sets are purpose-sized for the task in front of you.

### Sequence Governs, Not the Printed Date

- **`PKG NN` numbers are the order to work in.** The planned day/date printed on each package card is guidance only, not a hard deadline -- the cover page states this directly ("WORK THE PACKAGES IN ORDER — PKG numbers govern, printed days are the plan").
- This is intentional: the schedule is a live projection that drifts the moment real shop conditions change. Package sequence still respects true dependency order regardless of when work actually happens, so following `PKG 01, PKG 02, PKG 03...` in order stays safe even after the schedule has moved.
- If you reprint the book after a schedule shift, package numbers can change. Always work from the most recently generated book -- don't try to reconcile old `PKG` numbers against a new printout.

### Notes

- The book regenerates from live data every time it's opened/printed -- there is no saved/stale version.
- Completion rendering matches the Build Tracker and `MrpShopView` exactly: `part_completion` rows drive filled checkboxes and, at the package level, a "RECORDED COMPLETE" badge. There is no pre-fill toggle -- recorded completion always shows, since the book is meant to be regenerated as work progresses rather than marked up by hand.
- Print availability on kit sheets ("PRINTS: assembly ✓/— · parts n/m") is a status indicator on the web view only -- the PDF pages themselves are not embedded there. To get the actual print pages, use a section print set (above) or the full-book PDF endpoint.
- Controlled documents (item numbers with a third-letter `d`, e.g. `csd00010`) never appear as work rows on the Book or Tracker -- they're excluded from classification and instead listed on the cover page under "REFERENCE PRINTS -- READ FIRST". See [32-BUILD-BOOK.md](32-BUILD-BOOK.md) "Document Items" for how they get attached to a project.
- Purchased items print the supplier's own part number (or the item number with its `mmc`/`spn` prefix stripped) instead of the internal PDM item number, plus a SOURCE column on the Tracker showing where the part comes from -- see [32-BUILD-BOOK.md](32-BUILD-BOOK.md) "Purchased-Item Display Convention".
- See [32-BUILD-BOOK.md](32-BUILD-BOOK.md) for how work packages and kit chapters are derived, the `STATION_ABBREV` mapping (note: differs from the Build Tracker's own station-column abbreviations), the section print sets implementation, and the full-book PDF endpoint.

---

## 18. Managing Vendor Kits and Bundle Pricing

**Where:** MRP Dashboard → **Manage Kits** button, Routing Editor

**Use Case:** Compare the cost of purchasing a vendor-supplied bundle (e.g., a pre-welded tube assembly) against building the parts in-house. Track which parts are sourced from vendor kits vs manufactured internally.

**Added:** v3.9.3 (2026-07-09)

### Creating a Kit

1. Navigate to the **MRP Dashboard** for your project
2. Click the **Manage Kits** button in the top toolbar
3. The Kit Management slideout appears on the right side
4. Click **Add Kit**
5. Fill in the kit details:
   - **Kit Number** (auto-suggested: `KIT-001`, `KIT-002`, etc.)
   - **Kit Name** (e.g., "Tube Bundle", "Pre-Welded Frame Kit")
   - **Vendor** (optional: e.g., "ABC Fabrication")
   - **Price** (total price for the entire kit, e.g., `850.00`)
   - **Notes** (optional: any additional information)
6. Click **Add Kit**
7. The kit appears in the list with:
   - Part count (initially 0)
   - In-house cost comparison (calculated once parts are assigned)
   - Savings/extra cost percentage

### Assigning Parts to a Kit

**Method 1: Via Routing Editor (Recommended)**

1. Navigate to **Routing Editor** (`/mrp/routing`)
2. **Select a project filter** from the dropdown (kit sourcing is project-specific)
3. Select a part from the item list
4. Scroll to the **"Part Sourcing for Project [PROJECT-CODE]"** section (below routing operations, above raw materials)
5. Toggle from **Make In-House** to **Part of Kit**
6. Select the kit from the dropdown (e.g., `[KIT-001] Tube Bundle ($850.00)`)
7. Click **Save**
8. Repeat for each part in the vendor kit
9. The routing page shows a status message: "Part source updated"

**Method 2: Via Kit Management Slideout (Bulk)**

1. Open **Manage Kits** slideout
2. Click a kit card to expand it
3. Use the bulk API endpoints to assign multiple parts at once (no UI for bulk assignment yet)

### Viewing Cost Comparison

1. Open **Manage Kits** slideout
2. Each kit card shows:
   - **Kit Price** (vendor quote)
   - **In-House Cost** (labor + material for all assigned parts)
   - **Savings** (positive = kit is cheaper, negative = kit is more expensive)
   - **Savings %** (percentage savings or penalty)
3. Click a kit card to expand and see:
   - List of parts assigned to the kit
   - Part numbers and names

**Example:**
```
KIT-001 - Tube Bundle
Vendor: ABC Fabrication
Parts: 12 parts

Kit Price:        $850
In-House Cost:    $1,240
Savings:          $390 (31%)
```

### Temporarily Disabling a Kit

**Use Case:** Vendor kit is out of stock, need to build parts in-house temporarily.

1. Open **Manage Kits** slideout
2. Find the kit card
3. Click the **green checkmark icon** (toggles to gray circle)
4. Kit is now disabled (`use_kit = false`)
5. All parts assigned to this kit automatically fall back to in-house routing costs
6. Warning badge appears: "Kit pricing disabled - parts use in-house routing"
7. Project cost estimate recalculates to use routing costs instead of kit price

**To Re-Enable:** Click the gray circle icon (toggles back to green checkmark).

### Editing a Kit

1. Open **Manage Kits** slideout
2. Click the **pencil icon** on a kit card
3. Edit any field (kit name, vendor, price, notes)
4. Click **Update Kit**
5. Cost comparison recalculates automatically

### Deleting a Kit

1. Open **Manage Kits** slideout
2. Click the **trash icon** on a kit card
3. Confirm deletion: "Delete kit 'Tube Bundle'? Parts in this kit will revert to in-house routing."
4. Kit is deleted
5. All parts assigned to this kit automatically revert to `source_type = 'make'`
6. Parts now use in-house routing costs

### Understanding Kit Pricing in Cost Estimates

When viewing project cost estimates:

- **Items in active kits** (`use_kit = true`):
  - Show zero individual cost (labor + material = $0)
  - Marked as `"in_kit": true` in API responses
  - Kit price is added as a lump sum to the project total

- **Items in disabled kits** (`use_kit = false`):
  - Fall back to in-house routing costs
  - Calculate normally (labor + material + outsourced)

- **Cost breakdown**:
  - Labor Cost
  - Material Cost
  - Outsourced Cost
  - Purchased Cost (supplier parts)
  - **Kit Cost** (new category - sum of all active kits)
  - Subtotal = sum of all categories
  - Total = Subtotal × Overhead Multiplier

### Project Filter Requirement

**Important:** Part sourcing is **project-specific**. The same part may be:
- **Project A:** Part of a vendor kit
- **Project B:** Made in-house

You **must** select a project filter on the Routing page to configure part sourcing. If no project is selected, the sourcing UI displays: "Select a project filter to configure part sourcing."

### API Endpoints for Kit Management

| Task | Method | Endpoint |
|---|---|---|
| List kits for project | GET | `/api/mrp/projects/{id}/kits` |
| Create kit | POST | `/api/mrp/projects/{id}/kits` |
| Get kit details | GET | `/api/mrp/projects/{id}/kits/{kit_id}` |
| Update kit | PATCH | `/api/mrp/projects/{id}/kits/{kit_id}` |
| Delete kit | DELETE | `/api/mrp/projects/{id}/kits/{kit_id}` |
| Get item sources | GET | `/api/mrp/projects/{id}/item-sources` |
| Set item source | PUT | `/api/mrp/projects/{id}/items/{item_id}/source` |
| Remove item source | DELETE | `/api/mrp/projects/{id}/items/{item_id}/source` |
| Add parts to kit (bulk) | POST | `/api/mrp/projects/{id}/kits/{kit_id}/parts` |
| Remove parts from kit (bulk) | DELETE | `/api/mrp/projects/{id}/kits/{kit_id}/parts` |

### Notes

- **Dark Theme:** Kit Management slideout uses the MRP dark theme (`#0f172a` background, `#38bdf8` accents)
- **Savings Color Coding:**
  - Green = Positive savings (kit is cheaper)
  - Red = Extra cost (kit is more expensive)
- **In-House Cost Calculation:** Includes all routing labor, materials, and outsourced operations for parts assigned to the kit
- **Cost Estimate Integration:** Kit pricing is factored into the unified project cost estimate used across:
  - MRP Dashboard cost display
  - AI Assistant cost queries
  - Build Book cost summaries

**Related Documentation:**
- `37-KIT-BUNDLE-PRICING.md` - Full kit/bundle pricing system documentation
- `03-DATABASE-SCHEMA.md` - `project_kits` and `project_item_source` table schemas
- `06-BOM-COST-ROLLUP-GUIDE.md` - Cost calculation procedures

---

## Quick Reference: API Endpoints for Common Tasks

| Task | Method | Endpoint |
|---|---|---|
| Search items | GET | `/api/items?q=bracket` |
| Get item details | GET | `/api/items/csp0030` |
| Create item | POST | `/api/items` |
| Update item | PATCH | `/api/items/csp0030` |
| Upload file | POST | `/api/files/upload` |
| Download file | GET | `/api/files/{id}/download` |
| Get BOM tree | GET | `/api/bom/csp0030/tree` |
| Get where-used | GET | `/api/bom/csp0030/where-used` |
| Upload BOM | POST | `/api/bom/bulk` |
| Queue DXF | POST | `/api/tasks/generate-dxf/csp0030` |
| Queue SVG | POST | `/api/tasks/generate-svg/csp0030` |
| Check tasks | GET | `/api/tasks?status=pending` |
| Nest material groups | GET | `/api/nesting/projects/{id}/groups` |
| Create nest job | POST | `/api/nesting/projects/{id}/nest` |
| Get nest job | GET | `/api/nesting/jobs/{id}` |
| Download nested sheet | GET | `/api/nesting/jobs/{id}/sheets/{n}/download` |
| Get project cost report | GET | `/api/mrp/projects/{id}/cost-report` |
| Download Build Book section print set | POST | `/api/mrp/projects/{id}/section-prints` |
| Download full Build Book PDF (no UI button) | POST | `/api/mrp/projects/{id}/build-book` |
| API docs | GET | `/docs` |
| Health check | GET | `/health` |
