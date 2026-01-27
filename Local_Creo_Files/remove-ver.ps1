# Script to remove version numbers from Creo files
# Renames files like "stp010.prt.27" to "stp010.prt"

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

# Get all files with version numbers (excluding directories)
$files = Get-ChildItem -File | Where-Object { $_.Name -match '\.\d+$' }

Write-Host "Found $($files.Count) files with version numbers" -ForegroundColor Cyan
Write-Host ""

foreach ($file in $files) {
    # Remove the version number (everything after the last period if it's a number)
    $newName = $file.Name -replace '\.\d+$', ''
    
    $targetPath = Join-Path $file.Directory.FullName $newName
    
    # Check if target file already exists
    if (Test-Path $targetPath) {
        Write-Host "SKIP: $($file.Name) -> $newName (target exists)" -ForegroundColor Yellow
    }
    else {
        try {
            Rename-Item -Path $file.FullName -NewName $newName -ErrorAction Stop
            Write-Host "OK: $($file.Name) -> $newName" -ForegroundColor Green
        }
        catch {
            Write-Host "ERROR: $($file.Name) - $($_.Exception.Message)" -ForegroundColor Red
        }
    }
}

Write-Host ""
Write-Host "Done!" -ForegroundColor Cyan