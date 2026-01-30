# PDM-Web System - Integration and Extension Examples

**How to extend the PDM-Web system with new endpoints, views, schemas, and integrations**
**Related Docs:** [15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md](15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md), [18-GLOSSARY-TERMS.md](18-GLOSSARY-TERMS.md)

---

## Adding a New API Endpoint

### Example: Custom Cost Report Endpoint

To add a new endpoint to the FastAPI backend, create or extend a route module.

**Step 1: Define the Pydantic response schema** in `backend/app/models/schemas.py`:

```python
class CostReport(BaseModel):
    """Cost summary for an item and its BOM."""
    item_number: str
    name: Optional[str] = None
    price_est: Optional[float] = None
    file_count: int = 0
    bom_child_count: int = 0
    total_bom_cost: Optional[float] = None
```

**Step 2: Create the route** in a new file `backend/app/routes/reports.py`:

```python
"""Reports API routes."""

from fastapi import APIRouter, HTTPException
from ..services.supabase import get_supabase_client
from ..models.schemas import CostReport

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/cost/{item_number}", response_model=CostReport)
async def get_cost_report(item_number: str):
    """Generate a cost report for an item including BOM costs."""
    supabase = get_supabase_client()
    normalized = item_number.lower()

    # Get item
    item_result = supabase.table("items").select("*").eq(
        "item_number", normalized
    ).single().execute()

    if not item_result.data:
        raise HTTPException(status_code=404, detail=f"Item {item_number} not found")

    item = item_result.data

    # Count files
    files_result = supabase.table("files").select("id", count="exact").eq(
        "item_id", item["id"]
    ).execute()

    # Get BOM children with costs
    bom_result = supabase.table("bom").select(
        "child_item_id, quantity"
    ).eq("parent_item_id", item["id"]).execute()

    total_bom_cost = 0.0
    for entry in bom_result.data:
        child = supabase.table("items").select("price_est").eq(
            "id", entry["child_item_id"]
        ).single().execute()
        if child.data and child.data.get("price_est"):
            total_bom_cost += child.data["price_est"] * entry["quantity"]

    return CostReport(
        item_number=normalized,
        name=item.get("name"),
        price_est=item.get("price_est"),
        file_count=files_result.count or 0,
        bom_child_count=len(bom_result.data),
        total_bom_cost=total_bom_cost if total_bom_cost > 0 else None,
    )
```

**Step 3: Register the router** in `backend/app/routes/__init__.py`:

```python
from .reports import router as reports_router
```

And in `backend/app/main.py`:

```python
from .routes import reports_router

app.include_router(reports_router, prefix="/api")
```

**Step 4: Test** at `http://localhost:8000/docs` -- the new endpoint appears automatically in the Swagger UI.

---

## Adding a New Vue View

### Example: Cost Report View

**Step 1: Create the view component** at `frontend/src/views/CostReportView.vue`:

```vue
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../services/api'

interface CostReport {
  item_number: string
  name: string | null
  price_est: number | null
  file_count: number
  bom_child_count: number
  total_bom_cost: number | null
}

const route = useRoute()
const report = ref<CostReport | null>(null)
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  const itemNumber = route.params.itemNumber as string
  try {
    const response = await api.get(`/api/reports/cost/${itemNumber}`)
    report.value = response.data
  } catch (e: any) {
    error.value = e.response?.data?.detail || 'Failed to load cost report'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="cost-report">
    <h1>Cost Report</h1>

    <div v-if="loading">Loading...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else-if="report" class="report-content">
      <div class="info-row">
        <span class="label">Item</span>
        <span class="value">{{ report.item_number }}</span>
      </div>
      <div class="info-row">
        <span class="label">Name</span>
        <span class="value">{{ report.name || '-' }}</span>
      </div>
      <div class="info-row">
        <span class="label">Unit Cost</span>
        <span class="value">${{ report.price_est?.toFixed(2) || '-' }}</span>
      </div>
      <div class="info-row">
        <span class="label">Files</span>
        <span class="value">{{ report.file_count }}</span>
      </div>
      <div class="info-row">
        <span class="label">BOM Children</span>
        <span class="value">{{ report.bom_child_count }}</span>
      </div>
      <div class="info-row">
        <span class="label">Total BOM Cost</span>
        <span class="value">${{ report.total_bom_cost?.toFixed(2) || '-' }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cost-report {
  padding: 20px;
  max-width: 600px;
}
.info-row {
  display: grid;
  grid-template-columns: 150px 1fr;
  padding: 8px 0;
  border-bottom: 1px solid #e0e0e0;
}
.label {
  font-weight: 600;
  color: #555;
}
.error {
  color: #d32f2f;
  padding: 16px;
}
</style>
```

**Step 2: Add the route** in `frontend/src/router/index.ts`:

```typescript
{
  path: '/reports/cost/:itemNumber',
  name: 'cost-report',
  component: () => import('../views/CostReportView.vue'),
  meta: { requiresAuth: true }
},
```

The route is now accessible at `/reports/cost/csp0030` and requires authentication.

---

## Extending Pydantic Schemas

### Example: Adding a New Field to Items

To add a new field (e.g., `lead_time_days`) to items:

**Step 1: Add to the database** via Supabase SQL Editor:

```sql
ALTER TABLE items ADD COLUMN lead_time_days integer;
```

**Step 2: Update Pydantic schemas** in `backend/app/models/schemas.py`:

```python
class ItemBase(BaseModel):
    # ... existing fields ...
    lead_time_days: Optional[int] = None

class ItemUpdate(BaseModel):
    # ... existing fields ...
    lead_time_days: Optional[int] = None
```

The `Item` response model inherits from `ItemBase`, so it automatically includes the new field. The OpenAPI documentation updates automatically.

**Step 3: Update the frontend TypeScript type** in `frontend/src/types/index.ts` (or wherever types are defined):

```typescript
interface Item {
  // ... existing fields ...
  lead_time_days?: number
}
```

**Step 4: Display in the UI** by adding to the relevant Vue template:

```vue
<div class="info-row" v-if="selectedItem.lead_time_days">
  <span class="label">Lead Time</span>
  <span class="value">{{ selectedItem.lead_time_days }} days</span>
</div>
```

---

## Custom Supabase Queries

### Direct SQL via Supabase Dashboard

For ad-hoc queries, use the Supabase SQL Editor. This is useful for reports, data fixes, and diagnostics.

**Example: Items without files:**

```sql
SELECT i.item_number, i.name, i.lifecycle_state
FROM items i
LEFT JOIN files f ON i.id = f.item_id
WHERE f.id IS NULL
ORDER BY i.item_number;
```

**Example: BOM cost rollup for an assembly:**

```sql
WITH bom_costs AS (
    SELECT
        b.parent_item_id,
        p.item_number AS parent_number,
        c.item_number AS child_number,
        c.price_est AS child_cost,
        b.quantity,
        COALESCE(c.price_est, 0) * b.quantity AS line_total
    FROM bom b
    JOIN items p ON b.parent_item_id = p.id
    JOIN items c ON b.child_item_id = c.id
    WHERE p.item_number = 'sta01000'
)
SELECT
    parent_number,
    child_number,
    child_cost,
    quantity,
    line_total
FROM bom_costs
ORDER BY child_number;
```

**Example: Items modified in the last 7 days:**

```sql
SELECT item_number, name, lifecycle_state, updated_at
FROM items
WHERE updated_at > now() - interval '7 days'
ORDER BY updated_at DESC;
```

### Supabase Client Queries in Python

For programmatic queries from the backend:

```python
from app.services.supabase import get_supabase_client

supabase = get_supabase_client()

# Filter with multiple conditions
result = supabase.table("items").select("*") \
    .eq("lifecycle_state", "Design") \
    .not_.is_("material", "null") \
    .order("item_number") \
    .execute()

# Text search
result = supabase.table("items").select("*") \
    .or_("item_number.ilike.%steel%,name.ilike.%steel%,material.ilike.%steel%") \
    .execute()

# Join with related table
result = supabase.table("items").select("*, projects(name)") \
    .eq("lifecycle_state", "Released") \
    .execute()

# Count without fetching data
result = supabase.table("items").select("id", count="exact") \
    .eq("lifecycle_state", "Design") \
    .execute()
item_count = result.count
```

---

## Integrating with External Systems via API

### Example: Export Items to CSV for ERP

Create a script that calls the PDM-Web API and exports data:

```python
"""Export PDM items to CSV for ERP import."""

import csv
import requests

API_URL = "http://localhost:8000/api"

# Fetch all items
response = requests.get(f"{API_URL}/items", params={"limit": 10000})
response.raise_for_status()
items = response.json()

# Write CSV
with open("erp_items_export.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=[
        "item_number", "name", "description", "revision",
        "lifecycle_state", "material", "mass", "price_est"
    ])
    writer.writeheader()
    for item in items:
        writer.writerow({
            "item_number": item["item_number"],
            "name": item.get("name", ""),
            "description": item.get("description", ""),
            "revision": item.get("revision", ""),
            "lifecycle_state": item.get("lifecycle_state", ""),
            "material": item.get("material", ""),
            "mass": item.get("mass", ""),
            "price_est": item.get("price_est", ""),
        })

print(f"Exported {len(items)} items to erp_items_export.csv")
```

### Example: Import Supplier Prices from External System

```python
"""Import supplier prices into PDM from external pricing data."""

import csv
import requests

API_URL = "http://localhost:8000/api"

with open("supplier_prices.csv", "r") as f:
    reader = csv.DictReader(f)
    for row in reader:
        item_number = row["part_number"].lower()
        price = float(row["unit_price"])

        # Upsert item with price
        response = requests.patch(
            f"{API_URL}/items/{item_number}",
            params={"upsert": "true"},
            json={
                "price_est": price,
                "supplier_name": row.get("supplier", ""),
                "supplier_pn": row.get("supplier_pn", ""),
                "is_supplier_part": True,
            }
        )

        if response.status_code == 200:
            print(f"Updated {item_number}: ${price}")
        else:
            print(f"Failed {item_number}: {response.status_code} {response.text}")
```

### Example: Fetch BOM Tree from API

```python
"""Fetch and display a BOM tree from the PDM API."""

import requests

API_URL = "http://localhost:8000/api"


def print_bom_tree(item_number: str):
    """Fetch and print a BOM tree."""
    response = requests.get(f"{API_URL}/bom/{item_number}/tree")
    response.raise_for_status()
    tree = response.json()

    def print_node(node, depth=0):
        indent = "  " * depth
        item = node["item"]
        qty = node["quantity"]
        name = item.get("name", "")
        print(f"{indent}{item['item_number']} x{qty}  {name}")
        for child in node.get("children", []):
            print_node(child, depth + 1)

    print_node(tree)


print_bom_tree("sta01000")
```

---

## Webhook Examples

### Example: FastAPI Webhook Receiver

Add a webhook endpoint that external systems can call to notify PDM of events:

```python
"""Webhook receiver for external system notifications."""

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class PriceUpdateWebhook(BaseModel):
    """Incoming webhook payload for price updates."""
    item_number: str
    new_price: float
    currency: str = "USD"
    source: str = "external"


@router.post("/price-update")
async def receive_price_update(payload: PriceUpdateWebhook):
    """
    Receive a price update notification from an external system.

    External systems can POST to this endpoint when prices change.
    """
    from ..services.supabase import get_supabase_admin

    supabase = get_supabase_admin()
    normalized = payload.item_number.lower()

    # Update the item price
    result = supabase.table("items").update({
        "price_est": payload.new_price
    }).eq("item_number", normalized).execute()

    if not result.data:
        raise HTTPException(
            status_code=404,
            detail=f"Item {payload.item_number} not found"
        )

    return {
        "status": "updated",
        "item_number": normalized,
        "new_price": payload.new_price,
    }
```

### Example: Calling an External Webhook from PDM

To notify external systems when items change state, add a post-update hook:

```python
import httpx

WEBHOOK_URL = "https://external-system.example.com/api/pdm-updates"


async def notify_external_system(item_number: str, new_state: str):
    """Send a webhook notification to an external system."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(WEBHOOK_URL, json={
                "event": "lifecycle_state_changed",
                "item_number": item_number,
                "new_state": new_state,
                "source": "pdm-web",
            }, timeout=10.0)
            response.raise_for_status()
        except httpx.HTTPError as e:
            # Log but do not fail the primary operation
            print(f"Webhook notification failed: {e}")
```

---

## The Upload Bridge as an Integration Pattern

The `scripts/pdm-upload/` directory demonstrates a key integration pattern: **bridging a local filesystem workflow to a web API**.

### How It Works

```
Local CAD Workstation            Web API                Supabase
+-------------------+           +---------+            +----------+
| Creo exports file | --------> | FastAPI | ---------> | Storage  |
| to watched folder |   HTTP    | /files  |   Supabase | (bucket) |
+-------------------+  upload   | /upload |   client   +----------+
                                +---------+
| BOM text export   | --------> | FastAPI | ---------> | Database |
| from Creo         |   HTTP    | /bom    |   Supabase | (tables) |
+-------------------+   POST    | /bulk   |   client   +----------+
```

### Key Scripts

| Script | Purpose |
|--------|---------|
| `PDM-Upload-Service.ps1` | Watches local folders, detects new/changed files, uploads via API |
| `PDM-BOM-Parser.ps1` | Parses Creo BOM text exports, sends structured data to bulk BOM endpoint |
| `PDM-Upload-Functions.ps1` | Shared functions: item number extraction, API call wrappers, file type detection |
| `PDM-Upload-Config.ps1` | Configuration: API URL, watched folder paths, file extension mappings |

### Replicating This Pattern

To integrate another local system with PDM-Web, follow this pattern:

1. **Watch for local events** (new files, data exports, etc.)
2. **Extract structured data** from the local format (parse filenames, read text files)
3. **Call the appropriate API endpoint** (`POST /api/files/upload` for files, `POST /api/bom/bulk` for BOMs, `PATCH /api/items/{number}?upsert=true` for item data)
4. **Handle errors and retries** (network failures, API validation errors)
5. **Log operations** for debugging

This pattern works in any language. The upload bridge uses PowerShell because the local workstation runs Windows with Creo, but the same approach works with Python, Go, Node.js, or any language with HTTP client support.

### Example: Python Upload Bridge

```python
"""Minimal example of an upload bridge in Python."""

import os
import time
import requests
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

API_URL = "http://localhost:8000/api"
WATCH_DIR = r"C:\CADExport\CheckIn"


class FileUploadHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return

        filepath = Path(event.src_path)
        filename = filepath.name

        # Extract item number from filename
        import re
        match = re.match(r'^([a-z]{3}\d{4,6})', filename.lower())
        if not match:
            print(f"Skipping {filename}: no valid item number")
            return

        item_number = match.group(1)

        # Ensure item exists (upsert)
        requests.patch(
            f"{API_URL}/items/{item_number}",
            params={"upsert": "true"},
            json={"name": item_number.upper()}
        )

        # Upload file
        with open(filepath, "rb") as f:
            response = requests.post(
                f"{API_URL}/files/upload",
                files={"file": (filename, f)},
                data={"item_number": item_number}
            )

        if response.status_code == 200:
            print(f"Uploaded {filename} -> {item_number}")
        else:
            print(f"Failed {filename}: {response.text}")


if __name__ == "__main__":
    observer = Observer()
    observer.schedule(FileUploadHandler(), WATCH_DIR, recursive=False)
    observer.start()
    print(f"Watching {WATCH_DIR} for new files...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
```

---

## Adding a Pinia Store

### Example: Reports Store

Create `frontend/src/stores/reports.ts`:

```typescript
import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../services/api'

interface CostReport {
  item_number: string
  name: string | null
  price_est: number | null
  file_count: number
  bom_child_count: number
  total_bom_cost: number | null
}

export const useReportsStore = defineStore('reports', () => {
  const currentReport = ref<CostReport | null>(null)
  const loading = ref(false)
  const error = ref('')

  async function fetchCostReport(itemNumber: string) {
    loading.value = true
    error.value = ''
    try {
      const response = await api.get(`/api/reports/cost/${itemNumber}`)
      currentReport.value = response.data
    } catch (e: any) {
      error.value = e.response?.data?.detail || 'Failed to load report'
      currentReport.value = null
    } finally {
      loading.value = false
    }
  }

  return { currentReport, loading, error, fetchCostReport }
})
```

Use in a component:

```vue
<script setup lang="ts">
import { useReportsStore } from '../stores/reports'

const reportsStore = useReportsStore()

function loadReport(itemNumber: string) {
  reportsStore.fetchCostReport(itemNumber)
}
</script>
```

---

## Testing Custom Extensions

### Backend Testing

Test new endpoints using the FastAPI interactive docs:

1. Start the backend: `cd backend && uvicorn app.main:app --reload`
2. Open `http://localhost:8000/docs`
3. Find your new endpoint in the list
4. Click "Try it out" and fill in parameters
5. Click "Execute" and verify the response

Or test with curl:

```bash
# Test a GET endpoint
curl http://localhost:8000/api/reports/cost/csp0030

# Test a POST endpoint
curl -X POST http://localhost:8000/api/webhooks/price-update \
  -H "Content-Type: application/json" \
  -d '{"item_number": "csp0030", "new_price": 15.50}'

# Test file upload
curl -X POST http://localhost:8000/api/files/upload \
  -F "file=@/path/to/file.step" \
  -F "item_number=csp0030"
```

### Frontend Testing

1. Start both backend and frontend: two terminal windows
2. Open `http://localhost:5173` in a browser
3. Navigate to the new view
4. Open Developer Tools (F12) to monitor:
   - Console for JavaScript errors
   - Network for API request/response data
   - Vue DevTools extension for component state

### Checklist for New Extensions

- [ ] Pydantic schema validates input correctly (test with invalid data)
- [ ] Endpoint returns proper HTTP status codes (200, 404, 400, 500)
- [ ] Error messages are clear and actionable
- [ ] Admin client used where RLS bypass is needed
- [ ] Item numbers normalized to lowercase
- [ ] UUIDs converted to strings for Supabase queries
- [ ] New route registered in `__init__.py` and `main.py`
- [ ] Frontend route added to `router/index.ts` with `requiresAuth: true`
- [ ] OpenAPI docs render correctly at `/docs`

---

## Reference Resources

- **FastAPI:** https://fastapi.tiangolo.com/
- **Pydantic:** https://docs.pydantic.dev/
- **Vue 3:** https://vuejs.org/
- **Pinia:** https://pinia.vuejs.org/
- **Vue Router:** https://router.vuejs.org/
- **Supabase Python Client:** https://supabase.com/docs/reference/python/introduction
- **Supabase JavaScript Client:** https://supabase.com/docs/reference/javascript/introduction
- **Supabase Storage:** https://supabase.com/docs/guides/storage
- **FreeCAD API:** https://wiki.freecadweb.org/FreeCAD_API

---

**Last Updated:** 2025-01-29
**Version:** 3.0
**Related:** [15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md](15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md), [18-GLOSSARY-TERMS.md](18-GLOSSARY-TERMS.md)
