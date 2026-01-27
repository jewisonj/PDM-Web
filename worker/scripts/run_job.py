#!/usr/bin/env python3
"""
FreeCAD Job Runner - Executes processing tasks in the FreeCAD container

This script is called by the backend API to process CAD files.
It runs inside the Docker container.

Job types:
- flatten: Create DXF flat pattern from STEP file
- bend_drawing: Create SVG bend line drawing from STEP file
- convert_stl: Convert STEP to STL
- convert_obj: Convert STEP to OBJ
"""

import sys
import os
import json
import subprocess
from datetime import datetime


def log(message):
    """Log with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def run_freecad_script(script_name, input_file, output_file=None, extra_args=None):
    """Run a FreeCAD script with the given arguments"""
    script_path = f"/scripts/{script_name}"

    if not os.path.exists(script_path):
        raise FileNotFoundError(f"Script not found: {script_path}")

    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")

    cmd = ["freecadcmd", script_path, input_file]

    if output_file:
        cmd.append(output_file)

    if extra_args:
        cmd.extend(extra_args)

    log(f"Running: {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        log(f"STDERR: {result.stderr}")
        raise RuntimeError(f"FreeCAD script failed: {result.stderr}")

    log(f"STDOUT: {result.stdout}")
    return result.stdout


def flatten_sheetmetal(input_file, output_file=None, k_factor=0.35):
    """Create DXF flat pattern from STEP file"""
    log(f"Flattening sheet metal: {input_file}")

    extra_args = [str(k_factor)] if k_factor != 0.35 else None

    return run_freecad_script(
        "Flatten sheetmetal portable.py",
        input_file,
        output_file,
        extra_args
    )


def create_bend_drawing(input_file, output_file=None, k_factor=0.35):
    """Create SVG bend line drawing from STEP file"""
    log(f"Creating bend drawing: {input_file}")

    extra_args = [str(k_factor)] if k_factor != 0.35 else None

    return run_freecad_script(
        "Create bend drawing portable.py",
        input_file,
        output_file,
        extra_args
    )


def convert_to_stl(input_file, output_file=None):
    """Convert STEP to STL"""
    log(f"Converting to STL: {input_file}")

    return run_freecad_script(
        "convert_to_stl.py",
        input_file,
        output_file
    )


def convert_to_obj(input_file, output_file=None):
    """Convert STEP to OBJ"""
    log(f"Converting to OBJ: {input_file}")

    return run_freecad_script(
        "convert_to_obj.py",
        input_file,
        output_file
    )


def process_job(job_type, input_file, output_file=None, **kwargs):
    """Process a job based on type"""
    job_handlers = {
        "flatten": flatten_sheetmetal,
        "bend_drawing": create_bend_drawing,
        "convert_stl": convert_to_stl,
        "convert_obj": convert_to_obj,
    }

    if job_type not in job_handlers:
        raise ValueError(f"Unknown job type: {job_type}. Valid types: {list(job_handlers.keys())}")

    handler = job_handlers[job_type]
    return handler(input_file, output_file, **kwargs)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python run_job.py <job_type> <input_file> [output_file] [k_factor]")
        print("")
        print("Job types:")
        print("  flatten      - Create DXF flat pattern from STEP")
        print("  bend_drawing - Create SVG bend line drawing from STEP")
        print("  convert_stl  - Convert STEP to STL")
        print("  convert_obj  - Convert STEP to OBJ")
        print("")
        print("Examples:")
        print("  python run_job.py flatten /data/files/part.step")
        print("  python run_job.py bend_drawing /data/files/part.step /data/files/part_bends.svg 0.4")
        sys.exit(1)

    job_type = sys.argv[1]
    input_file = sys.argv[2]
    output_file = sys.argv[3] if len(sys.argv) > 3 else None
    k_factor = float(sys.argv[4]) if len(sys.argv) > 4 else 0.35

    try:
        result = process_job(job_type, input_file, output_file, k_factor=k_factor)
        log("Job completed successfully")
        sys.exit(0)
    except Exception as e:
        log(f"Job failed: {e}")
        sys.exit(1)
