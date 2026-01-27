# Workspace Comparison Web Server - Simplified
$Global:VaultPath = "D:\PDM_Vault\CADData"
$Global:DBPath = "D:\PDM_Vault\pdm.sqlite"
$Global:Port = 8082

function Query-SQLite {
    param([string]$Query)
    $output = & sqlite3.exe $Global:DBPath $Query 2>&1
    return $output
}

# Start HTTP listener
$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://+:$Global:Port/")
$listener.Start()

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Workspace Comparison Server (Simple)" -ForegroundColor White
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Server running on: http://${env:COMPUTERNAME}:$Global:Port" -ForegroundColor Green
Write-Host "Database: $Global:DBPath" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop..." -ForegroundColor Red
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

try {
    while ($listener.IsListening) {
        $context = $listener.GetContext()
        $request = $context.Request
        $response = $context.Response
        
        $url = $request.Url.LocalPath
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        
        Write-Host "[$timestamp] $($request.HttpMethod) $url from $($request.RemoteEndPoint.Address)" -ForegroundColor Gray
        
        # Add CORS headers
        $response.AddHeader("Access-Control-Allow-Origin", "*")
        $response.AddHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        $response.AddHeader("Access-Control-Allow-Headers", "Content-Type")
        
        # Handle OPTIONS preflight
        if ($request.HttpMethod -eq "OPTIONS") {
            $response.StatusCode = 200
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
                
                Write-Host "  Checking $($workspaceFiles.Count) files..." -ForegroundColor Cyan
                
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
                    
                    # Extract item_number from filename (remove extension, lowercase)
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
                    
                    # Check if file exists in vault database and get its path
                    $query = "SELECT file_path FROM files WHERE file_path LIKE '%$safeFileName' LIMIT 1;"
                    $dbResult = Query-SQLite -Query $query
                    
                    # Debug: Show what's happening for first few files
                    if ($fileName -like "6in*" -or $fileName -like "7219*" -or $fileName -like "chain*") {
                        Write-Host "    DEBUG: File=$fileName" -ForegroundColor Yellow
                        Write-Host "    DEBUG: Query=$query" -ForegroundColor Yellow
                        Write-Host "    DEBUG: Result=$dbResult" -ForegroundColor Yellow
                    }
                    
                    # Debug: Show what SQLite returned
                    if ($fileName -like "*temp*") {
                        $resultType = if ($null -eq $dbResult) { "null" } else { $dbResult.GetType().Name }
                        Write-Host "    DEBUG: Query for $fileName returned: [$dbResult] (Type: $resultType)" -ForegroundColor Magenta
                    }
                    
                    # SQLite returns error objects or empty strings when no results
                    $fileExistsInVault = $false
                    $vaultTimestamp = $null
                    $vaultPath = $null
                    $status = "Unknown"
                    
                    if ($dbResult) {
                        if ($dbResult -is [string]) {
                            $trimmed = $dbResult.Trim()
                            if ($trimmed.Length -gt 0 -and -not $trimmed.Contains("Error:")) {
                                $fileExistsInVault = $true
                                $vaultPath = $trimmed
                                
                                # Get actual file modification date from the vault folder
                                if (Test-Path $vaultPath) {
                                    try {
                                        $fileInfo = Get-Item -Path $vaultPath
                                        $vaultTimestamp = $fileInfo.LastWriteTime
                                    } catch {
                                        $status = "Error"
                                    }
                                }
                            }
                        }
                    }
                    
                    if (-not $fileExistsInVault) {
                        # File NOT in vault - brand new
                        $results.notInVault += @{
                            file = $fileName
                            workspaceTime = $workspaceTime
                            vaultTime = ""
                            status = "New"
                            description = $description
                        }
                        Write-Host "    NEW $fileName - Not in vault" -ForegroundColor Magenta
                    }
                    elseif ($null -ne $vaultTimestamp -and $workspaceTime -ne "Unknown") {
                        # Both timestamps exist - compare them
                        try {
                            $wsTime = [DateTime]::Parse($workspaceTime)
                            $timeDiff = ($wsTime - $vaultTimestamp).TotalSeconds
                            
                            $vaultTimeStr = $vaultTimestamp.ToString("M/d/yyyy, h:mm:ss tt")
                            
                            if ([Math]::Abs($timeDiff) -lt 2) {
                                # Within 2 seconds - consider up to date
                                $status = "Up To Date"
                                $results.upToDate += @{
                                    file = $fileName
                                    workspaceTime = $workspaceTime
                                    vaultTime = $vaultTimeStr
                                    status = $status
                                    description = $description
                                }
                                Write-Host "    OK $fileName - Up to date" -ForegroundColor Green
                            }
                            elseif ($timeDiff -gt 2) {
                                # Workspace is newer
                                $status = "Modified Locally"
                                $results.needCheckIn += @{
                                    file = $fileName
                                    workspaceTime = $workspaceTime
                                    vaultTime = $vaultTimeStr
                                    status = $status
                                    ageDiffHours = [math]::Round($timeDiff / 3600, 2)
                                    description = $description
                                }
                                Write-Host "    MODIFIED $fileName - Workspace newer" -ForegroundColor Yellow
                            }
                            else {
                                # Vault is newer
                                $status = "Out of Date"
                                $results.needUpdate += @{
                                    file = $fileName
                                    workspaceTime = $workspaceTime
                                    vaultTime = $vaultTimeStr
                                    status = $status
                                    ageDiffHours = [math]::Round(-$timeDiff / 3600, 2)
                                    description = $description
                                }
                                Write-Host "    OUTDATED $fileName - Vault newer" -ForegroundColor Cyan
                            }
                        } catch {
                            $status = "Error"
                            Write-Host "    ERROR $fileName - Could not parse timestamp" -ForegroundColor Red
                        }
                    }
                    else {
                        # File in vault but can't compare timestamps
                        $vaultTimeStr = if ($vaultTimestamp) { $vaultTimestamp.ToString("M/d/yyyy, h:mm:ss tt") } else { "Unknown" }
                        $results.upToDate += @{
                            file = $fileName
                            workspaceTime = $workspaceTime
                            vaultTime = $vaultTimeStr
                            status = "In Vault"
                            description = $description
                        }
                        Write-Host "    OK $fileName - In Vault (no timestamp compare)" -ForegroundColor Green
                    }
                }
                
                Write-Host "  Summary: In Vault=$($results.upToDate.Count), Not in Vault=$($results.notInVault.Count)" -ForegroundColor Yellow
                
                $json = $results | ConvertTo-Json -Depth 10
                $buffer = [System.Text.Encoding]::UTF8.GetBytes($json)
                $response.ContentType = "application/json"
                $response.ContentLength64 = $buffer.Length
                $response.OutputStream.Write($buffer, 0, $buffer.Length)
                
            } catch {
                Write-Host "  ERROR: $_" -ForegroundColor Red
                $error = @{ error = "Server error: $_" } | ConvertTo-Json
                $buffer = [System.Text.Encoding]::UTF8.GetBytes($error)
                $response.ContentType = "application/json"
                $response.StatusCode = 500
                $response.ContentLength64 = $buffer.Length
                $response.OutputStream.Write($buffer, 0, $buffer.Length)
            }
        }
        else {
            $response.StatusCode = 404
            Write-Host "  -> 404 Not Found" -ForegroundColor Red
        }
        
        $response.Close()
    }
} catch {
    Write-Host ""
    Write-Host "ERROR: $_" -ForegroundColor Red
} finally {
    $listener.Stop()
    Write-Host ""
    Write-Host "Server stopped." -ForegroundColor Yellow
}