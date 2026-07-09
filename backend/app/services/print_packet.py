"""Print Packet Generation Service.

Generates combined PDF print packets for MRP projects with:
- Cover sheet with project info and categorized parts lists
- Part PDFs with stamp overlays showing routing information
- Automatic compression and splitting for large jobs
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
from reportlab.lib.pagesizes import letter, landscape
from reportlab.pdfgen import canvas

from .supabase import get_supabase_admin

# Maximum size for a single PDF upload
# Matches print-packets bucket limit in Supabase
MAX_PDF_SIZE_BYTES = 50 * 1024 * 1024  # 50MB per bucket config

logger = logging.getLogger(__name__)


def _compress_pdf(pdf_bytes: bytes) -> bytes:
    """Compress PDF by removing duplicate objects and compressing streams."""
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        writer = PdfWriter()

        for page in reader.pages:
            writer.add_page(page)

        # Compress content streams and remove duplicates
        writer.add_metadata(reader.metadata or {})

        output = BytesIO()
        writer.write(output)
        output.seek(0)
        compressed = output.read()

        # Only use compressed version if it's actually smaller
        if len(compressed) < len(pdf_bytes):
            logger.info(f"PDF compressed: {len(pdf_bytes):,} -> {len(compressed):,} bytes ({100 - (len(compressed)*100//len(pdf_bytes))}% reduction)")
            return compressed
        return pdf_bytes
    except Exception as e:
        logger.warning(f"PDF compression failed: {e}")
        return pdf_bytes


def _split_pdf(pdf_bytes: bytes, max_size: int = MAX_PDF_SIZE_BYTES) -> list[bytes]:
    """Split a large PDF into multiple parts that fit under max_size.

    Returns a list of PDF byte arrays. If the PDF fits, returns a single-element list.
    """
    if len(pdf_bytes) <= max_size:
        return [pdf_bytes]

    reader = PdfReader(BytesIO(pdf_bytes))
    total_pages = len(reader.pages)

    if total_pages <= 1:
        # Can't split a single page, return as-is
        logger.warning(f"Cannot split single-page PDF of {len(pdf_bytes):,} bytes")
        return [pdf_bytes]

    # Estimate pages per chunk based on average page size
    avg_page_size = len(pdf_bytes) // total_pages
    pages_per_chunk = max(1, (max_size * 8 // 10) // avg_page_size)  # 80% of max to be safe

    logger.info(f"Splitting {total_pages} pages into chunks of ~{pages_per_chunk} pages each")

    parts = []
    start_page = 0

    while start_page < total_pages:
        end_page = min(start_page + pages_per_chunk, total_pages)

        writer = PdfWriter()
        for i in range(start_page, end_page):
            writer.add_page(reader.pages[i])

        output = BytesIO()
        writer.write(output)
        output.seek(0)
        chunk_bytes = output.read()

        # If chunk is still too big, reduce pages_per_chunk
        if len(chunk_bytes) > max_size and end_page - start_page > 1:
            pages_per_chunk = max(1, pages_per_chunk // 2)
            logger.info(f"Chunk too large ({len(chunk_bytes):,} bytes), reducing to {pages_per_chunk} pages per chunk")
            continue

        parts.append(chunk_bytes)
        start_page = end_page

    logger.info(f"Split PDF into {len(parts)} parts")
    return parts


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


# ============================================================================
# Assembly Tracking Sheet Constants and Functions
# ============================================================================

PRE_FAB_CUTOFF = 13  # sort_order <= 13 is pre-fab (through Press Brake)

# Stations to group into single "FAB" column (welding operations)
FAB_STATIONS = {"Weld Jigging", "Tig Welding", "Dual Shield Weld", "Weld Cleanup"}

# Post-fab individual stations (after FAB group)
POST_FAB_STATIONS = {"Paint and Paint Prep", "Mechanical Assembly"}

# Abbreviations for workstation column headers
STATION_ABBREV = {
    "Receiving": "RCV",
    "Saw": "SAW",
    "Deburr": "DBR",
    "Waterjet": "WJ",
    "Press Brake": "PB",
    "Weld Jigging": "JIG",
    "Tig Welding": "TIG",
    "Dual Shield Weld": "DS",
    "Weld Cleanup": "WCU",
    "Pipe Bending": "PIP",
    "Hole Punch - Iron Worker": "HP",
    "Part Staging": "STG",
    "Mechanical Assembly": "ASM",
    "Plumbing": "PLM",
    "Wiring": "WIR",
    "Inspection": "INS",
    "Galvanizing": "GAL",
    "Paint and Paint Prep": "PNT",
}


def _get_dynamic_workstation_columns(
    children: list[dict],
    routing_stations_by_item: dict[str, set[str]],
    routing_sequences_by_item: dict[str, dict[str, int]],
    all_workstations: list[dict],
    station_id_to_name: dict[str, str],
) -> tuple[list[dict], bool, list[dict]]:
    """
    Get workstation columns for tracking sheet.

    Returns: (pre_fab_columns, has_fab_work, post_fab_columns)
    - pre_fab_columns: Individual stations before TO FAB gate
    - has_fab_work: True if any child has FAB stations (Weld Jigging, Tig, etc.)
    - post_fab_columns: Paint and Assembly columns (if used)

    Columns are sorted by the minimum routing sequence across all children.
    """
    # Collect all station_ids used by children AND calculate minimum sequence per station
    used_station_ids = set()
    station_min_sequence = {}  # station_id -> min sequence across all children

    for child in children:
        child_id = child.get("child_item_id") or child.get("item_id")
        child_stations = routing_stations_by_item.get(child_id, set())
        child_sequences = routing_sequences_by_item.get(child_id, {})
        logger.info(f"    Child {child_id}: {len(child_stations)} stations")
        used_station_ids.update(child_stations)

        # Track minimum sequence for each station
        for station_id, sequence in child_sequences.items():
            if station_id not in station_min_sequence:
                station_min_sequence[station_id] = sequence
            else:
                station_min_sequence[station_id] = min(station_min_sequence[station_id], sequence)

    logger.info(f"    Total used_station_ids: {len(used_station_ids)}")
    logger.info(f"    Station min sequences: {station_min_sequence}")

    pre_fab = []
    has_fab_work = False
    post_fab = []

    for ws in all_workstations:
        if ws["id"] not in used_station_ids:
            continue
        name = ws["station_name"]

        if ws["sort_order"] <= PRE_FAB_CUTOFF:
            pre_fab.append(ws)
        elif name in FAB_STATIONS:
            has_fab_work = True  # Group into single FAB column
        elif name in POST_FAB_STATIONS:
            post_fab.append(ws)

    # Sort columns by minimum routing sequence (not sort_order)
    # Use a high default for stations without sequence data
    pre_fab.sort(key=lambda x: station_min_sequence.get(x["id"], 9999))
    post_fab.sort(key=lambda x: station_min_sequence.get(x["id"], 9999))

    return pre_fab, has_fab_work, post_fab


def _create_tracking_sheet(
    assembly_item_number: str,
    assembly_name: str,
    children: list[dict],
    pre_fab_columns: list[dict],
    has_fab_work: bool,
    post_fab_columns: list[dict],
    routing_stations_by_item: dict[str, set[str]],
    fab_station_ids: set[str],
    project_code: str,
) -> BytesIO:
    """Create tracking sheet PDF for one assembly (landscape orientation)."""

    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=landscape(letter))
    width, height = landscape(letter)  # 792 x 612 points

    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawString(36, height - 50, f"Assembly Tracking: {assembly_item_number}")
    c.setFont("Helvetica", 12)
    c.drawString(36, height - 70, f"Project: {project_code}")
    if assembly_name:
        # Truncate long names
        display_name = assembly_name[:60] + "..." if len(assembly_name) > 60 else assembly_name
        c.drawString(36, height - 88, display_name)

    # Draw table
    _draw_tracking_table(
        c, height - 110, children, pre_fab_columns,
        has_fab_work, post_fab_columns, routing_stations_by_item,
        fab_station_ids, width, height
    )

    c.save()
    packet.seek(0)
    return packet


def _draw_tracking_table(
    c: canvas.Canvas,
    y_start: float,
    children: list[dict],
    pre_fab_cols: list[dict],
    has_fab_work: bool,
    post_fab_cols: list[dict],
    routing_stations_by_item: dict[str, set[str]],
    fab_station_ids: set[str],
    page_width: float,
    page_height: float,
) -> None:
    """Draw tracking table with TO FAB gate (landscape layout with full station names)."""

    # Calculate dynamic column widths to fit page
    x_start = 36
    x_end = page_width - 36  # Right margin
    available_width = x_end - x_start

    # Fixed columns
    col_part = 80
    col_desc = 140
    col_qty = 30
    col_gate = 28  # TO FAB gate column
    col_fab = 45   # FAB column (if present)

    fixed_width = col_part + col_desc + col_qty + col_gate
    if has_fab_work:
        fixed_width += col_fab

    # Calculate station column width based on remaining space
    num_station_cols = len(pre_fab_cols) + len(post_fab_cols)
    if num_station_cols > 0:
        remaining_width = available_width - fixed_width
        col_station = max(50, min(70, remaining_width // num_station_cols))
    else:
        col_station = 60

    x_start = 36
    row_height = 20
    header_height = 28

    y = y_start

    # Draw header row
    c.setFont("Helvetica-Bold", 9)
    x = x_start

    # Part # header
    c.setFillColorRGB(0.95, 0.95, 0.95)
    c.rect(x, y - header_height, col_part, header_height, fill=1, stroke=1)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(x + 4, y - 18, "Part #")
    x += col_part

    # Description header
    c.setFillColorRGB(0.95, 0.95, 0.95)
    c.rect(x, y - header_height, col_desc, header_height, fill=1, stroke=1)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(x + 4, y - 18, "Description")
    x += col_desc

    # Qty header
    c.setFillColorRGB(0.95, 0.95, 0.95)
    c.rect(x, y - header_height, col_qty, header_height, fill=1, stroke=1)
    c.setFillColorRGB(0, 0, 0)
    c.drawCentredString(x + col_qty / 2, y - 18, "Qty")
    x += col_qty

    # Pre-fab station headers - full names
    for ws in pre_fab_cols:
        c.setFillColorRGB(0.95, 0.95, 0.95)
        c.rect(x, y - header_height, col_station, header_height, fill=1, stroke=1)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", 8)
        # Truncate long names if needed
        name = ws["station_name"]
        if len(name) > 12:
            name = name[:11] + "."
        c.drawCentredString(x + col_station / 2, y - 18, name)
        x += col_station

    # TO FAB gate header
    gate_x = x
    c.setFillColorRGB(0.85, 0.85, 0.85)
    c.rect(x, y - header_height, col_gate, header_height, fill=1, stroke=1)
    x += col_gate

    # FAB column header (if has fab work)
    if has_fab_work:
        c.setFillColorRGB(0.95, 0.95, 0.95)
        c.rect(x, y - header_height, col_fab, header_height, fill=1, stroke=1)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(x + col_fab / 2, y - 18, "FAB")
        x += col_fab

    # Post-fab station headers - full names
    for ws in post_fab_cols:
        c.setFillColorRGB(0.95, 0.95, 0.95)
        c.rect(x, y - header_height, col_station, header_height, fill=1, stroke=1)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", 8)
        name = ws["station_name"]
        if len(name) > 12:
            name = name[:11] + "."
        c.drawCentredString(x + col_station / 2, y - 18, name)
        x += col_station

    # Draw data rows
    y = y_start - header_height
    table_top = y
    table_bottom = y

    for child in children:
        if y < 72:  # Pagination check
            break

        child_item = child.get("items") or child
        child_id = child.get("child_item_id") or child_item.get("id")
        item_number = child_item.get("item_number", "")
        name = child_item.get("name") or child_item.get("description") or ""
        quantity = child.get("quantity", 1)
        child_stations = routing_stations_by_item.get(child_id, set())

        x = x_start

        # Part number cell - strip MMC/SPN prefixes for display
        display_pn = item_number
        pn_lower = item_number.lower()
        if pn_lower.startswith("mmc") or pn_lower.startswith("spn"):
            display_pn = item_number[3:]
        c.setFillColorRGB(1, 1, 1)
        c.rect(x, y - row_height, col_part, row_height, fill=1, stroke=1)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", 9)
        c.drawString(x + 4, y - 14, display_pn[:12])
        x += col_part

        # Description cell
        c.setFillColorRGB(1, 1, 1)
        c.rect(x, y - row_height, col_desc, row_height, fill=1, stroke=1)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(x + 4, y - 14, name[:22])
        x += col_desc

        # Qty cell
        c.setFillColorRGB(1, 1, 1)
        c.rect(x, y - row_height, col_qty, row_height, fill=1, stroke=1)
        c.setFillColorRGB(0, 0, 0)
        c.drawCentredString(x + col_qty / 2, y - 14, str(quantity))
        x += col_qty

        # Pre-fab station cells
        for ws in pre_fab_cols:
            applicable = ws["id"] in child_stations
            if applicable:
                c.setFillColorRGB(1, 1, 0.7)  # Yellow
            else:
                c.setFillColorRGB(0.85, 0.85, 0.85)  # Gray
            c.rect(x, y - row_height, col_station, row_height, fill=1, stroke=1)
            if applicable:
                c.setFillColorRGB(0, 0, 0)
                c.setFont("Helvetica", 9)
                c.drawCentredString(x + col_station / 2, y - 14, "(  )")
            x += col_station

        # Gate column cell (gray background, line drawn later)
        c.setFillColorRGB(0.9, 0.9, 0.9)
        c.rect(x, y - row_height, col_gate, row_height, fill=1, stroke=1)
        x += col_gate

        # FAB column cell
        if has_fab_work:
            has_fab_for_child = bool(child_stations & fab_station_ids)
            if has_fab_for_child:
                c.setFillColorRGB(1, 1, 0.7)  # Yellow
            else:
                c.setFillColorRGB(0.85, 0.85, 0.85)  # Gray
            c.rect(x, y - row_height, col_fab, row_height, fill=1, stroke=1)
            if has_fab_for_child:
                c.setFillColorRGB(0, 0, 0)
                c.setFont("Helvetica", 9)
                c.drawCentredString(x + col_fab / 2, y - 14, "(  )")
            x += col_fab

        # Post-fab station cells
        for ws in post_fab_cols:
            applicable = ws["id"] in child_stations
            if applicable:
                c.setFillColorRGB(1, 1, 0.7)  # Yellow
            else:
                c.setFillColorRGB(0.85, 0.85, 0.85)  # Gray
            c.rect(x, y - row_height, col_station, row_height, fill=1, stroke=1)
            if applicable:
                c.setFillColorRGB(0, 0, 0)
                c.setFont("Helvetica", 9)
                c.drawCentredString(x + col_station / 2, y - 14, "(  )")
            x += col_station

        y -= row_height
        table_bottom = y

    # Draw TO FAB gate - vertical lines on BOTH sides of the text
    c.saveState()
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(2)

    line_x = gate_x + col_gate / 2
    text_y = (table_top + table_bottom) / 2
    text_height = 35  # Approximate height of rotated text

    # Draw line ABOVE the text
    c.line(line_x, table_top + 4, line_x, text_y + text_height / 2 + 4)
    # Draw line BELOW the text
    c.line(line_x, text_y - text_height / 2 - 4, line_x, table_bottom)

    # Rotated "TO FAB" text (centered in the gap)
    c.translate(line_x, text_y)
    c.rotate(90)
    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(0, 0, 0)
    c.drawCentredString(0, -4, "TO FAB")
    c.restoreState()


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

    print(f"[PrintPacket] Generated PDF: {len(pdf_bytes):,} bytes ({len(pdf_bytes)/1024/1024:.2f} MB)", flush=True)
    logger.info(f"Generated PDF: {len(pdf_bytes):,} bytes")

    # 7. Compress the PDF
    pdf_bytes = _compress_pdf(pdf_bytes)
    print(f"[PrintPacket] After compression: {len(pdf_bytes):,} bytes ({len(pdf_bytes)/1024/1024:.2f} MB)", flush=True)
    logger.info(f"After compression: {len(pdf_bytes):,} bytes")

    # 8. Split if still too large (4MB chunks)
    print(f"[PrintPacket] Max chunk size: {MAX_PDF_SIZE_BYTES:,} bytes ({MAX_PDF_SIZE_BYTES/1024/1024:.2f} MB)", flush=True)
    pdf_parts = _split_pdf(pdf_bytes)
    is_split = len(pdf_parts) > 1
    print(f"[PrintPacket] Split into {len(pdf_parts)} parts", flush=True)

    # 9. Upload to Supabase Storage
    storage_paths = []
    for i, part_bytes in enumerate(pdf_parts):
        if is_split:
            storage_path = f"{project_code}/{project_code}_packet_part{i+1}.pdf"
        else:
            storage_path = f"{project_code}/{project_code}_packet.pdf"

        # Delete existing file if present (to replace)
        try:
            supabase.storage.from_("print-packets").remove([storage_path])
        except:
            pass

        logger.info(f"Uploading {storage_path}: {len(part_bytes):,} bytes ({len(part_bytes)/1024/1024:.2f} MB)")
        print(f"[PrintPacket] Uploading part {i+1}/{len(pdf_parts)}: {len(part_bytes):,} bytes ({len(part_bytes)/1024/1024:.2f} MB)", flush=True)

        try:
            supabase.storage.from_("print-packets").upload(
                storage_path,
                part_bytes,
                file_options={"content-type": "application/pdf", "upsert": "true"}
            )
            storage_paths.append(storage_path)
            print(f"[PrintPacket] Successfully uploaded {storage_path}", flush=True)
        except Exception as upload_err:
            print(f"[PrintPacket] Upload failed for {storage_path}: {upload_err}", flush=True)
            raise ValueError(f"Failed to upload part {i+1} ({len(part_bytes)/1024/1024:.2f} MB): {upload_err}")

    # If split, also delete any old single file
    if is_split:
        try:
            supabase.storage.from_("print-packets").remove([f"{project_code}/{project_code}_packet.pdf"])
        except:
            pass

    # 10. Update project record (store all paths as comma-separated if split)
    generated_at = datetime.utcnow().isoformat()
    supabase.table("mrp_projects").update({
        "print_packet_path": ",".join(storage_paths),
        "print_packet_generated_at": generated_at,
    }).eq("id", project_id).execute()

    # 11. Get signed URLs for download
    urls = []
    for path in storage_paths:
        signed = supabase.storage.from_("print-packets").create_signed_url(path, 3600)
        url = signed.get("signedURL") or signed.get("signedUrl")
        if url:
            urls.append(url)

    return {
        "url": urls[0] if urls else None,
        "urls": urls if is_split else None,
        "path": storage_paths[0] if storage_paths else None,
        "paths": storage_paths if is_split else None,
        "parts": len(pdf_parts) if is_split else None,
        "generated_at": generated_at,
    }


async def get_existing_packet(project_id: str) -> Optional[dict]:
    """Get info about existing print packet if available."""
    try:
        supabase = get_supabase_admin()

        result = supabase.table("mrp_projects").select(
            "print_packet_path, print_packet_generated_at"
        ).eq("id", project_id).single().execute()

        if not result.data or not result.data.get("print_packet_path"):
            return None

        path_str = result.data["print_packet_path"]
        paths = [p.strip() for p in path_str.split(",") if p.strip()]
        is_split = len(paths) > 1

        # Get fresh signed URLs for all paths
        urls = []
        for path in paths:
            signed = supabase.storage.from_("print-packets").create_signed_url(path, 3600)
            if signed:
                url = signed.get("signedURL") or signed.get("signedUrl")
                if url:
                    urls.append(url)

        if not urls:
            logger.warning(f"Failed to create signed URLs for packet: {path_str}")
            return None

        return {
            "url": urls[0],
            "urls": urls if is_split else None,
            "path": paths[0],
            "paths": paths if is_split else None,
            "parts": len(paths) if is_split else None,
            "generated_at": result.data.get("print_packet_generated_at"),
        }
    except Exception as e:
        logger.error(f"Error getting existing packet for project {project_id}: {e}")
        return None


async def _create_print_packet_pdf(
    project_code: str,
    customer: str,
    description: str,
    due_date: str,
    start_date: str,
    parts: list,
    supabase,
) -> bytes:
    """Create the combined PDF with cover sheet, tracking sheets, and stamped part PDFs."""

    print(f"=== _create_print_packet_pdf called for {project_code} with {len(parts)} parts ===")

    writer = PdfWriter()

    # Create cover sheet
    cover_pdf = _create_cover_sheet(
        project_code, customer, description, due_date, start_date, parts
    )
    cover_reader = PdfReader(cover_pdf)
    for page in cover_reader.pages:
        writer.add_page(page)

    # =========================================================================
    # Fetch data for tracking sheets
    # =========================================================================

    item_ids = [p["item_id"] for p in parts]

    # Fetch BOM children for all project items (to identify assemblies)
    bom_result = supabase.table("bom").select(
        "parent_item_id, child_item_id, quantity"
    ).in_("parent_item_id", item_ids).execute()

    # Get all child item IDs to fetch their details
    child_item_ids = set()
    for entry in bom_result.data or []:
        child_item_ids.add(entry["child_item_id"])

    # Fetch child item details
    child_items_map = {}
    if child_item_ids:
        child_items_result = supabase.table("items").select(
            "id, item_number, name, description"
        ).in_("id", list(child_item_ids)).execute()
        for item in child_items_result.data or []:
            child_items_map[item["id"]] = item

    # Build raw children_by_assembly lookup (includes all levels)
    raw_children_by_assembly = {}
    for entry in bom_result.data or []:
        parent_id = entry["parent_item_id"]
        child_id = entry["child_item_id"]
        child_info = child_items_map.get(child_id, {})

        child_entry = {
            "child_item_id": child_id,
            "quantity": entry["quantity"],
            "items": child_info,
        }

        if parent_id not in raw_children_by_assembly:
            raw_children_by_assembly[parent_id] = []
        raw_children_by_assembly[parent_id].append(child_entry)

    # Filter to FIRST-LEVEL children only
    # For each assembly, remove any children that are also children of its sub-assemblies
    children_by_assembly = {}
    for parent_id, children in raw_children_by_assembly.items():
        # Find which children are sub-assemblies (have their own children)
        sub_assembly_ids = set()
        for child in children:
            child_id = child["child_item_id"]
            if child_id in raw_children_by_assembly:
                sub_assembly_ids.add(child_id)

        # Collect all grandchildren (children of sub-assemblies)
        grandchildren_ids = set()
        for sub_asm_id in sub_assembly_ids:
            for grandchild in raw_children_by_assembly.get(sub_asm_id, []):
                grandchildren_ids.add(grandchild["child_item_id"])

        # Filter out grandchildren - keep only first-level children
        first_level_children = []
        for child in children:
            if child["child_item_id"] not in grandchildren_ids:
                first_level_children.append(child)

        children_by_assembly[parent_id] = first_level_children

    print(f"=== Found {len(children_by_assembly)} assemblies with first-level BOM children ===")
    logger.info(f"Found {len(children_by_assembly)} assemblies with first-level BOM children")

    # =========================================================================
    # Reorder parts hierarchically: top assembly -> sub-assemblies -> their parts
    # =========================================================================
    def get_hierarchical_order(parts_list, children_by_asm):
        """Reorder parts to follow BOM hierarchy (depth-first)."""
        # Build lookup by item_id
        parts_by_id = {p["item_id"]: p for p in parts_list}

        # Find which items are children of other items in the project
        child_ids = set()
        for parent_id, children in children_by_asm.items():
            for child in children:
                child_ids.add(child["child_item_id"])

        # Top-level assemblies are those that have children but aren't children themselves
        top_level_ids = []
        for part in parts_list:
            pid = part["item_id"]
            if pid in children_by_asm and pid not in child_ids:
                top_level_ids.append(pid)

        # If no clear top-level, fall back to assemblies first
        if not top_level_ids:
            top_level_ids = [p["item_id"] for p in parts_list if p["item_id"] in children_by_asm]

        # Build ordered list using depth-first traversal
        ordered = []
        visited = set()

        def visit(item_id):
            if item_id in visited:
                return
            visited.add(item_id)

            if item_id in parts_by_id:
                ordered.append(parts_by_id[item_id])

            # Visit children (sub-assemblies first, then parts)
            if item_id in children_by_asm:
                children = children_by_asm[item_id]
                # Sort: sub-assemblies first, then by item_number
                sub_asms = [c for c in children if c["child_item_id"] in children_by_asm]
                parts = [c for c in children if c["child_item_id"] not in children_by_asm]

                for child in sub_asms:
                    visit(child["child_item_id"])
                for child in parts:
                    visit(child["child_item_id"])

        # Start with top-level assemblies
        for top_id in top_level_ids:
            visit(top_id)

        # Add any remaining parts not in the hierarchy
        for part in parts_list:
            if part["item_id"] not in visited:
                ordered.append(part)
                visited.add(part["item_id"])

        return ordered

    parts = get_hierarchical_order(parts, children_by_assembly)
    print(f"=== Reordered {len(parts)} parts hierarchically ===")

    # Fetch all workstations with sort_order (explicitly sort to ensure order)
    ws_all_result = supabase.table("workstations").select(
        "id, station_code, station_name, sort_order"
    ).order("sort_order").execute()
    all_workstations = sorted(ws_all_result.data or [], key=lambda x: x.get("sort_order", 0))

    # Build station_id to station_name lookup
    station_id_to_name = {ws["id"]: ws["station_name"] for ws in all_workstations}

    # Build set of FAB station IDs (for grouped FAB column)
    fab_station_ids = set()
    for ws in all_workstations:
        if ws["station_name"] in FAB_STATIONS:
            fab_station_ids.add(ws["id"])

    # Fetch routing with station_id AND sequence for all items (including BOM children)
    all_item_ids = list(set(item_ids) | child_item_ids)
    routing_result = supabase.table("routing").select(
        "item_id, station_id, sequence"
    ).in_("item_id", all_item_ids).execute()

    # Build routing_stations_by_item lookup (item_id -> set of station_ids)
    # Build routing_sequences_by_item lookup (item_id -> {station_id: sequence})
    routing_stations_by_item = {}
    routing_sequences_by_item = {}
    for row in routing_result.data or []:
        item_id = row["item_id"]
        station_id = row["station_id"]
        sequence = row.get("sequence", 0)

        if item_id not in routing_stations_by_item:
            routing_stations_by_item[item_id] = set()
        routing_stations_by_item[item_id].add(station_id)

        if item_id not in routing_sequences_by_item:
            routing_sequences_by_item[item_id] = {}
        routing_sequences_by_item[item_id][station_id] = sequence

    logger.info(f"Built routing lookup for {len(routing_stations_by_item)} items")

    # =========================================================================
    # Process parts and insert tracking sheets
    # =========================================================================

    parts_processed = 0
    parts_skipped = 0
    tracking_sheets_added = 0

    for part in parts:
        if part["category"] in ("mcmaster", "supplier"):
            logger.debug(f"Skipping {part['item_number']} - {part['category']} part")
            continue  # Skip supplier parts - no drawings

        item_id = part["item_id"]

        # =====================================================================
        # Insert tracking sheet if this is an assembly with BOM children
        # =====================================================================
        logger.info(f"Checking if {part['item_number']} (id={item_id}) is an assembly...")
        logger.info(f"children_by_assembly has {len(children_by_assembly)} assemblies")

        if item_id in children_by_assembly:
            children = children_by_assembly[item_id]
            child_numbers = [c.get("items", {}).get("item_number", "?") for c in children]
            print(f"=== Assembly {part['item_number']} has {len(children)} BOM children: {child_numbers[:10]} ===")
            logger.info(f"Assembly {part['item_number']} has {len(children)} BOM children")

            # Get dynamic workstation columns for this assembly's children
            pre_fab_cols, has_fab_work, post_fab_cols = _get_dynamic_workstation_columns(
                children, routing_stations_by_item, routing_sequences_by_item,
                all_workstations, station_id_to_name
            )
            logger.info(f"  -> pre_fab: {len(pre_fab_cols)}, has_fab_work: {has_fab_work}, post_fab: {len(post_fab_cols)}")

            # Only create tracking sheet if there are workstation columns to show
            print(f"=== Checking columns: pre_fab={len(pre_fab_cols)}, has_fab={has_fab_work}, post_fab={len(post_fab_cols)} ===")
            if pre_fab_cols or has_fab_work or post_fab_cols:
                print(f"=== CREATING tracking sheet for {part['item_number']} ===")
                logger.info(f"Creating tracking sheet for assembly {part['item_number']} with {len(children)} children")

                tracking_pdf = _create_tracking_sheet(
                    assembly_item_number=part["item_number"],
                    assembly_name=part.get("name") or part.get("description") or "",
                    children=children,
                    pre_fab_columns=pre_fab_cols,
                    has_fab_work=has_fab_work,
                    post_fab_columns=post_fab_cols,
                    routing_stations_by_item=routing_stations_by_item,
                    fab_station_ids=fab_station_ids,
                    project_code=project_code,
                )
                tracking_reader = PdfReader(tracking_pdf)
                for page in tracking_reader.pages:
                    writer.add_page(page)
                tracking_sheets_added += 1
            else:
                logger.debug(f"Skipping tracking sheet for {part['item_number']} - no workstation columns")

        # =====================================================================
        # Add part's PDF with stamp overlay
        # =====================================================================
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

            # Download PDF from Supabase storage with timeout
            # Use signed URL + httpx for timeout control (Supabase SDK has no timeout)
            try:
                signed_url_response = supabase.storage.from_(bucket_name).create_signed_url(storage_path, 300)
                if not signed_url_response or not signed_url_response.get('signedURL'):
                    logger.warning(f"Failed to create signed URL for {part['item_number']}: {pdf_path}")
                    parts_skipped += 1
                    continue

                signed_url = signed_url_response['signedURL']

                # Download with 30 second timeout per file
                with httpx.Client(timeout=30.0) as client:
                    response = client.get(signed_url)
                    response.raise_for_status()
                    pdf_data = response.content
            except httpx.TimeoutException:
                logger.warning(f"Download timeout for {part['item_number']}: {pdf_path}")
                parts_skipped += 1
                continue
            except httpx.HTTPStatusError as e:
                logger.warning(f"HTTP error downloading {part['item_number']}: {e}")
                parts_skipped += 1
                continue

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

    logger.info(f"Print packet: processed {parts_processed} parts, skipped {parts_skipped}, added {tracking_sheets_added} tracking sheets")

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
            pn_lower = pn.lower()
            if show_link and pn_lower.startswith("mmc"):
                # McMaster link - strip MMC prefix
                display_pn = pn[3:]
                url = f"https://www.mcmaster.com/{display_pn}/"
                c.setFillColorRGB(0, 0, 0.8)
                c.drawString(72, y, display_pn)
                c.linkURL(url, (72, y - 2, 180, y + 10), relative=0)
                c.setFillColorRGB(0, 0, 0)
            elif pn_lower.startswith("spn"):
                # Supplier part - strip SPN prefix
                display_pn = pn[3:]
                c.drawString(72, y, display_pn)
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

    # Draw stamp box - transparent background (no fill) so drawing shows through
    c.setStrokeColorRGB(0.3, 0.3, 0.3)  # Dark gray border
    c.setLineWidth(0.5)
    c.rect(x, y, stamp_width, stamp_height, fill=0, stroke=1)  # fill=0 = transparent

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

    # Draw stamp content - strip MMC/SPN prefixes for display
    pn = part['item_number']
    pn_lower = pn.lower()
    display_pn = pn[3:] if pn_lower.startswith("mmc") or pn_lower.startswith("spn") else pn
    draw_line(f"Project - {project_code}", bold=True)
    draw_line(f"Part # - {display_pn}")
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
