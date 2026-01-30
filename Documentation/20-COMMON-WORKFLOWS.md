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

1. Open `http://localhost:8000/docs`
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
curl -X POST http://localhost:8000/api/files/upload \
  -F "file=@csp0030.step" \
  -F "item_number=csp0030"
```

### Via Swagger UI

1. Open `http://localhost:8000/docs`
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
curl -X POST http://localhost:8000/api/bom/bulk \
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
curl -X POST http://localhost:8000/api/tasks/generate-dxf/csp0030
curl -X POST http://localhost:8000/api/tasks/generate-svg/csp0030
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
curl -X PATCH http://localhost:8000/api/items/csp0030 \
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
curl -X PATCH http://localhost:8000/api/items/csp0030 \
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

1. Search for parts by project
2. View routing operations assigned to each part
3. Enter time spent on operations
4. Mark operations as complete
5. View PDF drawings inline

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
curl -X POST http://localhost:8000/api/mrp/projects/{project_id}/print-packet
```

The packet includes a cover sheet with categorized parts lists and individual part PDFs with routing stamp overlays.

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
| API docs | GET | `/docs` |
| Health check | GET | `/health` |
