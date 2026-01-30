#Requires -Version 5.1
<#
.SYNOPSIS
    Configuration for PDM Upload Service.

.DESCRIPTION
    Edit this file to customize the API URL and folder locations.
#>

$Config = @{
    # PDM-Web API URL (change for different environments)
    # Local development:
    ApiUrl       = "http://localhost:8001/api"
    # Production:
    # ApiUrl       = "https://pdm-web.fly.dev/api"

    # Local folder to watch for uploads
    WatchFolder  = "C:\PDM-Upload"

    # Log file location
    LogFile      = "C:\PDM-Upload\pdm-upload.log"

    # Delay (ms) after file detected before processing
    PollInterval = 500

    # Maximum log file size (bytes) before rotation
    MaxLogSize   = 10MB
}

# Logging function
function Write-Log {
    param([string]$Message)

    $timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $logEntry = "$timestamp $Message"

    # Write to console
    Write-Host $logEntry

    # Write to log file
    try {
        # Rotate log if too large
        if ((Test-Path $Config.LogFile) -and (Get-Item $Config.LogFile).Length -gt $Config.MaxLogSize) {
            $backupPath = $Config.LogFile -replace '\.log$', "_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
            Move-Item $Config.LogFile $backupPath -Force
        }

        Add-Content -Path $Config.LogFile -Value $logEntry -ErrorAction SilentlyContinue
    }
    catch {
        # Silently continue if log writing fails
    }
}
