@echo off
REM FreeCAD Job Runner - Windows batch script
REM Usage: freecad-job.bat <job_type> <input_file> [output_file] [k_factor]
REM
REM Job types:
REM   flatten      - Create DXF flat pattern from STEP
REM   bend_drawing - Create SVG bend line drawing from STEP
REM   convert_stl  - Convert STEP to STL
REM   convert_obj  - Convert STEP to OBJ
REM
REM Examples:
REM   freecad-job.bat flatten files\part.step
REM   freecad-job.bat bend_drawing files\part.step files\part_bends.svg 0.4

if "%~1"=="" (
    echo Usage: freecad-job.bat ^<job_type^> ^<input_file^> [output_file] [k_factor]
    echo.
    echo Job types:
    echo   flatten      - Create DXF flat pattern from STEP
    echo   bend_drawing - Create SVG bend line drawing from STEP
    echo   convert_stl  - Convert STEP to STL
    echo   convert_obj  - Convert STEP to OBJ
    exit /b 1
)

set JOB_TYPE=%~1
set INPUT_FILE=%~2
set OUTPUT_FILE=%~3
set K_FACTOR=%~4

REM Convert Windows path to container path
set INPUT_FILE=%INPUT_FILE:\=/%
set OUTPUT_FILE=%OUTPUT_FILE:\=/%

REM Run the job in the FreeCAD container
docker-compose exec freecad-worker python /scripts/run_job.py %JOB_TYPE% /data/%INPUT_FILE% %OUTPUT_FILE% %K_FACTOR%
