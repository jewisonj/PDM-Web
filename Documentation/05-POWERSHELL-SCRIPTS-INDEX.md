# Scripts and Automation Reference

Reference guide for all scripts and automation in the PDM-Web system.

---

## Overview

The PDM-Web system uses a small set of PowerShell scripts as a bridge between local CAD tools (Creo Parametric) and the web-based backend API. These scripts run on the engineer's workstation and handle file uploads, BOM parsing, and parameter synchronization.

Most automation that was previously handled by PowerShell Windows services is now handled directly by the FastAPI backend and Supabase. The remaining scripts serve a focused purpose: moving data from local CAD exports into the web system.

### Script Inventory

| Script | Location | Purpose |
|--------|----------|---------|
| PDM-Upload-Service.ps1 | `scripts/pdm-upload/` | FileSystemWatcher that processes dropped files |
| PDM-Upload-Functions.ps1 | `scripts/pdm-upload/` | HTTP upload helpers, item number extraction, MIME detection |
| PDM-BOM-Parser.ps1 | `scripts/pdm-upload/` | Creo BOM/parameter text file parser |
| PDM-Upload-Config.ps1 | `scripts/pdm-upload/` | Configuration (API URL, watch folder, logging) |
| deploy.ps1 | Project root | Fly.io deployment script |

---

## Upload Bridge Scripts

**Location:** `scripts/pdm-upload/`

These scripts form the "upload bridge" -- a local service that watches a folder on the engineer's workstation and automatically uploads files to the PDM-Web API.

### How It Works

1. The engineer (or Creo) drops files into `C:\PDM-Upload\`.
2. `PDM-Upload-Service.ps1` detects new files via FileSystemWatcher.
3. Based on file type and name, the service routes each file to the appropriate action:
   - CAD/STEP/DXF/SVG/PDF files are uploaded to `POST /api/files/upload`.
   - `BOM.txt` or `MLBOM.txt` files are parsed and sent to `POST /api/bom/bulk`.
   - `param.txt` files are parsed and sent to `PATCH /api/items/{item_number}?upsert=true`.
4. Successfully processed files are deleted from the watch folder.
5. Failed files are moved to `C:\PDM-Upload\Failed\` for manual review.

```
C:\PDM-Upload\              <-- Drop files here
  |
  +-- Failed\               <-- Failed uploads land here
  +-- pdm-upload.log        <-- Log file
```

---

### PDM-Upload-Config.ps1

**Purpose:** Central configuration for all upload bridge scripts.

**Configurable Values:**

| Setting | Default | Description |
|---------|---------|-------------|
| `ApiUrl` | `http://localhost:8000/api` | PDM-Web API base URL |
| `WatchFolder` | `C:\PDM-Upload` | Local folder to monitor for new files |
| `LogFile` | `C:\PDM-Upload\pdm-upload.log` | Log file path |
| `PollInterval` | `500` (ms) | Delay after file detection before processing |
| `MaxLogSize` | `10MB` | Log file rotation threshold |

**Switching to production API:**

Edit `PDM-Upload-Config.ps1` and change the `ApiUrl` value:

```powershell
$Config = @{
    # Local development:
    # ApiUrl = "http://localhost:8000/api"

    # Production:
    ApiUrl = "https://pdm-web.fly.dev/api"
    # ...
}
```

**Logging:**

The `Write-Log` function writes timestamped entries to both the console and the log file. Log files are automatically rotated when they exceed `MaxLogSize`.

Log format:
```
2026-01-29 14:30:00 PDM Upload Service Starting
2026-01-29 14:30:01 Processing: csp0030.step
2026-01-29 14:30:02 SUCCESS: Uploaded csp0030.step for item csp0030
```

---

### PDM-Upload-Service.ps1

**Purpose:** Main service script. Monitors the watch folder and dispatches file processing.

**Requirements:** PowerShell 5.1 or later.

**Starting the service:**

```powershell
cd scripts\pdm-upload
.\PDM-Upload-Service.ps1
```

Leave the PowerShell window open. Press Ctrl+C to stop.

**Startup behavior:**

1. Loads configuration, helper functions, and BOM parser (dot-sourced).
2. Creates the watch folder and `Failed` subfolder if they do not exist.
3. Processes any files already present in the watch folder.
4. Starts a FileSystemWatcher on `Created` events.
5. Runs indefinitely until interrupted.

**File processing flow:**

For each new file detected:

1. Skip temporary files (names starting with `~` or `.`).
2. Wait for the file to be fully written (up to 5 retries, 500ms each).
3. Wait 3 seconds after the Created event to allow related files to finish (Creo PDFs with embedded images).
4. Determine the file action using `Get-FileAction`.
5. Execute the appropriate handler:
   - `Upload` -- Extract item number, upload via `Upload-File`.
   - `BOM` / `MLBOM` -- Parse and upload via `Upload-BOM`.
   - `Parameters` -- Parse and update via `Update-Parameters`.
   - `Skip` -- Ignore unsupported file types.
6. Delete the file on success. On failure, move to `Failed\` folder with duplicate-name handling.

**Skipped items:** Files for `zzz`-prefixed items (reference/placeholder items) are silently deleted without uploading.

---

### PDM-Upload-Functions.ps1

**Purpose:** HTTP client functions and file classification logic.

**Functions:**

#### Get-ItemNumber

Extracts the item number from a filename. Supports these patterns:

| Pattern | Example Filename | Extracted Item Number |
|---------|-----------------|----------------------|
| Standard (3 letters + 4-6 digits) | `csp0030.step` | `csp0030` |
| With suffix | `csp0030_flat.dxf` | `csp0030` |
| Uppercase | `CSP0030_REV_A.pdf` | `csp0030` |
| McMaster | `mmc4464k478.prt` | `mmc4464k478` |
| Supplier | `spn12345.step` | `spn12345` |
| Reference | `zzz00001.prt` | `zzz00001` |

Returns `$null` if no valid item number pattern is found.

#### Get-FileAction

Determines what action to take based on filename and extension.

**Return values:**

| Action | Trigger | Description |
|--------|---------|-------------|
| `Upload` | `.step`, `.stp`, `.pdf`, `.dxf`, `.svg`, `.prt`, `.asm`, `.drw` | Upload as file attachment |
| `BOM` | File named `bom.txt` | Parse as single-level BOM |
| `MLBOM` | File named `mlbom.txt` | Parse as multi-level BOM |
| `Parameters` | File named `param.txt` | Parse as parameter update |
| `Skip` | All other files | Ignore (logs, configs, images, etc.) |

**Ignored files:** Script files (`.ps1`, `.bat`), config files, images, and a hardcoded list of known service files are always skipped.

#### Upload-File

Uploads a file to the API using multipart/form-data via .NET `HttpClient`.

**Parameters:**
- `FilePath` -- Full path to the file.
- `ItemNumber` -- Item number to associate with.

**Endpoint called:** `POST {ApiUrl}/files/upload`

**MIME type detection:**

| Extension | MIME Type |
|-----------|----------|
| `.pdf` | `application/pdf` |
| `.step`, `.stp` | `application/step` |
| `.dxf` | `application/dxf` |
| `.svg` | `image/svg+xml` |
| Others | `application/octet-stream` |

#### Upload-BOM

Parses a BOM text file and uploads the result to the bulk BOM endpoint.

**Parameters:**
- `FilePath` -- Path to the BOM text file.

**Process:**
1. Calls `Parse-BOMFile` to extract parent/children data.
2. Validates that a parent item number and at least one child were found.
3. Constructs a JSON request body with `parent_item_number`, `children`, and `source_file`.
4. Posts to `POST {ApiUrl}/bom/bulk`.

#### Update-Parameters

Parses a parameter text file and updates item properties.

**Parameters:**
- `FilePath` -- Path to the parameter text file.

**Process:**
1. Calls `Parse-ParameterFile` to extract item number and properties.
2. Validates that an item number was found.
3. Constructs a JSON request body with the non-null properties.
4. Sends to `PATCH {ApiUrl}/items/{item_number}?upsert=true`.

The `upsert=true` flag ensures the item is created if it does not already exist in the database.

---

### PDM-BOM-Parser.ps1

**Purpose:** Parses Creo's fixed-width text BOM and parameter exports.

**Functions:**

#### Parse-BOMFile

Parses a Creo BOM tree export text file into structured data suitable for the bulk BOM API.

**Input format:** Fixed-width columns exported from Creo. The file must contain a `Model Name` header row followed by a separator line of dashes.

Example input:
```
Model Name         DESCRIPTION            PROJECT   PRO_MP_MASS   PTC_MASTER_MATERIAL  CUT_LENGTH  SMT_THICKNESS
---------          -----------            -------   -----------   -----------------    ---------   -----------
 WMA20120.ASM     Assembly               PROJ1     10.5          Steel                -           -
   WMP20080.PRT   Bracket                PROJ1     2.5           Steel                500         3.0
   WMP20090.PRT   Shaft                  PROJ1     1.2           Aluminum             300         2.5
```

**Supported columns:** `Model Name`, `DESCRIPTION`, `PROJECT`, `PRO_MP_MASS`, `PTC_MASTER_MATERIAL`, `CUT_LENGTH`, `SMT_THICKNESS`, `CUT_TIME`, `PRICE_EST`

**Parsing behavior:**
- Column positions are calculated dynamically from the header line.
- The top-level assembly (low indent, `.ASM` extension) becomes the parent item.
- All other items become children.
- Duplicate children have their quantity incremented (not duplicated).
- Skeleton parts (`_SKEL.PRT`), standard features (`ASM_RIGHT`, `ASM_TOP`, etc.), and `zzz`-prefixed reference items are skipped.
- Numeric values (mass, thickness, cut_length, etc.) are parsed as doubles; non-numeric or placeholder (`-`) values become null.

**Return value:**
```powershell
@{
    parent_item_number = "wma20120"
    children = @(
        @{ item_number = "wmp20080"; quantity = 2; name = "Bracket"; material = "Steel"; mass = 2.5; thickness = 3.0; cut_length = 500; cut_time = $null; price_est = $null },
        @{ item_number = "wmp20090"; quantity = 1; name = "Shaft"; material = "Aluminum"; mass = 1.2; ... }
    )
}
```

#### Parse-ParameterFile

Parses a Creo parameter export for a single item. Uses the same column-based parsing logic as `Parse-BOMFile` but only reads the first data line.

**Return value:**
```powershell
@{
    item_number = "csp0030"
    name        = "Bracket"
    material    = "Steel"
    mass        = 2.5
    thickness   = 3.0
    cut_length  = 500
    cut_time    = $null
    price_est   = $null
}
```

#### Get-ColumnValue

Internal helper function that extracts a value from a fixed-width line given start and end column positions. Returns `$null` for empty, `-`, or out-of-range values.

---

## Deployment Script

### deploy.ps1

**Location:** Project root (`deploy.ps1`)

**Purpose:** Deploys the PDM-Web application to Fly.io.

**What it does:**

1. Loads environment variables from `backend/.env`.
2. Validates that required variables are set (`SUPABASE_URL`, `SUPABASE_ANON_KEY`).
3. Runs `flyctl deploy` with Supabase credentials passed as Docker build arguments.

**Usage:**
```powershell
.\deploy.ps1
```

**Prerequisites:**
- Fly.io CLI (`flyctl`) installed and authenticated.
- `backend/.env` file with valid Supabase credentials.

**Build arguments passed to Docker:**
- `VITE_SUPABASE_URL` -- Used at frontend build time for Supabase client configuration.
- `VITE_SUPABASE_ANON_KEY` -- Used at frontend build time for Supabase client configuration.

---

## Workflow Examples

### Uploading a STEP File

1. Save `csp0030.step` to `C:\PDM-Upload\`.
2. The upload service detects the file.
3. `Get-ItemNumber("csp0030.step")` returns `csp0030`.
4. `Upload-File` sends a multipart POST to `/api/files/upload` with `item_number=csp0030`.
5. The API stores the file in Supabase Storage at `pdm-files/csp0030/csp0030.step`.
6. The API creates or updates the file record in the database.
7. The local file is deleted.

### Uploading a BOM

1. Export a BOM tree from Creo to `C:\PDM-Upload\BOM.txt`.
2. The upload service detects `BOM.txt` and routes it to `Upload-BOM`.
3. `Parse-BOMFile` extracts the parent assembly and child items with quantities and properties.
4. The parsed data is posted to `/api/bom/bulk`.
5. The API creates/updates all items, deletes old BOM entries, and creates new relationships.
6. The local file is deleted.

### Updating Item Parameters

1. Export parameters from Creo to `C:\PDM-Upload\param.txt`.
2. The upload service detects `param.txt` and routes it to `Update-Parameters`.
3. `Parse-ParameterFile` extracts the item number and properties.
4. The data is sent to `PATCH /api/items/{item_number}?upsert=true`.
5. The API updates (or creates) the item with the new properties.
6. The local file is deleted.

---

## Troubleshooting

### Upload service not detecting files

1. Verify the service is running (PowerShell window is open and showing "File watcher started").
2. Confirm files are being saved to the correct folder (`C:\PDM-Upload\` by default).
3. Check the log file at `C:\PDM-Upload\pdm-upload.log`.

### File upload fails with 404

The item must exist in the database before a file can be uploaded. The upload bridge extracts the item number from the filename and sends it with the upload request. If the item does not exist, the API returns 404.

**Solution:** Upload a BOM or parameter file first to create the item, or create the item manually through the web UI.

### BOM parsing returns no children

1. Verify the BOM file has the expected fixed-width format with a `Model Name` header.
2. Check that the separator line (dashes) appears after the header.
3. Confirm child items have valid item number patterns (3 letters + 4-6 digits).
4. Review the `Failed\` folder for the moved file.

### Files appearing in Failed folder

Check the log file for the error message. Common causes:

- API is not running (connection refused).
- Item number could not be extracted from filename.
- File format does not match expected patterns.
- Network timeout.

### Changing the API URL

Edit `scripts/pdm-upload/PDM-Upload-Config.ps1` and update the `ApiUrl` value. Restart the service after changing configuration.

---

**Last Updated:** 2026-01-29
