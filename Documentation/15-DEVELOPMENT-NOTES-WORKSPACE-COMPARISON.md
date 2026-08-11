# PDM-Web - Development Notes and Lessons Learned

**Key decisions, pitfalls, and patterns from the v3.0 web migration**
**Related Docs:** [27-WEB-MIGRATION-PLAN.md](27-WEB-MIGRATION-PLAN.md), [24-VERSION-HISTORY.md](24-VERSION-HISTORY.md)

---

## Key Architecture Decisions

### 1. Supabase as Backend-as-a-Service

The decision to use Supabase (PostgreSQL + Auth + Storage) eliminated the need for a local database server, local file storage management, and a custom authentication system. This simplified deployment and removed the SQLite file-locking issues from the legacy system.

**Trade-offs accepted:**

- Cloud dependency -- requires internet access to operate
- Supabase RLS (Row Level Security) adds complexity to service-level operations
- Storage paths must be managed as Supabase bucket paths instead of filesystem paths

### 2. FastAPI Over Express/Node.js

Python with FastAPI was chosen for the backend because:

- Pydantic provides automatic request validation and schema documentation
- Async support is built-in, suitable for I/O-bound Supabase calls
- OpenAPI docs are auto-generated at `/docs` and `/redoc`
- Python is a better fit for future FreeCAD Docker integration (FreeCAD scripting is Python-based)

### 3. Vue 3 Composition API

The frontend uses Vue 3 with `<script setup>` syntax and the Composition API exclusively. This was chosen over the Options API for better TypeScript integration, more flexible code organization, and simpler reactive state management with `ref()` and `computed()`.

### 4. Desktop-First UI

The interface is designed for desktop and large tablet use. It is not mobile-first. This reflects the actual usage pattern: engineers at workstations viewing drawings, BOMs, and part data.

### 5. Upload Bridge Pattern

The `scripts/pdm-upload/` PowerShell scripts serve as a bridge between the local CAD/file system and the web backend. Rather than building a full desktop client, this lightweight approach watches local folders and pushes data to the FastAPI API. This preserves the core workflow from the legacy system (drop files in a folder, they get processed) while the data lands in the cloud.

---

## Common Pitfalls

### 1. Supabase RLS Requires Admin Client for Internal Services

**Problem:** The Supabase anon client respects Row Level Security policies. Internal operations like bulk BOM upload or file upload from the upload bridge service fail silently or with permission errors when using the anon client.

**Solution:** The backend maintains two Supabase clients:

```python
# backend/app/services/supabase.py

@lru_cache
def get_supabase_client() -> Client:
    """Anon key -- for user-level operations respecting RLS."""
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_anon_key)

@lru_cache
def get_supabase_admin() -> Client:
    """Service key -- bypasses RLS for trusted internal operations."""
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_key)
```

**Rule:** Use `get_supabase_admin()` only in endpoints called by trusted internal services (file upload, bulk BOM upload). Use `get_supabase_client()` for all user-facing endpoints.

### 2. Item Number Normalization

**Problem:** Item numbers must be lowercase everywhere. Inconsistent casing causes duplicate items, failed lookups, and broken BOM relationships.

**Solution:** Normalize to lowercase at every entry point:

- FastAPI routes: `item_number.lower()` in every handler
- Pydantic schema: regex pattern `^[a-z]{3}\d{4,6}$` on `ItemBase`
- Upload bridge: PowerShell normalizes before API calls
- Frontend: case-insensitive search with `.toLowerCase()`

**Pattern in route handlers:**

```python
normalized_number = item_number.lower()
result = supabase.table("items").select("*").eq("item_number", normalized_number).execute()
```

### 3. File Path Handling in Supabase Storage

**Problem:** Supabase Storage uses bucket-relative paths for operations but the database stores the full path including bucket name. Mixing these up causes "file not found" errors.

**Solution:** The convention is:

- **Storage operations** use the path within the bucket: `{item_number}/{filename}`
- **Database `file_path` column** stores the full path: `pdm-files/{item_number}/{filename}`
- **Signed URLs** are generated from the bucket-relative path

```python
bucket = "pdm-files"
path_in_bucket = f"{item_number}/{file.filename}"
storage_path = f"{bucket}/{path_in_bucket}"  # Stored in DB

# Upload uses bucket-relative path
supabase.storage.from_(bucket).upload(path_in_bucket, content)

# Signed URL uses bucket-relative path
supabase.storage.from_(bucket).create_signed_url(path_in_bucket, 3600)
```

### 4. Duplicate Key Handling in Upserts

**Problem:** Supabase does not have a native upsert that works cleanly with the Python client in all cases. The `update()` call returns empty data if the row does not exist, and `insert()` throws on duplicate keys.

**Solution:** The items PATCH endpoint implements a try-update-then-insert pattern:

```python
# Try update first
result = supabase.table("items").update(update_data).eq("item_number", normalized_number).execute()

if result.data:
    return result.data[0]

# Item doesn't exist -- create if upsert mode
if upsert:
    try:
        create_result = supabase.table("items").insert(new_item).execute()
        return create_result.data[0]
    except Exception as e:
        if "duplicate key" in str(e).lower() or "23505" in str(e):
            # Race condition -- retry update
            retry_result = supabase.table("items").update(update_data).eq("item_number", normalized_number).execute()
            ...
```

This handles the race condition where another process creates the item between the failed update and the insert attempt.

### 5. Supabase `single()` vs `limit(1)`

**Problem:** Calling `.single().execute()` throws an exception if zero rows are returned. This causes 500 errors for legitimate "not found" cases.

**Solution:** Use `.limit(1).execute()` and check `len(result.data)` when a missing row is expected (such as upload endpoints checking if an item exists). Use `.single()` only when you want a hard 404 on missing data.

```python
# Safe -- returns empty list if not found
result = supabase.table("items").select("id").eq("item_number", item_number).limit(1).execute()
if not result.data or len(result.data) == 0:
    raise HTTPException(status_code=404, detail="Item not found")

# Throws exception if not found -- use only when 404 is the correct behavior
result = supabase.table("items").select("*").eq("item_number", item_number).single().execute()
```

### 6. UUID Serialization

**Problem:** Pydantic UUID fields do not serialize directly to strings for Supabase queries. Passing a UUID object to `.eq()` fails silently.

**Solution:** Always convert UUIDs to strings before passing to Supabase:

```python
if item_data.get("project_id"):
    item_data["project_id"] = str(item_data["project_id"])
```

### 7. Wrong Port in workspace.html (404 Errors)

**Symptom:** All API calls from workspace.html returned 404. The browser console showed requests going to `localhost:8001`.

**Root Cause:** The `PDM_CONFIG` in `workspace.html` had `apiUrl: 'http://localhost:8001'` but the FastAPI backend runs on port 8001 (configured in `backend/.env` as `API_PORT=8001`).

**Diagnosis:** Checked browser Network tab -- requests were hitting port 8000 which had nothing listening. Compared against `backend/.env` and found the port mismatch.

**Fix:** Updated `workspace.html` to use `apiUrl: 'http://localhost:8001'`.

**Prevention:** Always check `backend/.env` for the actual `API_PORT` value before hardcoding URLs. Use a config object (`PDM_CONFIG`) so the port only needs to be changed in one place.

### 8. All Items Show "Not In Vault" (RLS Blocking Reads)

**Symptom:** The workspace comparison endpoint returned every file as "Not In Vault" even though items existed in Supabase.

**Root Cause:** The `get_supabase_client()` function uses the anon key, which is subject to Row Level Security. Unauthenticated requests (no JWT) were blocked by RLS policies on the `items` and `files` tables, returning empty result sets.

**Diagnosis:** Tested the same query in the Supabase SQL editor (which bypasses RLS) and got results. Tested with the admin client in a Python shell and got results. Confirmed that the workspace endpoint was using `get_supabase_client()` (anon key) instead of `get_supabase_admin()`.

**Fix:** Changed `workspace.py` to use `get_supabase_admin()` for all queries. This is appropriate because the workspace comparison is an internal service endpoint, not a user-facing browser operation.

**Prevention:** Any endpoint that runs without a user JWT must use `get_supabase_admin()`. Add a comment in the route file explaining why the admin client is used.

### 9. Windows strftime Crash (`%-m` Format Code)

**Symptom:** The workspace comparison endpoint crashed with `ValueError: Invalid format string` on Windows.

**Root Cause:** The `format_vault_time()` function used `%-m` (month without leading zero), which is a Linux/macOS-only strftime directive. On Windows, Python's strftime raises `ValueError` for this format.

**Diagnosis:** Stack trace pointed directly at the `strftime("%-m/%-d/%Y")` call. Confirmed this is a known Windows/Linux difference in Python's strftime implementation.

**Fix:** Replaced strftime with manual f-string formatting:
```python
f"{dt.month}/{dt.day}/{dt.year}, {hour}:{dt.minute:02d}:{dt.second:02d} {ampm}"
```

**Prevention:** Never use `%-` strftime directives in Python code that must run on Windows. Use f-string formatting with `dt.month`, `dt.day`, etc. instead, or use platform checks.

### 10. files.updated_at Column Missing

**Symptom:** The workspace comparison endpoint crashed with a Supabase error: column `updated_at` does not exist on the `files` table.

**Root Cause:** The `files` table only had `created_at`. The workspace comparison logic needed `updated_at` to determine when a file was last modified in the vault.

**Diagnosis:** Checked the Supabase table definition and confirmed `updated_at` was missing from `files`. Other tables (items, users, projects) had it, but files did not.

**Fix:** Applied migration `add_updated_at_to_files`:
```sql
ALTER TABLE files ADD COLUMN updated_at TIMESTAMPTZ DEFAULT now();
UPDATE files SET updated_at = created_at WHERE updated_at IS NULL;
CREATE OR REPLACE FUNCTION update_files_updated_at()
RETURNS TRIGGER AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$ LANGUAGE plpgsql;
CREATE TRIGGER files_updated_at_trigger BEFORE UPDATE ON files
FOR EACH ROW EXECUTE FUNCTION update_files_updated_at();
```

**Prevention:** When designing a table that will be queried for "last modified" time, always include an `updated_at` column with an auto-update trigger from the start.

### 11. UTC vs Local Timezone Mismatch

**Symptom:** Files checked in today showed "Out of Date" immediately after upload. The vault timestamp showed a time 6 hours ahead of the local file timestamp.

**Root Cause:** Supabase stores timestamps in UTC. PowerShell `Get-Item` returns `LastWriteTime` in the local timezone (CST = UTC-6). Direct comparison of UTC vault time against local file time always showed the vault as "newer" or the times as mismatched.

**Diagnosis:** Printed both timestamps side by side. A file modified at 2:00 PM CST was stored as 8:00 PM UTC in the vault. The comparison logic was comparing raw datetime values without timezone conversion.

**Fix:** Added timezone conversion in the Python backend using `dt.astimezone()`:
```python
def parse_vault_timestamp(ts_string):
    dt = datetime.fromisoformat(ts_string.replace('Z', '+00:00'))
    local_dt = dt.astimezone()  # Convert UTC to local timezone
    return local_dt
```

**Prevention:** Always convert vault (UTC) timestamps to local time before comparing with local file timestamps. Use `astimezone()` without arguments to convert to the server's local timezone.

### 12. Item Number Regex Ordering (McMaster Truncation)

**Symptom:** McMaster part numbers like `mmc12555k88` were being truncated to `mmc12555`. The item was created with the wrong number, and BOM lookups failed.

**Root Cause:** The item number extraction used regex patterns in this order: standard pattern `[a-z]{3}\d{4,6}` first, then `mmc\d+[a-z]*\d*`. The standard pattern matched `mmc12555` (3 letters + 5 digits) before the McMaster-specific pattern could match the full `mmc12555k88`.

**Diagnosis:** Added logging to show which regex pattern matched. Saw that `mmc12555k88` was matching the standard pattern as `mmc12555` instead of the McMaster pattern as `mmc12555k88`.

**Fix:** Reordered the regex checks in both Python (`workspace.py`, `files.py`) and PowerShell (`PDM-Local-Service.ps1`) to check `mmc`, `spn`, and `zzz` patterns **before** the standard `[a-z]{3}\d{4,6}` pattern:
```python
# Check special prefixes FIRST (they have different formats)
if filename_lower.startswith('mmc'):
    match = re.match(r'^(mmc\d+[a-z]*\d*)', filename_lower)
elif filename_lower.startswith('spn'):
    match = re.match(r'^(spn\d+[a-z]*\d*)', filename_lower)
elif filename_lower.startswith('zzz'):
    match = re.match(r'^(zzz\d+[a-z]*\d*)', filename_lower)
else:
    match = re.match(r'^([a-z]{3}\d{4,6})', filename_lower)
```

**Prevention:** Always check specific/longer patterns before general/shorter patterns. McMaster (`mmc`), supplier (`spn`), and reference (`zzz`) prefixes allow alphanumeric suffixes that the standard pattern does not expect.

### 13. Post-Upload Timestamps Don't Match (File Touch)

**Symptom:** After a successful check-in/upload, the workspace comparison immediately showed the file as "Out of Date" even though it was just uploaded.

**Root Cause:** The local file's `LastWriteTime` was set to when it was last saved by Creo (e.g., 1:30 PM). The upload to Supabase Storage recorded `updated_at` as `now()` (e.g., 1:45 PM). Since the vault timestamp was newer than the local file's LastWriteTime, the comparison flagged it as out of date.

**Diagnosis:** Compared the local `LastWriteTime` with the vault `updated_at` after upload. The vault time was always a few minutes ahead because `now()` was called at upload time, while the file's write time was frozen at last-save time.

**Fix:** Added a file "touch" operation in `PDM-Local-Service.ps1` after successful upload:
```powershell
# After successful upload, update local file's LastWriteTime
$file = Get-Item $filePath
$file.LastWriteTime = Get-Date
```

**Prevention:** After uploading a file, always update the local file's `LastWriteTime` to the current time so it stays in sync with the vault's `updated_at` timestamp.

### 14. CreoJS Workspace Mixed Content (HTTPS → HTTP Blocked)

**Symptom:** After workspace.html was deployed to the production domain (`https://pdm-web.fly.dev`), the workspace comparison feature failed to load local file timestamps. Browser console showed "Mixed Content" errors when trying to fetch from `http://localhost:8083`.

**Root Cause:** Browsers enforce mixed content security: HTTPS pages cannot make HTTP requests, even to localhost. When workspace.html moved from local development to being served from the production HTTPS domain, all calls to the local PDM-Local-Service (HTTP) were blocked by the browser.

**Diagnosis:**
1. Opened browser developer console and saw "Mixed Content: The page at 'https://pdm-web.fly.dev/...' was loaded over HTTPS, but requested an insecure XMLHttpRequest endpoint 'http://localhost:8083/api/file-timestamps'. This request has been blocked."
2. Confirmed the security rule: HTTPS→HTTP is blocked, but HTTP→HTTPS is allowed.

**Fix:** Changed the serving model to keep all workspace operations in HTTP:

1. **PDM-Local-Service now serves static files** from `creowebjs_apps/` directory:
   - Added `Handle-StaticFile` function to serve `.html`, `.js`, `.css`, `.svg` files
   - Mapped `GET /workspace.html` (and other static files) to the file handler
   - Set `$Global:WebAppsDir` to point to `creowebjs_apps/` directory
   - Changed `$Global:ApiUrl` to point to production (`https://pdm-web.fly.dev/api`)

2. **Workspace.html auto-detects its origin**:
```javascript
const _isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
const PDM_CONFIG = {
    apiUrl: _isLocal ? 'https://pdm-web.fly.dev' : window.location.origin,
    localServiceUrl: _isLocal ? window.location.origin : 'http://localhost:8083',
    frontendUrl: _isLocal ? 'https://pdm-web.fly.dev' : window.location.origin
};
```
When served from localhost (the expected case), `localServiceUrl` uses same origin (localhost:8083) and `apiUrl` points to fly.dev. This keeps all local service calls as HTTP→HTTP and cloud API calls as HTTP→HTTPS (allowed).

3. **Backend CORS config** added `http://localhost:8083` to allowed origins in `backend/app/config.py`:
```python
cors_origins: list[str] = [
    "http://localhost:5174",
    "http://localhost:3000",
    "http://localhost:8083",        # PDM-Local-Service (CreoJS workspace)
    "http://100.106.248.91:5174",   # Tailnet
]
```

4. **Creo browser now points to** `http://localhost:8083/workspace.html` instead of the production HTTPS URL. All HTTP, so no mixed content issues. API calls to fly.dev work fine (HTTP→HTTPS is allowed, only HTTPS→HTTP is blocked).

**Files Changed:**
- `Local_Creo_Files/Powershell/PDM-Local-Service.ps1` -- Added static file serving, changed API URL to fly.dev
- `Local_Creo_Files/creowebjs_apps/workspace.html` -- Added config auto-detection
- `backend/app/config.py` -- Added `http://localhost:8083` to CORS origins

**Prevention:** Always serve workspace.html from the local PDM-Local-Service (HTTP) to avoid mixed content issues. The service acts as a bridge between local file operations and the cloud API.

### 15. Upload Service Production API Switch

**Symptom:** Upload service was failing with "Unable to connect to the remote server" errors every time a file was dropped into the watch folder.

**Root Cause:** `PDM-Upload-Config.ps1` had `ApiUrl = "http://localhost:8001/api"` but the developer's local FastAPI backend wasn't running during normal CAD work. The upload service tried to connect to localhost and failed.

**Fix:** Changed the default `ApiUrl` in `PDM-Upload-Config.ps1` from `http://localhost:8001/api` to `https://pdm-web.fly.dev/api`:
```powershell
$Config = @{
    # Local development:
    # ApiUrl = "http://localhost:8001/api"
    # Production:
    ApiUrl = "https://pdm-web.fly.dev/api"
    # ...
}
```

**Trade-off:** Upload service now depends on internet connectivity and production API availability. For offline development or when testing API changes, switch `ApiUrl` back to localhost and run the backend locally.

**Files Changed:** `scripts/pdm-upload/PDM-Upload-Config.ps1`

**Prevention:** Consider the user's typical workflow. If they don't run the backend locally most of the time, default to the production API URL.

### 16. Duplicate Filename Handling (param_1.txt, bom_2.txt)

**Symptom:** When multiple files were dropped into the watch folder in rapid succession (e.g., Creo exporting param.txt, BOM.txt, and a STEP file), Windows added `_1`, `_2` suffixes to duplicate filenames before the service could process them. These numbered files (e.g., `param_1.txt`, `bom_2.txt`) were silently skipped as "unsupported file type".

**Root Cause:** `Get-FileAction` in `PDM-Upload-Functions.ps1` used exact string matching to identify special files:
```powershell
if ($fileName -eq 'param.txt')  { return 'Parameters' }
if ($fileName -eq 'bom.txt')    { return 'BOM' }
if ($fileName -eq 'mlbom.txt')  { return 'MLBOM' }
```
When Windows renamed the file to `param_1.txt`, it no longer matched the exact string.

**Diagnosis:** Checked the log file and saw:
```
2026-02-01 10:30:45 Processing: param_1.txt
2026-02-01 10:30:45 Skipping unsupported file: param_1.txt
```
Opened `param_1.txt` and confirmed it was a valid Creo parameter export with correct format.

**Fix:** Changed exact matching to regex patterns that accept the `_\d+` suffix:
```powershell
# Check for specific text file names (BOM/param files)
# Also handle _1, _2, etc. suffixes from duplicate drops (e.g. param_1.txt, bom_2.txt)
if ($fileName -match '^param(_\d+)?\.txt$')  { return 'Parameters' }
if ($fileName -match '^bom(_\d+)?\.txt$')    { return 'BOM' }
if ($fileName -match '^mlbom(_\d+)?\.txt$')  { return 'MLBOM' }
```

**Files Changed:** `scripts/pdm-upload/PDM-Upload-Functions.ps1`

**Prevention:** Use regex patterns for filename matching when Windows may add suffixes or users may rename files with variations. The pattern `^param(_\d+)?\.txt$` matches `param.txt`, `param_1.txt`, `param_2.txt`, etc.

### 17. Auto-Sync Upload Scripts on Service Launch

**Symptom:** After making changes to the upload scripts in the project source directory (`J:\PDM-Web\scripts\pdm-upload\`), the deployed service at `C:\PDM-Upload\` continued to run old code. The developer had to manually copy the updated scripts to `C:\PDM-Upload\` every time.

**Root Cause:** The upload service runs from `C:\PDM-Upload\` with copies of the .ps1 files. Code changes in the project directory didn't automatically propagate to the deployed location.

**Fix:** Modified `Start-PDMUpload.bat` to auto-sync scripts before starting the service:
```batch
REM Sync scripts from project source before starting
set "SOURCE=J:\PDM-Web\scripts\pdm-upload"
if exist "%SOURCE%\PDM-Upload-Service.ps1" (
    echo Syncing scripts from %SOURCE% ...
    copy /Y "%SOURCE%\PDM-Upload-Config.ps1"    "C:\PDM-Upload\" >nul
    copy /Y "%SOURCE%\PDM-Upload-Functions.ps1"  "C:\PDM-Upload\" >nul
    copy /Y "%SOURCE%\PDM-Upload-Service.ps1"    "C:\PDM-Upload\" >nul
    copy /Y "%SOURCE%\PDM-BOM-Parser.ps1"        "C:\PDM-Upload\" >nul
    echo Scripts synced.
) else (
    echo WARNING: Project source not found at %SOURCE%, using local copies.
)
```

**Files Changed:** `scripts/pdm-upload/Start-PDMUpload.bat`

**Benefits:**
- Developers get the latest script changes automatically on service restart
- No manual copy steps required
- Still works if the project drive is unavailable (falls back to local copies with a warning)
- Single batch file to launch ensures scripts are always in sync

**Prevention:** For deployed services that run from copied scripts, add auto-sync to the launcher so code changes propagate automatically.

### 18. PRICE_EST Removed from Creo Upload Pipeline

**Symptom:** Cost estimates calculated by the MRP pricing engine were being overwritten with stale Creo parameter values every time a BOM or parameter file was uploaded.

**Root Cause:** `PDM-BOM-Parser.ps1` included `PRICE_EST` in the `$script:ColumnMap`, so Creo BOM exports and parameter updates overwrote the `price_est` column in the database:
```powershell
$script:ColumnMap = @(
    @{ header = 'DESCRIPTION';         field = 'name';       type = 'string' }
    @{ header = 'PRO_MP_MASS';         field = 'mass';       type = 'number' }
    # ...
    @{ header = 'PRICE_EST';           field = 'price_est';  type = 'number' }  # <-- Problem
)
```

**Diagnosis:** Checked the Creo parameter exports and saw that `PRICE_EST` values were weeks old (from the last time a cost was manually entered in Creo). After uploading a BOM, the database `price_est` column was overwritten with these stale values instead of the live calculated estimates from the MRP pricing engine.

**Fix:** Removed `PRICE_EST` from `$script:ColumnMap` in `PDM-BOM-Parser.ps1`:
```powershell
$script:ColumnMap = @(
    @{ header = 'DESCRIPTION';         field = 'name';       type = 'string' }
    @{ header = 'PRO_MP_MASS';         field = 'mass';       type = 'number' }
    @{ header = 'SMT_THICKNESS';       field = 'thickness';  type = 'number' }
    @{ header = 'PTC_MASTER_MATERIAL'; field = 'material';   type = 'string' }
    @{ header = 'CUT_LENGTH';          field = 'cut_length'; type = 'number' }
    @{ header = 'CUT_TIME';            field = 'cut_time';   type = 'number' }
    # PRICE_EST removed - MRP pricing engine calculates cost estimates now
)
```

The `PRICE_EST` column can still exist in Creo exports. The parser just ignores it.

**Design Principle:** The MRP pricing engine is the single source of truth for cost estimates. CAD metadata (Creo parameters) should not overwrite calculated pricing data. Cost estimates are derived from:
- Material pricing ($/lb per alloy)
- Labor rates ($/hr per operation type)
- Overhead and markup percentages
- Real-time workstation rates

These are managed in the MRP UI and should not be overridden by static Creo parameters.

**Files Changed:** `scripts/pdm-upload/PDM-BOM-Parser.ps1`

**Prevention:** Separate calculated/derived fields (like cost estimates) from source-of-truth fields (like mass, thickness, material). Only allow the authoritative system to write calculated values.

---

### 19. PDF Upload Date Stamping Position

**Symptom:** PDF upload date stamps were overlapping with drawing title blocks in the lower-right corner, obscuring critical information like revision letters and approval signatures.

**Root Cause:** The initial PDF stamping implementation placed the date stamp in the lower-right corner with a 0.5" margin. Many engineering drawing templates have title blocks in this exact location, causing the stamp to cover drawing metadata.

**Diagnosis:** Reviewed uploaded PDFs and found the white background box of the date stamp was blocking revision numbers, engineer names, and approval dates in the title block. The stamp was also too small (8pt font) to be easily visible without zooming.

**Fix:** Repositioned the stamp to the lower-left corner and increased font size:

**Before:**
```python
# Position: lower right corner with margin
margin = 36  # 0.5 inch margin
text_width = c.stringWidth(stamp_text, "Helvetica", 8)
x = page_width - text_width - margin
y = margin

# Draw white background rectangle for readability
c.setFillColorRGB(1, 1, 1)
c.setStrokeColorRGB(0.5, 0.5, 0.5)
padding = 4
c.rect(x - padding, y - padding, text_width + padding * 2, 12 + padding, fill=1, stroke=1)

# Draw text
c.setFillColorRGB(0, 0, 0)
c.setFont("Helvetica", 8)
c.drawString(x, y, stamp_text)
```

**After:**
```python
# Position: lower left, past corner mark
x = 82  # ~1.1 inch from left edge (past corner marks)
y = 8   # Just below the margin line

# Draw text only (no box)
c.setFillColorRGB(0, 0, 0)
c.setFont("Helvetica", 12)  # Larger font for visibility
c.drawString(x, y, stamp_text)
```

**Changes Made:**
1. **Position moved from lower-right to lower-left** - Engineering drawings typically have corner marks and borders but leave the lower-left area clear
2. **X position: 82pt (~1.1")** - Past the corner mark zone but still in the margin
3. **Y position: 8pt** - Just above the bottom edge, below the margin line
4. **Font size: 8pt → 12pt** - More readable without zooming
5. **Removed white background box** - Cleaner appearance, less visual clutter, doesn't obscure underlying drawing lines

**Benefits:**
- Date stamp no longer obscures title block information
- Larger font is easier to read when printed or viewed at normal zoom
- Cleaner appearance without background box
- Still visible and unambiguous as an upload stamp

**Files Changed:** `backend/app/routes/files.py` (lines 65-75)

**Prevention:** When adding annotations or stamps to engineering drawings, avoid the lower-right corner (title block zone) and use the lower-left or upper areas. Test with actual drawing PDFs that have full title blocks, not blank test files.

---

### 20. Routing Editor State Reset and Purchase Info Save Issues

**Symptom 1:** When selecting a new item in the routing editor, the UI sometimes showed stale data from the previously selected item (old operations, old materials, old purchase info).

**Symptom 2:** After editing purchased part information (supplier name, part number, unit price) and switching to a different tab, the save operation would hang indefinitely. The loading spinner would keep spinning and the data never saved.

**Root Cause 1:** The routing editor did not fully reset state when `selectedItem` changed. Some computed properties and reactive refs retained old values across item switches.

**Root Cause 2:** When the user switched tabs while a save operation was in progress, the browser aborted the fetch request (throwing an `AbortError`). The save function did not catch this error type, so it threw an unhandled exception, leaving the UI in a loading state forever.

**Diagnosis:**
1. Checked the console and saw `AbortError: The user aborted a request` when switching tabs during save
2. Confirmed the save endpoint was working correctly when called without tab switching
3. Reviewed the `savePurchaseInfo()` function and found no error handling for `AbortError`
4. Traced state reset issues to missing `nextTick()` or `watch()` on `selectedItem` changes

**Fix (State Reset):**
Added explicit state reset when `selectedItem` changes:
```javascript
watch(() => selectedItem.value, (newItem) => {
  if (newItem) {
    // Reset all state
    operations.value = []
    assignedMaterials.value = []
    purchaseInfo.value = { ... }

    // Fetch fresh data
    fetchOperations()
    fetchMaterials()
    fetchPurchaseInfo()
  }
})
```

**Fix (AbortError Retry):**
Added error handling with retry logic in `savePurchaseInfo()`:
```javascript
async function savePurchaseInfo() {
  try {
    const response = await supabase.from('items').update({
      supplier_name: purchaseInfo.value.supplier_name,
      supplier_part_number: purchaseInfo.value.supplier_part_number,
      unit_price: purchaseInfo.value.unit_price
    }).eq('id', selectedItem.value.id)

    if (response.error) throw response.error

  } catch (err) {
    // If tab switch aborted the request, retry once
    if (err.name === 'AbortError') {
      console.log('Save aborted (tab switch), retrying...')
      await new Promise(resolve => setTimeout(resolve, 100))  // Brief delay
      return savePurchaseInfo()  // Retry
    }
    throw err  // Re-throw other errors
  }
}
```

**Files Changed:**
- `frontend/src/views/MrpRoutingView.vue` - Added state reset on item change, AbortError retry logic

**Prevention:**
- Always reset reactive state when the selected entity changes (use `watch()` with cleanup)
- Handle `AbortError` in any fetch/save operations that can be interrupted by user navigation
- Add retry logic for operations that are safe to retry (idempotent saves)
- Use loading spinners with timeout safeguards to prevent infinite loading states

---

### 21. Filename and Item Number Normalization (Suffix Stripping)

**Symptom:** Uploaded files had redundant suffixes like `abc0001_dxf.dxf` or `xxp123_prt.prt`. Item numbers extracted from filenames included Creo type suffixes like `abc0001_prt`, causing database mismatches.

**Root Cause:** Creo exports often append type indicators to filenames:
- `partname_prt.prt` (part file)
- `assemblyname_asm.asm` (assembly file)
- `drawingname_drw.drw` (drawing file)
- `partname_dxf.dxf` (DXF export)

When these files were uploaded without normalization:
1. Database stored paths like `pdm-files/abc0001_prt/abc0001_prt.prt`
2. Item numbers were extracted as `abc0001_prt` instead of `abc0001`
3. Queries for `abc0001` failed to find files stored under `abc0001_prt`
4. File list showed ugly redundant names

**Diagnosis:** Reviewed uploaded file paths in Supabase Storage and saw the pattern. Checked the `PDM-Upload-Functions.ps1` item number extraction and confirmed it did not strip suffixes before regex matching.

**Fix (Part 1 - Backend):** Added filename normalization in `POST /api/files/upload`:
```python
# backend/app/routes/files.py

# Normalize filename
filename = file.filename.lower()

# Strip redundant suffixes: abc0001_dxf.dxf → abc0001.dxf
filename = re.sub(r'_(dxf|prt|asm|drw)\.(dxf|prt|asm|drw|step|stp)$', r'.\2', filename)

# Convert .stp → .step (canonical extension)
filename = re.sub(r'\.stp$', '.step', filename)

# Strip type suffixes: abc0001_prt.prt → abc0001.prt
filename = re.sub(r'_(prt|asm|drw)\.', '.', filename)
```

**Fix (Part 2 - Upload Script):** Added suffix stripping in `PDM-Upload-Functions.ps1`:
```powershell
# Strip Creo type suffixes before item number detection
$baseName = $file.BaseName -replace '_prt$|_asm$|_drw$', ''

# Now extract item number from cleaned basename
$itemNumber = Extract-ItemNumber -BaseName $baseName
```

**Examples:**
- `abc0001_prt.prt` → `abc0001.prt` (filename), `abc0001` (item number)
- `xxp123_dxf.dxf` → `xxp123.dxf` (filename), `xxp123` (item number)
- `part.stp` → `part.step` (filename)
- `CSP0030_PRT.PRT` → `csp0030.prt` (filename), `csp0030` (item number)

**Why This Matters:**
- Cleaner file paths in Supabase Storage
- Item numbers match database records
- File queries don't fail due to suffix mismatches
- Consistent lowercase naming for case-sensitive systems
- Users see clean filenames in the UI

**Files Changed:**
- `backend/app/routes/files.py` -- filename normalization before storage
- `scripts/pdm-upload/PDM-Upload-Functions.ps1` -- suffix stripping before item number extraction

**Prevention:** Always normalize user-provided filenames at the entry point (upload handler). Don't trust client-side naming conventions. Apply transformations server-side before storage.

---

### 22. Files Table `storage_path` Column Does Not Exist

**Symptom:** Frontend queries to the `files` table failed with errors like `column "storage_path" does not exist` when trying to load PDFs or other files.

**Root Cause:** The `files` table schema uses `file_path` to store the full storage path including bucket prefix (e.g., `pdm-drawings/csp0030/A/1/csp0030.pdf`). There is no separate `storage_path` column. Some frontend code was querying for `storage_path` expecting it to be a distinct column.

**Diagnosis:**
1. Frontend tried to select `storage_path` from `files` table
2. Supabase returned error: `column "storage_path" does not exist`
3. Inspected database schema and confirmed only `file_path` column exists
4. Reviewed storage helper functions and found they parse bucket from `file_path`

**Fix:**
Changed all queries to select `file_path` instead of `storage_path`:
```typescript
// WRONG
const { data: files } = await supabase
  .from('files')
  .select('id, item_id, file_type, storage_path')  // Column doesn't exist!

// CORRECT
const { data: files } = await supabase
  .from('files')
  .select('id, item_id, file_type, file_path')  // Use file_path
```

Then use `getSignedUrlFromPath(file.file_path)` to parse bucket and generate signed URL.

**Files Changed:**
- `frontend/src/views/MrpPartLookupView.vue` - Changed query to use `file_path`
- Any other views querying `files` table

**Prevention:**
- Always check database schema before writing queries
- Use wildcard `select('*')` during development to see all available columns
- Document column names clearly in schema documentation
- Use TypeScript interfaces that match actual database schema

---

### 23. Creo Mapkey FAV_ Favorites Not Portable

**Symptom:** Creo mapkeys using `FAV_9_`, `FAV_10_`, and `FAV_14_` favorites failed when favorites were not configured or configured differently on different workstations.

**Root Cause:** Creo favorites (FAV_*) are user-specific and machine-specific. Mapkeys that reference favorites break when moved to a new workstation or when the user's favorites change. The mapkeys were relying on:
- `FAV_9_` pointing to `C:\PTC_Data\formats` (for drawing sheet formats)
- `FAV_10_` and `FAV_14_` pointing to `C:\PDM-Upload` (for file exports)

**Diagnosis:**
1. Tested mapkeys on fresh Creo installation without favorites configured
2. Mapkeys executed but saved files to working directory instead of target folder
3. Recorded manual navigation mapkey to understand correct command sequence
4. Discovered double-action pattern: must Select AND Activate each folder level

**Fix:**
Replaced all FAV_ favorite references with hard-coded folder navigation using `computer_pb` button and double-action Select/Activate:

```
// OLD (broken on new machines)
~ Activate `file_saveas` `pb_favorites__FAV_10_`;

// NEW (portable)
~ Activate `file_saveas` `computer_pb`;\
~ Select `file_saveas` `ph_list.Filelist` 1 `c:`;\
~ Activate `file_saveas` `ph_list.Filelist` 1 `c:`;\
~ Select `file_saveas` `ph_list.Filelist` 1 `PDM-Upload`;\
~ Activate `file_saveas` `ph_list.Filelist` 1 `PDM-Upload`;\
```

**Key Pattern:** Must use both `Select` AND `Activate` to "enter" each folder (mimics double-clicking).

**Mapkeys Modified:** 12 total
- Export mapkeys: `cipdf`, `expdf`, `exofa`, `exofp`, `exsta`
- Format mapkeys: `dfwmba`, `dfwmbp`, `dfwmap`, `dfamfap`, `dfamfbp`, `dfamfba`, `apsf`

**Documentation:** Created `MAPKEY_CHANGES.md` at project root with full details of all changes.

**Files Changed:**
- `config_FIXED.pro` - Updated mapkey definitions
- `MAPKEY_CHANGES.md` (NEW) - Full documentation of changes

**Prevention:**
- Never rely on Creo favorites in mapkeys intended for shared use
- Use hard-coded paths with `computer_pb` + double-action navigation
- Test mapkeys on fresh Creo installation without favorites configured
- Document mapkey changes in dedicated reference files
- Use exact folder names as they appear in Windows Explorer (case-sensitive)

### 34. Print Packet Routing Stamp Covering Drawing Content

**Symptom:** Routing stamp overlay on print packet PDFs was obscuring important drawing content. The white background box covered drawing lines, dimensions, and notes underneath the stamp.

**Root Cause:** The stamp box in `_create_stamp()` function used `fill=1` (solid white background) to ensure text readability. While this made the routing text legible, it created an opaque rectangle that blocked all underlying drawing content.

**Diagnosis:**
1. Generated print packet PDFs and reviewed routing stamp placement
2. Observed that stamp position was good (right edge, vertically centered)
3. Noticed that complex drawings with dense detail had important content hidden behind the stamp
4. Drawing lines, dimensions, and notes fell behind the white rectangle
5. Stamp served its purpose (showing routing) but at the cost of hiding drawing information

**Fix:** Changed stamp from opaque to transparent:

**Before:**
```python
# Draw stamp box with white background
c.setStrokeColorRGB(0, 0, 0)  # Black border
c.setLineWidth(1)
c.rect(x, y, stamp_width, stamp_height, fill=1, stroke=1)  # fill=1 = white background
```

**After:**
```python
# Draw stamp box - transparent background so drawing shows through
c.setStrokeColorRGB(0.3, 0.3, 0.3)  # Dark gray border
c.setLineWidth(0.5)
c.rect(x, y, stamp_width, stamp_height, fill=0, stroke=1)  # fill=0 = transparent
```

**Changes Made:**
1. **Background fill removed:** Changed `fill=1` to `fill=0` (transparent background)
2. **Border color softened:** Changed stroke from black `(0, 0, 0)` to dark gray `(0.3, 0.3, 0.3)` for less visual weight
3. **Border width reduced:** Changed line width from 1pt to 0.5pt for thinner, less intrusive border
4. **Text remains black:** Routing text stays black for maximum contrast and readability

**Benefits:**
- Drawing content is now visible through the stamp area
- Routing information remains readable (black text on white PDF background)
- Lighter gray border is less visually distracting
- No loss of functionality - all routing data still shown clearly

**Trade-off Accepted:**
- If the drawing has dark/dense content in the stamp area, text may be slightly harder to read
- This is acceptable because drawing content takes priority
- The stamp position (right edge, centered) is chosen to avoid title blocks and critical areas
- Most engineering drawings have white space on the right edge

**Files Changed:** `backend/app/services/print_packet.py` (`_create_stamp()` function, lines 1149-1152)

**Prevention:** When adding overlay annotations to PDFs:
- Default to transparent backgrounds to avoid obscuring content
- Use light borders (gray, thin) instead of heavy borders (black, thick)
- Position overlays in areas with expected white space (edges, margins)
- Test with real-world PDFs that have dense drawing content, not blank test files
- Consider that engineering drawings prioritize technical content over annotations

**Commit:** b1f3d21

---

### 35. MRP Dashboard N+1 Query Pattern (Batching Fix)

**Symptom:** The MRP dashboard sidebar took several seconds to load when opening projects with many parts (e.g., 59 parts). The browser hung briefly with the loading spinner, and Supabase logs showed 100+ concurrent queries.

**Root Cause:** Classic N+1 query problem. The `loadProjectParts()` function in `MrpDashboardView.vue` processed each part individually in an `async` loop:

```javascript
// OLD CODE (N+1 pattern)
for (const part of parts) {
  // Query 1: Fetch routing for this part
  const { data: routing } = await supabase
    .from('routing')
    .select('*')
    .eq('item_id', part.id)

  // Query 2: Check if part has BOM children
  const { data: children } = await supabase
    .from('bom')
    .select('id')
    .eq('parent_item_id', part.id)
    .limit(1)

  part.hasRouting = routing?.length > 0
  part.hasChildren = children?.length > 0
}
```

For 59 parts, this meant:
- 59 queries for routing data
- 59 queries for BOM checks
- **Total: 118 concurrent queries**

The queries were fired simultaneously (because the loop was async), overwhelming the connection pool and causing the UI to hang.

**Diagnosis:**
1. Opened browser DevTools Network tab and saw 118+ requests to Supabase within 1-2 seconds
2. Each request was tiny (single item lookup) but the volume was the problem
3. Realized the pattern: loop over parts, query per part (classic N+1)
4. Checked Supabase query logs and confirmed the pattern

**Fix:** Changed from per-item queries to batched queries with in-memory lookup:

```javascript
// NEW CODE (batched queries)

// Step 1: Collect all item IDs upfront
const itemIds = parts.map(p => p.id)

// Step 2: Batch fetch ALL routing data (1 query instead of 59)
const { data: allRouting } = await supabase
  .from('routing')
  .select('item_id, id')
  .in('item_id', itemIds)

// Step 3: Build routing lookup map
const routingMap = new Map()
allRouting?.forEach(r => {
  if (!routingMap.has(r.item_id)) {
    routingMap.set(r.item_id, [])
  }
  routingMap.get(r.item_id).push(r)
})

// Step 4: Batch fetch ALL BOM relationships (1 query instead of 59)
const { data: allBom } = await supabase
  .from('bom')
  .select('parent_item_id, id')
  .in('parent_item_id', itemIds)

// Step 5: Build BOM lookup set
const hasChildrenSet = new Set(allBom?.map(b => b.parent_item_id) || [])

// Step 6: Process parts synchronously using the maps
for (const part of parts) {
  part.hasRouting = (routingMap.get(part.id)?.length || 0) > 0
  part.hasChildren = hasChildrenSet.has(part.id)
}
```

**Performance Improvement:**
- **Before:** 118 queries, 3-5 second hang
- **After:** 4 queries (items + routing + BOM + project), instant load

**Query Breakdown (After):**
1. Main items query with project join
2. Batch routing lookup (`.in('item_id', [59 IDs])`)
3. Batch BOM lookup (`.in('parent_item_id', [59 IDs])`)
4. Total: 3-4 queries regardless of part count

**Key Pattern:**
1. **Collect all IDs upfront** before any queries
2. **Use `.in()` for batch queries** instead of per-item `.eq()`
3. **Build lookup maps/sets** in JavaScript for fast in-memory lookups
4. **Process items synchronously** using the pre-fetched data

**When to Use This Pattern:**
- Any time you're processing a list of items and need related data for each
- When you see 100+ concurrent queries in DevTools Network tab
- When UI hangs/freezes during data loading
- When loop contains `await supabase...` calls

**Files Changed:** `frontend/src/views/MrpDashboardView.vue` (lines 220-260 in `loadProjectParts()`)

**Prevention:**
- **Never query inside a loop** unless the list is guaranteed tiny (< 5 items)
- **Always batch fetch** related data with `.in()` for lists
- **Profile query counts** in browser DevTools during development
- **Watch for "fan-out" patterns** where each item triggers multiple queries

**Related Pitfalls:**
- Similar to pitfall #1 (RLS admin client) - both involve Supabase query optimization
- Pattern applies to any ORM/query system, not just Supabase

**Commit:** 29d8e85

---

### 36. Vite Proxy Timeout (Print Packet "Unexpected End of JSON")

**Symptom:** When generating print packets on the web (MRP dashboard, large projects), the browser showed "Unexpected end of JSON" or "SyntaxError: Unexpected end of JSON input" after ~30-60 seconds. The loading spinner would hang indefinitely.

**Root Cause:** The Vite dev server proxy has a default timeout of ~30-60 seconds. Print packet generation for large projects can take several minutes due to:
1. Downloading multiple PDFs from Supabase Storage (one per part)
2. Creating routing stamp overlays for each PDF
3. Combining all PDFs into a single packet
4. Uploading the final packet back to Supabase Storage

When the proxy timed out, it terminated the connection mid-response. The browser received an incomplete JSON response, causing the parse error.

**Diagnosis:**
1. Tested print packet generation for small projects (1-3 parts) - worked fine, completed in <30 seconds
2. Tested large project (20+ parts) - failed consistently with "Unexpected end of JSON" after ~60 seconds
3. Checked backend logs - the backend continued processing after the browser error and successfully completed the packet
4. Checked browser Network tab - request showed "cancelled" or "failed" status after ~60 seconds
5. Searched for Vite proxy timeout configuration and found the default timeout is around 30-60 seconds

**Fix:** Added `timeout: 300000` (5 minutes) to the Vite proxy configuration in `frontend/vite.config.ts`:

**Before:**
```typescript
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5174,
    host: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        // No timeout specified - defaults to ~30-60 seconds
      },
    },
  },
})
```

**After:**
```typescript
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5174,
    host: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        timeout: 300000, // 5 minutes for long-running operations like print packet generation
      },
    },
  },
})
```

**Why 5 Minutes:**
- Average print packet generation time for a 20-part project: ~2-3 minutes
- Worst case (50+ parts with large PDFs): ~4 minutes
- 5 minutes provides a safe buffer while still catching truly hung requests

**Important Notes:**
- **This only affects development mode** - The Vite dev server proxy is only active during `npm run dev`
- **Production is unaffected** - In production, the backend serves the frontend directly (no proxy layer)
- **Backend continues processing** - Even if the user navigates away, the backend completes the packet generation and saves it. The user can access the generated packet when they return.

**Files Changed:** `frontend/vite.config.ts` (line 14)

**Prevention:**
- **Always test long-running operations with realistic data** - Small test cases may not reveal timeout issues
- **Consider adding progress indicators** - For operations >30 seconds, show incremental progress instead of a static spinner
- **Add operation timeouts to endpoints** - Backend endpoints should have their own timeout handling independent of proxy timeouts
- **Check proxy configs for dev vs production differences** - Dev server proxies may have different behavior than production reverse proxies

**Related Patterns:**
- Similar to timeout issues in other proxies (nginx, Apache, load balancers)
- Backend operations that continue after client disconnect need proper error handling

**Commit:** 03f788e

---

### 37. DXF Download Filenames and Type Conversion Issues

**Symptom:** DXF bundle downloads from MRP dashboard had generic filenames like `item.dxf`, making it hard to identify parts when multiple files were extracted. Shop floor needed thickness and quantity info visible in filenames for waterjet programming.

**Root Cause (Part 1 - Generic Filenames):** The `download_project_dxfs` endpoint used the original DXF filename from storage without adding part metadata. When extracting a bundle of 20+ DXF files, all filenames were just the item numbers (e.g., `csp0030.dxf`), with no indication of material thickness or quantity needed.

**Root Cause (Part 2 - Type Mismatch):** The `item_info` dictionary used `item_id` as UUID objects for keys, but when looking up file info, the file's `item_id` was also a UUID. However, dictionary lookups were failing silently because Python UUIDs have subtle comparison issues. The lookup always returned `{}` from the `.get()` fallback.

**Diagnosis:**
1. Reviewed MRP dashboard DXF download flow - confirmed filenames didn't include part specs
2. Talked to shop floor users - they manually rename files before loading into waterjet CAM software
3. Added logging to see what was in `item_info` dictionary
4. Discovered type mismatch: dictionary keys were UUID objects, lookups were using UUID objects, but equality checks were failing
5. Tested explicit string conversion for both dictionary keys and lookups

**Fix (Part 1 - Descriptive Filenames):** Changed filename format to include thickness and quantity:
```python
# backend/app/routes/mrp.py (lines 664-670)

# Build descriptive filename: {item_number}_thk-{thickness}_qty-{quantity}.dxf
file_item_id = str(file_info["item_id"])  # Ensure string for lookup
info = item_info.get(file_item_id, {})
item_num = info.get("item_number", "")
thickness = info.get("thickness")
quantity = info.get("quantity", 1)

if item_num:
    # Format thickness as thousandths (0.25" -> 0250, 0.125" -> 0125)
    if thickness is not None:
        thk_str = f"{int(float(thickness) * 1000):04d}"
    else:
        thk_str = "0000"

    # Build filename: csp0030_thk-0250_qty-2.dxf
    filename = f"{item_num}_thk-{thk_str}_qty-{quantity}.dxf"
else:
    filename = file_info["file_name"]  # Fallback to original
```

**Fix (Part 2 - Type Conversion):** Convert UUID to string for all dictionary operations:
```python
# When building the info map (line 611)
item_id = str(p["item_id"])  # Ensure string key
item_info[item_id] = {
    "item_number": p["items"]["item_number"],
    "thickness": p["items"].get("thickness"),
    "quantity": p.get("quantity", 1)
}

# When looking up during file processing (line 657)
file_item_id = str(file_info["item_id"])  # Ensure string for lookup
info = item_info.get(file_item_id, {})
```

**Thickness Formatting Details:**
- Input: `thickness` field from `items` table (decimal inches, e.g., 0.25, 0.125, 0.0625)
- Output: 4-digit string representing thousandths of inch (e.g., "0250", "0125", "0063")
- Formula: `f"{int(float(thickness) * 1000):04d}"`
- Example conversions:
  - 0.25" → 0250 (250 thousandths)
  - 0.125" → 0125 (125 thousandths, 1/8")
  - 0.0625" → 0063 (62.5 thousandths, 1/16")
  - 0.1875" → 0188 (187.5 thousandths, 3/16")

**Why This Matters:**
- Shop floor can identify part thickness without opening files
- CAM programmer knows quantity to nest before starting
- Waterjet operator can verify correct material loaded based on filename
- Reduces programming errors and material waste
- Filenames match industry standard format (part_thk_qty)

**Benefits:**
- Zero additional clicks - information visible in file browser
- Prevents wrong material selection (e.g., 0.125" part cut from 0.25" stock)
- Enables batch sorting by thickness in CAM software
- Filenames are self-documenting for future reference

**Files Changed:** `backend/app/routes/mrp.py` (lines 605-670)

**Prevention:**
- **Always use strings for dictionary keys** when dealing with UUIDs from Supabase queries - UUID equality can be unreliable
- **Add debugging logs** to show dictionary contents when lookups might fail silently
- **Include critical metadata in filenames** for files used in manufacturing - operators shouldn't need to open files to get basic specs
- **Use standard industry formats** for manufacturing filenames (part_spec_qty pattern is common in sheet metal shops)
- **Format thickness in thousandths** - this is the standard unit in US sheet metal industry, easier to read than decimal inches

**Commit:** c2a5e26

---

## Coding Patterns

### Pydantic Schema Pattern

Every database entity follows the Base/Create/Update/Read pattern:

```python
class ItemBase(BaseModel):
    """Shared fields for creation and reading."""
    item_number: str = Field(..., pattern=r"^[a-z]{3}\d{4,6}$")
    name: Optional[str] = None
    revision: str = "A"
    lifecycle_state: str = "Design"

class ItemCreate(ItemBase):
    """Fields required to create an item."""
    pass

class ItemUpdate(BaseModel):
    """All fields optional for partial updates."""
    name: Optional[str] = None
    revision: Optional[str] = None
    # ... all fields as Optional

class Item(ItemBase):
    """Full item as returned from database."""
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
```

**Key points:**
- `ItemBase` has validation (regex pattern on `item_number`)
- `ItemCreate` inherits from `ItemBase` (required fields enforced)
- `ItemUpdate` is independent with all `Optional` fields (partial update)
- `Item` adds server-generated fields (`id`, timestamps)
- `from_attributes = True` allows construction from ORM-like objects

### Supabase Client Query Patterns

```python
# List with filters, pagination, ordering
query = supabase.table("items").select("*, projects(name)")
if q:
    query = query.or_(f"item_number.ilike.%{q}%,name.ilike.%{q}%")
if lifecycle_state:
    query = query.eq("lifecycle_state", lifecycle_state)
query = query.order("item_number").range(offset, offset + limit - 1)
result = query.execute()

# Join and flatten
for item in result.data:
    project_data = item.pop("projects", None)
    if project_data:
        item["project_name"] = project_data.get("name")
```

### FastAPI Route Pattern

```python
router = APIRouter(prefix="/items", tags=["items"])

@router.get("", response_model=list[Item])
async def list_items(
    q: Optional[str] = Query(None, description="Search term"),
    limit: int = Query(50, le=1000),
    offset: int = 0,
):
    supabase = get_supabase_client()
    # ... query and return
```

**Conventions:**
- All routers use `APIRouter` with a prefix and tags
- Response models are always specified for type safety and documentation
- Query parameters use FastAPI's `Query()` with descriptions and constraints
- All routes are `async def`

### Vue Composition API Pattern

```vue
<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useItemsStore } from '../stores/items'

const store = useItemsStore()
const searchInput = ref('')
const selectedItem = ref<Item | null>(null)

const filteredItems = computed(() => {
  let result = [...store.items]
  if (searchInput.value) {
    const q = searchInput.value.toLowerCase()
    result = result.filter(item => item.item_number.includes(q))
  }
  return result
})

onMounted(() => {
  store.fetchItems({ limit: 1000 })
})
</script>
```

**Conventions:**
- `<script setup>` syntax exclusively (no Options API)
- TypeScript for type safety
- Stores via Pinia for shared state
- `ref()` for mutable state, `computed()` for derived state
- Data fetching in `onMounted()`

### Signed URL Pattern for File Access

Files in Supabase Storage are accessed via time-limited signed URLs:

```typescript
// frontend/src/services/storage.ts
export async function getSignedUrlFromPath(filePath: string): Promise<string | null> {
  // filePath format: "pdm-files/item_number/filename.ext"
  const parts = filePath.split('/')
  const bucket = parts[0]
  const path = parts.slice(1).join('/')

  const { data, error } = await supabase.storage
    .from(bucket)
    .createSignedUrl(path, 3600)

  return data?.signedUrl ?? null
}
```

---

## UI Design Direction

The interface follows a compact, professional, desktop-first design language inspired by PLM systems like Windchill and Teamcenter.

**Design principles:**

- **Compact spacing:** 8-12px padding on table cells, 4-8px gaps between elements
- **Small, readable fonts:** 13px base, 11-12px for labels and metadata
- **Neutral color palette:** Gray/white backgrounds, no gradients, minimal color accents
- **Information density:** Tables fill available space, columns are tightly packed
- **Sticky headers:** Table headers remain visible when scrolling
- **Controls bar:** Search, filters, and actions in a single toolbar row
- **Detail panel:** Slides in from the right side, showing item details, files, BOM, and where-used data without leaving the table view
- **Monospace for identifiers:** Item numbers and revision codes use monospace font
- **Lifecycle state badges:** Small, muted colored badges (not bright or distracting)
- **Keyboard navigation:** Escape closes panels; future support for arrow key navigation

**Font stack:** `'Segoe UI', Tahoma, Geneva, Verdana, sans-serif`

---

## Items Table vs Files Table

The database has two tables that reference item data:

- **`items`** -- One record per part/assembly. Contains metadata: `item_number`, `name`, `material`, `mass`, `price_est`, `lifecycle_state`, etc.
- **`files`** -- Multiple records per item. Each file (STEP, DXF, SVG, PDF, CAD) is a separate record linked by `item_id`.

When updating item data, ensure both tables are consistent. The upload bridge handles this by upserting the item record and separately uploading/registering files.

---

## Environment Configuration

Settings are loaded from environment variables via Pydantic Settings:

```python
# backend/app/config.py
class Settings(BaseSettings):
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    debug: bool = False
    cors_allow_all: bool = False

    class Config:
        env_file = ".env"
```

A `.env` file in `backend/` provides these values for local development. In production, environment variables are set by the deployment platform.

**Required environment variables:**
- `SUPABASE_URL` -- Supabase project URL
- `SUPABASE_ANON_KEY` -- Public anon key
- `SUPABASE_SERVICE_KEY` -- Secret service role key (never expose to frontend)

---

## Important Reminders

1. **Always use the admin client for internal service endpoints** -- the anon client will silently fail or return empty data when RLS blocks the operation.
2. **Normalize item numbers to lowercase at every entry point** -- the database, API, and frontend all assume lowercase.
3. **Store full storage paths (bucket/path) in the `file_path` column** -- use bucket-relative paths for Storage API calls.
4. **Convert UUIDs to strings before Supabase queries** -- the Python client does not auto-serialize Pydantic UUID fields.
5. **Use `limit(1)` instead of `single()` when an empty result is valid** -- `single()` throws on zero rows.
6. **Column is `price_est`** not `est_price` -- this column name has caused confusion across all system versions.
7. **Suffix stripping** -- Always remove `_prt`, `_asm`, `_drw`, `_flat` from filenames before extracting item numbers. The upload bridge handles this in `PDM-Upload-Functions.ps1`.
8. **The `zzz` prefix is for reference-only items** -- they appear in BOM exports but should not be created as real items.
9. **Check `backend/.env` for API_PORT** -- do not assume port 8000. The actual port may differ (e.g., 8001).
10. **Never use `%-` strftime on Windows** -- use f-string formatting (`dt.month`, `dt.day`) instead of `%-m`, `%-d`.
11. **Always convert UTC to local time** before comparing vault timestamps with local file timestamps. Use `dt.astimezone()`.
12. **Check mmc/spn/zzz patterns before standard pattern** -- the standard `[a-z]{3}\d{4,6}` regex will truncate McMaster and supplier part numbers.
13. **Touch local files after upload** -- update `LastWriteTime` to `Get-Date` after a successful check-in so timestamps stay in sync with vault.
14. **Per-alloy pricing model** -- Material prices are stored as $/lb per alloy (CS, AL, SS) in `cost_settings`. Tube $/ft is derived at runtime as `$/lb × weight_lb_per_ft`. Changing a single $/lb default updates all sheet metal AND tube of that alloy simultaneously.
15. **Material auto-prefill logic** -- When auto-assigning materials to a part, map `item.material` text field (STEEL, 304SS, ALUMINUM) to `material_code` (CS, SS, AL), then find closest thickness match within 15% tolerance. This prevents exact-match failures when sheet thicknesses don't perfectly align.
16. **McMaster parts are read-only supplier info** -- For `mmc` prefix items, auto-populate supplier name as "McMaster-Carr" and provide product page link. Don't allow editing supplier name for McMaster parts to maintain data consistency.
17. **CreoJS Workspace serves from localhost HTTP** -- Serve workspace.html from PDM-Local-Service on `http://localhost:8083` to avoid mixed content (HTTPS→HTTP blocked). The local service serves static files and bridges to cloud API (HTTP→HTTPS is allowed).
18. **Upload service uses production API by default** -- `PDM-Upload-Config.ps1` points to `https://pdm-web.fly.dev/api` so uploads work without running local backend. Switch to localhost for offline development.
19. **Regex filename matching for duplicates** -- Use `^param(_\d+)?\.txt$` pattern to handle Windows `_1`, `_2` suffixes when files drop faster than processing.
20. **Auto-sync scripts on service launch** -- `Start-PDMUpload.bat` copies latest .ps1 files from project source to `C:\PDM-Upload\` before starting service.
21. **PRICE_EST removed from Creo parser** -- MRP pricing engine owns cost estimates. Parser ignores `PRICE_EST` column to prevent CAD metadata from overwriting calculated prices.
22. **Waterjet time auto-calculation in routing editor** -- The MRP routing editor automatically calculates waterjet cut time when Waterjet station is selected or when applying routing templates. Uses `cut_length` from item data and material/thickness-specific speed formula from the `cutting_parameters` table. Formula: `speed = ref_speed × (0.25/thickness)^exponent × machinability`. Auto-fills on station dropdown change and on template application (Formed SM, Flat SM). Waterjet station code must be exactly `012` to trigger auto-calculation.
23. **Purchased routing template** -- New "Purchased" template in routing editor with 3 stations: 005 Receiving (10min), 020 Staging (5min), 050 Inspection (5min). Used for supplier parts that don't require manufacturing operations.
24. **Purchase info save retry on AbortError** -- Fixed issue where saving purchased part info (supplier name, part number, unit price) would hang after switching tabs. The save operation now catches `AbortError` (from tab switch) and retries the save after a brief delay.
25. **PDF upload date stamp position** -- Changed PDF upload date stamp from lower-right to lower-left corner (x=82pt, past corner marks) to avoid overlap with drawing title blocks. Font size increased from 8pt to 12pt for better visibility. Removed white background box for cleaner appearance.
26. **Price badge on item list** -- Items with assigned `unit_price` now show a green "$" badge in the routing editor item list, making it easy to identify purchased parts with pricing data.
27. **Routing state reset on item change** -- Routing editor now properly resets all state (operations, materials, purchase info) when selecting a new item. Prevents stale data from previous item from appearing in the UI.
28. **Station grouping for cost analysis** -- Added `station_group` column to `workstations` table to categorize stations into logical groups (Weld, Assembly, Fabrication, QC, Outsourced). Groups enable high-level cost category analysis in MRP Cost Report without losing individual station detail. Ungrouped stations default to "Other" group.
29. **ECharts nested pie for dual-level visualization** -- Replaced Chart.js with ECharts for cost report pie chart to support nested (two-ring) visualization. Inner ring shows individual stations color-coded by group (lighter shades), outer ring shows station groups (bold colors). Chart size increased 50% for readability. Legend toggle switches between showing all stations (detailed) vs. groups only (cleaner). ECharts performance is superior to Chart.js for datasets with >50 slices.
30. **Grouped operations table with expand/collapse** -- Cost report operations table now has grouped view (default) where groups are expandable to show nested stations. Group badges use matching chart colors (Weld red, Assembly purple, Fabrication blue, QC green, Outsourced orange). Toggle "Group By Station" checkbox to switch between grouped and flat views. Click group row to expand/collapse nested stations.
31. **Station color inheritance from groups** -- Stations inherit lighter shades of their group's color for visual consistency between chart and table. Color palette uses 4 shades per group (lightest to boldest). Station slice colors assigned via index modulo to cycle through shades. Hard-coded color palettes in `groupColors` and `stationColors` objects for predictable appearance.
32. **Backend dual summary structures** -- Cost report endpoint returns both `operations_summary` (individual stations) and `operations_summary_grouped` (group-level with nested stations) to support both chart views and table modes. Chart data also duplicated as `cost_breakdown_chart` and `cost_breakdown_chart_grouped`. Frontend chooses which structure to display based on UI state.
33. **Print packet routing stamp transparency** -- Changed print packet routing stamp from opaque white background to transparent with dark gray border. Stamp box now uses `fill=0` (transparent) instead of `fill=1` (white), stroke color changed from black to dark gray (0.3, 0.3, 0.3), and line width set to 0.5pt. This prevents the stamp from obscuring underlying drawing content while maintaining readability of routing information.
34. **N+1 query batching pattern** -- Fixed MRP dashboard sidebar hanging when loading projects with many parts. The issue was a classic N+1 query pattern: for each part, two separate queries were executed (routing + BOM check), causing 118+ concurrent queries for a 59-part project. Solution: collect all item IDs upfront, batch fetch ALL routing data with a single `.in('item_id', itemIds)` query, batch fetch ALL BOM relationships with `.in('parent_item_id', itemIds)`, build lookup maps in memory, then process parts synchronously using the maps. Reduced 118 queries to 4 queries, making the sidebar load instantly. **Pattern:** Always batch fetch related data using `.in()` for large datasets instead of querying per-item in a loop.
35. **Vite proxy timeout for long operations** -- Added `timeout: 300000` (5 minutes) to Vite dev server proxy config in `frontend/vite.config.ts` to prevent "Unexpected end of JSON" errors during print packet generation. The default proxy timeout of ~30-60 seconds was too short for operations that download multiple PDFs, create overlays, and combine into one packet. **Development only** - production is unaffected since the backend serves the frontend directly (no proxy layer). Backend continues processing even if client disconnects.
36. **DXF filenames include thickness and quantity** -- DXF bundle downloads from MRP dashboard now use descriptive filenames: `{item_number}_thk-{thickness}_qty-{quantity}.dxf`. Thickness is formatted as 4-digit thousandths of inch (0.25" → 0250, 0.125" → 0125). This prevents shop floor errors when loading files into waterjet CAM software - operator can verify correct material thickness from filename without opening the file. Format matches industry standard (part_spec_qty pattern). **UUID dictionary keys must be strings** - when building lookup dictionaries with UUIDs from Supabase, always convert to string with `str(uuid)` for both keys and lookups, as UUID equality checks can fail silently.
37. **Backend reload requires killing all Python processes** -- On Windows, uvicorn's `--reload` flag doesn't always properly restart when code changes. Multiple zombie Python processes can accumulate on port 8001, and requests may be routed to old processes with stale code. **Always kill ALL Python processes before restarting backend:** `taskkill /F /IM python.exe`, then verify port 8001 is free with `netstat -ano | findstr 8001`, then start a single clean backend. VS Code integrated terminals can auto-start multiple servers. Use a single dedicated terminal for backend development.
38. **FastAPI route ordering matters** -- Parameterized routes like `@router.get("/{item_id}")` must be defined AFTER all specific routes (e.g., `/list`, `/upload`). FastAPI matches routes in definition order, and parameterized routes act as catch-alls that intercept any path. Always organize routes: specific paths first, then parameterized paths at the end. Test all endpoints after reorganizing routes.

---

### 37. Backend Code Changes Not Taking Effect

**Problem:** When modifying Python backend code (especially in `app/routes/files.py`), changes may not take effect even with uvicorn's `--reload` flag. Multiple zombie Python processes can accumulate on port 8001, and requests may be handled by old processes with stale code.

**Symptoms:**
- Code changes don't appear in behavior (e.g., PDF stamps don't move)
- Backend logs don't show expected debug output
- `netstat -ano | findstr 8001` shows multiple LISTENING processes
- Iteration numbers increment but visual changes don't appear

**Solution:**
1. Kill ALL Python processes: `taskkill /F /IM python.exe`
2. Verify port 8001 is free: `netstat -ano | findstr 8001` should return empty
3. Start a single clean backend: `cd backend && python -m uvicorn app.main:app --reload --port 8001`
4. Verify single listener: `netstat -ano | findstr 8001` should show ONE process

**Why This Happens:**
- Windows doesn't always release port bindings immediately
- Multiple terminal sessions may have started backends
- VS Code integrated terminals may auto-start servers
- The `--reload` flag watches files but may not properly restart in all cases

**Prevention:**
- Always check for existing processes before starting backend
- Use a single terminal for backend development
- Add `flush=True` to print statements for immediate output visibility

**Files Affected:** Any backend route file, especially `backend/app/routes/files.py`

**Related Pitfalls:**
- Similar to pitfall #1 (service restarts) - services can cache old code
- Applies to any hot-reload development workflow on Windows

**Commit:** (Current session)

---

### 38. Chrome PDF Extension Crash from Supabase Auth Events

**Problem:** Opening files via `window.open()` to Supabase signed URLs caused the Chrome PDF viewer extension to crash with "Aw, snap!" error. The page would briefly load the PDF, then crash completely.

**Root Cause:** Supabase fires `SIGNED_IN` auth events when generating signed URLs, even if the user is already authenticated. The auth handler in `auth.ts` called `fetchUser()` on every `SIGNED_IN` event, which made API requests to `/api/auth/user`. These API requests disrupted Chrome's PDF viewer extension message channels, causing the extension to crash mid-render.

**Flow:**
1. User clicks "View PDF" button
2. Frontend calls `getSignedUrlFromPath()` to get Supabase signed URL
3. Supabase client fires `SIGNED_IN` auth event during signed URL generation
4. Auth handler calls `fetchUser()` (unnecessary - user already loaded)
5. `fetchUser()` makes `/api/auth/user` request
6. Chrome PDF viewer extension receives message channel disruption
7. PDF extension crashes with "Aw, snap!" error

**Symptoms:**
- Clicking "View PDF" button shows PDF briefly (~1 second), then crashes
- Browser console shows "Aw, snap!" error page
- Happens consistently when opening PDFs via `window.open()`
- Works fine when downloading files (no extension involvement)
- Issue specific to Chrome's built-in PDF viewer

**Diagnosis:**
1. Added logging to auth event handler to see event frequency
2. Discovered `SIGNED_IN` events firing every time signed URL was generated
3. Confirmed `fetchUser()` was making API requests on each event
4. Tested disabling auth handler entirely - PDF viewing worked fine
5. Tested skipping `fetchUser()` when user already loaded - PDF viewing worked fine

**Fix:** Added guard clause in auth event handler to skip `fetchUser()` if user already loaded:

```typescript
// frontend/src/services/auth.ts

supabase.auth.onAuthStateChange(async (event, session) => {
  if (event === 'SIGNED_IN') {
    // Skip fetchUser if already loaded (prevents Chrome PDF extension crash)
    if (currentUser.value) {
      return
    }
    await fetchUser()
  }
  // ... other event handling
})
```

**Why This Works:**
- Prevents redundant API calls when user is already authenticated
- Avoids disrupting Chrome's PDF viewer extension message channels
- User data stays fresh from initial auth, no need to refetch on every signed URL
- Still fetches user on genuine sign-in events (when `currentUser.value` is null)

**Files Changed:**
- `frontend/src/services/auth.ts` - Added guard clause in `onAuthStateChange` handler

**Prevention:**
- **Avoid unnecessary API calls in auth event handlers** - check if data is already loaded before fetching
- **Be aware of auth event triggers** - Supabase fires events for internal operations like signed URL generation
- **Test file viewing in Chrome** - Chrome PDF extension is sensitive to message channel disruptions
- **Use browser DevTools Network tab** - helps identify unexpected API calls during user interactions
- **Consider idempotency** - auth handlers should safely handle duplicate events

**Related Patterns:**
- Similar to performance issues in other pitfalls - reducing unnecessary operations
- Chrome extension message channels are fragile and need stable contexts

**Commit:** (Current session)

---

### 39. Vue Proxy Breaks External Library Private Fields (shallowRef Pattern)

**Problem:** When integrating PDF.js library with Vue 3 for PDF measurement tool, the PDF document object became inaccessible after being stored in a `ref()`. Attempting to call methods on the PDF document returned "Cannot read private property #X" errors, and the PDF would not render.

**Root Cause:** Vue 3 wraps all objects in `ref()` with JavaScript Proxy objects to track reactivity. When the Proxy wraps an object with private class fields (fields defined with `#` syntax), those fields become inaccessible because Proxy cannot intercept Symbol-based property access. PDF.js `PDFDocumentProxy` uses private fields internally, so the Proxy breaks all internal state access.

**Code Pattern (Wrong):**
```typescript
import * as pdfjsLib from 'pdfjs-dist'

// This wraps PDFDocumentProxy in a Proxy, breaking private fields
const pdfDoc = ref<pdfjsLib.PDFDocumentProxy | null>(null)

async function loadPdf() {
  const loadingTask = pdfjsLib.getDocument(url)
  pdfDoc.value = await loadingTask.promise  // Wrapped in Proxy here!

  // Error when trying to access internal methods:
  const page = await pdfDoc.value.getPage(1)  // "Cannot read private field"
}
```

**Symptoms:**
- PDF fails to render in canvas
- Console errors: "Cannot read private property #X of PDFDocumentProxy"
- PDF.js methods return undefined or throw exceptions
- Works fine outside Vue components (plain JavaScript)

**Diagnosis:**
1. Checked browser console and saw private field access errors
2. Tested same PDF.js code in plain JavaScript - worked fine
3. Realized the issue was Vue's reactivity system wrapping the object
4. Researched Vue 3 documentation and found `shallowRef()` for this exact case
5. Tested `shallowRef()` instead of `ref()` - PDF worked immediately

**Fix:** Use `shallowRef()` instead of `ref()` for external library objects with private fields:

```typescript
import { shallowRef } from 'vue'
import * as pdfjsLib from 'pdfjs-dist'

// shallowRef skips proxy wrapping - keeps original object intact
const pdfDoc = shallowRef<pdfjsLib.PDFDocumentProxy | null>(null)

async function loadPdf() {
  const loadingTask = pdfjsLib.getDocument(url)
  pdfDoc.value = await loadingTask.promise  // Not wrapped in Proxy

  // Works fine - no private field access errors:
  const page = await pdfDoc.value.getPage(1)  // Success!
}
```

**Why This Works:**
- `shallowRef()` only tracks changes at the top level, doesn't deep-proxy inner objects
- PDF.js object keeps all private fields accessible
- Reactivity still works - replacing the entire PDF document triggers re-renders
- No loss of functionality, just no reactivity on inner properties (which don't change anyway)

**Files Changed:**
- `frontend/src/components/PdfMeasure.vue` - Line 24: `const pdfDoc = shallowRef<pdfjsLib.PDFDocumentProxy | null>(null)`

**Prevention:**
- **When integrating external libraries:** Check if the library uses private fields or Symbol-based properties
- **If private fields are used:** Use `shallowRef()` instead of `ref()`
- **General pattern:** For objects that manage their own internal state (like PDF.js, Canvas API, D3.js), use `shallowRef()`
- **When in doubt:** Try `shallowRef()` first for external libraries, switch to `ref()` only if you need deep reactivity

**Key Insight:**
The `shallowRef()` / `ref()` choice is about **what needs to be reactive**, not about whether to use reactivity. PDF.js object is replaced wholesale (entire new document loaded), not mutated piece-by-piece. `shallowRef()` captures that pattern perfectly.

**Related Patterns:**
- Similar to context-specific tool choices (use the right tool for the pattern)
- Vue's `markRaw()` is another option but `shallowRef()` is cleaner here
- D3.js selections, Canvas API contexts, and other library objects have same pattern

**Applies To:**
- PDF.js library integration
- D3.js selections
- Canvas API contexts
- Any external library with private fields or Symbol-based state

**Commit:** (Current session - PDF Measurement Tool feature)

---

### 40. Routing Badge Not Showing (Supabase 1000 Row Limit)

**Symptom:** The routing badge in MrpRoutingView.vue showed "No routing" for items like sjp00020 even though routing existed in the database. Some parts showed routing correctly, others did not, with no obvious pattern.

**Root Cause:** Supabase has a server-side hard limit of 1000 rows per query. The routing table had 1016+ rows. When the frontend queried `supabase.from('routing').select('item_id')` to get all item IDs with routing, Supabase truncated results at 1000 rows. Items whose routing entries fell beyond row 1000 (like sjp00020) weren't included in the returned data, so the routing count for those items was zero.

**Diagnosis:**
1. Checked routing table row count in Supabase SQL editor: `SELECT COUNT(*) FROM routing` returned 1016+
2. Checked query in browser DevTools Network tab - response only contained ~1000 rows
3. Realized the frontend was using a plain `select()` query with no pagination
4. Researched Supabase docs and confirmed 1000-row server limit exists
5. Tested with RPC function approach - worked correctly for all items

**Fix:** Created a PostgreSQL RPC function `get_routing_counts()` that uses SQL GROUP BY to return item_id/count pairs, bypassing the row limit:

```sql
-- Migration: add_routing_counts_function
CREATE OR REPLACE FUNCTION get_routing_counts()
RETURNS TABLE (item_id UUID, routing_count BIGINT) AS $$
BEGIN
  RETURN QUERY
  SELECT r.item_id, COUNT(*)::BIGINT as routing_count
  FROM routing r
  GROUP BY r.item_id;
END;
$$ LANGUAGE plpgsql;
```

Updated MrpRoutingView.vue to use RPC instead of direct table query:

```typescript
// OLD (broken for items beyond row 1000)
const { data: allRouting } = await supabase
  .from('routing')
  .select('item_id')

// NEW (works for any table size)
const { data: routingCounts } = await supabase
  .rpc('get_routing_counts')
```

**Why This Works:**
- RPC functions return computed results, not raw table rows
- The GROUP BY aggregation happens server-side in Postgres (no row limit)
- Result set is item_id + count pairs (one row per item with routing)
- Typical result is 50-200 rows (number of unique items with routing), well below 1000-row limit
- Even with 10,000 routing entries, result set stays small

**Files Changed:**
- Database migration: `add_routing_counts_function.sql` (new RPC function)
- `frontend/src/views/MrpRoutingView.vue` (lines ~145-155, changed to use RPC)

**Prevention:**
- **Never assume unlimited query results** - Supabase has hard limits
- **Use RPC functions for aggregations** - GROUP BY, COUNT, SUM operations should happen server-side
- **Test with production-scale data** - Small dev datasets don't reveal row limit issues
- **Check table row counts** - If a table has >500 rows, assume it will eventually hit the 1000 limit
- **Use pagination or RPC** - For tables that grow over time, plan for the limit from the start

**Related Patterns:**
- Similar to N+1 query batching (pitfall #35) - both involve optimizing database access patterns
- RPC functions are the Supabase equivalent of stored procedures for aggregations

**Commit:** 3ac1a85

---

### 41. DXF Generation Crash on Coincident Points

**Symptom:** DXF generation for sjp00020 failed with error `Part.OCCError: Line through identical points`. The flattening script crashed during arc or discretization processing, preventing DXF output from being created.

**Root Cause:** The `flatten_sheetmetal.py` script had two code paths that could produce zero-length edges (coincident start/end points):

1. **Arc fallback case (line ~189):** When arc processing failed, the script fell back to creating lines. If the arc start and end points were identical (zero-radius arc or degenerate geometry), it tried to create a line with identical start/end points, which crashes FreeCAD's Part module.

2. **Discretize fallback case (line ~233):** When edge type was unknown, the script discretized the edge into line segments. If discretization produced consecutive points that were identical (e.g., very small curve segments), it tried to create zero-length lines, causing the same crash.

**Diagnosis:**
1. Ran DXF generation for sjp00020 via MRP dashboard "Generate DXF" button
2. Backend logs showed `Part.OCCError: Line through identical points` from FreeCAD worker
3. Checked `flatten_sheetmetal.py` and found arc fallback and discretize cases lacked distance checks
4. Reviewed FreeCAD Part.makeLine() documentation - confirmed it rejects zero-length lines
5. Tested fix with zero-length edge check (`< 1e-6 mm`) - generation succeeded

**Fix:** Added distance checks before creating lines in both fallback cases:

```python
# Arc fallback case (line ~189)
try:
    # ... arc creation code ...
except Exception as e_arc:
    # Arc failed - fallback to line IF length is non-zero
    p1 = FreeCAD.Vector(...)
    p2 = FreeCAD.Vector(...)

    # Check for zero-length edge (coincident points)
    if p1.distanceToPoint(p2) < 1e-6:
        print(f"  Skipping degenerate arc edge (zero length)")
        continue

    line_2d = Part.makeLine(p1, p2)
    # ...

# Discretize fallback case (line ~233)
points_3d = edge.discretize(20)
for i in range(len(points_3d) - 1):
    p1 = project_to_2d(points_3d[i])
    p2 = project_to_2d(points_3d[i+1])

    # Check for zero-length segment
    if p1.distanceToPoint(p2) < 1e-6:
        continue

    segment = Part.makeLine(p1, p2)
    # ...
```

**Why 1e-6 Threshold:**
- FreeCAD works in millimeters internally
- 1e-6 mm = 0.000001 mm = 1 nanometer (effectively zero for sheet metal parts)
- Prevents floating-point precision issues from triggering false positives
- Standard tolerance for geometric equality checks in CAD systems

**Files Changed:**
- `worker/scripts/flatten_sheetmetal.py` (lines ~189 and ~233)

**Prevention:**
- **Always validate geometric inputs before creating shapes** - Check for degenerate cases (zero length, zero radius, etc.)
- **Use distance thresholds for comparisons** - Floating-point equality (`p1 == p2`) is unreliable, use `distance < epsilon`
- **Add defensive checks in fallback paths** - Fallback code runs when primary logic fails, so input assumptions may not hold
- **Test with real-world geometry** - CAD files can have edge cases (pun intended) like zero-radius arcs
- **Log and skip invalid geometry** - Better to skip a degenerate edge than crash the entire export

**Related Patterns:**
- Similar to other geometric processing pitfalls - always validate inputs before operations
- Epsilon-based comparisons are standard in CAD/CAM systems
- Defensive programming in error-handling paths is critical

**What Degenerate Geometry Looks Like:**
- Zero-radius arc from a sharp corner or vertex
- Collapsed edge from boolean operations
- Tiny sliver from surface intersection
- Duplicate vertices in imported STEP geometry
- Curve endpoints that overlap after projection to 2D

**Commit:** 3ac1a85

### 42. Incorrect MRP Part Quantities from Stale BOM Exports

**Symptom:** MRP Dashboard shows incorrect part quantities. For example, project WM_0513 showed vinyl decal (stp00260) quantity as 16 instead of 12.

**Root Cause:** Stale MLBOM export data from the CAD system. The MLBOM.txt file contained outdated BOM relationships that didn't match the current assembly structure in Creo.

**Example Case (WM_0513):**
- MRP Dashboard showed `stp00260` (vinyl decal) quantity as 16
- CAD assembly `STA01080` only had 1 instance of `JBA00020` (FRONT COVER)
- Stale MLBOM export had `STA01080 → JBA00020` with quantity 2 instead of 1
- BOM rollup calculation: 2 × 2 × 4 = 16 (should have been 1 × 2 × 4 = 8)

**Diagnosis:**
1. Checked `bom` table for parent-child relationship between STA01080 and JBA00020
2. Found quantity was 2 in the database
3. Verified in Creo that only 1 instance exists in the assembly
4. Checked `source_file` column - MLBOM export was weeks old
5. Realized the BOM upload had used stale export data

**How BOM Upload Works:**

The upload pipeline uses a full-replacement strategy:
1. **Parse MLBOM.txt** (`PDM-BOM-Parser.ps1`) - Uses indentation to detect parent-child relationships and counts duplicate children to determine quantities
2. **Upload to API** (`/api/bom/bulk`) - Backend **DELETES** all existing BOM entries for the parent, then **INSERTS** new entries from parsed data
3. **MRP Parts Rollup** (`MrpDashboardView.vue` `explodeBomRecursive()`) - Traverses BOM tree and multiplies quantities at each level to calculate total part requirements

**Fix:**
1. Re-exported MLBOM.txt from Creo (Tools → Table → Tree)
2. Re-uploaded via PowerShell upload service (copy to `C:\PDM-Upload`)
3. Clicked **Update** button in MRP Dashboard assemblies section to recalculate `mrp_project_parts`
4. Verified corrected quantities (16 → 12)

**Files Involved:**
- `scripts/pdm-upload/PDM-BOM-Parser.ps1` - Parses indented BOM text files
- `scripts/pdm-upload/PDM-Upload-Functions.ps1` - Calls `/api/bom/bulk`
- `backend/app/routes/bom.py` (line ~197) - DELETE then INSERT strategy
- `frontend/src/views/MrpDashboardView.vue` (lines 657-687) - `explodeBomRecursive()` function

**Prevention:**
- **Always re-export MLBOM after assembly changes** - Don't rely on old exports
- **The BOM upload is safe to re-run** - Full-replacement strategy prevents partial updates
- **MRP Dashboard "Update" button is a cache refresh** - Always click after BOM changes
- **Check `source_file` timestamp** - The `bom.source_file` column can help identify stale data

**Key Lesson:** MRP project parts (`mrp_project_parts`) is a calculated cache derived from the BOM tree. It does not auto-update when the BOM changes. You must manually trigger the recalculation via the "Update" button in the MRP Dashboard.

**Related Docs:**
- `Documentation/05-POWERSHELL-SCRIPTS-INDEX.md` - BOM parser details
- `Documentation/19-TROUBLESHOOTING-DECISION-TREE.md` - Step 5: Incorrect BOM Quantities
- `Documentation/20-COMMON-WORKFLOWS.md` - Section 4: Uploading a BOM

---

### 43. Design Book Image Management System Improvements

**Symptom (Route Conflict):** When accessing `/api/design-book-images/list` or `/api/design-book-images/upload`, the API returned 404 or responded with the wrong handler. The parameterized `/{image_id}` route was catching all paths.

**Symptom (Upload Form State):** After uploading an image in the Design Book Images view, the project ID was cleared from the upload form. Subsequent uploads lost the project association, requiring the user to re-select the project each time.

**Symptom (Design Book Re-rendering):** When images were added, modified, or removed from the Design Book image library, the III-00 (General Reference) section was not detected as changed during the Check & Update workflow. The section would not re-render with updated images.

**Root Cause (Route Conflict):** FastAPI route matching is order-dependent. The parameterized route `@router.get("/{image_id}")` was defined before specific paths like `/list` and `/upload`. Since `/{image_id}` matches any path segment, it intercepted requests intended for `/list` and `/upload`, treating them as image IDs.

**Root Cause (Upload Form State):** The `resetUploadForm()` function cleared ALL form fields after successful upload, including `uploadProjectId`. When viewing images in a Design Book context (where `bookCode` is set and the project ID is pre-selected), clearing `uploadProjectId` lost this context.

**Root Cause (Design Book Re-rendering):** The Master Design Book diffing algorithm compares content hashes to detect changes. The III-00 (General Reference) section descriptor did not include any image-related data in its hash input. When images changed in the `design_book_images` table, the descriptor payload remained the same, so the content hash stayed the same, and the section was marked as "unchanged."

**Diagnosis:**

**Route Conflict:**
1. Tested `/api/design-book-images/list` endpoint from frontend - returned 422 validation error (tried to parse "list" as UUID)
2. Checked route definition order in `backend/app/routes/design_book_images.py`
3. Found `@router.get("/{image_id}")` at line 348, before specific routes
4. Confirmed FastAPI matches routes in definition order (first match wins)

**Upload Form State:**
1. Uploaded first image in Design Book context - worked fine, project ID pre-filled
2. Uploaded second image - project dropdown showed "Select project (optional)..." instead of template project
3. Added logging to `resetUploadForm()` - confirmed `uploadProjectId` was being cleared
4. Checked if `bookCode` prop was available - yes, it was set
5. Realized the reset function needed to preserve `uploadProjectId` when in Design Book mode

**Design Book Re-rendering:**
1. Added images to Design Book image library
2. Clicked "Check for Changes" in Master Design Book view
3. Diff showed no changes, even though new images existed
4. Reviewed `master_design_book.py` hash input builder
5. Confirmed III-00 descriptor had static payload with no image references
6. Realized images needed to be represented in the hash input to trigger re-render

**Fix (Route Conflict):** Reorganized routes in `backend/app/routes/design_book_images.py` to place specific paths BEFORE parameterized routes:

**Before:**
```python
@router.get("")  # Empty path for list
async def list_images(...):
    ...

@router.post("/upload")  # Specific path
async def upload_image(...):
    ...

@router.get("/{image_id}")  # Parameterized - catches everything!
async def get_image(image_id: UUID):
    ...
```

**After:**
```python
# Specific paths FIRST
@router.get("/list")  # Changed from "" to "/list"
async def list_images(...):
    ...

@router.post("/upload")
async def upload_image(...):
    ...

# Parameterized routes LAST
@router.get("/{image_id}")
async def get_image(image_id: UUID):
    ...
```

Also updated frontend to use the new path: `/api/design-book-images/list` instead of `/api/design-book-images`

**Fix (Upload Form State):** Modified `resetUploadForm()` to preserve `uploadProjectId` when in Design Book context:

```javascript
function resetUploadForm() {
  uploadFile.value = null
  uploadPreview.value = null
  uploadCaption.value = ''
  uploadNotes.value = ''
  uploadCategoryId.value = ''
  // Keep uploadProjectId if we're in a design book context
  if (!bookCode.value) {
    uploadProjectId.value = ''
  }
  uploadItemSearch.value = ''
  uploadItemId.value = ''
  uploadWidthPct.value = 100
}
```

**Logic:** If `bookCode` is set (Design Book mode), preserve the project ID. Otherwise (standalone image management), clear it.

**Fix (Design Book Re-rendering):** Added image hash computation and injection into III-00 descriptor payload:

**New Function (`_compute_image_hash`):**
```python
def _compute_image_hash(supabase, project_id: str) -> str:
    """Compute a hash of all images for a project to detect changes.

    Uses image IDs and updated_at timestamps to create a deterministic hash
    that changes when images are added, removed, or modified.
    """
    if not project_id:
        return ""

    try:
        # Get all images for the project
        result = supabase.table("design_book_images")\
            .select("id, updated_at")\
            .eq("project_id", project_id)\
            .order("id")\
            .execute()

        if not result.data:
            return ""

        # Build deterministic string: id1:timestamp1|id2:timestamp2|...
        parts = []
        for img in result.data:
            parts.append(f"{img['id']}:{img['updated_at']}")

        # Hash the concatenated string
        import hashlib
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
    except Exception as e:
        print(f"Warning: Failed to compute image hash: {e}")
        return ""
```

**Injection Point (in `check_book` and `update_book`):**
```python
# Inject image hash into general_reference descriptor to trigger re-render when images change
# This ensures III-00 is re-rendered when images are added/removed/modified
if book.get("template_project_id"):
    image_hash = _compute_image_hash(supabase, book["template_project_id"])
    for d in non_spine:
        if d.get("kind") == "general_reference":
            d.setdefault("payload", {})["_image_hash"] = image_hash
            break
```

**How It Works:**
1. Before hashing descriptors, compute image hash from project's images
2. Find the III-00 (general_reference) descriptor
3. Inject `_image_hash` into its `payload` dictionary
4. When the descriptor is hashed, the image hash participates
5. If images changed, hash changes, section detected as changed, re-renders

**Why This Approach:**
- Deterministic: Same images → same hash (ordered by ID, formatted consistently)
- Lightweight: Only queries image IDs and timestamps (not full records or file bytes)
- Non-invasive: Injects into payload (which is already part of hash input), doesn't modify core schema
- Fast: Single query, simple string concatenation, standard SHA-256

**Files Changed:**

**Route Conflict:**
- `backend/app/routes/design_book_images.py` (lines 158, 348+)
  - Changed `/` to `/list` for list endpoint
  - Reorganized routes: specific paths first, parameterized routes last
- `frontend/src/views/MrpDesignBookImagesView.vue` (line ~180)
  - Updated API call from `/api/design-book-images` to `/api/design-book-images/list`

**Upload Form State:**
- `frontend/src/views/MrpDesignBookImagesView.vue` (lines 293-306)
  - Modified `resetUploadForm()` to preserve `uploadProjectId` when `bookCode` is set

**Design Book Re-rendering:**
- `backend/app/services/master_design_book.py` (lines 246-267)
  - Added `_compute_image_hash()` function
- `backend/app/services/master_design_book.py` (lines 1896-1903)
  - Injected image hash into III-00 descriptor payload before hashing

**Why This Matters:**

**Route Conflict:** Without proper route ordering, the API becomes unpredictable. The parameterized route acts as a catch-all, breaking all specific endpoints defined after it. This is a common pitfall in path-based routing frameworks.

**Upload Form State:** In workflow-oriented UIs, preserving context across operations reduces friction. When a user is working within a specific Design Book, they expect the project association to persist for all uploads, not reset after each one.

**Design Book Re-rendering:** The Master Design Book is a controlled document where accuracy is critical. When images change, the printed III-00 section must be re-rendered to show the current image set. Without hash participation, stale images would persist in the document, violating the change detection contract.

**Benefits:**

**Route Conflict:**
- API endpoints work as documented
- Frontend can call `/list` without UUID validation errors
- Clear separation between specific operations and ID-based lookups

**Upload Form State:**
- Reduces clicks: no need to re-select project after each upload
- Prevents errors: images automatically tagged with correct project
- Better UX: context preservation matches user mental model

**Design Book Re-rendering:**
- Automatic change detection: adding/removing images triggers III-00 re-render
- Accurate revision tracking: change notices show when images changed
- No manual intervention: system detects and handles image changes transparently

**Prevention:**

**Route Conflict:**
- **Always define specific paths before parameterized paths** in FastAPI routers
- **Use explicit path prefixes** (`/list`, `/upload`) instead of empty strings or root paths
- **Test all endpoints after route reorganization** to verify routing behavior
- **Consider route priority** when designing API path structure

**Upload Form State:**
- **Preserve workflow context** when resetting forms between operations
- **Check for ambient state** (like `bookCode`, `projectId`) before clearing fields
- **Design reset logic** based on use cases: standalone vs. workflow-embedded
- **Test multi-step workflows** to catch context loss issues

**Design Book Re-rendering:**
- **Include related data in hash inputs** when that data affects rendered output
- **Use deterministic hashing** for cache invalidation and change detection
- **Compute hashes from source data** (DB queries), not rendered artifacts (PDFs)
- **Test change detection** with add/modify/delete scenarios for all data types

**Related Patterns:**
- Similar to route ordering in Express.js, Flask, and other path-based routers
- Form state preservation is analogous to wizard/multi-step form patterns
- Hash-based change detection is the same pattern used for BOM rollup cache invalidation

**Applies To:**
- FastAPI route definition order (all parameterized routes should be last)
- Any UI with workflow context (preserve context across operations in the same flow)
- Cache invalidation and change detection systems (content-addressable hashing)

**Commit:** (Current session - Design Book Image Management)

**Related Docs:**
- `Documentation/36-MASTER-DESIGN-BOOK-PLAN.md` — Master Design Book architecture
- `Documentation/24-VERSION-HISTORY.md` — Version history (to be updated)

---

### 44. Purchase List CSV Must Include Individual Kit Parts

**Date:** 2026-07-27
**Symptom:** The purchase list CSV export showed vendor bundles as a single line item, making it impossible for the shop to verify individual parts on receipt.
**Root Cause:** The `get_purchase_list_csv()` function only exported bundle metadata (kit number, vendor, total part count), not the individual parts within each bundle.
**Impact:** When KIT-001 (18 tube parts) arrived from the vendor, the shop had no checklist to verify all parts were included and matched the bound prints in the receiving booklet.

**The Fix:**

Modified `backend/app/services/master_design_book.py::get_purchase_list_csv()` (lines 2636-2711) to:

1. Query `project_item_source` joined with `project_kits` and `items` to fetch all parts with `source_type='kit'`
2. Query `mrp_project_parts` to get part quantities for the template project
3. Build a `kit_parts_by_number` map: `{kit_number: [{item_number, name, qty}, ...]}`
4. For each bundle in the CSV:
   - Write bundle header row (Type=BUNDLE)
   - Write individual kit part rows underneath (Type=KIT PART, indented with leading space)
5. Separate bundles from individual purchased parts with a blank row

**CSV Structure Change:**

Before:
```csv
Part #,Source,Description,Qty,Long Lead,Type,Ordered,Received
KIT-001,Precision Tube Laser,Tube Laser Bundle (18 parts),1,,BUNDLE,,
mmc9056k362,McMaster-Carr,M8 Socket Cap Screw,100,,PART,,
```

After:
```csv
Part #,Source,Description,Qty,Long Lead,Type,Ordered,Received
KIT-001,Precision Tube Laser,Tube Laser Bundle (18 parts),1,,BUNDLE,,
  csp00010,KIT-001,TUBE 2X2X.125 28.43 LONG,2,,KIT PART,,
  csp00020,KIT-001,TUBE 2X2X.125 24.75 LONG,2,,KIT PART,,
  ...

mmc9056k362,McMaster-Carr,M8 Socket Cap Screw,100,,PART,,
```

**How to Diagnose:**

1. Export purchase list CSV: `GET /api/design-books/{book_code}/purchase-list-csv`
2. Check if bundles have individual parts listed underneath
3. Verify `Type` column shows BUNDLE / KIT PART / PART distinctions
4. Confirm quantities match the project BOM (`mrp_project_parts`)

**Why This Matters:**

**Incoming Inspection:** When vendor bundles arrive, the shop needs to verify every part against its print. A bundle header alone doesn't provide the detail needed for this quality control step. The shop flow is:
1. Unpack bundle
2. Cross-check each part number against CSV checklist
3. Match physical parts to bound prints in I-RCV receiving booklet
4. Check off both bundle and individual parts
5. Route verified parts to staging areas

**Traceability:** The CSV provides a complete audit trail of what was ordered and received. Without individual part visibility, it's impossible to track which specific parts were missing or incorrect in a vendor shipment.

**Prevention:**

- **Export full hierarchies** when dealing with bundles/kits/assemblies - users need detail, not just summary
- **Include child items in checklists** for verification workflows (purchasing, receiving, inspection)
- **Query related tables** (like `project_item_source`) to reconstruct full context when exporting data
- **Use indentation/formatting** in CSV exports to show hierarchical relationships visually
- **Test with real workflow** - have shop personnel review CSV format before finalizing

**Related Work:**

- **KIT-001 created for SPA0040** (2026-07-27): Copied PTL tube bundle from SPA0030 to new project. 33 parts total at $10,755.85. Note: `csp00060` was excluded because it was commonized into `csp00050` across both projects.

**Applies To:**
- CSV/Excel export features where hierarchical data must be represented
- Purchase/receiving workflows requiring item-by-item verification
- Any "bundle" or "kit" concept where the whole contains multiple trackable parts

**Commit:** (Current session - Kit Management)

**Related Docs:**
- `Documentation/37-KIT-BUNDLE-PRICING.md` — Kit/bundle pricing system
- `Documentation/38-KIT-SOURCING-IN-BUILD-DOCS.md` — Section 7: Purchase List CSV Enhancement
- `Documentation/36-MASTER-DESIGN-BOOK-PLAN.md` — Master Design Book architecture

---

### 39. STL Viewer with 3D Annotations

**What was built:** Interactive Three.js-based 3D model viewer with click-to-annotate capability for both internal users and external suppliers.

**Files Created:**
- `frontend/src/components/StlViewer.vue` - Three.js STL viewer component with CSS2D labels
- `backend/app/routes/annotations.py` - Annotation CRUD API routes

**Database Changes:**
New table: `model_annotations`
```sql
CREATE TABLE model_annotations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id UUID NOT NULL REFERENCES files(id),
    item_id UUID NOT NULL REFERENCES items(id),
    position_x NUMERIC NOT NULL,
    position_y NUMERIC NOT NULL,
    position_z NUMERIC NOT NULL,
    normal_x NUMERIC,
    normal_y NUMERIC,
    normal_z NUMERIC,
    content TEXT NOT NULL,
    author_type TEXT NOT NULL CHECK (author_type IN ('user', 'supplier')),
    author_id TEXT NOT NULL,
    author_name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

**Architecture Decisions:**
1. **Three.js + OrbitControls** for 3D rendering with intuitive camera control
2. **CSS2DRenderer** for annotation labels that scale properly with zoom
3. **Raycasting for click detection** to find exact surface position and normal vector
4. **Dual authentication support** - Works with both user JWT tokens (`/api/files/{file_id}/annotations`) and supplier tokens (`/api/supplier/items/{item_number}/files/{file_id}/annotations`)
5. **Color-coded markers** - Blue spheres for user annotations, green for supplier annotations
6. **Position + Normal storage** - Stores both 3D position and surface normal for future enhancement (e.g., arrow indicators)

**Integration Points:**
- `ItemDetailView.vue` - "View 3D" button for STL files opens viewer with annotation mode
- `SupplierItemView.vue` - Suppliers can view and annotate STL models shared with them
- Both users and suppliers see all annotations on the same model (two-way communication)

**How to Use:**
1. Click "View 3D" on any STL file
2. Click "Add Note" button to enter annotation mode
3. Click on the 3D model surface to place an annotation marker
4. Enter note text and save
5. Annotations appear as colored spheres with hover labels
6. Click any annotation to view full content and timestamp

**Prevention/Best Practices:**
- Always store both `position` and `normal` even if normal isn't used yet (future-proofs for directional indicators)
- Use CSS2D labels (not sprite-based) for better text readability and accessibility
- Separate annotation endpoints by auth type to enforce proper RLS
- Store `author_name` denormalized to avoid joins when displaying annotations

**Files Changed:**
- `frontend/src/components/StlViewer.vue` (NEW)
- `backend/app/routes/annotations.py` (NEW)
- `frontend/src/views/ItemDetailView.vue` - Added STL viewer integration
- `frontend/src/views/supplier/SupplierItemView.vue` - Added STL viewer for suppliers
- `backend/app/models/schemas.py` - Added `Annotation`, `AnnotationCreate` schemas
- `backend/app/routes/__init__.py` - Registered annotations router

**Testing:**
1. Upload STL file to an item
2. Open 3D viewer from item detail page
3. Add annotation as user
4. Grant supplier access to same item (with STL file type)
5. Supplier logs in, opens 3D viewer, adds annotation
6. Both annotations visible to both parties with color coding

---

### 40. Supplier Portal File Type and Field Enhancements

**What was added:** Extended Supplier Portal to support IMAGE file type in addition to PDF and STEP, plus added `thickness` and `mass` fields to supplier item responses.

**Root Cause:** Suppliers were initially restricted to PDF (drawings) and STEP (3D models) for manufacturability. However, reference images (photos, diagrams, assembly instructions) are often critical for quoting and production. Additionally, thickness and mass data were missing from supplier API responses even though they're visible in internal views.

**Files Changed:**
- `backend/app/routes/supplier.py`:
  - Line 114: Added `'IMAGE'` to default `file_types` array
  - Lines 152-153, 229-230: Added `thickness` and `mass` to `SupplierItemView` responses
  - Lines 415-516: Added supplier annotation endpoints (`GET`/`POST /api/supplier/items/{item_number}/files/{file_id}/annotations`)

- `backend/app/models/supplier_schemas.py`:
  - Added `thickness: Optional[float]` and `mass: Optional[float]` to `SupplierItemView` schema

- `frontend/src/types/supplier.ts`:
  - Added `thickness?: number` and `mass?: number` to `SupplierItemView` interface

- `frontend/src/views/supplier/SupplierItemView.vue`:
  - Added STL viewer integration (lines 6, 22-24, 70-85, 242-255)
  - Added "View 3D" button for STL files (lines 182-188)

**Impact:**
- Suppliers can now download reference images (photos, assembly diagrams)
- Suppliers see part thickness and mass in portal (critical for material/weight calculations)
- Suppliers can add 3D annotations to STL files visible to internal team

**File Type Mapping:**
- PDF - Technical drawings (DXF converted to PDF)
- STEP - 3D CAD models for CAM programming
- IMAGE - Reference photos, assembly instructions, material certifications
- STL - 3D mesh for visualization and annotation (added in this session)

**Prevention:**
- When adding new file types, update both `file_types` array default AND supplier access UI
- Always include relevant item metadata (`thickness`, `mass`, `material`) in supplier responses
- Document which file types serve which supplier use cases

---

### 41. Per-Unit vs Per-Line-Item Time Basis for MRP Routing

**What was built:** Added `time_basis` field to routing operations to distinguish between per-unit times (multiply by quantity) and per-line-item times (fixed regardless of quantity).

**Symptom:** Kit-supplied parts with receiving operations (e.g., "5 min receiving") were inflating project schedules when ordered in quantity. Ordering 20 pieces showed 100 minutes of receiving time (20 × 5 min), but in reality, receiving one shipment line takes 5 minutes total regardless of piece count.

**Root Cause:** The scheduling system multiplied ALL routing times by quantity. This is correct for manufacturing operations (cutting 10 brackets takes 10× the time of cutting 1), but incorrect for procurement operations like receiving, inspection, or kitting. These are per-line-item activities, not per-piece.

**Database Changes:**
Added `time_basis` column to `routing` table:
```sql
ALTER TABLE routing ADD COLUMN time_basis TEXT DEFAULT 'per_unit'
  CHECK (time_basis IN ('per_unit', 'per_line_item'));
```

**Code Changes:**
- `frontend/src/utils/buildTracker.ts`:
  - Lines 112, 392: Added `time_basis?: 'per_unit' | 'per_line_item'` to routing interfaces
  - Line 433: Set `time_basis: op.timeBasis` when creating routing from kit operations

- `frontend/src/utils/scheduling.ts`:
  - Line 87: Added `time_basis` to `RoutingStep` interface
  - Lines 300-304: Implemented time_basis logic in schedule calculation:
    ```typescript
    const timeBasis = r.time_basis || 'per_unit'
    const durationMin = timeBasis === 'per_line_item'
      ? (r.est_time_min || 0)           // Fixed time regardless of quantity
      : (r.est_time_min || 0) * part.quantity  // Traditional: multiply by quantity
    ```

- `frontend/src/views/MrpRoutingView.vue`:
  - Line 62: Added `time_basis: 'per_unit' | 'per_line_item'` to `RoutingRow` interface
  - Line 1087: Default new manual stations to `'per_unit'`
  - Line 1154: Preserve `time_basis` when adding stations from templates
  - Line 1179: Default to `'per_unit'` when loading existing routing if field is null

**Use Cases:**

**Per-Unit (Multiply by Quantity):**
- Fabrication: Cutting 10 brackets = 10× cutting time
- Machining: Drilling 50 holes = 50× drilling time
- Assembly: Welding 8 frames = 8× welding time
- Finishing: Painting 30 parts = 30× painting time

**Per-Line-Item (Fixed Time):**
- Receiving: Unpacking one shipment box = fixed 5 min regardless of piece count inside
- Inspection (sampling): QC check of batch = fixed time (not every piece)
- Kitting: Preparing one kit set = fixed time regardless of how many kits are ordered
- Vendor quoting: Time to get quote is per RFQ, not per piece

**How It Works:**
1. Kit-supplied parts get `RCVE` (Receiving) station with `time_basis: 'per_line_item'`
2. Routing editor shows time basis in UI (future enhancement: toggle in routing view)
3. Build Tracker schedule calculation respects time basis
4. Build Book work packages show correct time estimates

**Backward Compatibility:**
- Existing routing records default to `'per_unit'` (preserves current behavior)
- No data migration required
- Null values treated as `'per_unit'`

**Testing:**
1. Create kit with receiving operation (5 min)
2. Add kit part to project with quantity 20
3. Build Tracker schedule shows 5 min total (not 100 min)
4. Change to `'per_unit'` → schedule shows 100 min
5. Change back to `'per_line_item'` → schedule shows 5 min

**Prevention:**
- When adding new routing templates, consider whether the operation scales with quantity
- Receiving, inspection, and kitting operations should default to `'per_line_item'`
- Manufacturing operations (cut, weld, paint) should use `'per_unit'`
- Document time basis in routing notes if non-obvious

**Files Changed:**
- Database migration: `ALTER TABLE routing ADD COLUMN time_basis TEXT DEFAULT 'per_unit' CHECK (time_basis IN ('per_unit', 'per_line_item'))` - **APPLIED** (column now exists in production)
- `backend/app/routes/mrp.py` - Cost calculation respects time_basis (fixed vs variable labor costs)
- `frontend/src/utils/buildTracker.ts` - Added time_basis support in build tracker, KIT_SUPPLIED_ROUTING uses per_line_item
- `frontend/src/utils/scheduling.ts` - Implemented time_basis calculation logic (duration calculation checks time_basis)
- `frontend/src/views/MrpRoutingView.vue` - Added time_basis to routing editor interface, PURCHASED template uses per_line_item
- `frontend/src/utils/masterDesignBook.ts` - Added time_basis to routing interface

**Auto-Migration Applied:**
- Existing mmc/spn prefixed parts with Receiving/Staging operations were automatically migrated to use `time_basis: 'per_line_item'`
- Manufacturing operations (cutting, welding, assembly) remain `'per_unit'`

**Follow-Up Tasks:**
1. ~~Create database migration file for `time_basis` column~~ - **COMPLETE**
2. Add UI toggle in Routing Editor to set time_basis per station (currently defaults correct, but no manual toggle)
3. ~~Update routing templates to set correct defaults (RCVE = per_line_item, FAB/WELD/ASSY = per_unit)~~ - **COMPLETE**
4. Show time basis indicator in Build Tracker station columns (e.g., "5m (per line)" vs "5m (per unit)")

---

### 42. Missing Routing on New Top-Level Assemblies Causes Schedule Discrepancies

**Symptom:** When comparing two similar projects (SPA0030 vs SPA0040), one project showed significantly lower total time despite having identical part counts, quantities, and kit sourcing.

**Example Case:**
- **SPA0030:** 133 parts, 299 total qty, 33 kit-sourced → ~159 hours total
- **SPA0040:** 133 parts, 299 total qty, 33 kit-sourced → ~145 hours total
- **Discrepancy:** 14 hours (840 minutes) difference

**Root Cause:** The top-level assembly items had different routing configurations:
- SPA0030 uses top assembly `csa00010` which had 840 minutes of routing defined:
  - 017 Weld Cleanup: 240 min
  - 025 Mechanical Assembly: 240 min
  - 047 Vinyl Wrap: 240 min
  - 050 Inspection: 120 min
- SPA0040 uses top assembly `csa00015` which had **NO routing defined** (empty routing table)

**Why This Happens:**
When creating a new project variant with a different top-level assembly item number:
1. The new assembly item is created in the `items` table
2. The BOM structure is populated (all child relationships)
3. BUT routing operations are NOT automatically copied from the original assembly
4. The new assembly has zero operations, leading to missing time in project estimates

**Diagnostic Steps:**

1. **Compare project totals** in the MRP Dashboard or Build Tracker:
   - Look for unexpectedly low total hours on a new project
   - Compare similar projects (same BOM depth, part count, kit sourcing)

2. **Check top assembly routing** in the database:
   ```sql
   -- Get routing for both top assemblies
   SELECT r.station_code, w.station_name, r.est_time_min
   FROM routing r
   JOIN workstations w ON r.station_code = w.station_code
   WHERE r.item_id IN (
     SELECT id FROM items WHERE item_number IN ('csa00010', 'csa00015')
   )
   ORDER BY r.sequence;
   ```

3. **Verify in Routing Editor:**
   - Open MRP Routing Editor
   - Filter by the suspect top assembly item
   - Check if operations are defined

**How to Fix:**

**Option 1: Copy routing via SQL (fastest for exact duplicates)**

```sql
-- Copy routing from csa00010 to csa00015
INSERT INTO routing (item_id, station_code, sequence, est_time_min, notes, method)
SELECT
  (SELECT id FROM items WHERE item_number = 'csa00015'),
  station_code,
  sequence,
  est_time_min,
  notes,
  method
FROM routing
WHERE item_id = (SELECT id FROM items WHERE item_number = 'csa00010');
```

**Option 2: Add routing manually via Routing Editor**

1. Navigate to MRP Routing Editor
2. Select the new assembly item
3. Add each required operation with station and time estimate
4. Save routing

**Option 3: Apply routing template** (if a standard template exists)

1. Open Routing Editor
2. Select the assembly item
3. Click the appropriate template button (e.g., "Formed SM" or "Flat SM")
4. Adjust times as needed

**Verification:**

After adding routing, verify the fix:

1. **Check routing in database:**
   ```sql
   SELECT COUNT(*) FROM routing
   WHERE item_id = (SELECT id FROM items WHERE item_number = 'csa00015');
   -- Should return > 0
   ```

2. **Compare project totals again:**
   - Both projects should now show similar total hours
   - Difference should be within expected range (minor BOM variations)

3. **Check Build Tracker schedule:**
   - Open MRP Project Tracking for the fixed project
   - Verify the top assembly now has scheduled operations
   - Total project duration should increase to match the baseline

**Prevention:**

1. **When creating a new project variant:**
   - After creating the new top assembly item and BOM
   - Immediately check if routing needs to be copied
   - Use SQL copy method if the routing is identical to the original

2. **Routing checklist for new projects:**
   - [ ] Top assembly has routing operations defined
   - [ ] Critical sub-assemblies have routing (weldments, kits)
   - [ ] Schedule calculation shows reasonable total hours
   - [ ] Compare against similar projects to validate

3. **Add validation in project creation workflow:**
   - (Future enhancement) Warn when a project's top assembly has no routing
   - (Future enhancement) Offer to copy routing from a template or similar item

**Related Documentation:**
- `Documentation/20-COMMON-WORKFLOWS.md` - Section 15: Project Scheduling and Capacity Planning
- `Documentation/32-BUILD-BOOK.md` - Build Book relies on complete routing data
- `Documentation/31-BUILD-TRACKER-SHEET.md` - Build Tracker matrix depends on routing

**Files Involved:**
- Database: `routing` table, `items` table
- Frontend: `frontend/src/views/MrpRoutingView.vue` (Routing Editor)
- Frontend: `frontend/src/utils/scheduling.ts` (Schedule calculation)
- Frontend: `frontend/src/views/MrpProjectTrackingView.vue` (Project Tracking view)

**Date Discovered:** 2026-07-27
**Affected Projects:** SPA0040 (fixed), potential issue for any new project variant
**Severity:** High (leads to incorrect project time estimates and schedules)

---

### 43. Database Query Case Sensitivity (file_type, status fields)

**Symptom:** Queries return zero results when data clearly exists. Example: searching for DXF files returns nothing, but the UI shows DXF files are present.

**Root Cause:** PostgreSQL string comparisons are case-sensitive by default. The `files.file_type` column stores uppercase values (`'DXF'`, `'STEP'`, `'PDF'`, `'SVG'`, `'CAD'`) but queries may use lowercase (`'dxf'`).

**Example of the Bug:**

```sql
-- WRONG: Returns 0 rows even when DXF files exist
SELECT * FROM files WHERE file_type = 'dxf';

-- CORRECT: Matches actual data
SELECT * FROM files WHERE file_type = 'DXF';

-- ALSO CORRECT: Case-insensitive match
SELECT * FROM files WHERE UPPER(file_type) = 'DXF';
```

**Affected Columns (known uppercase conventions):**
- `files.file_type`: `'DXF'`, `'STEP'`, `'PDF'`, `'SVG'`, `'CAD'`, `'IMAGE'`, `'OTHER'`
- `mrp_projects.status`: `'Setup'`, `'Active'`, `'Complete'`, `'On Hold'`
- `items.lifecycle_state`: `'Design'`, `'Production'`, `'Obsolete'`

**Prevention Rules:**

1. **Always verify actual data format first:**
   ```sql
   SELECT DISTINCT file_type FROM files ORDER BY file_type;
   ```

2. **Use case-insensitive comparison when uncertain:**
   ```sql
   WHERE UPPER(file_type) = 'DXF'
   -- or
   WHERE file_type ILIKE 'dxf'
   ```

3. **Sanity-check results:** If a query returns zero matches for something that should exist (e.g., "no sheet metal parts have DXF files"), the query is likely wrong—investigate the query before reporting the result.

**Real-World Impact:** Incorrectly reported that 39/39 sheet metal parts in project WM_0513 were missing DXF files. All 39 actually had DXF files—the query just used the wrong case.

**Date Discovered:** 2026-08-06
**Severity:** High (leads to incorrect reports and wasted investigation time)

---

## Primary Test Projects

**Note:** The primary projects used for development and testing are **SPA0030** and **SPA0040**, not TEST-PROG01.

**Background:**
- `TEST-PROG01` was the original test project used in early development
- As the system matured, real production projects `SPA0030` and `SPA0040` became the primary testing ground
- These projects provide realistic data for:
  - Kit sourcing (both have KIT-001 tube laser bundle from Precision Tube Laser)
  - Routing complexity (mix of fabrication, welding, assembly operations)
  - Design Book generation (Master Design Book "spa-standard" is built from SPA0030)
  - Schedule calculation and capacity planning
  - Build Tracker and Build Book rendering

**Usage:**
- When testing MRP features, use `SPA0030` or `SPA0040` for realistic scenarios
- When testing kit sourcing, both projects have KIT-001 configured (SPA0030: 18 parts, SPA0040: 33 parts)
- When testing Design Book generation, spa-standard template project is SPA0030
- `TEST-PROG01` may have stale or incomplete data; prefer the SPA projects

**Project Details:**

| Project | Purpose | Kit Sourcing | Design Book |
|---------|---------|--------------|-------------|
| SPA0030 | Primary test project | KIT-001 (18 parts, PTL tube bundle) | Template for spa-standard book (rev 3) |
| SPA0040 | Secondary test project | KIT-001 (33 parts, PTL tube bundle) | Not yet published |
| TEST-PROG01 | Legacy test project | May have stale data | Not used |

**Related Documentation:**
- `Documentation/38-KIT-SOURCING-IN-BUILD-DOCS.md` - Kit sourcing details and measured impact on SPA0030
- `Documentation/36-MASTER-DESIGN-BOOK-PLAN.md` - Design Book architecture (spa-standard from SPA0030)
- `Documentation/32-BUILD-BOOK.md` - Build Book structure and rendering

---

## 16. MRP Vendor Kits View - Dual Kit Systems

**Date:** 2026-08-11
**Version:** v3.9.11

### What Was Built

A new full-page Vendor Kits management UI (`MrpKitsView.vue`, 1055 lines) for managing vendor kits/bundles at the project level. This extends the existing kit pricing system with a more sophisticated interface.

**Key Features:**
- Project-scoped kit management (kit number, name, vendor, price, notes)
- Detailed kit item tracking with quantities and unit prices
- Inline editing of quantities and prices
- Kit activation toggle (only one active kit per project)
- Cost comparison: vendor quote vs calculated item total
- Add/remove parts from kits via modal
- Navigate from MRP Dashboard via "Vendor Kits" button

**Route:** `/mrp/kits`
**Component:** `frontend/src/views/MrpKitsView.vue`

---

### Architecture Issue: Dual Kit Systems

**IMPORTANT:** The new UI expects a `kit_items` table that **does not exist** in the database yet. This creates a **parallel system** to the existing kit pricing feature.

**Existing System (Doc 37):**
- Table: `project_item_source` (created 2026-07-09)
- Purpose: Mark parts as "make" or "kit" for cost calculation
- UI: Kit Management Slideout on MRP Dashboard
- Backend: `backend/app/routes/kits.py` (uses `project_item_source`)

**New System (Doc 46):**
- Table: `kit_items` (NOT CREATED YET)
- Purpose: Track kit contents with quantities and unit prices
- UI: Dedicated `/mrp/kits` view
- Backend: Expects new endpoints for `kit_items` CRUD

**Tables Expected by New UI:**

```sql
-- Already exists (shared between both systems)
CREATE TABLE project_kits (
    id UUID PRIMARY KEY,
    project_id UUID REFERENCES mrp_projects(id),
    kit_number VARCHAR(50),
    kit_name VARCHAR(255),
    vendor VARCHAR(255),
    price DECIMAL(12, 2),
    use_kit BOOLEAN,
    notes TEXT,
    ...
);

-- NEW - Does not exist yet!
CREATE TABLE kit_items (
    id UUID PRIMARY KEY,
    kit_id UUID REFERENCES project_kits(id) ON DELETE CASCADE,
    item_id UUID REFERENCES items(id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL DEFAULT 1,
    unit_price DECIMAL(12, 2),  -- Optional unit price
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_item_per_kit UNIQUE (kit_id, item_id)
);
```

**Vue Component Queries:**

```javascript
// Load kits with part counts
const { data } = await supabase
  .from('project_kits')
  .select(`
    *,
    kit_items (
      quantity
    )
  `)
  .eq('project_id', selectedProjectId.value)

// Load kit items with item details
const { data } = await supabase
  .from('kit_items')
  .select(`
    *,
    items (
      item_number,
      description,
      material,
      thickness
    )
  `)
  .eq('kit_id', kitId)
```

**These queries will FAIL** until the `kit_items` table is created.

---

### What's Missing

1. **Database Migration**
   - File: `backend/migrations/2026-08-11_kit_items.sql`
   - Action: Create `kit_items` table with foreign keys, indexes, RLS policies

2. **Backend API Endpoints**
   - `GET /api/mrp/projects/{project_id}/kits` - Update to return `part_count` and `total_pieces` from `kit_items`
   - `GET /api/mrp/projects/{project_id}/kits/{kit_id}/items` - List kit items
   - `POST /api/mrp/projects/{project_id}/kits/{kit_id}/items` - Bulk add items to kit
   - `PATCH /api/kit-items/{item_id}` - Update quantity/unit_price
   - `DELETE /api/kit-items/{item_id}` - Remove item from kit
   - `GET /api/mrp/projects/{project_id}/available-items?exclude_kit={kit_id}` - Items not in kit

3. **Cost Calculation Updates**
   - File: `backend/app/services/cost_estimate.py`
   - Query `kit_items` instead of (or in addition to) `project_item_source`
   - Exclude parts found in active kits from individual cost calculations

4. **Schema Documentation**
   - File: `Documentation/03-DATABASE-SCHEMA.md`
   - Add `kit_items` table definition

---

### Decision Required

**Keep Both Systems or Migrate to One?**

**Option A: Keep Both (Parallel Systems)**
- `project_item_source` → Simple "make vs kit" toggle (Routing page)
- `kit_items` → Detailed kit composition (/mrp/kits view)
- **Pros:** Non-breaking change, existing features continue to work
- **Cons:** Dual data models increase complexity, potential for inconsistency

**Option B: Migrate to `kit_items` Only**
- Deprecate `project_item_source`
- Migrate existing data to `kit_items` format
- Update all cost calculations to use `kit_items`
- Remove Kit Management Slideout from MRP Dashboard
- **Pros:** Single source of truth, simpler long-term
- **Cons:** Migration effort, breaking change

**Recommendation:** **Option B** - Migrate to `kit_items` only.

**Reasons:**
- `kit_items` provides richer data model (qty + unit_price)
- Dedicated UI is more usable than modal slideout
- Single data model simplifies future enhancements (kit templates, price history, etc.)
- Migration can be done with data preservation (convert existing `project_item_source` to `kit_items` with qty=1)

---

### Migration Strategy

**Phase 1: Database Setup**
1. Create `kit_items` table migration
2. Migrate existing `project_item_source` data:
   ```sql
   INSERT INTO kit_items (kit_id, item_id, quantity, unit_price, created_at)
   SELECT kit_id, item_id, 1 AS quantity, NULL AS unit_price, created_at
   FROM project_item_source
   WHERE source_type = 'kit' AND kit_id IS NOT NULL;
   ```
3. Test migration on dev environment

**Phase 2: Backend Updates**
1. Add `kit_items` CRUD endpoints to `backend/app/routes/kits.py`
2. Update `GET /api/mrp/projects/{project_id}/kits` to use `kit_items`
3. Update `cost_estimate.py` to query `kit_items` instead of `project_item_source`
4. Add unit tests

**Phase 3: Frontend Updates**
1. Test `/mrp/kits` view with real data
2. Remove Kit Management Slideout from MRP Dashboard (optional)
3. Remove `project_item_source` UI from Routing page (optional)

**Phase 4: Deprecation**
1. Mark `project_item_source` as deprecated in schema comments
2. Optionally drop table after confirming all features work with `kit_items`
3. Update documentation to reflect new system

---

### Files Changed

**Frontend:**
- `frontend/src/views/MrpKitsView.vue` - New 1055-line view
- `frontend/src/views/MrpDashboardView.vue` - Added "Vendor Kits" nav button
- `frontend/src/router/index.ts` - Added `/mrp/kits` route

**Backend:**
- No changes yet (requires migration and API updates)

**Documentation:**
- `Documentation/46-MRP-VENDOR-KITS.md` - Complete feature documentation
- `Documentation/00-TABLE-OF-CONTENTS.md` - Added doc 46 to index

---

### Next Steps

1. **Create `kit_items` migration** (highest priority - UI is non-functional without this)
2. **Update backend API routes** to support `kit_items` CRUD
3. **Update cost calculation** to use new data model
4. **Test with sample project** to verify full workflow
5. **Migrate existing data** from `project_item_source` to `kit_items`
6. **Deprecate old system** (optional, but recommended)

---

### Related Documentation

- **46-MRP-VENDOR-KITS.md** - Full feature documentation (new)
- **37-KIT-BUNDLE-PRICING.md** - Original kit pricing system (uses `project_item_source`)
- **03-DATABASE-SCHEMA.md** - Needs update with `kit_items` table
- **04-SERVICES-REFERENCE.md** - Needs update with new API endpoints

---

**Last Updated:** 2026-08-11
**Version:** 3.9.11
**Related:** [27-WEB-MIGRATION-PLAN.md](27-WEB-MIGRATION-PLAN.md), [24-VERSION-HISTORY.md](24-VERSION-HISTORY.md)
