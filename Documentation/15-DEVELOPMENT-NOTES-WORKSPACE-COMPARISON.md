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

---

**Last Updated:** 2025-01-29
**Version:** 3.0
**Related:** [27-WEB-MIGRATION-PLAN.md](27-WEB-MIGRATION-PLAN.md), [24-VERSION-HISTORY.md](24-VERSION-HISTORY.md)
