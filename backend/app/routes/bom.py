"""BOM (Bill of Materials) API routes."""

from fastapi import APIRouter, HTTPException
from uuid import UUID

from ..services.supabase import get_supabase_client
from ..models.schemas import BOMEntry, BOMCreate, BOMTreeNode, Item

router = APIRouter(prefix="/bom", tags=["bom"])


@router.get("/{item_number}", response_model=list[BOMEntry])
async def get_bom(item_number: str):
    """Get single-level BOM for an item (direct children only)."""
    supabase = get_supabase_client()

    # Get parent item ID
    item_result = supabase.table("items").select("id").eq("item_number", item_number.lower()).single().execute()

    if not item_result.data:
        raise HTTPException(status_code=404, detail=f"Item {item_number} not found")

    # Get BOM entries
    bom_result = supabase.table("bom").select("*").eq("parent_item_id", item_result.data["id"]).execute()

    return bom_result.data


@router.get("/{item_number}/tree")
async def get_bom_tree(item_number: str, max_depth: int = 10):
    """Get full BOM tree (recursive) for an item."""
    supabase = get_supabase_client()

    # Get parent item
    item_result = supabase.table("items").select("*").eq("item_number", item_number.lower()).single().execute()

    if not item_result.data:
        raise HTTPException(status_code=404, detail=f"Item {item_number} not found")

    def build_tree(item_id: str, depth: int = 0) -> list[dict]:
        """Recursively build BOM tree."""
        if depth >= max_depth:
            return []

        # Get children
        bom_result = supabase.table("bom").select("child_item_id, quantity").eq("parent_item_id", item_id).execute()

        children = []
        for entry in bom_result.data:
            # Get child item details
            child_result = supabase.table("items").select("*").eq("id", entry["child_item_id"]).single().execute()

            if child_result.data:
                child_node = {
                    "item": child_result.data,
                    "quantity": entry["quantity"],
                    "children": build_tree(entry["child_item_id"], depth + 1)
                }
                children.append(child_node)

        return children

    return {
        "item": item_result.data,
        "quantity": 1,
        "children": build_tree(item_result.data["id"])
    }


@router.get("/{item_number}/where-used")
async def get_where_used(item_number: str):
    """Get list of assemblies that contain this item."""
    supabase = get_supabase_client()

    # Get item ID
    item_result = supabase.table("items").select("id").eq("item_number", item_number.lower()).single().execute()

    if not item_result.data:
        raise HTTPException(status_code=404, detail=f"Item {item_number} not found")

    # Get parent items
    bom_result = supabase.table("bom").select("parent_item_id, quantity").eq("child_item_id", item_result.data["id"]).execute()

    parents = []
    for entry in bom_result.data:
        parent_result = supabase.table("items").select("*").eq("id", entry["parent_item_id"]).single().execute()
        if parent_result.data:
            parents.append({
                "item": parent_result.data,
                "quantity": entry["quantity"]
            })

    return parents


@router.post("", response_model=BOMEntry)
async def add_bom_entry(bom: BOMCreate):
    """Add a BOM relationship."""
    supabase = get_supabase_client()

    # Validate parent and child exist
    parent = supabase.table("items").select("id").eq("id", str(bom.parent_item_id)).single().execute()
    child = supabase.table("items").select("id").eq("id", str(bom.child_item_id)).single().execute()

    if not parent.data:
        raise HTTPException(status_code=404, detail="Parent item not found")
    if not child.data:
        raise HTTPException(status_code=404, detail="Child item not found")

    # Prevent self-reference
    if str(bom.parent_item_id) == str(bom.child_item_id):
        raise HTTPException(status_code=400, detail="Item cannot be its own child")

    bom_data = {
        "parent_item_id": str(bom.parent_item_id),
        "child_item_id": str(bom.child_item_id),
        "quantity": bom.quantity,
        "source_file": bom.source_file,
    }

    try:
        result = supabase.table("bom").insert(bom_data).execute()
        return result.data[0]
    except Exception as e:
        if "duplicate key" in str(e).lower():
            raise HTTPException(status_code=409, detail="BOM relationship already exists")
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{bom_id}")
async def update_bom_entry(bom_id: UUID, quantity: int):
    """Update BOM quantity."""
    supabase = get_supabase_client()

    result = supabase.table("bom").update({"quantity": quantity}).eq("id", str(bom_id)).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="BOM entry not found")

    return result.data[0]


@router.delete("/{bom_id}")
async def delete_bom_entry(bom_id: UUID):
    """Delete a BOM relationship."""
    supabase = get_supabase_client()

    result = supabase.table("bom").delete().eq("id", str(bom_id)).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="BOM entry not found")

    return {"message": "BOM entry deleted"}
