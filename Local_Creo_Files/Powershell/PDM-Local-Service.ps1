#Requires -Version 5.1
<#
.SYNOPSIS
    PDM Local Service - bridges Creo's embedded browser with the PDM-Web backend.

.DESCRIPTION
    HTTP server on localhost:8083 that provides local file operations
    for workspace.html running inside Creo Parametric's browser.

    Endpoints:
      POST /api/file-timestamps  - Read local file modification times
      POST /api/checkin           - Upload local files to PDM-Web API (FastAPI -> Supabase)
      POST /api/download          - Download files from PDM-Web API to local workspace

    This service replaces the legacy Local-FileTimestamp-Service.ps1 and integrates
    with the new FastAPI backend instead of the old SQLite vault.

.NOTES
    Start with: powershell -ExecutionPolicy Bypass -File PDM-Local-Service.ps1
#>

# ============================================
# Configuration
# ============================================

$Global:Port = 8083
$Global:ServiceName = "PDM-Local-Service"

# PDM-Web API URL - same as PDM-Upload config
# Change this to match your environment
$Global:ApiUrl = "http://localhost:8000/api"
# Production:
# $Global:ApiUrl = "https://pdm-web.fly.dev/api"

# ============================================
# Logging
# ============================================

function Write-ServiceLog {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $color = switch ($Level) {
        "ERROR"   { "Red" }
        "WARN"    { "Yellow" }
        "SUCCESS" { "Green" }
        default   { "Gray" }
    }
    Write-Host "[$timestamp] [$Level] $Message" -ForegroundColor $color
}

# ============================================
# Helper: Extract item number from filename
# ============================================

function Get-ItemNumber {
    param([string]$FileName)

    $baseName = [IO.Path]::GetFileNameWithoutExtension($FileName)

    # Standard: 3 letters + 4-6 digits (e.g., csp0030, wma20120)
    if ($baseName -match '^([a-zA-Z]{3}\d{4,6})') {
        return $Matches[1].ToLower()
    }
    # McMaster: mmc prefix
    if ($baseName -match '^(mmc[a-zA-Z0-9]+)') {
        return $Matches[1].ToLower()
    }
    # Supplier: spn prefix
    if ($baseName -match '^(spn[a-zA-Z0-9]+)') {
        return $Matches[1].ToLower()
    }
    return $null
}

# ============================================
# Helper: Read request body as JSON
# ============================================

function Read-RequestBody {
    param([System.Net.HttpListenerRequest]$Request)

    $reader = New-Object System.IO.StreamReader($Request.InputStream)
    $body = $reader.ReadToEnd()
    $reader.Close()
    return $body | ConvertFrom-Json
}

# ============================================
# Helper: Send JSON response
# ============================================

function Send-JsonResponse {
    param(
        [System.Net.HttpListenerResponse]$Response,
        [object]$Data,
        [int]$StatusCode = 200
    )

    $json = $Data | ConvertTo-Json -Depth 10
    $buffer = [System.Text.Encoding]::UTF8.GetBytes($json)
    $Response.ContentType = "application/json"
    $Response.StatusCode = $StatusCode
    $Response.ContentLength64 = $buffer.Length
    $Response.OutputStream.Write($buffer, 0, $buffer.Length)
}

# ============================================
# Handler: POST /api/file-timestamps
# ============================================

function Handle-FileTimestamps {
    param(
        [System.Net.HttpListenerRequest]$Request,
        [System.Net.HttpListenerResponse]$Response
    )

    $data = Read-RequestBody -Request $Request
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
            filename      = $fileInfo.filename
            fullPath      = $filePath
            lastWriteTime = $timestamp
            success       = ($timestamp -ne "Unknown")
        }
    }

    $responseData = @{ files = $results }
    Send-JsonResponse -Response $Response -Data $responseData

    Write-ServiceLog "Returned timestamps for $($files.Count) files" "SUCCESS"
}

# ============================================
# Handler: POST /api/checkin
# ============================================

function Handle-CheckIn {
    param(
        [System.Net.HttpListenerRequest]$Request,
        [System.Net.HttpListenerResponse]$Response
    )

    $data = Read-RequestBody -Request $Request
    $files = $data.files

    Write-ServiceLog "Check-in request for $($files.Count) files" "INFO"

    Add-Type -AssemblyName System.Net.Http

    $results = @()
    $succeeded = 0
    $failed = 0

    foreach ($fileInfo in $files) {
        $filename = $fileInfo.filename
        $fullPath = $fileInfo.fullPath

        # Validate file exists
        if (-not (Test-Path $fullPath)) {
            Write-ServiceLog "  File not found: $fullPath" "ERROR"
            $results += @{
                filename = $filename
                success  = $false
                error    = "File not found: $fullPath"
            }
            $failed++
            continue
        }

        # Extract item number
        $itemNumber = Get-ItemNumber -FileName $filename
        if (-not $itemNumber) {
            Write-ServiceLog "  Cannot extract item number from: $filename" "ERROR"
            $results += @{
                filename = $filename
                success  = $false
                error    = "Cannot extract item number from filename"
            }
            $failed++
            continue
        }

        # Upload to FastAPI backend
        $uri = "$Global:ApiUrl/files/upload"
        $httpClient = $null
        $form = $null

        try {
            $httpClient = New-Object System.Net.Http.HttpClient
            $form = New-Object System.Net.Http.MultipartFormDataContent

            # Add item_number field
            $itemField = New-Object System.Net.Http.StringContent($itemNumber)
            $form.Add($itemField, "item_number")

            # Add file
            $fileBytes = [IO.File]::ReadAllBytes($fullPath)
            $fileContent = New-Object System.Net.Http.ByteArrayContent(,$fileBytes)

            # Determine MIME type
            $ext = [IO.Path]::GetExtension($filename).ToLower()
            $mimeType = switch ($ext) {
                '.pdf'  { 'application/pdf' }
                '.step' { 'application/step' }
                '.stp'  { 'application/step' }
                '.dxf'  { 'application/dxf' }
                '.svg'  { 'image/svg+xml' }
                default { 'application/octet-stream' }
            }
            $fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse($mimeType)
            $form.Add($fileContent, "file", $filename)

            $apiResponse = $httpClient.PostAsync($uri, $form).Result

            if ($apiResponse.IsSuccessStatusCode) {
                Write-ServiceLog "  Uploaded: $filename -> item $itemNumber" "SUCCESS"
                $results += @{
                    filename   = $filename
                    success    = $true
                    itemNumber = $itemNumber
                }
                $succeeded++
            } else {
                $errorBody = $apiResponse.Content.ReadAsStringAsync().Result
                Write-ServiceLog "  Upload failed ($($apiResponse.StatusCode)): $filename - $errorBody" "ERROR"
                $results += @{
                    filename = $filename
                    success  = $false
                    error    = "API error ($($apiResponse.StatusCode)): $errorBody"
                }
                $failed++
            }
        }
        catch {
            Write-ServiceLog "  Exception uploading $filename : $_" "ERROR"
            $results += @{
                filename = $filename
                success  = $false
                error    = "Upload exception: $_"
            }
            $failed++
        }
        finally {
            if ($form) { $form.Dispose() }
            if ($httpClient) { $httpClient.Dispose() }
        }
    }

    $responseData = @{
        results = $results
        summary = @{
            total     = $files.Count
            succeeded = $succeeded
            failed    = $failed
        }
    }

    Send-JsonResponse -Response $Response -Data $responseData

    Write-ServiceLog "Check-in complete: $succeeded succeeded, $failed failed" $(if ($failed -gt 0) {"WARN"} else {"SUCCESS"})
}

# ============================================
# Handler: POST /api/download
# ============================================

function Handle-Download {
    param(
        [System.Net.HttpListenerRequest]$Request,
        [System.Net.HttpListenerResponse]$Response
    )

    $data = Read-RequestBody -Request $Request
    $files = $data.files
    $workspaceDir = $data.workspaceDir

    Write-ServiceLog "Download request for $($files.Count) files to $workspaceDir" "INFO"

    if (-not (Test-Path $workspaceDir)) {
        Write-ServiceLog "Workspace directory not found: $workspaceDir" "ERROR"
        Send-JsonResponse -Response $Response -Data @{
            error = "Workspace directory not found: $workspaceDir"
        } -StatusCode 400
        return
    }

    $results = @()
    $succeeded = 0
    $failed = 0

    foreach ($fileInfo in $files) {
        $filename = $fileInfo.filename
        $itemNumber = Get-ItemNumber -FileName $filename

        if (-not $itemNumber) {
            Write-ServiceLog "  Cannot extract item number from: $filename" "ERROR"
            $results += @{
                filename = $filename
                success  = $false
                error    = "Cannot extract item number"
            }
            $failed++
            continue
        }

        try {
            # Step 1: Get item details from API
            $itemUri = "$Global:ApiUrl/items/$itemNumber"
            $itemResponse = Invoke-RestMethod -Uri $itemUri -Method Get -ErrorAction Stop

            # Step 2: Find the matching file record
            $matchingFile = $null
            foreach ($f in $itemResponse.files) {
                if ($f.file_name -eq $filename) {
                    $matchingFile = $f
                    break
                }
            }

            if (-not $matchingFile) {
                Write-ServiceLog "  No vault file found for: $filename" "WARN"
                $results += @{
                    filename = $filename
                    success  = $false
                    error    = "File not found in vault"
                }
                $failed++
                continue
            }

            # Step 3: Get signed download URL
            $downloadUri = "$Global:ApiUrl/files/$($matchingFile.id)/download"
            $downloadInfo = Invoke-RestMethod -Uri $downloadUri -Method Get -ErrorAction Stop

            # Step 4: Download the file
            $signedUrl = $downloadInfo.url
            $destPath = Join-Path $workspaceDir $filename

            Invoke-WebRequest -Uri $signedUrl -OutFile $destPath -ErrorAction Stop

            Write-ServiceLog "  Downloaded: $filename" "SUCCESS"
            $results += @{
                filename = $filename
                success  = $true
                destPath = $destPath
            }
            $succeeded++
        }
        catch {
            Write-ServiceLog "  Download failed for $filename : $_" "ERROR"
            $results += @{
                filename = $filename
                success  = $false
                error    = "Download error: $_"
            }
            $failed++
        }
    }

    $responseData = @{
        results = $results
        summary = @{
            total     = $files.Count
            succeeded = $succeeded
            failed    = $failed
        }
    }

    Send-JsonResponse -Response $Response -Data $responseData

    Write-ServiceLog "Download complete: $succeeded succeeded, $failed failed" $(if ($failed -gt 0) {"WARN"} else {"SUCCESS"})
}

# ============================================
# Main HTTP Server Loop
# ============================================

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:$Global:Port/")

try {
    $listener.Start()
    Write-ServiceLog "==================================================" "INFO"
    Write-ServiceLog "  $Global:ServiceName Started" "SUCCESS"
    Write-ServiceLog "==================================================" "INFO"
    Write-ServiceLog "Server: http://localhost:$Global:Port" "INFO"
    Write-ServiceLog "API Backend: $Global:ApiUrl" "INFO"
    Write-ServiceLog "Press Ctrl+C to stop..." "WARN"
    Write-ServiceLog "==================================================" "INFO"
    Write-ServiceLog "Endpoints:" "INFO"
    Write-ServiceLog "  POST /api/file-timestamps  - Local file timestamps" "INFO"
    Write-ServiceLog "  POST /api/checkin           - Upload files to vault" "INFO"
    Write-ServiceLog "  POST /api/download          - Download files from vault" "INFO"
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

        # CORS headers (Creo browser runs on file:// or chrome-extension://)
        $response.AddHeader("Access-Control-Allow-Origin", "*")
        $response.AddHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        $response.AddHeader("Access-Control-Allow-Headers", "Content-Type")

        # Handle OPTIONS preflight
        if ($method -eq "OPTIONS") {
            $response.StatusCode = 200
            $response.Close()
            continue
        }

        Write-ServiceLog "$method $url" "INFO"

        try {
            switch ("$method $url") {
                "POST /api/file-timestamps" {
                    Handle-FileTimestamps -Request $request -Response $response
                }
                "POST /api/checkin" {
                    Handle-CheckIn -Request $request -Response $response
                }
                "POST /api/download" {
                    Handle-Download -Request $request -Response $response
                }
                "GET /health" {
                    Send-JsonResponse -Response $response -Data @{
                        status  = "healthy"
                        service = $Global:ServiceName
                        apiUrl  = $Global:ApiUrl
                    }
                }
                default {
                    $response.StatusCode = 404
                    Write-ServiceLog "404 Not Found: $method $url" "WARN"
                }
            }
        }
        catch {
            Write-ServiceLog "Handler error: $_" "ERROR"
            try {
                Send-JsonResponse -Response $response -Data @{
                    error = "Internal server error: $_"
                } -StatusCode 500
            } catch {
                # Response may already be closed
            }
        }

        $response.Close()
    }
} catch {
    Write-ServiceLog "Service error: $_" "ERROR"
} finally {
    $listener.Stop()
    Write-ServiceLog "$Global:ServiceName stopped" "WARN"
}
