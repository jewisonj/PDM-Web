# ============================================
#   PDM-Library.ps1 (sqlite3.exe version)
# ============================================

$Global:SQLiteExe = "sqlite3.exe"
$Global:PDMRoot   = "D:\PDM_Vault"
$Global:DBPath    = Join-Path $Global:PDMRoot "pdm.sqlite"

# --------------------------------------------
# LOGGING
# --------------------------------------------
$Global:LogPath = Join-Path $Global:PDMRoot "logs\pdm.log"
if (!(Test-Path (Split-Path $Global:LogPath))) {
    New-Item -ItemType Directory -Path (Split-Path $Global:LogPath) | Out-Null
}
function Write-Log {
    param([string]$Message)
    $timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    Add-Content -Path $Global:LogPath -Value "$timestamp $Message"
}

# --------------------------------------------
# EXECUTE SQL (INSERT / UPDATE / DELETE)
# --------------------------------------------
function Exec-SQL {
    param([string]$Query)

    & $Global:SQLiteExe $Global:DBPath "$Query" 2>$null
}

# --------------------------------------------
# QUERY SQL (SELECT)
# returns string[] (rows)
# --------------------------------------------
function Query-SQL {
    param([string]$Query)

    $result = & $Global:SQLiteExe -separator '|' $Global:DBPath "$Query" 2>$null

    if ($LASTEXITCODE -ne 0) {
        Write-Log "SQLite ERROR: $Query"
        return @()
    }

    if ($result -is [string]) { return @($result) }
    return $result
}
