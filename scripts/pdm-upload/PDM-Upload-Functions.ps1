#Requires -Version 5.1
<#
.SYNOPSIS
    API client functions for PDM Upload Service.

.DESCRIPTION
    Contains functions for:
    - Extracting item numbers from filenames
    - Determining file actions by extension/content
    - Uploading files to the API
    - Uploading BOMs
    - Updating item parameters
#>

function Get-ItemNumber {
    <#
    .SYNOPSIS
        Extract item number from filename.

    .DESCRIPTION
        Handles various naming patterns:
        - csp0030.step -> csp0030
        - csp0030_flat.dxf -> csp0030
        - CSP0030_REV_A.pdf -> csp0030
        - mmc4464k478.prt -> mmc4464k478
    #>
    param([string]$FileName)

    $baseName = [IO.Path]::GetFileNameWithoutExtension($FileName)

    # Standard pattern: 3 letters + 4-6 digits
    if ($baseName -match '^([a-zA-Z]{3}\d{4,6})') {
        return $Matches[1].ToLower()
    }

    # McMaster pattern: mmc followed by alphanumeric
    if ($baseName -match '^(mmc[a-zA-Z0-9]+)') {
        return $Matches[1].ToLower()
    }

    # Supplier pattern: spn followed by alphanumeric
    if ($baseName -match '^(spn[a-zA-Z0-9]+)') {
        return $Matches[1].ToLower()
    }

    # Reference pattern: zzz followed by alphanumeric
    if ($baseName -match '^(zzz[a-zA-Z0-9]+)') {
        return $Matches[1].ToLower()
    }

    return $null
}


function Get-FileAction {
    <#
    .SYNOPSIS
        Determine what action to take based on file type.

    .RETURNS
        'Upload' - Upload as file to item
        'BOM' - Parse as single-level BOM text file
        'MLBOM' - Parse as multi-level BOM text file
        'Parameters' - Parse as parameter update file
        'Skip' - Ignore this file
    #>
    param([string]$FilePath)

    $fileName = [IO.Path]::GetFileName($FilePath).ToLower()
    $ext = [IO.Path]::GetExtension($FilePath).ToLower()

    # Ignore service files and common non-upload files
    $ignoreExtensions = @('.ps1', '.bat', '.cmd', '.log', '.ini', '.config', '.json', '.md', '.txt', '.jpg', '.jpeg', '.png', '.gif')
    $ignoreFiles = @('pdm-upload-config.ps1', 'pdm-upload-functions.ps1', 'pdm-upload-service.ps1',
                     'pdm-bom-parser.ps1', 'start-pdmupload.bat', 'install-pdmupload.ps1',
                     'test-api.ps1', 'desktop.ini', 'thumbs.db')

    # Skip ignored files
    if ($ignoreFiles -contains $fileName) {
        return 'Skip'
    }

    # Check for specific text file names (BOM/param files)
    switch ($fileName) {
        'param.txt'  { return 'Parameters' }
        'bom.txt'    { return 'BOM' }
        'mlbom.txt'  { return 'MLBOM' }
    }

    # Skip other ignored extensions (after checking for specific .txt files above)
    if ($ignoreExtensions -contains $ext) {
        return 'Skip'
    }

    # Then check by extension for uploads
    switch ($ext) {
        '.step' { return 'Upload' }
        '.stp'  { return 'Upload' }
        '.pdf'  { return 'Upload' }
        '.dxf'  { return 'Upload' }
        '.svg'  { return 'Upload' }
        '.prt'  { return 'Upload' }
        '.asm'  { return 'Upload' }
        '.drw'  { return 'Upload' }
        default { return 'Skip' }
    }
}


function Upload-File {
    <#
    .SYNOPSIS
        Upload a file to the PDM-Web API.

    .DESCRIPTION
        Uses multipart/form-data to upload file with item_number.
    #>
    param(
        [string]$FilePath,
        [string]$ItemNumber
    )

    $uri = "$($Config.ApiUrl)/files/upload"
    $fileName = [IO.Path]::GetFileName($FilePath)

    # Use .NET HttpClient for reliable multipart upload
    Add-Type -AssemblyName System.Net.Http

    $httpClient = New-Object System.Net.Http.HttpClient
    $form = New-Object System.Net.Http.MultipartFormDataContent

    # Add item_number field
    $itemField = New-Object System.Net.Http.StringContent($ItemNumber)
    $form.Add($itemField, "item_number")

    # Add file (use comma to prevent array unrolling)
    $fileBytes = [IO.File]::ReadAllBytes($FilePath)
    $fileContent = New-Object System.Net.Http.ByteArrayContent(,$fileBytes)

    # Determine content type
    $ext = [IO.Path]::GetExtension($FilePath).ToLower()
    $mimeType = switch ($ext) {
        '.pdf'  { 'application/pdf' }
        '.step' { 'application/step' }
        '.stp'  { 'application/step' }
        '.dxf'  { 'application/dxf' }
        '.svg'  { 'image/svg+xml' }
        '.prt'  { 'application/octet-stream' }
        '.asm'  { 'application/octet-stream' }
        '.drw'  { 'application/octet-stream' }
        default { 'application/octet-stream' }
    }

    $fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse($mimeType)
    $form.Add($fileContent, "file", $fileName)

    try {
        $response = $httpClient.PostAsync($uri, $form).Result

        if (-not $response.IsSuccessStatusCode) {
            $errorBody = $response.Content.ReadAsStringAsync().Result
            throw "Upload failed ($($response.StatusCode)): $errorBody"
        }

        $result = $response.Content.ReadAsStringAsync().Result | ConvertFrom-Json
        return $result
    }
    finally {
        $form.Dispose()
        $httpClient.Dispose()
    }
}


function Upload-BOM {
    <#
    .SYNOPSIS
        Parse a BOM text file and upload to API.

    .DESCRIPTION
        Uses the Parse-BOMFile function to extract BOM data,
        then calls the /api/bom/bulk endpoint.
    #>
    param([string]$FilePath)

    # Parse the BOM file
    $bomData = Parse-BOMFile -FilePath $FilePath

    if (-not $bomData.parent_item_number) {
        throw "Could not determine parent assembly from BOM file"
    }

    if ($bomData.children.Count -eq 0) {
        throw "No children found in BOM file"
    }

    # Build request body
    $body = @{
        parent_item_number = $bomData.parent_item_number
        children = $bomData.children
        source_file = [IO.Path]::GetFileName($FilePath)
    } | ConvertTo-Json -Depth 5

    $uri = "$($Config.ApiUrl)/bom/bulk"

    $result = Invoke-RestMethod -Uri $uri -Method Post -Body $body -ContentType 'application/json'

    return $result
}


function Upload-MLBOM {
    <#
    .SYNOPSIS
        Parse a multi-level BOM text file and upload to API.

    .DESCRIPTION
        Uses Parse-MLBOMFile to extract hierarchical BOM data,
        then calls /api/bom/bulk once per assembly in the tree.
        Each assembly's BOM is replaced independently.

    .RETURNS
        Hashtable with aggregate stats:
        - assemblies_processed: Number of assemblies uploaded
        - total_items_created: Sum of items created
        - total_items_updated: Sum of items updated
        - total_bom_entries: Sum of BOM entries created
        - details: Array of per-assembly results
    #>
    param([string]$FilePath)

    # Parse the multi-level BOM file
    $bomGroups = Parse-MLBOMFile -FilePath $FilePath

    if ($bomGroups.Count -eq 0) {
        throw "No assembly BOM groups found in MLBOM file"
    }

    $sourceFile = [IO.Path]::GetFileName($FilePath)
    $uri = "$($Config.ApiUrl)/bom/bulk"

    $totalCreated = 0
    $totalUpdated = 0
    $totalBomEntries = 0
    $details = @()

    foreach ($group in $bomGroups) {
        if ($group.children.Count -eq 0) { continue }

        # Build request body for this assembly
        $body = @{
            parent_item_number = $group.parent_item_number
            children           = $group.children
            source_file        = $sourceFile
        } | ConvertTo-Json -Depth 5

        $result = Invoke-RestMethod -Uri $uri -Method Post -Body $body -ContentType 'application/json'

        $totalCreated += $result.items_created
        $totalUpdated += $result.items_updated
        $totalBomEntries += $result.bom_entries_created
        $details += $result

        Write-Log "  MLBOM: $($group.parent_item_number) -> $($result.bom_entries_created) children ($($result.items_created) new, $($result.items_updated) updated)"
    }

    return @{
        assemblies_processed = $bomGroups.Count
        total_items_created  = $totalCreated
        total_items_updated  = $totalUpdated
        total_bom_entries    = $totalBomEntries
        details              = $details
    }
}


function Update-Parameters {
    <#
    .SYNOPSIS
        Parse a parameter text file and update item properties.

    .DESCRIPTION
        Uses the Parse-ParameterFile function to extract item properties,
        then calls the /api/items/{item_number}?upsert=true endpoint.
    #>
    param([string]$FilePath)

    # Parse the parameter file
    $paramData = Parse-ParameterFile -FilePath $FilePath

    if (-not $paramData.item_number) {
        throw "Could not determine item number from parameter file"
    }

    $itemNumber = $paramData.item_number

    # Build request body (exclude item_number)
    $bodyData = @{}
    foreach ($key in $paramData.Keys) {
        if ($key -ne 'item_number' -and $null -ne $paramData[$key]) {
            $bodyData[$key] = $paramData[$key]
        }
    }

    $body = $bodyData | ConvertTo-Json

    $uri = "$($Config.ApiUrl)/items/$itemNumber`?upsert=true"

    $result = Invoke-RestMethod -Uri $uri -Method Patch -Body $body -ContentType 'application/json'

    return @{ item_number = $itemNumber; result = $result }
}
