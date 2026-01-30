. "D:\PDM_PowerShell\PDM-Library.ps1"

# -----------------------------
# Configuration
# -----------------------------
$Global:PDMRoot     = "D:\PDM_Vault"
$Global:CADDataRoot = Join-Path $Global:PDMRoot "CADData"
$Global:ParamsPath  = Join-Path $Global:CADDataRoot "ParameterUpdate"

Write-Log "Part-Parameter-Watcher Started."

# Ensure ParameterUpdate folder exists
if (-not (Test-Path $Global:ParamsPath)) {
    New-Item -ItemType Directory -Path $Global:ParamsPath | Out-Null
    Write-Log "Created ParameterUpdate folder: $Global:ParamsPath"
}

# -----------------------------
# FileSystemWatcher
# -----------------------------
$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $Global:ParamsPath
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
    
    Write-Log "Processing Part Parameter file: $fileName"
    
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
    
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match 'Model Name') {
            $headerLine = $lines[$i]
            
            # Map column names to their starting positions
            $columnMap['DESCRIPTION'] = $headerLine.IndexOf('DESCRIPTION')
            $columnMap['PROJECT'] = $headerLine.IndexOf('PROJECT')
            $columnMap['PRO_MP_MASS'] = $headerLine.IndexOf('PRO_MP_MASS')
            $columnMap['PTC_MASTER_MATERIAL'] = $headerLine.IndexOf('PTC_MASTER_MATERIAL')
            $columnMap['CUT_LENGTH'] = $headerLine.IndexOf('CUT_LENGTH')
            $columnMap['SMT_THICKNESS'] = $headerLine.IndexOf('SMT_THICKNESS')
            $columnMap['CUT_TIME'] = $headerLine.IndexOf('CUT_TIME')
            $columnMap['PRICE_EST'] = $headerLine.IndexOf('PRICE_EST')
            
            Write-Log "Found header at line $i, parsed column positions"
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
        if ($startPos -lt 0 -or $startPos -ge $Line.Length) {
            return ''
        }
        
        # Determine end position (either next column or end of line)
        $endPos = $Line.Length
        if ($NextColumnName -and $columnMap[$NextColumnName] -gt $startPos) {
            $endPos = $columnMap[$NextColumnName]
        }
        
        $length = $endPos - $startPos
        if ($length -le 0) {
            return ''
        }
        
        return $Line.Substring($startPos, $length).Trim()
    }
    
    # Find the part (first non-header, non-separator line with a part number)
    $partItem = $null
    $partData = $null
    
    foreach ($line in $lines) {
        $trimmedLine = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmedLine)) { continue }
        if ($trimmedLine -match '^-+') { continue }
        if ($trimmedLine -match 'Model Name') { continue }
        
        # Match single part line - should be first non-indented line with .PRT or .ASM
        # Format: " WMP20080.PRT" (1-2 spaces, not 3+)
        if ($line -match '^\s{1,2}((?:[A-Za-z]{3}\d{4,6})|(?:(?:mmc|spn)[A-Za-z0-9]+))\.(PRT|ASM|prt|asm)') {
            $partItem = $matches[1].ToLower()
            
            # Detect if this is a supplier part
            $isSupplierPart = $false
            $supplierPrefix = $null
            $supplierPN = $null
            
            if ($partItem -match '^(mmc|spn)(.+)$') {
                $isSupplierPart = $true
                $supplierPrefix = $matches[1]  # 'mmc' or 'spn'
                $supplierPN = $matches[2]      # '4464k478' or '91694a345'
            }
            
            # Extract values using column positions
            $description = Get-ColumnValue $line 'DESCRIPTION' 'PROJECT'
            $project = Get-ColumnValue $line 'PROJECT' 'PRO_MP_MASS'
            $massStr = Get-ColumnValue $line 'PRO_MP_MASS' 'PTC_MASTER_MATERIAL'
            $material = Get-ColumnValue $line 'PTC_MASTER_MATERIAL' 'CUT_LENGTH'
            $cutLengthStr = Get-ColumnValue $line 'CUT_LENGTH' 'SMT_THICKNESS'
            $thicknessStr = Get-ColumnValue $line 'SMT_THICKNESS' 'CUT_TIME'
            $cutTimeStr = Get-ColumnValue $line 'CUT_TIME' 'PRICE_EST'
            $priceEstStr = Get-ColumnValue $line 'PRICE_EST'
            
            # Convert to numbers
            $mass = if ($massStr -match '^\d+(\.\d+)?$') { [double]$massStr } else { $null }
            $thickness = if ($thicknessStr -match '^\d+(\.\d+)?$') { [double]$thicknessStr } else { $null }
            $cutLength = if ($cutLengthStr -match '^\d+(\.\d+)?$') { [double]$cutLengthStr } else { $null }
            $cutTime = if ($cutTimeStr -match '^\d+(\.\d+)?$') { [double]$cutTimeStr } else { $null }
            $priceEst = if ($priceEstStr -match '^\d+(\.\d+)?$') { [double]$priceEstStr } else { $null }
            
            $partData = @{
                ItemNumber = $partItem
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
            }
            
            Write-Log "Found part: $partItem$(if ($isSupplierPart) {' [SUPPLIER]'} else {''})"
            break
        }
    }
    
    if ($null -eq $partItem) {
        Write-Log "ERROR: Could not find part in file"
        Remove-Item -Path $filePath -Force -ErrorAction SilentlyContinue
        return
    }
    
    # Update database
    Write-Log "Updating parameters for $partItem"
    
    # Check if item exists
    $itemExists = & $Global:SQLiteExe $Global:DBPath "SELECT COUNT(*) FROM items WHERE item_number='$partItem';" 2>$null
    
    if ([int]$itemExists -eq 0) {
        # Create new item
        if ($partData.IsSupplier) {
            # Supplier part
            $suppPrefix = $partData.SupplierPrefix
            $suppPN = $partData.SupplierPN.Replace("'", "''")
            Exec-SQL "INSERT INTO items (item_number, revision, iteration, lifecycle_state, is_supplier_part, supplier_prefix, supplier_pn) VALUES ('$partItem', 'A', 1, 'Design', 1, '$suppPrefix', '$suppPN');"
            Write-Log "  Created SUPPLIER item: $partItem ($suppPrefix-$suppPN)"
        }
        else {
            # Internal part
            Exec-SQL "INSERT INTO items (item_number, revision, iteration, lifecycle_state, is_supplier_part) VALUES ('$partItem', 'A', 1, 'Design', 0);"
            Write-Log "  Created item record for $partItem"
        }
    }
    
    # Update item properties
    $desc = $partData.Description.Replace("'", "''")
    $proj = $partData.Project.Replace("'", "''")
    $mat = $partData.Material.Replace("'", "''")
    $mass = if ($null -ne $partData.Mass) { $partData.Mass } else { "NULL" }
    $thick = if ($null -ne $partData.Thickness) { $partData.Thickness } else { "NULL" }
    $cutLen = if ($null -ne $partData.CutLength) { $partData.CutLength } else { "NULL" }
    $cutTime = if ($null -ne $partData.CutTime) { $partData.CutTime } else { "NULL" }
    $priceEst = if ($null -ne $partData.PriceEst) { $partData.PriceEst } else { "NULL" }
    
    if ($partData.IsSupplier) {
        # Supplier part - update with supplier-specific fields
        $suppPrefix = $partData.SupplierPrefix
        $suppPN = $partData.SupplierPN.Replace("'", "''")
        Exec-SQL "UPDATE items SET description='$desc', project='$proj', material='$mat', mass=$mass, thickness=$thick, cut_length=$cutLen, cut_time=$cutTime, price_est=$priceEst, is_supplier_part=1, supplier_prefix='$suppPrefix', supplier_pn='$suppPN', modified_at=CURRENT_TIMESTAMP WHERE item_number='$partItem';"
    }
    else {
        # Internal part - standard update
        Exec-SQL "UPDATE items SET description='$desc', project='$proj', material='$mat', mass=$mass, thickness=$thick, cut_length=$cutLen, cut_time=$cutTime, price_est=$priceEst, modified_at=CURRENT_TIMESTAMP WHERE item_number='$partItem';"
    }
    
    Write-Log "Parameter update completed for $partItem"
    
    # Delete the file
    try {
        Remove-Item -Path $filePath -Force
        Write-Log "Deleted processed parameter file: $fileName"
    }
    catch {
        Write-Log "ERROR: Failed to delete $fileName : $_"
    }
}

Write-Host "Part-Parameter-Watcher is running..."
Write-Host "Monitoring: $Global:ParamsPath"
Write-Log "Part-Parameter-Watcher monitoring: $Global:ParamsPath"

while ($true) {
    Start-Sleep -Seconds 2
}