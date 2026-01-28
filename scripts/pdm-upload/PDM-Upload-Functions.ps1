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

    # Check for specific text file names first
    switch ($fileName) {
        'param.txt'  { return 'Parameters' }
        'bom.txt'    { return 'BOM' }
        'mlbom.txt'  { return 'MLBOM' }
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
        Creates the item if it doesn't exist.
    #>
    param(
        [string]$FilePath,
        [string]$ItemNumber
    )

    $uri = "$($Config.ApiUrl)/files/upload"
    $fileName = [IO.Path]::GetFileName($FilePath)

    # Build multipart form
    $boundary = [System.Guid]::NewGuid().ToString()
    $LF = "`r`n"

    # Read file bytes
    $fileBytes = [IO.File]::ReadAllBytes($FilePath)
    $fileEnc = [System.Text.Encoding]::GetEncoding('ISO-8859-1').GetString($fileBytes)

    # Determine content type
    $ext = [IO.Path]::GetExtension($FilePath).ToLower()
    $contentType = switch ($ext) {
        '.pdf'  { 'application/pdf' }
        '.step' { 'application/step' }
        '.stp'  { 'application/step' }
        '.dxf'  { 'application/dxf' }
        '.svg'  { 'image/svg+xml' }
        default { 'application/octet-stream' }
    }

    $body = @"
--$boundary$LF
Content-Disposition: form-data; name="item_number"$LF
$LF
$ItemNumber$LF
--$boundary$LF
Content-Disposition: form-data; name="file"; filename="$fileName"$LF
Content-Type: $contentType$LF
$LF
$fileEnc$LF
--$boundary--$LF
"@

    $headers = @{
        "Content-Type" = "multipart/form-data; boundary=$boundary"
    }

    $result = Invoke-RestMethod -Uri $uri -Method Post -Body $body -Headers $headers -ContentType "multipart/form-data; boundary=$boundary"

    return $result
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
