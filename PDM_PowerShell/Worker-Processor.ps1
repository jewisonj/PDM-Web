. "D:\PDM_PowerShell\PDM-Library.ps1"

# -----------------------------
# Configuration
# -----------------------------
$Global:ToolsPath    = "D:\FreeCAD\Tools"
$Global:FlattenBat   = Join-Path $Global:ToolsPath "flatten_sheetmetal.bat"
$Global:BendDrawBat  = Join-Path $Global:ToolsPath "create_bend_drawing.bat"
$Global:CADDataRoot  = "D:\PDM_Vault\CADData"
$Global:DXFPath      = Join-Path $Global:CADDataRoot "DXF"
$Global:SVGPath      = Join-Path $Global:CADDataRoot "SVG"
$Global:CheckInPath  = Join-Path $Global:CADDataRoot "CheckIn"

$Global:PollInterval = 5  # seconds between work queue checks

Write-Log "PDM Worker Processor Started."
Write-Log "Tools Path: $Global:ToolsPath"

# Verify batch files exist
if (!(Test-Path $Global:FlattenBat)) {
    Write-Log "ERROR: flatten_sheetmetal.bat not found at $Global:FlattenBat"
    exit 1
}

if (!(Test-Path $Global:BendDrawBat)) {
    Write-Log "ERROR: create_bend_drawing.bat not found at $Global:BendDrawBat"
    exit 1
}

# -----------------------------
# Get pending tasks from work_queue
# -----------------------------
function Get-PendingTasks {
    param([string]$TaskType)

    # Call sqlite3 directly with proper separator
    $result = & sqlite3.exe -separator '|' $Global:DBPath "
        SELECT task_id, item_number, file_path, task_type
        FROM work_queue
        WHERE status = 'Pending'
          AND task_type = '$TaskType'
        ORDER BY created_at ASC
        LIMIT 1;
    " 2>$null

    if (-not $result -or $result.Count -eq 0) {
        return $null
    }

    # Parse the pipe-separated result
    $parts = $result -split '\|'

    if ($parts.Count -lt 4) {
        Write-Log "ERROR: Invalid task data returned from database: $result"
        return $null
    }

    return [PSCustomObject]@{
        TaskId     = [int]$parts[0]
        ItemNumber = $parts[1]
        FilePath   = $parts[2]
        TaskType   = $parts[3]
    }
}

# -----------------------------
# Update task status
# -----------------------------
function Update-TaskStatus {
    param(
        [int]$TaskId,
        [string]$Status  # 'Processing', 'Completed', 'Failed'
    )

    $timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")

    if ($Status -eq 'Processing') {
        Exec-SQL "
            UPDATE work_queue
            SET status='$Status', started_at='$timestamp'
            WHERE task_id=$TaskId;
        "
    }
    elseif ($Status -eq 'Completed' -or $Status -eq 'Failed') {
        Exec-SQL "
            UPDATE work_queue
            SET status='$Status', completed_at='$timestamp'
            WHERE task_id=$TaskId;
        "
    }
}

# -----------------------------
# Generate DXF using existing batch file
# -----------------------------
function Generate-DXF {
    param(
        [string]$ItemNumber,
        [string]$CADFilePath
    )

    Write-Log "Generating DXF for $ItemNumber from $CADFilePath"

    # Check if CAD file exists
    if (!(Test-Path $CADFilePath)) {
        Write-Log "ERROR: CAD file not found: $CADFilePath"
        return $false
    }

    # Get file extension to determine if it's STEP or native format
    $ext = [System.IO.Path]::GetExtension($CADFilePath).ToLower()
    
    # For native Creo files (.prt, .asm), we need STEP first
    if ($ext -eq ".prt" -or $ext -eq ".asm") {
        # Check if STEP file exists
        $stepFile = Join-Path (Join-Path $Global:CADDataRoot "STEP") "$ItemNumber.step"
        
        if (Test-Path $stepFile) {
            Write-Log "Using existing STEP file: $stepFile"
            $CADFilePath = $stepFile
        }
        else {
            Write-Log "WARNING: No STEP file found for $ItemNumber. Attempting direct processing..."
        }
    }

    try {
        # Define output path directly in CheckIn folder
        $outputDXF = Join-Path $Global:CheckInPath "$ItemNumber.dxf"
        
        Write-Log "Running flatten_sheetmetal.bat with output: $outputDXF"
        
        # Run batch file with input and output arguments
        Push-Location $Global:ToolsPath
        
        $process = Start-Process -FilePath $Global:FlattenBat `
                                 -ArgumentList "`"$CADFilePath`" `"$outputDXF`"" `
                                 -NoNewWindow `
                                 -Wait `
                                 -PassThru `
                                 -RedirectStandardOutput "$env:TEMP\dxf_stdout.txt" `
                                 -RedirectStandardError "$env:TEMP\dxf_stderr.txt"
        
        Pop-Location
        
        $stdout = Get-Content "$env:TEMP\dxf_stdout.txt" -Raw -ErrorAction SilentlyContinue
        $stderr = Get-Content "$env:TEMP\dxf_stderr.txt" -Raw -ErrorAction SilentlyContinue

        # Check exit code - batch file returns 0 on success
        if ($process.ExitCode -eq 0) {
            Write-Log "DXF generation completed successfully (exit code 0)"
            Write-Log "File created at: $outputDXF (CheckIn-Watcher will register it)"
            return $true
        }
        else {
            Write-Log "ERROR: DXF generation failed (exit code $($process.ExitCode))"
            if ($stdout) { Write-Log "Output: $stdout" }
            if ($stderr) { Write-Log "Errors: $stderr" }
            return $false
        }
    }
    catch {
        Write-Log "ERROR generating DXF for $ItemNumber : $_"
        Pop-Location
        return $false
    }
}

# -----------------------------
# Generate SVG using existing batch file
# -----------------------------
function Generate-SVG {
    param(
        [string]$ItemNumber,
        [string]$CADFilePath
    )

    Write-Log "Generating SVG for $ItemNumber from $CADFilePath"

    # Check if CAD file exists
    if (!(Test-Path $CADFilePath)) {
        Write-Log "ERROR: CAD file not found: $CADFilePath"
        return $false
    }

    # Get file extension
    $ext = [System.IO.Path]::GetExtension($CADFilePath).ToLower()
    
    # For native Creo files, prefer STEP
    if ($ext -eq ".prt" -or $ext -eq ".asm") {
        $stepFile = Join-Path (Join-Path $Global:CADDataRoot "STEP") "$ItemNumber.step"
        
        if (Test-Path $stepFile) {
            Write-Log "Using existing STEP file: $stepFile"
            $CADFilePath = $stepFile
        }
        else {
            Write-Log "WARNING: No STEP file found for $ItemNumber."
        }
    }

    try {
        # Define output path directly in CheckIn folder
        $outputSVG = Join-Path $Global:CheckInPath "$ItemNumber.svg"
        
        Write-Log "Running create_bend_drawing.bat with output: $outputSVG"
        
        # Run batch file with input and output arguments
        Push-Location $Global:ToolsPath
        
        $process = Start-Process -FilePath $Global:BendDrawBat `
                                 -ArgumentList "`"$CADFilePath`" `"$outputSVG`"" `
                                 -NoNewWindow `
                                 -Wait `
                                 -PassThru `
                                 -RedirectStandardOutput "$env:TEMP\svg_stdout.txt" `
                                 -RedirectStandardError "$env:TEMP\svg_stderr.txt"
        
        Pop-Location
        
        $stdout = Get-Content "$env:TEMP\svg_stdout.txt" -Raw -ErrorAction SilentlyContinue
        $stderr = Get-Content "$env:TEMP\svg_stderr.txt" -Raw -ErrorAction SilentlyContinue

        # Check exit code - batch file returns 0 on success
        if ($process.ExitCode -eq 0) {
            Write-Log "SVG generation completed successfully (exit code 0)"
            Write-Log "File created at: $outputSVG (CheckIn-Watcher will register it)"
            return $true
        }
        else {
            Write-Log "ERROR: SVG generation failed (exit code $($process.ExitCode))"
            if ($stdout) { Write-Log "Output: $stdout" }
            if ($stderr) { Write-Log "Errors: $stderr" }
            return $false
        }
    }
    catch {
        Write-Log "ERROR generating SVG for $ItemNumber : $_"
        Pop-Location
        return $false
    }
}

# -----------------------------
# Process a single task
# -----------------------------
function Process-Task {
    param([PSCustomObject]$Task)

    Write-Log "Processing task $($Task.TaskId): $($Task.TaskType) for $($Task.ItemNumber)"

    # Mark as processing
    Update-TaskStatus -TaskId $Task.TaskId -Status 'Processing'

    $success = $false

    switch ($Task.TaskType) {
        'GENERATE_DXF' {
            $success = Generate-DXF -ItemNumber $Task.ItemNumber -CADFilePath $Task.FilePath
        }
        'GENERATE_SVG' {
            $success = Generate-SVG -ItemNumber $Task.ItemNumber -CADFilePath $Task.FilePath
        }
        default {
            Write-Log "Unknown task type: $($Task.TaskType)"
        }
    }

    # Update final status
    if ($success) {
        Update-TaskStatus -TaskId $Task.TaskId -Status 'Completed'
        Write-Log "Task $($Task.TaskId) completed successfully"
    }
    else {
        Update-TaskStatus -TaskId $Task.TaskId -Status 'Failed'
        Write-Log "Task $($Task.TaskId) failed"
    }
}

# -----------------------------
# Main worker loop
# -----------------------------
Write-Host "PDM Worker Processor is running..."
Write-Host "Using tools from: $Global:ToolsPath"
Write-Host "Monitoring task types: GENERATE_DXF, GENERATE_SVG"
Write-Host "Press Ctrl+C to stop"
Write-Host ""

$taskTypes = @('GENERATE_DXF', 'GENERATE_SVG')

while ($true) {
    foreach ($taskType in $taskTypes) {
        # Get one pending task of this type
        $task = Get-PendingTasks -TaskType $taskType

        if ($null -ne $task) {
            Process-Task -Task $task
        }
    }

    # Sleep before next poll
    Start-Sleep -Seconds $Global:PollInterval
}