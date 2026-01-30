#!/usr/bin/env python3
"""
PDM Worker Queue Processor

Standalone polling loop that picks up pending tasks from the work_queue table,
executes FreeCAD jobs via docker exec, and uploads results to Supabase Storage.

Usage:
    python worker_loop.py

Environment variables (from .env):
    SUPABASE_URL          - Supabase project URL
    SUPABASE_SERVICE_KEY  - Supabase service role key (admin access)
    DOCKER_CONTAINER      - FreeCAD container name (default: pdm-freecad-worker)
    POLL_INTERVAL         - Seconds between polls (default: 5)
    TEMP_DIR              - Local temp directory for file I/O (default: ./files/temp)
"""

import os
import sys
import time
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

# Load .env from backend directory (shared config)
env_path = Path(__file__).resolve().parent.parent / "backend" / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    # Try project root
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Configuration
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
DOCKER_CONTAINER = os.environ.get("DOCKER_CONTAINER", "pdm-freecad-worker")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "5"))
TEMP_DIR = Path(os.environ.get("TEMP_DIR", Path(__file__).resolve().parent.parent / "files" / "temp"))
STORAGE_BUCKET = "pdm-files"

# Task type to job mapping
TASK_MAP = {
    "GENERATE_DXF": {
        "job_type": "flatten",
        "output_suffix": "_flat.dxf",
        "file_type": "DXF",
    },
    "GENERATE_SVG": {
        "job_type": "bend_drawing",
        "output_suffix": "_bends.svg",
        "file_type": "SVG",
    },
}


def log(message: str):
    """Log with timestamp."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}", flush=True)


def now_iso() -> str:
    """Current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat()


def claim_task(supabase, task: dict) -> bool:
    """Atomically claim a task by setting status to processing.

    Returns True if we got it, False if another worker beat us.
    """
    result = supabase.table("work_queue").update({
        "status": "processing",
        "started_at": now_iso(),
    }).eq("id", task["id"]).eq("status", "pending").execute()

    return bool(result.data)


def complete_task(supabase, task_id: str, error_message: str = None):
    """Mark a task as completed or failed."""
    update = {
        "status": "failed" if error_message else "completed",
        "completed_at": now_iso(),
    }
    if error_message:
        update["error_message"] = error_message[:2000]  # Truncate long errors

    supabase.table("work_queue").update(update).eq("id", task_id).execute()


def download_step_file(supabase, file_path: str, item_number: str) -> Path:
    """Download a STEP file from Supabase Storage to local temp dir.

    file_path from DB looks like: pdm-files/csp0030/csp0030.step
    or just: csp0030/csp0030.step (path within bucket)
    """
    # Strip bucket prefix if present
    path_in_bucket = file_path
    if path_in_bucket.startswith(f"{STORAGE_BUCKET}/"):
        path_in_bucket = path_in_bucket[len(STORAGE_BUCKET) + 1:]

    # Create temp directory for this item
    item_dir = TEMP_DIR / item_number
    item_dir.mkdir(parents=True, exist_ok=True)

    # Download
    filename = Path(path_in_bucket).name
    local_path = item_dir / filename

    log(f"  Downloading {path_in_bucket} -> {local_path}")
    data = supabase.storage.from_(STORAGE_BUCKET).download(path_in_bucket)
    local_path.write_bytes(data)

    return local_path


def run_freecad_job(job_type: str, input_path: Path, output_path: Path) -> subprocess.CompletedProcess:
    """Execute a FreeCAD job via docker exec."""
    # Convert host paths to container paths
    # Host: ./files/temp/csp0030/csp0030.step
    # Container: /data/files/temp/csp0030/csp0030.step
    container_input = str(input_path).replace(str(TEMP_DIR.parent), "/data/files")
    container_output = str(output_path).replace(str(TEMP_DIR.parent), "/data/files")

    # Normalize path separators for Linux container
    container_input = container_input.replace("\\", "/")
    container_output = container_output.replace("\\", "/")

    cmd = [
        "docker", "exec", DOCKER_CONTAINER,
        "python3", "/scripts/run_job.py",
        job_type, container_input, container_output,
    ]

    log(f"  Running: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return result


def upload_output(supabase, output_path: Path, item_number: str, item_id: str, file_type: str):
    """Upload generated DXF/SVG to Supabase Storage and register in files table."""
    filename = output_path.name
    path_in_bucket = f"{item_number}/{filename}"
    storage_path = f"{STORAGE_BUCKET}/{path_in_bucket}"

    content = output_path.read_bytes()
    file_size = len(content)

    # Determine MIME type
    mime_types = {
        ".dxf": "application/dxf",
        ".svg": "image/svg+xml",
    }
    ext = output_path.suffix.lower()
    content_type = mime_types.get(ext, "application/octet-stream")

    # Upload to storage (update if exists)
    log(f"  Uploading {filename} -> {path_in_bucket}")
    try:
        supabase.storage.from_(STORAGE_BUCKET).upload(
            path_in_bucket, content,
            file_options={"content-type": content_type}
        )
    except Exception as e:
        if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
            supabase.storage.from_(STORAGE_BUCKET).update(
                path_in_bucket, content,
                file_options={"content-type": content_type}
            )
        else:
            raise

    # Upsert file record in files table
    existing = supabase.table("files").select("id, iteration") \
        .eq("item_id", item_id).eq("file_name", filename).limit(1).execute()

    if existing.data:
        new_iteration = existing.data[0]["iteration"] + 1
        supabase.table("files").update({
            "file_path": storage_path,
            "file_size": file_size,
            "iteration": new_iteration,
        }).eq("id", existing.data[0]["id"]).execute()
        log(f"  Updated file record: {filename} (iteration {new_iteration})")
    else:
        supabase.table("files").insert({
            "item_id": item_id,
            "file_type": file_type,
            "file_name": filename,
            "file_path": storage_path,
            "file_size": file_size,
            "iteration": 1,
        }).execute()
        log(f"  Created file record: {filename}")


def process_task(supabase, task: dict):
    """Process a single work queue task."""
    task_id = task["id"]
    task_type = task["task_type"]
    item_id = task["item_id"]
    payload = task.get("payload") or {}
    file_path = payload.get("file_path", "")

    if task_type not in TASK_MAP:
        complete_task(supabase, task_id, f"Unknown task type: {task_type}")
        return

    mapping = TASK_MAP[task_type]

    # Get item number from item_id
    item_result = supabase.table("items").select("item_number").eq("id", item_id).limit(1).execute()
    if not item_result.data:
        complete_task(supabase, task_id, f"Item not found: {item_id}")
        return

    item_number = item_result.data[0]["item_number"]
    log(f"Processing {task_type} for {item_number}")

    item_dir = TEMP_DIR / item_number

    try:
        # 1. Download STEP file
        input_path = download_step_file(supabase, file_path, item_number)

        # 2. Determine output path
        stem = input_path.stem  # e.g. "csp0030"
        output_filename = f"{stem}{mapping['output_suffix']}"
        output_path = item_dir / output_filename

        # 3. Run FreeCAD
        result = run_freecad_job(mapping["job_type"], input_path, output_path)

        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip() or f"Exit code {result.returncode}"
            log(f"  FAILED: {error}")
            complete_task(supabase, task_id, error)
            return

        # 4. Verify output exists
        if not output_path.exists():
            complete_task(supabase, task_id, f"Output file not created: {output_filename}")
            return

        # 5. Upload output
        upload_output(supabase, output_path, item_number, item_id, mapping["file_type"])

        # 6. Mark completed
        complete_task(supabase, task_id)
        log(f"  Completed {task_type} for {item_number} -> {output_filename}")

    except Exception as e:
        log(f"  ERROR: {e}")
        complete_task(supabase, task_id, str(e))

    finally:
        # Clean up temp files for this item
        if item_dir.exists():
            shutil.rmtree(item_dir, ignore_errors=True)


def main():
    """Main polling loop."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        log("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        sys.exit(1)

    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    log("=" * 50)
    log("PDM Worker Queue Processor Starting")
    log(f"  Supabase URL: {SUPABASE_URL}")
    log(f"  Docker container: {DOCKER_CONTAINER}")
    log(f"  Poll interval: {POLL_INTERVAL}s")
    log(f"  Temp directory: {TEMP_DIR}")
    log("=" * 50)

    # Ensure temp directory exists
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        try:
            # Fetch one pending task (oldest first)
            result = supabase.table("work_queue") \
                .select("*") \
                .eq("status", "pending") \
                .order("created_at") \
                .limit(1) \
                .execute()

            if result.data:
                task = result.data[0]

                # Try to claim it
                if claim_task(supabase, task):
                    process_task(supabase, task)
                else:
                    log(f"Task {task['id']} already claimed by another worker")

        except KeyboardInterrupt:
            log("Shutting down...")
            break
        except Exception as e:
            log(f"Poll error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
