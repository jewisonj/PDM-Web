# Workspace Comparison Web Server
$Global:VaultPath = "V:\CADData"
$Global:DBPath = "V:\pdm.sqlite"
$Global:Port = 8082

function Query-SQLite {
    param([string]$Query)
    $output = & sqlite3.exe $Global:DBPath $Query 2>&1
    return $output
}

function Get-WorkspaceComparison {
    param([string]$WorkspacePath)
    
    if (-not (Test-Path $WorkspacePath)) {
        return @{ error = "Workspace path not found: $WorkspacePath" }
    }
    
    # Get all CAD files from workspace
    $workspaceFiles = @{}
    Get-ChildItem -Path $WorkspacePath -Include *.prt,*.asm,*.drw -Recurse | ForEach-Object {
        $workspaceFiles[$_.Name] = $_
    }
    
    $results = @{
        needCheckIn = @()
        needUpdate = @()
        upToDate = @()
        notInVault = @()
        workspacePath = $WorkspacePath
    }
    
    # Compare workspace files against database
    foreach ($fileName in $workspaceFiles.Keys) {
        $wsFile = $workspaceFiles[$fileName]
        
        # Query database for file info
        $query = "SELECT filename, filepath, created_date, modified_date FROM files WHERE filename = '$fileName' ORDER BY modified_date DESC LIMIT 1;"
        $dbResult = Query-SQLite -Query $query
        
        if ($dbResult) {
            # Parse database result
            $fields = $dbResult -split '\|'
            try {
                $dbModified = [DateTime]::Parse($fields[3])
                $timeDiff = ($wsFile.LastWriteTime - $dbModified).TotalSeconds
                
                $fileInfo = @{
                    file = $fileName
                    workspaceTime = $wsFile.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")
                    vaultTime = $dbModified.ToString("yyyy-MM-dd HH:mm:ss")
                    ageDiffHours = [math]::Round($timeDiff / 3600, 2)
                }
                
                if ($timeDiff -gt 60) {
                    $results.needCheckIn += $fileInfo
                } elseif ($timeDiff -lt -60) {
                    $results.needUpdate += $fileInfo
                } else {
                    $results.upToDate += $fileName
                }
            } catch {
                $results.notInVault += @{
                    file = $fileName
                    workspaceTime = $wsFile.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")
                    error = "Database parse error"
                }
            }
        } else {
            $results.notInVault += @{
                file = $fileName
                workspaceTime = $wsFile.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")
            }
        }
    }
    
    return $results
}

# Start HTTP listener
$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:$Global:Port/")
$listener.Start()

Write-Host "Workspace Comparison Server running on http://localhost:$Global:Port" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop..." -ForegroundColor Yellow

try {
    while ($listener.IsListening) {
        $context = $listener.GetContext()
        $request = $context.Request
        $response = $context.Response
        
        $url = $request.Url.LocalPath
        
        if ($url -eq "/" -or $url -eq "/index.html") {
            # Serve HTML page
            $html = Get-Content -Path (Join-Path $PSScriptRoot "workspace_compare.html") -Raw
            $buffer = [System.Text.Encoding]::UTF8.GetBytes($html)
            $response.ContentType = "text/html"
            $response.ContentLength64 = $buffer.Length
            $response.OutputStream.Write($buffer, 0, $buffer.Length)
        }
        elseif ($url -eq "/api/compare") {
            # Handle comparison request
            $reader = New-Object System.IO.StreamReader($request.InputStream)
            $body = $reader.ReadToEnd()
            $reader.Close()
            
            $data = $body | ConvertFrom-Json
            $workspacePath = $data.workspacePath
            
            $results = Get-WorkspaceComparison -WorkspacePath $workspacePath
            
            $json = $results | ConvertTo-Json -Depth 10
            $buffer = [System.Text.Encoding]::UTF8.GetBytes($json)
            $response.ContentType = "application/json"
            $response.ContentLength64 = $buffer.Length
            $response.OutputStream.Write($buffer, 0, $buffer.Length)
        }
        else {
            # 404
            $response.StatusCode = 404
        }
        
        $response.Close()
    }
} finally {
    $listener.Stop()
}