# Local-FileTimestamp-Service.ps1
# Runs on local machine to provide file timestamps for workspace files
# Listens on localhost:8083

$Global:Port = 8083
$Global:ServiceName = "Local-FileTimestamp"

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

# Start HTTP listener
$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:$Global:Port/")

try {
    $listener.Start()
    Write-ServiceLog "==================================================" "INFO"
    Write-ServiceLog "  $Global:ServiceName Service Started" "SUCCESS"
    Write-ServiceLog "==================================================" "INFO"
    Write-ServiceLog "Server: http://localhost:$Global:Port" "INFO"
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
        
        if ($url -eq "/api/file-timestamps" -and $method -eq "POST") {
            $reader = New-Object System.IO.StreamReader($request.InputStream)
            $body = $reader.ReadToEnd()
            $reader.Close()
            
            try {
                $data = $body | ConvertFrom-Json
                $files = $data.files
                
                Write-ServiceLog "Getting timestamps for $($files.Count) files..." "INFO"
                
                $results = @()
                foreach ($fileInfo in $files) {
                    $filePath = $fileInfo.fullPath
                    $timestamp = "Unknown"
                    
                    if (Test-Path $filePath) {
                        try {
                            $file = Get-Item $filePath
                            $timestamp = $file.LastWriteTime.ToString("M/d/yyyy, h:mm:ss tt")
                        } catch {
                            Write-ServiceLog "Error getting timestamp for $filePath : $_" "ERROR"
                        }
                    }
                    
                    $results += @{
                        filename = $fileInfo.filename
                        fullPath = $filePath
                        lastWriteTime = $timestamp
                        success = ($timestamp -ne "Unknown")
                    }
                }
                
                $responseData = @{ files = $results }
                $json = $responseData | ConvertTo-Json -Depth 10
                $buffer = [System.Text.Encoding]::UTF8.GetBytes($json)
                $response.ContentType = "application/json"
                $response.ContentLength64 = $buffer.Length
                $response.OutputStream.Write($buffer, 0, $buffer.Length)
                
                Write-ServiceLog "Returned timestamps for $($files.Count) files" "SUCCESS"
                
            } catch {
                Write-ServiceLog "Request error: $_" "ERROR"
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