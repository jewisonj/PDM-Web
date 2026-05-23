# PDM System - Version History and Release Notes

**Track changes, updates, and system evolution across all versions**
**Related Docs:** [27-WEB-MIGRATION-PLAN.md](27-WEB-MIGRATION-PLAN.md), [15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md](15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md)

---

## Current Version

### v3.7.1 (2026-05-22) -- Vite Proxy Timeout Fix

**Status:** Current Production Release

**Summary:** Fixed "Unexpected end of JSON" error when generating print packets for large projects.

#### Bug Fixes

**Print Packet Generation Timeout**

- **Issue:** Large projects (20+ parts) caused "Unexpected end of JSON" errors during print packet generation
- **Root Cause:** Vite dev server proxy default timeout (~30-60 seconds) was too short for operations that download multiple PDFs, create overlays, and combine into one packet
- **Fix:** Added `timeout: 300000` (5 minutes) to Vite proxy configuration in `frontend/vite.config.ts`
- **Note:** Only affects development mode; production serves frontend directly from backend (no proxy)
- **Commit:** 03f788e

#### Files Changed

- `frontend/vite.config.ts` -- Added timeout to proxy configuration

#### Documentation

- Added Pitfall #36 to Development Notes explaining the timeout issue and fix
- Added Reminder #35 documenting the Vite proxy timeout pattern

---

### v3.7 (2026-05-12) -- MRP Part Lookup Redesign and PDF Serving Improvements

**Status:** Previous Release (superseded by v3.7.1)

**Summary:** Redesigned MRP Part Lookup view with unified layout, removed Print Lookup page, improved PDF serving via Supabase Storage, and documented mapkey changes for Creo favorites.

#### Features Added

**Unified Part Lookup View**

The MRP Part Lookup view has been completely redesigned to match the Routing Editor layout and serve as the unified view for all part/PDF viewing needs:

- **Sidebar Layout:** Left sidebar with search bar and project filter matches Routing Editor design
- **All Parts Option:** New "All Parts" option in project filter shows all items across all projects (not just project-specific)
- **File Badges:** PDF icons displayed in red (🔴) for visual clarity, Material badges show material type, Operations badges show routing operation count
- **Project Filter:** Dropdown to filter by specific project or view all parts system-wide
- **Removed Print Lookup:** Print Lookup page completely removed (route commented out, all navigation links removed)
- **Shop Terminal Navigation:** MRP Shop view navigation now shows only Shop Terminal and Part Lookup buttons (Print Lookup button removed)

**PDF Serving via Supabase Storage**

PDFs are now served directly from Supabase Storage buckets using storage helper functions:

- **Storage Buckets:** Files stored in three buckets: `pdm-drawings` (PDFs), `pdm-cad` (PRT/ASM), `pdm-exports` (STEP/DXF/SVG)
- **Storage Helper Functions:** New `frontend/src/services/storage.ts` provides helper functions for URL generation
- **Key Function:** `getSignedUrlFromPath()` parses storage paths and creates signed URLs (1-hour expiry)
- **File Path Format:** Stored in `files` table as `pdm-drawings/csp00025/A/1/csp00025.pdf` (no separate `storage_path` column)
- **Bug Fix:** Fixed queries that tried to select non-existent `storage_path` column (use `file_path` column directly)

**Mapkey Changes for Creo Integration**

Documented changes to Creo mapkeys replacing FAV_ favorite references with hard-coded paths:

- **FAV_ Favorites Removed:** All FAV_9_, FAV_10_, FAV_14_ favorite button references replaced with computer_pb navigation
- **Hard-Coded Paths:** Uses `computer_pb` button + double-action Select/Activate for folder navigation
- **Two Destination Paths:**
  - `C:\PTC_Data\formats` (for drawing format files)
  - `C:\PDM-Upload` (for file exports to PDM system)
- **12 Mapkeys Modified:** All export and format selection mapkeys updated
- **Documentation:** Created `MAPKEY_CHANGES.md` at project root with full details

#### Database/Storage Architecture

**Files Table Structure:**
- `id` (UUID) - Primary key
- `item_id` (UUID) - Links to items table
- `file_type` (TEXT) - PDF, STEP, DXF, SVG, CAD, etc.
- `file_name` (TEXT) - Original filename
- `file_path` (TEXT) - Full storage path including bucket (e.g., `pdm-drawings/csp00025/A/1/csp00025.pdf`)
- `file_size` (INTEGER) - Size in bytes
- `revision` (TEXT) - File revision letter
- `iteration` (INTEGER) - File iteration number

**Storage Buckets:**
- `pdm-drawings` - PDF files
- `pdm-cad` - Creo CAD files (PRT, ASM)
- `pdm-exports` - Exported files (STEP, DXF, SVG)
- `pdm-other` - Other file types

**Storage Helper Functions (`frontend/src/services/storage.ts`):**
- `parseStoragePath()` - Parses full path to extract bucket and path
- `getSignedUrl()` - Creates signed URL for bucket/path (1 hour expiry)
- `getSignedUrlFromPath()` - Creates signed URL from full storage path
- `getBucketForFile()` - Maps file extension to bucket
- `buildStoragePath()` - Builds storage path from item/revision/iteration
- `uploadFile()` - Uploads file to appropriate bucket
- `downloadFile()` - Downloads file as blob
- `createFileRecord()` - Creates/updates files table record

#### Frontend Changes

**Modified View:** `frontend/src/views/MrpPartLookupView.vue` (~500 lines redesigned)

- **Layout:** Switched from top search bar to sidebar layout matching Routing Editor
- **Sidebar Components:**
  - Search input with icon
  - Project filter dropdown (All Parts + project-specific options)
  - Parts list with scrollable table
  - File badges (PDF red icon, Material badge, Operations badge)
- **Main Panel:**
  - PDF viewer using signed URLs from Supabase Storage
  - Part details tab with material/operations info
- **Data Loading:**
  - Loads all files and builds availability sets for badge display
  - Uses `getSignedUrlFromPath()` to generate PDF URLs
  - Queries files table using `file_path` column (not `storage_path`)

**Removed View:** `frontend/src/views/MrpPrintLookupView.vue` (DELETED)

- Print Lookup page no longer needed
- Part Lookup view serves all PDF viewing needs

**Modified View:** `frontend/src/views/MrpShopView.vue` (~20 lines modified)

- Removed "Print Lookup" navigation button
- Navigation now shows only "Shop Terminal" and "Part Lookup"

**Modified Router:** `frontend/src/router/index.ts`

- Print Lookup route commented out (lines 97-102)
- Route definition preserved in comments for reference

#### Files Changed Summary

- `frontend/src/views/MrpPartLookupView.vue` -- Complete redesign with sidebar layout, all parts filter, PDF serving
- `frontend/src/views/MrpPrintLookupView.vue` -- DELETED
- `frontend/src/views/MrpShopView.vue` -- Removed Print Lookup navigation button
- `frontend/src/router/index.ts` -- Commented out Print Lookup route
- `frontend/src/services/storage.ts` -- Storage helper functions for PDF serving
- `MAPKEY_CHANGES.md` -- NEW, documents Creo mapkey changes

#### Use Cases

**Part Lookup View:**
- **Shop Floor PDF Access:** Workers can quickly find and view PDFs for any part across all projects
- **Project-Specific View:** Filter to see only parts in a specific project
- **Material Identification:** Material badges show material type at a glance
- **Routing Status:** Operations badges show if routing is defined
- **All Parts View:** "All Parts" option enables cross-project part search

**PDF Serving:**
- **Secure Access:** Signed URLs expire after 1 hour, preventing unauthorized long-term access
- **No Backend Proxy:** PDFs served directly from Supabase Storage, reducing backend load
- **Browser Caching:** Signed URLs enable browser caching for better performance
- **Multiple Buckets:** Files organized by type for easier management and access control

**Mapkey Changes:**
- **Portable Configuration:** Mapkeys no longer depend on Creo favorites being set up correctly
- **Consistent Paths:** All users navigate to same hard-coded paths
- **No Setup Required:** New users don't need to configure favorites

#### Technical Notes

- **Storage Path Format:** Full path includes bucket prefix (e.g., `pdm-drawings/...`) stored in single `file_path` column
- **No `storage_path` Column:** Database does not have separate `storage_path` column; use `file_path` for all queries
- **Signed URL Expiry:** URLs valid for 1 hour (3600 seconds) by default, configurable in `getSignedUrl()` calls
- **File Type Mapping:** `storage.ts` maps file extensions to buckets and database file types
- **Print Lookup Removal:** Route and view files preserved in comments/history for reference, not deleted from git
- **Mapkey Double-Action:** Creo mapkeys require both Select and Activate commands to navigate into folders

#### Related Documentation

- [MAPKEY_CHANGES.md](../MAPKEY_CHANGES.md) -- Creo mapkey changes reference
- [03-DATABASE-SCHEMA.md](03-DATABASE-SCHEMA.md) -- Updated files table schema
- [04-SERVICES-REFERENCE.md](04-SERVICES-REFERENCE.md) -- Storage service reference
- [20-COMMON-WORKFLOWS.md](20-COMMON-WORKFLOWS.md) -- Updated MRP workflows

---

## Previous Versions

### v3.6 (2026-05-01) -- Station Grouping and Cost Report Enhancements

**Status:** Previous Release (superseded by v3.7)

**Summary:** Enhanced MRP cost reporting with station grouping and nested pie chart visualization, plus refined PDF upload date stamping for better drawing readability.

#### Features Added

**Station Grouping for Cost Reports**

The MRP Cost Report now groups workstations into logical categories for better cost analysis and visualization:

- **Database:** Added `station_group` column to `workstations` table
- **Groups Defined:**
  - **Weld:** Stations 014-017 (Weld Jigging, Tack Welding, Final Welding, Weld Finishing)
  - **Assembly:** Stations 020, 025, 035, 045 (Mechanical Assembly, Electrical Assembly, Sub-Assembly, Final Assembly)
  - **Fabrication:** Stations 005, 010 (Saw, Press Brake)
  - **QC:** Station 050 (Inspection)
  - **Outsourced:** Stations 060-080 (Powder Coating, Anodizing, Plating, Heat Treating, Waterjet External)
- **Backend:** New `operations_summary_grouped` and `cost_breakdown_chart_grouped` data structures in `/api/mrp/projects/{id}/cost-report`
- **Use Case:** Quickly identify which cost categories (Weld vs Assembly vs Fabrication) dominate project costs without drilling into individual stations

**ECharts Nested Pie Chart Visualization**

Replaced Chart.js pie chart with ECharts nested pie chart for richer cost visualization:

- **Inner Ring:** Individual workstations color-coded by group (lighter shades)
- **Outer Ring:** Station groups (Weld, Assembly, Fabrication, QC, Outsourced) with bold colors
- **Interactive Legend Toggle:** Switch between "Show Groups" (outer ring only) and "Show Stations" (all stations)
- **Chart Size:** Increased by 50% for better readability
- **Color Palette:**
  - Weld: Red (#ef4444)
  - Assembly: Purple (#8b5cf6)
  - Fabrication: Blue (#3b82f6)
  - QC: Green (#10b981)
  - Outsourced: Orange (#f97316)
  - Raw Material: Amber (#f59e0b)
  - Purchased Parts: Purple (#a855f7)
- **Dependencies:** Added `echarts` and `vue-echarts` to frontend

**Grouped Operations Table**

Cost report operations table now has grouped view with expandable station details:

- **Default View:** Groups (e.g., "Weld") with group-level totals
- **Expandable:** Click group to see individual stations (e.g., "014 - Weld Jigging", "015 - Tack Welding")
- **Color Badges:** Group names displayed with matching chart colors
- **Toggle:** Switch between grouped and flat view using "Group By Station" checkbox

**PDF Upload Date Stamping (Refinement)**

Improved PDF date stamp positioning to avoid title block conflicts:

- **Previous Issue:** Stamp overlapped title blocks in lower-right corner, obscuring revision letters and signatures
- **New Position:** Lower-left corner at x=82pt, y=8pt (~1.1" from left edge, just past corner hash marks)
- **Font Size:** Increased from 8pt to 12pt for better visibility
- **Format:** "Upload - MM/DD/YYYY" in Helvetica, black text, no background box
- **Location:** `backend/app/routes/files.py` in `stamp_pdf_upload_date()` function
- **Files Changed:** `backend/app/routes/files.py`

#### Database Changes

**Migration: Add station_group to workstations**

```sql
ALTER TABLE workstations ADD COLUMN station_group TEXT;

-- Update existing stations with groups
UPDATE workstations SET station_group = 'Fabrication' WHERE station_code IN ('005', '010');
UPDATE workstations SET station_group = 'Weld' WHERE station_code IN ('014', '015', '016', '017');
UPDATE workstations SET station_group = 'Assembly' WHERE station_code IN ('020', '025', '035', '045');
UPDATE workstations SET station_group = 'QC' WHERE station_code = '050';
UPDATE workstations SET station_group = 'Outsourced' WHERE station_code IN ('060', '065', '070', '075', '080');
```

**Schema Change:**

| Table | Column | Type | Description |
|-------|--------|------|-------------|
| `workstations` | `station_group` | TEXT | Logical grouping: Weld, Assembly, Fabrication, QC, Outsourced, Other |

#### Backend Changes

**Modified Endpoint:** `GET /api/mrp/projects/{project_id}/cost-report`

- **Added Fields to Response:**
  - `operations_summary_grouped`: Array of group-level summaries with nested stations
  - `cost_breakdown_chart_grouped`: Chart data with group-level aggregation
- **Query Enhancement:** Fetch `station_group` from `workstations` table
- **Grouping Logic:** Aggregate operations by `station_group`, sum time and cost, collect stations per group
- **Chart Data:** Prepare both individual station slices (with `station_group` tag) and grouped slices (with nested `stations`)
- **File:** `backend/app/routes/mrp.py` (~100 lines modified)

**New Data Structures:**

```python
# Per-group summary
{
  "group_name": "Weld",
  "total_time_min": 245.5,
  "total_cost": 4910.0,
  "station_count": 4,
  "stations": [
    {
      "station_code": "014",
      "station_name": "Weld Jigging",
      "is_outsourced": false,
      "total_time_min": 60.0,
      "total_cost": 1200.0
    },
    ...
  ]
}

# Grouped chart slice
{
  "label": "Weld",
  "value": 4910.0,
  "category": "labor",
  "stations": [...]  # Same as above
}
```

#### Frontend Changes

**Modified View:** `frontend/src/views/MrpCostReportView.vue` (~300 lines modified)

- **Replaced Chart.js with ECharts:** Swapped `vue-chartjs` for `vue-echarts` with nested pie chart
- **New Interfaces:**
  - `OperationSummaryGrouped`: Group-level operation data with nested stations
  - `GroupStation`: Individual station within a group
  - `ChartSliceGrouped`: Chart data with nested station details
- **Chart Configuration:**
  - Inner ring (radius 0-55%): Individual stations with group-based colors
  - Outer ring (radius 60-80%): Station groups
  - Tooltip: Shows station/group name, cost, percentage
  - Legend: Toggle between groups (default) and all stations
- **Operations Table:**
  - Grouped view with expandable rows
  - Group badge with matching chart color
  - Station detail rows hidden by default, expand on click
  - Toggle to switch to flat view (all stations listed)
- **Color System:**
  - `groupColors`: Bold colors for outer ring (Weld red, Assembly purple, etc.)
  - `stationColors`: Lighter shades for inner ring (4 shades per group)
  - Color assignment: Stations inherit group color with index-based shade selection
- **Legend Toggle:** Button switches between `showDetailedLegend` (stations) and group-only view

**Dependencies Added:**

```json
{
  "echarts": "^6.0.0",
  "vue-echarts": "^8.0.1"
}
```

#### Files Changed Summary

- `backend/app/routes/mrp.py` -- Station grouping logic, grouped summaries, chart data
- `frontend/src/views/MrpCostReportView.vue` -- ECharts nested pie, grouped table, legend toggle
- `frontend/package.json` -- Added echarts and vue-echarts
- `backend/app/routes/files.py` -- PDF stamp position refinement (already in v3.5.1)
- Database migration (manual via Supabase SQL Editor) -- Add station_group column

#### Use Cases

- **Cost Category Analysis:** Quickly see if Weld, Assembly, or Fabrication dominates project costs
- **Drill-Down Detail:** Click groups to expand and see individual station costs
- **Visual Cost Distribution:** Nested pie chart shows both high-level (groups) and detailed (stations) at once
- **Legend Clarity:** Toggle legend between groups (fewer items, cleaner) and all stations (detailed)
- **Comparison:** Compare multiple projects by group-level costs without station noise
- **PDF Readability:** Upload stamps no longer obscure title block signatures and revision letters

#### Technical Notes

- **Station Group Assignment:** Groups assigned manually in migration, not auto-detected
- **Ungrouped Stations:** Stations without `station_group` default to "Other"
- **Chart Color Mapping:** Station colors use index modulo to cycle through 4 shades per group
- **ECharts Performance:** Nested pie renders faster than Chart.js for large datasets (>50 slices)
- **Legend Toggle:** Only affects visible legend items, chart data remains unchanged
- **PDF Stamping:** Uses ReportLab Canvas to overlay text on existing PDF pages

#### Related Documentation

- [03-DATABASE-SCHEMA.md](03-DATABASE-SCHEMA.md) -- Updated workstations table schema
- [04-SERVICES-REFERENCE.md](04-SERVICES-REFERENCE.md) -- Updated cost-report endpoint
- [02-PDM-COMPLETE-OVERVIEW.md](02-PDM-COMPLETE-OVERVIEW.md) -- MRP cost reporting overview
- [20-COMMON-WORKFLOWS.md](20-COMMON-WORKFLOWS.md) -- Cost report usage workflow

---

## Previous Versions

### v3.5.1 (2026-04-30) -- Routing Editor Enhancements and PDF Upload Improvements

**Status:** Previous Release (superseded by v3.6)

**Summary:** Enhanced MRP routing editor with automatic waterjet time calculation, new Purchased routing template, improved UI state management, and refined PDF upload date stamping.

#### Features Added

**Automatic Waterjet Time Calculation in Routing Editor**

The routing editor now automatically calculates waterjet cutting time when selecting the Waterjet station or applying routing templates:

- **Auto-calculation trigger:** When "012 - Waterjet" is selected in the station dropdown
- **Data source:** Uses `cut_length` from item data (populated from Creo `CUT_LENGTH` parameter)
- **Formula:** `speed = ref_speed × (0.25/thickness)^exponent × machinability` from `cutting_parameters` table
- **Cut time:** `(cut_length / speed) + handling_time` in minutes
- **Material mapping:** STEEL/STEEL_HSLA → CS, ALUMINUM/AL → AL, STAINLESS/304SS → SS
- **Template integration:** Auto-fills time when applying "Formed SM" or "Flat SM" templates
- **Manual override:** User can edit the calculated time if needed

This eliminates manual time estimation for waterjet operations and ensures consistency with material-specific cutting speeds.

**New Purchased Routing Template**

Added a "Purchased" routing template for supplier parts:
- **005 - Receiving:** 10 minutes
- **020 - Staging:** 5 minutes
- **050 - Inspection:** 5 minutes

Use this template for `mmc` and `spn` prefixed items that don't require manufacturing but need receiving/inspection tracking.

**Price Badge on Item List**

Items with assigned `unit_price` now show a green "$" badge in the routing editor item list, making it easy to identify purchased parts with pricing data at a glance.

#### Bug Fixes

**Purchase Info Save Hanging After Tab Switch**

- **Issue:** Editing purchased part info (supplier name, part number, unit price) and then switching to a different browser tab would cause the save operation to hang indefinitely with a spinning loader.
- **Fix:** Added `AbortError` handling with automatic retry logic. When a tab switch aborts the save request, the system waits 100ms and retries the save operation.
- **Files Changed:** `frontend/src/views/MrpRoutingView.vue`

**Routing State Reset on Item Change**

- **Issue:** When selecting a new item in the routing editor, stale data from the previously selected item would sometimes appear (old operations, materials, purchase info).
- **Fix:** Added explicit state reset with `watch()` on `selectedItem` to clear all reactive state and fetch fresh data when switching items.
- **Files Changed:** `frontend/src/views/MrpRoutingView.vue`

**PDF Upload Date Stamp Position**

- **Issue:** PDF upload date stamps were overlapping with drawing title blocks in the lower-right corner, obscuring revision letters, engineer names, and approval signatures.
- **Fix:**
  - Moved stamp from lower-right to lower-left corner (x=82pt, ~1.1" from left edge, past corner marks)
  - Increased font size from 8pt to 12pt for better visibility
  - Removed white background box for cleaner appearance
  - New position: lower-left, just above bottom edge (y=8pt)
- **Files Changed:** `backend/app/routes/files.py`

#### Files Changed Summary

- `frontend/src/views/MrpRoutingView.vue` - Waterjet auto-calc, Purchased template, state reset, AbortError retry, price badge
- `backend/app/routes/files.py` - PDF stamp repositioning and font size increase

#### Related Documentation

- [15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md](15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md) - Pitfalls #19-20, Important Reminders #22-27
- [20-COMMON-WORKFLOWS.md](20-COMMON-WORKFLOWS.md) - MRP Routing Editor section updated
- [waterjet-cutting-speeds.md](waterjet-cutting-speeds.md) - Waterjet speed reference

---

### v3.5 (2026-02-07) -- Waterjet Cut Time Calculation and Shop Floor Enhancements

**Status:** Previous Release

#### New Features

- **MRP-Based Waterjet Cut Time Calculation** -- Automatic cut time estimation using physics-based power-law formula:
  - New `cutting_parameters` table with material-specific reference speeds, machinability indices, and thickness exponents
  - Formula: `speed = ref_speed × (0.25/thickness)^exponent × machinability`
  - Auto-calculates `cut_time` on BOM upload (replaces Creo estimates which lack machinability data)
  - Material mapping: `STEEL/STEEL_HSLA → CS`, `AL/ALUMINUM → AL`, `SS/STAINLESS → SS`
  - Default parameters (Q3 quality, 60,000 PSI, 0.014" nozzle):
    - Carbon Steel (CS): 12 IPM @ 0.25", machinability 1.0, exponent 0.55
    - Aluminum (AL): 35 IPM @ 0.25", machinability 2.9, exponent 0.55
    - Stainless Steel (SS): 10.8 IPM @ 0.25", machinability 0.9, exponent 0.55
  - Handling time added from `cost_settings.handling_time_min` (default 0.5 min)
- **Batch Recalculate Cut Times** -- New endpoint `POST /api/items/recalculate-cut-times` to recalculate all existing items:
  - Filters for sheet metal parts with valid material, thickness, and cut_length
  - Updates `routing_operations.est_time_min` for waterjet operations
  - Returns count of updated items
- **Cost Settings UI for Cutting Parameters** -- New section in MRP Cost Settings view:
  - View/edit reference speeds, machinability indices, and exponents for CS/AL/SS
  - Live preview calculation at 0.25" thickness
  - Save changes with optimistic UI updates
- **File Upload Normalization** -- Upload endpoint now normalizes all filenames before storage:
  - Removes redundant suffixes: `xxp123_dxf.dxf → xxp123.dxf`, `abc0001_prt.prt → abc0001.prt`
  - Converts file extensions: `.stp → .step` (canonical extension)
  - Strips type suffixes from filenames: `_prt`, `_asm`, `_drw` (legacy Creo naming)
  - Lowercases all filenames for consistency
  - PDM-Upload script also strips suffixes from item numbers extracted from filenames
- **MRP Shop View Material Filter** -- New material/thickness filter for shop floor queue:
  - Dropdown shows all unique material sizes in project (e.g., `0.25" STEEL`, `0.125" 304SS`)
  - Counts displayed for each filter option and "All Sizes"
  - Filters queue table to show only matching material sizes
  - "Select All" checkbox works on filtered items only (not entire queue)
  - Filter resets when switching projects or stations
  - Supports both sheet metal (thickness + material) and tube (size × material from name)

#### Database Changes

- **New Table:** `cutting_parameters` -- Stores material-specific cutting parameters:
  - Columns: `id`, `material_code` (CS/AL/SS), `material_name`, `ref_speed_ipm` (speed at 0.25"), `machinability` (relative to steel), `exponent` (thickness scaling), `created_at`, `updated_at`
  - Seeded with defaults for CS (1.0), AL (2.9), SS (0.9) machinability
- **Migration:** `create_cutting_parameters_table` -- Creates table and inserts default values

#### Backend Changes

- **New Service:** `backend/app/services/cutting.py` (~127 lines) -- Cutting time calculation logic:
  - `calculate_cutting_speed()`: Power-law formula for speed in IPM
  - `calculate_cut_time()`: Cut time = (length / speed) + handling_time
  - `map_material_to_code()`: Maps item material strings to cutting parameter codes
- **Modified Endpoint:** `POST /api/bom/upload` -- Integrated cut time calculation:
  - Calls `calculate_cut_time()` for each part with valid material/thickness/cut_length
  - Updates `est_time_min` in routing_operations if cut_time > 0
  - Logs calculated cut times for debugging
- **New Endpoint:** `POST /api/items/recalculate-cut-times` -- Batch recalculate existing items:
  - Query items with material, thickness, and cut_length
  - Recalculate cut times using current cutting parameters
  - Update routing_operations for waterjet station
  - Return count of updated items
- **Modified Endpoint:** `POST /api/files/upload` -- Added filename normalization:
  - Strip `_dxf`, `_prt`, `_asm`, `_drw` suffixes
  - Convert `.stp → .step`
  - Lowercase all filenames
  - Preserve original extension

#### Frontend Changes

- **Modified View:** `frontend/src/views/MrpCostSettingsView.vue` (~200 lines added) -- New "Cutting Parameters" section:
  - Table showing CS/AL/SS parameters with editable inputs
  - Real-time preview of cutting speed at 0.25" thickness
  - Save button with loading state and optimistic updates
  - Fetches from `/api/cutting-parameters`, updates via PUT
- **Modified View:** `frontend/src/views/MrpShopView.vue` (~150 lines modified) -- Material filter:
  - Added `material`, `thickness`, `material_size` fields to `QueueItem` interface
  - Fetch material/thickness from items table in queue query
  - Build `material_size` display string (handles sheet metal and tube formats)
  - Computed `availableMaterialSizes` with numeric thickness sorting
  - Computed `filteredQueueItems` filtered by selected material size
  - Material filter dropdown in queue header with counts
  - New "Material" column in parts table
  - Modified "Select All" to work on filtered items only

#### PowerShell Changes

- **Modified Script:** `scripts/pdm-upload/PDM-Upload-Functions.ps1` -- Item number extraction:
  - Added suffix stripping: `_prt`, `_asm`, `_drw` removed before item number detection
  - Example: `abc0001_prt.prt → abc0001` (not `abc0001_prt`)
  - Ensures item numbers match database records after upload normalization

#### Documentation

- **New Reference Doc:** `Documentation/waterjet-cutting-speeds.md` -- Comprehensive cutting speed reference:
  - Machinability index table (mild steel 1.0, stainless 0.9, aluminum 2.9, rubber 15-25+)
  - Cutting speed tables for 8 thickness values across 6 materials
  - Quality vs speed multipliers (Q1-Q5)
  - Equipment variables (nozzle size, pressure, abrasive flow, pump type)
  - Material variables (hardness, thickness, brittleness)
  - Pure waterjet vs abrasive waterjet comparison
  - Rubber cutting notes (pure waterjet preferred, stackable, lower pressure)
  - Links to online calculators (Hypertherm, KMT, OMAX IntelliMAX)
  - Sources with citations

#### Use Cases

- **Accurate Time Estimates:** Physics-based cut time calculation replaces Creo's generic estimates (which lack material/thickness awareness)
- **Material Grouping:** Shop workers can filter queue by material size to batch similar cuts (reduces setup time)
- **Batch Updates:** After tweaking cutting parameters, recalculate all existing items with one API call
- **Filename Consistency:** All uploaded files follow consistent naming (lowercase, no redundant suffixes, canonical extensions)
- **Waterjet Optimization:** Adjust machinability indices and exponents per material as shop floor data is collected

#### Technical Notes

- Cut time formula uses inches throughout (Creo exports thickness and cut_length in inches)
- Handling time added to account for setup, loading, unloading (default 0.5 min)
- Material code mapping is case-insensitive and checks for prefixes/substrings
- Filename normalization happens before storage (all database paths already normalized)
- Material filter sorts by thickness numerically, then by material name alphabetically
- Cutting parameters stored separately from cost_settings to allow future expansion (e.g., per-alloy tube pricing)

---

## Previous Versions

### v3.4 (2026-02-05) -- Project Scheduling and Capacity Planning

**Status:** Previous (superseded by v3.5)

#### New Features

- **Capacity-Constrained Project Scheduling** -- MRP Project Tracking view now calculates realistic shop floor schedules with:
  - BOM-based dependency analysis (assemblies wait for all child parts)
  - Per-station capacity limits (waterjet 12 hrs/day, press brake/saw 8 hrs/day, weld/assembly 3 parallel stations)
  - Priority scoring (leaf parts before assemblies, smaller assemblies first, thickness grouping)
  - Task splitting across days when capacity exceeded
  - Real-time schedule recalculation when operations marked complete
- **Live Completion Tracking** -- Project Tracking view subscribes to `part_completion` table changes via Supabase Realtime:
  - Automatic schedule refresh when shop workers mark operations complete
  - Gantt bars update to reflect new start dates for dependent tasks
  - Accurate "days remaining" calculation based on current status
- **Enhanced Gantt Visualization** -- Gantt bars now positioned using scheduled start/end days instead of simple time estimates:
  - In-progress bars show completion percentage as gradient (green → blue)
  - Bar hover shows quantity × total minutes for each part
  - Weekend highlighting for visual reference

#### Architecture

- **New Module:** `frontend/src/utils/scheduling.ts` (~565 lines) -- Complete scheduling algorithm with four phases:
  1. **Build Dependency Graph:** Analyze BOM structure, identify assemblies, calculate BOM depth, map all descendants
  2. **Create Scheduled Tasks:** Convert routing operations to tasks with predecessor relationships (sequential + assembly dependencies)
  3. **Priority Scoring:** Score tasks based on completion status, BOM depth, assembly size, routing sequence, and thickness
  4. **Capacity-Constrained Scheduling:** Allocate tasks to days respecting station capacity, split large tasks across days, track utilization per station per day
- **Station Capacity Configuration:** Hardcoded in `STATION_CAPACITIES` constant (lines 108-119) with per-station daily minutes and parallel capacity
- **Interfaces:** `ScheduledTask`, `PartSchedule`, `StationDaySlot`, `ScheduleResult` for type-safe scheduling data

#### Frontend Changes

- **Modified View:** `frontend/src/views/MrpProjectTrackingView.vue` -- Integrated scheduling into project load:
  - Store raw parts/BOM/routing data for re-scheduling
  - Call `calculateSchedule()` on project load with completion data
  - Subscribe to `part_completion` changes via Supabase Realtime channel
  - Trigger `refreshSchedule()` on completion events
  - Update Gantt bar positioning to use scheduled start/end days
  - Show "Scheduled Days" in project info display
- **Station Capacity Limits:** Configurable per-station (waterjet, press brake, saw, weld jigging, mech assembly) with fallback to shared worker pool (24 hrs/day, 3 workers) for low-volume stations

#### Documentation

- **New Section:** `Documentation/20-COMMON-WORKFLOWS.md` -- Section 15: "Project Scheduling and Capacity Planning" (~210 lines) with:
  - Algorithm overview (four phases explained in detail)
  - Station capacity configuration table and modification guide
  - Real-time updates technical implementation
  - UI usage guide (project info, Gantt bars, progress bar)
  - Limitations and future improvements
  - Troubleshooting table

#### Use Cases

- **Project Timeline Estimation:** Calculate realistic completion dates based on shop floor capacity constraints
- **Workload Planning:** Visualize per-station utilization to identify bottlenecks
- **Progress Tracking:** See live updates as shop workers complete operations
- **Dependency Management:** Ensure assemblies don't start until all child parts are ready
- **Resource Allocation:** Understand how many parallel stations or shifts are needed to meet deadlines

#### Technical Notes

- Schedule recalculates entirely on each update (no incremental patching) to ensure correctness
- Circular BOM references are protected via parent chain tracking in descendant recursion
- Tasks can split across multiple days if operation time exceeds daily capacity
- Completed tasks receive highest priority (+10,000 points) to lock their positions early
- Weekend days are included in day count but not excluded from capacity allocation (limitation to address in future)

---

## Previous Versions

### v3.3 (2026-02-03) -- Project Cost Report and FreeCAD Script Improvements

**Status:** Previous (superseded by v3.4)

#### New Features

- **Project Cost Report** (`/mrp/cost-report`) -- Comprehensive project cost breakdown view with:
  - Project info bar (code, customer, description, total cost)
  - Interactive pie chart (chart.js) showing cost distribution by labor workstation, raw materials, purchased parts, and outsourced operations
  - Summary cards for labor, materials, outsourced, purchased, overhead multiplier, and total
  - Manufactured items table with expandable operations detail
  - Operations summary table (per-workstation totals across all items)
  - Purchased parts table with supplier info and pricing
  - Print support with `@media print` CSS for browser-based printing
  - Accessible from MRP Dashboard via "Cost Report" button (pink dot badge)
- **DXF Flattening Simplification** -- Updated `flatten_sheetmetal.py` to use FreeCAD's built-in `unfold()` method instead of manual bend manipulation, improving robustness and maintainability.
- **SVG Bend Drawing Improvements** -- Enhanced `bend_drawing.py` with better dimension placement, clearer bend line annotations, and improved layout.

#### Backend Changes

- **Migration:** None (uses existing database schema)
- **New Endpoint:** `GET /api/mrp/projects/{project_id}/cost-report` (~255 lines) -- Aggregates cost data from items, routing operations, purchased parts, and MRP cost settings. Returns comprehensive cost breakdown with labor grouped by workstation, material costs by alloy, outsourced operations aggregated, and purchased parts list.

#### Frontend Changes

- **New View:** `frontend/src/views/MrpCostReportView.vue` -- Full-page cost report with chart.js pie chart, summary cards, three data tables (manufactured items, operations summary, purchased parts), and print support.
- **Router:** Added `/mrp/cost-report` route to `frontend/src/router/index.ts`.
- **Navigation:** Added "Cost Report" button with pink dot badge to MRP Dashboard (`MrpDashboardView.vue`). Button passes selected project as query parameter.
- **Dependencies:** Added `chart.js` and `vue-chartjs` to `frontend/package.json`.

#### Files Changed

- `backend/app/routes/mrp.py` -- Added cost-report endpoint with labor, material, outsourced, and purchased parts aggregation
- `frontend/src/views/MrpCostReportView.vue` (NEW) -- Full-page cost report view
- `frontend/src/router/index.ts` -- Added cost-report route
- `frontend/src/views/MrpDashboardView.vue` -- Added Cost Report nav button
- `frontend/package.json` -- Added chart.js and vue-chartjs
- `FreeCAD/Tools/Flatten_sheetmetal_portable.py` -- Simplified to use built-in unfold()
- `FreeCAD/Tools/Create_bend_drawing_portable.py` -- Improved dimension placement

#### Use Cases

- **Project Estimating:** Review total project cost broken down by labor, materials, outsourced operations, and purchased components.
- **Cost Analysis:** Identify which operations or workstations contribute most to project cost via visual pie chart.
- **Quote Preparation:** Print cost report for customer quotes or internal reviews.
- **Budget Tracking:** Compare estimated costs against actual labor/material expenditures (when integrated with time tracking).

---

## Previous Versions

### v3.2 (2026-01-31) -- Per-Material Pricing and Purchased Parts Enhancement

**Status:** Previous (superseded by v3.3)

#### New Features

- **Per-Material Pricing Defaults** -- Replaced generic material pricing ($0.85/lb SM, $8.00/ft tube) with per-alloy defaults: `default_cs_price_per_lb` ($0.85), `default_al_price_per_lb` ($3.00), `default_ss_price_per_lb` ($3.50). Tube $/ft is now derived at runtime as `$/lb × weight_lb_per_ft`.
- **Material Auto-Prefill** -- When selecting a part with no routing materials assigned, the system auto-maps `item.material` (STEEL, 304SS, ALUMINUM) to `material_code` (CS/AL/SS) and finds closest matching thickness within 15% tolerance.
- **Auto-Calculate Blank Mass** -- Auto-trigger blank mass calculation when both width and height dimensions are filled in the routing editor.
- **Material Assignment Badge** -- Added `[Mat]` badge with golden border (`#b8860b`) in part list when material is assigned to routing.
- **Purchased Part Info Section** -- Added "Purchased Part Information" section to routing editor showing supplier name, part number, and unit price for `mmc`/`spn` prefixed items.
- **McMaster Auto-Fill** -- Automatically populate supplier name ("McMaster-Carr") and add product page link when `mmc` prefix detected. For other supplier parts (`spn`), supplier info is editable.

#### Database Changes

- **Migration `replace_material_price_defaults_per_alloy`** -- Replaced `default_sm_price_per_lb` ($0.85) and `default_tube_price_per_ft` ($8.00) with three per-alloy keys: `default_cs_price_per_lb`, `default_al_price_per_lb`, `default_ss_price_per_lb`.
- **Migration `clear_sm_price_per_unit_use_defaults`** -- Cleared all `raw_materials.price_per_unit` for SM materials to ensure they use the new per-alloy defaults.

#### UI/UX Improvements

- Golden border on assigned material rows in routing editor for visibility.
- Sheet metal materials now show "default" placeholder with effective price (matching tube style).
- Purchased part section appears contextually based on item number prefix.
- McMaster parts get automatic product page link with external icon.

#### Files Changed

- `frontend/src/views/MrpRoutingView.vue` -- Major updates: per-alloy pricing, auto-prefill, auto-calculate, Mat badge, purchased part section.
- `frontend/src/views/MrpCostSettingsView.vue` -- Updated for per-alloy pricing display.
- `frontend/src/views/MrpDashboardView.vue` -- Updated to show material assignment badge in part list.
- `backend/app/routes/mrp.py` -- Updated cost-estimate endpoint for per-alloy defaults.
- `.claude/agents/pricing.md` -- New specialized pricing agent with cost estimation expertise.
- `CLAUDE.md` -- Added pricing agent to agent table.

---

## Previous Versions

### v3.1 (2026-01-30) -- Workspace Comparison and Local Service

**Status:** Previous (superseded by v3.2)

#### New Features

- **Workspace Comparison API** (`POST /api/workspace/compare`) -- New FastAPI endpoint that compares local Creo workspace files against the Supabase vault, returning status (Current, Out of Date, Not In Vault) with timestamps.
- **PDM-Local-Service** (`Local_Creo_Files/Powershell/PDM-Local-Service.ps1`) -- New PowerShell HTTP server on `localhost:8083` with endpoints for file timestamps, check-in (upload), download, and health check. Bridges Creo's embedded browser with local file operations.
- **Auto-create items on upload** -- The `POST /api/files/upload` endpoint now automatically creates items when they don't exist, if the `item_number` matches recognized naming conventions (standard, mmc, spn, zzz).
- **workspace.html modernized** -- All legacy endpoint references (DATASERVER:8082, localhost:8083 old service, dataserver:3000) replaced with new `PDM_CONFIG` object pointing to FastAPI backend (port 8001) and local service (port 8083).

#### Database Changes

- **Migration `add_updated_at_to_files`** -- Added `updated_at` column to `files` table with default `now()`, backfill from `created_at`, and auto-update trigger (`files_updated_at_trigger`).

#### Bug Fixes

- **Wrong port (404s):** workspace.html had `apiUrl: 'http://localhost:8000'` but backend runs on port 8001. Fixed by updating to 8001.
- **All items "Not In Vault" (RLS):** `get_supabase_client()` (anon key) was blocked by RLS for unauthenticated reads. Fixed by using `get_supabase_admin()` (service role key).
- **Windows strftime crash:** `format_vault_time` used `%-m` (Linux-only). Fixed with manual f-string formatting.
- **files.updated_at missing:** Workspace comparison referenced a column that didn't exist. Added via migration.
- **UTC vs local timezone mismatch:** Vault UTC timestamps compared directly against local PowerShell timestamps caused false "Out of Date". Fixed with `dt.astimezone()` conversion.
- **Item number regex ordering:** `mmc12555k88` was truncated to `mmc12555` because standard pattern matched first. Fixed by checking mmc/spn/zzz patterns before standard pattern.
- **Post-upload timestamp mismatch:** Local file's LastWriteTime was older than upload time. Fixed by touching file's LastWriteTime to `Get-Date` after successful upload.

#### Files Changed/Created

- `backend/app/routes/workspace.py` (NEW) -- Workspace comparison endpoint
- `backend/app/routes/files.py` (MODIFIED) -- Auto-create items, regex import
- `backend/app/routes/__init__.py` (MODIFIED) -- Added workspace_router
- `backend/app/main.py` (MODIFIED) -- Added workspace_router
- `Local_Creo_Files/Powershell/PDM-Local-Service.ps1` (MODIFIED) -- Port fix, regex reorder, file touch after upload
- `Local_Creo_Files/creowebjs_apps/workspace.html` (MODIFIED) -- PDM_CONFIG, new API endpoints
- `Local_Creo_Files/Powershell/Backup/Local-FileTimestamp-Service.ps1` (DELETED) -- Obsolete

#### Architecture Decisions

- **Keep a local service:** Creo's embedded browser can't access local files directly. A PowerShell HTTP server on localhost:8083 bridges file operations.
- **Admin client for workspace:** Uses `get_supabase_admin()` to bypass RLS since it's an internal service endpoint without user JWTs.
- **UTC to local conversion:** All vault timestamps are converted to local time server-side before comparison and display.

---

## Previous Versions

### v3.0 -- Web Migration (2025)

**Status:** Previous (superseded by v3.1)

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
| v3.0 | 2025 | Previous | Core web migration, superseded by v3.1 |
| v3.1 | 2026-01-30 | Previous | Workspace comparison, PDM-Local-Service, auto-create items |
| v3.2 | 2026-01-31 | Previous | Per-material pricing, purchased parts enhancement |
| v3.3 | 2026-02-03 | Previous | Project cost report, FreeCAD script improvements |
| v3.4 | 2026-02-05 | Previous | Project scheduling, capacity planning |
| v3.5 | 2026-02-07 | Previous | Waterjet cut time calculation, shop floor enhancements |
| v3.6 | 2026-05-01 | Previous | Station grouping, ECharts nested pie, PDF stamp refinement |
| v3.7 | 2026-05-12 | Previous | MRP Part Lookup redesign, PDF serving improvements, mapkey documentation |
| v3.7.1 | 2026-05-22 | Current | Vite proxy timeout fix for print packet generation |

---

## Checking Your Version

**v3.7.1 indicators:**
- `frontend/vite.config.ts` has `timeout: 300000` in the proxy configuration
- Development Notes has Pitfall #36 (Vite Proxy Timeout)
- Important Reminders has #35 (Vite proxy timeout for long operations)

**v3.7 indicators:**
- `frontend/src/views/MrpPartLookupView.vue` has sidebar layout with project filter and "All Parts" option
- `frontend/src/views/MrpPrintLookupView.vue` does not exist (deleted)
- `frontend/src/router/index.ts` has Print Lookup route commented out
- `frontend/src/services/storage.ts` has `getSignedUrlFromPath()` function
- `MAPKEY_CHANGES.md` exists at project root
- MRP Shop view has only "Shop Terminal" and "Part Lookup" navigation buttons (no Print Lookup)

**v3.6 indicators:**
- `workstations` table has `station_group` column
- MRP Cost Report view uses ECharts nested pie chart (not Chart.js)
- Cost Report has grouped operations table with expandable groups
- `frontend/package.json` includes `echarts` and `vue-echarts` dependencies

**v3.5 indicators:**
- `backend/app/services/cutting.py` exists
- `cutting_parameters` table exists in database
- MRP Cost Settings view has "Cutting Parameters" section
- MRP Shop view has material/thickness filter dropdown
- `Documentation/waterjet-cutting-speeds.md` reference doc exists
- File upload normalizes filenames (strips `_prt`, `_asm`, `_drw`, lowercases)

**v3.4 indicators:**
- `frontend/src/utils/scheduling.ts` exists
- MRP Project Tracking view has Gantt chart with scheduled start/end days
- Project info shows "Scheduled Days" calculation
- Gantt bars positioned by capacity-constrained schedule

**v3.3 indicators:**
- `frontend/src/views/MrpCostReportView.vue` exists
- `frontend/package.json` includes `chart.js` and `vue-chartjs` dependencies
- `backend/app/routes/mrp.py` has `/projects/{project_id}/cost-report` endpoint
- MRP Dashboard has "Cost Report" button with pink dot badge

**v3.2 indicators:**
- `mrp_cost_settings` table has `default_cs_price_per_lb`, `default_al_price_per_lb`, `default_ss_price_per_lb` columns
- Routing view shows purchased part info section for `mmc`/`spn` items
- Material assignment badge `[Mat]` appears in MRP part list

**v3.1 indicators:**
- `backend/app/routes/workspace.py` exists
- `files` table has `updated_at` column
- `PDM-Local-Service.ps1` exists in `Local_Creo_Files/Powershell/`
- `Local-FileTimestamp-Service.ps1` is deleted (was in `Backup/`)
- Backend runs on port 8001 (check `backend/.env` for `API_PORT=8001`)

**v3.0 indicators:**
- Backend runs with `uvicorn` (not Node.js or PowerShell services)
- Frontend uses Vue 3 (check `frontend/package.json` for `vue` dependency)
- Database is Supabase PostgreSQL (check `backend/.env` for `SUPABASE_URL`)
- API available at `http://localhost:8001/docs`

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

**Last Updated:** 2026-05-22
**Current Version:** v3.7.1
**Related:** [27-WEB-MIGRATION-PLAN.md](27-WEB-MIGRATION-PLAN.md), [15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md](15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md)
