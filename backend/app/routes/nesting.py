"""DXF Nesting API routes.

Provides endpoints for:
- Grouping project parts by material + thickness
- Creating nesting jobs
- Checking job status and results
- Downloading nested sheet DXFs
"""

from fastapi import APIRouter, HTTPException
from uuid import UUID
from typing import Optional
from pydantic import BaseModel

from ..services.supabase import get_supabase_admin

router = APIRouter(prefix="/nesting", tags=["nesting"])


# === Request/Response Models ===

class NestJobCreate(BaseModel):
    material: str
    thickness: float
    sheet_width_in: float
    sheet_height_in: float
    sheet_label: Optional[str] = None
    spacing_in: float = 0.125
    margin_in: float = 0.5
    rotation_step_deg: int = 5


# === Endpoints ===

@router.get("/projects/{project_id}/groups")
async def get_nest_groups(project_id: UUID):
    """
    Get parts grouped by material + thickness for nesting.

    Returns groups with part counts, total pieces, and DXF availability.
    Only includes parts (item_number 3rd char == 'p') that are not supplier parts.
    """
    supabase = get_supabase_admin()

    # Get all project parts with item details
    parts_result = supabase.table("mrp_project_parts") \
        .select("quantity, item_id, items(id, item_number, name, material, thickness, is_supplier_part)") \
        .eq("project_id", str(project_id)) \
        .execute()

    if not parts_result.data:
        return {"groups": []}

    # Get all DXF files for items in this project
    item_ids = [p["item_id"] for p in parts_result.data if p.get("items")]
    dxf_lookup = {}
    if item_ids:
        files_result = supabase.table("files") \
            .select("item_id, file_path") \
            .eq("file_type", "DXF") \
            .in_("item_id", item_ids) \
            .execute()
        for f in (files_result.data or []):
            dxf_lookup[f["item_id"]] = f["file_path"]

    # Group by (material, thickness)
    groups = {}
    for pp in parts_result.data:
        item = pp.get("items")
        if not item:
            continue

        # Skip supplier parts and non-part items
        if item.get("is_supplier_part"):
            continue
        item_number = item.get("item_number", "")
        if len(item_number) < 3 or item_number[2] != "p":
            continue

        material = item.get("material") or "Unknown"
        thickness = item.get("thickness") or 0
        group_key = f"{material.lower().strip()}_{thickness}"

        if group_key not in groups:
            groups[group_key] = {
                "material": material,
                "thickness": thickness,
                "group_key": group_key,
                "part_count": 0,
                "total_pieces": 0,
                "parts_with_dxf": 0,
                "parts": [],
            }

        has_dxf = item["id"] in dxf_lookup
        groups[group_key]["parts"].append({
            "item_id": item["id"],
            "item_number": item_number,
            "name": item.get("name"),
            "quantity": pp["quantity"],
            "has_dxf": has_dxf,
            "dxf_file_path": dxf_lookup.get(item["id"]),
        })
        groups[group_key]["part_count"] += 1
        groups[group_key]["total_pieces"] += pp["quantity"]
        if has_dxf:
            groups[group_key]["parts_with_dxf"] += 1

    # Sort groups: most parts first
    sorted_groups = sorted(groups.values(), key=lambda g: g["total_pieces"], reverse=True)

    return {"groups": sorted_groups}


@router.post("/projects/{project_id}/nest")
async def create_nest_job(project_id: UUID, body: NestJobCreate):
    """
    Create a nesting job for a material+thickness group.

    Finds all parts in the project matching the material and thickness,
    creates a nest job record, populates job items from BOM quantities,
    and queues a NEST_PARTS task for the worker.
    """
    supabase = get_supabase_admin()

    # Verify project exists and get project_code for storage path
    project_result = supabase.table("mrp_projects") \
        .select("id, project_code") \
        .eq("id", str(project_id)) \
        .single() \
        .execute()

    if not project_result.data:
        raise HTTPException(status_code=404, detail="Project not found")

    project_code = project_result.data["project_code"]

    # Get parts matching material + thickness that have DXFs
    parts_result = supabase.table("mrp_project_parts") \
        .select("quantity, item_id, items(id, item_number, name, material, thickness, is_supplier_part)") \
        .eq("project_id", str(project_id)) \
        .execute()

    # Filter to matching parts with DXFs
    matching_items = []
    item_ids = []
    for pp in (parts_result.data or []):
        item = pp.get("items")
        if not item:
            continue
        if item.get("is_supplier_part"):
            continue
        item_number = item.get("item_number", "")
        if len(item_number) < 3 or item_number[2] != "p":
            continue
        item_material = (item.get("material") or "Unknown").strip()
        item_thickness = item.get("thickness") or 0
        if item_material.lower() == body.material.lower().strip() and float(item_thickness) == float(body.thickness):
            matching_items.append({"item": item, "quantity": pp["quantity"]})
            item_ids.append(item["id"])

    if not item_ids:
        raise HTTPException(status_code=400, detail="No matching parts found for this material and thickness")

    # Get DXF files for these items
    files_result = supabase.table("files") \
        .select("item_id, file_path") \
        .eq("file_type", "DXF") \
        .in_("item_id", item_ids) \
        .execute()

    dxf_lookup = {}
    for f in (files_result.data or []):
        dxf_lookup[f["item_id"]] = f["file_path"]

    # Filter to only items with DXFs
    nestable_items = [mi for mi in matching_items if mi["item"]["id"] in dxf_lookup]

    if not nestable_items:
        raise HTTPException(status_code=400, detail="No parts in this group have DXF files")

    # Create nest job
    job_data = {
        "project_id": str(project_id),
        "material": body.material,
        "thickness": body.thickness,
        "sheet_width_in": body.sheet_width_in,
        "sheet_height_in": body.sheet_height_in,
        "sheet_label": body.sheet_label,
        "spacing_in": body.spacing_in,
        "margin_in": body.margin_in,
        "rotation_step_deg": body.rotation_step_deg,
        "status": "pending",
        "output_prefix": f"projects/{project_code}/nests/",
    }

    job_result = supabase.table("nest_jobs").insert(job_data).execute()
    if not job_result.data:
        raise HTTPException(status_code=500, detail="Failed to create nest job")
    nest_job = job_result.data[0]
    nest_job_id = nest_job["id"]

    # Update output_prefix with job ID
    output_prefix = f"projects/{project_code}/nests/{nest_job_id}/"
    supabase.table("nest_jobs").update({"output_prefix": output_prefix}).eq("id", nest_job_id).execute()

    # Create nest job items
    job_items = []
    for mi in nestable_items:
        item = mi["item"]
        job_items.append({
            "nest_job_id": nest_job_id,
            "item_id": item["id"],
            "item_number": item["item_number"],
            "quantity": mi["quantity"],
            "dxf_file_path": dxf_lookup[item["id"]],
        })

    supabase.table("nest_job_items").insert(job_items).execute()

    # Create work queue entry
    wq_data = {
        "task_type": "NEST_PARTS",
        "status": "pending",
        "payload": {"nest_job_id": nest_job_id},
    }
    wq_result = supabase.table("work_queue").insert(wq_data).execute()

    if wq_result.data:
        wq_id = wq_result.data[0]["id"]
        supabase.table("nest_jobs").update({"work_queue_id": wq_id}).eq("id", nest_job_id).execute()

    return {
        "job_id": nest_job_id,
        "status": "pending",
        "material": body.material,
        "thickness": body.thickness,
        "parts_count": len(nestable_items),
        "total_pieces": sum(mi["quantity"] for mi in nestable_items),
        "sheet_size": f"{body.sheet_width_in} x {body.sheet_height_in} in",
    }


@router.get("/jobs/{nest_job_id}")
async def get_nest_job(nest_job_id: UUID):
    """Get nest job status, items, and results."""
    supabase = get_supabase_admin()

    # Get job
    job_result = supabase.table("nest_jobs") \
        .select("*") \
        .eq("id", str(nest_job_id)) \
        .single() \
        .execute()

    if not job_result.data:
        raise HTTPException(status_code=404, detail="Nest job not found")

    # Get job items
    items_result = supabase.table("nest_job_items") \
        .select("*") \
        .eq("nest_job_id", str(nest_job_id)) \
        .execute()

    # Get results if completed
    results = []
    if job_result.data["status"] == "completed":
        results_result = supabase.table("nest_results") \
            .select("*") \
            .eq("nest_job_id", str(nest_job_id)) \
            .order("sheet_index") \
            .execute()
        results = results_result.data or []

    return {
        "job": job_result.data,
        "items": items_result.data or [],
        "results": results,
    }


@router.get("/projects/{project_id}/jobs")
async def list_nest_jobs(project_id: UUID):
    """List all nest jobs for a project, newest first."""
    supabase = get_supabase_admin()

    jobs_result = supabase.table("nest_jobs") \
        .select("*") \
        .eq("project_id", str(project_id)) \
        .order("created_at", desc=True) \
        .execute()

    return {"jobs": jobs_result.data or []}


@router.get("/jobs/{nest_job_id}/sheets/{sheet_index}/download")
async def download_nest_sheet(nest_job_id: UUID, sheet_index: int):
    """Get a signed download URL for a nested sheet DXF."""
    supabase = get_supabase_admin()

    # Get the result row
    result = supabase.table("nest_results") \
        .select("dxf_path") \
        .eq("nest_job_id", str(nest_job_id)) \
        .eq("sheet_index", sheet_index) \
        .single() \
        .execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Sheet not found")

    dxf_path = result.data["dxf_path"]

    try:
        url_result = supabase.storage.from_("pdm-files").create_signed_url(dxf_path, 3600)
        return {
            "url": url_result["signedURL"],
            "filename": f"sheet_{sheet_index:02d}.dxf",
            "expires_in": 3600,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not generate download URL: {str(e)}")


@router.get("/jobs/{nest_job_id}/sheets/{sheet_index}/svg")
async def get_nest_sheet_svg(nest_job_id: UUID, sheet_index: int):
    """Get a signed URL for the SVG preview of a nested sheet."""
    supabase = get_supabase_admin()

    result = supabase.table("nest_results") \
        .select("svg_path") \
        .eq("nest_job_id", str(nest_job_id)) \
        .eq("sheet_index", sheet_index) \
        .single() \
        .execute()

    if not result.data or not result.data.get("svg_path"):
        raise HTTPException(status_code=404, detail="SVG preview not available")

    svg_path = result.data["svg_path"]

    try:
        url_result = supabase.storage.from_("pdm-files").create_signed_url(svg_path, 3600)
        return {
            "url": url_result["signedURL"],
            "filename": f"sheet_{sheet_index:02d}.svg",
            "expires_in": 3600,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not generate SVG URL: {str(e)}")


@router.delete("/jobs/{nest_job_id}")
async def delete_nest_job(nest_job_id: UUID):
    """Delete a nest job, its results, and all output files from storage."""
    supabase = get_supabase_admin()
    job_id = str(nest_job_id)

    # Verify job exists
    job_result = supabase.table("nest_jobs").select("id, output_prefix").eq("id", job_id).single().execute()
    if not job_result.data:
        raise HTTPException(status_code=404, detail="Nest job not found")

    # Get all result rows to find files to delete
    results = supabase.table("nest_results").select("dxf_path, svg_path").eq("nest_job_id", job_id).execute()

    # Delete files from storage
    storage_paths = []
    for row in (results.data or []):
        if row.get("dxf_path"):
            storage_paths.append(row["dxf_path"])
        if row.get("svg_path"):
            storage_paths.append(row["svg_path"])

    # Also delete manifest if output_prefix is set
    output_prefix = job_result.data.get("output_prefix")
    if output_prefix:
        storage_paths.append(f"{output_prefix}manifest.json")

    if storage_paths:
        try:
            supabase.storage.from_("pdm-files").remove(storage_paths)
        except Exception:
            pass  # Best-effort cleanup, don't fail the delete

    # Delete database rows (nest_results first due to FK, then job items, then job)
    supabase.table("nest_results").delete().eq("nest_job_id", job_id).execute()
    supabase.table("nest_job_items").delete().eq("nest_job_id", job_id).execute()
    supabase.table("work_queue").delete().eq("payload->>nest_job_id", job_id).execute()
    supabase.table("nest_jobs").delete().eq("id", job_id).execute()

    return {"deleted": True}
