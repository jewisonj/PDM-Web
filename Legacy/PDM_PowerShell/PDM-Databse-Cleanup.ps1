# PDM-Database-Cleanup.ps1
# Scans for missing files and removes their database entries
# Run manually as admin when you've deleted files that need cleanup

param(
    [switch]$DryRun,      # Show what would be deleted without actually deleting
    [switch]$Verbose,     # Show detailed progress
    [string]$FileType = "ALL"  # Filter: ALL, CAD, STEP, DXF, SVG, PDF
)

$Global:DBPath = "D:\PDM_Vault\pdm.sqlite"
$Global:VaultPath = "D:\PDM_Vault"
$Global:LogFile = "D:\PDM_Vault\Logs\database-cleanup-$(Get-Date -Format 'yyyy-MM-dd_HH-mm-ss').log"

function Write-Log {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] [$Level] $Message"
    
    $color = switch ($Level) {
        "ERROR" { "Red" }
        "WARN"  { "Yellow" }
        "SUCCESS" { "Green" }
        "INFO" { "Cyan" }
        default { "White" }
    }
    
    Write-Host $logMessage -ForegroundColor $color
    Add-Content -Path $Global:LogFile -Value $logMessage
}

function Test-SQLiteInstalled {
    $sqlite = Get-Command sqlite3.exe -ErrorAction SilentlyContinue
    if (-not $sqlite) {
        Write-Log "sqlite3.exe not found in PATH" "ERROR"
        Write-Log "Please ensure sqlite3.exe is installed and in your PATH" "ERROR"
        return $false
    }
    return $true
}

function Get-OrphanedFiles {
    param([string]$FileTypeFilter)
    
    Write-Log "Querying database for files..." "INFO"
    
    # Build SQL query
    $query = "SELECT file_id, item_number, file_path, file_type FROM files"
    if ($FileTypeFilter -ne "ALL") {
        $query += " WHERE file_type = '$FileTypeFilter'"
    }
    $query += ";"
    
    # Execute query and parse results
    $result = & sqlite3.exe $Global:DBPath $query
    
    if (-not $result) {
        Write-Log "No files found in database" "WARN"
        return @()
    }
    
    $orphanedFiles = @()
    $totalFiles = 0
    $missingFiles = 0
    
    foreach ($line in $result) {
        $totalFiles++
        $parts = $line -split '\|'
        
        if ($parts.Count -ge 4) {
            $fileId = $parts[0]
            $itemNumber = $parts[1]
            $filePath = $parts[2]
            $fileType = $parts[3]
            
            # Check if file exists
            if (-not (Test-Path $filePath)) {
                $missingFiles++
                
                $orphanedFiles += [PSCustomObject]@{
                    FileId = $fileId
                    ItemNumber = $itemNumber
                    FilePath = $filePath
                    FileType = $fileType
                }
                
                if ($Verbose) {
                    Write-Log "Missing: $filePath" "WARN"
                }
            } elseif ($Verbose) {
                Write-Log "Exists: $filePath" "INFO"
            }
        }
    }
    
    Write-Log "Scanned $totalFiles files, found $missingFiles missing" "INFO"
    
    return $orphanedFiles
}

function Remove-OrphanedFileEntries {
    param([array]$OrphanedFiles)
    
    if ($OrphanedFiles.Count -eq 0) {
        Write-Log "No orphaned files to remove" "SUCCESS"
        return
    }
    
    Write-Log "Found $($OrphanedFiles.Count) orphaned file entries" "WARN"
    
    if ($DryRun) {
        Write-Log "DRY RUN - No changes will be made" "WARN"
        Write-Log "Files that would be removed:" "INFO"
        foreach ($file in $OrphanedFiles) {
            Write-Log "  [$($file.FileType)] $($file.ItemNumber) - $($file.FilePath)" "WARN"
        }
        return
    }
    
    # Confirm deletion
    Write-Host ""
    Write-Host "WARNING: About to delete $($OrphanedFiles.Count) database entries!" -ForegroundColor Yellow
    Write-Host "Files to be removed from database:" -ForegroundColor Yellow
    
    # Group by file type
    $grouped = $OrphanedFiles | Group-Object FileType
    foreach ($group in $grouped) {
        Write-Host "  $($group.Name): $($group.Count) files" -ForegroundColor Cyan
    }
    
    Write-Host ""
    $confirm = Read-Host "Continue with deletion? (yes/no)"
    
    if ($confirm -ne "yes") {
        Write-Log "Cleanup cancelled by user" "WARN"
        return
    }
    
    Write-Log "Removing orphaned file entries..." "INFO"
    
    $successCount = 0
    $failCount = 0
    
    foreach ($file in $OrphanedFiles) {
        try {
            $query = "DELETE FROM files WHERE file_id = $($file.FileId);"
            $null = & sqlite3.exe $Global:DBPath $query
            
            Write-Log "Deleted: [$($file.FileType)] $($file.ItemNumber) - $($file.FilePath)" "SUCCESS"
            $successCount++
            
        } catch {
            Write-Log "Failed to delete file_id $($file.FileId): $_" "ERROR"
            $failCount++
        }
    }
    
    Write-Log "Cleanup complete: $successCount deleted, $failCount failed" "SUCCESS"
}

function Get-OrphanedItems {
    Write-Log "Checking for items with no files..." "INFO"
    
    # Find items that have no files
    $query = @"
SELECT item_id, item_number, name, revision, iteration, lifecycle_state
FROM items
WHERE item_number NOT IN (SELECT DISTINCT item_number FROM files);
"@
    
    $result = & sqlite3.exe $Global:DBPath $query
    
    if (-not $result) {
        Write-Log "No orphaned items found" "INFO"
        return @()
    }
    
    $orphanedItems = @()
    
    foreach ($line in $result) {
        $parts = $line -split '\|'
        
        if ($parts.Count -ge 6) {
            $orphanedItems += [PSCustomObject]@{
                ItemId = $parts[0]
                ItemNumber = $parts[1]
                Name = $parts[2]
                Revision = $parts[3]
                Iteration = $parts[4]
                LifecycleState = $parts[5]
            }
        }
    }
    
    Write-Log "Found $($orphanedItems.Count) items with no files" "WARN"
    
    return $orphanedItems
}

function Remove-OrphanedItems {
    param([array]$OrphanedItems)
    
    if ($OrphanedItems.Count -eq 0) {
        Write-Log "No orphaned items to remove" "SUCCESS"
        return
    }
    
    if ($DryRun) {
        Write-Log "DRY RUN - Items that would be removed:" "WARN"
        foreach ($item in $OrphanedItems) {
            Write-Log "  $($item.ItemNumber) ($($item.Name)) - Rev $($item.Revision).$($item.Iteration)" "WARN"
        }
        return
    }
    
    Write-Host ""
    Write-Host "Found $($OrphanedItems.Count) items with no files" -ForegroundColor Yellow
    $confirm = Read-Host "Remove orphaned items from database? (yes/no)"
    
    if ($confirm -ne "yes") {
        Write-Log "Orphaned item cleanup skipped" "WARN"
        return
    }
    
    Write-Log "Removing orphaned items..." "INFO"
    
    $successCount = 0
    $failCount = 0
    
    foreach ($item in $OrphanedItems) {
        try {
            # Also delete from BOM if item is referenced
            $bomQuery = "DELETE FROM bom WHERE parent_item = '$($item.ItemNumber)' OR child_item = '$($item.ItemNumber)';"
            $null = & sqlite3.exe $Global:DBPath $bomQuery
            
            # Delete item
            $itemQuery = "DELETE FROM items WHERE item_id = $($item.ItemId);"
            $null = & sqlite3.exe $Global:DBPath $itemQuery
            
            Write-Log "Deleted: $($item.ItemNumber) ($($item.Name))" "SUCCESS"
            $successCount++
            
        } catch {
            Write-Log "Failed to delete item $($item.ItemNumber): $_" "ERROR"
            $failCount++
        }
    }
    
    Write-Log "Item cleanup complete: $successCount deleted, $failCount failed" "SUCCESS"
}

function Show-Statistics {
    Write-Log "Database Statistics:" "INFO"
    
    $queries = @{
        "Total Items" = "SELECT COUNT(*) FROM items;"
        "Total Files" = "SELECT COUNT(*) FROM files;"
        "CAD Files" = "SELECT COUNT(*) FROM files WHERE file_type = 'CAD';"
        "STEP Files" = "SELECT COUNT(*) FROM files WHERE file_type = 'STEP';"
        "DXF Files" = "SELECT COUNT(*) FROM files WHERE file_type = 'DXF';"
        "SVG Files" = "SELECT COUNT(*) FROM files WHERE file_type = 'SVG';"
        "PDF Files" = "SELECT COUNT(*) FROM files WHERE file_type = 'PDF';"
        "BOM Entries" = "SELECT COUNT(*) FROM bom;"
        "Pending Tasks" = "SELECT COUNT(*) FROM work_queue WHERE status = 'Pending';"
    }
    
    foreach ($label in $queries.Keys) {
        $count = & sqlite3.exe $Global:DBPath $queries[$label]
        Write-Log "  $label : $count" "INFO"
    }
}

# Main execution
Write-Log "========================================" "INFO"
Write-Log "PDM Database Cleanup Tool" "INFO"
Write-Log "========================================" "INFO"
Write-Log "Database: $Global:DBPath" "INFO"
Write-Log "Log File: $Global:LogFile" "INFO"

if ($DryRun) {
    Write-Log "MODE: DRY RUN (no changes will be made)" "WARN"
}

Write-Log "" "INFO"

# Check prerequisites
if (-not (Test-Path $Global:DBPath)) {
    Write-Log "Database not found: $Global:DBPath" "ERROR"
    exit 1
}

if (-not (Test-SQLiteInstalled)) {
    exit 1
}

# Ensure log directory exists
$logDir = Split-Path $Global:LogFile -Parent
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

# Show current statistics
Show-Statistics
Write-Log "" "INFO"

# Scan for orphaned files
$orphanedFiles = Get-OrphanedFiles -FileTypeFilter $FileType

# Remove orphaned files
if ($orphanedFiles.Count -gt 0) {
    Remove-OrphanedFileEntries -OrphanedFiles $orphanedFiles
    Write-Log "" "INFO"
}

# Check for orphaned items (items with no files)
$orphanedItems = Get-OrphanedItems

# Remove orphaned items
if ($orphanedItems.Count -gt 0) {
    Remove-OrphanedItems -OrphanedItems $orphanedItems
    Write-Log "" "INFO"
}

# Show final statistics
if (-not $DryRun) {
    Write-Log "Final Statistics:" "INFO"
    Show-Statistics
}

Write-Log "" "INFO"
Write-Log "========================================" "INFO"
Write-Log "Cleanup Complete" "SUCCESS"
Write-Log "========================================" "INFO"
Write-Log "Log saved to: $Global:LogFile" "INFO"