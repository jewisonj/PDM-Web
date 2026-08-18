@echo off
REM DXF Processing Dashboard Launcher
REM Opens the dashboard HTML in your default browser

title DXF Dashboard

REM Use local copy if it exists, otherwise use source
if exist "C:\PDM-Upload\dxf_dashboard.html" (
    start "" "C:\PDM-Upload\dxf_dashboard.html"
) else if exist "%~dp0dxf_dashboard.html" (
    start "" "%~dp0dxf_dashboard.html"
) else (
    echo ERROR: dxf_dashboard.html not found!
    echo Run Start-PDMUpload.bat first to sync scripts.
    pause
)
