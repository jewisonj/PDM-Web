# Technical Debt Audit - PDM-Web

**Date:** 2026-01-30
**Scope:** Full codebase review - frontend, backend, database usage, deployment
**Focus:** Technical debt, AI-generated code smells, performance, Fly.io resource usage

---

## Executive Summary

The codebase is **functionally working but operationally fragile**. The main risks fall into four categories:

| Category | Critical | High | Medium | Low |
|----------|----------|------|--------|-----|
| Security & Auth | 2 | 2 | 3 | 0 |
| Performance (N+1, memory) | 2 | 5 | 4 | 0 |
| Code Quality & Debt | 0 | 4 | 6 | 3 |
| Deployment & Ops | 1 | 2 | 4 | 2 |
| **Totals** | **5** | **13** | **17** | **5** |

---

## TIER 1 - CRITICAL (Fix Before Production)

### C1. Missing Authentication on Public Endpoints

**Files:** `backend/app/routes/auth.py:67`, `items.py:13`, `projects.py:13`, `files.py:68`

Multiple endpoints have no auth checks. Any unauthenticated client can read all items, projects, files, and users.

```python
# auth.py:67 - Docstring says "admin only" but nothing enforces it
@router.get("/users", response_model=list[User])
async def list_users():
    """List all users (admin only in production)."""
    result = supabase.table("users").select("*").order("username").execute()
    return result.data
```

**Fix:** Add a `get_current_user` dependency to all route functions. Create a shared dependency:
```python
async def get_current_user(authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    user = supabase.auth.get_user(token)
    if not user: raise HTTPException(401)
    return user
```

---

### C2. `.env` Files Contain Real Credentials in Git Working Tree

**Files:** `backend/.env`, `frontend/.env`

Both contain actual Supabase URLs, anon keys, and the backend has the **service key** (full admin access). If this repo is ever shared or made public, credentials are exposed.

**Fix:**
```bash
# Add to .gitignore (verify they're already there, then clean working tree)
echo "backend/.env" >> .gitignore
echo "frontend/.env" >> .gitignore
```
Rotate Supabase keys if this repo has ever been pushed to a remote.

---

### C3. N+1 Query in MRP Dashboard - 100+ Queries Per Project Load

**File:** `frontend/src/views/MrpDashboardView.vue:182-209`

When loading project parts, the code runs a **separate Supabase query for each part** to get routing times and BOM counts:

```typescript
const partsWithRouting = await Promise.all((data || []).map(async (pp: any) => {
  // Query 1 per part: get routing
  const { data: routingData } = await supabase
    .from('routing').select('est_time_min').eq('item_id', pp.item_id)

  // Query 2 per part: check if assembly
  const { count: bomCount } = await supabase
    .from('bom').select('*', { count: 'exact', head: true }).eq('parent_item_id', pp.item_id)
}))
```

**Impact:** 50-part project = 100 extra queries. Visible as 2-5 second load times.

**Fix:** Batch-fetch all routing and BOM counts in two bulk queries before the map:
```typescript
const itemIds = data.map(pp => pp.item_id)
const { data: allRouting } = await supabase
  .from('routing').select('item_id, est_time_min').in('item_id', itemIds)
const { data: allBom } = await supabase
  .from('bom').select('parent_item_id').in('parent_item_id', itemIds)
// Then look up from maps instead of querying in loop
```

---

### C4. Recursive N+1 in BOM Tree Builder

**File:** `backend/app/routes/bom.py:40-67`

The `build_tree()` function queries each child item individually, then recurses. A 3-level BOM with 10 children per level = **72+ queries** instead of 2-3.

```python
for entry in bom_result.data:
    child_result = supabase.table("items").select("*").eq("id", entry["child_item_id"]).single().execute()
    children.append(build_tree(entry["child_item_id"], depth + 1))  # Recursive
```

**Fix:** Use an iterative approach: collect all child IDs at each level, batch-fetch them, then assemble the tree in memory.

---

### C5. File Upload Buffers Entire File in Memory

**File:** `backend/app/routes/files.py:137-138`

```python
content = await file.read()  # Loads ENTIRE file into RAM
file_size = len(content)
```

No size limit check. On Fly.io with 512MB RAM, a 300MB STEP file will OOM the server.

**Fix:** Add a max file size check (e.g., 100MB) and return 413 if exceeded. For larger files, implement chunked upload or use Supabase presigned URLs for direct-to-storage upload from the frontend.

---

## TIER 2 - HIGH (Fix Soon, Performance/Reliability Impact)

### H1. CORS Allows All Origins If Env Var Set

**File:** `backend/app/main.py:34-41`

```python
allow_origins=["*"] if settings.cors_allow_all else settings.cors_origins,
```

The `CORS_ALLOW_ALL` env var defaults to `false` but can be flipped. This combined with `allow_credentials=True` is a dangerous combination. Consider removing the `allow_all` option entirely, or at least disabling credentials when origins are wildcarded.

---

### H2. Health Check Is a Stub

**File:** `backend/app/main.py:55-58`

```python
@app.get("/health")
async def health():
    return {"status": "healthy"}  # Always returns healthy
```

Fly.io uses this to determine if the instance is alive. If Supabase is down, the app reports healthy but can't serve any data.

**Fix:** Add a lightweight Supabase connectivity check:
```python
@app.get("/health")
async def health():
    try:
        supabase = get_supabase_client()
        supabase.table("projects").select("id").limit(1).execute()
        return {"status": "healthy"}
    except Exception:
        raise HTTPException(503, detail="Database unreachable")
```

---

### H3. No Static Asset Caching or Compression

**File:** `backend/app/main.py:64-93`

FastAPI serves frontend assets with **no Cache-Control headers and no gzip compression**. Every page load re-downloads all JS/CSS bundles (300-400KB uncompressed).

**Fix:**
1. Add `GzipMiddleware` to FastAPI (saves ~60-70% bandwidth)
2. Set `Cache-Control: max-age=31536000, immutable` for `/assets/*` (Vite hashes filenames)

```python
from starlette.middleware.gzip import GzipMiddleware
app.add_middleware(GzipMiddleware, minimum_size=1000)
```

---

### H4. Item Number Validation Schema Rejects Valid Items

**File:** `backend/app/models/schemas.py:58`

```python
item_number: str = Field(..., pattern=r"^[a-z]{3}\d{4,6}$")
```

This only accepts `abc1234` format, but the system has McMaster items like `mmc93337a110` and supplier items like `spnca3102e14s-2pb` which contain alphanumeric suffixes and dashes. The schema will reject valid items on POST.

**Fix:** Widen the pattern to match actual usage:
```python
item_number: str = Field(..., pattern=r"^[a-z]{3}[a-z0-9\-]+$")
```

---

### H5. Bare Exception Handling Throughout Backend

**Files:** `backend/app/routes/files.py:155`, `auth.py:61`, `auth.py:110`, `services/print_packet.py:166`

```python
except Exception as e:
    if "already exists" in str(e).lower():  # String matching on exceptions
        # ...
    else:
        raise HTTPException(500, detail=f"Storage error: {str(e)}")
```

This catches `MemoryError`, `SystemExit`, `KeyboardInterrupt`, etc. Error messages expose internal details.

**Fix:** Catch specific exception types. Use generic error messages for users, log details server-side.

---

### H6. Frontend Components Are 2000+ Lines

**Files:**
- `MrpDashboardView.vue` - **2565 lines** (project CRUD + assemblies + parts + nesting + costs + print packets)
- `MrpRoutingView.vue` - **2369 lines** (item search + routing CRUD + cost calc + material + PDF)

These are AI-generated monoliths. Each view handles 5-7 distinct responsibilities. They're hard to maintain, hard to test, and cause long initial parse times.

**Fix:** Extract into composables and sub-components:
- `MrpDashboardView` -> `ProjectsPanel`, `PartsTable`, `NestingPanel`, `CostPanel`
- `MrpRoutingView` -> `ItemSelector`, `RoutingTable`, `MaterialAssigner`, `PdfPreview`

---

### H7. Client-Side Filtering of 1000 Items on Every Keystroke

**File:** `frontend/src/views/ItemsView.vue:42-79, 97`

```typescript
itemsStore.fetchItems({ limit: 1000 })  // Fetch ALL items upfront

const filteredItems = computed(() => {
  let result = [...itemsStore.items]  // Copy entire array
  // Filter + sort on every reactive change
})
```

With 1000 items, this re-runs on every keystroke, filter change, or sort toggle. The search input doesn't even debounce (`@vueuse/core` is imported for `useDebounceFn` but never actually used).

**Fix:**
1. Implement server-side filtering/search via API
2. Add debounce to search input (300ms)
3. Use virtual scrolling for large lists

---

### H8. N+1 Query in MRP Part Lookup

**File:** `frontend/src/views/MrpPartLookupView.vue:142-195`

Same pattern as C3 - loops through parts and fires a separate routing query for each one.

**Fix:** Same approach - batch-fetch routing data before the loop.

---

## TIER 3 - MEDIUM (Address During Normal Development)

### M1. No Structured Logging in Backend

**Files:** `backend/app/routes/files.py:117`, `207` and others

Backend uses `print()` statements instead of Python's logging module. No log levels, no timestamps, no request IDs. Fly.io captures stdout but you can't filter or aggregate.

**Fix:** Replace `print()` with `logging.info()` / `logging.error()`. Add a logging config in `main.py`.

---

### M2. Missing Security Headers

**File:** `backend/app/main.py`

No `X-Frame-Options`, `X-Content-Type-Options`, `Strict-Transport-Security`, or `Content-Security-Policy` headers. Fly.io handles HTTPS but these headers provide defense-in-depth.

**Fix:** Add a simple middleware:
```python
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
```

---

### M3. SELECT * Everywhere (28+ Instances)

**Files:** Throughout frontend views and backend routes

Nearly every Supabase query uses `.select("*")` instead of selecting specific columns. This wastes bandwidth and can leak fields not needed by the UI.

**Fix:** Audit each query and specify only needed columns. Priority: high-frequency queries like items list, routing, cost estimates.

---

### M4. No Transactions in Bulk BOM Upload

**File:** `backend/app/routes/bom.py:130-200`

The bulk BOM operation: (1) creates parent item, (2) creates child items, (3) deletes old BOM entries, (4) inserts new ones. If step 3 succeeds but step 4 fails, the BOM is orphaned with zero entries.

**Fix:** Wrap in a Supabase RPC function that runs as a single transaction, or implement compensating logic.

---

### M5. Missing Database Indexes for MRP Queries

Common queries filter on columns that likely lack indexes:

- `routing(item_id)` - used in every cost calculation
- `routing_materials(item_id)` - used in print packets
- `mrp_project_parts(project_id)` - used in dashboard, nesting
- `files(file_type, item_id)` - compound index for "find PDF for item"

**Fix:** Add indexes via Supabase migration.

---

### M6. Frontend Queries Bypass Backend for Some Tables

Tables like `cost_settings`, `raw_materials`, and `workstations` are queried directly from the frontend AND from the backend. When the frontend updates `cost_settings`, the backend's cached cost calculations don't reflect the change until restart.

**Fix:** Route all writes through the API. Frontend reads can remain direct for low-latency, but writes should go through backend to maintain consistency.

---

### M7. Polling Every 3 Seconds Without Backoff

**File:** `frontend/src/views/MrpDashboardView.vue:840-849`

Nesting job polling hits the backend every 3 seconds. For multiple users or tabs, this multiplies.

**Fix:** Implement exponential backoff (3s -> 5s -> 10s -> 30s) or switch to Supabase Realtime subscription for job status changes.

---

### M8. Unused Dependencies

**File:** `frontend/package.json`

`@vueuse/core` (~100KB) is imported but `useDebounceFn` is defined and never called. The debounced fetch in `ItemsView.vue:88-94` is dead code.

**Fix:** Either implement the debounce properly or remove the dependency.

---

### M9. CSS Color Duplication Across MRP Views

Colors like `#059669`, `#374151`, `#1e293b` are repeated 50+ times across MRP view `<style>` blocks with no CSS variables.

**Fix:** Extract a shared `mrp-theme.css` with CSS custom properties.

---

### M10. Print Packet PDF Generation Loads All PDFs to Memory

**File:** `backend/app/services/print_packet.py:269-346`

For a 100-part project with 10-page PDFs each, this loads 1000 pages into memory simultaneously.

**Fix:** Process PDFs in smaller batches and write intermediate results to temp files.

---

## TIER 4 - LOW (Nice to Have)

### L1. Hardcoded Supabase URL in config.py
Default URL is hardcoded. Not a problem if env var is always set, but fragile.

### L2. Login Endpoint Uses Query Params Instead of Request Body
`auth.py:76` takes `email` and `password` as query parameters on a POST endpoint.

### L3. Auth Token Handling Gets Fresh Session on Every API Call
`frontend/src/services/supabase.ts:45-75` calls `getSession()` on every `apiCall()`.

### L4. Frontend Build Skips TypeScript Checking
Dockerfile line 24 comments out type checking for faster builds. Could miss type errors.

### L5. Missing BOM Quantity Validation
`backend/app/routes/bom.py:256` accepts zero or negative quantities.

---

## Fly.io Resource Assessment

### Current Configuration (`fly.toml`)
```toml
[[vm]]
  memory = "512mb"
  cpu_kind = "shared"
  cpus = 1
```

### Memory Budget (512MB)
| Component | Estimate |
|-----------|----------|
| Python runtime | ~50MB |
| Uvicorn + FastAPI | ~30MB |
| Supabase client | ~20MB |
| Static file serving | ~10MB |
| **Baseline** | **~110MB** |
| Available for requests | **~400MB** |

**Risk areas:**
- File upload (currently buffers entire file): 100MB file = 100MB RAM spike
- Print packet generation: 50-part project = ~200MB for PDF assembly
- Concurrent requests: 5 simultaneous users doing different things could exceed budget

### Recommendations
1. **Keep 512MB** for now if file uploads are capped at ~50MB
2. **Bump to 1GB** if large STEP files (100MB+) will be uploaded
3. **Add GzipMiddleware** to reduce bandwidth (saves ~60% on static assets)
4. **Add Cache-Control headers** for `/assets/*` to eliminate repeat downloads
5. **CPU is fine** - workload is I/O-bound (Supabase REST calls)

### Docker Image Size
- Final image: ~220-240MB uncompressed, ~80-120MB compressed
- Acceptable for Fly.io (they cache layers)

---

## AI-Generated Code Smells

These patterns suggest AI assistance without sufficient human review:

1. **Copy-paste error handling** - Same try/catch pattern repeated 15+ times with slight variations instead of a shared utility
2. **Comments that contradict code** - `auth.py:67` says "admin only in production" but has no enforcement
3. **Dead code left in place** - `useDebounceFn` imported and defined but never called; `debouncedFetch` function exists but the watcher that should use it is empty
4. **Monolith views** - 2500-line single-file components that do everything. An AI will happily keep appending to the same file
5. **Inconsistent patterns** - Some API calls use `apiCall()` helper, others use raw `fetch()`, others query Supabase directly. Three different patterns for the same thing
6. **Over-fetching everywhere** - `SELECT *` on every query because it's the easiest thing to generate
7. **N+1 queries in loops** - `Promise.all(items.map(async item => { await query(item.id) }))` is a common AI pattern that looks clean but generates massive query counts

---

## Suggested Fix Order

Work through these in order. Each tier should be complete before moving to the next.

### Phase 1: Security & Stability (Tier 1)
1. Add auth middleware to all backend endpoints (C1)
2. Verify .env files are gitignored and credentials aren't in history (C2)
3. Add file size limit to upload endpoint (C5)
4. Fix N+1 in MRP Dashboard parts loading (C3)
5. Fix recursive N+1 in BOM tree builder (C4)

### Phase 2: Performance & Reliability (Tier 2)
6. Add GzipMiddleware and Cache-Control headers (H3)
7. Fix health check to verify Supabase connectivity (H2)
8. Implement server-side search/filter for items (H7)
9. Fix item number validation schema (H4)
10. Replace bare exception handlers (H5)
11. Fix N+1 in Part Lookup view (H8)

### Phase 3: Code Quality (Tier 3)
12. Add structured logging (M1)
13. Add security headers (M2)
14. Narrow SELECT * to specific columns on hot paths (M3)
15. Add missing database indexes (M5)
16. Extract large components into sub-components (H6)
17. Centralize CSS variables (M9)

### Phase 4: Polish (Tier 4 + remaining Medium)
18. Route all writes through API (M6)
19. Implement polling backoff (M7)
20. Remove unused dependencies (M8)
21. Add transactions to bulk BOM (M4)
22. Remaining low-priority items
