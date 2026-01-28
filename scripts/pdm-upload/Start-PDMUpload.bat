@echo off
REM PDM Upload Service Starter
REM Run this to start the file watcher service

title PDM Upload Service
cd /d "%~dp0"

echo ==========================================
echo PDM Upload Service
echo ==========================================
echo.
echo Starting file watcher...
echo Press Ctrl+C to stop
echo.

powershell -ExecutionPolicy Bypass -File "%~dp0PDM-Upload-Service.ps1"

pause
