# Part Numbers List Server
# Serves searchable list of all part numbers in PDM system

$serviceName = "PDM-PartNumbersList"
$nodeExe = "C:\Program Files\nodejs\node.exe"
$scriptPath = "D:\PDM_PowerShell\part-numbers-server.js"

Write-Host "Starting Part Numbers List Server..." -ForegroundColor Cyan

# Check if service exists
$service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue

if ($service) {
    Write-Host "Stopping existing service..." -ForegroundColor Yellow
    Stop-Service -Name $serviceName -Force
    Start-Sleep -Seconds 2
}

# Start the Node.js server
Write-Host "Starting Node.js server on port 3002..." -ForegroundColor Green
Start-Process -FilePath $nodeExe -ArgumentList $scriptPath -NoNewWindow

Write-Host ""
Write-Host "Part Numbers List Server started!" -ForegroundColor Green
Write-Host "Access at: http://localhost:3002/parts" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow

# Keep script running
try {
    while ($true) {
        Start-Sleep -Seconds 1
    }
} finally {
    Write-Host "Shutting down..." -ForegroundColor Yellow
}
