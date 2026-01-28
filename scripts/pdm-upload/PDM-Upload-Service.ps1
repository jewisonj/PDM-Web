#Requires -Version 5.1
<#
.SYNOPSIS
    PDM File Upload Service - Watches a folder and uploads files to PDM-Web API.

.DESCRIPTION
    This script monitors C:\PDM-Upload for new files and:
    - Uploads STEP, PDF, DXF, SVG files to the PDM-Web API
    - Parses BOM text files and uploads BOM relationships
    - Parses parameter text files and updates item properties

    Designed to run as a Windows Service via Task Scheduler or NSSM.

.NOTES
    Author: PDM-Web
    Version: 1.0.0
#>

# Load configuration and helper functions
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. "$ScriptDir\PDM-Upload-Config.ps1"
. "$ScriptDir\PDM-Upload-Functions.ps1"
. "$ScriptDir\PDM-BOM-Parser.ps1"

# Ensure watch folder exists
if (-not (Test-Path $Config.WatchFolder)) {
    New-Item -ItemType Directory -Path $Config.WatchFolder -Force | Out-Null
    Write-Log "Created watch folder: $($Config.WatchFolder)"
}

# Ensure Failed folder exists
$FailedFolder = Join-Path $Config.WatchFolder "Failed"
if (-not (Test-Path $FailedFolder)) {
    New-Item -ItemType Directory -Path $FailedFolder -Force | Out-Null
}

Write-Log "=========================================="
Write-Log "PDM Upload Service Starting"
Write-Log "API URL: $($Config.ApiUrl)"
Write-Log "Watch Folder: $($Config.WatchFolder)"
Write-Log "=========================================="

# Process a single file
function Process-DroppedFile {
    param([string]$FilePath)

    $fileName = [IO.Path]::GetFileName($FilePath)

    # Skip temporary files
    if ($fileName.StartsWith("~") -or $fileName.StartsWith(".")) {
        Write-Log "Skipping temp file: $fileName"
        return
    }

    # Wait for file to be fully written
    $maxRetries = 5
    $retryCount = 0
    while ($retryCount -lt $maxRetries) {
        try {
            $stream = [IO.File]::Open($FilePath, 'Open', 'Read', 'None')
            $stream.Close()
            break
        }
        catch {
            $retryCount++
            if ($retryCount -eq $maxRetries) {
                Write-Log "ERROR: Cannot access file after $maxRetries attempts: $fileName"
                return
            }
            Start-Sleep -Milliseconds 500
        }
    }

    Write-Log "Processing: $fileName"

    try {
        # Determine what to do with this file
        $action = Get-FileAction -FilePath $FilePath

        switch ($action) {
            'Upload' {
                # Extract item number from filename
                $itemNumber = Get-ItemNumber -FileName $fileName

                if (-not $itemNumber) {
                    throw "Could not extract item number from filename: $fileName"
                }

                # Skip zzz (reference) items
                if ($itemNumber.StartsWith("zzz")) {
                    Write-Log "Skipping reference item: $itemNumber"
                    Remove-Item $FilePath -Force
                    return
                }

                # Upload the file
                $result = Upload-File -FilePath $FilePath -ItemNumber $itemNumber
                Write-Log "SUCCESS: Uploaded $fileName for item $itemNumber"
            }

            'BOM' {
                # Parse and upload single-level BOM
                $result = Upload-BOM -FilePath $FilePath
                Write-Log "SUCCESS: Uploaded BOM - Parent: $($result.parent_item_number), Children: $($result.bom_entries_created)"
            }

            'MLBOM' {
                # Parse and upload multi-level BOM (same endpoint, parser handles structure)
                $result = Upload-BOM -FilePath $FilePath
                Write-Log "SUCCESS: Uploaded MLBOM - Parent: $($result.parent_item_number), Children: $($result.bom_entries_created)"
            }

            'Parameters' {
                # Parse and update parameters
                $result = Update-Parameters -FilePath $FilePath
                Write-Log "SUCCESS: Updated parameters for item $($result.item_number)"
            }

            'Skip' {
                Write-Log "Skipping unsupported file type: $fileName"
            }
        }

        # Delete the file on success (except Skip)
        if ($action -ne 'Skip') {
            Remove-Item $FilePath -Force
        }
    }
    catch {
        $errorMsg = $_.Exception.Message
        Write-Log "ERROR: Failed to process $fileName - $errorMsg"

        # Move to Failed folder
        $failedPath = Join-Path $FailedFolder $fileName

        # Handle duplicate names in Failed folder
        $counter = 1
        while (Test-Path $failedPath) {
            $baseName = [IO.Path]::GetFileNameWithoutExtension($fileName)
            $ext = [IO.Path]::GetExtension($fileName)
            $failedPath = Join-Path $FailedFolder "${baseName}_$counter$ext"
            $counter++
        }

        Move-Item $FilePath $failedPath -Force
        Write-Log "Moved failed file to: $failedPath"
    }
}

# Process any existing files in the folder
Write-Log "Checking for existing files..."
$existingFiles = Get-ChildItem -Path $Config.WatchFolder -File
foreach ($file in $existingFiles) {
    Process-DroppedFile -FilePath $file.FullName
}

# Set up FileSystemWatcher
$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $Config.WatchFolder
$watcher.Filter = "*.*"
$watcher.IncludeSubdirectories = $false
$watcher.NotifyFilter = [IO.NotifyFilters]'FileName, LastWrite'

# Event handler for new files
$onCreated = Register-ObjectEvent $watcher "Created" -Action {
    $filePath = $Event.SourceEventArgs.FullPath
    $fileName = $Event.SourceEventArgs.Name

    # Small delay to ensure file is fully written
    Start-Sleep -Milliseconds $Config.PollInterval

    # Process the file
    Process-DroppedFile -FilePath $filePath
}

# Enable the watcher
$watcher.EnableRaisingEvents = $true
Write-Log "File watcher started. Monitoring: $($Config.WatchFolder)"

# Keep script running
try {
    while ($true) {
        Start-Sleep -Seconds 1
    }
}
finally {
    # Cleanup on exit
    $watcher.EnableRaisingEvents = $false
    Unregister-Event -SourceIdentifier $onCreated.Name -ErrorAction SilentlyContinue
    $watcher.Dispose()
    Write-Log "PDM Upload Service stopped"
}
