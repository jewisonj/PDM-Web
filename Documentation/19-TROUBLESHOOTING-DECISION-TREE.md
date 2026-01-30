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

### Step 1: Verify Item Number Format

Item numbers must match the pattern `[a-z]{3}\d{4,6}` (3 lowercase letters + 4-6 digits).

**Check in Supabase SQL Editor:**

```sql
SELECT item_number FROM items
WHERE item_number !~ '^[a-z]{3}\d{4,6}$'
ORDER BY item_number;
```

This should return no rows. Any results indicate invalid item numbers.

### Step 2: Check for Duplicate Items

```sql
SELECT item_number, COUNT(*) as cnt
FROM items
GROUP BY item_number
HAVING COUNT(*) > 1;
```

The `item_number` column has a unique constraint, so true duplicates should not exist. If you see this error during inserts, the upsert logic should handle it.

### Step 3: Orphaned Files

Files linked to deleted items:

```sql
SELECT f.id, f.file_name, f.item_id
FROM files f
LEFT JOIN items i ON f.item_id = i.id
WHERE i.id IS NULL;
```

### Step 4: Orphaned BOM Entries

BOM entries referencing deleted items:

```sql
SELECT b.id, b.parent_item_id, b.child_item_id
FROM bom b
LEFT JOIN items p ON b.parent_item_id = p.id
LEFT JOIN items c ON b.child_item_id = c.id
WHERE p.id IS NULL OR c.id IS NULL;
```

### Step 5: Check items vs files Consistency

Every file should have a valid `item_id`:

```sql
SELECT f.file_name, f.item_id
FROM files f
WHERE f.item_id NOT IN (SELECT id FROM items);
```

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

**Last Updated:** 2025-01-29
**Version:** 3.0
**Related:** [15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md](15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md), [18-GLOSSARY-TERMS.md](18-GLOSSARY-TERMS.md)
