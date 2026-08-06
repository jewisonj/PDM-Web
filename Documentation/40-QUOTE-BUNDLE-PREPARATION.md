# Quote Bundle Preparation Guide

**Document ID:** 40
**Last Updated:** 2026-08-04
**Purpose:** Guide for preparing STEP file quote bundles for external fabricators

---

## Overview

When requesting manufacturing quotes from external fabricators, we prepare organized STEP file bundles with descriptive BOMs. This guide covers the complete process from querying the PDM BOM to delivering revision-controlled quote packages.

**Typical Use Cases:**
- Initial quote for new project (all parts at Rev A)
- Updated quote after design changes (rev bumps)
- Re-quote after consolidating/eliminating parts

**Key Difference from Kit Sourcing (Doc 39):**
- Kit sourcing (Doc 39): Ordering vendor-supplied bundles for parts we'll use as-is
- Quote bundles (this doc): Sending our designs to fabricators for price quotes with revision tracking

---

## Quick Reference

### Export Folder Structure

```
STP_Export/
├── Tubes/
│   ├── Tubes_BOM.csv
│   └── {part_number}_{rev}.step       # e.g., csp00010_B.step
└── Sheetmetal/
    ├── Sheetmetal_BOM.csv
    └── {part_number}_{rev}.step       # e.g., csp00120_A.step
```

### CSV Format

**Category BOMs (Tubes_BOM.csv, Sheetmetal_BOM.csv):**
```csv
Qty,Number,REV,Description,Material,Thickness,CHANGES
2,csp00010,B,FRONT POST,STEEL_HSLA,0.125,Consolidated - qty 2->4
1,csp00120,A,REAR BRACKET,STEEL_HSLA,0.1875,NEW PART
4,csp00140,B,TOP BRACE,STEEL_HSLA,0.125,Updated geometry
```

### Revision Tracking Rules

| Scenario | Rev Assignment | Example |
|----------|---------------|---------|
| **New part** (not in previous quote) | Start at **Rev A** | csp00120 → Rev A |
| **Updated part** (already quoted) | **Bump by one letter** | csp00010_A.step → csp00010_B.step |
| **Eliminated part** | **Remove from folder and CSV** | csp00060 consolidated → delete file |
| **Consolidated part** (merged into another) | **Update qty, note in CHANGES** | csp00060 → csp00050 (qty 2→4) |

---

## Step-by-Step Process

### Step 1: Get Fresh BOM Data from PDM

Query the database for the complete BOM from your top-level assembly.

**Example SQL (via Supabase or backend API):**

```sql
WITH RECURSIVE bom_tree AS (
  -- Start with top-level assembly
  SELECT i.id, i.item_number, i.name, i.material, i.thickness,
         1 as quantity, 0 as level
  FROM items i
  WHERE i.item_number = 'csa00015'

  UNION ALL

  -- Recurse through children
  SELECT child.id, child.item_number, child.name, child.material, child.thickness,
         b.quantity * bt.quantity, bt.level + 1
  FROM bom_tree bt
  JOIN bom b ON b.parent_item_id = bt.id
  JOIN items child ON child.id = b.child_item_id
  WHERE bt.level < 10
    AND child.item_number NOT IN ('csa00900')  -- Exclude specific sub-assemblies
)
SELECT
  item_number,
  name,
  material,
  thickness,
  SUM(quantity) as total_qty
FROM bom_tree
WHERE item_number LIKE 'csp0%'     -- CSP parts only (adjust prefix as needed)
GROUP BY item_number, name, material, thickness
ORDER BY item_number;
```

**Key Exclusions:**
- Sub-assemblies that have their own quote bundle (e.g., door assembly `csa00900`)
- Supplier parts (`mmc`, `spn` prefixes)
- Reference-only items (`zzz` prefix)

**Common BOM Exclusion Patterns:**
```sql
-- Exclude specific assemblies
WHERE child.item_number NOT IN ('csa00900', 'csa00800')

-- Exclude by prefix
WHERE child.item_number NOT LIKE 'mmc%'
  AND child.item_number NOT LIKE 'spn%'
  AND child.item_number NOT LIKE 'zzz%'
```

### Step 2: Check STEP File Availability

Verify all parts have STEP files in PDM:

```sql
SELECT
  i.item_number,
  i.name,
  f.file_name,
  f.file_type
FROM items i
LEFT JOIN files f ON f.item_id = i.id
  AND (f.file_type = 'STP' OR f.file_name LIKE '%.step')
WHERE i.item_number IN ('csp00010', 'csp00050', ...)
ORDER BY i.item_number;
```

**Action Items:**
- Parts **with files**: Ready to export
- Parts **without files**: Upload STEP files first (via PDM Upload Service or API)

**Missing File Handling:**
```
csp00230 - ELECTRICAL BOX - NO STEP FILE
  → Upload from Creo workspace before proceeding
```

### Step 3: Compare with Previous Quote Bundle

Navigate to your export folder (e.g., `STP_Export/`) and inventory existing files.

**Check Current Revisions:**

```
STP_Export/Tubes/
  csp00010_A.step  → Current rev: A
  csp00050_A.step  → Current rev: A
  csp00140_A.step  → Current rev: A

STP_Export/Sheetmetal/
  csp00120_A.step  → Current rev: A
  csp00160_A.step  → Current rev: A
```

**Cross-Reference with Fresh BOM:**

| Item | In Folder? | Current Rev | Fresh BOM Qty | Previous Qty | Status |
|------|-----------|-------------|---------------|--------------|--------|
| csp00010 | ✓ | A | 2 | 2 | No change |
| csp00050 | ✓ | A | 4 | 2 | **Qty change (consolidation)** |
| csp00060 | ✓ | A | - | 2 | **Eliminated (consolidated into csp00050)** |
| csp00120 | ✓ | A | - | 1 | **Eliminated (consolidated into csp00140)** |
| csp00140 | ✓ | A | 2 | 1 | **Qty change (consolidation)** |
| csp00230 | ✗ | - | 1 | - | **New part** |

### Step 4: Determine Revision Bumps

Apply revision rules based on comparison:

**Rev Bump Decision Tree:**

```
Is part in previous quote folder?
│
├─ YES → Has the geometry changed?
│        │
│        ├─ YES → Bump rev by one letter (A→B, B→C)
│        │        Add note: "Updated geometry"
│        │
│        └─ NO → Has the quantity changed?
│                 │
│                 ├─ YES → Bump rev by one letter (quantity change triggers re-quote)
│                 │        Add note: "Qty change: 2→4"
│                 │
│                 └─ NO → Keep same rev, copy existing file
│
└─ NO → Part is new
         Assign Rev A
         Add note: "NEW PART"
```

**Example Revision Plan:**

| Item | Previous | New Rev | Action | Changes Note |
|------|----------|---------|--------|--------------|
| csp00010 | A | **B** | Download new STEP, rename to `_B` | No geometry change, but re-quote |
| csp00050 | A | **B** | Download new STEP, rename to `_B` | Consolidated - qty 2→4 |
| csp00060 | A | - | **DELETE FILE** | Consolidated into csp00050 |
| csp00120 | A | - | **DELETE FILE** | Consolidated into csp00140 |
| csp00140 | A | **B** | Download new STEP, rename to `_B` | Consolidated - qty 1→2 |
| csp00160 | A | - | **DELETE FILE** | Consolidated into csp00150 |
| csp00230 | - | **A** | Download STEP, name as `_A` | NEW PART |

### Step 5: Download Fresh STEP Files from PDM

For each part needing an update:

1. **Get item details** from API:
   ```bash
   curl -s "http://localhost:8001/api/items/csp00050"
   ```

2. **Find STEP file ID** in response:
   ```json
   {
     "item_number": "csp00050",
     "name": "FRONT POST",
     "files": [
       {"id": "abc-123", "file_type": "STP", "file_name": "csp00050.step"}
     ]
   }
   ```

3. **Get signed download URL**:
   ```bash
   curl -s "http://localhost:8001/api/files/abc-123/download"
   ```

4. **Download and rename** with revision letter:
   ```bash
   # Download to temp location
   wget -O temp.step "https://...supabase.co/storage/..."

   # Rename with revision
   mv temp.step STP_Export/Tubes/csp00050_B.step
   ```

**Batch Download Script Pattern:**

```python
import requests
import json

API_BASE = "http://localhost:8001/api"

parts_to_update = [
    {"item": "csp00050", "rev": "B", "category": "Tubes"},
    {"item": "csp00140", "rev": "B", "category": "Sheetmetal"},
    {"item": "csp00230", "rev": "A", "category": "Sheetmetal"}
]

for part in parts_to_update:
    # Get item details
    r = requests.get(f"{API_BASE}/items/{part['item']}")
    item_data = r.json()

    # Find STEP file
    step_file = next((f for f in item_data.get('files', [])
                      if f.get('file_type') == 'STP'), None)

    if not step_file:
        print(f"WARNING: No STEP for {part['item']}")
        continue

    # Get download URL
    r = requests.get(f"{API_BASE}/files/{step_file['id']}/download")
    download_url = r.json()['url']

    # Download file
    r = requests.get(download_url)
    filename = f"{part['item']}_{part['rev']}.step"
    filepath = f"STP_Export/{part['category']}/{filename}"

    with open(filepath, 'wb') as f:
        f.write(r.content)

    print(f"Downloaded: {filepath}")
```

### Step 6: Update CSV BOMs

Update the category BOMs with new revision letters and change notes.

**Tubes_BOM.csv:**

```csv
Qty,Number,REV,Description,Material,Thickness,CHANGES
4,csp00050,B,FRONT POST,STEEL_HSLA,0.125,Consolidated - qty 2->4 (absorbed csp00060)
2,csp00010,B,OUTSIDE CROSS TUBE,STEEL_HSLA,0.125,Re-quote
1,csp00270,B,DRAIN PIPE,STEEL_HSLA,0.125,Re-quote
```

**Sheetmetal_BOM.csv:**

```csv
Qty,Number,REV,Description,Material,Thickness,CHANGES
2,csp00140,B,TOP BRACE,STEEL_HSLA,0.125,Consolidated - qty 1->2 (absorbed csp00120)
2,csp00150,B,SIDE BRACKET,STEEL_HSLA,0.1875,Consolidated - qty 1->2 (absorbed csp00160)
1,csp00230,A,ELECTRICAL BOX,STEEL_HSLA,0.0625,NEW PART
```

**CSV Generation Best Practices:**

1. **Material Consistency:**
   - Use vendor's preferred material codes (e.g., "STEEL_HSLA" not "Steel, 1018")
   - Override PDM material if needed (PDM may show "6061-T6 ALUMINUM" but vendor wants "AL")

2. **Thickness Format:**
   - Use decimal inches: `0.125`, `0.0625`, `0.1875`
   - Avoid fractions: Use `0.125` not `1/8`

3. **CHANGES Column:**
   - Be specific about what changed
   - Track consolidations explicitly
   - Note geometry updates vs. quantity-only changes

**Example CHANGES Notes:**

| Scenario | CHANGES Note |
|----------|--------------|
| New part | `NEW PART` |
| Geometry update | `Updated geometry - hole pattern changed` |
| Consolidation | `Consolidated - qty 2->4 (absorbed csp00060)` |
| Material change | `Material changed: AL -> STEEL` |
| Thickness change | `Thickness changed: 0.125 -> 0.1875` |
| Re-quote only | `Re-quote` (no design change) |

### Step 7: Track Consolidations

Document which parts were consolidated and why:

**Consolidation Log (keep in STP_Export/README.txt):**

```
=== QUOTE UPDATE - 2026-08-04 ===

CONSOLIDATIONS:
  csp00060 (REAR POST, qty 2) → ELIMINATED
    ├─ Consolidated into csp00050 (FRONT POST)
    └─ New qty: 4 (was 2)

  csp00120 (SIDE BRACKET LEFT, qty 1) → ELIMINATED
    ├─ Consolidated into csp00140 (SIDE BRACKET, qty 2)
    └─ Now ambidextrous design

  csp00160 (MOUNTING PLATE LEFT, qty 1) → ELIMINATED
    ├─ Consolidated into csp00150 (MOUNTING PLATE, qty 2)
    └─ Now ambidextrous design

NEW PARTS:
  csp00230 (ELECTRICAL BOX, qty 1)
    └─ Added for electrical routing

PART COUNT CHANGE:
  Previous quote: 18 parts
  Current quote:  15 parts (3 eliminated, 1 added)
```

**Why Track Consolidations:**

- Helps vendor understand BOM changes
- Provides context for price comparison (fewer parts ≠ lower cost if qty increases)
- Documents design evolution for future reference

### Step 8: Items Needing Attention

Flag any parts with incomplete data before sending to vendor:

**Checklist:**

```
REVIEW BEFORE SENDING:
  ☐ All STEP files present in folders
  ☐ All revision letters assigned
  ☐ CSV BOMs match folder contents (no orphaned files)
  ☐ Material fields populated (no "DUMMY2" or blank)
  ☐ Thickness fields populated (no "TBD")
  ☐ Item names/descriptions meaningful (not just numbers)
  ☐ CHANGES column explains differences from previous quote
```

**Common Issues:**

| Issue | Example | Fix |
|-------|---------|-----|
| Missing material | `material: "DUMMY2"` | Update in PDM, re-export BOM |
| Missing thickness | `thickness: null` | Update in PDM, re-export BOM |
| Generic name | `name: "csp00460"` | Update in PDM with descriptive name |
| Wrong file extension | `csp00230.stp` | Rename to `.step` for consistency |

**Items from Context Needing Attention:**

```
csp00230 - ELECTRICAL BOX
  ⚠ Material shows "DUMMY2" in database
  ⚠ Thickness TBD
  → ACTION: Update PDM with actual material and thickness before sending quote

csp00460 - (no proper name)
  ⚠ Item needs descriptive name in database
  → ACTION: Add description in PDM
```

---

## Future Planning Notes

Track upcoming design changes that will require future quotes:

**Example: Tube Gauge Change**

```
PLANNED CHANGE (Not in current quote):
  All 2x2 tubes will change from 11 gauge (0.125") to 14 gauge (0.075")

  Affected parts:
    csp00010 - OUTSIDE CROSS TUBE
    csp00050 - FRONT POST
    csp00270 - DRAIN PIPE

  Timeline: Q3 2026

  When implementing:
    → Bump all affected parts to next revision (B→C)
    → Update thickness in PDM: 0.125 → 0.075
    → Note in CHANGES: "Gauge changed: 11ga -> 14ga (0.125 -> 0.075)"
```

**Why Document Future Changes:**

- Prevents accidentally mixing old/new design in same quote
- Helps estimate impact of design changes (how many parts affected?)
- Provides timeline context for vendor relationships

---

## Complete Workflow Checklist

Use this checklist for each quote bundle update:

```
☐ 1. Get fresh BOM from PDM (SQL query or API)
☐ 2. Check STEP file availability for all parts
☐ 3. Compare with previous quote bundle (inventory STP_Export/)
☐ 4. Determine revision bumps (A→B for changes, A for new)
☐ 5. Download fresh STEP files from PDM storage
☐ 6. Rename files with revision letters (csp00050_B.step)
☐ 7. Delete eliminated parts from folders
☐ 8. Update CSV BOMs with revisions and CHANGES notes
☐ 9. Document consolidations in README.txt
☐ 10. Review for missing/incomplete data (material, thickness, names)
☐ 11. Cross-check CSV against folder contents (no orphans)
☐ 12. Zip and send to vendor
```

---

## Vendor Submission Package

**Final Folder Structure:**

```
CSA00015_Quote_2026-08-04.zip
├── README.txt                          # Consolidation log, change summary
├── Tubes/
│   ├── Tubes_BOM.csv
│   ├── csp00010_B.step
│   ├── csp00050_B.step
│   └── csp00270_B.step
└── Sheetmetal/
    ├── Sheetmetal_BOM.csv
    ├── csp00120_A.step
    ├── csp00140_B.step
    ├── csp00150_B.step
    └── csp00230_A.step
```

**README.txt Template:**

```
PROJECT: CSA00015 - FINISHED ASSEMBLY
QUOTE REQUEST: Updated pricing
DATE: 2026-08-04

CHANGE SUMMARY:
- Consolidated 3 parts (rear posts and brackets now ambidextrous)
- Added 1 new part (electrical box)
- Updated 4 existing parts (see CHANGES column in BOMs)

Part count: 15 (was 18)
Material: STEEL_HSLA (all parts)

TUBES (4 parts):
  See Tubes/Tubes_BOM.csv for details
  All .step files in Tubes/ folder

SHEETMETAL (11 parts):
  See Sheetmetal/Sheetmetal_BOM.csv for details
  All .step files in Sheetmetal/ folder

NOTES:
- Parts with REV "A" are new to this quote
- Parts with REV "B" have changed since last quote (see CHANGES column)
- Previous parts csp00060, csp00120, csp00160 have been eliminated (consolidated)

Please quote:
1. Per-part pricing
2. Total cost for one complete assembly (quantities in BOM)
3. Lead time

Contact: Jack (jack@company.com)
```

---

## Troubleshooting

### Missing STEP Files

**Symptom:** Part in BOM but no STEP file in PDM

**Diagnosis:**
```sql
SELECT item_number, name
FROM items
WHERE item_number = 'csp00230'
  AND id NOT IN (SELECT item_id FROM files WHERE file_type = 'STP');
```

**Fix:**
1. Export STEP from Creo workspace
2. Upload via PDM Upload Service or API
3. Re-run Step 5 (download fresh files)

### Incorrect Material in PDM

**Symptom:** PDM shows "6061-T6 ALUMINUM" but vendor needs "STEEL_HSLA"

**Fix (Option 1 - Update PDM):**
```sql
UPDATE items SET material = 'STEEL_HSLA' WHERE item_number = 'csp00230';
```

**Fix (Option 2 - Override in CSV):**
- Manually edit CSV material column
- Add note: "Material override: PDM shows AL, actual is STEEL"

### File Naming Mismatches

**Symptom:** Downloaded file named `csp00050.step` but need `csp00050_B.step`

**Fix:**
```bash
# Rename manually after download
mv csp00050.step csp00050_B.step

# Or use script pattern from Step 5 with rev suffix
```

### CSV/Folder Mismatch

**Symptom:** CSV lists 15 parts but folder has 18 files

**Diagnosis:**
```bash
# Count files in folder
ls STP_Export/Tubes/*.step | wc -l

# Count rows in CSV (minus header)
tail -n +2 STP_Export/Tubes/Tubes_BOM.csv | wc -l
```

**Fix:**
- Remove obsolete files from folder
- Or add missing entries to CSV
- Goal: 1-to-1 match between CSV rows and .step files

---

## Related Documentation

- **39-KIT-SOURCING-STEP-EXPORT.md** - Ordering vendor kits (different from quoting)
- **03-DATABASE-SCHEMA.md** - `items` and `files` table schemas
- **20-COMMON-WORKFLOWS.md** - General PDM workflows
- **06-BOM-COST-ROLLUP-GUIDE.md** - Cost analysis after quotes return

---

## API Reference

### Get BOM Tree
```
GET /api/bom/{item_number}/tree
```

Returns nested BOM structure with quantities rolled up.

### Get Item Details
```
GET /api/items/{item_number}
```

Returns item properties and associated files array.

### Get File Download URL
```
GET /api/files/{file_id}/download
```

Returns signed URL for downloading file from storage (1-hour expiry).

### Example: Bulk File Download

```python
import requests

def download_quote_bundle(assembly, parts_list, output_folder):
    """
    Download STEP files for quote bundle.

    Args:
        assembly: Top assembly number (e.g., 'csa00015')
        parts_list: List of {'item': 'csp00050', 'rev': 'B', 'category': 'Tubes'}
        output_folder: Base path (e.g., 'STP_Export/')
    """
    API_BASE = "http://localhost:8001/api"

    for part in parts_list:
        # Get item details
        r = requests.get(f"{API_BASE}/items/{part['item']}")
        if r.status_code != 200:
            print(f"ERROR: Item {part['item']} not found")
            continue

        item = r.json()

        # Find STEP file
        step_file = next((f for f in item.get('files', [])
                          if f['file_type'] == 'STP'), None)
        if not step_file:
            print(f"WARNING: No STEP file for {part['item']}")
            continue

        # Get download URL
        r = requests.get(f"{API_BASE}/files/{step_file['id']}/download")
        download_url = r.json()['url']

        # Download and save
        r = requests.get(download_url)
        filename = f"{part['item']}_{part['rev']}.step"
        filepath = f"{output_folder}/{part['category']}/{filename}"

        with open(filepath, 'wb') as f:
            f.write(r.content)

        print(f"✓ {filepath}")

# Usage
parts_for_quote = [
    {'item': 'csp00050', 'rev': 'B', 'category': 'Tubes'},
    {'item': 'csp00140', 'rev': 'B', 'category': 'Sheetmetal'},
    {'item': 'csp00230', 'rev': 'A', 'category': 'Sheetmetal'}
]

download_quote_bundle('csa00015', parts_for_quote, 'STP_Export')
```

---

## Version History

| Date | Changes |
|------|---------|
| 2026-08-04 | Initial documentation - CSA00015 quote bundle process |
