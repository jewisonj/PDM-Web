@echo off
REM Install Right-Click Context Menu for STEP Files
REM This script adds "Create Flat DXF" and "Create Bend Drawing" to the right-click menu

echo ========================================
echo FreeCAD Sheet Metal Context Menu Installer
echo ========================================
echo.
echo This will add the following options to your right-click menu for .step and .stp files:
echo   - Create Flat DXF
echo   - Create Bend Drawing
echo.
echo You must run this as Administrator!
echo.
pause

REM Check if running as administrator
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: This script must be run as Administrator!
    echo.
    echo Right-click this file and select "Run as administrator"
    pause
    exit /b 1
)

echo Running as Administrator - OK
echo.

REM Get the directory where this batch file is located
set "SCRIPT_DIR=%~dp0"

REM Verify the batch files exist
if not exist "%SCRIPT_DIR%flatten_sheetmetal.bat" (
    echo ERROR: flatten_sheetmetal.bat not found in %SCRIPT_DIR%
    pause
    exit /b 1
)

if not exist "%SCRIPT_DIR%create_bend_drawing_open.bat" (
    echo ERROR: create_bend_drawing_open.bat not found in %SCRIPT_DIR%
    pause
    exit /b 1
)

echo Found batch files in: %SCRIPT_DIR%
echo.

REM Check if FreeCAD exists
if exist "%SCRIPT_DIR%..\bin\freecadcmd.exe" (
    echo Found FreeCAD at: %SCRIPT_DIR%..\bin\freecadcmd.exe
) else (
    echo WARNING: Could not find FreeCAD at expected location
    echo The context menu will still be installed, but may not work until FreeCAD is installed
)
echo.

REM Create temporary registry file
set "REG_FILE=%TEMP%\freecad_context_menu.reg"

echo Creating registry entries...
echo.

(
echo Windows Registry Editor Version 5.00
echo.
echo ; Add "Create Flat DXF" to .step files
echo [HKEY_CLASSES_ROOT\SystemFileAssociations\.step\shell\FreeCAD_Flatten]
echo @="Create Flat DXF"
echo "Icon"="%SCRIPT_DIR:\=\\%flatten_sheetmetal.bat"
echo.
echo [HKEY_CLASSES_ROOT\SystemFileAssociations\.step\shell\FreeCAD_Flatten\command]
echo @="\"%SCRIPT_DIR:\=\\%flatten_sheetmetal.bat\" \"%%1\""
echo.
echo ; Add "Create Bend Drawing" to .step files
echo [HKEY_CLASSES_ROOT\SystemFileAssociations\.step\shell\FreeCAD_BendDrawing]
echo @="Create Bend Drawing"
echo "Icon"="%SCRIPT_DIR:\=\\%create_bend_drawing_open.bat"
echo.
echo [HKEY_CLASSES_ROOT\SystemFileAssociations\.step\shell\FreeCAD_BendDrawing\command]
echo @="\"%SCRIPT_DIR:\=\\%create_bend_drawing_open.bat\" \"%%1\""
echo.
echo ; Add "Create Flat DXF" to .stp files
echo [HKEY_CLASSES_ROOT\SystemFileAssociations\.stp\shell\FreeCAD_Flatten]
echo @="Create Flat DXF"
echo "Icon"="%SCRIPT_DIR:\=\\%flatten_sheetmetal.bat"
echo.
echo [HKEY_CLASSES_ROOT\SystemFileAssociations\.stp\shell\FreeCAD_Flatten\command]
echo @="\"%SCRIPT_DIR:\=\\%flatten_sheetmetal.bat\" \"%%1\""
echo.
echo ; Add "Create Bend Drawing" to .stp files
echo [HKEY_CLASSES_ROOT\SystemFileAssociations\.stp\shell\FreeCAD_BendDrawing]
echo @="Create Bend Drawing"
echo "Icon"="%SCRIPT_DIR:\=\\%create_bend_drawing_open.bat"
echo.
echo [HKEY_CLASSES_ROOT\SystemFileAssociations\.stp\shell\FreeCAD_BendDrawing\command]
echo @="\"%SCRIPT_DIR:\=\\%create_bend_drawing_open.bat\" \"%%1\""
) > "%REG_FILE%"

echo Registry file created at: %REG_FILE%
echo.
echo Importing registry entries...
regedit /s "%REG_FILE%"

if %errorlevel% == 0 (
    echo.
    echo ========================================
    echo SUCCESS!
    echo ========================================
    echo.
    echo Context menu options have been installed!
    echo.
    echo You can now right-click any .step or .stp file and select:
    echo   - "Create Flat DXF"
    echo   - "Create Bend Drawing"
    echo.
    echo The SVG will automatically open in your browser after creation.
) else (
    echo.
    echo ========================================
    echo FAILED
    echo ========================================
    echo.
    echo Could not import registry entries.
    echo Please check that you are running as Administrator.
)

REM Clean up temp file
del "%REG_FILE%" 2>nul

echo.
pause