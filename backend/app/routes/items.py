"""Items API routes."""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from uuid import UUID

from ..services.supabase import get_supabase_admin
from ..services.cutting import calculate_cut_time
from ..models.schemas import Item, ItemCreate, ItemUpdate, ItemWithFiles, ItemSearchParams

router = APIRouter(prefix="/items", tags=["items"])


@router.get("", response_model=list[Item])
async def list_items(
    q: Optional[str] = Query(None, description="Search term"),
    lifecycle_state: Optional[str] = None,
    project_id: Optional[UUID] = None,
    is_supplier_part: Optional[bool] = None,
    limit: int = Query(50, le=1000),
    offset: int = 0,
):
    """List items with optional filtering."""
    supabase = get_supabase_admin()

    # Join with projects to get project name
    query = supabase.table("items").select("*, projects(name)")

    # Apply filters
    if q:
        # Search in item_number and name
        query = query.or_(f"item_number.ilike.%{q}%,name.ilike.%{q}%")
    if lifecycle_state:
        query = query.eq("lifecycle_state", lifecycle_state)
    if project_id:
        query = query.eq("project_id", str(project_id))
    if is_supplier_part is not None:
        query = query.eq("is_supplier_part", is_supplier_part)

    # Pagination and ordering
    query = query.order("item_number").range(offset, offset + limit - 1)

    result = query.execute()

    # Flatten project name into each item
    items = []
    for item in result.data:
        project_data = item.pop("projects", None)
        if project_data:
            item["project_name"] = project_data.get("name")
        else:
            item["project_name"] = None
        items.append(item)

    return items


@router.get("/{item_number}", response_model=ItemWithFiles)
async def get_item(item_number: str):
    """Get item by item_number with associated files."""
    # Use admin client - this endpoint is called by the PowerShell local service
    # which doesn't carry user auth tokens. RLS only allows 'authenticated' role
    # for SELECT, so anon key returns 0 rows and .single() throws.
    supabase = get_supabase_admin()

    try:
        result = supabase.table("items").select("*, projects(name)").eq("item_number", item_number.lower()).single().execute()
    except Exception:
        raise HTTPException(status_code=404, detail=f"Item {item_number} not found")

    if not result.data:
        raise HTTPException(status_code=404, detail=f"Item {item_number} not found")

    item = result.data

    # Flatten project name
    project_data = item.pop("projects", None)
    if project_data:
        item["project_name"] = project_data.get("name")
    else:
        item["project_name"] = None

    # Get associated files
    files_result = supabase.table("files").select("*").eq("item_id", item["id"]).execute()
    item["files"] = files_result.data or []

    return item


@router.post("", response_model=Item)
async def create_item(item: ItemCreate):
    """Create a new item."""
    supabase = get_supabase_admin()

    # Normalize item_number to lowercase
    item_data = item.model_dump()
    item_data["item_number"] = item_data["item_number"].lower()

    # Convert UUID to string if present
    if item_data.get("project_id"):
        item_data["project_id"] = str(item_data["project_id"])

    try:
        result = supabase.table("items").insert(item_data).execute()
        return result.data[0]
    except Exception as e:
        if "duplicate key" in str(e).lower():
            raise HTTPException(status_code=409, detail=f"Item {item.item_number} already exists")
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{item_number}", response_model=Item)
async def update_item(item_number: str, item: ItemUpdate, upsert: bool = False):
    """
    Update an existing item, or create it if upsert=True.

    Args:
        item_number: The item number to update
        item: The fields to update
        upsert: If True, create the item if it doesn't exist (default: False)

    Uses admin client for upsert operations (trusted internal service).
    """
    # Use admin client for upsert (internal service), regular client otherwise
    supabase = get_supabase_admin() if upsert else get_supabase_admin()
    normalized_number = item_number.lower()

    # Filter out None values AND cut_time (cut_time is calculated by MRP, not uploaded)
    update_data = {k: v for k, v in item.model_dump().items() if v is not None and k != "cut_time"}

    if not update_data and not upsert:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Convert UUID to string if present
    if update_data.get("project_id"):
        update_data["project_id"] = str(update_data["project_id"])

    # Try to update first
    result = supabase.table("items").update(update_data).eq("item_number", normalized_number).execute()

    if result.data:
        updated_item = result.data[0]
        # Recalculate cut_time if we have required data
        material = updated_item.get("material")
        thickness = updated_item.get("thickness")
        cut_length = updated_item.get("cut_length")
        if material and thickness and cut_length:
            new_cut_time = calculate_cut_time(material, float(thickness), float(cut_length), supabase)
            if new_cut_time:
                supabase.table("items").update({"cut_time": new_cut_time}).eq("id", updated_item["id"]).execute()
                updated_item["cut_time"] = new_cut_time
        return updated_item

    # Item doesn't exist - create if upsert mode
    if upsert:
        # Determine if it's a supplier part
        is_supplier = normalized_number.startswith("mmc") or normalized_number.startswith("spn")

        new_item = {
            "item_number": normalized_number,
            "name": normalized_number.upper(),
            "revision": "A",
            "iteration": 1,
            "lifecycle_state": "Design",
            "is_supplier_part": is_supplier,
            **update_data
        }
        try:
            create_result = supabase.table("items").insert(new_item).execute()
            created_item = create_result.data[0]
            # Recalculate cut_time if we have required data
            material = created_item.get("material")
            thickness = created_item.get("thickness")
            cut_length = created_item.get("cut_length")
            if material and thickness and cut_length:
                new_cut_time = calculate_cut_time(material, float(thickness), float(cut_length), supabase)
                if new_cut_time:
                    supabase.table("items").update({"cut_time": new_cut_time}).eq("id", created_item["id"]).execute()
                    created_item["cut_time"] = new_cut_time
            return created_item
        except Exception as e:
            if "duplicate key" in str(e).lower() or "23505" in str(e):
                # Item exists but update returned no data (schema cache lag)
                # Retry the update
                retry_result = supabase.table("items").update(update_data).eq("item_number", normalized_number).execute()
                if retry_result.data:
                    return retry_result.data[0]
                # Fall through to fetch the item as-is
                fetch_result = supabase.table("items").select("*").eq("item_number", normalized_number).single().execute()
                return fetch_result.data
            raise HTTPException(status_code=400, detail=str(e))

    raise HTTPException(status_code=404, detail=f"Item {item_number} not found")


@router.delete("/{item_number}")
async def delete_item(item_number: str):
    """Delete an item."""
    supabase = get_supabase_admin()

    result = supabase.table("items").delete().eq("item_number", item_number.lower()).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail=f"Item {item_number} not found")

    return {"message": f"Item {item_number} deleted"}


@router.get("/{item_number}/history")
async def get_item_history(item_number: str):
    """Get lifecycle history for an item."""
    supabase = get_supabase_admin()

    try:
        item_result = supabase.table("items").select("id").eq("item_number", item_number.lower()).single().execute()
    except Exception:
        raise HTTPException(status_code=404, detail=f"Item {item_number} not found")

    if not item_result.data:
        raise HTTPException(status_code=404, detail=f"Item {item_number} not found")

    # Get history
    history = supabase.table("lifecycle_history").select("*").eq("item_id", item_result.data["id"]).order("changed_at", desc=True).execute()

    return history.data


@router.post("/recalculate-cut-times")
async def recalculate_all_cut_times():
    """
    Batch recalculate cut_time for all items that have material, thickness, and cut_length.

    This is useful after:
    - Updating cutting_parameters (speeds, machinability, exponent)
    - Changing handling_time_min in cost_settings
    - Initial migration to calculated cut times

    Returns count of items updated.
    """
    supabase = get_supabase_admin()

    # Fetch all items with required fields for cut time calculation
    result = supabase.table("items") \
        .select("id, item_number, material, thickness, cut_length") \
        .not_.is_("material", "null") \
        .not_.is_("thickness", "null") \
        .not_.is_("cut_length", "null") \
        .execute()

    if not result.data:
        return {"message": "No items found with material, thickness, and cut_length", "items_updated": 0}

    updated_count = 0
    skipped_count = 0

    for item in result.data:
        try:
            new_cut_time = calculate_cut_time(
                item["material"],
                float(item["thickness"]),
                float(item["cut_length"]),
                supabase
            )

            if new_cut_time:
                supabase.table("items") \
                    .update({"cut_time": new_cut_time}) \
                    .eq("id", item["id"]) \
                    .execute()
                updated_count += 1
            else:
                skipped_count += 1
        except Exception:
            skipped_count += 1
            continue

    return {
        "message": f"Recalculated cut times for {updated_count} items",
        "items_updated": updated_count,
        "items_skipped": skipped_count,
        "total_processed": len(result.data)
    }


@router.post("/{item_id}/generate-dxf")
async def generate_dxf(item_id: UUID):
    """
    Request DXF/SVG generation for an item.

    Sets needs_dxf=true and queues generation tasks if a STEP file exists.
    """
    supabase = get_supabase_admin()

    # Get item info
    item_result = supabase.table("items").select("id, item_number").eq("id", str(item_id)).single().execute()
    if not item_result.data:
        raise HTTPException(status_code=404, detail="Item not found")

    item = item_result.data
    item_number = item["item_number"]

    # Set needs_dxf flag
    supabase.table("items").update({"needs_dxf": True}).eq("id", str(item_id)).execute()

    # Find most recent STEP file
    step_result = supabase.table("files") \
        .select("id, file_path") \
        .eq("item_id", str(item_id)) \
        .eq("file_type", "STEP") \
        .order("created_at", desc=True) \
        .limit(1) \
        .execute()

    if not step_result.data:
        return {
            "message": f"needs_dxf set for {item_number}, but no STEP file found",
            "needs_dxf": True,
            "queued": False
        }

    step_file = step_result.data[0]

    # Check if DXF already exists
    dxf_exists = supabase.table("files") \
        .select("id") \
        .eq("item_id", str(item_id)) \
        .eq("file_type", "DXF") \
        .execute()

    if dxf_exists.data:
        return {
            "message": f"DXF already exists for {item_number}",
            "needs_dxf": True,
            "queued": False,
            "dxf_exists": True
        }

    # Queue DXF and SVG generation
    queued_tasks = []
    for task_type in ["GENERATE_DXF", "GENERATE_SVG"]:
        try:
            supabase.table("work_queue").insert({
                "item_id": str(item_id),
                "file_id": step_file["id"],
                "task_type": task_type,
                "payload": {"file_path": step_file["file_path"], "item_number": item_number},
                "status": "pending"
            }).execute()
            queued_tasks.append(task_type)
        except Exception as e:
            print(f"Warning: Failed to queue {task_type} for {item_number}: {e}")

    return {
        "message": f"Queued DXF/SVG generation for {item_number}",
        "needs_dxf": True,
        "queued": True,
        "tasks": queued_tasks
    }
