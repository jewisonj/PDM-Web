# BOM Management and Cost Analysis Guide

## Overview

The Bill of Materials (BOM) system manages parent-child relationships between assemblies and their component parts. BOM data flows from Creo CAD exports through the PDM Upload Service into the Supabase PostgreSQL database, where it can be queried through the FastAPI backend for tree views, where-used analysis, and cost rollup calculations.

---

## BOM Structure in the Database

### Single-Level BOM

The `bom` table stores **single-level** parent-child relationships. Each row represents one direct relationship between a parent assembly and a child component.

```sql
-- Each BOM entry links a parent item to a child item with a quantity
bom (
    id              UUID PRIMARY KEY,
    parent_item_id  UUID REFERENCES items(id),
    child_item_id   UUID REFERENCES items(id),
    quantity        INTEGER DEFAULT 1,
    source_file     TEXT,            -- e.g., 'BOM.txt'
    created_at      TIMESTAMPTZ,
    UNIQUE(parent_item_id, child_item_id)
);
```

**Example structure:**

```
wma20120 (Top Assembly)
  |-- wmp20080 x4   (Bracket)
  |-- wmp20090 x2   (Shaft)
  |-- wsa20100 x1   (Sub-Assembly)
        |-- wsp20110 x3  (Plate)
        |-- wsp20120 x1  (Support)
```

In the database, this is stored as two separate single-level BOM records:

| parent_item_id | child_item_id | quantity |
|---|---|---|
| (wma20120's UUID) | (wmp20080's UUID) | 4 |
| (wma20120's UUID) | (wmp20090's UUID) | 2 |
| (wma20120's UUID) | (wsa20100's UUID) | 1 |
| (wsa20100's UUID) | (wsp20110's UUID) | 3 |
| (wsa20100's UUID) | (wsp20120's UUID) | 1 |

To reconstruct a full multi-level BOM tree, the API recursively traverses child assemblies.

---

## Data Flow: Creo Export to Database

### Step 1: Export BOM from Creo

In Creo Parametric, export a BOM tree as a fixed-width text file. The file includes columns for part properties:

```
Model Name         DESCRIPTION            PROJECT   PRO_MP_MASS   PTC_MASTER_MATERIAL  CUT_LENGTH  SMT_THICKNESS  CUT_TIME  PRICE_EST
---------          -----------            -------   -----------   -----------------    ---------   -----------    --------  ---------
 WMA20120.ASM     Top Assembly           PROJ1     10.5          Steel                -           -              -         -
   WMP20080.PRT   Bracket                PROJ1     2.5           STEEL_HSLA           500         3.0            15        2.50
   WMP20090.PRT   Shaft                  PROJ1     1.2           ALUMINUM_6061        300         2.5            10        3.75
   WMP20080.PRT   Bracket                PROJ1     2.5           STEEL_HSLA           500         3.0            15        2.50
```

In the example above, `WMP20080.PRT` appears twice, so the parser counts its quantity as 2.

### Step 2: Place File in Upload Folder

Save the export as `BOM.txt` (or `MLBOM.txt` for multi-level) in the PDM Upload Service watch folder (default: `C:\PDM-Upload`).

### Step 3: PDM Upload Service Detects the File

The `PDM-Upload-Service.ps1` file watcher detects the new file and determines it is a BOM file based on the filename (`BOM.txt` or `MLBOM.txt`).

### Step 4: BOM Parser Extracts Data

`PDM-BOM-Parser.ps1` parses the fixed-width text file:

1. **Finds the header line** containing `Model Name` to determine column positions.
2. **Identifies the parent assembly** -- the first item with `.ASM` extension and minimal indentation.
3. **Extracts child items** with their properties:
   - `item_number` -- extracted from the model name, normalized to lowercase
   - `name` -- from the DESCRIPTION column
   - `material` -- from PTC_MASTER_MATERIAL column
   - `mass` -- from PRO_MP_MASS column
   - `thickness` -- from SMT_THICKNESS column
   - `cut_length` -- from CUT_LENGTH column
   - `cut_time` -- from CUT_TIME column
   - `price_est` -- from PRICE_EST column
4. **Counts quantities** -- duplicate item numbers are consolidated with incremented quantity.
5. **Skips special items** -- `zzz` prefixed reference items, skeleton parts (`_SKEL.PRT`), and standard assembly features.

The parser produces a JSON structure:

```json
{
    "parent_item_number": "wma20120",
    "children": [
        {
            "item_number": "wmp20080",
            "quantity": 2,
            "name": "Bracket",
            "material": "STEEL_HSLA",
            "mass": 2.5,
            "thickness": 3.0,
            "cut_length": 500,
            "cut_time": 15,
            "price_est": 2.50
        },
        {
            "item_number": "wmp20090",
            "quantity": 1,
            "name": "Shaft",
            "material": "ALUMINUM_6061",
            "mass": 1.2,
            "thickness": 2.5,
            "cut_length": 300,
            "cut_time": 10,
            "price_est": 3.75
        }
    ],
    "source_file": "BOM.txt"
}
```

### Step 5: Upload to API

The Upload Service sends this JSON to `POST /api/bom/bulk`.

### Step 6: API Processes Bulk BOM

The `/api/bom/bulk` endpoint performs these operations using the admin Supabase client (bypassing RLS):

1. **Get or create the parent item** -- looks up the parent by `item_number`; creates it if it does not exist.
2. **Delete existing BOM entries** -- removes all current BOM rows for this parent (full replacement strategy).
3. **For each child item:**
   - Look up or create the child item in the `items` table.
   - Update the child item's properties (`material`, `mass`, `thickness`, `cut_length`, `cut_time`, `price_est`) from the parsed data.
   - Items with `mmc` or `spn` prefixes are automatically flagged as `is_supplier_part = true`.
   - Create the BOM relationship row.
4. **Return a summary** with counts of items created, updated, and BOM entries created.

---

## API Endpoints

### Get Single-Level BOM

```
GET /api/bom/{item_number}
```

Returns direct BOM entries (raw `bom` table rows) for the given assembly.

### Get BOM Tree (Recursive)

```
GET /api/bom/{item_number}/tree?max_depth=10
```

Returns the full hierarchical BOM tree. The API recursively traverses children up to `max_depth` levels (default 10).

**Response structure:**

```json
{
    "item": { "id": "...", "item_number": "wma20120", "name": "Top Assembly", ... },
    "quantity": 1,
    "children": [
        {
            "item": { "id": "...", "item_number": "wmp20080", "name": "Bracket", ... },
            "quantity": 4,
            "children": []
        },
        {
            "item": { "id": "...", "item_number": "wsa20100", "name": "Sub-Assembly", ... },
            "quantity": 1,
            "children": [
                {
                    "item": { "id": "...", "item_number": "wsp20110", ... },
                    "quantity": 3,
                    "children": []
                }
            ]
        }
    ]
}
```

### Where-Used Query

```
GET /api/bom/{item_number}/where-used
```

Returns all assemblies that contain the specified item as a direct child. Useful for impact analysis when a part changes.

**Response structure:**

```json
[
    {
        "item": { "id": "...", "item_number": "wma20120", "name": "Top Assembly", ... },
        "quantity": 4
    }
]
```

### Bulk BOM Upload

```
POST /api/bom/bulk
```

**Request body:**

```json
{
    "parent_item_number": "wma20120",
    "children": [
        {
            "item_number": "wmp20080",
            "quantity": 4,
            "name": "Bracket",
            "material": "STEEL_HSLA",
            "mass": 2.5,
            "thickness": 3.0,
            "cut_length": 500,
            "cut_time": 15,
            "price_est": 2.50
        }
    ],
    "source_file": "BOM.txt"
}
```

**Response:**

```json
{
    "parent_item_number": "wma20120",
    "parent_item_id": "uuid-here",
    "items_created": 2,
    "items_updated": 3,
    "bom_entries_created": 5,
    "children": ["wmp20080", "wmp20090", "wsa20100"]
}
```

### Add Single BOM Entry

```
POST /api/bom
```

**Request body:**

```json
{
    "parent_item_id": "uuid-of-parent",
    "child_item_id": "uuid-of-child",
    "quantity": 2,
    "source_file": "manual"
}
```

### Update BOM Quantity

```
PATCH /api/bom/{bom_id}?quantity=3
```

### Delete BOM Entry

```
DELETE /api/bom/{bom_id}
```

---

## Cost Rollup

### Overview

Cost rollup calculates the total estimated cost of an assembly by summing the `price_est` values of all component items, factoring in BOM quantities. This is done through database queries rather than a dedicated script.

### The price_est Field

Each item in the `items` table has a `price_est` (NUMERIC) column representing the estimated cost per unit. This value can be populated in two ways:

1. **Automatically via BOM upload** -- When a Creo BOM export includes the `PRICE_EST` column, the bulk upload endpoint updates the `price_est` on each child item.
2. **Manually via API** -- Update an item's price directly:

```
PATCH /api/items/csp0030
Content-Type: application/json

{
    "price_est": 25.50
}
```

### Recursive Cost Calculation

The total cost of an assembly is calculated by recursively traversing the BOM tree:

```
Total Cost = Assembly's own price_est
           + SUM(child_price_est * child_quantity)
           + SUM(sub-assembly costs, recursively)
```

### SQL: Single-Level Cost Rollup

Calculate the cost of an assembly's direct children:

```sql
SELECT
    i_parent.item_number AS assembly,
    i_parent.price_est AS assembly_price,
    SUM(COALESCE(i_child.price_est, 0) * b.quantity) AS children_cost,
    COALESCE(i_parent.price_est, 0)
        + SUM(COALESCE(i_child.price_est, 0) * b.quantity) AS total_cost
FROM items i_parent
JOIN bom b ON b.parent_item_id = i_parent.id
JOIN items i_child ON b.child_item_id = i_child.id
WHERE i_parent.item_number = 'wma20120'
GROUP BY i_parent.item_number, i_parent.price_est;
```

### SQL: Full Recursive Cost Rollup

Use a recursive CTE to calculate costs across the entire BOM hierarchy:

```sql
WITH RECURSIVE bom_tree AS (
    -- Base case: direct children of the top assembly
    SELECT
        b.child_item_id AS item_id,
        b.quantity AS effective_qty,
        1 AS depth
    FROM bom b
    JOIN items i ON b.parent_item_id = i.id
    WHERE i.item_number = 'wma20120'

    UNION ALL

    -- Recursive: children of sub-assemblies
    SELECT
        b.child_item_id,
        b.quantity * bt.effective_qty,
        bt.depth + 1
    FROM bom b
    JOIN bom_tree bt ON b.parent_item_id = bt.item_id
    WHERE bt.depth < 10
)
SELECT
    SUM(COALESCE(i.price_est, 0) * bt.effective_qty) AS total_children_cost
FROM bom_tree bt
JOIN items i ON bt.item_id = i.id;
```

This query multiplies quantities at each level to get the effective quantity. For example, if the top assembly uses 2 sub-assemblies and each sub-assembly uses 3 plates, the effective quantity for the plate is 6.

### Python: Cost Rollup via API

The BOM tree endpoint returns a nested structure that can be used for cost rollup in application code:

```python
import httpx

def calculate_cost(node: dict) -> float:
    """Recursively calculate cost from BOM tree node."""
    item = node["item"]
    qty = node["quantity"]
    own_price = item.get("price_est") or 0

    children_cost = sum(
        calculate_cost(child) for child in node.get("children", [])
    )

    return (own_price + children_cost) * qty

# Fetch the BOM tree
response = httpx.get("http://localhost:8000/api/bom/wma20120/tree")
tree = response.json()

total_cost = calculate_cost(tree)
print(f"Total estimated cost: ${total_cost:.2f}")
```

### Cost Breakdown Report

To produce a detailed cost breakdown showing each level:

```python
def print_cost_breakdown(node: dict, indent: int = 0) -> float:
    """Print hierarchical cost breakdown."""
    item = node["item"]
    qty = node["quantity"]
    price = item.get("price_est") or 0
    item_num = item["item_number"]
    name = item.get("name", "")

    children_cost = 0
    for child in node.get("children", []):
        children_cost += print_cost_breakdown(child, indent + 2)

    total = (price + children_cost) * qty
    line_cost = price * qty

    prefix = " " * indent
    if node.get("children"):
        print(f"{prefix}[ASM] {item_num} ({name}) x{qty} @ ${price:.2f}")
        print(f"{prefix}  Subtotal: ${total:.2f} = ${line_cost:.2f} (own) + ${children_cost * qty:.2f} (children)")
    else:
        print(f"{prefix}[PART] {item_num} ({name}) x{qty} @ ${price:.2f} = ${line_cost:.2f}")

    return total
```

---

## Circular Reference Protection

### In the API

The BOM tree endpoint (`GET /api/bom/{item_number}/tree`) uses a `max_depth` parameter (default 10) to prevent infinite recursion. If the BOM tree exceeds this depth, traversal stops.

### In the Bulk Upload

The `POST /api/bom/bulk` endpoint checks for self-references:

```python
if str(bom.parent_item_id) == str(bom.child_item_id):
    raise HTTPException(status_code=400, detail="Item cannot be its own child")
```

### In SQL Queries

When writing custom recursive CTEs, always include a depth limit:

```sql
WHERE bt.depth < 10  -- Prevent infinite loops
```

---

## Item Naming Conventions in BOM Data

| Prefix | Type | BOM Behavior |
|---|---|---|
| Standard (e.g., `csp`, `wma`) | In-house parts/assemblies | Created or updated normally |
| `mmc` | McMaster-Carr purchased parts | Created with `is_supplier_part = true` |
| `spn` | Other supplier parts | Created with `is_supplier_part = true` |
| `zzz` | Reference/dummy items | Skipped entirely during BOM upload |

Skeleton parts (`_SKEL.PRT`) and standard assembly features (`ASM_RIGHT`, `ASM_TOP`, `ASM_FRONT`, `ASM_DEF_CSYS`) are also filtered out by the parser.

---

## Common Use Cases

### Get full cost for a manufacturing run

```sql
-- Cost for building 5 units of wma20120
WITH RECURSIVE bom_tree AS (
    SELECT b.child_item_id AS item_id, b.quantity AS effective_qty, 1 AS depth
    FROM bom b
    JOIN items i ON b.parent_item_id = i.id
    WHERE i.item_number = 'wma20120'

    UNION ALL

    SELECT b.child_item_id, b.quantity * bt.effective_qty, bt.depth + 1
    FROM bom b
    JOIN bom_tree bt ON b.parent_item_id = bt.item_id
    WHERE bt.depth < 10
)
SELECT
    5 AS build_qty,
    5 * (
        COALESCE((SELECT price_est FROM items WHERE item_number = 'wma20120'), 0)
        + COALESCE((
            SELECT SUM(COALESCE(i.price_est, 0) * bt.effective_qty)
            FROM bom_tree bt JOIN items i ON bt.item_id = i.id
        ), 0)
    ) AS total_cost;
```

### Find items missing price data

```sql
SELECT i.item_number, i.name, i.material
FROM items i
WHERE i.price_est IS NULL
  AND i.item_number NOT LIKE 'zzz%'
  AND EXISTS (SELECT 1 FROM bom b WHERE b.child_item_id = i.id)
ORDER BY i.item_number;
```

### Compare cost of two revisions

Query the items table for both revisions and compare their BOM tree costs using the recursive cost rollup query.

### Identify high-cost components

```sql
SELECT
    i_child.item_number,
    i_child.name,
    i_child.price_est,
    b.quantity,
    i_child.price_est * b.quantity AS line_cost
FROM bom b
JOIN items i_parent ON b.parent_item_id = i_parent.id
JOIN items i_child ON b.child_item_id = i_child.id
WHERE i_parent.item_number = 'wma20120'
  AND i_child.price_est IS NOT NULL
ORDER BY line_cost DESC;
```

---

## Integration with MRP

BOM data feeds into the MRP (Manufacturing Resource Planning) system:

1. An **MRP project** references a `top_assembly_id` from the `items` table.
2. The BOM tree is exploded to generate a parts list with effective quantities.
3. The `mrp_project_parts` table stores the exploded BOM with required quantities per project.
4. Cost data from `price_est` supports project costing and quoting.

---

## Troubleshooting

### BOM upload returns no children

**Problem:** `POST /api/bom/bulk` response shows `bom_entries_created: 0`.

**Solution:**
- Verify the BOM text file has the correct format with `Model Name` in the header.
- Check that child items are indented (at least 3 spaces) relative to the parent assembly.
- Ensure child item numbers match the expected pattern (3 letters + 4-6 digits).

### Price data not appearing

**Problem:** Items have `price_est: null` after BOM upload.

**Solution:**
- Verify the Creo BOM export includes the `PRICE_EST` column in the header.
- Check that price values are numeric (not text like "N/A" or "-").
- The parser only accepts values matching the pattern `^\d+\.?\d*$`.

### Duplicate key error on BOM upload

**Problem:** Error containing "duplicate key" during bulk upload.

**Solution:** The bulk upload endpoint deletes all existing BOM entries for the parent before inserting new ones. If this error occurs, it may be a race condition from concurrent uploads. Retry the operation.

### BOM tree shows wrong quantities

**Problem:** Quantities in the tree do not match the Creo BOM.

**Solution:**
- The parser counts duplicate item numbers in the text file and sums their quantity.
- Verify the source text file has the correct number of occurrences for each part.
- Check the `source_file` field on BOM entries to confirm which file was last uploaded.

---

## Related Documentation

- **Database Schema:** `Documentation/03-DATABASE-SCHEMA.md` -- Full table definitions
- **Database Maintenance:** `Documentation/07-PDM-DATABASE-CLEANUP-GUIDE.md` -- Cleanup procedures
- **Upload Service Scripts:** `scripts/pdm-upload/` -- PDM-BOM-Parser.ps1, PDM-Upload-Service.ps1

---

**Last Updated:** 2026-01-29
