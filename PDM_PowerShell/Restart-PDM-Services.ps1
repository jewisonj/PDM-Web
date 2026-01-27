# Restart-PDM-Services.ps1
# Restarts all PDM NSSM services safely and shows status.

$services = @(
    "PDM-CheckInWatcher",
    "PDM-ReleaseWatcher",
    "PDM-ReviseWatcher",
    "PDM-WorkerProcessor"
)

Write-Host "Restarting PDM services..." -ForegroundColor Cyan

foreach ($svc in $services) {
    try {
        Write-Host "→ Restarting $svc..." -NoNewline
        nssm restart $svc
        Start-Sleep -Milliseconds 500
        Write-Host " OK" -ForegroundColor Green
    }
    catch {
        Write-Host " FAILED" -ForegroundColor Red
        $errMsg = $_.Exception.Message
        Write-Host "  Error restarting ${svc}: $errMsg" -ForegroundColor Red
    }
}

Write-Host "`nVerifying service status..." -ForegroundColor Cyan

foreach ($svc in $services) {
    try {
        $s = Get-Service -Name $svc -ErrorAction SilentlyContinue
        if ($s) {
            $statusColor = if ($s.Status -eq 'Running') { 'Green' } else { 'Red' }
            Write-Host ("{0,-25} {1}" -f $s.Name, $s.Status) -ForegroundColor $statusColor
        }
        else {
            Write-Host ("{0,-25} NOT INSTALLED" -f $svc) -ForegroundColor Yellow
        }
    }
    catch {
        Write-Host ("{0,-25} ERROR CHECKING" -f $svc) -ForegroundColor Red
    }
}

Write-Host "`nAll requested PDM services processed." -ForegroundColor Cyan