@echo off
REM STEP to STL Converter - Batch Wrapper
REM Usage: convert_to_stl.bat input.step [output.stl]

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "PYTHON_SCRIPT=%SCRIPT_DIR%convert_to_stl.py"

REM Find FreeCAD
set "FREECAD_CMD="

if exist "%SCRIPT_DIR%..\bin\freecadcmd.exe" (
    set "FREECAD_CMD=%SCRIPT_DIR%..\bin\freecadcmd.exe"
    goto :run
)

where freecadcmd.exe >nul 2>&1
if %errorlevel% == 0 (
    set "FREECAD_CMD=freecadcmd.exe"
    goto :run
)

if exist "C:\Program Files\FreeCAD 0.21\bin\freecadcmd.exe" (
    set "FREECAD_CMD=C:\Program Files\FreeCAD 0.21\bin\freecadcmd.exe"
    goto :run
)

echo ERROR: Could not find freecadcmd.exe
exit /b 1

:run
if not exist "%PYTHON_SCRIPT%" (
    echo ERROR: Python script not found: %PYTHON_SCRIPT%
    exit /b 1
)

if "%~1"=="" (
    echo Usage: %~nx0 input.step [output.stl]
    exit /b 1
)

"!FREECAD_CMD!" "%PYTHON_SCRIPT%" %* 2>&1

exit /b %errorlevel%
