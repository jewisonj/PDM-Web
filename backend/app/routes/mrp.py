"""MRP (Manufacturing Resource Planning) API routes."""

import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from uuid import UUID
import io
import zipfile

logger = logging.getLogger(__name__)

from ..services.print_packet import generate_print_packet, get_existing_packet
from ..services.supabase import get_supabase_admin
from ..services.cost_estimate import compute_project_cost_estimate

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
    estimate = compute_project_cost_estimate(str(project_id))

    if estimate is None:
        raise HTTPException(status_code=404, detail="Project not found or has no parts")

    return estimate


# --- Project Cost Report ---

@router.get("/projects/{project_id}/cost-report")
async def get_project_cost_report(project_id: UUID, group_by: str = None):
    """
    Full cost report for an MRP project with per-operation breakdowns.

    Returns manufactured items with operation details, purchased parts with
    supplier info, operations summary across the project, and pre-computed
    chart data for a pie chart visualization.

    Query params:
        group_by: If "station_group", aggregates operations by station group
    """
    supabase = get_supabase_admin()
    pid = str(project_id)

    # Load project info
    project_result = supabase.table("mrp_projects").select(
        "project_code, customer, description"
    ).eq("id", pid).execute()
    project_info = project_result.data[0] if project_result.data else {}

    # Load cost settings
    settings_result = supabase.table("cost_settings").select("setting_key, setting_value").execute()
    settings = {r["setting_key"]: float(r["setting_value"]) for r in (settings_result.data or [])}
    default_labor_rate = settings.get("default_labor_rate", 65.0)
    overhead_multiplier = settings.get("overhead_multiplier", 1.0)
    default_price_per_lb = {
        "CS": settings.get("default_cs_price_per_lb", 0.85),
        "AL": settings.get("default_al_price_per_lb", 3.00),
        "SS": settings.get("default_ss_price_per_lb", 3.50),
    }

    # Load project parts with extended item fields
    parts_result = supabase.table("mrp_project_parts").select(
        "item_id, quantity, items(id, item_number, name, mass, is_supplier_part, unit_price, supplier_name, supplier_pn)"
    ).eq("project_id", pid).execute()

    if not parts_result.data:
        raise HTTPException(status_code=404, detail="Project not found or has no parts")

    # Filter out zzz-prefix items (reference-only parts, not for manufacturing)
    parts_data = [
        p for p in parts_result.data
        if not (p.get("items") or {}).get("item_number", "").lower().startswith("zzz")
    ]

    if not parts_data:
        raise HTTPException(status_code=404, detail="Project has no manufacturable parts")

    # Load all workstations (including station_group for grouping)
    ws_result = supabase.table("workstations").select(
        "id, station_code, station_name, hourly_rate, is_outsourced, outsourced_cost_default, station_group"
    ).execute()
    ws_map = {w["id"]: w for w in (ws_result.data or [])}

    # Collect all item IDs
    item_ids = [p["item_id"] for p in parts_data]

    # Load routing for all items
    routing_result = supabase.table("routing").select(
        "item_id, station_id, sequence, est_time_min, cost_override, time_basis"
    ).in_("item_id", item_ids).order("sequence").execute()

    routing_by_item: dict[str, list] = {}
    for r in (routing_result.data or []):
        routing_by_item.setdefault(r["item_id"], []).append(r)

    # Load routing materials for all items
    rm_result = supabase.table("routing_materials").select(
        "item_id, qty_required, raw_materials(material_type, material_code, weight_lb_per_ft, price_per_unit)"
    ).in_("item_id", item_ids).execute()

    rm_by_item: dict[str, list] = {}
    for rm in (rm_result.data or []):
        rm_by_item.setdefault(rm["item_id"], []).append(rm)

    # Load kit sourcing - parts that come pre-made from vendor
    kit_source_result = supabase.table("project_item_source").select(
        "item_id, kit_id"
    ).eq("project_id", pid).eq("source_type", "kit").execute()
    kit_sourced_ids = {ks["item_id"] for ks in (kit_source_result.data or [])}

    # Load project kits with prices (only active kits where use_kit=true)
    kits_result = supabase.table("project_kits").select(
        "id, kit_number, kit_name, vendor, price, use_kit"
    ).eq("project_id", pid).eq("use_kit", True).execute()
    kits_data = kits_result.data or []
    total_kit_cost = sum(float(k.get("price") or 0) for k in kits_data)

    # --- Computation loop ---
    manufactured_items = []
    purchased_items = []
    ops_accumulator: dict[str, dict] = {}  # station_id -> aggregated data
    total_labor = 0.0
    total_material = 0.0
    total_outsourced = 0.0
    total_purchased = 0.0

    for part in parts_data:
        item = part.get("items") or {}
        item_id = part["item_id"]
        qty = part.get("quantity", 1) or 1
        is_supplier = item.get("is_supplier_part", False)

        if is_supplier:
            unit_price = float(item.get("unit_price") or 0)
            extended = unit_price * qty
            total_purchased += extended
            purchased_items.append({
                "item_id": item_id,
                "item_number": item.get("item_number", ""),
                "name": item.get("name", ""),
                "quantity": qty,
                "unit_price": round(unit_price, 2),
                "extended_cost": round(extended, 2),
                "supplier_name": item.get("supplier_name") or "",
                "supplier_pn": item.get("supplier_pn") or "",
            })
            continue

        # Kit-sourced parts: $0 labor/material (kit price covers it)
        # The kit price is tracked separately in project_kits table
        is_kit_sourced = item_id in kit_sourced_ids
        if is_kit_sourced:
            manufactured_items.append({
                "item_id": item_id,
                "item_number": item.get("item_number", ""),
                "name": item.get("name", ""),
                "quantity": qty,
                "material_cost": 0.0,
                "labor_cost": 0.0,
                "outsourced_cost": 0.0,
                "unit_cost": 0.0,
                "extended_cost": 0.0,
                "is_kit_sourced": True,
                "operations": [],  # No operations - comes pre-made from vendor
            })
            continue

        # Calculate per-operation costs
        # Track fixed (per_line_item) vs variable (per_unit) costs separately
        item_operations = []
        item_labor_fixed = 0.0      # per_line_item operations - don't multiply by qty
        item_labor_variable = 0.0   # per_unit operations - multiply by qty
        item_outsourced_fixed = 0.0
        item_outsourced_variable = 0.0

        for step in routing_by_item.get(item_id, []):
            ws = ws_map.get(step["station_id"], {})
            op_cost = 0.0
            is_outsourced = ws.get("is_outsourced", False)
            time_basis = step.get("time_basis", "per_unit")

            if is_outsourced:
                cost = step.get("cost_override")
                if cost is None:
                    cost = ws.get("outsourced_cost_default") or 0
                op_cost = float(cost)
                if time_basis == "per_line_item":
                    item_outsourced_fixed += op_cost
                else:
                    item_outsourced_variable += op_cost
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

            item_operations.append({
                "station_code": ws.get("station_code", ""),
                "station_name": ws.get("station_name", ""),
                "is_outsourced": is_outsourced,
                "est_time_min": float(step.get("est_time_min") or 0),
                "time_basis": time_basis,
                "cost": round(op_cost, 2),
            })

            # Accumulate into operations summary
            sid = step["station_id"]
            if sid not in ops_accumulator:
                ops_accumulator[sid] = {
                    "station_code": ws.get("station_code", ""),
                    "station_name": ws.get("station_name", ""),
                    "station_group": ws.get("station_group", "Other"),
                    "is_outsourced": is_outsourced,
                    "total_time_min": 0.0,
                    "total_cost": 0.0,
                    "items": set(),
                }
            # Respect time_basis: per_line_item = fixed time, per_unit = multiply by qty
            time_basis = step.get("time_basis", "per_unit")
            time_multiplier = 1 if time_basis == "per_line_item" else qty
            ops_accumulator[sid]["total_time_min"] += float(step.get("est_time_min") or 0) * time_multiplier
            ops_accumulator[sid]["total_cost"] += op_cost * time_multiplier
            ops_accumulator[sid]["items"].add(item.get("item_number", ""))

        # Calculate material cost (same logic as cost-estimate)
        item_material = 0.0
        item_mass = float(item.get("mass") or 0)
        for rm in rm_by_item.get(item_id, []):
            raw = rm.get("raw_materials") or {}
            mat_type = raw.get("material_type", "")
            mat_code = raw.get("material_code", "")
            price = raw.get("price_per_unit")
            mat_default_per_lb = default_price_per_lb.get(mat_code, 0.85)

            if mat_type == "SM":
                per_lb = float(price) if price is not None else mat_default_per_lb
                item_material += float(rm.get("qty_required") or 0) * per_lb
            else:
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

        # Calculate total costs respecting time_basis:
        # - Fixed costs (per_line_item): charged once regardless of qty
        # - Variable costs (per_unit): multiplied by qty

        # Extended = fixed costs (once) + variable costs (per qty)
        extended = (item_labor_fixed + item_outsourced_fixed +
                    (item_labor_variable + item_outsourced_variable + item_material) * qty)

        # Unit cost = variable costs per piece (for comparison/quoting)
        unit_cost = item_labor_variable + item_outsourced_variable + item_material

        total_labor += item_labor_fixed + item_labor_variable * qty
        total_material += item_material * qty
        total_outsourced += item_outsourced_fixed + item_outsourced_variable * qty

        manufactured_items.append({
            "item_id": item_id,
            "item_number": item.get("item_number", ""),
            "name": item.get("name", ""),
            "quantity": qty,
            "material_cost": round(item_material * qty, 2),
            "labor_cost": round(item_labor_fixed + item_labor_variable * qty, 2),
            "outsourced_cost": round(item_outsourced_fixed + item_outsourced_variable * qty, 2),
            "unit_cost": round(unit_cost, 2),
            "extended_cost": round(extended, 2),
            "operations": item_operations,
        })

    # Build operations summary (per-station)
    operations_summary = sorted([
        {
            "station_code": v["station_code"],
            "station_name": v["station_name"],
            "station_group": v["station_group"],
            "is_outsourced": v["is_outsourced"],
            "total_time_min": round(v["total_time_min"], 1),
            "total_cost": round(v["total_cost"], 2),
            "item_count": len(v["items"]),
            "items": sorted(v["items"]),
        }
        for v in ops_accumulator.values()
    ], key=lambda x: x["total_cost"], reverse=True)

    # Build grouped operations summary (by station_group)
    group_accumulator: dict[str, dict] = {}
    for op in operations_summary:
        grp = op["station_group"] or "Other"
        if grp not in group_accumulator:
            group_accumulator[grp] = {
                "group_name": grp,
                "total_time_min": 0.0,
                "total_cost": 0.0,
                "station_count": 0,
                "stations": [],
            }
        group_accumulator[grp]["total_time_min"] += op["total_time_min"]
        group_accumulator[grp]["total_cost"] += op["total_cost"]
        group_accumulator[grp]["station_count"] += 1
        group_accumulator[grp]["stations"].append({
            "station_code": op["station_code"],
            "station_name": op["station_name"],
            "is_outsourced": op["is_outsourced"],
            "total_time_min": op["total_time_min"],
            "total_cost": op["total_cost"],
        })

    operations_summary_grouped = sorted([
        {
            "group_name": v["group_name"],
            "total_time_min": round(v["total_time_min"], 1),
            "total_cost": round(v["total_cost"], 2),
            "station_count": v["station_count"],
            "stations": v["stations"],
        }
        for v in group_accumulator.values()
    ], key=lambda x: x["total_cost"], reverse=True)

    # Build chart data: labor ops individually, outsourced aggregated, material, purchased
    chart_data = []
    for op in operations_summary:
        if op["total_cost"] > 0 and not op["is_outsourced"]:
            chart_data.append({
                "label": op["station_name"],
                "value": op["total_cost"],
                "category": "labor",
                "station_group": op["station_group"],
            })
    if total_material > 0:
        chart_data.append({
            "label": "Raw Material",
            "value": round(total_material, 2),
            "category": "material",
        })
    if total_purchased > 0:
        chart_data.append({
            "label": "Purchased Parts",
            "value": round(total_purchased, 2),
            "category": "purchased",
        })
    if total_outsourced > 0:
        chart_data.append({
            "label": "Outsourced",
            "value": round(total_outsourced, 2),
            "category": "outsourced",
        })
    if total_kit_cost > 0:
        chart_data.append({
            "label": "Vendor Kits",
            "value": round(total_kit_cost, 2),
            "category": "kit",
        })

    # Build grouped chart data (for grouped pie view)
    chart_data_grouped = []
    for grp in operations_summary_grouped:
        if grp["total_cost"] > 0:
            chart_data_grouped.append({
                "label": grp["group_name"],
                "value": grp["total_cost"],
                "category": "labor_group",
                "stations": grp["stations"],
            })
    if total_material > 0:
        chart_data_grouped.append({
            "label": "Raw Material",
            "value": round(total_material, 2),
            "category": "material",
        })
    if total_purchased > 0:
        chart_data_grouped.append({
            "label": "Purchased Parts",
            "value": round(total_purchased, 2),
            "category": "purchased",
        })
    if total_outsourced > 0:
        chart_data_grouped.append({
            "label": "Outsourced",
            "value": round(total_outsourced, 2),
            "category": "outsourced",
        })
    if total_kit_cost > 0:
        chart_data_grouped.append({
            "label": "Vendor Kits",
            "value": round(total_kit_cost, 2),
            "category": "kit",
        })

    subtotal = total_labor + total_material + total_outsourced + total_purchased + total_kit_cost
    total = subtotal * overhead_multiplier

    # Build kits summary for response
    kits_summary = [{
        "kit_id": k["id"],
        "kit_number": k["kit_number"],
        "kit_name": k["kit_name"],
        "vendor": k.get("vendor"),
        "price": float(k.get("price") or 0),
    } for k in kits_data]

    return {
        "project_id": pid,
        "project_code": project_info.get("project_code", ""),
        "customer": project_info.get("customer") or "",
        "description": project_info.get("description") or "",
        "labor_cost": round(total_labor, 2),
        "material_cost": round(total_material, 2),
        "outsourced_cost": round(total_outsourced, 2),
        "purchased_cost": round(total_purchased, 2),
        "kit_cost": round(total_kit_cost, 2),
        "overhead_multiplier": overhead_multiplier,
        "subtotal": round(subtotal, 2),
        "total": round(total, 2),
        "manufactured_items": manufactured_items,
        "purchased_items": purchased_items,
        "kits": kits_summary,
        "operations_summary": operations_summary,
        "operations_summary_grouped": operations_summary_grouped,
        "cost_breakdown_chart": chart_data,
        "cost_breakdown_chart_grouped": chart_data_grouped,
    }


class BuildBookRequest(BaseModel):
    """BuildBook structure computed by the frontend (frontend/src/utils/buildBook.ts)."""
    book: dict


class SectionPrintsRequest(BaseModel):
    """One book section's print set: label + ordered items with quantities."""
    label: str
    items: list[dict]


@router.post("/projects/{project_id}/section-prints")
async def create_section_prints(project_id: UUID, payload: SectionPrintsRequest):
    """
    Combined PDF of one Build Book section's prints (a work package, a kit, or
    the design reference docs), each print stamped with its quantity in a
    white-backed box in the top-right margin. Small and fast — the shop pulls
    just the set they're about to work.
    """
    try:
        from ..services.build_book import generate_section_prints
        result = generate_section_prints(str(project_id), payload.label, payload.items)
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in payload.label)[:60]
        return Response(
            content=result["pdf"],
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{result["project_code"]}_{safe}.pdf"',
                "X-Pages": str(result["pages"]),
                "X-Prints-Bound": str(result["prints_bound"]),
                "X-Missing": str(len(result["missing"])),
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Section prints generation failed")
        raise HTTPException(status_code=500, detail=f"Failed to generate section prints: {str(e)}")


@router.post("/projects/{project_id}/build-book")
async def create_build_book(project_id: UUID, payload: BuildBookRequest):
    """
    Generate the Build Book PDF for an MRP project.

    The frontend computes the book structure (packages, kits, milestones) from
    the live schedule and posts it here; this endpoint renders the pages and
    binds reference-document prints behind the cover plus each kit's prints
    behind its chapter. Streams the finished PDF back (a full book with prints
    can exceed the storage upload limit); a copy is stored in print-packets
    when it fits.
    """
    try:
        from ..services.build_book import generate_build_book
        result = generate_build_book(str(project_id), payload.book)
        filename = f"{result['project_code']}_build_book.pdf"
        # plain Response, not StreamingResponse: the bytes are already in memory, and
        # Starlette iterates a BytesIO line-by-line (binary "lines"), which is glacial
        return Response(
            content=result["pdf"],
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Pages": str(result["pages"]),
                "X-Prints-Bound": str(result["prints_bound"]),
                "X-Stored-Path": result["stored_path"] or "",
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Build book generation failed")
        raise HTTPException(status_code=500, detail=f"Failed to generate build book: {str(e)}")


@router.post("/projects/{project_id}/print-packet")
async def create_print_packet(project_id: UUID):
    """
    Generate a new print packet for an MRP project.

    This creates a combined PDF with:
    - Cover sheet with project info and categorized parts lists
    - Each part's PDF with stamp overlays showing routing info

    Returns the download URL, storage path, and generation timestamp.
    """
    print(f"=== create_print_packet endpoint called for project_id={project_id} ===")
    try:
        result = await generate_print_packet(str(project_id))
        print(f"=== print packet generated successfully ===")
        print(f"=== result: {result} ===")
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


@router.get("/projects/{project_id}/download-dxfs")
async def download_project_dxfs(project_id: UUID):
    """
    Download all DXF files for a project as a ZIP archive.

    Filenames include part info: {item_number}_thk-{thickness}_qty-{quantity}.dxf
    Example: sjp00015_thk-0250_qty-1.dxf

    Returns a streaming ZIP file containing all DXF files for parts in the project.
    """
    supabase = get_supabase_admin()

    # Get all project parts with item details (including thickness and quantity)
    parts_result = supabase.table("mrp_project_parts") \
        .select("item_id, quantity, items(item_number, needs_dxf, thickness)") \
        .eq("project_id", str(project_id)) \
        .execute()

    if not parts_result.data:
        raise HTTPException(status_code=404, detail="No parts found in project")

    # Filter to only parts with needs_dxf=true (excluding zzz reference items)
    item_ids = []
    item_info = {}  # item_id (str) -> {item_number, thickness, quantity}
    for p in parts_result.data:
        if p.get("items") and p["items"].get("needs_dxf"):
            item_number = p["items"].get("item_number", "")
            # Skip zzz-prefix items (reference-only parts, not for manufacturing)
            if item_number.lower().startswith("zzz"):
                continue
            item_id = str(p["item_id"])  # Ensure string key
            item_ids.append(item_id)
            item_info[item_id] = {
                "item_number": item_number,
                "thickness": p["items"].get("thickness"),
                "quantity": p.get("quantity", 1)
            }

    logger.info(f"DXF download: {len(item_ids)} items with needs_dxf, item_info keys: {list(item_info.keys())[:3]}")

    if not item_ids:
        raise HTTPException(status_code=404, detail="No sheet metal parts (needs_dxf) found in project")

    # Get DXF files for these items
    files_result = supabase.table("files") \
        .select("item_id, file_name, file_path") \
        .eq("file_type", "DXF") \
        .in_("item_id", item_ids) \
        .execute()

    if not files_result.data:
        raise HTTPException(status_code=404, detail="No DXF files found for project parts")

    # Get project code for ZIP filename
    project_result = supabase.table("mrp_projects") \
        .select("project_code") \
        .eq("id", str(project_id)) \
        .single() \
        .execute()

    project_code = project_result.data.get("project_code", "project") if project_result.data else "project"

    # Create ZIP file in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for file_info in files_result.data:
            try:
                # Extract bucket and path from file_path (format: bucket-name/path/to/file)
                path_parts = file_info["file_path"].split("/")
                bucket = path_parts[0]
                file_path = "/".join(path_parts[1:])

                # Download file from storage
                file_data = supabase.storage.from_(bucket).download(file_path)

                # Build descriptive filename: {item_number}_thk-{thickness}_qty-{quantity}.dxf
                file_item_id = str(file_info["item_id"])  # Ensure string for lookup
                info = item_info.get(file_item_id, {})
                item_num = info.get("item_number", "")
                thickness = info.get("thickness")
                quantity = info.get("quantity", 1)

                if item_num:
                    # Format thickness as thousandths (0.25" -> 0250, 0.125" -> 0125)
                    if thickness is not None:
                        thk_str = f"{int(float(thickness) * 1000):04d}"
                    else:
                        thk_str = "0000"

                    filename = f"{item_num}_thk-{thk_str}_qty-{quantity}.dxf"
                else:
                    filename = file_info["file_name"]

                zip_file.writestr(filename, file_data)
            except Exception as e:
                print(f"Failed to add {file_info['file_name']} to ZIP: {e}")
                continue

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{project_code}_dxfs.zip"'}
    )
