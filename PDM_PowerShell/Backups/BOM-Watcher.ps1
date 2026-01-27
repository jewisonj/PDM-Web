. "D:\PDM_PowerShell\PDM-Library.ps1"

# -----------------------------
# Configuration
# -----------------------------
$Global:PDMRoot     = "D:\PDM_Vault"
$Global:CADDataRoot = Join-Path $Global:PDMRoot "CADData"
$Global:BOMPath     = Join-Path $Global:CADDataRoot "BOM"

Write-Log "BOM-Watcher Started."

# Ensure BOM folder exists
if (-not (Test-Path $Global:BOMPath)) {
    New-Item -ItemType Directory -Path $Global:BOMPath | Out-Null
    Write-Log "Created BOM folder: $Global:BOMPath"
}

# -----------------------------
# FileSystemWatcher
# -----------------------------
$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $Global:BOMPath
$watcher.Filter = "*.txt"
$watcher.IncludeSubdirectories = $false
$watcher.EnableRaisingEvents = $true

Register-ObjectEvent $watcher Created -Action {
    $filePath = $Event.SourceEventArgs.FullPath
    $fileName = [System.IO.Path]::GetFileName($filePath)
    
    # Wait for file to be fully written
    Start-Sleep -Milliseconds 1000
    
    # Check if file still exists
    if (-not (Test-Path $filePath)) {
        return
    }
    
    # Wait for file to be readable (not locked)
    $maxRetries = 5
    $retryCount = 0
    $fileAccessible = $false
    
    while ($retryCount -lt $maxRetries) {
        try {
            $testStream = [System.IO.File]::Open($filePath, 'Open', 'Read', 'None')
            $testStream.Close()
            $fileAccessible = $true
            break
        }
        catch {
            Start-Sleep -Milliseconds 500
            $retryCount++
        }
    }
    
    if (-not $fileAccessible) {
        return
    }
    
    # Setup logging in event scope
    function Write-Log {
        param([string]$Message)
        $timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        $logPath = "D:\PDM_Vault\logs\pdm.log"
        Add-Content -Path $logPath -Value "$timestamp $Message"
    }
    
    # Setup SQL functions in event scope
    $Global:SQLiteExe = "sqlite3.exe"
    $Global:DBPath = "D:\PDM_Vault\pdm.sqlite"
    
    function Exec-SQL {
        param([string]$Query)
        & $Global:SQLiteExe $Global:DBPath "$Query" 2>$null
    }
    
    Write-Log "Processing BOM file: $fileName"
    
    # Parse the file
    try {
        $lines = Get-Content -Path $filePath -ErrorAction Stop
    }
    catch {
        Write-Log "ERROR: Failed to read file $filePath : $_"
        Remove-Item -Path $filePath -Force -ErrorAction SilentlyContinue
        return
    }
    
    # Find parent assembly
    $parentItem = $null
    foreach ($line in $lines) {
        $trimmedLine = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmedLine)) { continue }
        if ($trimmedLine -match '^-+') { continue }
        if ($trimmedLine -match 'Model Name') { continue }
        
        if ($trimmedLine -match '([A-Za-z]{3}\d{4,6})\.(ASM|asm)') {
            $parentItem = $matches[1].ToLower()
            Write-Log "Parent assembly: $parentItem"
            break
        }
    }
    
    if ($null -eq $parentItem) {
        Write-Log "ERROR: Could not find parent assembly"
        Remove-Item -Path $filePath -Force -ErrorAction SilentlyContinue
        return
    }
    
    # Parse child items - ONLY lines with 3+ leading spaces (excludes parent line)
    $children = @{}
    $startParsing = $false
    
    foreach ($line in $lines) {
        if ($line -match '^-+$' -or $line -match '^\s*Model Name') {
            $startParsing = $true
            continue
        }
        if (-not $startParsing) { continue }
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        if ($line -match 'Materials|ASM_RIGHT|ASM_TOP|ASM_FRONT|ASM_DEF_CSYS|Insert Here|APNT|SIM_PART') { continue }
        
        # Match parts - internal (wmp20010) OR supplier (mmc4464k478, spn91694a345)
        # Parent line: " WMA20120.ASM" (1 space)
        # Child lines: "   WMP20080.PRT" or "   MMC4464K478.PRT" (3+ spaces)
        if ($line -match '^\s{3,}((?:[A-Za-z]{3}\d{4,6})|(?:(?:mmc|spn)[A-Za-z0-9]+))\.(PRT|ASM|prt|asm)?') {
            $itemNumber = $matches[1].ToLower()
            
            # Detect if this is a supplier part
            $isSupplierPart = $false
            $supplierPrefix = $null
            $supplierPN = $null
            
            if ($itemNumber -match '^(mmc|spn)(.+)$') {
                $isSupplierPart = $true
                $supplierPrefix = $matches[1]  # 'mmc' or 'spn'
                $supplierPN = $matches[2]      # '4464k478' or '91694a345'
            }
            
            # Parse by fixed column positions from header alignment
            # Model(0-16), Description(17-29), Project(30-47), Material(48-68), Mass(69-81), Thickness(82-96), CutLength(97+)
            $lineLength = $line.Length
            
            $description = if ($lineLength -gt 17) { $line.Substring(17, [Math]::Min(13, $lineLength - 17)).Trim() } else { '' }
            $project = if ($lineLength -gt 30) { $line.Substring(30, [Math]::Min(18, $lineLength - 30)).Trim() } else { '' }
            $material = if ($lineLength -gt 48) { $line.Substring(48, [Math]::Min(21, $lineLength - 48)).Trim() } else { '' }
            $massStr = if ($lineLength -gt 69) { $line.Substring(69, [Math]::Min(13, $lineLength - 69)).Trim() } else { '' }
            $thicknessStr = if ($lineLength -gt 82) { $line.Substring(82, [Math]::Min(15, $lineLength - 82)).Trim() } else { '' }
            $cutLengthStr = if ($lineLength -gt 97) { $line.Substring(97).Trim() } else { '' }
            
            # Convert to numbers
            $mass = if ($massStr -match '^\d+(\.\d+)?$') { [double]$massStr } else { $null }
            $thickness = if ($thicknessStr -match '^\d+(\.\d+)?$') { [double]$thicknessStr } else { $null }
            $cutLength = if ($cutLengthStr -match '^\d+(\.\d+)?$') { [double]$cutLengthStr } else { $null }
            
            # Add or increment quantity
            if ($children.ContainsKey($itemNumber)) {
                $children[$itemNumber].Quantity++
            }
            else {
                $children[$itemNumber] = @{
                    Quantity = 1
                    Description = $description
                    Project = $project
                    Material = $material
                    Mass = $mass
                    Thickness = $thickness
                    CutLength = $cutLength
                    IsSupplier = $isSupplierPart
                    SupplierPrefix = $supplierPrefix
                    SupplierPN = $supplierPN
                }
            }
            
            Write-Log "  Found: $itemNumber (qty: $($children[$itemNumber].Quantity))$(if ($isSupplierPart) {' [SUPPLIER]'} else {''})"
        }
    }
    
    if ($children.Count -eq 0) {
        Write-Log "WARNING: No child items found"
        Remove-Item -Path $filePath -Force -ErrorAction SilentlyContinue
        return
    }
    
    # Update database
    Write-Log "Updating BOM for $parentItem"
    
    # Ensure parent item exists
    $parentExists = & $Global:SQLiteExe $Global:DBPath "SELECT COUNT(*) FROM items WHERE item_number='$parentItem';" 2>$null
    if ([int]$parentExists -eq 0) {
        Exec-SQL "INSERT INTO items (item_number, name, revision, iteration, lifecycle_state, description) VALUES ('$parentItem', 'Assembly', 'A', 1, 'Design', 'Assembly');"
        Write-Log "  Created item record for $parentItem"
    }
    
    # Delete old BOM entries
    Exec-SQL "DELETE FROM bom WHERE parent_item='$parentItem';"
    Write-Log "  Cleared old BOM entries"
    
    # Insert new BOM entries and update item properties
    foreach ($childItem in $children.Keys) {
        $childData = $children[$childItem]
        $qty = $childData.Quantity
        $escapedFile = $fileName.Replace("'", "''")
        
        # Ensure child item exists in items table
        $childExists = & $Global:SQLiteExe $Global:DBPath "SELECT COUNT(*) FROM items WHERE item_number='$childItem';" 2>$null
        if ([int]$childExists -eq 0) {
            # Create item - different logic for supplier vs internal parts
            if ($childData.IsSupplier) {
                # Supplier part
                $suppPrefix = $childData.SupplierPrefix
                $suppPN = $childData.SupplierPN.Replace("'", "''")
                Exec-SQL "INSERT INTO items (item_number, revision, iteration, lifecycle_state, is_supplier_part, supplier_prefix, supplier_pn) VALUES ('$childItem', 'A', 1, 'Design', 1, '$suppPrefix', '$suppPN');"
                Write-Log "  Created SUPPLIER item: $childItem ($suppPrefix-$suppPN)"
            }
            else {
                # Internal part
                Exec-SQL "INSERT INTO items (item_number, revision, iteration, lifecycle_state, is_supplier_part) VALUES ('$childItem', 'A', 1, 'Design', 0);"
                Write-Log "  Created item record for $childItem"
            }
        }
        
        # Insert BOM relationship
        Exec-SQL "INSERT INTO bom (parent_item, child_item, quantity, source_file) VALUES ('$parentItem', '$childItem', $qty, '$escapedFile');"
        Write-Log "  BOM: $parentItem -> $childItem (qty: $qty)"
        
        # Update item properties (both internal and supplier)
        $desc = $childData.Description.Replace("'", "''")
        $proj = $childData.Project.Replace("'", "''")
        $mat = $childData.Material.Replace("'", "''")
        $mass = if ($null -ne $childData.Mass) { $childData.Mass } else { "NULL" }
        $thick = if ($null -ne $childData.Thickness) { $childData.Thickness } else { "NULL" }
        $cutLen = if ($null -ne $childData.CutLength) { $childData.CutLength } else { "NULL" }
        
        if ($childData.IsSupplier) {
            # Supplier part - update with supplier-specific fields
            $suppPrefix = $childData.SupplierPrefix
            $suppPN = $childData.SupplierPN.Replace("'", "''")
            Exec-SQL "UPDATE items SET description='$desc', project='$proj', material='$mat', mass=$mass, thickness=$thick, cut_length=$cutLen, is_supplier_part=1, supplier_prefix='$suppPrefix', supplier_pn='$suppPN', modified_at=CURRENT_TIMESTAMP WHERE item_number='$childItem';"
        }
        else {
            # Internal part - standard update
            Exec-SQL "UPDATE items SET description='$desc', project='$proj', material='$mat', mass=$mass, thickness=$thick, cut_length=$cutLen, modified_at=CURRENT_TIMESTAMP WHERE item_number='$childItem';"
        }
        Write-Log "  Updated properties for $childItem"
    }
    
    Write-Log "BOM update completed for $parentItem"
    
    # Delete the file
    try {
        Remove-Item -Path $filePath -Force
        Write-Log "Deleted processed BOM file: $fileName"
    }
    catch {
        Write-Log "ERROR: Failed to delete $fileName : $_"
    }
}

Write-Host "BOM-Watcher is running..."
Write-Host "Monitoring: $Global:BOMPath"
Write-Log "BOM-Watcher monitoring: $Global:BOMPath"

while ($true) {
    Start-Sleep -Seconds 2
}