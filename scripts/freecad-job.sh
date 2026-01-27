#!/bin/bash
# FreeCAD Job Runner - Shell script
# Usage: ./freecad-job.sh <job_type> <input_file> [output_file] [k_factor]
#
# Job types:
#   flatten      - Create DXF flat pattern from STEP
#   bend_drawing - Create SVG bend line drawing from STEP
#   convert_stl  - Convert STEP to STL
#   convert_obj  - Convert STEP to OBJ
#
# Examples:
#   ./freecad-job.sh flatten files/part.step
#   ./freecad-job.sh bend_drawing files/part.step files/part_bends.svg 0.4

set -e

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: ./freecad-job.sh <job_type> <input_file> [output_file] [k_factor]"
    echo ""
    echo "Job types:"
    echo "  flatten      - Create DXF flat pattern from STEP"
    echo "  bend_drawing - Create SVG bend line drawing from STEP"
    echo "  convert_stl  - Convert STEP to STL"
    echo "  convert_obj  - Convert STEP to OBJ"
    exit 1
fi

JOB_TYPE="$1"
INPUT_FILE="$2"
OUTPUT_FILE="${3:-}"
K_FACTOR="${4:-}"

# Build args
ARGS="$JOB_TYPE /data/$INPUT_FILE"
[ -n "$OUTPUT_FILE" ] && ARGS="$ARGS /data/$OUTPUT_FILE"
[ -n "$K_FACTOR" ] && ARGS="$ARGS $K_FACTOR"

# Run the job in the FreeCAD container
docker-compose exec freecad-worker python /scripts/run_job.py $ARGS
