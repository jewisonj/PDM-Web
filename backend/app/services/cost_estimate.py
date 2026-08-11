"""Shared project cost estimate calculation.

Used by both the MRP API routes and the AI assistant tools so pricing
numbers always match, no matter where they're requested from.
"""

from typing import Any, Optional

from .supabase import get_supabase_admin


def compute_project_cost_estimate(project_id: str) -> Optional[dict[str, Any]]:
    """
    Compute a full cost estimate for an MRP project.

    Joins project parts, items, routing, workstations, routing_materials,
    and raw_materials to calculate labor, material, outsourced, and
    purchased costs.

    Kit pricing model:
    - Kits are global (vendor_kits/project_kits table)
    - kit_items tracks parts in each kit with quantities and unit prices
    - project_kit_usage links projects to kits with is_active flag
    - Active kit parts skip in-house costing; kit price is added separately
    - If kit has total price (project_kits.price), use that
    - Otherwise sum kit_items prices

    Returns None if the project has no parts (or doesn't exist).
    """
    supabase = get_supabase_admin()
    pid = str(project_id)

    # Load cost settings
    settings_result = supabase.table("cost_settings").select("setting_key, setting_value").execute()
    settings = {r["setting_key"]: float(r["setting_value"]) for r in (settings_result.data or [])}
    default_labor_rate = settings.get("default_labor_rate", 65.0)
    overhead_multiplier = settings.get("overhead_multiplier", 1.0)
    # Per-material $/lb defaults (used for both sheet metal and tube)
    default_price_per_lb = {
        "CS": settings.get("default_cs_price_per_lb", 0.85),
        "AL": settings.get("default_al_price_per_lb", 3.00),
        "SS": settings.get("default_ss_price_per_lb", 3.50),
    }

    # Load project parts
    parts_result = supabase.table("mrp_project_parts").select(
        "item_id, quantity, items(id, item_number, name, mass, is_supplier_part, unit_price)"
    ).eq("project_id", pid).execute()

    if not parts_result.data:
        return None

    # Filter out zzz-prefix items (reference-only parts, not for manufacturing)
    parts_data = [
        p for p in parts_result.data
        if not (p.get("items") or {}).get("item_number", "").lower().startswith("zzz")
    ]

    if not parts_data:
        return None

    # --- Kit Pricing Support ---
    # Load kit usage for this project (which kits are linked and active)
    kit_usage_result = supabase.table("project_kit_usage").select(
        "kit_id, is_active"
    ).eq("project_id", pid).execute()

    active_kit_ids = {ku["kit_id"] for ku in (kit_usage_result.data or []) if ku.get("is_active")}
    linked_kit_ids = {ku["kit_id"] for ku in (kit_usage_result.data or [])}

    # Load kit details for linked kits
    kits_map = {}
    if linked_kit_ids:
        kits_result = supabase.table("project_kits").select(
            "id, kit_number, kit_name, vendor, price"
        ).in_("id", list(linked_kit_ids)).execute()
        kits_map = {k["id"]: k for k in (kits_result.data or [])}

    # Load kit_items for active kits to know which parts are covered
    items_in_active_kits = set()
    kit_item_prices = {}  # kit_id -> {item_id: unit_price * qty}

    if active_kit_ids:
        kit_items_result = supabase.table("kit_items").select(
            "kit_id, item_id, quantity, unit_price"
        ).in_("kit_id", list(active_kit_ids)).execute()

        for ki in (kit_items_result.data or []):
            items_in_active_kits.add(ki["item_id"])
            # Track per-kit costs for kits without a bundle price
            kit_id = ki["kit_id"]
            if kit_id not in kit_item_prices:
                kit_item_prices[kit_id] = {}
            unit_price = ki.get("unit_price") or 0
            quantity = ki.get("quantity") or 1
            kit_item_prices[kit_id][ki["item_id"]] = float(unit_price) * quantity

    # Load all workstations
    ws_result = supabase.table("workstations").select("id, station_code, station_name, hourly_rate, is_outsourced, outsourced_cost_default").execute()
    ws_map = {w["id"]: w for w in (ws_result.data or [])}

    # Collect all item IDs
    item_ids = [p["item_id"] for p in parts_data]

    # Load routing for all items
    routing_result = supabase.table("routing").select(
        "item_id, station_id, est_time_min, cost_override, time_basis"
    ).in_("item_id", item_ids).execute()

    # Group routing by item_id
    routing_by_item: dict[str, list] = {}
    for r in (routing_result.data or []):
        routing_by_item.setdefault(r["item_id"], []).append(r)

    # Load routing materials for all items
    rm_result = supabase.table("routing_materials").select(
        "item_id, qty_required, raw_materials(material_type, material_code, weight_lb_per_ft, price_per_unit)"
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

    for part in parts_data:
        item = part.get("items") or {}
        item_id = part["item_id"]
        qty = part.get("quantity", 1) or 1
        is_supplier = item.get("is_supplier_part", False)

        # Check if this item is covered by an active kit
        in_active_kit = item_id in items_in_active_kits
        kit_info = None

        # Find which kit covers this item
        if in_active_kit:
            for kit_id in active_kit_ids:
                if kit_id in kit_item_prices and item_id in kit_item_prices[kit_id]:
                    kit = kits_map.get(kit_id)
                    if kit:
                        kit_info = {
                            "kit_id": kit["id"],
                            "kit_number": kit["kit_number"],
                            "kit_name": kit["kit_name"],
                        }
                        break

        # If item is covered by an active kit, skip individual costing
        if in_active_kit:
            items_output.append({
                "item_id": item_id,
                "item_number": item.get("item_number", ""),
                "name": item.get("name", ""),
                "quantity": qty,
                "is_supplier_part": False,
                "in_kit": True,
                "kit_info": kit_info,
                "labor_cost": 0,
                "material_cost": 0,
                "outsourced_cost": 0,
                "unit_cost": 0,
                "extended_cost": 0,
            })
            continue

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
                "in_kit": False,
                "labor_cost": 0,
                "material_cost": 0,
                "outsourced_cost": 0,
                "unit_cost": unit_price,
                "extended_cost": extended
            })
            continue

        # Calculate labor and outsourced costs from routing
        # Track fixed (per_line_item) vs variable (per_unit) costs separately
        item_labor_fixed = 0.0      # per_line_item: don't multiply by qty
        item_labor_variable = 0.0   # per_unit: multiply by qty
        item_outsourced_fixed = 0.0
        item_outsourced_variable = 0.0
        for step in routing_by_item.get(item_id, []):
            ws = ws_map.get(step["station_id"], {})
            time_basis = step.get("time_basis", "per_unit")
            if ws.get("is_outsourced"):
                cost = step.get("cost_override")
                if cost is None:
                    cost = ws.get("outsourced_cost_default") or 0
                if time_basis == "per_line_item":
                    item_outsourced_fixed += float(cost)
                else:
                    item_outsourced_variable += float(cost)
            else:
                override = step.get("cost_override")
                if override is not None:
                    op_cost = float(override)
                else:
                    rate = float(ws.get("hourly_rate") or default_labor_rate)
                    time_min = float(step.get("est_time_min") or 0)
                    op_cost = (time_min / 60) * rate
                if time_basis == "per_line_item":
                    item_labor_fixed += op_cost
                else:
                    item_labor_variable += op_cost

        # Calculate material cost
        item_material = 0.0
        item_mass = float(item.get("mass") or 0)
        for rm in rm_by_item.get(item_id, []):
            raw = rm.get("raw_materials") or {}
            mat_type = raw.get("material_type", "")
            mat_code = raw.get("material_code", "")
            price = raw.get("price_per_unit")
            mat_default_per_lb = default_price_per_lb.get(mat_code, 0.85)

            if mat_type == "SM":
                # Sheet metal: price_per_unit is $/lb, fallback to per-material default
                per_lb = float(price) if price is not None else mat_default_per_lb
                item_material += float(rm.get("qty_required") or 0) * per_lb
            else:
                # Tubing: price_per_unit is a direct $/ft override
                # Otherwise derive $/ft from per-material $/lb * weight_lb_per_ft
                wt_per_ft = float(raw.get("weight_lb_per_ft") or 0)
                if price is not None:
                    per_ft = float(price)
                else:
                    per_ft = mat_default_per_lb * wt_per_ft
                if item_mass > 0 and wt_per_ft > 0:
                    length_ft = (item_mass / wt_per_ft) + (2 / 12)
                    item_material += length_ft * per_ft
                else:
                    item_material += (float(rm.get("qty_required") or 0) / 12) * per_ft

        # Variable unit cost (per piece) - for quoting
        unit_cost = item_labor_variable + item_outsourced_variable + item_material
        # Extended = fixed costs (once) + variable costs (per qty)
        extended = (item_labor_fixed + item_outsourced_fixed +
                    (item_labor_variable + item_outsourced_variable + item_material) * qty)

        total_labor += item_labor_fixed + item_labor_variable * qty
        total_material += item_material * qty
        total_outsourced += item_outsourced_fixed + item_outsourced_variable * qty

        items_output.append({
            "item_id": item_id,
            "item_number": item.get("item_number", ""),
            "name": item.get("name", ""),
            "quantity": qty,
            "is_supplier_part": False,
            "in_kit": False,
            "labor_cost": round(item_labor_fixed + item_labor_variable * qty, 2),
            "material_cost": round(item_material * qty, 2),
            "outsourced_cost": round(item_outsourced_fixed + item_outsourced_variable * qty, 2),
            "unit_cost": round(unit_cost, 2),
            "extended_cost": round(extended, 2)
        })

    # Calculate total kit costs from active kits
    total_kit_cost = 0.0
    kits_output = []
    for kit_id in active_kit_ids:
        kit = kits_map.get(kit_id)
        if kit:
            # Use kit's bundle price if set, otherwise sum item prices
            kit_bundle_price = float(kit.get("price") or 0)
            kit_items_total = sum(kit_item_prices.get(kit_id, {}).values())

            # Prefer bundle price, fall back to items total
            if kit_bundle_price > 0:
                kit_price = kit_bundle_price
            else:
                kit_price = kit_items_total

            total_kit_cost += kit_price

            # Count parts in this kit
            parts_in_kit = len(kit_item_prices.get(kit_id, {}))

            kits_output.append({
                "kit_id": kit_id,
                "kit_number": kit["kit_number"],
                "kit_name": kit["kit_name"],
                "vendor": kit.get("vendor"),
                "price": round(kit_price, 2),
                "bundle_price": kit_bundle_price if kit_bundle_price > 0 else None,
                "items_total": round(kit_items_total, 2),
                "part_count": parts_in_kit,
            })

    subtotal = total_labor + total_material + total_outsourced + total_purchased + total_kit_cost
    total = subtotal * overhead_multiplier

    return {
        "project_id": pid,
        "labor_cost": round(total_labor, 2),
        "material_cost": round(total_material, 2),
        "outsourced_cost": round(total_outsourced, 2),
        "purchased_cost": round(total_purchased, 2),
        "kit_cost": round(total_kit_cost, 2),
        "overhead_multiplier": overhead_multiplier,
        "subtotal": round(subtotal, 2),
        "total": round(total, 2),
        "items": items_output,
        "kits": kits_output,
    }
