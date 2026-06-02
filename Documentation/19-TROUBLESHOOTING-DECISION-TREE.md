# PDM-Web System - Troubleshooting Guide

**Diagnostic guide for common issues in the web-based PDM system**
**Related Docs:** [15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md](15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md), [18-GLOSSARY-TERMS.md](18-GLOSSARY-TERMS.md)

---

## Start Here - Choose Your Problem

### Problem Categories

1. [Backend Not Starting](#backend-not-starting)
2. [Frontend Not Loading](#frontend-not-loading)
3. [Authentication Issues](#authentication-issues)
4. [File Upload Failures](#file-upload-failures)
5. [BOM Upload Issues](#bom-upload-issues)
   - [Step 5: Incorrect BOM Quantities in MRP Project Parts](#step-5-incorrect-bom-quantities-in-mrp-project-parts)
6. [Database Connection Problems](#database-connection-problems)
7. [Data Issues](#data-issues)
8. [Upload Bridge Problems](#upload-bridge-problems)

---

## Backend Not Starting

**Symptom:** `uvicorn` fails to start or the API returns errors.

### Step 1: Check Uvicorn Output

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Look for error messages in the terminal output. Common errors are listed below.

### Step 2: Missing .env File or Environment Variables

**Error:** `ValidationError` from Pydantic Settings, or empty/missing Supabase URL.

```
pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
supabase_url
  Field required
```

**Fix:** Create or verify `backend/.env`:

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_KEY=eyJ...
API_PORT=8000
DEBUG=true
CORS_ALLOW_ALL=true
```

**Verify the file exists:**

```bash
# Check .env exists in backend directory
ls backend/.env
```

### Step 3: Missing Python Dependencies

**Error:** `ModuleNotFoundError: No module named 'fastapi'` (or similar).

**Fix:**

```bash
cd backend
pip install -r requirements.txt
```

If using a virtual environment, make sure it is activated first.

### Step 4: Port Already in Use

**Error:** `[Errno 98] Address already in use` or `[WinError 10048]`.

**Fix:**

```bash
# Find what is using the port (Windows)
netstat -ano | findstr :8000

# Kill the process by PID
taskkill /PID <pid> /F

# Or use a different port
uvicorn app.main:app --reload --port 8001
```

### Step 5: Supabase Connection Failure

**Error:** Network errors, timeout, or `AuthApiError`.

**Diagnostic steps:**

1. Verify the Supabase URL is correct (check dashboard at https://supabase.com/dashboard)
2. Verify the anon key and service key match the project
3. Check internet connectivity
4. Try accessing the Supabase URL in a browser: `https://your-project.supabase.co/rest/v1/`

### Step 6: Import Errors

**Error:** `ImportError` or circular import issues.

**Common causes:**

- Running from wrong directory (must be in `backend/` or use `cd backend && uvicorn app.main:app`)
- Missing `__init__.py` in a package directory
- Circular imports between modules

**Fix:** Ensure you run uvicorn from the `backend/` directory:

```bash
cd backend
uvicorn app.main:app --reload
```

---

## Frontend Not Loading

**Symptom:** Browser shows blank page, errors, or cannot connect to API.

### Step 1: Check Vite Dev Server

```bash
cd frontend
npm run dev
```

**Error:** `npm ERR! Missing script: "dev"`

**Fix:**

```bash
cd frontend
npm install
npm run dev
```

### Step 2: Node Modules Missing

**Error:** `Cannot find module` errors during startup.

**Fix:**

```bash
cd frontend
rm -rf node_modules
npm install
npm run dev
```

### Step 3: API URL Misconfigured

**Symptom:** Frontend loads but shows no data, or network requests fail in browser dev tools.

**Diagnostic:**

1. Open browser Developer Tools (F12)
2. Go to the Network tab
3. Look for failed API requests (red entries)
4. Check the request URL -- it should point to `http://localhost:8000/api/`

**Fix:** Verify the API base URL in the frontend configuration. Check `frontend/.env` or `frontend/src/services/` for the API URL setting. It should point to the backend server:

```
VITE_API_URL=http://localhost:8000
```

Or if using the Supabase client directly, verify `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` are set.

### Step 4: CORS Errors

**Symptom:** Browser console shows `Access-Control-Allow-Origin` errors.

**Diagnostic:** Open browser Developer Tools (F12), check Console tab for CORS messages.

**Fix:** Ensure the backend CORS configuration allows the frontend origin. In `backend/.env`:

```
CORS_ALLOW_ALL=true
```

Or add the specific origin to `cors_origins` in `backend/app/config.py`.

### Step 5: Blank Page After Build

**Symptom:** `npm run build` succeeds but the page is blank in production.

**Diagnostic:** Check browser console for JavaScript errors. Common cause is incorrect base URL for the router.

**Fix:** Verify `vite.config.ts` has the correct `base` setting for your deployment path.

---

## Authentication Issues

**Symptom:** Cannot log in, or logged-in state is lost.

### Step 1: Wrong Credentials

**Symptom:** Login form shows "Invalid credentials" or similar error.

**Diagnostic:**

1. Verify the email/password in Supabase Auth dashboard
2. Check if the user exists: Supabase Dashboard -> Authentication -> Users
3. Try resetting the password via the dashboard

### Step 2: JWT Token Expired

**Symptom:** Was logged in, now API calls return 401 Unauthorized.

**Diagnostic:** Open browser Developer Tools -> Application tab -> Local Storage. Look for the Supabase session token and check its expiry.

**Fix:** Log out and log back in. The Supabase client library should auto-refresh tokens, but if the refresh token has also expired, a fresh login is required.

### Step 3: RLS Blocking Data Access

**Symptom:** User is authenticated but API returns empty data or 403 errors.

**Diagnostic:**

1. Check Supabase Dashboard -> Table Editor -> items table
2. Click the RLS shield icon to view policies
3. Verify that the authenticated user matches the policy conditions

**Common cause:** RLS policies require a specific role or user ID that the current user does not have.

**Temporary fix for development:** Use the admin client (`get_supabase_admin()`) in the affected endpoint. For production, fix the RLS policy in the Supabase dashboard.

### Step 4: Auth State Not Persisting

**Symptom:** User must log in again after every page refresh.

**Diagnostic:** Check that the auth store is properly initializing on app load. The `router/index.ts` navigation guard calls `authStore.initialize()` before each route.

**Fix:** Verify the auth store's `initialize()` method calls `supabase.auth.getSession()` to restore the session from local storage.

---

## File Upload Failures

**Symptom:** File upload returns an error or the file does not appear in the system.

### Step 1: Check the Upload Endpoint Response

Use browser Developer Tools (Network tab) or the FastAPI docs at `/docs` to test the upload endpoint directly.

```bash
# Test with curl
curl -X POST http://localhost:8000/api/files/upload \
  -F "file=@test.step" \
  -F "item_number=csp0030"
```

### Step 2: Item Does Not Exist

**Error:** `404: Item csp0030 not found`

**Fix:** The item must exist in the `items` table before files can be uploaded to it. Create the item first:

```bash
curl -X POST http://localhost:8000/api/items \
  -H "Content-Type: application/json" \
  -d '{"item_number": "csp0030", "name": "CSP0030"}'
```

Or use the upload bridge with `upsert=true` to auto-create items.

### Step 3: Supabase Storage Bucket Missing

**Error:** `StorageApiError: Bucket not found`

**Fix:** Create the `pdm-files` bucket in the Supabase Dashboard:

1. Go to Supabase Dashboard -> Storage
2. Click "New bucket"
3. Name: `pdm-files`
4. Set public/private as needed (private recommended, use signed URLs)

### Step 4: File Size Limit

**Error:** `413 Request Entity Too Large` or Supabase storage size error.

**Fix:** Supabase free tier has a file size limit (default 50MB). For larger files:

1. Check Supabase project settings for storage limits
2. Consider compressing files before upload
3. Upgrade Supabase plan if needed

### Step 5: Duplicate File in Storage

**Error:** `The resource already exists`

The upload endpoint handles this by falling back to an update operation. If this error persists, check that the exception handling in `files.py` is catching the correct error string.

### Step 6: RLS on Storage

**Symptom:** Upload succeeds in the API but storage operation fails silently.

**Fix:** The file upload endpoint should use `get_supabase_admin()` to bypass RLS for storage operations. Verify this is the case in `backend/app/routes/files.py`.

---

## BOM Upload Issues

**Symptom:** BOM data is not appearing in the system or the upload returns errors.

### Step 1: Check BOM Endpoint Response

```bash
curl -X POST http://localhost:8000/api/bom/bulk \
  -H "Content-Type: application/json" \
  -d '{
    "parent_item_number": "sta01000",
    "children": [
      {"item_number": "stp01000", "quantity": 7}
    ]
  }'
```

### Step 2: BOM Parser Not Finding Items

**Symptom:** Upload bridge runs but no BOM data is uploaded.

**Diagnostic:** Check the BOM text file format. The parser expects specific column headers from Creo BOM exports.

**Fix:** Verify the BOM file matches the expected format in `PDM-BOM-Parser.ps1`. Check the parser output for error messages.

### Step 3: Circular Reference Protection

**Symptom:** BOM tree endpoint returns incomplete data.

The tree endpoint has a `max_depth` parameter (default 10) to prevent infinite recursion. If your BOM is deeper than 10 levels, increase this parameter:

```
GET /api/bom/{item_number}/tree?max_depth=20
```

### Step 4: Reference Items (zzz prefix)

**Symptom:** Some BOM children are not created.

This is expected behavior. Items with the `zzz` prefix are reference-only and are intentionally skipped during BOM upload. See `backend/app/routes/bom.py` bulk upload logic.

### Step 5: Incorrect BOM Quantities in MRP Project Parts

**Symptom:** MRP Dashboard shows incorrect quantities for parts (e.g., vinyl decal shows 16 needed instead of 12).

**Root Cause:** Stale BOM export data from CAD system. The MLBOM.txt file has outdated quantity data that doesn't match the current CAD assembly structure.

**Example Case (WM_0513):**
- MRP Dashboard showed `stp00260` (vinyl decal) quantity as 16
- CAD assembly (`STA01080`) only has 1 instance of `JBA00020` (FRONT COVER)
- Stale MLBOM export had `STA01080 → JBA00020` with quantity 2 (should be 1)
- BOM parser counted duplicates and multiplied: 2 × 2 × 4 = 16 instead of 1 × 2 × 4 = 8

**Diagnostic Steps:**

1. **Check BOM data in database:**

```sql
SELECT parent_item_id, child_item_id, quantity, source_file
FROM bom
WHERE parent_item_id IN (
  SELECT id FROM items WHERE item_number = 'sta01080'
)
AND child_item_id IN (
  SELECT id FROM items WHERE item_number = 'jba00020'
);
```

Expected result: quantity should match CAD assembly structure.

2. **Verify in CAD assembly:**
   - Open the parent assembly in Creo Parametric
   - Check how many instances of the child part exist (Model Tree)
   - Compare with BOM quantity in database

3. **Check MLBOM export timestamp:**
   - Look at `source_file` field in BOM records
   - Verify when MLBOM.txt was last exported from CAD
   - If old, re-export is needed

**How BOM Upload Works:**

The BOM upload pipeline (`scripts/pdm-upload/`) uses a full-replacement strategy:

1. **Parse MLBOM.txt** (`PDM-BOM-Parser.ps1`):
   - Uses indentation to detect parent-child relationships
   - Counts duplicate child entries under same parent
   - Increments quantity for each duplicate found

2. **Upload to API** (`PDM-Upload-Functions.ps1` → `/api/bom/bulk`):
   - Backend endpoint (`backend/app/routes/bom.py` line ~197)
   - **DELETES** all existing BOM entries for the parent
   - **INSERTS** new BOM entries from parsed data
   - This ensures a clean update with no stale data carryover

3. **MRP Parts Rollup** (`frontend/src/views/MrpDashboardView.vue`):
   - `explodeBomRecursive()` function (lines 657-687) traverses BOM tree
   - Multiplies quantities at each level to calculate total needed
   - Inserts results into `mrp_project_parts` table (is_manual=false)

**Resolution Steps:**

1. **Re-export MLBOM from CAD:**
   - Open top-level assembly in Creo Parametric
   - Tools → Table → Tree
   - Include columns: Model Name, DESCRIPTION, PROJECT, PRO_MP_MASS, PTC_MASTER_MATERIAL, CUT_LENGTH, SMT_THICKNESS, CUT_TIME, PRICE_EST
   - Save as `MLBOM.txt`

2. **Re-upload via PowerShell scripts:**
   - Ensure PDM Upload Service is running
   - Copy `MLBOM.txt` to `C:\PDM-Upload`
   - Service automatically parses and uploads to `/api/bom/bulk`
   - Check log for success: `SUCCESS: Uploaded BOM - Parent: wma20120, Children: 15`

3. **Update MRP project parts:**
   - Open MRP Dashboard for the project
   - Navigate to **Assemblies** section
   - Click **Update** button next to affected assembly
   - This triggers `updateBom()` function (line 494):
     - Deletes BOM-derived parts (is_manual=false)
     - Re-explodes assembly with new BOM data
     - Inserts corrected quantities into mrp_project_parts

4. **Verify corrected quantities:**
   - Check MRP Dashboard parts list
   - Confirm quantities match CAD assembly structure
   - If still incorrect, check for circular BOM references or missing parts

**Prevention:**

- Always re-export MLBOM when making assembly changes in CAD
- Use version control or timestamps on MLBOM exports to track staleness
- The BOM upload process is safe to re-run (full replacement, idempotent)
- MRP Dashboard "Update" button is a cache refresh trigger (always safe to click)

**See Also:**
- `Documentation/05-POWERSHELL-SCRIPTS-INDEX.md` -- BOM parser details
- `Documentation/20-COMMON-WORKFLOWS.md` -- Section 4: Uploading a BOM

---

## Database Connection Problems

**Symptom:** API returns 500 errors related to database operations.

### Step 1: Verify Supabase Project Status

1. Go to https://supabase.com/dashboard
2. Select your project
3. Check the project status indicator (should show "Healthy")
4. If paused (free tier), click "Restore" to restart

### Step 2: Check API Keys

**Symptom:** `AuthApiError` or `Invalid API key`.

**Diagnostic:**

1. Go to Supabase Dashboard -> Settings -> API
2. Copy the correct URL, anon key, and service role key
3. Update `backend/.env` with the correct values
4. Restart uvicorn

### Step 3: Table Does Not Exist

**Error:** `relation "items" does not exist`

**Fix:** Run the database migrations. Check the Supabase SQL Editor and verify tables exist. If migrating from scratch, apply the schema from the migration plan.

### Step 4: Check Supabase Logs

1. Go to Supabase Dashboard -> Logs
2. Select "Postgres" or "API" logs
3. Filter for errors in the relevant time range
4. Look for connection pool exhaustion, query timeouts, or permission errors

### Step 5: Query Timeout

**Symptom:** Slow responses or timeout errors on complex queries (especially BOM tree).

**Fix:** The recursive BOM tree query makes multiple Supabase calls. For deep trees, this can be slow. Consider:

- Reducing `max_depth`
- Implementing server-side caching
- Using a PostgreSQL recursive CTE query instead of multiple API calls

---

## Data Issues

**Symptom:** Incorrect data in the database, missing items, or inconsistent records.

### Step 1: Routing Badge Shows "No Routing" When Routing Exists

**Symptom:** MRP routing view shows "No routing" for items that have routing entries in the database.

**Cause:** Supabase has a 1000-row query limit. If the routing table has >1000 rows, queries that fetch all routing data will be truncated, causing items beyond row 1000 to show as "No routing".

**Fix:** The system now uses an RPC function `get_routing_counts()` to bypass this limit. If you see this issue:

1. Check routing table size: `SELECT COUNT(*) FROM routing`
2. If >1000 rows, verify the RPC function exists: `SELECT * FROM get_routing_counts() LIMIT 5`
3. If function doesn't exist, apply migration `add_routing_counts_function`

**See:** Development Notes pitfall #40 for full details.

---

### Step 2: Verify Item Number Format

Item numbers must match the pattern `[a-z]{3}\d{4,6}` (3 lowercase letters + 4-6 digits).

**Check in Supabase SQL Editor:**

```sql
SELECT item_number FROM items
WHERE item_number !~ '^[a-z]{3}\d{4,6}$'
ORDER BY item_number;
```

This should return no rows. Any results indicate invalid item numbers.

### Step 3: Check for Duplicate Items

```sql
SELECT item_number, COUNT(*) as cnt
FROM items
GROUP BY item_number
HAVING COUNT(*) > 1;
```

The `item_number` column has a unique constraint, so true duplicates should not exist. If you see this error during inserts, the upsert logic should handle it.

### Step 4: Orphaned Files

Files linked to deleted items:

```sql
SELECT f.id, f.file_name, f.item_id
FROM files f
LEFT JOIN items i ON f.item_id = i.id
WHERE i.id IS NULL;
```

### Step 5: Orphaned BOM Entries

BOM entries referencing deleted items:

```sql
SELECT b.id, b.parent_item_id, b.child_item_id
FROM bom b
LEFT JOIN items p ON b.parent_item_id = p.id
LEFT JOIN items c ON b.child_item_id = c.id
WHERE p.id IS NULL OR c.id IS NULL;
```

### Step 6: Check items vs files Consistency

Every file should have a valid `item_id`:

```sql
SELECT f.file_name, f.item_id
FROM files f
WHERE f.item_id NOT IN (SELECT id FROM items);
```

---

## DXF/SVG Generation Issues

**Symptom:** DXF or SVG generation fails or produces incorrect output.

### DXF Generation Crashes with "Line through identical points"

**Error:** `Part.OCCError: Line through identical points` in FreeCAD worker logs.

**Cause:** The STEP file contains degenerate geometry (zero-length edges, zero-radius arcs, or coincident points). This can happen when:
- CAD model has sharp corners that export as zero-radius arcs
- Boolean operations create collapsed edges
- Surface intersections produce tiny slivers
- STEP import/export introduces duplicate vertices

**Fix:** The system now skips zero-length edges automatically. If you see this error:

1. Check FreeCAD worker logs: `docker logs pdm-freecad-worker`
2. Look for "Skipping degenerate arc edge" or "Skipping zero-length segment" messages
3. If DXF generation still fails, the STEP file may need geometry cleanup in CAD

**Workaround:** Re-export STEP file from CAD with geometry repair option enabled.

**See:** Development Notes pitfall #41 for technical details.

---

## Upload Bridge Problems

**Symptom:** The local PowerShell upload scripts are not sending data to the API.

### Step 1: Verify API Connectivity

```powershell
# Test API health
Invoke-RestMethod -Uri "http://localhost:8000/health"
# Should return: @{status=healthy}
```

If this fails, the backend is not running or the URL is wrong. See [Backend Not Starting](#backend-not-starting).

### Step 2: Check Upload Configuration

Review `scripts/pdm-upload/PDM-Upload-Config.ps1` for the correct API URL and watched folders.

### Step 3: Check Upload Service Logs

Run the upload service manually to see output:

```powershell
cd scripts\pdm-upload
.\PDM-Upload-Service.ps1
```

Watch for error messages about file processing, API calls, or authentication.

### Step 4: File Naming Issues

The upload bridge extracts item numbers from filenames. Filenames must start with a valid item number (3 letters + 4-6 digits).

**Valid:** `csp0030.step`, `wma20120_flat.dxf`
**Invalid:** `part1.step`, `test-file.step`, `CSP0030.step` (uppercase)

### Step 5: BOM Parser Issues

If BOM files are not being processed, check:

1. The BOM text file is in the expected format
2. The watched folder path is correct in the configuration
3. The API URL for the bulk BOM endpoint is reachable

```powershell
# Test BOM endpoint directly
$body = @{
    parent_item_number = "sta01000"
    children = @(
        @{ item_number = "stp01000"; quantity = 1 }
    )
} | ConvertTo-Json -Depth 3

Invoke-RestMethod -Uri "http://localhost:8000/api/bom/bulk" `
    -Method POST `
    -ContentType "application/json" `
    -Body $body
```

---

## Diagnostic Tools Reference

### Browser Developer Tools (F12)

- **Console tab:** JavaScript errors, Vue warnings, failed API responses
- **Network tab:** API request/response details, status codes, timing
- **Application tab:** Local Storage (auth tokens), cookies, service workers

### FastAPI Interactive Docs

- **Swagger UI:** `http://localhost:8000/docs` -- test any endpoint interactively
- **ReDoc:** `http://localhost:8000/redoc` -- read-only API documentation

### Supabase Dashboard

- **Table Editor:** Browse and edit data directly
- **SQL Editor:** Run ad-hoc queries for diagnostics
- **Logs:** API logs, Postgres logs, Auth logs
- **Storage:** Browse uploaded files, check bucket configuration
- **Auth:** User management, view active sessions

### FastAPI Logs

Uvicorn prints request logs to the terminal:

```
INFO:     127.0.0.1:52000 - "GET /api/items?limit=1000 HTTP/1.1" 200 OK
INFO:     127.0.0.1:52000 - "POST /api/files/upload HTTP/1.1" 404 Not Found
```

Look for non-200 status codes to identify failing endpoints.

### Health Check

```bash
curl http://localhost:8000/health
# Expected: {"status":"healthy"}
```

If this fails, the backend process is not running.

---

## Quick Diagnostic Checklist

When something is not working, run through this checklist:

1. **Backend running?** -- Check terminal for uvicorn output
2. **Frontend running?** -- Check terminal for Vite output
3. **`.env` file present?** -- Check `backend/.env` for Supabase credentials
4. **Supabase project active?** -- Check dashboard status
5. **Browser console errors?** -- F12 -> Console tab
6. **Network requests failing?** -- F12 -> Network tab
7. **CORS errors?** -- Set `CORS_ALLOW_ALL=true` in backend `.env`
8. **Auth token valid?** -- Try logging out and back in
9. **Admin client used where needed?** -- File upload and BOM bulk endpoints need `get_supabase_admin()`
10. **Item numbers lowercase?** -- Check all entry points normalize to lowercase

---

**Last Updated:** 2026-06-02
**Version:** 3.1
**Related:** [15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md](15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md), [18-GLOSSARY-TERMS.md](18-GLOSSARY-TERMS.md), [20-COMMON-WORKFLOWS.md](20-COMMON-WORKFLOWS.md)
