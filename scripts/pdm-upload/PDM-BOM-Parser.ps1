#Requires -Version 5.1
<#
.SYNOPSIS
    BOM and Parameter file parser for PDM Upload Service.

.DESCRIPTION
    Parses Creo's fixed-width text BOM exports and parameter updates.
    Column positions are detected dynamically from the header line,
    so any column order is supported.

    Expected BOM format (from Creo):
    Model Name         DESCRIPTION            PROJECT   PRO_MP_MASS   PTC_MASTER_MATERIAL  CUT_LENGTH  SMT_THICKNESS
    ---------          -----------            -------   -----------   -----------------    ---------   -----------
     WMA20120.ASM     Assembly               PROJ1     10.5          Steel                -           -
       WMP20080.PRT   Bracket                PROJ1     2.5           Steel                500         3.0
       WMP20090.PRT   Shaft                  PROJ1     1.2           Aluminum             300         2.5
#>


# =============================================================================
# Column Mapping: Creo header name -> DB field name + value type
# To add a new parameter, just add a row here.
# =============================================================================
$script:ColumnMap = @(
    @{ header = 'DESCRIPTION';         field = 'name';       type = 'string' }
    @{ header = 'PRO_MP_MASS';         field = 'mass';       type = 'number' }
    @{ header = 'SMT_THICKNESS';       field = 'thickness';  type = 'number' }
    @{ header = 'PTC_MASTER_MATERIAL'; field = 'material';   type = 'string' }
    @{ header = 'CUT_LENGTH';          field = 'cut_length'; type = 'number' }
    @{ header = 'CUT_TIME';            field = 'cut_time';   type = 'number' }
    @{ header = 'PRICE_EST';           field = 'price_est';  type = 'number' }
)

# Additional headers to track for column boundary detection (not extracted as properties)
$script:BoundaryHeaders = @('Model Name', 'PROJECT', 'Current Rep:')


# =============================================================================
# Shared Helper Functions
# =============================================================================

function Find-HeaderLine {
    <#
    .SYNOPSIS
        Find the header line in a Creo text export and return it with its index.
    #>
    param([string[]]$Lines)

    for ($i = 0; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i] -match 'Model Name') {
            return @{ line = $Lines[$i]; index = $i }
        }
    }
    return $null
}


function Get-HeaderColumns {
    <#
    .SYNOPSIS
        Scan a header line and return column positions for all recognized headers.

    .DESCRIPTION
        Finds positions of all mapped columns plus boundary-only columns.
        Returns a hashtable of column_key -> position (or -1 if not found).
        All positions are detected from the header, so column order doesn't matter.
    #>
    param([string]$HeaderLine)

    $cols = @{}

    # Map property columns (these get extracted as values)
    foreach ($mapping in $script:ColumnMap) {
        $pos = $HeaderLine.IndexOf($mapping.header)
        $cols[$mapping.field] = if ($pos -ge 0) { $pos } else { -1 }
    }

    # Map boundary-only columns (used for column width detection, not extracted)
    foreach ($bh in $script:BoundaryHeaders) {
        $pos = $HeaderLine.IndexOf($bh)
        if ($pos -ge 0) {
            $cols["_boundary_$bh"] = $pos
        }
    }

    return $cols
}


function Get-ColumnValue {
    <#
    .SYNOPSIS
        Extract a single value from a fixed-width line by column key.

    .DESCRIPTION
        Uses the column's start position and dynamically finds the next
        column to the right as the end boundary. Works with any column order.
    #>
    param(
        [string]$Line,
        [hashtable]$Cols,
        [string]$ColKey
    )

    $start = $Cols[$ColKey]
    if ($null -eq $start -or $start -lt 0) { return $null }
    if ($start -ge $Line.Length) { return $null }

    # Find the next column position to the right of $start
    $end = $Line.Length
    foreach ($colPos in $Cols.Values) {
        if ($colPos -is [int] -and $colPos -gt $start -and $colPos -lt $end) {
            $end = $colPos
        }
    }

    $length = $end - $start
    if ($length -le 0) { return $null }

    $value = $Line.Substring($start, [Math]::Min($length, $Line.Length - $start)).Trim()

    if ($value -eq '-' -or $value -eq '') { return $null }

    return $value
}


function Extract-ItemProperties {
    <#
    .SYNOPSIS
        Extract all mapped properties from a data line.

    .DESCRIPTION
        Uses the column mapping to pull each field from the line,
        converting numeric fields to [double]. Returns a hashtable
        of DB field names -> typed values (nulls included).
    #>
    param(
        [string]$Line,
        [hashtable]$Cols
    )

    $props = @{}

    foreach ($mapping in $script:ColumnMap) {
        $raw = Get-ColumnValue -Line $Line -Cols $Cols -ColKey $mapping.field

        if ($mapping.type -eq 'number') {
            if ($raw -and $raw -match '^[\d.]+$') {
                $props[$mapping.field] = [double]$raw
            } else {
                $props[$mapping.field] = $null
            }
        }
        else {
            # string
            $props[$mapping.field] = if ($raw) { $raw.Trim() } else { $null }
        }
    }

    return $props
}


# =============================================================================
# Parse-BOMFile
# =============================================================================

function Parse-BOMFile {
    <#
    .SYNOPSIS
        Parse a Creo single-level BOM text file.

    .RETURNS
        Hashtable with:
        - parent_item_number + parent properties
        - children: Array of child items with properties
    #>
    param([string]$FilePath)

    $lines = Get-Content $FilePath -Encoding UTF8

    $result = @{
        parent_item_number = $null
        parent_name        = $null
        parent_material    = $null
        parent_mass        = $null
        parent_cut_length  = $null
        parent_thickness   = $null
        parent_cut_time    = $null
        parent_price_est   = $null
        children = @()
    }

    $header = Find-HeaderLine -Lines $lines
    if (-not $header) { throw "Invalid BOM file: no 'Model Name' header found" }

    $cols = Get-HeaderColumns -HeaderLine $header.line

    # Track children for quantity counting
    $childrenMap = @{}

    $inData = $false
    for ($i = $header.index + 1; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]

        if ($line -match '^[\s-]+$' -and $line -match '-{3,}') {
            $inData = $true
            continue
        }

        if (-not $inData) { continue }
        if ([string]::IsNullOrWhiteSpace($line)) { continue }

        # Calculate indent level
        $trimmedLine = $line.TrimStart()
        $indent = $line.Length - $trimmedLine.Length

        # Extract item number
        $itemMatch = [regex]::Match($line, '([A-Za-z]{3}\d{4,6}|mmc[A-Za-z0-9]+|spn[A-Za-z0-9]+)', 'IgnoreCase')
        if (-not $itemMatch.Success) { continue }

        $itemNumber = $itemMatch.Groups[1].Value.ToLower()

        # Skip reference items, skeleton parts, and standard features
        if ($itemNumber.StartsWith("zzz")) { continue }
        if ($line -match '_SKEL\.PRT') { continue }
        if ($line -match 'ASM_RIGHT|ASM_TOP|ASM_FRONT|ASM_DEF_CSYS') { continue }

        $isAssembly = $line -match '\.ASM'
        $props = Extract-ItemProperties -Line $line -Cols $cols

        if ($indent -lt 3 -and $isAssembly -and -not $result.parent_item_number) {
            # Top-level assembly (parent)
            $result.parent_item_number = $itemNumber
            $result.parent_name        = $props.name
            $result.parent_material    = $props.material
            $result.parent_mass        = $props.mass
            $result.parent_cut_length  = $props.cut_length
            $result.parent_thickness   = $props.thickness
            $result.parent_cut_time    = $props.cut_time
            $result.parent_price_est   = $props.price_est
        }
        else {
            # Child part/subassembly
            if ($childrenMap.ContainsKey($itemNumber)) {
                $childrenMap[$itemNumber].quantity++
            }
            else {
                $childrenMap[$itemNumber] = @{
                    item_number = $itemNumber
                    quantity    = 1
                    name        = $props.name
                    material    = $props.material
                    mass        = $props.mass
                    cut_length  = $props.cut_length
                    thickness   = $props.thickness
                    cut_time    = $props.cut_time
                    price_est   = $props.price_est
                }
            }
        }
    }

    $result.children = @($childrenMap.Values)
    return $result
}


# =============================================================================
# Parse-ParameterFile
# =============================================================================

function Parse-ParameterFile {
    <#
    .SYNOPSIS
        Parse a Creo parameter text file (single item, first data line only).

    .RETURNS
        Hashtable with item_number and properties.
    #>
    param([string]$FilePath)

    $lines = Get-Content $FilePath -Encoding UTF8

    $result = @{
        item_number = $null
    }

    $header = Find-HeaderLine -Lines $lines
    if (-not $header) { throw "Invalid parameter file: no 'Model Name' header found" }

    $cols = Get-HeaderColumns -HeaderLine $header.line

    $inData = $false
    for ($i = $header.index + 1; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]

        if ($line -match '^[\s-]+$' -and $line -match '-{3,}') {
            $inData = $true
            continue
        }

        if (-not $inData) { continue }
        if ([string]::IsNullOrWhiteSpace($line)) { continue }

        $itemMatch = [regex]::Match($line, '([A-Za-z]{3}\d{4,6}|mmc[A-Za-z0-9]+|spn[A-Za-z0-9]+)', 'IgnoreCase')

        if ($itemMatch.Success) {
            $result.item_number = $itemMatch.Groups[1].Value.ToLower()

            $props = Extract-ItemProperties -Line $line -Cols $cols
            foreach ($key in $props.Keys) {
                $result[$key] = $props[$key]
            }

            # Only process first data line
            break
        }
    }

    return $result
}


# =============================================================================
# Parse-MLBOMFile
# =============================================================================

function Parse-MLBOMFile {
    <#
    .SYNOPSIS
        Parse a Creo multi-level BOM text file preserving hierarchy.

    .DESCRIPTION
        Reads the indentation structure to determine parent-child
        relationships at every assembly level.

    .RETURNS
        Array of hashtables, each with:
        - parent_item_number + parent properties
        - children: Array of direct child items with properties
    #>
    param([string]$FilePath)

    $lines = Get-Content $FilePath -Encoding UTF8

    $header = Find-HeaderLine -Lines $lines
    if (-not $header) { throw "Invalid MLBOM file: no 'Model Name' header found" }

    $cols = Get-HeaderColumns -HeaderLine $header.line

    # First pass: collect all item lines with properties
    $itemLines = @()
    $inData = $false

    for ($i = $header.index + 1; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]

        if ($line -match '^[\s-]+$' -and $line -match '-{3,}') {
            $inData = $true
            continue
        }

        if (-not $inData) { continue }
        if ([string]::IsNullOrWhiteSpace($line)) { continue }

        # Only process lines containing .ASM or .PRT
        if ($line -notmatch '\.(ASM|PRT)') { continue }

        # Skip excluded, skeleton, and datum features
        if ($line -match '\bExclude\b') { continue }
        if ($line -match '_SKEL\.PRT') { continue }
        if ($line -match 'ASM_RIGHT|ASM_TOP|ASM_FRONT|ASM_DEF_CSYS') { continue }

        $itemMatch = [regex]::Match($line, '([A-Za-z]{3}\d{4,6}|mmc[A-Za-z0-9]+|spn[A-Za-z0-9]+)', 'IgnoreCase')
        if (-not $itemMatch.Success) { continue }

        $itemNumber = $itemMatch.Groups[1].Value.ToLower()

        $trimmed = $line.TrimStart()
        $indent = $line.Length - $trimmed.Length

        $isAssembly = $line -match '\.ASM'

        $props = Extract-ItemProperties -Line $line -Cols $cols

        $itemLines += @{
            item_number = $itemNumber
            indent      = $indent
            is_assembly = $isAssembly
            name        = $props.name
            material    = $props.material
            mass        = $props.mass
            cut_length  = $props.cut_length
            thickness   = $props.thickness
            cut_time    = $props.cut_time
            price_est   = $props.price_est
        }
    }

    # Second pass: build parent-child relationships using assembly stack
    $assemblyStack = [System.Collections.ArrayList]@()
    $bomGroups = @{}
    $parentProps = @{}

    foreach ($item in $itemLines) {
        # Pop assemblies at same or deeper indent level
        while ($assemblyStack.Count -gt 0 -and $assemblyStack[$assemblyStack.Count - 1].indent -ge $item.indent) {
            $assemblyStack.RemoveAt($assemblyStack.Count - 1)
        }

        # If there's a parent assembly on the stack, this item is its child
        if ($assemblyStack.Count -gt 0) {
            $parentNumber = $assemblyStack[$assemblyStack.Count - 1].item_number

            if (-not $item.item_number.StartsWith("zzz")) {
                if (-not $bomGroups.ContainsKey($parentNumber)) {
                    $bomGroups[$parentNumber] = @{}
                    $parentEntry = $assemblyStack[$assemblyStack.Count - 1]
                    $parentProps[$parentNumber] = @{
                        name       = $parentEntry.name
                        material   = $parentEntry.material
                        mass       = $parentEntry.mass
                        cut_length = $parentEntry.cut_length
                        thickness  = $parentEntry.thickness
                        cut_time   = $parentEntry.cut_time
                        price_est  = $parentEntry.price_est
                    }
                }

                if ($bomGroups[$parentNumber].ContainsKey($item.item_number)) {
                    $bomGroups[$parentNumber][$item.item_number].quantity++
                }
                else {
                    $bomGroups[$parentNumber][$item.item_number] = @{
                        item_number = $item.item_number
                        quantity    = 1
                        name        = $item.name
                        material    = $item.material
                        mass        = $item.mass
                        cut_length  = $item.cut_length
                        thickness   = $item.thickness
                        cut_time    = $item.cut_time
                        price_est   = $item.price_est
                    }
                }
            }
        }

        # If this is an assembly, push onto the stack
        if ($item.is_assembly) {
            $assemblyStack.Add(@{
                indent      = $item.indent
                item_number = $item.item_number
                name        = $item.name
                material    = $item.material
                mass        = $item.mass
                cut_length  = $item.cut_length
                thickness   = $item.thickness
                cut_time    = $item.cut_time
                price_est   = $item.price_est
            }) | Out-Null
        }
    }

    # Convert to array of BOM groups (include parent properties)
    $result = @()
    foreach ($parentNumber in $bomGroups.Keys) {
        $pp = if ($parentProps.ContainsKey($parentNumber)) { $parentProps[$parentNumber] } else { @{} }
        $result += @{
            parent_item_number = $parentNumber
            parent_name        = $pp.name
            parent_material    = $pp.material
            parent_mass        = $pp.mass
            parent_cut_length  = $pp.cut_length
            parent_thickness   = $pp.thickness
            parent_cut_time    = $pp.cut_time
            parent_price_est   = $pp.price_est
            children           = @($bomGroups[$parentNumber].Values)
        }
    }

    return $result
}
