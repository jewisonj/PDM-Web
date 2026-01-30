#!/usr/bin/env python3
"""
DXF Nesting Worker

Polls the work_queue table for NEST_PARTS tasks and executes nesting jobs.
Downloads DXF inputs from Supabase Storage, runs BLF nesting, and uploads
nested DXF output sheets back to storage.

Usage:
    python nest_worker.py

Environment variables:
    SUPABASE_URL          - Supabase project URL
    SUPABASE_SERVICE_KEY  - Supabase service role key
    POLL_INTERVAL         - Seconds between polls (default: 5)
    TEMP_DIR              - Local temp directory (default: /tmp/nest-work)
"""

import os
import sys
import json
import time
import shutil
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

from dxf_parser import parse_dxf_to_polygons, get_bounding_box, get_total_area
from nester import nest_parts
from dxf_writer import write_nested_sheet

# Load environment
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "5"))
TEMP_DIR = Path(os.environ.get("TEMP_DIR", "/tmp/nest-work"))
STORAGE_BUCKET = "pdm-files"


def log(message: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}", flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def claim_task(supabase, task: dict) -> bool:
    """Atomically claim a task."""
    result = supabase.table("work_queue").update({
        "status": "processing",
        "started_at": now_iso(),
    }).eq("id", task["id"]).eq("status", "pending").execute()
    return bool(result.data)


def complete_task(supabase, task_id: str, error_message: str = None):
    """Mark task as completed or failed."""
    update = {
        "status": "failed" if error_message else "completed",
        "completed_at": now_iso(),
    }
    if error_message:
        update["error_message"] = error_message[:2000]
    supabase.table("work_queue").update(update).eq("id", task_id).execute()


def process_nest_task(supabase, task: dict):
    """Process a NEST_PARTS task end-to-end."""
    task_id = task["id"]
    payload = task.get("payload") or {}
    nest_job_id = payload.get("nest_job_id")

    if not nest_job_id:
        complete_task(supabase, task_id, "Missing nest_job_id in payload")
        return

    log(f"Processing nest job: {nest_job_id}")

    work_dir = TEMP_DIR / nest_job_id
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Update nest_jobs status to processing
        supabase.table("nest_jobs").update({
            "status": "processing",
        }).eq("id", nest_job_id).execute()

        # 2. Fetch job parameters
        job_result = supabase.table("nest_jobs").select("*").eq("id", nest_job_id).single().execute()
        if not job_result.data:
            raise ValueError(f"Nest job not found: {nest_job_id}")
        job = job_result.data

        # 3. Fetch job items
        items_result = supabase.table("nest_job_items").select("*").eq("nest_job_id", nest_job_id).execute()
        if not items_result.data:
            raise ValueError("No items in nest job")
        job_items = items_result.data

        log(f"  Job: {job['material']} {job['thickness']}\" on {job['sheet_width_in']}x{job['sheet_height_in']} sheet")
        log(f"  Items: {len(job_items)} parts, {sum(i['quantity'] for i in job_items)} total pieces")

        # 4. Download all DXF files
        dxf_paths = {}  # item_number -> local path
        for item in job_items:
            file_path = item["dxf_file_path"]
            # Strip bucket prefix if present
            path_in_bucket = file_path
            if path_in_bucket.startswith(f"{STORAGE_BUCKET}/"):
                path_in_bucket = path_in_bucket[len(STORAGE_BUCKET) + 1:]

            local_path = work_dir / f"{item['item_number']}.dxf"
            log(f"  Downloading {path_in_bucket}")

            try:
                data = supabase.storage.from_(STORAGE_BUCKET).download(path_in_bucket)
                local_path.write_bytes(data)
                dxf_paths[item["item_number"]] = str(local_path)
            except Exception as e:
                log(f"  WARNING: Failed to download DXF for {item['item_number']}: {e}")
                continue

        if not dxf_paths:
            raise ValueError("Failed to download any DXF files")

        # 5. Parse DXFs to polygons
        parts_for_nesting = []
        for item in job_items:
            if item["item_number"] not in dxf_paths:
                continue

            log(f"  Parsing {item['item_number']}...")
            polygons = parse_dxf_to_polygons(dxf_paths[item["item_number"]])

            if not polygons:
                log(f"  WARNING: No valid polygons found in {item['item_number']}")
                continue

            # Use the largest polygon as the part outline
            outline = polygons[0]
            bbox_w, bbox_h = get_bounding_box(polygons)
            area = get_total_area(polygons)

            # Update job item with geometry metadata
            supabase.table("nest_job_items").update({
                "bounding_box_w": round(bbox_w, 4),
                "bounding_box_h": round(bbox_h, 4),
                "area_sq_in": round(area, 4),
            }).eq("id", item["id"]).execute()

            parts_for_nesting.append({
                "id": item["item_number"],
                "polygon": outline,
                "quantity": item["quantity"],
            })

        if not parts_for_nesting:
            raise ValueError("No valid geometry found in any DXF files")

        log(f"  Nesting {len(parts_for_nesting)} unique parts...")

        # 6. Run nesting
        result = nest_parts(
            parts=parts_for_nesting,
            sheet_width=float(job["sheet_width_in"]),
            sheet_height=float(job["sheet_height_in"]),
            spacing=float(job["spacing_in"]),
            margin=float(job["margin_in"]),
            rotation_step=int(job["rotation_step_deg"]),
        )

        log(f"  Nesting complete: {result.total_sheets} sheets, {result.total_parts_placed} parts placed")

        # 7. Generate output DXFs and upload
        output_prefix = job.get("output_prefix", f"projects/unknown/nests/{nest_job_id}/")
        nest_result_rows = []

        for sheet in result.sheets:
            output_filename = f"sheet_{sheet.index:02d}.dxf"
            output_path = work_dir / output_filename

            log(f"  Writing {output_filename} ({len(sheet.placements)} parts, {sheet.utilization:.1%} util)")

            write_nested_sheet(
                sheet=sheet,
                original_dxf_paths=dxf_paths,
                output_path=str(output_path),
            )

            # Upload to Supabase Storage
            storage_path = f"{output_prefix}{output_filename}"
            content = output_path.read_bytes()

            log(f"  Uploading {storage_path}")
            try:
                supabase.storage.from_(STORAGE_BUCKET).upload(
                    storage_path, content,
                    file_options={"content-type": "application/dxf"},
                )
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    supabase.storage.from_(STORAGE_BUCKET).update(
                        storage_path, content,
                        file_options={"content-type": "application/dxf"},
                    )
                else:
                    raise

            # Build placements data for the manifest
            placements_data = []
            for p in sheet.placements:
                placements_data.append({
                    "part_id": p.part_id,
                    "instance": p.instance,
                    "x": round(p.x, 4),
                    "y": round(p.y, 4),
                    "rotation": p.rotation,
                })

            nest_result_rows.append({
                "nest_job_id": nest_job_id,
                "sheet_index": sheet.index,
                "dxf_path": storage_path,
                "utilization": round(sheet.utilization, 4),
                "parts_on_sheet": len(sheet.placements),
                "placements": placements_data,
            })

        # 8. Upload manifest
        manifest = {
            "job_id": nest_job_id,
            "material": job["material"],
            "thickness": float(job["thickness"]),
            "sheet": {
                "width_in": float(job["sheet_width_in"]),
                "height_in": float(job["sheet_height_in"]),
                "margin_in": float(job["margin_in"]),
            },
            "params": {
                "spacing_in": float(job["spacing_in"]),
                "rotation_step_deg": int(job["rotation_step_deg"]),
            },
            "results": {
                "sheets": result.total_sheets,
                "parts_placed": result.total_parts_placed,
                "avg_utilization": round(result.avg_utilization, 4),
            },
            "outputs": [
                {
                    "sheet_index": r["sheet_index"],
                    "dxf_path": r["dxf_path"],
                    "utilization": r["utilization"],
                    "parts_on_sheet": r["parts_on_sheet"],
                    "placements": r["placements"],
                }
                for r in nest_result_rows
            ],
        }

        manifest_path = f"{output_prefix}manifest.json"
        manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")

        try:
            supabase.storage.from_(STORAGE_BUCKET).upload(
                manifest_path, manifest_bytes,
                file_options={"content-type": "application/json"},
            )
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                supabase.storage.from_(STORAGE_BUCKET).update(
                    manifest_path, manifest_bytes,
                    file_options={"content-type": "application/json"},
                )
            else:
                raise

        # 9. Insert nest_results rows
        if nest_result_rows:
            supabase.table("nest_results").insert(nest_result_rows).execute()

        # 10. Update nest_jobs with summary
        supabase.table("nest_jobs").update({
            "status": "completed",
            "sheets_used": result.total_sheets,
            "total_parts_placed": result.total_parts_placed,
            "avg_utilization": round(result.avg_utilization, 4),
            "manifest": manifest,
            "completed_at": now_iso(),
        }).eq("id", nest_job_id).execute()

        # 11. Mark work_queue task completed
        complete_task(supabase, task_id)
        log(f"  Nest job {nest_job_id} completed successfully")

    except Exception as e:
        log(f"  ERROR: {e}")
        # Mark both nest_jobs and work_queue as failed
        supabase.table("nest_jobs").update({
            "status": "failed",
            "error_message": str(e)[:2000],
            "completed_at": now_iso(),
        }).eq("id", nest_job_id).execute()
        complete_task(supabase, task_id, str(e))

    finally:
        # Clean up temp files
        if work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)


def main():
    """Main polling loop."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        log("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        sys.exit(1)

    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    log("=" * 50)
    log("DXF Nesting Worker Starting")
    log(f"  Supabase URL: {SUPABASE_URL}")
    log(f"  Poll interval: {POLL_INTERVAL}s")
    log(f"  Temp directory: {TEMP_DIR}")
    log("=" * 50)

    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        try:
            # Poll for NEST_PARTS tasks only
            result = supabase.table("work_queue") \
                .select("*") \
                .eq("status", "pending") \
                .eq("task_type", "NEST_PARTS") \
                .order("created_at") \
                .limit(1) \
                .execute()

            if result.data:
                task = result.data[0]
                if claim_task(supabase, task):
                    process_nest_task(supabase, task)
                else:
                    log(f"Task {task['id']} already claimed")

        except KeyboardInterrupt:
            log("Shutting down...")
            break
        except Exception as e:
            log(f"Poll error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
