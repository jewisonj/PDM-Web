@echo off
title DXF Processing Dashboard
cd /d "%~dp0"
echo Starting DXF Processing Dashboard...
echo.
python dxf_report_server.py
pause
