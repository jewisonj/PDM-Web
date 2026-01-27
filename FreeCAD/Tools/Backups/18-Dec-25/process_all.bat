@echo off
REM Batch Process All STEP Files
REM Processes all .step files in the current directory
REM Generates both DXF flat patterns and SVG bend drawings

setlocal enabledelayedexpansion

REM Get the directory where this batch file is located
set "SCRIPT_DIR=%~dp0"
set "FLATTEN_SCRIPT=%SCRIPT_DIR%Flatten sheetmetal portable.py"
set "DRAWING_SCRIPT=%SCRIPT_DIR%Create bend drawing portable.py"

REM Try to find FreeCAD
set "FREECAD_CMD="

if exist "%SCRIPT_DIR%..\bin\freecadcmd.exe" (
    set "FREECAD_CMD=%SCRIPT_DIR%..\bin\freecadcmd.exe"
    goto :found
)

where freecadcmd.exe >nul 2>&1
if %errorlevel% == 0 (
    set "FREECAD_CMD=freecadcmd.exe"
    goto :found
)

echo ERROR: Could not find freecadcmd.exe
echo Please ensure FreeCAD is installed in D:\FreeCAD\bin\
pause
exit /b 1

:found
echo Found FreeCAD: !FREECAD_CMD!
echo.

REM Count STEP files
set COUNT=0
for %%f in (*.step *.stp) do set /a COUNT+=1

if %COUNT% == 0 (
    echo No STEP files found in current directory: %CD%
    echo.
    echo Usage: Place this batch file in a folder with .step files, or
    echo        Run from a directory containing .step files
    pause
    exit /b 1
)

echo Found %COUNT% STEP file(s) to process
echo.
echo Press any key to start processing, or Ctrl+C to cancel...
pause >nul

set PROCESSED=0
set FAILED=0

echo.
echo ========================================
echo Starting batch processing...
echo ========================================
echo.

for %%f in (*.step *.stp) do (
    echo.
    echo [%date% %time%] Processing: %%f
    echo ----------------------------------------
    
    REM Flatten to DXF
    echo Step 1/2: Creating flat pattern DXF...
    "!FREECAD_CMD!" "%FLATTEN_SCRIPT%" "%%f"
    if !errorlevel! == 0 (
        echo   ✓ DXF created successfully
    ) else (
        echo   ✗ DXF creation failed
        set /a FAILED+=1
    )
    
    REM Create bend drawing
    echo Step 2/2: Creating bend line drawing SVG...
    "!FREECAD_CMD!" "%DRAWING_SCRIPT%" "%%f"
    if !errorlevel! == 0 (
        echo   ✓ SVG created successfully
        set /a PROCESSED+=1
    ) else (
        echo   ✗ SVG creation failed
        set /a FAILED+=1
    )
    
    echo ----------------------------------------
)

echo.
echo ========================================
echo Batch Processing Complete
echo ========================================
echo Total files: %COUNT%
echo Successfully processed: %PROCESSED%
echo Failed: %FAILED%
echo.
echo Output files are in the same directory as input files
echo.
pause
