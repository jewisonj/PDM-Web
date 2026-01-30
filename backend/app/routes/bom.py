"""BOM (Bill of Materials) API routes."""

from fastapi import APIRouter, HTTPException
from uuid import UUID

from ..services.supabase import get_supabase_client, get_supabase_admin
from ..models.schemas import BOMEntry, BOMCreate, BOMTreeNode, Item, BOMBulkCreate, BOMBulkResponse

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


@router.post("/bulk", response_model=BOMBulkResponse)
async def bulk_upload_bom(bom: BOMBulkCreate):
    """
    Bulk upload BOM - replaces entire BOM for an assembly.

    This endpoint:
    1. Creates the parent assembly item if it doesn't exist
    2. Creates/updates all child items with their properties
    3. Deletes all existing BOM entries for the parent
    4. Creates new BOM relationships

    Used by the local PDM upload client when processing BOM text files from Creo.
    Uses admin client to bypass RLS for trusted internal operations.
    """
    supabase = get_supabase_admin()

    parent_number = bom.parent_item_number.lower()
    items_created = 0
    items_updated = 0

    # 1. Get or create parent item
    parent_result = supabase.table("items").select("id").eq("item_number", parent_number).execute()

    if parent_result.data:
        parent_id = parent_result.data[0]["id"]
    else:
        # Create parent item
        parent_data = {
            "item_number": parent_number,
            "name": parent_number.upper(),
            "revision": "A",
            "iteration": 1,
            "lifecycle_state": "Design",
        }
        create_result = supabase.table("items").insert(parent_data).execute()
        parent_id = create_result.data[0]["id"]
        items_created += 1

    # 2. Delete existing BOM entries for this parent
    supabase.table("bom").delete().eq("parent_item_id", parent_id).execute()

    # 3. Process each child item
    child_item_numbers = []
    bom_entries_created = 0

    for child in bom.children:
        child_number = child.item_number.lower()
        child_item_numbers.append(child_number)

        # Skip zzz (reference) items - don't create them
        if child_number.startswith("zzz"):
            continue

        # Check if child item exists
        child_result = supabase.table("items").select("id").eq("item_number", child_number).execute()

        # Prepare item properties
        item_props = {
            "name": child.name,
            "material": child.material,
            "mass": child.mass,
            "thickness": child.thickness,
            "cut_length": child.cut_length,
            "cut_time": child.cut_time,
            "price_est": child.price_est,
        }
        # Filter out None values
        item_props = {k: v for k, v in item_props.items() if v is not None}

        if child_result.data:
            # Update existing item
            child_id = child_result.data[0]["id"]
            if item_props:
                supabase.table("items").update(item_props).eq("id", child_id).execute()
                items_updated += 1
        else:
            # Create new item
            is_supplier = child_number.startswith("mmc") or child_number.startswith("spn")
            new_item = {
                "item_number": child_number,
                "name": child_number.upper(),
                "revision": "A",
                "iteration": 1,
                "lifecycle_state": "Design",
                "is_supplier_part": is_supplier,
                **item_props
            }
            create_result = supabase.table("items").insert(new_item).execute()
            child_id = create_result.data[0]["id"]
            items_created += 1

        # 4. Create BOM relationship
        bom_data = {
            "parent_item_id": parent_id,
            "child_item_id": child_id,
            "quantity": child.quantity,
            "source_file": bom.source_file,
        }
        supabase.table("bom").insert(bom_data).execute()
        bom_entries_created += 1

    return BOMBulkResponse(
        parent_item_number=parent_number,
        parent_item_id=parent_id,
        items_created=items_created,
        items_updated=items_updated,
        bom_entries_created=bom_entries_created,
        children=child_item_numbers
    )


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
