. "D:\PDM_PowerShell\PDM-Library.ps1"

# -----------------------------
# Global paths
# -----------------------------
$Global:PDMRoot      = "D:\PDM_Vault"
$Global:CADDataRoot  = Join-Path $Global:PDMRoot "CADData"
$Global:CheckInPath  = Join-Path $Global:CADDataRoot "CheckIn"
$Global:PDFPath      = Join-Path $Global:CADDataRoot "PDF"
$Global:DXFPath      = Join-Path $Global:CADDataRoot "DXF"
$Global:STEPPath     = Join-Path $Global:CADDataRoot "STEP"
$Global:NeutralPath  = Join-Path $Global:CADDataRoot "Neutral"
$Global:ArchivePath  = Join-Path $Global:CADDataRoot "Archive"

Write-Log "Unified Check-In Ingestion Engine Started."

# Ensure folders exist
foreach ($p in @(
    $Global:CheckInPath,
    $Global:PDFPath,
    $Global:STEPPath,
    $Global:NeutralPath,
    $Global:ArchivePath,
    $Global:CADDataRoot,
    $Global:DXFPath
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

    # Special handling for NEU: assembly-only BOM source
    if ($ext -eq "neu") {
        # Expect itemnumber_asm.neu → link to ITEMNUMBER
        if ($item -match "^[A-Za-z]{3}\d{4}_asm$") {
            return [PSCustomObject]@{
                ItemNumber = $item.Replace("_asm", "")  # normalized, e.g. csa0030
                Extension  = "neu"
                FileType   = "NEUTRAL_ASM"
                DestFolder = $Global:NeutralPath
            }
        }

        Write-Log "Ignoring part NEU file: $FileName"
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
        "step" { $fileType = "STEP"; $destFolder = $Global:STEPPath    }
        "stp"  { $fileType = "STEP"; $destFolder = $Global:STEPPath    }
    }

    return [PSCustomObject]@{
        ItemNumber = $item
        Extension  = $ext
        FileType   = $fileType
        DestFolder = $destFolder
    }
}

# -----------------------------
# Ensure item exists
# -----------------------------
function Ensure-ItemExists {
    param([string]$ItemNumber)

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
    }
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
        [int]$Iteration
    )

    $escapedPath = $FilePath.Replace("'", "''")

    $existing = Query-SQL "
        SELECT file_id FROM files
        WHERE item_number='$ItemNumber'
          AND file_path='$escapedPath';
    "

    if ($existing.Count -gt 0) {
        Write-Log "DB: files duplicate skipped for $ItemNumber | $FileType | $Revision.$Iteration | $FilePath"
        return
    }

    Exec-SQL "
        INSERT INTO files (item_number, file_path, file_type, revision, iteration)
        VALUES ('$ItemNumber', '$escapedPath', '$FileType', '$Revision', $Iteration);
    "
    Write-Log "DB: files → $ItemNumber | $FileType | $Revision.$Iteration | $FilePath"

    if ($FileType -eq 'CAD') {
        Exec-SQL "
            INSERT INTO work_queue (item_number, file_path, task_type)
            VALUES ('$ItemNumber', '$escapedPath', 'PARAM_SYNC');
        "
        Write-Log "Queue: Added PARAM_SYNC task for $ItemNumber"

        Exec-SQL "
            INSERT INTO work_queue (item_number, file_path, task_type)
            VALUES ('$ItemNumber', '$escapedPath', 'SYNC');
        "
        Write-Log "Queue: Added SYNC task for $ItemNumber"
    }
}

# -----------------------------
# Handle a single check-in
# -----------------------------
function Handle-CheckInFile {
    param([string]$SourcePath)

    $fileName = [System.IO.Path]::GetFileName($SourcePath)
    $info = Get-FileClassification -FileName $fileName

	# If classification returns null — could be PART NEU or junk
	if ($null -eq $info) {

		# PART NEU CLEANUP: delete files like csp0030.neu
		if ($fileName -match "^[A-Za-z]{3}\d{4}\.neu$") {
			try {
				Remove-Item -Path $SourcePath -Force
				Write-Log "Auto-removed PART NEU file (ignored): $fileName"
			}
			catch {
				Write-Log "ERROR deleting PART NEU file $fileName : $_"
			}
			return
		}

		# TEMP/JUNK FILE: skip silently
		Write-Log "Skipped temp/invalid file: $fileName"
		return
	}


    $itemNumber = $info.ItemNumber
    $fileType   = $info.FileType
    $destFolder = $info.DestFolder

    Write-Log "Check-in detected: $fileName → Item $itemNumber, Type $fileType"

    # Ensure item exists
    $itemMeta = Ensure-ItemExists -ItemNumber $itemNumber
    $rev  = $itemMeta.Revision
    $iter = [int]$itemMeta.Iteration

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

    # Normalize item number to 3 letters + 4 digits if present
    # This links csp0220_dxf.dxf, csp0220_something.pdf → csp0220
    $prefix = [regex]::Match($fileName, "^[A-Za-z]{3}\d{4}")
    if ($prefix.Success) {
        $itemNumber = $prefix.Value
    }

    # Register file
    Register-FileRecord -ItemNumber $itemNumber `
                        -FilePath   $destPath  `
                        -FileType   $fileType  `
                        -Revision   $rev       `
                        -Iteration  $iter

    # BOM trigger: when an assembly NEU file arrives ( *_asm.neu )
    if ($fileType -eq "NEUTRAL_ASM") {
        $neuFileName = "${itemNumber}_asm.neu"
        $neuPath     = Join-Path $Global:NeutralPath $neuFileName

        if (Test-Path $neuPath) {
            Write-Log "Starting BOM extraction for $itemNumber from $neuPath"
            Start-Job -ScriptBlock {
                param($item, $neu)
                & "D:\PDM_PowerShell\Parse-Neu-BOM.ps1" -ItemNumber $item -NeuFile $neu
            } -ArgumentList $itemNumber, $neuPath | Out-Null
        }
        else {
            Write-Log "BOM ERROR: NEU file not found for $itemNumber at $neuPath"
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
