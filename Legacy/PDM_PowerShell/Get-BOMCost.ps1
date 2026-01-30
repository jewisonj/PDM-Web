# BOM Cost Rollup Tool
# Recursively calculates estimated price for an assembly based on BOM

param(
    [Parameter(Mandatory=$true)]
    [string]$Assembly,
    [int]$Quantity = 1
)

$Global:DBPath = "D:\PDM_Vault\pdm.sqlite"

function Query-SQLite {
    param([string]$Query)
    $output = & sqlite3.exe $Global:DBPath $Query 2>&1
    return $output
}

function Get-ItemPrice {
    param([string]$ItemNumber)
    
    $query = "SELECT price_est FROM items WHERE item_number = '$ItemNumber' LIMIT 1;"
    $result = Query-SQLite -Query $query
    
    if ($result -and $result -is [string]) {
        $trimmed = $result.Trim()
        if ($trimmed.Length -gt 0 -and -not $trimmed.Contains("Error:")) {
            try {
                return [decimal]$trimmed
            } catch {
                return 0
            }
        }
    }
    return 0
}

function Get-BOMCostRecursive {
    param(
        [string]$ItemNumber,
        [int]$Quantity = 1,
        [int]$Level = 0,
        [System.Collections.ArrayList]$ParentChain = @()
    )
    
    $indent = "  " * $Level
    
    # Check for circular reference - only if this item is in our PARENT chain
    if ($ParentChain -contains $ItemNumber) {
        Write-Host "${indent}[!] $ItemNumber (circular reference - skipping)" -ForegroundColor Yellow
        return 0
    }
    
    # Add this item to the parent chain for recursion
    $newChain = New-Object System.Collections.ArrayList
    $newChain.AddRange($ParentChain)
    $newChain.Add($ItemNumber) | Out-Null
    
    # Get item's own price
    $itemPrice = Get-ItemPrice -ItemNumber $ItemNumber
    
    # Get BOM children
    $bomQuery = "SELECT child_item, SUM(quantity) as total_qty FROM bom WHERE parent_item = '$ItemNumber' GROUP BY child_item;"
    $bomResult = Query-SQLite -Query $bomQuery
    
    if (-not $bomResult -or $bomResult.Contains("Error:")) {
        # Leaf item (no children) - print immediately
        $totalCost = $itemPrice * $Quantity
        $priceStr = if ($itemPrice -gt 0) { "`$$($itemPrice.ToString('N2'))" } else { "no price" }
        Write-Host "${indent}[PART] $ItemNumber x$Quantity @ $priceStr = `$$($totalCost.ToString('N2'))" -ForegroundColor Cyan
        return $totalCost
    }
    
    # Has children - print parent BEFORE recursing into children
    $priceStr = if ($itemPrice -gt 0) { "`$$($itemPrice.ToString('N2'))" } else { "no price" }
    Write-Host "${indent}[ASM] $ItemNumber x$Quantity @ $priceStr" -ForegroundColor Green
    
    # Parse BOM results
    $children = @()
    $bomLines = $bomResult -split "`n"
    foreach ($line in $bomLines) {
        if ($line.Trim().Length -gt 0) {
            $parts = $line -split '\|'
            if ($parts.Count -ge 2) {
                $children += @{
                    item = $parts[0]
                    qty = [int]$parts[1]
                }
            }
        }
    }
    
    # Calculate subtotal for children (recurse)
    $childrenCost = 0
    foreach ($child in $children) {
        $childCost = Get-BOMCostRecursive -ItemNumber $child.item -Quantity ($child.qty * $Quantity) -Level ($Level + 1) -ParentChain $newChain
        $childrenCost += $childCost
    }
    
    # Total cost = item price + children cost
    $totalCost = ($itemPrice * $Quantity) + $childrenCost
    $assemblyOnlyCost = $itemPrice * $Quantity
    
    # Print summary with breakdown
    Write-Host "${indent}  Subtotal: `$$($totalCost.ToString('N2')) = `$$($assemblyOnlyCost.ToString('N2')) (Assembly) + `$$($childrenCost.ToString('N2')) (Children)" -ForegroundColor Magenta
    
    return $totalCost
}

# Main execution
Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  BOM Cost Rollup for $Assembly" -ForegroundColor White
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

$totalCost = Get-BOMCostRecursive -ItemNumber $Assembly.ToLower() -Quantity $Quantity

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Total Estimated Cost: `$$($totalCost.ToString('N2'))" -ForegroundColor Green
if ($Quantity -gt 1) {
    Write-Host "  Per Unit: `$$($($totalCost / $Quantity).ToString('N2'))" -ForegroundColor Green
}
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""