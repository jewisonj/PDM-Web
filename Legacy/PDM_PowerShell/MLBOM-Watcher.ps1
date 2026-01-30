. "D:\PDM_PowerShell\PDM-Library.ps1"

# -----------------------------
# Configuration
# -----------------------------
$Global:PDMRoot     = "D:\PDM_Vault"
$Global:CADDataRoot = Join-Path $Global:PDMRoot "CADData"
$Global:BOMPath     = Join-Path $Global:CADDataRoot "BOM"

Write-Log "MLBOM-Watcher (Multi-Level BOM) Started."

# Ensure BOM folder exists
if (-not (Test-Path $Global:BOMPath)) {
    New-Item -ItemType Directory -Path $Global:BOMPath | Out-Null
    Write-Log "Created BOM folder: $Global:BOMPath"
}

$Global:SQLiteExe = "sqlite3.exe"
$Global:DBPath = "D:\PDM_Vault\pdm.sqlite"

function Exec-SQL {
    param([string]$Query)
    & $Global:SQLiteExe $Global:DBPath "$Query" 2>$null
}

# -----------------------------
# FileSystemWatcher - watches for MLBOM*.txt files
# -----------------------------
$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $Global:BOMPath
$watcher.Filter = "MLBOM*.txt"
$watcher.IncludeSubdirectories = $false
$watcher.EnableRaisingEvents = $true

Register-ObjectEvent $watcher Created -Action {
    $filePath = $Event.SourceEventArgs.FullPath
    $fileName = [System.IO.Path]::GetFileName($filePath)
    
    # Wait for file to be fully written
    Start-Sleep -Milliseconds 1500
    
    if (-not (Test-Path $filePath)) { return }
    
    # Wait for file to be readable
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
    
    if (-not $fileAccessible) { return }
    
    # Setup logging in event scope
    function Write-Log {
        param([string]$Message)
        $timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        $logPath = "D:\PDM_Vault\logs\pdm.log"
        Add-Content -Path $logPath -Value "$timestamp $Message"
    }
    
    $Global:SQLiteExe = "sqlite3.exe"
    $Global:DBPath = "D:\PDM_Vault\pdm.sqlite"
    
    function Exec-SQL {
        param([string]$Query)
        & $Global:SQLiteExe $Global:DBPath "$Query" 2>$null
    }
    
    Write-Log "Processing Multi-Level BOM file: $fileName"
    
    # Parse the file
    try {
        $lines = Get-Content -Path $filePath -ErrorAction Stop
    }
    catch {
        Write-Log "ERROR: Failed to read file $filePath : $_"
        Remove-Item -Path $filePath -Force -ErrorAction SilentlyContinue
        return
    }
    
    # Find header line and extract column positions
    $headerLine = $null
    $columnMap = @{}
    $headerLineIndex = -1
    
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match 'Model Name') {
            $headerLine = $lines[$i]
            $headerLineIndex = $i
            
            # Map column names to their starting positions
            $columnMap['MODEL'] = $headerLine.IndexOf('Model Name')
            $columnMap['DESCRIPTION'] = $headerLine.IndexOf('DESCRIPTION')
            $columnMap['PROJECT'] = $headerLine.IndexOf('PROJECT')
            $columnMap['PRO_MP_MASS'] = $headerLine.IndexOf('PRO_MP_MASS')
            $columnMap['SMT_THICKNESS'] = $headerLine.IndexOf('SMT_THICKNESS')
            $columnMap['PTC_MASTER_MATERIAL'] = $headerLine.IndexOf('PTC_MASTER_MATERIAL')
            $columnMap['CUT_LENGTH'] = $headerLine.IndexOf('CUT_LENGTH')
            $columnMap['CUT_TIME'] = $headerLine.IndexOf('CUT_TIME')
            $columnMap['PRICE_EST'] = $headerLine.IndexOf('PRICE_EST')
            
            Write-Log "Found header at line $i"
            Write-Log "  Column positions: MODEL=$($columnMap['MODEL']), DESC=$($columnMap['DESCRIPTION']), PROJ=$($columnMap['PROJECT']), MASS=$($columnMap['PRO_MP_MASS']), THICK=$($columnMap['SMT_THICKNESS']), MAT=$($columnMap['PTC_MASTER_MATERIAL']), CUTLEN=$($columnMap['CUT_LENGTH']), CUTTIME=$($columnMap['CUT_TIME']), PRICE=$($columnMap['PRICE_EST'])"
            break
        }
    }
    
    if ($null -eq $headerLine) {
        Write-Log "ERROR: Could not find header line with 'Model Name'"
        Remove-Item -Path $filePath -Force -ErrorAction SilentlyContinue
        return
    }
    
    # Helper function to extract column value based on position
    function Get-ColumnValue {
        param(
            [string]$Line,
            [string]$ColumnName,
            [string]$NextColumnName = $null
        )
        
        $startPos = $columnMap[$ColumnName]
        if ($startPos -lt 0 -or $startPos -ge $Line.Length) { return '' }
        
        $endPos = $Line.Length
        if ($NextColumnName -and $columnMap.ContainsKey($NextColumnName) -and $columnMap[$NextColumnName] -gt $startPos) {
            $endPos = $columnMap[$NextColumnName]
        }
        
        $length = $endPos - $startPos
        if ($length -le 0) { return '' }
        if ($startPos + $length -gt $Line.Length) { $length = $Line.Length - $startPos }
        
        return $Line.Substring($startPos, $length).Trim()
    }
    
    # Helper function to get indent level (number of leading spaces / 2)
    function Get-IndentLevel {
        param([string]$Line)
        $match = [regex]::Match($Line, '^(\s*)')
        return [math]::Floor($match.Groups[1].Length / 2)
    }
    
    # Helper to extract item number from model name
    # Handles: CSP00010.PRT, CSP00020<CSP00025>.PRT, MMC4464K358.PRT, SPNTANK.PRT
    function Get-ItemNumber {
        param([string]$ModelName)
        
        $modelName = $ModelName.Trim()
        
        # Skip pattern lines like "Pattern 2 of MMC92240A542.PRT"
        if ($modelName -match '^Pattern \d+ of') { return $null }
        
        # Handle family table instances: CSP00020<CSP00025>.PRT -> csp00020
        if ($modelName -match '^([A-Za-z]{3}[A-Za-z0-9]+)<[^>]+>\.(PRT|ASM)') {
            return $matches[1].ToLower()
        }
        
        # Handle standard parts: CSP00010.PRT, MMC4464K358.PRT, SPNTANK.PRT
        if ($modelName -match '^([A-Za-z]{3}[A-Za-z0-9]+)\.(PRT|ASM)') {
            return $matches[1].ToLower()
        }
        
        # Handle skeleton parts: CSA00030_SKEL.PRT -> skip
        if ($modelName -match '_SKEL\.PRT') { return $null }
        
        return $null
    }
    
    # Helper to check if model is an assembly
    function Is-Assembly {
        param([string]$ModelName)
        return $ModelName -match '\.ASM$'
    }
    
    # Track all items and their properties
    $allItems = @{}
    
    # Track BOM relationships: parent -> @{ child -> qty }
    $bomRelationships = @{}
    
    # Assembly stack to track current parent at each level
    # Index = indent level, Value = item_number
    $assemblyStack = @{}
    
    # Process data lines (skip header and separator)
    $startLine = $headerLineIndex + 2  # Skip header and --- line
    
    for ($i = $startLine; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]
        
        # Skip empty lines
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        
        # Skip separator lines
        if ($line -match '^[\s-]*$') { continue }
        
        # Skip pattern reference lines
        if ($line -match 'Pattern \d+ of') { continue }
        
        # Skip system/reference items
        if ($line -match 'Materials|ASM_RIGHT|ASM_TOP|ASM_FRONT|ASM_DEF_CSYS|Insert Here|APNT|SIM_PART|Current Rep:') { continue }
        
        # Get indent level
        $indentLevel = Get-IndentLevel $line
        
        # Extract model name from the line
        $modelEndPos = if ($columnMap['DESCRIPTION'] -gt 0) { $columnMap['DESCRIPTION'] } else { 30 }
        $modelPart = $line.Substring(0, [Math]::Min($modelEndPos, $line.Length)).Trim()
        
        # Get item number
        $itemNumber = Get-ItemNumber $modelPart
        if ($null -eq $itemNumber) { continue }
        
        $isAsm = Is-Assembly $modelPart
        
        # Extract properties using column positions
        $description = Get-ColumnValue $line 'DESCRIPTION' 'PROJECT'
        $project = Get-ColumnValue $line 'PROJECT' 'PRO_MP_MASS'
        $massStr = Get-ColumnValue $line 'PRO_MP_MASS' 'SMT_THICKNESS'
        $thicknessStr = Get-ColumnValue $line 'SMT_THICKNESS' 'PTC_MASTER_MATERIAL'
        $material = Get-ColumnValue $line 'PTC_MASTER_MATERIAL' 'CUT_LENGTH'
        $cutLengthStr = Get-ColumnValue $line 'CUT_LENGTH' 'CUT_TIME'
        $cutTimeStr = Get-ColumnValue $line 'CUT_TIME' 'PRICE_EST'
        $priceEstStr = Get-ColumnValue $line 'PRICE_EST'
        
        # Convert to numbers
        $mass = if ($massStr -match '^\d+(\.\d+)?$') { [double]$massStr } else { $null }
        $thickness = if ($thicknessStr -match '^\d+(\.\d+)?$') { [double]$thicknessStr } else { $null }
        $cutLength = if ($cutLengthStr -match '^\d+(\.\d+)?$') { [double]$cutLengthStr } else { $null }
        $cutTime = if ($cutTimeStr -match '^\d+(\.\d+)?$') { [double]$cutTimeStr } else { $null }
        $priceEst = if ($priceEstStr -match '^\d+(\.\d+)?$') { [double]$priceEstStr } else { $null }
        
        # Detect supplier parts
        $isSupplierPart = $false
        $supplierPrefix = $null
        $supplierPN = $null
        
        if ($itemNumber -match '^(mmc|spn)(.+)$') {
            $isSupplierPart = $true
            $supplierPrefix = $matches[1]
            $supplierPN = $matches[2]
        }
        
        # Store/update item properties (keep first occurrence's properties, or update if better data)
        if (-not $allItems.ContainsKey($itemNumber)) {
            $allItems[$itemNumber] = @{
                Description = $description
                Project = $project
                Material = $material
                Mass = $mass
                Thickness = $thickness
                CutLength = $cutLength
                CutTime = $cutTime
                PriceEst = $priceEst
                IsSupplier = $isSupplierPart
                SupplierPrefix = $supplierPrefix
                SupplierPN = $supplierPN
                IsAssembly = $isAsm
            }
        }
        
        # Update assembly stack
        if ($isAsm) {
            $assemblyStack[$indentLevel] = $itemNumber
            # Clear deeper levels
            $keysToRemove = $assemblyStack.Keys | Where-Object { $_ -gt $indentLevel }
            foreach ($k in $keysToRemove) { $assemblyStack.Remove($k) }
        }
        
        # Find parent assembly (one level up in indent)
        $parentLevel = $indentLevel - 1
        $parentItem = $null
        
        if ($parentLevel -ge 0 -and $assemblyStack.ContainsKey($parentLevel)) {
            $parentItem = $assemblyStack[$parentLevel]
        }
        
        # Add BOM relationship if we have a parent
        if ($null -ne $parentItem) {
            if (-not $bomRelationships.ContainsKey($parentItem)) {
                $bomRelationships[$parentItem] = @{}
            }
            
            if ($bomRelationships[$parentItem].ContainsKey($itemNumber)) {
                $bomRelationships[$parentItem][$itemNumber]++
            } else {
                $bomRelationships[$parentItem][$itemNumber] = 1
            }
        }
    }
    
    Write-Log "Parsed $($allItems.Count) unique items, $($bomRelationships.Count) assemblies with BOMs"
    
    # Now update the database
    $escapedFile = $fileName.Replace("'", "''")
    
    # 1. Create/update all items
    foreach ($itemNumber in $allItems.Keys) {
        $itemData = $allItems[$itemNumber]
        
        # Check if item exists
        $exists = & $Global:SQLiteExe $Global:DBPath "SELECT COUNT(*) FROM items WHERE item_number='$itemNumber';" 2>$null
        
        if ([int]$exists -eq 0) {
            # Create new item
            if ($itemData.IsSupplier) {
                $suppPrefix = $itemData.SupplierPrefix
                $suppPN = $itemData.SupplierPN.Replace("'", "''")
                Exec-SQL "INSERT INTO items (item_number, revision, iteration, lifecycle_state, is_supplier_part, supplier_prefix, supplier_pn) VALUES ('$itemNumber', 'A', 1, 'Design', 1, '$suppPrefix', '$suppPN');"
                Write-Log "  Created SUPPLIER item: $itemNumber"
            } else {
                Exec-SQL "INSERT INTO items (item_number, revision, iteration, lifecycle_state, is_supplier_part) VALUES ('$itemNumber', 'A', 1, 'Design', 0);"
                Write-Log "  Created item: $itemNumber"
            }
        }
        
        # Update item properties
        $desc = ($itemData.Description -replace "'", "''")
        $proj = ($itemData.Project -replace "'", "''")
        $mat = ($itemData.Material -replace "'", "''")
        $mass = if ($null -ne $itemData.Mass) { $itemData.Mass } else { "NULL" }
        $thick = if ($null -ne $itemData.Thickness) { $itemData.Thickness } else { "NULL" }
        $cutLen = if ($null -ne $itemData.CutLength) { $itemData.CutLength } else { "NULL" }
        $cutTime = if ($null -ne $itemData.CutTime) { $itemData.CutTime } else { "NULL" }
        $priceEst = if ($null -ne $itemData.PriceEst) { $itemData.PriceEst } else { "NULL" }
        
        # Only update properties that have values (don't overwrite with empty)
        $updateParts = @()
        if ($desc) { $updateParts += "description='$desc'" }
        if ($proj) { $updateParts += "project='$proj'" }
        if ($mat) { $updateParts += "material='$mat'" }
        if ($mass -ne "NULL") { $updateParts += "mass=$mass" }
        if ($thick -ne "NULL") { $updateParts += "thickness=$thick" }
        if ($cutLen -ne "NULL") { $updateParts += "cut_length=$cutLen" }
        if ($cutTime -ne "NULL") { $updateParts += "cut_time=$cutTime" }
        if ($priceEst -ne "NULL") { $updateParts += "price_est=$priceEst" }
        $updateParts += "modified_at=CURRENT_TIMESTAMP"
        
        if ($updateParts.Count -gt 1) {
            $updateSQL = "UPDATE items SET " + ($updateParts -join ", ") + " WHERE item_number='$itemNumber';"
            Exec-SQL $updateSQL
        }
    }
    
    Write-Log "Updated properties for $($allItems.Count) items"
    
    # 2. Update BOM relationships for each assembly
    foreach ($parentItem in $bomRelationships.Keys) {
        $children = $bomRelationships[$parentItem]
        
        # Delete old BOM entries for this parent
        Exec-SQL "DELETE FROM bom WHERE parent_item='$parentItem';"
        
        # Insert new BOM entries
        foreach ($childItem in $children.Keys) {
            $qty = $children[$childItem]
            Exec-SQL "INSERT INTO bom (parent_item, child_item, quantity, source_file) VALUES ('$parentItem', '$childItem', $qty, '$escapedFile');"
        }
        
        Write-Log "  BOM updated: $parentItem -> $($children.Count) children"
    }
    
    Write-Log "Multi-Level BOM update completed: $($allItems.Count) items, $($bomRelationships.Count) assemblies"
    
    # Delete the file
    try {
        Remove-Item -Path $filePath -Force
        Write-Log "Deleted processed MLBOM file: $fileName"
    }
    catch {
        Write-Log "ERROR: Failed to delete $fileName : $_"
    }
}

Write-Host "MLBOM-Watcher (Multi-Level BOM) is running..."
Write-Host "Monitoring: $Global:BOMPath for MLBOM*.txt files"
Write-Log "MLBOM-Watcher monitoring: $Global:BOMPath for MLBOM*.txt files"

while ($true) {
    Start-Sleep -Seconds 2
}
