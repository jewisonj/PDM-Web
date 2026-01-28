"""Items API routes."""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from uuid import UUID

from ..services.supabase import get_supabase_client
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
    supabase = get_supabase_client()

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
    supabase = get_supabase_client()

    # Get item with project name
    result = supabase.table("items").select("*, projects(name)").eq("item_number", item_number.lower()).single().execute()

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
    supabase = get_supabase_client()

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
async def update_item(item_number: str, item: ItemUpdate):
    """Update an existing item."""
    supabase = get_supabase_client()

    # Filter out None values
    update_data = {k: v for k, v in item.model_dump().items() if v is not None}

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Convert UUID to string if present
    if update_data.get("project_id"):
        update_data["project_id"] = str(update_data["project_id"])

    result = supabase.table("items").update(update_data).eq("item_number", item_number.lower()).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail=f"Item {item_number} not found")

    return result.data[0]


@router.delete("/{item_number}")
async def delete_item(item_number: str):
    """Delete an item."""
    supabase = get_supabase_client()

    result = supabase.table("items").delete().eq("item_number", item_number.lower()).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail=f"Item {item_number} not found")

    return {"message": f"Item {item_number} deleted"}


@router.get("/{item_number}/history")
async def get_item_history(item_number: str):
    """Get lifecycle history for an item."""
    supabase = get_supabase_client()

    # Get item ID first
    item_result = supabase.table("items").select("id").eq("item_number", item_number.lower()).single().execute()

    if not item_result.data:
        raise HTTPException(status_code=404, detail=f"Item {item_number} not found")

    # Get history
    history = supabase.table("lifecycle_history").select("*").eq("item_id", item_result.data["id"]).order("changed_at", desc=True).execute()

    return history.data
