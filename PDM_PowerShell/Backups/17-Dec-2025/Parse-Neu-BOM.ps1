param(
    [string]$ItemNumber,
    [string]$NeuFile
)

. "D:\PDM_PowerShell\PDM-Library.ps1"

Write-Log "BOM: Parsing NEU for assembly $ItemNumber from $NeuFile"

if (-not (Test-Path $NeuFile)) {
    Write-Log "BOM ERROR: NEU file does not exist: $NeuFile"
    exit
}

# Read NEU lines
$lines = Get-Content $NeuFile

# Regex pattern for components:
# Recognizes:
#   Component CSP0030.PRT
#   Component LOWER_FRAME_SKEL.PRT
#   Component 4464K358.PRT
$regex = 'Component\s+([A-Za-z0-9_]+)\.PRT'

$children = @()

foreach ($line in $lines) {
    $m = [regex]::Match($line, $regex)
    if ($m.Success) {
        $rawChild = $m.Groups[1].Value

        # Normalize child:
        # 1. Lowercase
        # 2. Remove assembly skeleton default names if weird characters
        $child = $rawChild.ToLower()

        Write-Log "BOM: $ItemNumber → child $child"

        $children += $child
    }
}

# Nothing found?
if ($children.Count -eq 0) {
    Write-Log "BOM WARNING: No children found in NEU for $ItemNumber"
    exit
}

# Clear old BOM rows for this parent
Exec-SQL "
    DELETE FROM bom
    WHERE parent_item = '$ItemNumber';
"

# Insert all raw rows into bom_raw_temp
Exec-SQL "DELETE FROM bom_raw_temp;" 2>$null
Exec-SQL "
    CREATE TABLE IF NOT EXISTS bom_raw_temp (
        parent_item TEXT NOT NULL,
        child_item  TEXT NOT NULL
    );
"

foreach ($c in $children) {
    Exec-SQL "
        INSERT INTO bom_raw_temp (parent_item, child_item)
        VALUES ('$ItemNumber', '$c');
    "
}

# Collapse into grouped quantities
Exec-SQL "
    INSERT INTO bom (parent_item, child_item, quantity)
    SELECT parent_item, child_item, COUNT(*)
    FROM bom_raw_temp
    GROUP BY parent_item, child_item;
"

Write-Log "BOM extraction complete for assembly $ItemNumber"
