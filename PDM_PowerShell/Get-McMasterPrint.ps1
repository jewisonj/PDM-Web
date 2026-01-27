# Get-McMasterPrint.ps1
# Downloads technical drawing from McMaster-Carr for a given part number
# Usage: .\Get-McMasterPrint.ps1 -PartNumber "3528T18"

param(
    [Parameter(Mandatory=$true)]
    [string]$PartNumber,
    
    [string]$OutputFolder = "D:\PDM_Vault\CADData\CheckIn",
    
    [switch]$SaveHtml  # Save HTML for debugging
)

# Clean up part number (remove mmc prefix if present)
$cleanPN = $PartNumber -replace '^mmc', ''
$cleanPN = $cleanPN.ToUpper()

$mcmasterUrl = "https://www.mcmaster.com/$cleanPN/"

Write-Host "Fetching McMaster page: $mcmasterUrl" -ForegroundColor Cyan

try {
    # Use .NET HttpClient which handles compression automatically
    Add-Type -AssemblyName System.Net.Http
    
    $handler = New-Object System.Net.Http.HttpClientHandler
    $handler.AutomaticDecompression = [System.Net.DecompressionMethods]::GZip -bor [System.Net.DecompressionMethods]::Deflate
    
    $client = New-Object System.Net.Http.HttpClient($handler)
    $client.DefaultRequestHeaders.Add("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
    $client.DefaultRequestHeaders.Add("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8")
    $client.DefaultRequestHeaders.Add("Accept-Language", "en-US,en;q=0.9")
    
    $response = $client.GetAsync($mcmasterUrl).Result
    $html = $response.Content.ReadAsStringAsync().Result
    
    $client.Dispose()
    
    if ($SaveHtml) {
        $debugFile = Join-Path $OutputFolder "mcmaster_debug_$cleanPN.html"
        $html | Out-File -FilePath $debugFile -Encoding UTF8
        Write-Host "DEBUG: Saved HTML to $debugFile" -ForegroundColor Magenta
        Write-Host "DEBUG: Response length: $($html.Length) chars" -ForegroundColor Magenta
    }
    
    # Check if we got a valid page
    if ($html.Length -lt 1000) {
        Write-Host "WARNING: Response seems too short, may be blocked" -ForegroundColor Yellow
    }
    
    # Pattern 1: Look for CAD image - technical drawing
    # src="/mvC/Library/CAD1/20250511/12BFB0A2/3528T18_*.GIF"
    if ($html -match 'src="(/mvC/Library/CAD[^"]+\.GIF)"') {
        $gifPath = $matches[1]
        $gifUrl = "https://www.mcmaster.com$gifPath"
        
        Write-Host "Found technical drawing: $gifUrl" -ForegroundColor Green
        
        $outputFile = Join-Path $OutputFolder "mmc$($cleanPN.ToLower()).gif"
        
        $webClient = New-Object System.Net.WebClient
        $webClient.Headers.Add("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        $webClient.DownloadFile($gifUrl, $outputFile)
        $webClient.Dispose()
        
        Write-Host "Downloaded: $outputFile" -ForegroundColor Green
        return @{ Success = $true; PartNumber = "mmc$($cleanPN.ToLower())"; FilePath = $outputFile }
    }
    
    # Pattern 2: Any mvC GIF path
    if ($html -match 'src="(/mvC/[^"]+\.[Gg][Ii][Ff])"') {
        $gifPath = $matches[1]
        $gifUrl = "https://www.mcmaster.com$gifPath"
        
        Write-Host "Found image: $gifUrl" -ForegroundColor Green
        
        $outputFile = Join-Path $OutputFolder "mmc$($cleanPN.ToLower()).gif"
        
        $webClient = New-Object System.Net.WebClient
        $webClient.Headers.Add("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        $webClient.DownloadFile($gifUrl, $outputFile)
        $webClient.Dispose()
        
        Write-Host "Downloaded: $outputFile" -ForegroundColor Green
        return @{ Success = $true; PartNumber = "mmc$($cleanPN.ToLower())"; FilePath = $outputFile }
    }
    
    # Pattern 3: Look for image with part number
    $escapedPN = [regex]::Escape($cleanPN)
    if ($html -match "src=`"([^`"]*$escapedPN[^`"]*\.(gif|png|jpg|GIF|PNG|JPG))`"") {
        $imgPath = $matches[1]
        $ext = $matches[2].ToLower()
        
        if ($imgPath -notmatch '^http') {
            $imgUrl = "https://www.mcmaster.com$imgPath"
        } else {
            $imgUrl = $imgPath
        }
        
        Write-Host "Found part image: $imgUrl" -ForegroundColor Green
        
        $outputFile = Join-Path $OutputFolder "mmc$($cleanPN.ToLower()).$ext"
        
        $webClient = New-Object System.Net.WebClient
        $webClient.Headers.Add("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        $webClient.DownloadFile($imgUrl, $outputFile)
        $webClient.Dispose()
        
        Write-Host "Downloaded: $outputFile" -ForegroundColor Green
        return @{ Success = $true; PartNumber = "mmc$($cleanPN.ToLower())"; FilePath = $outputFile }
    }
    
    # Pattern 4: Look in JSON data for cadDrawingUrl
    if ($html -match '"cadDrawingUrl"\s*:\s*"([^"]+)"') {
        $cadUrl = $matches[1] -replace '\\/', '/'
        if ($cadUrl -notmatch '^http') {
            $cadUrl = "https://www.mcmaster.com$cadUrl"
        }
        
        Write-Host "Found CAD URL in JSON: $cadUrl" -ForegroundColor Green
        
        $ext = if ($cadUrl -match '\.(\w+)$') { $matches[1].ToLower() } else { "gif" }
        $outputFile = Join-Path $OutputFolder "mmc$($cleanPN.ToLower()).$ext"
        
        $webClient = New-Object System.Net.WebClient
        $webClient.Headers.Add("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        $webClient.DownloadFile($cadUrl, $outputFile)
        $webClient.Dispose()
        
        Write-Host "Downloaded: $outputFile" -ForegroundColor Green
        return @{ Success = $true; PartNumber = "mmc$($cleanPN.ToLower())"; FilePath = $outputFile }
    }
    
    Write-Host "No technical drawing found on page" -ForegroundColor Red
    Write-Host "TIP: Run with -SaveHtml to inspect the page" -ForegroundColor Yellow
    
    return @{
        Success = $false
        PartNumber = "mmc$($cleanPN.ToLower())"
        Url = $mcmasterUrl
        Error = "No image found"
    }
}
catch {
    Write-Host "ERROR: Failed to fetch McMaster page - $_" -ForegroundColor Red
    return @{
        Success = $false
        PartNumber = "mmc$($cleanPN.ToLower())"
        Url = $mcmasterUrl
        Error = $_.Exception.Message
    }
}
