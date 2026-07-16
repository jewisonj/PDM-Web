# Kit Sourcing STEP Export Guide

**Document ID:** 39
**Last Updated:** 2026-07-16
**Purpose:** Practical guide for exporting STEP files and BOMs for kit sourcing orders

---

## Overview

When sourcing kits from vendors (tubes, sheet metal, hardware bundles), we need to provide STEP files organized by category along with BOMs. This guide covers the complete process from querying the PDM BOM to delivering organized export packages.

**Typical Use Cases:**
- Tube cutting kit orders (e.g., SendCutSend)
- Sheet metal kit orders (flat/formed parts)
- Combined tube + sheet metal kits for assemblies
- Updated part replacements in existing kit orders

---

## Quick Reference

### API Endpoints

```bash
# 1. Get full BOM tree
GET http://localhost:8001/api/bom/{item_number}/tree

# 2. Get item details (includes files array)
GET http://localhost:8001/api/items/{part_number}

# 3. Get signed download URL for file
GET http://localhost:8001/api/files/{file_id}/download
```

### Export Folder Structure

```
{Assembly}_Kit_Export/
├── {Assembly}_Kit_BOM.csv           # Combined BOM with Category column
├── Tubes/
│   ├── Tubes_BOM.csv
│   └── *.step                       # STEP files for tubes
└── Sheetmetal/
    ├── Sheetmetal_BOM.csv
    └── *.step                       # STEP files for sheet metal
```

### CSV Format

**Category BOMs (Tubes_BOM.csv, Sheetmetal_BOM.csv):**
```csv
Qty,Number,Description,Material,Thickness
2,csp00010,OUTSIDE CROSS TUBE,304SS,0.125
1,csp00270,DRAIN SUMP,316SS,0.125
```

**Combined BOM ({Assembly}_Kit_BOM.csv):**
```csv
Qty,Number,Description,Material,Thickness,Category
2,csp00010,OUTSIDE CROSS TUBE,304SS,0.125,Tubes
1,csp00270,DRAIN SUMP,316SS,0.125,Sheetmetal
```

### Material Override Pattern

**IMPORTANT:** Material in PDM may not match what's ordered. Override as needed:

| Category | Material Override | Notes |
|----------|-------------------|-------|
| Tubes | 304SS | All tubes for this project |
| Sheetmetal | 316SS | All sheet metal for this project |

Thickness values come from PDM but material is specified per-kit based on project requirements.

---

## Step-by-Step Process

### Step 1: Query BOM Tree from PDM

Use the BOM tree API to get the complete bill of materials:

```bash
curl -s "http://localhost:8001/api/bom/csa00020/tree"
```

**Response Structure:**
```json
{
  "item_number": "csa00020",
  "name": "CLIMBING SPA ASSEMBLY",
  "revision": "C",
  "children": [
    {
      "item_number": "csp00010",
      "name": "OUTSIDE CROSS TUBE",
      "description": "OUTSIDE CROSS TUBE",
      "quantity": 2,
      "material": "6061-T6 ALUMINUM",
      "thickness": null,
      "needs_dxf": false,
      "is_supplier_part": false,
      "files": [
        {"id": "file-uuid", "file_type": "STEP", "file_path": "..."}
      ],
      "children": []
    }
  ]
}
```

### Step 2: Categorize Parts

**Automatic Classification:**

| Category | Criteria |
|----------|----------|
| **Tubes** | Description contains "TUBE", "POST", "RAIL", "PIPE" AND `needs_dxf=false` AND `thickness=null` |
| **Sheetmetal** | `needs_dxf=true` OR `thickness` is not null |
| **Excluded** | `is_supplier_part=true` (MMC, SPN prefixes) |

**Manual Override:**
- User can specify parts to exclude (e.g., `csp00540`)
- User can add parts with quantities not in BOM

**IMPORTANT Exclusions:**
- Parts with `mmc` prefix (McMaster-Carr catalog items)
- Parts with `spn` prefix (other supplier parts)
- These are flagged with `is_supplier_part=true` in the API response

### Step 3: Download STEP Files

For each part in the BOM:

1. **Get item details** to retrieve file metadata:
   ```bash
   curl -s "http://localhost:8001/api/items/csp00010"
   ```

2. **Extract STEP file ID** from the `files` array:
   ```python
   step_file = next((f for f in item.get('files', [])
                     if f.get('file_type') == 'STEP'), None)
   file_id = step_file['id']
   ```

3. **Get signed download URL**:
   ```bash
   curl -s "http://localhost:8001/api/files/{file_id}/download"
   ```

   Response:
   ```json
   {"url": "https://...supabase.co/storage/v1/object/sign/..."}
   ```

4. **Download file** from the signed URL:
   ```python
   import urllib.request
   urllib.request.urlretrieve(url, f'{dest_folder}/{part_num}.step')
   ```

### Step 4: Organize Export Package

Create the folder structure and copy files:

```python
import os
from pathlib import Path

# Create folders
base = Path("CSA00020_Kit_Export")
tubes = base / "Tubes"
sheetmetal = base / "Sheetmetal"

os.makedirs(tubes, exist_ok=True)
os.makedirs(sheetmetal, exist_ok=True)

# Copy files to appropriate folders
for part in categorized_parts['tubes']:
    shutil.copy(f'downloads/{part["number"]}.step', tubes)

for part in categorized_parts['sheetmetal']:
    shutil.copy(f'downloads/{part["number"]}.step', sheetmetal)
```

### Step 5: Generate BOM CSVs

```python
import csv

# Write Tubes BOM
with open(tubes / 'Tubes_BOM.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Qty', 'Number', 'Description'])
    for part in categorized_parts['tubes']:
        writer.writerow([part['qty'], part['number'], part['description']])

# Write Sheetmetal BOM
with open(sheetmetal / 'Sheetmetal_BOM.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Qty', 'Number', 'Description'])
    for part in categorized_parts['sheetmetal']:
        writer.writerow([part['qty'], part['number'], part['description']])

# Write Combined BOM
all_parts = [(p, 'Tubes') for p in categorized_parts['tubes']] + \
            [(p, 'Sheetmetal') for p in categorized_parts['sheetmetal']]

with open(base / f'{assembly}_Kit_BOM.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Qty', 'Number', 'Description', 'Category'])
    for part, category in all_parts:
        writer.writerow([part['qty'], part['number'], part['description'], category])
```

---

## Handling Updated Files

When vendor or engineer provides updated STEP files (e.g., after design review):

### Common File Naming Issues

Vendors may return files with variations:
- Suffix added: `csp00270_prt.stp`
- Wrong extension: `.stp` instead of `.step`
- Mixed case: `CSP00270.STP`

### Normalization Process

```python
import shutil
from pathlib import Path

def normalize_step_file(source_path, dest_folder):
    """
    Normalize STEP file name and copy to destination.

    Examples:
        csp00270_prt.stp → csp00270.step
        CSP00010.STP → csp00010.step
        csp00540_asm.step → csp00540.step
    """
    filename = Path(source_path).stem  # Get filename without extension

    # Strip common CAD suffixes
    suffixes = ['_prt', '_asm', '_drw', '_PRT', '_ASM', '_DRW']
    for suffix in suffixes:
        if filename.endswith(suffix):
            filename = filename[:-len(suffix)]
            break

    # Normalize to lowercase
    filename = filename.lower()

    # Ensure .step extension
    dest_path = Path(dest_folder) / f'{filename}.step'

    # Copy/overwrite
    shutil.copy(source_path, dest_path)
    print(f"Copied: {source_path} → {dest_path}")

    return dest_path
```

**Usage:**
```python
# User provides updated files
updated_files = [
    'vendor_feedback/csp00270_prt.stp',
    'vendor_feedback/csp00540_asm.stp'
]

for file in updated_files:
    normalize_step_file(file, 'CSA00020_Kit_Export/Tubes')
```

---

## Complete Python Script Template

```python
#!/usr/bin/env python3
"""
Kit Sourcing STEP Export Script
Exports STEP files and BOMs for kit orders
"""

import subprocess
import json
import csv
import urllib.request
import shutil
from pathlib import Path

API_BASE = "http://localhost:8001/api"

def get_bom_tree(assembly_number):
    """Get full BOM tree from PDM."""
    result = subprocess.run(
        ['curl', '-s', f'{API_BASE}/bom/{assembly_number}/tree'],
        capture_output=True, text=True
    )
    return json.loads(result.stdout)

def get_item(part_number):
    """Get item details including files."""
    result = subprocess.run(
        ['curl', '-s', f'{API_BASE}/items/{part_number}'],
        capture_output=True, text=True
    )
    return json.loads(result.stdout)

def get_download_url(file_id):
    """Get signed download URL for file."""
    result = subprocess.run(
        ['curl', '-s', f'{API_BASE}/files/{file_id}/download'],
        capture_output=True, text=True
    )
    return json.loads(result.stdout).get('url')

def download_step(part_number, dest_folder):
    """Download STEP file for a part."""
    item = get_item(part_number)

    # Find STEP file
    step_file = next((f for f in item.get('files', [])
                      if f.get('file_type') == 'STEP'), None)

    if not step_file:
        print(f"WARNING: No STEP file for {part_number}")
        return False

    # Get download URL
    url = get_download_url(step_file['id'])
    if not url:
        print(f"ERROR: Could not get download URL for {part_number}")
        return False

    # Download
    dest_path = Path(dest_folder) / f'{part_number}.step'
    urllib.request.urlretrieve(url, dest_path)
    print(f"Downloaded: {part_number}.step")
    return True

def categorize_bom(bom_tree, exclude_parts=None):
    """
    Categorize parts into tubes and sheetmetal.

    Returns:
        {
            'tubes': [{'number': 'csp00010', 'qty': 2, 'description': '...'}],
            'sheetmetal': [...]
        }
    """
    exclude_parts = exclude_parts or []
    tubes = []
    sheetmetal = []

    def process_node(node, parent_qty=1):
        # Skip supplier parts
        if node.get('is_supplier_part'):
            return

        # Skip excluded parts
        if node['item_number'] in exclude_parts:
            return

        qty = node.get('quantity', 1) * parent_qty

        # Categorize
        desc = node.get('description', '').upper()
        is_tube = any(kw in desc for kw in ['TUBE', 'POST', 'RAIL', 'PIPE'])
        is_sheet = node.get('needs_dxf') or node.get('thickness') is not None

        part = {
            'number': node['item_number'],
            'qty': qty,
            'description': node.get('description', ''),
            'thickness': node.get('thickness'),
            'material': node.get('material', '')
        }

        if is_tube and not is_sheet:
            tubes.append(part)
        elif is_sheet:
            sheetmetal.append(part)

        # Recurse
        for child in node.get('children', []):
            process_node(child, qty)

    process_node(bom_tree)
    return {'tubes': tubes, 'sheetmetal': sheetmetal}

def write_csv(filepath, parts, category=None, material_override=None):
    """
    Write BOM CSV file with Material and Thickness columns.

    Args:
        filepath: Output CSV path
        parts: List of part dicts with 'number', 'qty', 'description', 'thickness'
        category: If provided, adds Category column (for combined BOM)
        material_override: Material to use (overrides PDM value)
    """
    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)

        if category:
            writer.writerow(['Qty', 'Number', 'Description', 'Material', 'Thickness', 'Category'])
            for part, cat in parts:
                writer.writerow([
                    part['qty'], part['number'], part['description'],
                    material_override or part.get('material', ''),
                    part.get('thickness', ''), cat
                ])
        else:
            writer.writerow(['Qty', 'Number', 'Description', 'Material', 'Thickness'])
            for part in parts:
                writer.writerow([
                    part['qty'], part['number'], part['description'],
                    material_override or part.get('material', ''),
                    part.get('thickness', '')
                ])

    print(f"Wrote: {filepath}")

def export_kit(assembly_number, output_folder, exclude_parts=None):
    """
    Complete kit export process.

    Args:
        assembly_number: Top-level assembly (e.g., 'csa00020')
        output_folder: Base export folder path
        exclude_parts: List of part numbers to exclude
    """
    # Setup folders
    base = Path(output_folder)
    tubes_folder = base / 'Tubes'
    sheet_folder = base / 'Sheetmetal'

    tubes_folder.mkdir(parents=True, exist_ok=True)
    sheet_folder.mkdir(parents=True, exist_ok=True)

    # Get BOM
    print(f"Fetching BOM for {assembly_number}...")
    bom = get_bom_tree(assembly_number)

    # Categorize
    print("Categorizing parts...")
    categorized = categorize_bom(bom, exclude_parts)

    # Download files
    print("\nDownloading STEP files...")
    for part in categorized['tubes']:
        download_step(part['number'], tubes_folder)

    for part in categorized['sheetmetal']:
        download_step(part['number'], sheet_folder)

    # Write BOMs with material overrides
    # NOTE: Override materials per project requirements (PDM may differ)
    print("\nGenerating BOMs...")
    write_csv(tubes_folder / 'Tubes_BOM.csv', categorized['tubes'],
              material_override='304SS')
    write_csv(sheet_folder / 'Sheetmetal_BOM.csv', categorized['sheetmetal'],
              material_override='316SS')

    # Combined BOM
    all_parts = [(p, 'Tubes') for p in categorized['tubes']] + \
                [(p, 'Sheetmetal') for p in categorized['sheetmetal']]
    # For combined, write tubes then sheetmetal with respective materials
    with open(base / f'{assembly_number.upper()}_Kit_BOM.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Qty', 'Number', 'Description', 'Material', 'Thickness', 'Category'])
        for part in categorized['tubes']:
            writer.writerow([part['qty'], part['number'], part['description'],
                           '304SS', part.get('thickness', ''), 'Tubes'])
        for part in categorized['sheetmetal']:
            writer.writerow([part['qty'], part['number'], part['description'],
                           '316SS', part.get('thickness', ''), 'Sheetmetal'])

    print(f"\nExport complete: {base}")

if __name__ == '__main__':
    # Example usage
    export_kit(
        assembly_number='csa00020',
        output_folder='CSA00020_Kit_Export',
        exclude_parts=['csp00540']  # Optional exclusions
    )
