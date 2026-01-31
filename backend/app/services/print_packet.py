"""Print Packet Generation Service.

Generates combined PDF print packets for MRP projects with:
- Cover sheet with project info and categorized parts lists
- Part PDFs with stamp overlays showing routing information
"""

import os
import math
import logging
from io import BytesIO
from datetime import datetime, timedelta
from typing import Optional
import tempfile
import httpx

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from .supabase import get_supabase_admin

logger = logging.getLogger(__name__)


def categorize_part(item_number: str) -> str:
    """Categorize part by item_number prefix."""
    pn = item_number.lower()
    if pn.startswith('mmc'):
        return 'mcmaster'
    elif pn.startswith('spn'):
        return 'supplier'
    elif pn.startswith('zzz'):
        return 'reference'
    else:
        return 'manufactured'


async def generate_print_packet(project_id: str) -> dict:
    """
    Generate a print packet PDF for an MRP project.

    Returns dict with: url, path, generated_at
    """
    supabase = get_supabase_admin()

    # 1. Fetch project info
    project_result = supabase.table("mrp_projects").select("*").eq("id", project_id).single().execute()
    if not project_result.data:
        raise ValueError(f"Project not found: {project_id}")

    project = project_result.data
    project_code = project["project_code"]

    # 2. Fetch project parts with item details
    parts_result = supabase.table("mrp_project_parts").select(
        "quantity, items(id, item_number, name, description, is_supplier_part)"
    ).eq("project_id", project_id).execute()

    if not parts_result.data:
        raise ValueError("No parts found in project")

    # Build parts list, filtering out zzz* reference parts
    parts = []
    item_ids = []
    for row in parts_result.data:
        item = row.get("items")
        if not item:
            continue
        item_number = item.get("item_number", "")
        if item_number.lower().startswith("zzz"):
            continue

        parts.append({
            "item_id": item["id"],
            "item_number": item_number,
            "name": item.get("name") or "",
            "description": item.get("description") or "",
            "quantity": row["quantity"],
            "category": categorize_part(item_number),
            "is_supplier_part": item.get("is_supplier_part", False),
        })
        item_ids.append(item["id"])

    if not parts:
        raise ValueError("No valid parts to include in print packet")

    # Sort parts: assemblies first, then alphabetically
    def sort_key(p):
        name_desc = (p["name"] + p["description"]).lower()
        is_asm = 0 if "asm" in name_desc else 1
        return (is_asm, p["item_number"])

    parts.sort(key=sort_key)

    # 3. Fetch routing for each item
    routing_result = supabase.table("routing").select(
        "item_id, sequence, workstations(station_code, station_name)"
    ).in_("item_id", item_ids).order("sequence").execute()

    routing_by_item = {}
    for row in routing_result.data or []:
        item_id = row["item_id"]
        ws = row.get("workstations")
        if ws:
            if item_id not in routing_by_item:
                routing_by_item[item_id] = []
            routing_by_item[item_id].append(f"{ws['station_code']} - {ws['station_name']}")

    # 4. Fetch PDF file paths for each item
    files_result = supabase.table("files").select(
        "item_id, file_path"
    ).in_("item_id", item_ids).eq("file_type", "PDF").not_.is_("file_path", "null").execute()

    pdf_by_item = {}
    for row in files_result.data or []:
        if row["item_id"] not in pdf_by_item:
            pdf_by_item[row["item_id"]] = row["file_path"]

    # 5. Fetch raw materials
    materials_result = supabase.table("routing_materials").select(
        "item_id, qty_required, blank_width_in, blank_height_in, raw_materials(part_number, material_type, material_code, dim1_in, dim2_in, wall_or_thk_in)"
    ).in_("item_id", item_ids).execute()

    materials_by_item = {}
    for row in materials_result.data or []:
        item_id = row["item_id"]
        mat = row.get("raw_materials")
        if mat:
            if item_id not in materials_by_item:
                materials_by_item[item_id] = []
            materials_by_item[item_id].append({
                "qty_required": float(row["qty_required"] or 0),
                "part_number": mat.get("part_number", ""),
                "material_type": mat.get("material_type", ""),
                "material_code": mat.get("material_code", ""),
                "dim1": mat.get("dim1_in"),
                "dim2": mat.get("dim2_in"),
                "thickness": mat.get("wall_or_thk_in"),
            })

    # Enrich parts with routing, pdf_path, materials
    for part in parts:
        item_id = part["item_id"]
        part["routing"] = routing_by_item.get(item_id, [])
        part["pdf_path"] = pdf_by_item.get(item_id)
        part["raw_materials"] = materials_by_item.get(item_id, [])

    # Calculate start date from total routing time
    total_minutes = 0
    for part in parts:
        part_time = len(part["routing"]) * 15  # Estimate if no specific times
        total_minutes += part_time * part["quantity"]

    work_days = math.ceil(total_minutes / 480) if total_minutes > 0 else 5

    due_date = project.get("due_date")
    start_date = project.get("start_date")

    if due_date and not start_date:
        try:
            due_dt = datetime.strptime(str(due_date), "%Y-%m-%d")
            start_dt = due_dt - timedelta(days=work_days)
            start_date = start_dt.strftime("%m/%d/%Y")
            due_date = due_dt.strftime("%m/%d/%Y")
        except:
            pass
    elif due_date:
        try:
            due_dt = datetime.strptime(str(due_date), "%Y-%m-%d")
            due_date = due_dt.strftime("%m/%d/%Y")
        except:
            pass

    if start_date:
        try:
            start_dt = datetime.strptime(str(start_date), "%Y-%m-%d")
            start_date = start_dt.strftime("%m/%d/%Y")
        except:
            pass

    # 6. Generate PDF
    pdf_bytes = await _create_print_packet_pdf(
        project_code=project_code,
        customer=project.get("customer") or "",
        description=project.get("description") or "",
        due_date=due_date or "",
        start_date=start_date or "",
        parts=parts,
        supabase=supabase,
    )

    # 7. Upload to Supabase Storage
    storage_path = f"{project_code}/{project_code}_packet.pdf"

    # Delete existing file if present (to replace)
    try:
        supabase.storage.from_("print-packets").remove([storage_path])
    except:
        pass

    upload_result = supabase.storage.from_("print-packets").upload(
        storage_path,
        pdf_bytes,
        file_options={"content-type": "application/pdf", "upsert": "true"}
    )

    # 8. Update project record
    generated_at = datetime.utcnow().isoformat()
    supabase.table("mrp_projects").update({
        "print_packet_path": storage_path,
        "print_packet_generated_at": generated_at,
    }).eq("id", project_id).execute()

    # 9. Get signed URL for download
    signed = supabase.storage.from_("print-packets").create_signed_url(storage_path, 3600)

    return {
        "url": signed.get("signedURL") or signed.get("signedUrl"),
        "path": storage_path,
        "generated_at": generated_at,
    }


async def get_existing_packet(project_id: str) -> Optional[dict]:
    """Get info about existing print packet if available."""
    supabase = get_supabase_admin()

    result = supabase.table("mrp_projects").select(
        "print_packet_path, print_packet_generated_at"
    ).eq("id", project_id).single().execute()

    if not result.data or not result.data.get("print_packet_path"):
        return None

    path = result.data["print_packet_path"]

    # Get fresh signed URL
    signed = supabase.storage.from_("print-packets").create_signed_url(path, 3600)

    return {
        "url": signed.get("signedURL") or signed.get("signedUrl"),
        "path": path,
        "generated_at": result.data.get("print_packet_generated_at"),
    }


async def _create_print_packet_pdf(
    project_code: str,
    customer: str,
    description: str,
    due_date: str,
    start_date: str,
    parts: list,
    supabase,
) -> bytes:
    """Create the combined PDF with cover sheet and stamped part PDFs."""

    writer = PdfWriter()

    # Create cover sheet
    cover_pdf = _create_cover_sheet(
        project_code, customer, description, due_date, start_date, parts
    )
    cover_reader = PdfReader(cover_pdf)
    for page in cover_reader.pages:
        writer.add_page(page)

    # Process each part's PDF
    parts_processed = 0
    parts_skipped = 0

    for part in parts:
        if part["category"] in ("mcmaster", "supplier"):
            logger.debug(f"Skipping {part['item_number']} - {part['category']} part")
            continue  # Skip supplier parts - no drawings

        pdf_path = part.get("pdf_path")
        if not pdf_path:
            logger.warning(f"No PDF path for {part['item_number']}")
            parts_skipped += 1
            continue

        logger.info(f"Processing PDF for {part['item_number']}: {pdf_path}")

        try:
            # Parse bucket and path from file_path
            # Format: "bucket-name/item/rev/iter/filename.pdf"
            path_parts = pdf_path.split('/', 1)
            if len(path_parts) != 2:
                logger.warning(f"Invalid path format for {part['item_number']}: {pdf_path}")
                parts_skipped += 1
                continue

            bucket_name = path_parts[0]  # e.g., "pdm-drawings"
            storage_path = path_parts[1]  # e.g., "csp00540/A/1/csp00540.pdf"

            logger.info(f"Downloading from bucket '{bucket_name}' path '{storage_path}'")

            # Download PDF from Supabase storage
            pdf_data = supabase.storage.from_(bucket_name).download(storage_path)

            if pdf_data is None:
                logger.warning(f"Download returned None for {part['item_number']}: {pdf_path}")
                parts_skipped += 1
                continue

            # Check if we got bytes or something else
            if isinstance(pdf_data, bytes):
                logger.info(f"Downloaded {len(pdf_data)} bytes for {part['item_number']}")
            else:
                logger.warning(f"Unexpected download type for {part['item_number']}: {type(pdf_data)}")
                parts_skipped += 1
                continue

            if len(pdf_data) == 0:
                logger.warning(f"Empty PDF data for {part['item_number']}")
                parts_skipped += 1
                continue

            reader = PdfReader(BytesIO(pdf_data))
            logger.info(f"PDF has {len(reader.pages)} pages for {part['item_number']}")

            for page in reader.pages:
                # Get page dimensions
                page_width = float(page.mediabox.width)
                page_height = float(page.mediabox.height)

                # Create stamp overlay
                stamp_pdf = _create_stamp(
                    part, project_code, start_date, due_date,
                    page_width, page_height
                )
                stamp_reader = PdfReader(stamp_pdf)

                # Merge stamp onto page
                page.merge_page(stamp_reader.pages[0])
                writer.add_page(page)

            parts_processed += 1

        except Exception as e:
            logger.error(f"Error processing PDF for {part['item_number']}: {e}", exc_info=True)
            parts_skipped += 1
            continue

    logger.info(f"Print packet: processed {parts_processed} parts, skipped {parts_skipped}")

    # Write to bytes
    output = BytesIO()
    writer.write(output)
    output.seek(0)
    return output.read()


def _create_cover_sheet(
    project_code: str,
    customer: str,
    description: str,
    due_date: str,
    start_date: str,
    parts: list,
) -> BytesIO:
    """Create cover sheet PDF with categorized parts lists."""

    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=letter)
    width, height = letter

    # Title
    c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(width/2, height - 80, f"Project: {project_code}")

    # Project info
    c.setFont("Helvetica", 14)
    y = height - 130

    if customer:
        c.drawString(72, y, f"Customer: {customer}")
        y -= 25
    if description:
        c.drawString(72, y, f"Description: {description}")
        y -= 25
    if due_date:
        c.drawString(72, y, f"Due Date: {due_date}")
        y -= 25
    if start_date:
        c.drawString(72, y, f"Start Date: {start_date}")
        y -= 25

    y -= 20

    # Helper to draw a parts table section
    def draw_parts_section(title: str, section_parts: list, show_link: bool = False):
        nonlocal y, c

        if not section_parts:
            return

        if y < 150:
            c.showPage()
            y = height - 72

        c.setFont("Helvetica-Bold", 14)
        c.drawString(72, y, title)
        y -= 20

        # Header
        c.setFont("Helvetica-Bold", 10)
        c.drawString(72, y, "Part Number")
        c.drawString(200, y, "Description")
        c.drawString(480, y, "Qty")
        y -= 5
        c.line(72, y, width - 72, y)
        y -= 15

        c.setFont("Helvetica", 9)
        for part in section_parts:
            if y < 72:
                c.showPage()
                y = height - 72
                c.setFont("Helvetica", 9)

            pn = part["item_number"]
            if show_link and pn.lower().startswith("mmc"):
                # McMaster link
                mmc_pn = pn[3:]
                url = f"https://www.mcmaster.com/{mmc_pn}/"
                c.setFillColorRGB(0, 0, 0.8)
                c.drawString(72, y, mmc_pn)
                c.linkURL(url, (72, y - 2, 180, y + 10), relative=0)
                c.setFillColorRGB(0, 0, 0)
            else:
                c.drawString(72, y, pn)

            desc = (part.get("description") or part.get("name") or "")[:40]
            c.drawString(200, y, desc)
            c.drawString(480, y, str(part["quantity"]))

            y -= 3
            c.setStrokeColorRGB(0.8, 0.8, 0.8)
            c.line(72, y, width - 72, y)
            c.setStrokeColorRGB(0, 0, 0)
            y -= 12

        y -= 15

    # Categorize parts
    mfg_parts = [p for p in parts if p["category"] == "manufactured"]
    mcmaster_parts = [p for p in parts if p["category"] == "mcmaster"]
    supplier_parts = [p for p in parts if p["category"] == "supplier"]

    # Draw sections
    draw_parts_section("Manufactured Parts", mfg_parts)
    draw_parts_section("McMaster-Carr Parts", mcmaster_parts, show_link=True)
    draw_parts_section("Supplier Parts", supplier_parts)

    # Raw Materials section
    material_totals = {}
    for part in parts:
        part_qty = part["quantity"]
        for mat in part.get("raw_materials", []):
            pn = mat.get("part_number", "")
            if not pn:
                continue
            mat_qty = float(mat.get("qty_required", 0))
            total_qty = mat_qty * part_qty

            if pn in material_totals:
                material_totals[pn]["total_qty"] += total_qty
            else:
                material_totals[pn] = {
                    "part_number": pn,
                    "material_code": mat.get("material_code", ""),
                    "material_type": mat.get("material_type", ""),
                    "dim1": mat.get("dim1"),
                    "dim2": mat.get("dim2"),
                    "thickness": mat.get("thickness"),
                    "total_qty": total_qty,
                }

    if material_totals:
        if y < 150:
            c.showPage()
            y = height - 72

        c.setFont("Helvetica-Bold", 14)
        c.drawString(72, y, "Raw Material Requirements")
        y -= 20

        c.setFont("Helvetica-Bold", 10)
        c.drawString(72, y, "Material P/N")
        c.drawString(180, y, "Material / Size")
        c.drawString(350, y, "Total")
        c.drawString(420, y, "Feet")
        c.drawString(480, y, "Sticks")
        y -= 5
        c.line(72, y, width - 72, y)
        y -= 15

        c.setFont("Helvetica", 9)
        for pn, mat in material_totals.items():
            if y < 72:
                c.showPage()
                y = height - 72
                c.setFont("Helvetica", 9)

            c.drawString(72, y, mat["part_number"][:15])

            dims = f"{mat['material_code']} "
            if mat["dim1"] and mat["dim2"]:
                dims += f"{mat['dim1']}x{mat['dim2']}"
            if mat["thickness"]:
                dims += f"x{mat['thickness']}"
            c.drawString(180, y, dims[:25])

            if mat["material_type"] == "SM":
                c.drawString(350, y, f"{mat['total_qty']:.1f} lb")
            else:
                total_in = mat["total_qty"]
                total_ft = total_in / 12
                sticks = math.ceil(total_ft / 20)
                c.drawString(350, y, f"{total_in:.1f} in")
                c.drawString(420, y, f"{total_ft:.1f}")
                c.drawString(480, y, str(sticks))

            y -= 3
            c.setStrokeColorRGB(0.8, 0.8, 0.8)
            c.line(72, y, width - 72, y)
            c.setStrokeColorRGB(0, 0, 0)
            y -= 12

    c.save()
    packet.seek(0)
    return packet


def _create_stamp(
    part: dict,
    project_code: str,
    start_date: str,
    due_date: str,
    page_width: float,
    page_height: float,
) -> BytesIO:
    """Create stamp overlay for a page."""

    routing = part.get("routing", [])

    # Calculate stamp height based on routing lines
    base_height = 120
    routing_height = len(routing) * 14
    stamp_height = base_height + routing_height
    stamp_width = 180

    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=(page_width, page_height))

    # Position: right edge, vertically centered
    x = page_width - stamp_width - 20
    y = (page_height - stamp_height) / 2

    # Draw stamp box
    c.setStrokeColorRGB(0, 0, 0)
    c.setFillColorRGB(1, 1, 1)
    c.rect(x, y, stamp_width, stamp_height, fill=1, stroke=1)

    # Text settings
    c.setFillColorRGB(0, 0, 0)
    line_height = 14
    current_y = y + stamp_height - 18

    def draw_line(text: str, bold: bool = False):
        nonlocal current_y
        if bold:
            c.setFont("Helvetica-Bold", 9)
        else:
            c.setFont("Helvetica", 9)
        c.drawString(x + 8, current_y, text)
        current_y -= line_height

    # Draw stamp content
    draw_line(f"Project - {project_code}", bold=True)
    draw_line(f"Part # - {part['item_number']}")
    if start_date:
        draw_line(f"Start - {start_date}")
    if due_date:
        draw_line(f"Due - {due_date}")
    draw_line(f"QTY - ({part['quantity']})")

    if routing:
        current_y -= 4
        draw_line("WORKSTATIONS", bold=True)
        for route in routing:
            draw_line(f"  {route}  ( )")

    c.save()
    packet.seek(0)
    return packet
