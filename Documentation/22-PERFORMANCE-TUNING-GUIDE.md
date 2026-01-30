# PDM-Web - Performance Tuning Guide

**Optimization Strategies for the Web-Based PDM System**
**Related Docs:** [23-SYSTEM-CONFIGURATION.md](23-SYSTEM-CONFIGURATION.md), [21-BACKUP-RECOVERY-GUIDE.md](21-BACKUP-RECOVERY-GUIDE.md)

---

## Architecture Overview

PDM-Web has four performance-sensitive layers:

1. **Supabase PostgreSQL** -- Cloud-managed database with automatic optimization
2. **FastAPI Backend** -- Python API server (uvicorn in development, gunicorn in production)
3. **Vue 3 Frontend** -- Client-side SPA built with Vite
4. **Supabase Storage** -- Cloud file storage with signed URL access

Each layer has different tuning strategies. This guide covers practical optimizations for each.

---

## Supabase PostgreSQL Optimization

### Indexing Strategy

Supabase PostgreSQL supports standard PostgreSQL indexes. The following indexes are recommended for PDM-Web query patterns. Apply these through the Supabase SQL Editor or via a migration.

```sql
-- Item lookup by item_number (most frequent query)
CREATE INDEX IF NOT EXISTS idx_items_item_number ON items(item_number);

-- Item filtering by lifecycle state
CREATE INDEX IF NOT EXISTS idx_items_lifecycle_state ON items(lifecycle_state);

-- Item filtering by project
CREATE INDEX IF NOT EXISTS idx_items_project_id ON items(project_id);

-- Item text search (item_number, name)
CREATE INDEX IF NOT EXISTS idx_items_search
  ON items USING gin(to_tsvector('english', coalesce(item_number, '') || ' ' || coalesce(name, '')));

-- File lookup by item_id (loading files for an item detail view)
CREATE INDEX IF NOT EXISTS idx_files_item_id ON files(item_id);

-- BOM parent lookups (loading BOM for an assembly)
CREATE INDEX IF NOT EXISTS idx_bom_parent_item_id ON bom(parent_item_id);

-- BOM child lookups (where-used queries)
CREATE INDEX IF NOT EXISTS idx_bom_child_item_id ON bom(child_item_id);

-- Work queue status (pending task polling)
CREATE INDEX IF NOT EXISTS idx_work_queue_status ON work_queue(status);

-- Lifecycle history by item
CREATE INDEX IF NOT EXISTS idx_lifecycle_history_item_id ON lifecycle_history(item_id);

-- Checkouts by item
CREATE INDEX IF NOT EXISTS idx_checkouts_item_id ON checkouts(item_id);
```

### Query Pattern Optimization

**Select only needed columns.** The Supabase client and backend code should specify columns rather than using `select("*")` when possible. This reduces data transfer and memory usage.

```python
# Less efficient -- fetches all columns
result = supabase.table("items").select("*").eq("item_number", "csp0030").execute()

# More efficient -- fetches only what the list view needs
result = supabase.table("items").select(
    "id, item_number, name, lifecycle_state, revision, iteration, project_id"
).eq("lifecycle_state", "Design").execute()
```

**Use pagination.** The items API already supports `limit` and `offset` parameters. Avoid loading the full item table at once when the dataset grows large.

```
GET /api/items?limit=50&offset=0
GET /api/items?limit=50&offset=50
```

**Optimize BOM tree queries.** The recursive BOM tree endpoint (`/api/bom/{item_number}/tree`) makes multiple database round-trips. For deeply nested BOMs, consider:

- Setting a reasonable `max_depth` parameter (default is 10)
- Caching BOM tree results for assemblies that change infrequently
- Using PostgreSQL recursive CTEs for server-side tree resolution if performance becomes an issue:

```sql
-- Example recursive CTE for BOM tree (server-side)
WITH RECURSIVE bom_tree AS (
    SELECT b.child_item_id, b.quantity, 1 AS depth
    FROM bom b
    WHERE b.parent_item_id = '<parent-uuid>'
    UNION ALL
    SELECT b.child_item_id, b.quantity, bt.depth + 1
    FROM bom b
    JOIN bom_tree bt ON b.parent_item_id = bt.child_item_id
    WHERE bt.depth < 10
)
SELECT i.*, bt.quantity, bt.depth
FROM bom_tree bt
JOIN items i ON i.id = bt.child_item_id
ORDER BY bt.depth, i.item_number;
```

### Database Monitoring

Use the Supabase Dashboard to monitor query performance:

1. Navigate to **Database > Query Performance** (available on Pro plan)
2. Identify slow queries by execution time
3. Use `EXPLAIN ANALYZE` in the SQL Editor to inspect query plans:

```sql
EXPLAIN ANALYZE
SELECT * FROM items
WHERE item_number ILIKE '%csp%'
ORDER BY item_number;
```

4. Check for sequential scans on large tables -- these indicate missing indexes
5. Monitor connection count under **Settings > Database** to ensure you are not exhausting the connection pool

### Connection Pooling

Supabase provides PgBouncer connection pooling. The backend's Supabase Python client handles connection management automatically. For production deployments with high concurrency:

- Use the **pooled connection string** (port 6543) rather than the direct connection string (port 5432) for any direct database access
- The Supabase client library uses the REST API by default, which is pooled at the API gateway level

---

## FastAPI Backend Optimization

### Async Request Handling

FastAPI supports async handlers natively. All route handlers in PDM-Web are already declared with `async def`, which allows uvicorn to handle concurrent requests efficiently. Ensure any new routes follow this pattern:

```python
# Correct -- non-blocking
@router.get("/items")
async def list_items():
    result = supabase.table("items").select("*").execute()
    return result.data

# Avoid -- blocks the event loop (only if using synchronous I/O libraries)
@router.get("/items")
def list_items():
    result = supabase.table("items").select("*").execute()
    return result.data
```

Note: The Supabase Python client uses `httpx` internally, which supports both sync and async modes. The current implementation uses synchronous calls within async handlers. For high-load scenarios, consider switching to the async Supabase client.

### Production Server Configuration

**Development (uvicorn):**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

**Production (gunicorn with uvicorn workers):**
```bash
gunicorn app.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers 4 \
  --bind 0.0.0.0:8080 \
  --timeout 120
```

**Worker count guidelines:**
- Formula: `(2 * CPU_CORES) + 1`
- For a 2-core server: 5 workers
- For a single-core server (Fly.io free tier): 2 workers
- Monitor memory usage -- each worker uses approximately 50-100 MB

### Supabase Client Caching

The backend uses `@lru_cache` to cache Supabase client instances, avoiding re-initialization on every request:

```python
# backend/app/services/supabase.py
@lru_cache
def get_supabase_client() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_anon_key)

@lru_cache
def get_supabase_admin() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_key)
```

This is correct and should not be changed. The `@lru_cache` decorator ensures only one client instance is created per process.

### Request Validation

Pydantic schemas in `backend/app/models/schemas.py` provide automatic request validation. This is both a security feature and a performance feature -- invalid requests are rejected immediately without hitting the database.

```python
class ItemBase(BaseModel):
    item_number: str = Field(..., pattern=r"^[a-z]{3}\d{4,6}$")
    # Regex validation prevents malformed item numbers from reaching the database
```

### Upload Performance

File uploads go through the FastAPI backend to Supabase Storage. For large files:

- The backend reads the entire file into memory before uploading (`content = await file.read()`)
- For files larger than 50 MB, consider streaming the upload or increasing the server timeout
- The upload bridge script (`scripts/pdm-upload/`) processes files sequentially, which is appropriate for its use case

---

## Vue Frontend Optimization

### Vite Build Optimization

Vite provides fast development with Hot Module Replacement (HMR) and optimized production builds by default.

**Development:**
```bash
cd frontend && npm run dev
# Starts on port 5174 with HMR
```

**Production build:**
```bash
cd frontend && npm run build
# Outputs optimized static files to dist/
```

Vite automatically performs:
- Tree shaking (removes unused code)
- Code splitting (loads routes on demand)
- Asset minification (CSS, JavaScript)
- Content hashing (cache-busting filenames)

### Lazy Loading Routes

For larger applications, use dynamic imports to lazy-load route components. This reduces the initial bundle size.

```typescript
// Eager loading (loads everything upfront)
import ItemBrowser from '../views/ItemBrowser.vue'
import ItemDetail from '../views/ItemDetail.vue'

// Lazy loading (loads on navigation)
const ItemBrowser = () => import('../views/ItemBrowser.vue')
const ItemDetail = () => import('../views/ItemDetail.vue')
```

### Pinia Store Caching

The items store (`frontend/src/stores/items.ts`) caches fetched items in a reactive `ref`. This means navigating between the item list and item detail view does not require re-fetching data.

**Current caching behavior:**
- `items` ref holds the last-fetched list of items
- `currentItem` ref holds the currently viewed item with its files
- Data is re-fetched on explicit user actions (search, filter change, navigation)

**Optimization strategies for growing datasets:**

1. **Debounce search input** to reduce API calls during typing:
   ```typescript
   import { useDebounceFn } from '@vueuse/core'

   const debouncedFetch = useDebounceFn((query: string) => {
     fetchItems({ q: query })
   }, 300)
   ```

2. **Cache item detail views** to avoid re-fetching when navigating back:
   ```typescript
   const itemCache = new Map<string, Item>()

   async function fetchItem(itemNumber: string) {
     if (itemCache.has(itemNumber)) {
       currentItem.value = itemCache.get(itemNumber)!
       return
     }
     // ... fetch from Supabase
     itemCache.set(itemNumber, data)
   }
   ```

3. **Use pagination** in the item list view instead of loading all items at once

### Direct Supabase Queries

The frontend uses the Supabase JavaScript client directly for most data operations (items store, storage service). This is efficient because:

- Queries go directly from the browser to Supabase's PostgREST API
- No extra hop through the FastAPI backend for standard CRUD operations
- Supabase handles connection pooling and query optimization at the gateway level

The FastAPI backend is used for:
- Authentication verification (`/api/auth/me`)
- Operations requiring the service role key (file uploads via the bridge script, bulk BOM operations)
- Complex business logic

### Browser Caching

Supabase Storage supports cache headers. The frontend storage service sets `cacheControl: '3600'` on uploads:

```typescript
const { data, error } = await supabase.storage
  .from(bucket)
  .upload(path, file, {
    cacheControl: '3600',  // 1 hour browser cache
    upsert: true
  })
```

For frequently accessed files (drawings, PDFs), this means subsequent views will use the browser cache rather than re-downloading.

---

## Supabase Storage Performance

### Signed URLs

The application uses signed URLs for file access. Signed URLs are generated server-side and are valid for a configurable duration (default: 1 hour / 3600 seconds).

```typescript
// frontend/src/services/storage.ts
export async function getSignedUrl(
  bucket: BucketName,
  path: string,
  expiresIn: number = 3600
): Promise<string | null> {
  const { data, error } = await supabase.storage
    .from(bucket)
    .createSignedUrl(path, expiresIn)
  return data?.signedUrl ?? null
}
```

**Performance considerations:**
- Generate signed URLs on demand, not in bulk (they are fast to create)
- Cache signed URLs client-side for the duration of their validity
- For PDF viewers and image previews, the signed URL serves content directly from Supabase's CDN

### Storage Bucket Organization

Files are organized by item number and revision:

```
{bucket}/{item_number}/{revision}/{iteration}/{filename}
```

Example: `pdm-exports/csp0030/A/1/csp0030.step`

This structure supports efficient listing by item and avoids flat directory performance issues.

### Upload Performance

For the upload bridge script (`scripts/pdm-upload/`), files are processed sequentially:

1. File detected in `C:\PDM-Upload`
2. File uploaded to FastAPI backend via HTTP multipart form
3. Backend uploads to Supabase Storage
4. Database record created/updated

For bulk operations (large BOM uploads, many files at once), the sequential processing ensures reliability over raw speed. The 3-second delay in the file watcher is intentional to allow CAD software to finish writing files.

---

## Monitoring and Diagnostics

### Supabase Dashboard Metrics

The Supabase Dashboard provides built-in monitoring:

- **Database:** Query performance, active connections, storage usage
- **Auth:** Login attempts, active sessions, failed authentications
- **Storage:** Bandwidth usage, storage capacity
- **API:** Request counts, error rates, response times

Navigate to your project at https://supabase.com/dashboard to access these metrics.

### FastAPI Built-in Docs

The backend exposes interactive API documentation:

- **Swagger UI:** `http://localhost:8001/docs` (development)
- **ReDoc:** `http://localhost:8001/redoc` (development)
- **Health check:** `http://localhost:8001/health`

Use the Swagger UI to test individual endpoints and measure response times.

### Frontend Developer Tools

Use browser developer tools to monitor frontend performance:

- **Network tab:** Monitor API call frequency, payload sizes, and response times
- **Performance tab:** Profile component render times
- **Vue DevTools:** Inspect Pinia store state, component hierarchy, and reactivity

---

## Performance Checklist

### Initial Deployment

- [ ] Apply recommended database indexes (see SQL above)
- [ ] Configure production gunicorn worker count appropriately
- [ ] Build frontend with `npm run build` (not dev mode)
- [ ] Verify Supabase project is on an appropriate plan for expected load

### Ongoing Monitoring

- [ ] Check Supabase Dashboard for slow queries monthly
- [ ] Monitor database storage usage (Supabase free tier: 500 MB)
- [ ] Monitor file storage usage (Supabase free tier: 1 GB)
- [ ] Review API response times for degradation
- [ ] Check frontend bundle size after adding new dependencies

### When Performance Degrades

1. Check Supabase Dashboard for connection count spikes or slow queries
2. Run `EXPLAIN ANALYZE` on suspected slow queries
3. Review backend logs for error patterns or timeouts
4. Check browser network tab for failed or slow API calls
5. Verify indexes exist on frequently queried columns
6. Consider upgrading Supabase plan if hitting resource limits

---

**Last Updated:** 2025-01-29
**Version:** 3.0
**Related:** [23-SYSTEM-CONFIGURATION.md](23-SYSTEM-CONFIGURATION.md), [21-BACKUP-RECOVERY-GUIDE.md](21-BACKUP-RECOVERY-GUIDE.md)
