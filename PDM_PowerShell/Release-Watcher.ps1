. "D:\PDM_PowerShell\PDM-Library.ps1"

Write-Log "Release Watcher Started."

# --- Ensure release folders exist ---
$ReleaseRoot = "D:\PDM_Vault\Release"
$ReleasePDF  = Join-Path $ReleaseRoot "PDF"
$ReleaseSTEP = Join-Path $ReleaseRoot "STEP"
$ReleaseVis  = Join-Path $ReleaseRoot "Vis"

foreach ($p in @($ReleaseRoot, $ReleasePDF, $ReleaseSTEP, $ReleaseVis)) {
    if (-not (Test-Path $p)) {
        New-Item -ItemType Directory -Path $p | Out-Null
        Write-Log "Created missing release folder: $p"
    }
}

# --- Watcher ---
$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = "D:\PDM_Vault\CADData\Release"
$watcher.Filter = "*.*"
$watcher.IncludeSubdirectories = $false
$watcher.EnableRaisingEvents = $true

Register-ObjectEvent $watcher Created -Action {

    Start-Sleep -Milliseconds 500

    $filePath = $Event.SourceEventArgs.FullPath
    $fileName = $Event.SourceEventArgs.Name
    $item = $fileName.Split(".")[0]

    Write-Log "Release detected for $item file: $fileName"

    #---------------------------------------
    # 1) Ensure item exists
    #---------------------------------------
    $exists = Query-SQL "SELECT COUNT(*) FROM items WHERE item_number='$item';"

    if ($exists[0] -eq "0") {
        Write-Log "ERROR: Item $item not found. Cannot release."
        return
    }

    #---------------------------------------
    # 2) Get current revision
    #---------------------------------------
    $currentRev = (Query-SQL "
        SELECT revision FROM items WHERE item_number='$item';
    ")[0]

    #---------------------------------------
    # 3) Determine release folder
    #---------------------------------------
    $ext = [System.IO.Path]::GetExtension($fileName).ToLower()

    switch ($ext) {
        ".pdf" { $destFolder = $ReleasePDF }
        ".step" { $destFolder = $ReleaseSTEP }
        ".stp"  { $destFolder = $ReleaseSTEP }
        ".glb"  { $destFolder = $ReleaseVis }
        ".pvz"  { $destFolder = $ReleaseVis }
        default {
            Write-Log "Unknown release file type: $ext"
            return
        }
    }

    # Ensure final folder exists
    if (!(Test-Path $destFolder)) {
        New-Item -ItemType Directory -Path $destFolder | Out-Null
    }

    #---------------------------------------
    # 4) Archive old release files
    #---------------------------------------
    $oldFiles = Get-ChildItem -Path $destFolder -Filter "$item.*" -ErrorAction SilentlyContinue

    $archiveDir = Join-Path $destFolder "Archive"
    if (!(Test-Path $archiveDir)) {
        New-Item -ItemType Directory -Path $archiveDir | Out-Null
    }

    foreach ($old in $oldFiles) {
        $archivePath = Join-Path $archiveDir "$($old.Name)_rev$currentRev"
        Move-Item -Path $old.FullName -Destination $archivePath -Force
        Write-Log "Archived old release file: $archivePath"
    }

    #---------------------------------------
    # 5) Move new file to release folder
    #---------------------------------------
    $newReleasePath = Join-Path $destFolder $fileName
    Move-Item -Path $filePath -Destination $newReleasePath -Force
    Write-Log "Released file placed: $newReleasePath"

    #---------------------------------------
    # 6) Update lifecycle state
    #---------------------------------------
    Exec-SQL "
        UPDATE items
        SET lifecycle_state='Released',
            modified_at=CURRENT_TIMESTAMP
        WHERE item_number='$item';
    "

    #---------------------------------------
    # 7) Insert lifecycle history
    #---------------------------------------
    Exec-SQL "
        INSERT INTO lifecycle_history
            (item_number, old_state, new_state, old_revision, new_revision)
        VALUES
            ('$item', 'Design', 'Released', '$currentRev', '$currentRev');
    "

    Write-Log "Item $item released at revision $currentRev"
}

Write-Host "Release Watcher is running..."

while ($true) {
    Start-Sleep -Seconds 2
}
