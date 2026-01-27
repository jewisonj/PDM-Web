. "D:\PDM_PowerShell\PDM-Library.ps1"

# -----------------------------
# Global paths
# -----------------------------
$Global:PDMRoot      = "D:\PDM_Vault"
$Global:CADDataRoot  = Join-Path $Global:PDMRoot "CADData"
$Global:CheckInPath  = Join-Path $Global:CADDataRoot "CheckIn"
$Global:PDFPath      = Join-Path $Global:CADDataRoot "PDF"
$Global:DXFPath      = Join-Path $Global:CADDataRoot "DXF"
$Global:SVGPath      = Join-Path $Global:CADDataRoot "SVG"
$Global:STEPPath     = Join-Path $Global:CADDataRoot "STEP"
$Global:ArchivePath  = Join-Path $Global:CADDataRoot "Archive"

# FreeCAD configuration
$Global:FreeCADExe   = "C:\Program Files\FreeCAD 0.21\bin\FreeCAD.exe"  # Adjust path as needed
$Global:ScriptsPath  = "D:\PDM_Scripts"

# -----------------------------
# Prefix rules for item number validation
# Each entry: prefix = @{ CreateItem = $true/$false; FetchPrint = $true/$false }
# Prefixes not listed here fall back to standard XXX##### pattern
# -----------------------------
$Global:PrefixRules = @{
    'mmc' = @{ CreateItem = $true; FetchPrint = $false }   # McMaster-Carr supplier parts - create item (manual PDF upload)
    'spn' = @{ CreateItem = $true; FetchPrint = $false }   # Generic supplier parts - create item
    'zzz' = @{ CreateItem = $false; FetchPrint = $false }  # Reference/tooling models - do NOT create item
}

# McMaster scraper script location (disabled for now - McMaster blocks automated requests)
# $Global:McMasterScript = "D:\PDM_PowerShell\Get-McMasterPrint.ps1"

Write-Log "Unified Check-In Ingestion Engine Started."

# Ensure folders exist
foreach ($p in @(
    $Global:CheckInPath,
    $Global:PDFPath,
    $Global:STEPPath,
    $Global:ArchivePath,
    $Global:CADDataRoot,
    $Global:DXFPath,
    $Global:SVGPath,
    $Global:ScriptsPath
)) {
    if (-not (Test-Path $p)) {
        New-Item -ItemType Directory -Path $p | Out-Null
        Write-Log "Created missing folder: $p"
    }
}

# -----------------------------
# Classification
# -----------------------------
function Get-FileClassification {
    param([string]$FileName)

    $ext  = [System.IO.Path]::GetExtension($FileName).ToLower().TrimStart('.')
    $item = [System.IO.Path]::GetFileNameWithoutExtension($FileName)

    # Ignore junk / tmp
    if ($FileName.StartsWith("~") -or $ext -eq "" -or $ext -eq "tmp") {
        return $null
    }

    $fileType   = "OTHER"
    $destFolder = $Global:ArchivePath

    switch ($ext) {
        "prt"  { $fileType = "CAD";  $destFolder = $Global:CADDataRoot }
        "asm"  { $fileType = "CAD";  $destFolder = $Global:CADDataRoot }
        "drw"  { $fileType = "CAD";  $destFolder = $Global:CADDataRoot }
        "pdf"  { $fileType = "PDF";  $destFolder = $Global:PDFPath     }
        "dxf"  { $fileType = "DXF";  $destFolder = $Global:DXFPath     }
        "svg"  { $fileType = "SVG";  $destFolder = $Global:SVGPath     }
        "step" { $fileType = "STEP"; $destFolder = $Global:STEPPath    }
        "stp"  { $fileType = "STEP"; $destFolder = $Global:STEPPath    }
        "obj"  { $fileType = "OBJ";  $destFolder = $Global:STEPPath    }
    }

    return [PSCustomObject]@{
        ItemNumber = $item
        Extension  = $ext
        FileType   = $fileType
        DestFolder = $destFolder
    }
}

# -----------------------------
# Fetch McMaster print for mmc parts
# -----------------------------
function Fetch-McMasterPrint {
    param([string]$ItemNumber)
    
    if (-not (Test-Path $Global:McMasterScript)) {
        Write-Log "McMaster script not found: $Global:McMasterScript"
        return
    }
    
    # Extract the part number (remove mmc prefix)
    $partNumber = $ItemNumber -replace '^mmc', ''
    
    Write-Log "Fetching McMaster print for: $partNumber"
    
    try {
        # Run the scraper script
        $result = & $Global:McMasterScript -PartNumber $partNumber -OutputFolder $Global:CheckInPath
        
        if ($result.Success) {
            Write-Log "McMaster print downloaded successfully for $ItemNumber"
        } else {
            Write-Log "McMaster print not found for $ItemNumber"
        }
    }
    catch {
        Write-Log "ERROR fetching McMaster print: $_"
    }
}

# -----------------------------
# Check if item number matches a special prefix
# Returns: @{ Matched = $true/$false; CreateItem = $true/$false; Prefix = 'xxx' }
# -----------------------------
function Get-PrefixRule {
    param([string]$ItemNumber)
    
    $lower = $ItemNumber.ToLower()
    
    foreach ($prefix in $Global:PrefixRules.Keys) {
        if ($lower.StartsWith($prefix)) {
            return @{
                Matched    = $true
                CreateItem = $Global:PrefixRules[$prefix].CreateItem
                Prefix     = $prefix
            }
        }
    }
    
    return @{
        Matched    = $false
        CreateItem = $true  # Default: create item for standard parts
        Prefix     = $null
    }
}

# -----------------------------
# Validate item number format
# Returns $true if valid, $false if should be skipped
# -----------------------------
function Test-ValidItemNumber {
    param([string]$ItemNumber)
    
    $lower = $ItemNumber.ToLower()
    $prefixRule = Get-PrefixRule -ItemNumber $lower
    
    # Special prefix - always valid (but may not create item)
    if ($prefixRule.Matched) {
        return $true
    }
    
    # Standard pattern: 3 letters + 4-6 digits
    if ($lower -match '^[a-z]{3}\d{4,6}$') {
        return $true
    }
    
    # Also allow standard pattern with suffixes (e.g., csp0030_flat)
    if ($lower -match '^[a-z]{3}\d{4,6}_') {
        return $true
    }
    
    return $false
}

# -----------------------------
# Ensure item exists (only if CreateItem = $true)
# -----------------------------
function Ensure-ItemExists {
    param(
        [string]$ItemNumber,
        [bool]$CreateItem = $true
    )

    $row = Query-SQL "
        SELECT revision || '|' || iteration || '|' || lifecycle_state
        FROM items
        WHERE item_number = '$ItemNumber';
    "

    if (-not [string]::IsNullOrWhiteSpace($row)) {
        $parts = $row -split '\|'
        return [PSCustomObject]@{
            ItemNumber = $ItemNumber
            Revision   = $parts[0]
            Iteration  = [int]$parts[1]
            State      = $parts[2]
            Exists     = $true
        }
    }

    # Item doesn't exist
    if (-not $CreateItem) {
        Write-Log "Skipping item creation for $ItemNumber (prefix rule)"
        return [PSCustomObject]@{
            ItemNumber = $ItemNumber
            Revision   = 'A'
            Iteration  = 1
            State      = 'Reference'
            Exists     = $false
        }
    }

    Exec-SQL "
        INSERT INTO items (item_number, revision, iteration, lifecycle_state)
        VALUES ('$ItemNumber', 'A', 1, 'Design');
    "
    Write-Log "Created new item record for $ItemNumber at A.1 (Design)"

    return [PSCustomObject]@{
        ItemNumber = $ItemNumber
        Revision   = 'A'
        Iteration  = 1
        State      = 'Design'
        Exists     = $true
    }
}

# -----------------------------
# Check if item has existing DXF/SVG
# -----------------------------
function Check-ExistingExports {
    param([string]$ItemNumber)

    $dxfCount = Query-SQL "
        SELECT COUNT(*) FROM files
        WHERE item_number='$ItemNumber' AND file_type='DXF';
    "

    $svgCount = Query-SQL "
        SELECT COUNT(*) FROM files
        WHERE item_number='$ItemNumber' AND file_type='SVG';
    "

    return [PSCustomObject]@{
        HasDXF = ([int]$dxfCount[0] -gt 0)
        HasSVG = ([int]$svgCount[0] -gt 0)
    }
}

# -----------------------------
# Queue DXF/SVG generation task
# -----------------------------
function Queue-ExportGeneration {
    param(
        [string]$ItemNumber,
        [string]$CADFilePath,
        [string]$ExportType  # 'DXF' or 'SVG'
    )

    $escapedPath = $CADFilePath.Replace("'", "''")

    # Check if task already queued - call sqlite3 directly
    $existing = & sqlite3.exe $Global:DBPath "
        SELECT COUNT(*) FROM work_queue
        WHERE item_number='$ItemNumber'
          AND task_type='GENERATE_$ExportType'
          AND status='Pending';
    " 2>$null

    if ($existing -and [int]$existing -gt 0) {
        Write-Log "Queue: $ExportType generation task already pending for $ItemNumber"
        return
    }

    Exec-SQL "
        INSERT INTO work_queue (item_number, file_path, task_type, status)
        VALUES ('$ItemNumber', '$escapedPath', 'GENERATE_$ExportType', 'Pending');
    "
    Write-Log "Queue: Added GENERATE_$ExportType task for $ItemNumber"
}

# -----------------------------
# File registration
# -----------------------------
function Register-FileRecord {
    param(
        [string]$ItemNumber,
        [string]$FilePath,
        [string]$FileType,
        [string]$Revision,
        [int]$Iteration,
        [bool]$ItemExists = $true
    )

    # Skip file registration if item wasn't created (e.g., zzz reference parts)
    if (-not $ItemExists) {
        Write-Log "DB: Skipping file registration for $ItemNumber (no item record)"
        return
    }

    $escapedPath = $FilePath.Replace("'", "''")

    # Check if this exact file path already exists for this item
    # Call sqlite3 directly to get proper multi-column results
    $existing = & sqlite3.exe -separator '|' $Global:DBPath "
        SELECT file_id, iteration FROM files
        WHERE item_number='$ItemNumber'
          AND file_path='$escapedPath';
    " 2>$null

    if ($existing) {
        # File exists - this is an overwrite, bump file iteration only
        $parts = $existing -split '\|'
        $fileId = $parts[0]
        $oldIteration = [int]$parts[1]
        $newIteration = $oldIteration + 1
        
        # Update the existing file record with new iteration and timestamp
        Exec-SQL "
            UPDATE files 
            SET iteration=$newIteration, added_at=CURRENT_TIMESTAMP
            WHERE file_id=$fileId;
        "
        Write-Log "DB: file updated (iteration bumped) → $ItemNumber | $FileType | $Revision.$newIteration | $FilePath"
    }
    else {
        # New file - insert it
        Exec-SQL "
            INSERT INTO files (item_number, file_path, file_type, revision, iteration)
            VALUES ('$ItemNumber', '$escapedPath', '$FileType', '$Revision', $Iteration);
        "
        Write-Log "DB: files → $ItemNumber | $FileType | $Revision.$Iteration | $FilePath"
    }

    # Queue PARAM_SYNC and SYNC tasks for CAD files only
    if ($FileType -eq 'CAD') {
        Exec-SQL "
            INSERT INTO work_queue (item_number, file_path, task_type, status)
            VALUES ('$ItemNumber', '$escapedPath', 'PARAM_SYNC', 'Pending');
        "
        Write-Log "Queue: Added PARAM_SYNC task for $ItemNumber"

        Exec-SQL "
            INSERT INTO work_queue (item_number, file_path, task_type, status)
            VALUES ('$ItemNumber', '$escapedPath', 'SYNC', 'Pending');
        "
        Write-Log "Queue: Added SYNC task for $ItemNumber"
    }

    # Check if we need to regenerate DXF/SVG - ONLY for STEP files
    # (Your batch scripts only work with STEP files)
    if ($FileType -eq 'STEP') {
        $exports = Check-ExistingExports -ItemNumber $ItemNumber

        if ($exports.HasDXF) {
            Queue-ExportGeneration -ItemNumber $ItemNumber -CADFilePath $escapedPath -ExportType 'DXF'
        }

        if ($exports.HasSVG) {
            Queue-ExportGeneration -ItemNumber $ItemNumber -CADFilePath $escapedPath -ExportType 'SVG'
        }
    }
}

# -----------------------------
# Extract item number from filename
# Handles various formats:
#   csp0030.dxf          → csp0030
#   csp0030_flat.dxf     → csp0030
#   csp0030_drawing.svg  → csp0030
#   mmc3006t426.prt      → mmc3006t426
#   spn551436.prt        → spn551436
# -----------------------------
function Extract-ItemNumber {
    param([string]$FileName)
    
    # Remove extension
    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($FileName)
    
    # Remove Creo suffixes (_prt, _asm, _drw, _flat, _drawing, etc.)
    $baseName = $baseName -replace '_prt$', ''
    $baseName = $baseName -replace '_asm$', ''
    $baseName = $baseName -replace '_drw$', ''
    $baseName = $baseName -replace '_flat$', ''
    $baseName = $baseName -replace '_drawing$', ''
    
    $lower = $baseName.ToLower()
    
    # Check special prefixes first (mmc, spn, zzz, etc.)
    foreach ($prefix in $Global:PrefixRules.Keys) {
        if ($lower.StartsWith($prefix)) {
            # Return the full name after prefix (allow any characters)
            return $lower
        }
    }
    
    # Extract standard item pattern: 3 letters + 4-6 digits
    if ($lower -match '^([a-z]{3}\d{4,6})') {
        return $matches[1]
    }
    
    return $lower
}

# -----------------------------
# Handle a single check-in
# -----------------------------
function Handle-CheckInFile {
    param([string]$SourcePath)

    $fileName = [System.IO.Path]::GetFileName($SourcePath)
    $info = Get-FileClassification -FileName $fileName

    # If classification returns null – could be PART NEU or junk
    if ($null -eq $info) {

        # TEMP/JUNK FILE: skip silently
        Write-Log "Skipped temp/invalid file: $fileName"
        return
    }

    $itemNumber = $info.ItemNumber
    $fileType   = $info.FileType
    $destFolder = $info.DestFolder

    Write-Log "Check-in detected: $fileName → Item $itemNumber, Type $fileType"

    # For DXF/SVG files, extract the actual item number from filename
    # This handles cases like csp0030_flat.dxf linking to csp0030
    if ($fileType -eq 'DXF' -or $fileType -eq 'SVG') {
        $extractedItem = Extract-ItemNumber -FileName $fileName
        if ($extractedItem) {
            $itemNumber = $extractedItem
            Write-Log "Linked $fileType to item: $itemNumber"
        }
    }
    
    # Extract proper item number for all file types
    $itemNumber = Extract-ItemNumber -FileName $fileName
    
    # Check prefix rules to determine if we should create an item
    $prefixRule = Get-PrefixRule -ItemNumber $itemNumber
    $shouldCreateItem = $prefixRule.CreateItem
    
    if ($prefixRule.Matched) {
        Write-Log "Prefix rule matched: $($prefixRule.Prefix) - CreateItem: $shouldCreateItem"
    }

    # Ensure item exists (or skip based on prefix rule)
    $itemMeta = Ensure-ItemExists -ItemNumber $itemNumber -CreateItem $shouldCreateItem
    $rev  = $itemMeta.Revision
    $iter = [int]$itemMeta.Iteration
    $itemExists = $itemMeta.Exists

    # Ensure destination folder exists
    if (-not (Test-Path $destFolder)) {
        New-Item -ItemType Directory -Path $destFolder | Out-Null
        Write-Log "Created missing destination folder: $destFolder"
    }

    $destPath = Join-Path $destFolder $fileName

    try {
        Move-Item -Path $SourcePath -Destination $destPath -Force
        Write-Log "Moved $fileName → $destPath"
    }
    catch {
        Write-Log "ERROR: Failed to move $fileName from $SourcePath to $destPath. $_"
        return
    }

    # Register file (only if item exists)
    Register-FileRecord -ItemNumber $itemNumber `
                        -FilePath   $destPath  `
                        -FileType   $fileType  `
                        -Revision   $rev       `
                        -Iteration  $iter      `
                        -ItemExists $itemExists

    # Fetch McMaster print if this is an mmc part and we should fetch prints
    if ($prefixRule.Matched -and $prefixRule.Prefix -eq 'mmc' -and $Global:PrefixRules['mmc'].FetchPrint) {
        # Only fetch if we don't already have a PDF for this item
        $existingPdf = Query-SQL "SELECT COUNT(*) FROM files WHERE item_number='$itemNumber' AND file_type='PDF';"
        if ([int]$existingPdf -eq 0) {
            Fetch-McMasterPrint -ItemNumber $itemNumber
        } else {
            Write-Log "PDF already exists for $itemNumber, skipping McMaster fetch"
        }
    }
}

# -----------------------------
# FileSystemWatcher
# -----------------------------
$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $Global:CheckInPath
$watcher.Filter = "*.*"
$watcher.IncludeSubdirectories = $false
$watcher.EnableRaisingEvents = $true

Register-ObjectEvent $watcher Created -Action {
    Start-Sleep -Milliseconds 800
    $filePath = $Event.SourceEventArgs.FullPath
    try {
        Handle-CheckInFile -SourcePath $filePath
    }
    catch {
        Write-Log "ERROR in Handle-CheckInFile for $filePath : $_"
    }
}

Write-Host "Unified Check-In Watcher is running..."
Write-Log "Unified Check-In Watcher is running..."

while ($true) {
    Start-Sleep -Seconds 2
}
