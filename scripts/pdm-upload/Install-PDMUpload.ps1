#Requires -Version 5.1
<#
.SYNOPSIS
    Installs the PDM Upload Service to C:\PDM-Upload.

.DESCRIPTION
    - Creates C:\PDM-Upload folder
    - Creates Failed subfolder
    - Copies service scripts
    - Creates desktop shortcut (optional)
#>

param(
    [switch]$CreateShortcut
)

$SourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TargetDir = "C:\PDM-Upload"
$FailedDir = Join-Path $TargetDir "Failed"

Write-Host "PDM Upload Service Installer" -ForegroundColor Cyan
Write-Host "=============================" -ForegroundColor Cyan
Write-Host ""

# Create directories
if (-not (Test-Path $TargetDir)) {
    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
    Write-Host "[OK] Created: $TargetDir" -ForegroundColor Green
} else {
    Write-Host "[OK] Exists: $TargetDir" -ForegroundColor Yellow
}

if (-not (Test-Path $FailedDir)) {
    New-Item -ItemType Directory -Path $FailedDir -Force | Out-Null
    Write-Host "[OK] Created: $FailedDir" -ForegroundColor Green
} else {
    Write-Host "[OK] Exists: $FailedDir" -ForegroundColor Yellow
}

# Copy scripts
$scripts = @(
    "PDM-Upload-Config.ps1",
    "PDM-Upload-Functions.ps1",
    "PDM-Upload-Service.ps1",
    "PDM-BOM-Parser.ps1",
    "Start-PDMUpload.bat"
)

foreach ($script in $scripts) {
    $source = Join-Path $SourceDir $script
    $target = Join-Path $TargetDir $script

    if (Test-Path $source) {
        Copy-Item $source $target -Force
        Write-Host "[OK] Copied: $script" -ForegroundColor Green
    } else {
        Write-Host "[WARN] Not found: $script" -ForegroundColor Yellow
    }
}

# Create desktop shortcut if requested
if ($CreateShortcut) {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $shortcutPath = Join-Path $desktop "PDM Upload Service.lnk"

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = Join-Path $TargetDir "Start-PDMUpload.bat"
    $shortcut.WorkingDirectory = $TargetDir
    $shortcut.Description = "Start PDM Upload Service"
    $shortcut.Save()

    Write-Host "[OK] Created desktop shortcut" -ForegroundColor Green
}

Write-Host ""
Write-Host "Installation complete!" -ForegroundColor Cyan
Write-Host ""
Write-Host "To start the service:" -ForegroundColor White
Write-Host "  1. Run: $TargetDir\Start-PDMUpload.bat" -ForegroundColor Gray
Write-Host "  2. Drop files into: $TargetDir" -ForegroundColor Gray
Write-Host ""
Write-Host "File types:" -ForegroundColor White
Write-Host "  - param.txt    -> Update item parameters" -ForegroundColor Gray
Write-Host "  - BOM.txt      -> Upload single-level BOM" -ForegroundColor Gray
Write-Host "  - MLBOM.txt    -> Upload multi-level BOM" -ForegroundColor Gray
Write-Host "  - *.step/stp   -> Upload CAD file" -ForegroundColor Gray
Write-Host "  - *.pdf/dxf/svg -> Upload document" -ForegroundColor Gray
Write-Host ""
