#Requires -Version 5.1
<#
.SYNOPSIS
    BOM and Parameter file parser for PDM Upload Service.

.DESCRIPTION
    Parses Creo's fixed-width text BOM exports and parameter updates.

    Expected BOM format (from Creo):
    Model Name         DESCRIPTION            PROJECT   PRO_MP_MASS   PTC_MASTER_MATERIAL  CUT_LENGTH  SMT_THICKNESS
    ---------          -----------            -------   -----------   -----------------    ---------   -----------
     WMA20120.ASM     Assembly               PROJ1     10.5          Steel                -           -
       WMP20080.PRT   Bracket                PROJ1     2.5           Steel                500         3.0
       WMP20090.PRT   Shaft                  PROJ1     1.2           Aluminum             300         2.5
#>

function Parse-BOMFile {
    <#
    .SYNOPSIS
        Parse a Creo BOM text file.

    .RETURNS
        Hashtable with:
        - parent_item_number: The assembly item number
        - children: Array of child items with properties
    #>
    param([string]$FilePath)

    $lines = Get-Content $FilePath -Encoding UTF8

    $result = @{
        parent_item_number = $null
        children = @()
    }

    # Find header line to get column positions
    $headerLine = $null
    $headerIndex = 0
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match 'Model Name') {
            $headerLine = $lines[$i]
            $headerIndex = $i
            break
        }
    }

    if (-not $headerLine) {
        throw "Invalid BOM file: no 'Model Name' header found"
    }

    # Calculate column positions from header
    $cols = @{
        ModelName   = $headerLine.IndexOf('Model Name')
        Description = if ($headerLine.IndexOf('DESCRIPTION') -ge 0) { $headerLine.IndexOf('DESCRIPTION') } else { -1 }
        Project     = if ($headerLine.IndexOf('PROJECT') -ge 0) { $headerLine.IndexOf('PROJECT') } else { -1 }
        Mass        = if ($headerLine.IndexOf('PRO_MP_MASS') -ge 0) { $headerLine.IndexOf('PRO_MP_MASS') } else { -1 }
        Material    = if ($headerLine.IndexOf('PTC_MASTER_MATERIAL') -ge 0) { $headerLine.IndexOf('PTC_MASTER_MATERIAL') } else { -1 }
        CutLength   = if ($headerLine.IndexOf('CUT_LENGTH') -ge 0) { $headerLine.IndexOf('CUT_LENGTH') } else { -1 }
        Thickness   = if ($headerLine.IndexOf('SMT_THICKNESS') -ge 0) { $headerLine.IndexOf('SMT_THICKNESS') } else { -1 }
        CutTime     = if ($headerLine.IndexOf('CUT_TIME') -ge 0) { $headerLine.IndexOf('CUT_TIME') } else { -1 }
        PriceEst    = if ($headerLine.IndexOf('PRICE_EST') -ge 0) { $headerLine.IndexOf('PRICE_EST') } else { -1 }
    }

    # Track children for quantity counting
    $childrenMap = @{}

    # Parse data lines (skip header and separator)
    $inData = $false
    for ($i = $headerIndex + 1; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]

        # Separator line marks start of data
        if ($line -match '^[\s-]+$' -and $line -match '-{3,}') {
            $inData = $true
            continue
        }

        if (-not $inData) { continue }
        if ([string]::IsNullOrWhiteSpace($line)) { continue }

        # Calculate indent level (number of leading spaces)
        $trimmedLine = $line.TrimStart()
        $indent = $line.Length - $trimmedLine.Length

        # Extract item number (3 letters + 4-6 digits, or mmc/spn patterns)
        $itemMatch = [regex]::Match($line, '([A-Za-z]{3}\d{4,6}|mmc[A-Za-z0-9]+|spn[A-Za-z0-9]+)', 'IgnoreCase')

        if (-not $itemMatch.Success) { continue }

        $itemNumber = $itemMatch.Groups[1].Value.ToLower()

        # Skip reference items, skeleton parts, and standard features
        if ($itemNumber.StartsWith("zzz")) { continue }
        if ($line -match '_SKEL\.PRT') { continue }
        if ($line -match 'ASM_RIGHT|ASM_TOP|ASM_FRONT|ASM_DEF_CSYS') { continue }

        # Determine if this is parent assembly or child
        $isAssembly = $line -match '\.ASM'

        if ($indent -lt 3 -and $isAssembly -and -not $result.parent_item_number) {
            # This is the top-level assembly (parent)
            $result.parent_item_number = $itemNumber
        }
        else {
            # This is a child part/subassembly

            # Extract properties from columns
            $description = Get-ColumnValue -Line $line -Cols $cols -StartCol 'Description' -EndCol 'Project'
            $material = Get-ColumnValue -Line $line -Cols $cols -StartCol 'Material' -EndCol 'CutLength'
            $massStr = Get-ColumnValue -Line $line -Cols $cols -StartCol 'Mass' -EndCol 'Material'
            $cutLengthStr = Get-ColumnValue -Line $line -Cols $cols -StartCol 'CutLength' -EndCol 'Thickness'
            $thicknessStr = Get-ColumnValue -Line $line -Cols $cols -StartCol 'Thickness' -EndCol 'CutTime'
            $cutTimeStr = Get-ColumnValue -Line $line -Cols $cols -StartCol 'CutTime' -EndCol 'PriceEst'
            $priceEstStr = Get-ColumnValue -Line $line -Cols $cols -StartCol 'PriceEst' -EndCol $null

            # Parse numeric values
            $mass = $null
            $cutLength = $null
            $thickness = $null
            $cutTime = $null
            $priceEst = $null

            if ($massStr -and $massStr -match '^[\d.]+$') {
                $mass = [double]$massStr
            }
            if ($cutLengthStr -and $cutLengthStr -match '^[\d.]+$') {
                $cutLength = [double]$cutLengthStr
            }
            if ($thicknessStr -and $thicknessStr -match '^[\d.]+$') {
                $thickness = [double]$thicknessStr
            }
            if ($cutTimeStr -and $cutTimeStr -match '^[\d.]+$') {
                $cutTime = [double]$cutTimeStr
            }
            if ($priceEstStr -and $priceEstStr -match '^[\d.]+$') {
                $priceEst = [double]$priceEstStr
            }

            # Check for duplicate (increment quantity)
            if ($childrenMap.ContainsKey($itemNumber)) {
                $childrenMap[$itemNumber].quantity++
            }
            else {
                $childrenMap[$itemNumber] = @{
                    item_number = $itemNumber
                    quantity    = 1
                    name        = if ($description) { $description.Trim() } else { $null }
                    material    = if ($material) { $material.Trim() } else { $null }
                    mass        = $mass
                    cut_length  = $cutLength
                    thickness   = $thickness
                    cut_time    = $cutTime
                    price_est   = $priceEst
                }
            }
        }
    }

    # Convert children map to array
    $result.children = @($childrenMap.Values)

    return $result
}


function Parse-ParameterFile {
    <#
    .SYNOPSIS
        Parse a Creo parameter text file (single item).

    .RETURNS
        Hashtable with item_number and properties.
    #>
    param([string]$FilePath)

    $lines = Get-Content $FilePath -Encoding UTF8

    $result = @{
        item_number = $null
    }

    # Find header line
    $headerLine = $null
    $headerIndex = 0
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match 'Model Name') {
            $headerLine = $lines[$i]
            $headerIndex = $i
            break
        }
    }

    if (-not $headerLine) {
        throw "Invalid parameter file: no 'Model Name' header found"
    }

    # Calculate column positions
    $cols = @{
        ModelName   = $headerLine.IndexOf('Model Name')
        Description = if ($headerLine.IndexOf('DESCRIPTION') -ge 0) { $headerLine.IndexOf('DESCRIPTION') } else { -1 }
        Project     = if ($headerLine.IndexOf('PROJECT') -ge 0) { $headerLine.IndexOf('PROJECT') } else { -1 }
        Mass        = if ($headerLine.IndexOf('PRO_MP_MASS') -ge 0) { $headerLine.IndexOf('PRO_MP_MASS') } else { -1 }
        Material    = if ($headerLine.IndexOf('PTC_MASTER_MATERIAL') -ge 0) { $headerLine.IndexOf('PTC_MASTER_MATERIAL') } else { -1 }
        CutLength   = if ($headerLine.IndexOf('CUT_LENGTH') -ge 0) { $headerLine.IndexOf('CUT_LENGTH') } else { -1 }
        Thickness   = if ($headerLine.IndexOf('SMT_THICKNESS') -ge 0) { $headerLine.IndexOf('SMT_THICKNESS') } else { -1 }
        CutTime     = if ($headerLine.IndexOf('CUT_TIME') -ge 0) { $headerLine.IndexOf('CUT_TIME') } else { -1 }
        PriceEst    = if ($headerLine.IndexOf('PRICE_EST') -ge 0) { $headerLine.IndexOf('PRICE_EST') } else { -1 }
    }

    # Find first data line (after separator)
    $inData = $false
    for ($i = $headerIndex + 1; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]

        if ($line -match '^[\s-]+$' -and $line -match '-{3,}') {
            $inData = $true
            continue
        }

        if (-not $inData) { continue }
        if ([string]::IsNullOrWhiteSpace($line)) { continue }

        # Extract item number
        $itemMatch = [regex]::Match($line, '([A-Za-z]{3}\d{4,6}|mmc[A-Za-z0-9]+|spn[A-Za-z0-9]+)', 'IgnoreCase')

        if ($itemMatch.Success) {
            $result.item_number = $itemMatch.Groups[1].Value.ToLower()

            # Extract properties
            $description = Get-ColumnValue -Line $line -Cols $cols -StartCol 'Description' -EndCol 'Project'
            $material = Get-ColumnValue -Line $line -Cols $cols -StartCol 'Material' -EndCol 'CutLength'
            $massStr = Get-ColumnValue -Line $line -Cols $cols -StartCol 'Mass' -EndCol 'Material'
            $cutLengthStr = Get-ColumnValue -Line $line -Cols $cols -StartCol 'CutLength' -EndCol 'Thickness'
            $thicknessStr = Get-ColumnValue -Line $line -Cols $cols -StartCol 'Thickness' -EndCol 'CutTime'
            $cutTimeStr = Get-ColumnValue -Line $line -Cols $cols -StartCol 'CutTime' -EndCol 'PriceEst'
            $priceEstStr = Get-ColumnValue -Line $line -Cols $cols -StartCol 'PriceEst' -EndCol $null

            if ($description) { $result.name = $description.Trim() }
            if ($material) { $result.material = $material.Trim() }

            if ($massStr -and $massStr -match '^[\d.]+$') {
                $result.mass = [double]$massStr
            }
            if ($cutLengthStr -and $cutLengthStr -match '^[\d.]+$') {
                $result.cut_length = [double]$cutLengthStr
            }
            if ($thicknessStr -and $thicknessStr -match '^[\d.]+$') {
                $result.thickness = [double]$thicknessStr
            }
            if ($cutTimeStr -and $cutTimeStr -match '^[\d.]+$') {
                $result.cut_time = [double]$cutTimeStr
            }
            if ($priceEstStr -and $priceEstStr -match '^[\d.]+$') {
                $result.price_est = [double]$priceEstStr
            }

            # Only process first data line for parameter files
            break
        }
    }

    return $result
}


function Get-ColumnValue {
    <#
    .SYNOPSIS
        Extract value from fixed-width column.
    #>
    param(
        [string]$Line,
        [hashtable]$Cols,
        [string]$StartCol,
        [string]$EndCol
    )

    $start = $Cols[$StartCol]
    if ($start -lt 0) { return $null }

    # Determine end position
    $end = $Line.Length
    if ($EndCol -and $Cols.ContainsKey($EndCol) -and $Cols[$EndCol] -ge 0) {
        $end = $Cols[$EndCol]
    }

    if ($start -ge $Line.Length) { return $null }

    $length = [Math]::Min($end - $start, $Line.Length - $start)
    if ($length -le 0) { return $null }

    $value = $Line.Substring($start, $length).Trim()

    # Return null for placeholder values
    if ($value -eq '-' -or $value -eq '') { return $null }

    return $value
}
