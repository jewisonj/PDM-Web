"""Project Kits API routes for bundle/kit pricing."""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from uuid import UUID
from typing import Optional
from decimal import Decimal

logger = logging.getLogger(__name__)

from ..services.supabase import get_supabase_admin

router = APIRouter(prefix="/mrp/projects", tags=["kits"])


# --- Pydantic Models ---

class KitCreate(BaseModel):
    kit_number: str
    kit_name: str
    vendor: Optional[str] = None
    price: float = 0.0
    use_kit: bool = True
    notes: Optional[str] = None


class KitUpdate(BaseModel):
    kit_number: Optional[str] = None
    kit_name: Optional[str] = None
    vendor: Optional[str] = None
    price: Optional[float] = None
    use_kit: Optional[bool] = None
    notes: Optional[str] = None


class ItemSourceUpdate(BaseModel):
    source_type: str  # 'make' | 'kit'
    kit_id: Optional[str] = None


# --- Kit CRUD ---

@router.get("/{project_id}/kits")
async def list_project_kits(project_id: UUID):
    """
    List all kits for a project with part counts and comparison data.

    Returns each kit with:
    - Kit details (name, vendor, price, use_kit toggle)
    - Count of parts assigned to the kit
    - Sum of in-house costs for comparison
    """
    supabase = get_supabase_admin()
    pid = str(project_id)

    # Get all kits for this project
    kits_result = supabase.table("project_kits").select("*").eq("project_id", pid).order("kit_number").execute()
    kits = kits_result.data or []

    if not kits:
        return []

    # Get all item sources for this project that reference these kits
    kit_ids = [k["id"] for k in kits]
    sources_result = supabase.table("project_item_source").select(
        "kit_id, item_id"
    ).eq("project_id", pid).eq("source_type", "kit").in_("kit_id", kit_ids).execute()

    # Count parts per kit
    kit_part_counts = {}
    kit_item_ids = {}  # kit_id -> list of item_ids
    for src in (sources_result.data or []):
        kid = src["kit_id"]
        kit_part_counts[kid] = kit_part_counts.get(kid, 0) + 1
        kit_item_ids.setdefault(kid, []).append(src["item_id"])

    # Calculate in-house cost comparison for each kit
    # We need to sum the routing costs for all items in each kit
    kit_inhouse_costs = {}

    for kit_id, item_ids in kit_item_ids.items():
        if not item_ids:
            kit_inhouse_costs[kit_id] = 0.0
            continue

        # Get project parts to find quantities
        parts_result = supabase.table("mrp_project_parts").select(
            "item_id, quantity"
        ).eq("project_id", pid).in_("item_id", item_ids).execute()

        item_qtys = {p["item_id"]: p.get("quantity", 1) or 1 for p in (parts_result.data or [])}

        # Get routing for these items
        routing_result = supabase.table("routing").select(
            "item_id, est_time_min, cost_override, station_id"
        ).in_("item_id", item_ids).execute()

        # Get workstation rates
        ws_result = supabase.table("workstations").select(
            "id, hourly_rate, is_outsourced, outsourced_cost_default"
        ).execute()
        ws_map = {w["id"]: w for w in (ws_result.data or [])}

        # Get cost settings for default rate
        settings_result = supabase.table("cost_settings").select(
            "setting_key, setting_value"
        ).execute()
        settings = {r["setting_key"]: float(r["setting_value"]) for r in (settings_result.data or [])}
        default_labor_rate = settings.get("default_labor_rate", 65.0)

        # Get items for mass lookup
        items_result = supabase.table("items").select(
            "id, mass"
        ).in_("id", item_ids).execute()
        item_mass = {i["id"]: float(i.get("mass") or 0) for i in (items_result.data or [])}

        # Get routing materials for these items
        rm_result = supabase.table("routing_materials").select(
            "item_id, qty_required, raw_materials(material_type, material_code, weight_lb_per_ft, price_per_unit)"
        ).in_("item_id", item_ids).execute()

        # Per-material $/lb defaults
        default_price_per_lb = {
            "CS": settings.get("default_cs_price_per_lb", 0.85),
            "AL": settings.get("default_al_price_per_lb", 3.00),
            "SS": settings.get("default_ss_price_per_lb", 3.50),
        }

        # Calculate total in-house cost (labor + materials)
        total_labor = 0.0
        for r in (routing_result.data or []):
            ws = ws_map.get(r["station_id"], {})
            qty = item_qtys.get(r["item_id"], 1)

            if ws.get("is_outsourced"):
                cost = r.get("cost_override")
                if cost is None:
                    cost = ws.get("outsourced_cost_default") or 0
                total_labor += float(cost) * qty
            else:
                override = r.get("cost_override")
                if override is not None:
                    total_labor += float(override) * qty
                else:
                    rate = float(ws.get("hourly_rate") or default_labor_rate)
                    time_min = float(r.get("est_time_min") or 0)
                    total_labor += (time_min / 60) * rate * qty

        # Calculate material costs
        total_material = 0.0
        for rm in (rm_result.data or []):
            raw = rm.get("raw_materials") or {}
            mat_type = raw.get("material_type", "")
            mat_code = raw.get("material_code", "")
            price = raw.get("price_per_unit")
            mat_default_per_lb = default_price_per_lb.get(mat_code, 0.85)
            qty = item_qtys.get(rm["item_id"], 1)

            if mat_type == "SM":
                # Sheet metal: price_per_unit is $/lb
                per_lb = float(price) if price is not None else mat_default_per_lb
                total_material += float(rm.get("qty_required") or 0) * per_lb * qty
            else:
                # Tubing: derive cost from item mass and weight_lb_per_ft
                wt_per_ft = float(raw.get("weight_lb_per_ft") or 0)
                mass = item_mass.get(rm["item_id"], 0)
                if price is not None:
                    per_ft = float(price)
                else:
                    per_ft = mat_default_per_lb * wt_per_ft
                if mass > 0 and wt_per_ft > 0:
                    length_ft = (mass / wt_per_ft) + (2 / 12)  # Add 2" waste
                    total_material += length_ft * per_ft * qty
                else:
                    total_material += (float(rm.get("qty_required") or 0) / 12) * per_ft * qty

        kit_inhouse_costs[kit_id] = {
            "total": total_labor + total_material,
            "labor": total_labor,
            "material": total_material,
        }

    # Build response with enriched data
    result = []
    for kit in kits:
        kid = kit["id"]
        part_count = kit_part_counts.get(kid, 0)
        cost_data = kit_inhouse_costs.get(kid, {"total": 0.0})
        inhouse_cost = cost_data["total"] if isinstance(cost_data, dict) else cost_data
        kit_price = float(kit.get("price") or 0)
        savings = inhouse_cost - kit_price
        savings_pct = (savings / inhouse_cost * 100) if inhouse_cost > 0 else 0

        result.append({
            **kit,
            "part_count": part_count,
            "inhouse_cost": round(inhouse_cost, 2),
            "inhouse_labor": round(cost_data.get("labor", 0) if isinstance(cost_data, dict) else 0, 2),
            "inhouse_material": round(cost_data.get("material", 0) if isinstance(cost_data, dict) else 0, 2),
            "savings": round(savings, 2),
            "savings_percent": round(savings_pct, 1),
        })

    return result


@router.post("/{project_id}/kits")
async def create_kit(project_id: UUID, body: KitCreate):
    """Create a new kit for a project."""
    supabase = get_supabase_admin()

    data = {
        "project_id": str(project_id),
        "kit_number": body.kit_number,
        "kit_name": body.kit_name,
        "vendor": body.vendor,
        "price": body.price,
        "use_kit": body.use_kit,
        "notes": body.notes,
    }

    result = supabase.table("project_kits").insert(data).execute()

    if not result.data:
        raise HTTPException(status_code=400, detail="Failed to create kit")

    return result.data[0]


@router.get("/{project_id}/kits/{kit_id}")
async def get_kit(project_id: UUID, kit_id: UUID):
    """Get a single kit with its assigned parts."""
    supabase = get_supabase_admin()
    pid = str(project_id)
    kid = str(kit_id)

    # Get kit
    kit_result = supabase.table("project_kits").select("*").eq("id", kid).eq("project_id", pid).execute()

    if not kit_result.data:
        raise HTTPException(status_code=404, detail="Kit not found")

    kit = kit_result.data[0]

    # Get parts assigned to this kit
    sources_result = supabase.table("project_item_source").select(
        "item_id, items(item_number, name)"
    ).eq("kit_id", kid).eq("source_type", "kit").execute()

    parts = []
    for src in (sources_result.data or []):
        item = src.get("items") or {}
        parts.append({
            "item_id": src["item_id"],
            "item_number": item.get("item_number", ""),
            "name": item.get("name", ""),
        })

    return {
        **kit,
        "parts": parts,
    }


@router.patch("/{project_id}/kits/{kit_id}")
async def update_kit(project_id: UUID, kit_id: UUID, body: KitUpdate):
    """Update a kit's details."""
    supabase = get_supabase_admin()
    pid = str(project_id)
    kid = str(kit_id)

    # Build update data (only include non-None fields)
    data = {}
    if body.kit_number is not None:
        data["kit_number"] = body.kit_number
    if body.kit_name is not None:
        data["kit_name"] = body.kit_name
    if body.vendor is not None:
        data["vendor"] = body.vendor
    if body.price is not None:
        data["price"] = body.price
    if body.use_kit is not None:
        data["use_kit"] = body.use_kit
    if body.notes is not None:
        data["notes"] = body.notes

    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = supabase.table("project_kits").update(data).eq("id", kid).eq("project_id", pid).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Kit not found")

    return result.data[0]


@router.delete("/{project_id}/kits/{kit_id}")
async def delete_kit(project_id: UUID, kit_id: UUID):
    """
    Delete a kit.

    Parts assigned to this kit will have their kit_id set to NULL
    (handled by ON DELETE SET NULL constraint).
    """
    supabase = get_supabase_admin()
    pid = str(project_id)
    kid = str(kit_id)

    # First, update any item sources that reference this kit to 'make'
    supabase.table("project_item_source").update({
        "source_type": "make",
        "kit_id": None
    }).eq("kit_id", kid).execute()

    # Then delete the kit
    result = supabase.table("project_kits").delete().eq("id", kid).eq("project_id", pid).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Kit not found")

    return {"deleted": True, "id": kid}


# --- Item Source Management ---

@router.get("/{project_id}/item-sources")
async def list_item_sources(project_id: UUID):
    """
    Get the sourcing method for all items in a project.

    Returns a map of item_id -> source info.
    Items not in the table default to 'make'.
    """
    supabase = get_supabase_admin()
    pid = str(project_id)

    result = supabase.table("project_item_source").select(
        "item_id, source_type, kit_id, project_kits(kit_number, kit_name)"
    ).eq("project_id", pid).execute()

    # Build a map for easy lookup
    sources = {}
    for src in (result.data or []):
        kit = src.get("project_kits") or {}
        sources[src["item_id"]] = {
            "source_type": src["source_type"],
            "kit_id": src["kit_id"],
            "kit_number": kit.get("kit_number"),
            "kit_name": kit.get("kit_name"),
        }

    return sources


@router.put("/{project_id}/items/{item_id}/source")
async def set_item_source(project_id: UUID, item_id: UUID, body: ItemSourceUpdate):
    """
    Set the sourcing method for an item in a project.

    - source_type='make': Item uses in-house routing (default)
    - source_type='kit': Item is part of a vendor kit (requires kit_id)
    """
    supabase = get_supabase_admin()
    pid = str(project_id)
    iid = str(item_id)

    # Validate source_type
    if body.source_type not in ('make', 'kit'):
        raise HTTPException(status_code=400, detail="source_type must be 'make' or 'kit'")

    # If kit, validate kit_id
    if body.source_type == 'kit':
        if not body.kit_id:
            raise HTTPException(status_code=400, detail="kit_id required when source_type is 'kit'")

        # Verify kit exists and belongs to this project
        kit_result = supabase.table("project_kits").select("id").eq("id", body.kit_id).eq("project_id", pid).execute()
        if not kit_result.data:
            raise HTTPException(status_code=404, detail="Kit not found in this project")

    data = {
        "project_id": pid,
        "item_id": iid,
        "source_type": body.source_type,
        "kit_id": body.kit_id if body.source_type == 'kit' else None,
    }

    # Upsert (insert or update on conflict)
    result = supabase.table("project_item_source").upsert(
        data,
        on_conflict="project_id,item_id"
    ).execute()

    if not result.data:
        raise HTTPException(status_code=400, detail="Failed to update item source")

    return result.data[0]


@router.delete("/{project_id}/items/{item_id}/source")
async def remove_item_source(project_id: UUID, item_id: UUID):
    """
    Remove the source override for an item (revert to default 'make').
    """
    supabase = get_supabase_admin()
    pid = str(project_id)
    iid = str(item_id)

    supabase.table("project_item_source").delete().eq("project_id", pid).eq("item_id", iid).execute()

    return {"deleted": True, "item_id": iid}


# --- Kit Parts Bulk Operations ---

@router.post("/{project_id}/kits/{kit_id}/parts")
async def add_parts_to_kit(project_id: UUID, kit_id: UUID, item_ids: list[str]):
    """
    Add multiple parts to a kit at once.
    """
    supabase = get_supabase_admin()
    pid = str(project_id)
    kid = str(kit_id)

    # Verify kit exists
    kit_result = supabase.table("project_kits").select("id").eq("id", kid).eq("project_id", pid).execute()
    if not kit_result.data:
        raise HTTPException(status_code=404, detail="Kit not found")

    # Upsert all item sources
    data = [
        {
            "project_id": pid,
            "item_id": iid,
            "source_type": "kit",
            "kit_id": kid,
        }
        for iid in item_ids
    ]

    if data:
        supabase.table("project_item_source").upsert(
            data,
            on_conflict="project_id,item_id"
        ).execute()

    return {"added": len(item_ids), "kit_id": kid}


@router.delete("/{project_id}/kits/{kit_id}/parts")
async def remove_parts_from_kit(project_id: UUID, kit_id: UUID, item_ids: list[str]):
    """
    Remove multiple parts from a kit (reverts them to 'make').
    """
    supabase = get_supabase_admin()
    pid = str(project_id)
    kid = str(kit_id)

    # Update all matching item sources to 'make'
    for iid in item_ids:
        supabase.table("project_item_source").update({
            "source_type": "make",
            "kit_id": None
        }).eq("project_id", pid).eq("item_id", iid).eq("kit_id", kid).execute()

    return {"removed": len(item_ids), "kit_id": kid}


# --- Kit Warning Check ---

@router.get("/{project_id}/kits/{kit_id}/warnings")
async def get_kit_warnings(project_id: UUID, kit_id: UUID):
    """
    Check for warnings related to a kit.

    Returns warnings if:
    - use_kit is OFF but parts are still assigned to this kit
    """
    supabase = get_supabase_admin()
    pid = str(project_id)
    kid = str(kit_id)

    # Get kit
    kit_result = supabase.table("project_kits").select("use_kit, kit_name").eq("id", kid).eq("project_id", pid).execute()

    if not kit_result.data:
        raise HTTPException(status_code=404, detail="Kit not found")

    kit = kit_result.data[0]
    warnings = []

    # If use_kit is OFF, check for assigned parts
    if not kit.get("use_kit", True):
        sources_result = supabase.table("project_item_source").select(
            "item_id, items(item_number, name)"
        ).eq("kit_id", kid).eq("source_type", "kit").execute()

        if sources_result.data:
            parts = [
                {
                    "item_id": s["item_id"],
                    "item_number": s.get("items", {}).get("item_number", ""),
                    "name": s.get("items", {}).get("name", ""),
                }
                for s in sources_result.data
            ]
            warnings.append({
                "type": "kit_disabled_with_parts",
                "message": f"Kit '{kit['kit_name']}' is disabled but {len(parts)} parts are still assigned. These parts will use in-house routing.",
                "parts": parts,
            })

    return {"warnings": warnings}
