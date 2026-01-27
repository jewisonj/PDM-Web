# Restart-PDM-Services.ps1
# Restarts all PDM NSSM services safely and shows status.

$services = @(
    "PDM-CheckInWatcher",
    "PDM-ReleaseWatcher",
    "PDM-ReviseWatcher"
)

Write-Host "Restarting PDM services..." -ForegroundColor Cyan

foreach ($svc in $services) {
    try {
        Write-Host "→ Restarting $svc..." -NoNewline
        nssm restart $svc
        Write-Host " OK" -ForegroundColor Green
    }
    catch {
        Write-Host " FAILED" -ForegroundColor Red
        Write-Host "  Error restarting $svc: $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host "`nVerifying service status..." -ForegroundColor Cyan

foreach ($svc in $services) {
    $s = Get-Service -Name $svc
    Write-Host ("{0,-22} {1}" -f $s.Name, $s.Status)
}

Write-Host "`nAll requested PDM services processed." -ForegroundColor Cyan
