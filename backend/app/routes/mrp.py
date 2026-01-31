"""MRP (Manufacturing Resource Planning) API routes."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from uuid import UUID

from ..services.print_packet import generate_print_packet, get_existing_packet
from ..services.supabase import get_supabase_admin

router = APIRouter(prefix="/mrp", tags=["mrp"])


# --- Cost Settings ---

class CostSettingUpdate(BaseModel):
    setting_value: float


@router.get("/cost-settings")
async def get_cost_settings():
    """Return all cost settings as a key-value object."""
    supabase = get_supabase_admin()
    result = supabase.table("cost_settings").select("*").execute()
    return {row["setting_key"]: row for row in (result.data or [])}


@router.put("/cost-settings/{key}")
async def update_cost_setting(key: str, body: CostSettingUpdate):
    """Update a single cost setting value."""
    supabase = get_supabase_admin()
    result = supabase.table("cost_settings").update({
        "setting_value": body.setting_value
    }).eq("setting_key", key).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
    return result.data[0]


# --- Project Cost Estimate ---

@router.get("/projects/{project_id}/cost-estimate")
async def get_project_cost_estimate(project_id: UUID):
    """
    Compute and return a full cost estimate for an MRP project.

    Joins project parts, items, routing, workstations, routing_materials,
    and raw_materials to calculate labor, material, outsourced, and
    purchased costs.
    """
    supabase = get_supabase_admin()
    pid = str(project_id)

    # Load cost settings
    settings_result = supabase.table("cost_settings").select("setting_key, setting_value").execute()
    settings = {r["setting_key"]: float(r["setting_value"]) for r in (settings_result.data or [])}
    default_labor_rate = settings.get("default_labor_rate", 65.0)
    default_sm_price = settings.get("default_sm_price_per_lb", 3.50)
    default_tube_price = settings.get("default_tube_price_per_ft", 8.0)
    overhead_multiplier = settings.get("overhead_multiplier", 1.0)

    # Load project parts
    parts_result = supabase.table("mrp_project_parts").select(
        "item_id, quantity, items(id, item_number, name, mass, is_supplier_part, unit_price)"
    ).eq("project_id", pid).execute()

    if not parts_result.data:
        raise HTTPException(status_code=404, detail="Project not found or has no parts")

    # Load all workstations
    ws_result = supabase.table("workstations").select("id, station_code, station_name, hourly_rate, is_outsourced, outsourced_cost_default").execute()
    ws_map = {w["id"]: w for w in (ws_result.data or [])}

    # Collect all item IDs
    item_ids = [p["item_id"] for p in parts_result.data]

    # Load routing for all items
    routing_result = supabase.table("routing").select(
        "item_id, station_id, est_time_min, cost_override"
    ).in_("item_id", item_ids).execute()

    # Group routing by item_id
    routing_by_item: dict[str, list] = {}
    for r in (routing_result.data or []):
        routing_by_item.setdefault(r["item_id"], []).append(r)

    # Load routing materials for all items
    rm_result = supabase.table("routing_materials").select(
        "item_id, qty_required, raw_materials(material_type, weight_lb_per_ft, price_per_unit)"
    ).in_("item_id", item_ids).execute()

    # Group routing materials by item_id
    rm_by_item: dict[str, list] = {}
    for rm in (rm_result.data or []):
        rm_by_item.setdefault(rm["item_id"], []).append(rm)

    # Calculate costs per item
    items_output = []
    total_labor = 0.0
    total_material = 0.0
    total_outsourced = 0.0
    total_purchased = 0.0

    for part in parts_result.data:
        item = part.get("items") or {}
        item_id = part["item_id"]
        qty = part.get("quantity", 1) or 1
        is_supplier = item.get("is_supplier_part", False)

        if is_supplier:
            unit_price = float(item.get("unit_price") or 0)
            extended = unit_price * qty
            total_purchased += extended
            items_output.append({
                "item_id": item_id,
                "item_number": item.get("item_number", ""),
                "name": item.get("name", ""),
                "quantity": qty,
                "is_supplier_part": True,
                "labor_cost": 0,
                "material_cost": 0,
                "outsourced_cost": 0,
                "unit_cost": unit_price,
                "extended_cost": extended
            })
            continue

        # Calculate labor and outsourced costs from routing
        item_labor = 0.0
        item_outsourced = 0.0
        for step in routing_by_item.get(item_id, []):
            ws = ws_map.get(step["station_id"], {})
            if ws.get("is_outsourced"):
                cost = step.get("cost_override")
                if cost is None:
                    cost = ws.get("outsourced_cost_default") or 0
                item_outsourced += float(cost)
            else:
                override = step.get("cost_override")
                if override is not None:
                    item_labor += float(override)
                else:
                    rate = float(ws.get("hourly_rate") or default_labor_rate)
                    time_min = float(step.get("est_time_min") or 0)
                    item_labor += (time_min / 60) * rate

        # Calculate material cost
        item_material = 0.0
        item_mass = float(item.get("mass") or 0)
        for rm in rm_by_item.get(item_id, []):
            raw = rm.get("raw_materials") or {}
            mat_type = raw.get("material_type", "")
            price = raw.get("price_per_unit")

            if mat_type == "SM":
                per_lb = float(price) if price is not None else default_sm_price
                item_material += float(rm.get("qty_required") or 0) * per_lb
            else:
                per_ft = float(price) if price is not None else default_tube_price
                wt_per_ft = float(raw.get("weight_lb_per_ft") or 0)
                if item_mass > 0 and wt_per_ft > 0:
                    length_ft = (item_mass / wt_per_ft) + (2 / 12)
                    item_material += length_ft * per_ft
                else:
                    item_material += (float(rm.get("qty_required") or 0) / 12) * per_ft

        unit_cost = item_labor + item_outsourced + item_material
        extended = unit_cost * qty

        total_labor += item_labor * qty
        total_material += item_material * qty
        total_outsourced += item_outsourced * qty

        items_output.append({
            "item_id": item_id,
            "item_number": item.get("item_number", ""),
            "name": item.get("name", ""),
            "quantity": qty,
            "is_supplier_part": False,
            "labor_cost": round(item_labor, 2),
            "material_cost": round(item_material, 2),
            "outsourced_cost": round(item_outsourced, 2),
            "unit_cost": round(unit_cost, 2),
            "extended_cost": round(extended, 2)
        })

    subtotal = total_labor + total_material + total_outsourced + total_purchased
    total = subtotal * overhead_multiplier

    return {
        "project_id": pid,
        "labor_cost": round(total_labor, 2),
        "material_cost": round(total_material, 2),
        "outsourced_cost": round(total_outsourced, 2),
        "purchased_cost": round(total_purchased, 2),
        "overhead_multiplier": overhead_multiplier,
        "subtotal": round(subtotal, 2),
        "total": round(total, 2),
        "items": items_output
    }


@router.post("/projects/{project_id}/print-packet")
async def create_print_packet(project_id: UUID):
    """
    Generate a new print packet for an MRP project.

    This creates a combined PDF with:
    - Cover sheet with project info and categorized parts lists
    - Each part's PDF with stamp overlays showing routing info

    Returns the download URL, storage path, and generation timestamp.
    """
    try:
        result = await generate_print_packet(str(project_id))
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate print packet: {str(e)}")


@router.get("/projects/{project_id}/print-packet")
async def get_print_packet(project_id: UUID):
    """
    Get the existing print packet for an MRP project.

    Returns the download URL if a packet exists, or 404 if not.
    """
    result = await get_existing_packet(str(project_id))

    if not result:
        raise HTTPException(status_code=404, detail="No print packet found for this project")

    return result
