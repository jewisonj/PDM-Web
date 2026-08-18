@echo off
title PDM Worker Loop
cd /d "%~dp0"
echo ============================================================
echo PDM Worker Loop - DXF/SVG Generation Processor
echo ============================================================
echo.
echo This worker polls the work_queue table and processes tasks.
echo Press Ctrl+C to stop.
echo.
python worker_loop.py
pause
