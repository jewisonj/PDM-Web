. "D:\PDM_PowerShell\PDM-Library.ps1"

Write-Log "Revise Watcher Started."

# --- Ensure folders ---
$CADRoot    = "D:\PDM_Vault\CADData"
$ArchiveDir = Join-Path $CADRoot "Archive"

if (!(Test-Path $ArchiveDir)) {
    New-Item -ItemType Directory -Path $ArchiveDir | Out-Null
}

# --- Revision bumping helper ---
function Get-NextRevision {
    param([string]$rev)

    $rev = $rev.ToUpper()

    # Simple A → B → … → Z
    if ($rev.Length -eq 1 -and $rev -ne "Z") {
        return [char](([byte][char]$rev) + 1)
    }

    # Multi-letter sequence (Z → AA, AA → AB, etc.)
    $chars = $rev.ToCharArray()
    for ($i = $chars.Length - 1; $i -ge 0; $i--) {

        if ($chars[$i] -ne 'Z') {
            $chars[$i] = [char](([byte]$chars[$i]) + 1)
            return -join $chars
        }

        $chars[$i] = 'A'
    }

    return "A" + (-join $chars)
}


# --- File system watcher ---
$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = "D:\PDM_Vault\CADData\Revise"
$watcher.Filter = "*.*"
$watcher.IncludeSubdirectories = $false
$watcher.EnableRaisingEvents = $true


Register-ObjectEvent $watcher Created -Action {

    Start-Sleep -Milliseconds 500

    $filePath = $Event.SourceEventArgs.FullPath
    $fileName = $Event.SourceEventArgs.Name
    $item     = $fileName.Split(".")[0]

    Write-Log "Revision requested for $item"

    # -----------------------------------------
    # 1) Ensure item exists and is Released
    # -----------------------------------------
    $itemRow = Query-SQL "
        SELECT revision || '|' || iteration || '|' || lifecycle_state
        FROM items
        WHERE item_number='$item';
    "

    if ($itemRow.Count -eq 0) {
        Write-Log "ERROR: Item $item does not exist. Cannot revise."
        return
    }

    $parts      = $itemRow[0] -split '\|'
    $currentRev = $parts[0]
    $currentIter= [int]$parts[1]
    $state      = $parts[2]

    if ($state -ne "Released") {
        Write-Log "ERROR: Revision rejected. Item $item is '$state', must be 'Released'."
        return
    }

    # -----------------------------------------
    # 2) Compute new revision
    # -----------------------------------------
    $newRev = Get-NextRevision $currentRev
    Write-Log "Revision bump: $currentRev → $newRev"

    # -----------------------------------------
    # 3) Archive old CAD
    # -----------------------------------------
    $oldCADPath = Join-Path $CADRoot $fileName

    if (Test-Path $oldCADPath) {

        if (!(Test-Path $ArchiveDir)) {
            New-Item -ItemType Directory -Path $ArchiveDir | Out-Null
        }

        $extension = [System.IO.Path]::GetExtension($fileName)
        $archiveName = "${item}_rev$currentRev$extension"
        $archivePath = Join-Path $ArchiveDir $archiveName

        Move-Item -Path $oldCADPath -Destination $archivePath -Force
        Write-Log "Archived old CAD: $archivePath"
    }

    # -----------------------------------------
    # 4) Move new CAD into CADData
    # -----------------------------------------
    $newCADPath = Join-Path $CADRoot $fileName
    Move-Item -Path $filePath -Destination $newCADPath -Force

    Write-Log "Placed new revision CAD into CADData: $newCADPath"

    # -----------------------------------------
    # 5) Reset state back to Design + set new revision
    # -----------------------------------------
    Exec-SQL "
        UPDATE items
        SET revision='$newRev',
            iteration=1,
            lifecycle_state='Design',
            modified_at=CURRENT_TIMESTAMP
        WHERE item_number='$item';
    "

    # -----------------------------------------
    # 6) Insert lifecycle history entry
    # -----------------------------------------
    Exec-SQL "
        INSERT INTO lifecycle_history
            (item_number, old_state, new_state, old_revision, new_revision, old_iteration, new_iteration)
        VALUES
            ('$item', 'Released', 'Design', '$currentRev', '$newRev', $currentIter, 1);
    "

    # -----------------------------------------
    # 7) Register new CAD file in files table
    # -----------------------------------------
    Exec-SQL "
        INSERT INTO files (item_number, file_path, file_type, revision, iteration)
        VALUES ('$item', '$newCADPath', 'CAD', '$newRev', 1);
    "

    Write-Log "Revision complete for $item → $newRev"
}

Write-Host "Revise Watcher is running..."

while ($true) { Start-Sleep -Seconds 2 }
