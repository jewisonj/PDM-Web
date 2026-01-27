# BOM Cost Rollup Tool - Get-BOMCost.ps1

## Overview

The **Get-BOMCost.ps1** script provides a powerful tool for calculating the estimated total cost of an assembly by recursively traversing the Bill of Materials (BOM) tree and summing component costs.

**Location:** `D:\PDM_PowerShell\Get-BOMCost.ps1`

---

## Purpose

This tool helps with:
- **Cost Estimation**: Calculate estimated prices for assemblies and subassemblies
- **Pricing Analysis**: Understand cost breakdown by assembly level
- **BOM Analysis**: Visualize the full hierarchical cost structure
- **Manufacturing Planning**: Support for MRP cost rollup calculations

---

## How It Works

### Algorithm

1. **Input:** Assembly item number (e.g., `wma20120`)
2. **Query Database:** Fetch the assembly's own price (`price_est`) from `items` table
3. **Get Children:** Query `bom` table for all direct children with quantities
4. **Recursive Traversal:** For each child:
   - Fetch child's price
   - Multiply by quantity
   - Recursively fetch children of child (subassemblies)
   - Accumulate all costs
5. **Circular Reference Detection:** Track parent chain to prevent infinite loops
6. **Output:** Hierarchical cost breakdown with subtotals

### Cost Formula

```
Total Cost = (Assembly Price × Qty) + (Sum of All Children Costs)

Where:
- Assembly Price = price_est from items table
- Children Costs = Recursively calculated for all subassemblies
- Qty = BOM quantity multiplied by parent quantity
```

---

## Usage

### Basic Syntax

```powershell
.\Get-BOMCost.ps1 -Assembly <ItemNumber> [-Quantity <Number>]
```

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `Assembly` | String | Yes | N/A | Item number to calculate cost for (e.g., `wma20120`, `csp0030`) |
| `Quantity` | Integer | No | 1 | Quantity multiplier for cost calculation |

### Examples

#### Single Assembly Cost
```powershell
.\Get-BOMCost.ps1 -Assembly "wma20120"
```

Output:
```
==================================================
  BOM Cost Rollup for wma20120
==================================================

[ASM] wma20120 x1 @ $50.00
  [PART] csp0030 x4 @ $2.50 = $10.00
  [ASM] sub_asm x2 @ $15.00
    [PART] csp0031 x2 @ $3.75 = $7.50
    [PART] csp0032 x1 @ $5.00 = $5.00
    Subtotal: $17.50 = $15.00 (Assembly) + $12.50 (Children)
  Subtotal: $77.50 = $50.00 (Assembly) + $27.50 (Children)

==================================================
  Total Estimated Cost: $77.50
==================================================
```

#### Multiple Quantity Cost
```powershell
.\Get-BOMCost.ps1 -Assembly "csp0030" -Quantity 5
```

Calculates cost for 5 units of the assembly (useful for manufacturing runs)

---

## Output Interpretation

### Color-Coded Display

The script uses color-coded output for easy reading:

- **Green [ASM]:** Assembly items that contain child parts (subassemblies)
- **Cyan [PART]:** Leaf items (parts with no children)
- **Magenta:** Subtotal breakdown lines showing cost composition
- **Yellow [!]:** Circular reference warning (if detected)

### Hierarchical Structure

- Indentation levels show BOM hierarchy depth
- Left indentation increases for nested subassemblies
- Costs are rolled up from bottom to top

### Cost Breakdown

Each subtotal shows:
```
Subtotal: $X.XX = $Y.YY (Assembly) + $Z.ZZ (Children)
```

Where:
- **$X.XX** = Total cost including all children
- **$Y.YY** = Cost of the assembly itself only
- **$Z.ZZ** = Cost of all child components combined

---

## Data Requirements

### Database Schema

The script queries two tables from `D:\PDM_Vault\pdm.sqlite`:

#### items Table
```sql
CREATE TABLE items (
    item_number TEXT NOT NULL PRIMARY KEY,
    price_est REAL,           -- Estimated cost per unit
    ... other fields
);
```

#### bom Table
```sql
CREATE TABLE bom (
    parent_item TEXT NOT NULL,  -- Assembly item
    child_item TEXT NOT NULL,   -- Component item
    quantity INTEGER NOT NULL,  -- Quantity in parent
    ... other fields
);
```

### Price Data Entry

Prices must be populated in the `items` table before using this tool:

#### From BOM-Watcher
Prices can be automatically populated by the **BOM-Watcher.ps1** service when BOM files are imported:

1. In Creo, export BOM tree with price column
2. Place file in `D:\PDM_Vault\CADData\BOM\`
3. BOM-Watcher automatically parses and updates `price_est`

#### Manual Entry
Insert prices directly into database:

```powershell
# Using sqlite3.exe
sqlite3.exe D:\PDM_Vault\pdm.sqlite "UPDATE items SET price_est=25.50 WHERE item_number='csp0030';"

# Or using Query-SQL function from PDM-Library.ps1
Exec-SQL "UPDATE items SET price_est=25.50 WHERE item_number='csp0030';"
```

---

## Circular Reference Handling

### What It Does

The script tracks the "parent chain" - the path from the root assembly down to the current item. If a part appears in its own parent chain, it's flagged as circular and skipped.

### Why This Matters

Circular references can occur if:
- A subassembly incorrectly contains itself in the BOM
- BOM data was manually edited with errors
- A part is used both at top level and in subassemblies (legitimate - not circular)

### Example

```
wma20120 (assembly)
├── csp0030 (part)
└── sub_asm (subassembly)
    └── wma20120 (CIRCULAR - would cause infinite recursion)

[!] wma20120 (circular reference - skipping)
```

---

## Troubleshooting

### Script Not Found

**Problem:** `Cannot find script Get-BOMCost.ps1`

**Solution:**
```powershell
# Navigate to script directory
cd D:\PDM_PowerShell

# Run with full path
.\Get-BOMCost.ps1 -Assembly "wma20120"
```

### Database Connection Error

**Problem:** `Database connection error` or `sqlite3.exe not found`

**Solution:**
1. Verify sqlite3.exe is in PATH or `D:\PDM_PowerShell\SQLite\`
2. Verify database file exists: `D:\PDM_Vault\pdm.sqlite`
3. Check file permissions - database must be readable

### Assembly Not Found

**Problem:** Script runs but shows no items (no output or error)

**Solution:**
1. Verify item exists in database:
   ```powershell
   sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT item_number FROM items WHERE item_number='wma20120';"
   ```
2. Verify item number case (internally normalized to lowercase):
   ```powershell
   .\Get-BOMCost.ps1 -Assembly "WMA20120"  # Script will convert to lowercase
   ```

### Prices Not Showing

**Problem:** All items show "no price" instead of dollar amounts

**Solution:**
1. Verify prices are populated in database:
   ```powershell
   sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT item_number, price_est FROM items WHERE price_est > 0 LIMIT 10;"
   ```
2. If empty, add prices via BOM-Watcher or manual entry (see "Price Data Entry" section above)

### Unexpected Cost Totals

**Problem:** Cost seems too high or too low

**Solution:**
1. Verify BOM quantities are correct:
   ```powershell
   sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT child_item, SUM(quantity) FROM bom WHERE parent_item='wma20120' GROUP BY child_item;"
   ```
2. Check if prices are per-unit or per-assembly
3. Review the hierarchical output to trace cost accumulation

---

## Integration with PDM Workflow

### BOM-Watcher Integration

**BOM-Watcher.ps1** automatically populates price data:

1. In Creo, create BOM export including `PRICE_EST` column
2. Save to `D:\PDM_Vault\CADData\BOM\[itemname].txt`
3. BOM-Watcher detects and parses file
4. Extracts prices and updates database
5. `Get-BOMCost.ps1` can then calculate total costs

### MLBOM-Watcher Integration

The **MLBOM-Watcher.ps1** also supports price extraction from multi-level BOM files with better hierarchy handling.

### Manufacturing Planning

Use cost rollup results for:
- **Pricing:** Set selling price based on component cost + margin
- **Profitability:** Analyze cost vs revenue
- **Design Optimization:** Identify high-cost assemblies for value engineering
- **Sourcing:** Decide whether to buy vs. make

---

## Advanced Usage

### Scripting with Costs

Integrate into PowerShell scripts for automated cost calculations:

```powershell
# Load results into variable
$costOutput = & .\Get-BOMCost.ps1 -Assembly "wma20120"

# Parse for specific values (advanced)
# Note: Script outputs formatted text, not structured data
# For programmatic access, modify script to return objects
```

### Batch Cost Calculations

Create a script to calculate costs for multiple assemblies:

```powershell
# assemblies.txt contains one item per line
$assemblies = Get-Content "assemblies.txt"

foreach ($assembly in $assemblies) {
    Write-Host "Calculating cost for $assembly..."
    .\Get-BOMCost.ps1 -Assembly $assembly
}
```

### Export Results

Redirect output to capture and export costs:

```powershell
.\Get-BOMCost.ps1 -Assembly "wma20120" | Out-File -Path "cost_report.txt"
```

---

## Performance Notes

- **Speed:** Typically completes in < 1 second for most BOMs
- **Scalability:** Performance depends on BOM depth and breadth
- **Database Load:** Minimal - uses efficient SQLite queries with GROUP BY
- **Memory:** Minimal - only tracks parent chain in memory

---

## Future Enhancements

Potential improvements could include:

- [ ] Export costs to CSV/Excel
- [ ] Cost comparison between revisions
- [ ] What-if analysis (price changes)
- [ ] Supplier cost variations
- [ ] Cost trend tracking over time
- [ ] Integration with MRP forecasting
- [ ] Structured output (JSON/CSV) for automation

---

## Related Tools

- **BOM-Watcher.ps1** - Automatically populates price data
- **MLBOM-Watcher.ps1** - Multi-level BOM processing with pricing
- **PDM-Database-Cleanup.ps1** - Database maintenance
- **PDM Browser** - Web interface to view BOMs and associated data

---

## Support & Documentation

- **Main PDM Documentation:** `D:\PDM_COMPLETE_OVERVIEW.md`
- **Database Schema:** `D:\Skills\database_schema.md`
- **Services Reference:** `D:\Skills\services.md`
- **PowerShell Scripts:** `D:\PDM_PowerShell\README.md`

---

**Last Updated:** 2025-01-03
