@echo off
REM PDM Upload Service Starter
REM Run this to start the file watcher service

title PDM Upload Service
cd /d "C:\PDM-Upload"

REM Sync scripts from project source before starting
set "SOURCE=J:\PDM-Web\scripts\pdm-upload"
if exist "%SOURCE%\PDM-Upload-Service.ps1" (
    echo Syncing scripts from %SOURCE% ...
    copy /Y "%SOURCE%\PDM-Upload-Config.ps1"    "C:\PDM-Upload\" >nul
    copy /Y "%SOURCE%\PDM-Upload-Functions.ps1"  "C:\PDM-Upload\" >nul
    copy /Y "%SOURCE%\PDM-Upload-Service.ps1"    "C:\PDM-Upload\" >nul
    copy /Y "%SOURCE%\PDM-BOM-Parser.ps1"        "C:\PDM-Upload\" >nul
    echo Scripts synced.
) else (
    echo WARNING: Project source not found at %SOURCE%, using local copies.
)

echo.
echo ==========================================
echo PDM Upload Service
echo ==========================================
echo.
echo Starting file watcher...
echo Press Ctrl+C to stop
echo.

powershell -ExecutionPolicy Bypass -File "C:\PDM-Upload\PDM-Upload-Service.ps1"

pause
