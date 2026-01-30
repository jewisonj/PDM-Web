# Clear PDM Data Script
# DESTRUCTIVE - Removes all CAD data and resets database

param(
    [switch]$Confirm,
    [switch]$WhatIf
)

Write-Host ""
Write-Host "==================================================" -ForegroundColor Red
Write-Host "  WARNING: PDM DATA CLEANUP - DESTRUCTIVE OPERATION" -ForegroundColor Red
Write-Host "==================================================" -ForegroundColor Red
Write-Host ""

if (-not $Confirm -and -not $WhatIf) {
    Write-Host "This script will DELETE:" -ForegroundColor Yellow
    Write-Host "  * All files in D:\PDM_Vault\CADData\" -ForegroundColor Yellow
    Write-Host "  * All database records (items, files, bom, etc.)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "This action CANNOT be undone!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Usage:" -ForegroundColor Cyan
    Write-Host "  .\Clear-PDM-Data.ps1 -WhatIf     # Preview what would be deleted" -ForegroundColor Gray
    Write-Host "  .\Clear-PDM-Data.ps1 -Confirm    # Actually delete (requires backup)" -ForegroundColor Gray
    Write-Host ""
    exit
}

$dbPath = "D:\PDM_Vault\pdm.sqlite"
$cadPath = "D:\PDM_Vault\CADData"

# Check for backup
$backups = Get-ChildItem "D:\" -Directory -Filter "PDM_Backup_*" | Sort-Object Name -Descending | Select-Object -First 1
if (-not $backups -and $Confirm) {
    Write-Host "ERROR: No backup found!" -ForegroundColor Red
    Write-Host "Run Pre-Migration-Backup.ps1 first!" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

if ($backups) {
    Write-Host "+ Found backup: $($backups.Name)" -ForegroundColor Green
    Write-Host ""
}

# Stop services
if ($Confirm) {
    Write-Host "Stopping PDM services..." -ForegroundColor Yellow
    Stop-Service "CheckIn-Watcher" -ErrorAction SilentlyContinue
    Stop-Service "BOM-Watcher" -ErrorAction SilentlyContinue
    Stop-Service "Worker-Processor" -ErrorAction SilentlyContinue
    Stop-Service "Workspace-Compare" -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Write-Host "+ Services stopped" -ForegroundColor Green
    Write-Host ""
}

# Clear CADData folder
Write-Host "CADData Folder Cleanup:" -ForegroundColor Cyan
$subfolders = @("STEP", "DXF", "SVG", "PDF", "Archive", "CheckIn", "BOM", "Release", "Revise")
$rootFiles = Get-ChildItem -Path $cadPath -File -Filter "*.prt", "*.asm", "*.drw" -ErrorAction SilentlyContinue

foreach ($folder in $subfolders) {
    $path = Join-Path $cadPath $folder
    if (Test-Path $path) {
        $files = Get-ChildItem -Path $path -File -Recurse
        if ($WhatIf) {
            Write-Host "  Would delete $($files.Count) files from $folder\" -ForegroundColor Yellow
        } else {
            Remove-Item "$path\*" -Recurse -Force
            Write-Host "  + Deleted $($files.Count) files from $folder\" -ForegroundColor Green
        }
    }
}

if ($WhatIf) {
    Write-Host "  Would delete $($rootFiles.Count) CAD files from root" -ForegroundColor Yellow
} else {
    foreach ($file in $rootFiles) {
        Remove-Item $file.FullName -Force
    }
    Write-Host "  + Deleted $($rootFiles.Count) CAD files from root" -ForegroundColor Green
}

Write-Host ""

# Clear database tables
Write-Host "Database Cleanup:" -ForegroundColor Cyan
$tables = @("items", "files", "bom", "work_queue", "lifecycle_history", "checkouts")

foreach ($table in $tables) {
    $query = "SELECT COUNT(*) FROM $table;"
    $count = & sqlite3.exe $dbPath $query
    
    if ($WhatIf) {
        Write-Host "  Would delete $count records from $table" -ForegroundColor Yellow
    } else {
        $deleteQuery = "DELETE FROM $table;"
        & sqlite3.exe $dbPath $deleteQuery
        Write-Host "  + Deleted $count records from $table" -ForegroundColor Green
    }
}

Write-Host ""

if ($Confirm) {
    Write-Host "==================================================" -ForegroundColor Green
    Write-Host "  Cleanup Complete!" -ForegroundColor Green
    Write-Host "==================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  1. Verify cleanup was successful" -ForegroundColor Gray
    Write-Host "  2. Start services: .\Start-PDM-Services.ps1" -ForegroundColor Gray
    Write-Host "  3. Begin migration with clean data" -ForegroundColor Gray
    Write-Host ""
} elseif ($WhatIf) {
    Write-Host "==================================================" -ForegroundColor Yellow
    Write-Host "  Preview Complete (No Changes Made)" -ForegroundColor Yellow
    Write-Host "==================================================" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To actually perform cleanup:" -ForegroundColor Cyan
    Write-Host "  .\Clear-PDM-Data.ps1 -Confirm" -ForegroundColor Gray
    Write-Host ""
}
