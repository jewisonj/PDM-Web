@echo off
REM Flatten Sheet Metal - Batch Wrapper
REM Auto-detects FreeCAD location and runs the Python script
REM Usage: flatten_sheetmetal.bat input.step [output.dxf] [k_factor]

setlocal enabledelayedexpansion

REM Get the directory where this batch file is located
set "SCRIPT_DIR=%~dp0"
set "PYTHON_SCRIPT=%SCRIPT_DIR%Flatten sheetmetal portable.py"

REM Try to find FreeCAD in common locations
set "FREECAD_CMD="

REM Check parent directory first (D:\FreeCAD\bin\freecadcmd.exe)
if exist "%SCRIPT_DIR%..\bin\freecadcmd.exe" (
    set "FREECAD_CMD=%SCRIPT_DIR%..\bin\freecadcmd.exe"
    echo Found FreeCAD: !FREECAD_CMD!
    goto :run
)

REM Check if FreeCAD is in PATH
where freecadcmd.exe >nul 2>&1
if %errorlevel% == 0 (
    set "FREECAD_CMD=freecadcmd.exe"
    echo Found FreeCAD in PATH
    goto :run
)

REM Check common installation directories
if exist "C:\Program Files\FreeCAD 0.21\bin\freecadcmd.exe" (
    set "FREECAD_CMD=C:\Program Files\FreeCAD 0.21\bin\freecadcmd.exe"
    echo Found FreeCAD: !FREECAD_CMD!
    goto :run
)

if exist "C:\Program Files\FreeCAD 0.20\bin\freecadcmd.exe" (
    set "FREECAD_CMD=C:\Program Files\FreeCAD 0.20\bin\freecadcmd.exe"
    echo Found FreeCAD: !FREECAD_CMD!
    goto :run
)

REM FreeCAD not found
echo ERROR: Could not find freecadcmd.exe
echo.
echo Please ensure FreeCAD is installed or specify the location manually:
echo   SET FREECAD_PATH=D:\FreeCAD\bin\freecadcmd.exe
echo   %~nx0 input.step
echo.
echo Searched locations:
echo   - %SCRIPT_DIR%..\bin\freecadcmd.exe
echo   - PATH environment variable
echo   - C:\Program Files\FreeCAD 0.21\bin\freecadcmd.exe
echo   - C:\Program Files\FreeCAD 0.20\bin\freecadcmd.exe
pause
exit /b 1

:run
REM Check if Python script exists
if not exist "%PYTHON_SCRIPT%" (
    echo ERROR: Python script not found: %PYTHON_SCRIPT%
    pause
    exit /b 1
)

REM Check if input file was provided
if "%~1"=="" (
    echo Usage: %~nx0 input.step [output.dxf] [k_factor]
    echo.
    echo Examples:
    echo   %~nx0 bracket.step
    echo   %~nx0 bracket.step bracket_flat.dxf
    echo   %~nx0 bracket.step bracket_flat.dxf 0.4
    echo.
    echo K-factor default: 0.35
    pause
    exit /b 1
)

REM Run FreeCAD with the Python script
echo.
echo Running: "!FREECAD_CMD!" "%PYTHON_SCRIPT%" %*
echo.
"!FREECAD_CMD!" "%PYTHON_SCRIPT%" %*

REM Check result
if %errorlevel% == 0 (
    echo.
    echo ========================================
    echo SUCCESS!
    echo ========================================
) else (
    echo.
    echo ========================================
    echo FAILED - Check error messages above
    echo ========================================
)

echo.