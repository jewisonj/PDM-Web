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

**Symptom:** All API calls from workspace.html returned 404. The browser console showed requests going to `localhost:8000`.

**Root Cause:** The `PDM_CONFIG` in `workspace.html` had `apiUrl: 'http://localhost:8000'` but the FastAPI backend runs on port 8001 (configured in `backend/.env` as `API_PORT=8001`).

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

---

**Last Updated:** 2026-02-01
**Version:** 3.2.1
**Related:** [27-WEB-MIGRATION-PLAN.md](27-WEB-MIGRATION-PLAN.md), [24-VERSION-HISTORY.md](24-VERSION-HISTORY.md)
