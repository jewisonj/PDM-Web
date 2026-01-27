# Workspace Comparison Web Server Service
# Provides web-based comparison of Creo workspace files against PDM vault

$Global:VaultPath = "D:\PDM_Vault\CADData"
$Global:DBPath = "D:\PDM_Vault\pdm.sqlite"
$Global:Port = 8082
$Global:ServiceName = "PDM-WorkspaceCompare"

function Query-SQLite {
    param([string]$Query)
    $output = & "C:\sqlite\sqlite3.exe" $Global:DBPath $Query 2>&1
    return $output
}

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
        "DEBUG" { "Magenta" }
        default { "Gray" }
    }
    Write-Host "[$timestamp] [$Level] $Message" -ForegroundColor $color
}

# Start HTTP listener
$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://+:$Global:Port/")

try {
    $listener.Start()
    Write-ServiceLog "==================================================" "INFO"
    Write-ServiceLog "  $Global:ServiceName Service Started" "SUCCESS"
    Write-ServiceLog "==================================================" "INFO"
    Write-ServiceLog "Server: http://${env:COMPUTERNAME}:$Global:Port" "INFO"
    Write-ServiceLog "Database: $Global:DBPath" "INFO"
    Write-ServiceLog "Press Ctrl+C to stop..." "WARN"
    Write-ServiceLog "==================================================" "INFO"
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
        $client = $request.RemoteEndPoint.Address
        
        Write-ServiceLog "$method $url from $client" "INFO"
        
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
        
        if ($url -eq "/api/compare-filelist") {
            $reader = New-Object System.IO.StreamReader($request.InputStream)
            $body = $reader.ReadToEnd()
            $reader.Close()
            
            try {
                $data = $body | ConvertFrom-Json
                $workspaceFiles = $data.files
                
                Write-ServiceLog "Comparing $($workspaceFiles.Count) files..." "INFO"
                
                $results = @{
                    upToDate = @()
                    notInVault = @()
                    needCheckIn = @()
                    needUpdate = @()
                }
                
                foreach ($wsFile in $workspaceFiles) {
                    $fileName = $wsFile.filename
                    $safeFileName = $fileName -replace "'", "''"
                    $workspaceTime = $wsFile.lastWriteTime
                    
                    # Extract item_number from filename
                    $itemNumber = $fileName -replace '\.(prt|asm|drw)$', ''
                    $itemNumber = $itemNumber.ToLower()
                    $safeItemNumber = $itemNumber -replace "'", "''"
                    
                    # Get description from items table
                    $descQuery = "SELECT description FROM items WHERE item_number = '$safeItemNumber' LIMIT 1;"
                    $descResult = Query-SQLite -Query $descQuery
                    $description = ""
                    if ($descResult -and $descResult -is [string]) {
                        $trimmed = $descResult.Trim()
                        if ($trimmed.Length -gt 0 -and -not $trimmed.Contains("Error:")) {
                            $description = $trimmed
                        }
                    }
                    
                    # Check if file exists in vault (database lookup)
                    $query = "SELECT file_path FROM files WHERE file_path LIKE '%$safeFileName' LIMIT 1;"
                    $dbResult = Query-SQLite -Query $query
                    
                    # Debug logging for troubleshooting
                    if ($fileName -like "6in*" -or $fileName -like "7219*" -or $fileName -like "chain*") {
                        Write-ServiceLog "DEBUG: File=$fileName Query=$query Result=$dbResult" "DEBUG"
                    }
                    
                    $fileExistsInVault = $false
                    $vaultTimestamp = $null
                    $vaultPath = $null
                    
                    if ($dbResult) {
                        if ($dbResult -is [string]) {
                            $trimmed = $dbResult.Trim()
                            if ($trimmed.Length -gt 0 -and -not $trimmed.Contains("Error:")) {
                                $fileExistsInVault = $true
                                $vaultPath = $trimmed
                                
                                # Get file modification time from vault
                                if (Test-Path $vaultPath) {
                                    try {
                                        $fileInfo = Get-Item -Path $vaultPath
                                        $vaultTimestamp = $fileInfo.LastWriteTime
                                    } catch {
                                        Write-ServiceLog "Error accessing $vaultPath" "ERROR"
                                    }
                                }
                            }
                        }
                    }
                    
                    if (-not $fileExistsInVault) {
                        # New file
                        $results.notInVault += @{
                            file = $fileName
                            workspaceTime = $workspaceTime
                            vaultTime = ""
                            status = "New"
                            description = $description
                        }
                    }
                    elseif ($null -ne $vaultTimestamp -and $workspaceTime -ne "Unknown") {
                        # Compare timestamps
                        try {
                            $wsTime = [DateTime]::Parse($workspaceTime)
                            $timeDiff = ($wsTime - $vaultTimestamp).TotalSeconds
                            $vaultTimeStr = $vaultTimestamp.ToString("M/d/yyyy, h:mm:ss tt")
                            
                            if ([Math]::Abs($timeDiff) -lt 2) {
                                $results.upToDate += @{
                                    file = $fileName
                                    workspaceTime = $workspaceTime
                                    vaultTime = $vaultTimeStr
                                    status = "Up To Date"
                                    description = $description
                                }
                            }
                            elseif ($timeDiff -gt 2) {
                                $results.needCheckIn += @{
                                    file = $fileName
                                    workspaceTime = $workspaceTime
                                    vaultTime = $vaultTimeStr
                                    status = "Modified Locally"
                                    ageDiffHours = [math]::Round($timeDiff / 3600, 2)
                                    description = $description
                                }
                            }
                            else {
                                $results.needUpdate += @{
                                    file = $fileName
                                    workspaceTime = $workspaceTime
                                    vaultTime = $vaultTimeStr
                                    status = "Out of Date"
                                    ageDiffHours = [math]::Round(-$timeDiff / 3600, 2)
                                    description = $description
                                }
                            }
                        } catch {
                            Write-ServiceLog "Timestamp parse error for $fileName" "ERROR"
                        }
                    }
                    else {
                        # File in vault but no timestamp comparison
                        $vaultTimeStr = if ($vaultTimestamp) { $vaultTimestamp.ToString("M/d/yyyy, h:mm:ss tt") } else { "Unknown" }
                        $results.upToDate += @{
                            file = $fileName
                            workspaceTime = $workspaceTime
                            vaultTime = $vaultTimeStr
                            status = "In Vault"
                            description = $description
                        }
                    }
                }
                
                Write-ServiceLog "Results: UpToDate=$($results.upToDate.Count) Modified=$($results.needCheckIn.Count) OutOfDate=$($results.needUpdate.Count) New=$($results.notInVault.Count)" "SUCCESS"
                
                $json = $results | ConvertTo-Json -Depth 10
                $buffer = [System.Text.Encoding]::UTF8.GetBytes($json)
                $response.ContentType = "application/json"
                $response.ContentLength64 = $buffer.Length
                $response.OutputStream.Write($buffer, 0, $buffer.Length)
                
            } catch {
                Write-ServiceLog "Request error: $_" "ERROR"
                $errorResponse = @{ error = "Server error: $_" } | ConvertTo-Json
                $buffer = [System.Text.Encoding]::UTF8.GetBytes($errorResponse)
                $response.ContentType = "application/json"
                $response.StatusCode = 500
                $response.ContentLength64 = $buffer.Length
                $response.OutputStream.Write($buffer, 0, $buffer.Length)
            }
        }
        else {
            $response.StatusCode = 404
            Write-ServiceLog "404 Not Found: $url" "WARN"
        }
        
        $response.Close()
    }
} catch {
    Write-ServiceLog "Service error: $_" "ERROR"
} finally {
    $listener.Stop()
    Write-ServiceLog "$Global:ServiceName service stopped" "WARN"
}