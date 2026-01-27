@echo off
REM Create Bend Drawing - Batch Wrapper
REM Auto-detects FreeCAD location and runs the Python script
REM Usage: create_bend_drawing.bat input.step [output.svg] [k_factor]

setlocal enabledelayedexpansion

REM Get the directory where this batch file is located
set "SCRIPT_DIR=%~dp0"
set "PYTHON_SCRIPT=%SCRIPT_DIR%Create bend drawing portable.py"

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
    echo Usage: %~nx0 input.step [output.svg] [k_factor]
    echo.
    echo Examples:
    echo   %~nx0 bracket.step
    echo   %~nx0 bracket.step bracket_bends.svg
    echo   %~nx0 bracket.step bracket_bends.svg 0.4
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

REM REM Check result
REM if %errorlevel% == 0 (
    REM echo.
    REM echo ========================================
    REM echo SUCCESS!
    REM echo ========================================
    REM echo.
    REM echo Opening SVG in browser...
    
    REM REM Find the output SVG file
    REM REM If user specified output, use that, otherwise find the auto-generated one
    REM if not "%~2"=="" (
        REM set "SVG_FILE=%~2"
    REM ) else (
        REM REM Auto-generated filename is input_bends.svg
        REM for %%f in ("%~1") do set "SVG_FILE=%%~dpnf_bends.svg"
    REM )
    
    REM REM Open in default browser
    REM start "" "!SVG_FILE!"
REM ) else (
    REM echo.
    REM echo ========================================
    REM echo FAILED - Check error messages above
    REM echo ========================================
REM )

echo.