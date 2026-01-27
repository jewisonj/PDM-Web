# Local_PDM_Services.ps1
# Local PDM services for workspace tool
# Handles check-in operations (copying files to CheckIn folder)
# Can be run as a Windows service using NSSM or directly in PowerShell

param(
    [switch]$InstallService,
    [switch]$UninstallService,
    [switch]$StartService,
    [switch]$StopService,
    [switch]$RestartService
)

$Global:Port = 8083
$Global:ServiceName = "Local-PDM-Services"
$Global:CheckInPath = "D:\PDM_Vault\CADData\CheckIn"
$Global:ScriptPath = $PSCommandPath
$Global:NSSMPath = "C:\PTC_Data\Tools\nssm.exe"  # Adjust path if NSSM is elsewhere

function Write-ServiceLog {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $color = switch ($Level) {
        "ERROR" { "Red" }
        "WARN"  { "Yellow" }
        "SUCCESS" { "Green" }
        default { "Gray" }
    }
    Write-Host "[$timestamp] [$Level] $Message" -ForegroundColor $color
}

function Install-PDMService {
    Write-ServiceLog "Installing $Global:ServiceName as Windows service..." "INFO"
    
    if (-not (Test-Path $Global:NSSMPath)) {
        Write-ServiceLog "NSSM not found at $Global:NSSMPath" "ERROR"
        Write-ServiceLog "Please install NSSM or update the path in this script" "ERROR"
        return
    }
    
    # Check if service already exists
    $existingService = Get-Service -Name $Global:ServiceName -ErrorAction SilentlyContinue
    if ($existingService) {
        Write-ServiceLog "Service already exists. Uninstall first with -UninstallService" "WARN"
        return
    }
    
    # Install service
    $arguments = @(
        "install"
        $Global:ServiceName
        "powershell.exe"
        "-ExecutionPolicy Bypass -NoProfile -File `"$Global:ScriptPath`""
    )
    
    & $Global:NSSMPath $arguments
    
    # Set service description
    & $Global:NSSMPath set $Global:ServiceName Description "Local PDM services for Creo workspace tool"
    
    # Set service to auto-start
    & $Global:NSSMPath set $Global:ServiceName Start SERVICE_AUTO_START
    
    Write-ServiceLog "Service installed successfully" "SUCCESS"
    Write-ServiceLog "Use -StartService to start the service" "INFO"
}

function Uninstall-PDMService {
    Write-ServiceLog "Uninstalling $Global:ServiceName..." "INFO"
    
    # Stop service if running
    $service = Get-Service -Name $Global:ServiceName -ErrorAction SilentlyContinue
    if ($service -and $service.Status -eq 'Running') {
        Write-ServiceLog "Stopping service first..." "INFO"
        Stop-Service -Name $Global:ServiceName -Force
        Start-Sleep -Seconds 2
    }
    
    # Remove service
    if (Test-Path $Global:NSSMPath) {
        & $Global:NSSMPath remove $Global:ServiceName confirm
        Write-ServiceLog "Service uninstalled successfully" "SUCCESS"
    } else {
        Write-ServiceLog "NSSM not found, cannot uninstall service" "ERROR"
    }
}

function Start-PDMService {
    Write-ServiceLog "Starting $Global:ServiceName..." "INFO"
    Start-Service -Name $Global:ServiceName
    Write-ServiceLog "Service started" "SUCCESS"
}

function Stop-PDMService {
    Write-ServiceLog "Stopping $Global:ServiceName..." "INFO"
    Stop-Service -Name $Global:ServiceName -Force
    Write-ServiceLog "Service stopped" "SUCCESS"
}

function Restart-PDMService {
    Write-ServiceLog "Restarting $Global:ServiceName..." "INFO"
    Restart-Service -Name $Global:ServiceName -Force
    Write-ServiceLog "Service restarted" "SUCCESS"
}

# Handle service management commands
if ($InstallService) {
    Install-PDMService
    exit 0
}

if ($UninstallService) {
    Uninstall-PDMService
    exit 0
}

if ($StartService) {
    Start-PDMService
    exit 0
}

if ($StopService) {
    Stop-PDMService
    exit 0
}

if ($RestartService) {
    Restart-PDMService
    exit 0
}

# Main service loop
Write-ServiceLog "==================================================" "INFO"
Write-ServiceLog "  $Global:ServiceName Starting" "SUCCESS"
Write-ServiceLog "==================================================" "INFO"
Write-ServiceLog "Server: http://localhost:$Global:Port" "INFO"
Write-ServiceLog "CheckIn Path: $Global:CheckInPath" "INFO"
Write-ServiceLog "Script: $Global:ScriptPath" "INFO"
Write-ServiceLog "Press Ctrl+C to stop..." "WARN"
Write-ServiceLog "==================================================" "INFO"

# Start HTTP listener
$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:$Global:Port/")

try {
    $listener.Start()
    Write-ServiceLog "HTTP listener started on port $Global:Port" "SUCCESS"
} catch {
    Write-ServiceLog "Failed to start listener: $_" "ERROR"
    exit 1
}

try {
    while ($listener.IsListening) {
        $context = $listener.GetContext()
        $request = $context.Request
        $response = $context.Response
        
        $url = $request.Url.LocalPath
        $method = $request.HttpMethod
        
        Write-ServiceLog "$method $url" "INFO"
        
        # Add CORS headers
        $response.AddHeader("Access-Control-Allow-Origin", "*")
        $response.AddHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        $response.AddHeader("Access-Control-Allow-Headers", "Content-Type")
        
        # Handle OPTIONS preflight
        if ($method -eq "OPTIONS") {
            $response.StatusCode = 200
            $response.Close()
            continue
        }
        
        # Health check endpoint
        if ($url -eq "/api/health" -and $method -eq "GET") {
            $healthData = @{
                status = "ok"
                service = $Global:ServiceName
                port = $Global:Port
                checkinPath = $Global:CheckInPath
                timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
            }
            $json = $healthData | ConvertTo-Json
            $buffer = [System.Text.Encoding]::UTF8.GetBytes($json)
            $response.ContentType = "application/json"
            $response.ContentLength64 = $buffer.Length
            $response.OutputStream.Write($buffer, 0, $buffer.Length)
            $response.Close()
            continue
        }
        
        # Check-in endpoint
        if ($url -eq "/api/checkin" -and $method -eq "POST") {
            $reader = New-Object System.IO.StreamReader($request.InputStream)
            $body = $reader.ReadToEnd()
            $reader.Close()
            
            try {
                $data = $body | ConvertFrom-Json
                $files = $data.files
                
                Write-ServiceLog "Check-in request for $($files.Count) files..." "INFO"
                
                # Ensure CheckIn directory exists
                if (-not (Test-Path $Global:CheckInPath)) {
                    New-Item -ItemType Directory -Path $Global:CheckInPath -Force | Out-Null
                    Write-ServiceLog "Created CheckIn directory: $Global:CheckInPath" "INFO"
                }
                
                $results = @()
                $successCount = 0
                $failCount = 0
                
                foreach ($fileInfo in $files) {
                    $sourcePath = $fileInfo.fullPath
                    $fileName = $fileInfo.filename
                    $destPath = Join-Path $Global:CheckInPath $fileName
                    
                    try {
                        if (Test-Path $sourcePath) {
                            # Copy file (not move)
                            Copy-Item -Path $sourcePath -Destination $destPath -Force
                            Write-ServiceLog "Copied: $fileName -> CheckIn" "SUCCESS"
                            $successCount++
                            
                            $results += @{
                                filename = $fileName
                                success = $true
                                message = "Copied to CheckIn folder"
                            }
                        } else {
                            Write-ServiceLog "File not found: $sourcePath" "ERROR"
                            $failCount++
                            
                            $results += @{
                                filename = $fileName
                                success = $false
                                error = "File not found"
                            }
                        }
                    } catch {
                        Write-ServiceLog "Error copying $fileName : $_" "ERROR"
                        $failCount++
                        
                        $results += @{
                            filename = $fileName
                            success = $false
                            error = $_.Exception.Message
                        }
                    }
                }
                
                Write-ServiceLog "Check-in complete: $successCount succeeded, $failCount failed" "SUCCESS"
                
                $responseData = @{ 
                    results = $results
                    summary = @{
                        total = $files.Count
                        succeeded = $successCount
                        failed = $failCount
                    }
                }
                $json = $responseData | ConvertTo-Json -Depth 10
                $buffer = [System.Text.Encoding]::UTF8.GetBytes($json)
                $response.ContentType = "application/json"
                $response.ContentLength64 = $buffer.Length
                $response.OutputStream.Write($buffer, 0, $buffer.Length)
                
            } catch {
                Write-ServiceLog "Request error: $_" "ERROR"
                $error = @{ error = "Server error: $_" } | ConvertTo-Json
                $buffer = [System.Text.Encoding]::UTF8.GetBytes($error)
                $response.ContentType = "application/json"
                $response.StatusCode = 500
                $response.ContentLength64 = $buffer.Length
                $response.OutputStream.Write($buffer, 0, $buffer.Length)
            }
            
            $response.Close()
        }
        # Download endpoint
        elseif ($url -eq "/api/download" -and $method -eq "POST") {
            $reader = New-Object System.IO.StreamReader($request.InputStream)
            $body = $reader.ReadToEnd()
            $reader.Close()
            
            try {
                $data = $body | ConvertFrom-Json
                $files = $data.files
                $workspaceDir = $data.workspaceDir
                
                Write-ServiceLog "Download request for $($files.Count) files to $workspaceDir..." "INFO"
                
                # Ensure workspace directory exists
                if (-not (Test-Path $workspaceDir)) {
                    Write-ServiceLog "Workspace directory does not exist: $workspaceDir" "ERROR"
                    $error = @{ error = "Workspace directory not found: $workspaceDir" } | ConvertTo-Json
                    $buffer = [System.Text.Encoding]::UTF8.GetBytes($error)
                    $response.ContentType = "application/json"
                    $response.StatusCode = 400
                    $response.ContentLength64 = $buffer.Length
                    $response.OutputStream.Write($buffer, 0, $buffer.Length)
                    $response.Close()
                    continue
                }
                
                $results = @()
                $successCount = 0
                $failCount = 0
                $Global:VaultCADPath = "D:\PDM_Vault\CADData"
                
                foreach ($fileInfo in $files) {
                    $fileName = $fileInfo.filename
                    $itemNumber = $fileName -replace '\.(prt|asm|drw)$', ''
                    
                    # Search for file in vault - check CAD folder first
                    $vaultPath = $null
                    $searchPath = Join-Path $Global:VaultCADPath $fileName
                    
                    if (Test-Path $searchPath) {
                        $vaultPath = $searchPath
                    } else {
                        # Search recursively in CADData folder
                        $found = Get-ChildItem -Path $Global:VaultCADPath -Filter $fileName -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
                        if ($found) {
                            $vaultPath = $found.FullName
                        }
                    }
                    
                    $destPath = Join-Path $workspaceDir $fileName
                    
                    try {
                        if ($vaultPath -and (Test-Path $vaultPath)) {
                            # Copy file from vault to workspace
                            Copy-Item -Path $vaultPath -Destination $destPath -Force
                            Write-ServiceLog "Downloaded: $fileName -> Workspace" "SUCCESS"
                            $successCount++
                            
                            $results += @{
                                filename = $fileName
                                success = $true
                                message = "Downloaded to workspace"
                                vaultPath = $vaultPath
                            }
                        } else {
                            Write-ServiceLog "File not found in vault: $fileName" "ERROR"
                            $failCount++
                            
                            $results += @{
                                filename = $fileName
                                success = $false
                                error = "File not found in vault"
                            }
                        }
                    } catch {
                        Write-ServiceLog "Error downloading $fileName : $_" "ERROR"
                        $failCount++
                        
                        $results += @{
                            filename = $fileName
                            success = $false
                            error = $_.Exception.Message
                        }
                    }
                }
                
                Write-ServiceLog "Download complete: $successCount succeeded, $failCount failed" "SUCCESS"
                
                $responseData = @{ 
                    results = $results
                    summary = @{
                        total = $files.Count
                        succeeded = $successCount
                        failed = $failCount
                    }
                }
                $json = $responseData | ConvertTo-Json -Depth 10
                $buffer = [System.Text.Encoding]::UTF8.GetBytes($json)
                $response.ContentType = "application/json"
                $response.ContentLength64 = $buffer.Length
                $response.OutputStream.Write($buffer, 0, $buffer.Length)
                
            } catch {
                Write-ServiceLog "Request error: $_" "ERROR"
                $error = @{ error = "Server error: $_" } | ConvertTo-Json
                $buffer = [System.Text.Encoding]::UTF8.GetBytes($error)
                $response.ContentType = "application/json"
                $response.StatusCode = 500
                $response.ContentLength64 = $buffer.Length
                $response.OutputStream.Write($buffer, 0, $buffer.Length)
            }
            
            $response.Close()
        }
        else {
            $response.StatusCode = 404
            Write-ServiceLog "404 Not Found: $url" "WARN"
            $response.Close()
        }
    }
} catch {
    Write-ServiceLog "Service error: $_" "ERROR"
} finally {
    $listener.Stop()
    Write-ServiceLog "$Global:ServiceName stopped" "WARN"
}