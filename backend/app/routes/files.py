"""Files API routes."""

import re
import zipfile
import csv
from io import BytesIO, StringIO
from datetime import datetime

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from typing import Optional
from uuid import UUID

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from ..services.supabase import get_supabase_admin
from ..models.schemas import FileInfo, FileCreate

router = APIRouter(prefix="/files", tags=["files"])


def get_next_rev(current_rev: str) -> str:
    """Increment revision letter: A->B, B->C, etc."""
    if not current_rev:
        return 'A'
    # Handle single letter revs
    if len(current_rev) == 1 and current_rev.isalpha():
        if current_rev.upper() == 'Z':
            return 'AA'
        return chr(ord(current_rev.upper()) + 1)
    return current_rev + '.1'  # Fallback


def get_file_type(filename: str) -> str:
    """Determine file type from extension."""
    ext = filename.lower().split(".")[-1] if "." in filename else ""
    type_map = {
        "stp": "STEP",
        "step": "STEP",
        "prt": "CAD",
        "asm": "CAD",
        "drw": "CAD",
        "dxf": "DXF",
        "svg": "SVG",
        "pdf": "PDF",
        "png": "IMAGE",
        "jpg": "IMAGE",
        "jpeg": "IMAGE",
        "stl": "STL",
    }
    return type_map.get(ext, "OTHER")


def stamp_pdf_upload_date(content: bytes, revision: str = "A", iteration: int = 1) -> bytes:
    """
    Stamp a PDF with upload date and revision/iteration info.

    Adds two stamps to each page:
    - Bottom left: "Upload - MM/DD/YYYY"
    - Bottom right: "A.1" (revision.iteration)

    Args:
        content: Original PDF file content as bytes
        revision: File revision letter (e.g., "A", "B")
        iteration: File iteration number (e.g., 1, 2, 3)

    Returns:
        Modified PDF content as bytes with stamps on each page
    """
    try:
        reader = PdfReader(BytesIO(content))
        writer = PdfWriter()

        # Get current date formatted as MM/DD/YYYY
        upload_date = datetime.now().strftime("%m/%d/%Y")
        date_stamp = f"Upload - {upload_date}"
        rev_stamp = f"{revision}.{iteration}"

        for page in reader.pages:
            # Get page dimensions
            page_width = float(page.mediabox.width)
            page_height = float(page.mediabox.height)

            # Create stamp overlay
            stamp_buffer = BytesIO()
            c = canvas.Canvas(stamp_buffer, pagesize=(page_width, page_height))

            c.setFillColorRGB(0, 0, 0)
            c.setFont("Helvetica", 12)

            # Position: lower left, past corner mark (upload date)
            x_left = 82  # ~1.1 inch from left edge
            y = 8   # Just below the margin line
            c.drawString(x_left, y, date_stamp)

            # Position: bottom left, near upload date stamp
            x_rev = 250  # Right after upload date text
            c.drawString(x_rev, y, rev_stamp)

            c.save()
            stamp_buffer.seek(0)

            # Merge stamp onto page
            stamp_reader = PdfReader(stamp_buffer)
            page.merge_page(stamp_reader.pages[0])
            writer.add_page(page)

        # Write to bytes
        output = BytesIO()
        writer.write(output)
        output.seek(0)
        return output.read()

    except Exception as e:
        # If stamping fails, return original content
        print(f"Warning: PDF stamping failed: {e}")
        return content


def normalize_filename(filename: str, item_number: str) -> str:
    """
    Normalize filename for consistent storage.

    Normalizations:
        - Lowercase everything
        - Strip redundant suffixes (_dxf, _prt, _asm, etc.)
        - Normalize .stp to .step

    Examples:
        xxp516691_dxf.dxf -> xxp516691.dxf
        XXP516691.STP -> xxp516691.step
        jbp00010_prt.stp -> jbp00010.step
        rxa00100_asm.stp -> rxa00100.step
        xxp516691.dxf -> xxp516691.dxf

    Args:
        filename: Original filename
        item_number: The item number (used as base for normalized name)

    Returns:
        Normalized filename as [item_number].[extension] (lowercase)
    """
    # Get extension (lowercase)
    if "." not in filename:
        return filename.lower()

    ext = filename.lower().split(".")[-1]

    # Normalize .stp to .step
    if ext == 'stp':
        ext = 'step'

    # For these file types, always normalize to [item_number].[ext]
    # This strips any suffixes like _dxf, _prt, _asm, _stp, etc.
    normalize_extensions = {'dxf', 'step', 'svg', 'pdf'}

    if ext in normalize_extensions:
        return f"{item_number.lower()}.{ext}"

    # For other files, just lowercase the original name
    return filename.lower()


# Valid item_number patterns for auto-creation
ITEM_NUMBER_PATTERNS = [
    re.compile(r"^mmc[a-z0-9_-]+$"),   # McMaster (e.g., mmc12555k88)
    re.compile(r"^spn[a-z0-9_-]+$"),   # Supplier (e.g., spnca3102e14s-2pb)
    re.compile(r"^zzz[a-z0-9]+$"),     # Reference
    re.compile(r"^[a-z]{3}\d{4,6}$"),  # Standard (e.g., stp02810)
]


def is_valid_item_number(item_number: str) -> bool:
    """Check if an item_number matches a known naming convention."""
    return any(p.match(item_number) for p in ITEM_NUMBER_PATTERNS)


def flatten_bom_tree(tree_node: dict, parent_path: str = "", level: int = 0) -> list[dict]:
    """
    Flatten a BOM tree into a list of items with their hierarchy.

    Args:
        tree_node: BOM tree node from get_bom_tree endpoint
        parent_path: Path of parent items (for indentation/hierarchy display)
        level: Current depth level

    Returns:
        List of dicts with: item, quantity, level, path
    """
    items = []

    # Add current item
    item_number = tree_node["item"]["item_number"]
    current_path = f"{parent_path}/{item_number}" if parent_path else item_number

    items.append({
        "item": tree_node["item"],
        "quantity": tree_node["quantity"],
        "level": level,
        "path": current_path
    })

    # Recursively add children
    for child in tree_node.get("children", []):
        items.extend(flatten_bom_tree(child, current_path, level + 1))

    return items


def generate_bom_csv(tree_node: dict) -> str:
    """
    Generate a CSV string from a BOM tree.

    Args:
        tree_node: BOM tree node from get_bom_tree endpoint

    Returns:
        CSV string with BOM data
    """
    flattened = flatten_bom_tree(tree_node)

    output = StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "Level",
        "Item Number",
        "Name",
        "Quantity",
        "Material",
        "Thickness",
        "Mass",
        "Revision",
        "Lifecycle State"
    ])

    # Data rows
    for entry in flattened:
        item = entry["item"]
        indent = "  " * entry["level"]  # Indent based on level

        writer.writerow([
            entry["level"],
            f"{indent}{item.get('item_number', '')}",
            item.get("name", ""),
            entry["quantity"],
            item.get("material", ""),
            item.get("thickness", ""),
            item.get("mass", ""),
            item.get("revision", ""),
            item.get("lifecycle_state", "")
        ])

    return output.getvalue()


def auto_create_item(supabase, item_number: str) -> dict:
    """Create a new item record for a recognized item number pattern."""
    item_data = {
        "item_number": item_number,
        "revision": "A",
        "iteration": 1,
        "lifecycle_state": "Design",
    }

    # Set supplier flag for mmc/spn prefixes
    if item_number.startswith("mmc"):
        item_data["is_supplier_part"] = True
        item_data["supplier_name"] = "McMaster-Carr"
    elif item_number.startswith("spn"):
        item_data["is_supplier_part"] = True

    result = supabase.table("items").insert(item_data).execute()
    return result.data[0]


@router.get("", response_model=list[FileInfo])
async def list_files(
    item_id: Optional[UUID] = None,
    file_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """List files with optional filtering."""
    supabase = get_supabase_admin()

    query = supabase.table("files").select("*")

    if item_id:
        query = query.eq("item_id", str(item_id))
    if file_type:
        query = query.eq("file_type", file_type)

    query = query.order("created_at", desc=True).range(offset, offset + limit - 1)

    result = query.execute()
    return result.data


@router.get("/fingerprint/{item_number}")
async def get_step_fingerprint(item_number: str):
    """
    Get the stored STEP fingerprint for an item.

    Used by upload clients to check if a file has changed before uploading.
    Returns the cached fingerprint if available, or null if no STEP file exists.
    """
    supabase = get_supabase_admin()

    clean_item_number = item_number.strip().lower()

    # Get item
    item_result = supabase.table("items").select("id, revision").eq(
        "item_number", clean_item_number
    ).limit(1).execute()

    if not item_result.data:
        return {
            "item_number": clean_item_number,
            "exists": False,
            "fingerprint": None,
            "message": "Item not found"
        }

    item_id = item_result.data[0]["id"]
    item_revision = item_result.data[0].get("revision", "A")

    # Get STEP file with fingerprint
    file_result = supabase.table("files").select(
        "id, file_name, step_fingerprint, revision, file_path"
    ).eq("item_id", item_id).or_(
        "file_type.eq.STP,file_type.eq.STEP"
    ).limit(1).execute()

    if not file_result.data:
        return {
            "item_number": clean_item_number,
            "exists": True,
            "has_step_file": False,
            "fingerprint": None,
            "revision": item_revision,
            "message": "No STEP file for this item"
        }

    file_record = file_result.data[0]
    stored_fp = file_record.get("step_fingerprint")

    # If no cached fingerprint, try to compute it
    if not stored_fp and file_record.get("file_path"):
        from ..services.step_compare import parse_step_fingerprint

        file_path = file_record["file_path"]
        parts = file_path.split("/", 1)
        bucket = parts[0] if len(parts) == 2 else "pdm-files"
        storage_path = parts[1] if len(parts) == 2 else file_path

        try:
            content = supabase.storage.from_(bucket).download(storage_path)
            fp = parse_step_fingerprint(content)
            stored_fp = fp.to_dict()

            # Cache it for future
            supabase.table("files").update({
                "step_fingerprint": stored_fp
            }).eq("id", file_record["id"]).execute()
        except Exception as e:
            return {
                "item_number": clean_item_number,
                "exists": True,
                "has_step_file": True,
                "fingerprint": None,
                "revision": file_record.get("revision", item_revision),
                "error": f"Could not compute fingerprint: {str(e)}"
            }

    return {
        "item_number": clean_item_number,
        "exists": True,
        "has_step_file": True,
        "fingerprint": stored_fp,
        "revision": file_record.get("revision", item_revision),
        "file_name": file_record.get("file_name")
    }


@router.get("/{file_id}", response_model=FileInfo)
async def get_file(file_id: UUID):
    """Get file metadata by ID."""
    supabase = get_supabase_admin()

    try:
        result = supabase.table("files").select("*").eq("id", str(file_id)).single().execute()
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")

    if not result.data:
        raise HTTPException(status_code=404, detail="File not found")

    return result.data


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    item_number: str = Form(...),
    revision: Optional[str] = Form(None),
    skip_comparison: bool = Form(False),
):
    """Upload a file and associate it with an item.

    Uses admin client to bypass RLS for internal upload service.

    For STEP files, automatically compares fingerprints and skips upload
    if file is geometrically identical to existing version.
    Set skip_comparison=true to force upload without comparison.
    """
    supabase = get_supabase_admin()

    clean_item_number = item_number.strip().lower()
    print(f"Upload request: item_number='{clean_item_number}', filename={file.filename}")

    # Get item ID (use limit(1) instead of single() to avoid error on 0 rows)
    item_result = supabase.table("items").select("id, revision").eq("item_number", clean_item_number).limit(1).execute()

    if not item_result.data or len(item_result.data) == 0:
        # Auto-create item if it matches a known naming convention
        if is_valid_item_number(clean_item_number):
            print(f"Auto-creating item: '{clean_item_number}'")
            item_data = auto_create_item(supabase, clean_item_number)
        else:
            print(f"Item not found and name doesn't match conventions: '{clean_item_number}'")
            raise HTTPException(status_code=404, detail=f"Item {clean_item_number} not found and doesn't match naming conventions")
    else:
        item_data = item_result.data[0]

    item_id = item_data["id"]
    file_revision = revision or item_data.get("revision", "A")

    # Read file content
    content = await file.read()

    # Determine file type
    file_type = get_file_type(file.filename)

    # Normalize filename (strip redundant suffixes like _dxf.dxf -> .dxf)
    normalized_filename = normalize_filename(file.filename, clean_item_number)
    if normalized_filename != file.filename:
        print(f"Normalized filename: {file.filename} -> {normalized_filename}")

    # Check if file record exists to determine iteration BEFORE stamping
    existing = supabase.table("files").select("id, iteration, step_fingerprint, file_path").eq("item_id", item_id).eq("file_name", normalized_filename).execute()

    # STEP file fingerprint comparison - skip upload if identical
    if file_type == "STEP" and not skip_comparison and existing.data:
        from ..services.step_compare import parse_step_fingerprint, StepFingerprint

        new_fp = parse_step_fingerprint(content, len(content))
        stored_fp_dict = existing.data[0].get("step_fingerprint")

        if stored_fp_dict:
            # Use cached fingerprint (fast path)
            entity_counts = stored_fp_dict.get("entity_counts", {})
            stored_fp = StepFingerprint()
            stored_fp.cartesian_points = entity_counts.get("cartesian_points", 0)
            stored_fp.directions = entity_counts.get("directions", 0)
            stored_fp.vectors = entity_counts.get("vectors", 0)
            stored_fp.lines = entity_counts.get("lines", 0)
            stored_fp.circles = entity_counts.get("circles", 0)
            stored_fp.planes = entity_counts.get("planes", 0)
            stored_fp.advanced_faces = entity_counts.get("advanced_faces", 0)
            stored_fp.closed_shells = entity_counts.get("closed_shells", 0)
            stored_fp.manifold_solids = entity_counts.get("manifold_solids", 0)
            stored_fp.total_entities = entity_counts.get("total", 0)

            bbox = stored_fp_dict.get("bounding_box", {})
            mins = bbox.get("min", [0, 0, 0])
            maxs = bbox.get("max", [0, 0, 0])
            stored_fp.min_x, stored_fp.min_y, stored_fp.min_z = mins
            stored_fp.max_x, stored_fp.max_y, stored_fp.max_z = maxs

            if stored_fp.matches(new_fp):
                print(f"STEP fingerprint match - skipping upload for {clean_item_number}")
                return {
                    "skipped": True,
                    "reason": "fingerprint_match",
                    "message": f"File identical to stored version (Rev {file_revision})",
                    "item_number": clean_item_number,
                    "id": existing.data[0]["id"]
                }
        else:
            # No cached fingerprint - download existing and compare
            file_path = existing.data[0].get("file_path")
            if file_path:
                parts = file_path.split("/", 1)
                bucket_name = parts[0] if len(parts) == 2 else "pdm-files"
                storage_path_existing = parts[1] if len(parts) == 2 else file_path

                try:
                    existing_content = supabase.storage.from_(bucket_name).download(storage_path_existing)
                    existing_fp = parse_step_fingerprint(existing_content)

                    # Cache the fingerprint for future comparisons
                    supabase.table("files").update({
                        "step_fingerprint": existing_fp.to_dict()
                    }).eq("id", existing.data[0]["id"]).execute()

                    if existing_fp.matches(new_fp):
                        print(f"STEP fingerprint match (after download) - skipping upload for {clean_item_number}")
                        return {
                            "skipped": True,
                            "reason": "fingerprint_match",
                            "message": f"File identical to stored version (Rev {file_revision})",
                            "item_number": clean_item_number,
                            "id": existing.data[0]["id"]
                        }
                except Exception as e:
                    print(f"Warning: Could not compare existing STEP file: {e}")

        # If we get here for a STEP file with existing data, the file is DIFFERENT
        # Bump the item's revision
        current_rev = item_data.get("revision", "A")
        new_rev = get_next_rev(current_rev)
        print(f"STEP file changed for {clean_item_number}: bumping revision {current_rev} -> {new_rev}")

        # Update item revision
        supabase.table("items").update({
            "revision": new_rev
        }).eq("id", item_id).execute()

        # Use new revision for the file
        file_revision = new_rev

    if existing.data:
        new_iteration = existing.data[0]["iteration"] + 1
        existing_file_id = existing.data[0]["id"]
    else:
        new_iteration = 1
        existing_file_id = None

    # Stamp PDFs with upload date and revision/iteration
    if file_type == "PDF":
        print(f"Stamping PDF: {file.filename} (Rev {file_revision} / Iter {new_iteration})", flush=True)
        content = stamp_pdf_upload_date(content, file_revision, new_iteration)

    file_size = len(content)

    # Upload to Supabase Storage
    # Use pdm-files bucket for all uploads via this service
    bucket = "pdm-files"
    path_in_bucket = f"{clean_item_number}/{normalized_filename}"
    storage_path = f"{bucket}/{path_in_bucket}"  # Full path including bucket for file_path column

    try:
        storage_result = supabase.storage.from_(bucket).upload(
            path_in_bucket,
            content,
            file_options={"content-type": file.content_type or "application/octet-stream"}
        )
    except Exception as e:
        # If file exists, update it
        if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
            supabase.storage.from_(bucket).update(
                path_in_bucket,
                content,
                file_options={"content-type": file.content_type or "application/octet-stream"}
            )
        else:
            raise HTTPException(status_code=500, detail=f"Storage error: {str(e)}")

    # Compute fingerprint for STEP files
    step_fingerprint = None
    if file_type == "STEP":
        from ..services.step_compare import parse_step_fingerprint
        fp = parse_step_fingerprint(content, len(content))
        step_fingerprint = fp.to_dict()

    # Update or create file record
    if existing_file_id:
        # Update existing file record
        update_data = {
            "file_path": storage_path,
            "file_size": file_size,
            "revision": file_revision,
            "iteration": new_iteration,
        }
        if step_fingerprint:
            update_data["step_fingerprint"] = step_fingerprint
        result = supabase.table("files").update(update_data).eq("id", existing_file_id).execute()
    else:
        # Create new file record
        file_data = {
            "item_id": item_id,
            "file_type": file_type,
            "file_name": normalized_filename,
            "file_path": storage_path,
            "file_size": file_size,
            "revision": file_revision,
            "iteration": 1,
        }
        if step_fingerprint:
            file_data["step_fingerprint"] = step_fingerprint
        result = supabase.table("files").insert(file_data).execute()

    file_record = result.data[0]

    # Auto-queue DXF generation for STEP files when item has needs_dxf flag
    if file_type == "STEP":
        # Check if item has needs_dxf flag set
        item_check = supabase.table("items").select("needs_dxf").eq("id", item_id).single().execute()
        if item_check.data and item_check.data.get("needs_dxf", False):
            print(f"Auto-queuing DXF generation for {clean_item_number}", flush=True)
            supabase.table("work_queue").insert({
                "item_id": item_id,
                "file_id": file_record["id"],
                "task_type": "GENERATE_DXF",
                "status": "pending",
                "payload": {"item_number": clean_item_number, "auto_queued": True}
            }).execute()

    return file_record


@router.get("/{file_id}/download")
async def get_download_url(file_id: UUID):
    """Get a signed download URL for a file."""
    supabase = get_supabase_admin()

    try:
        file_result = supabase.table("files").select("file_path, file_name").eq("id", str(file_id)).single().execute()
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")

    if not file_result.data:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = file_result.data["file_path"]

    if not file_path:
        raise HTTPException(status_code=404, detail="File not in storage")

    # Parse bucket name from file_path (e.g. "pdm-cad/stp01900/A/1/file.prt" -> bucket="pdm-cad", path="stp01900/A/1/file.prt")
    parts = file_path.split("/", 1)
    if len(parts) == 2:
        bucket = parts[0]
        storage_path = parts[1]
    else:
        bucket = "pdm-files"
        storage_path = file_path

    # Create signed URL (valid for 1 hour)
    try:
        url_result = supabase.storage.from_(bucket).create_signed_url(storage_path, 3600)
        return {
            "url": url_result["signedURL"],
            "filename": file_result.data["file_name"],
            "expires_in": 3600
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not generate download URL: {str(e)}")


@router.delete("/{file_id}")
async def delete_file(file_id: UUID):
    """Delete a file."""
    supabase = get_supabase_admin()

    try:
        file_result = supabase.table("files").select("file_path").eq("id", str(file_id)).single().execute()
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")

    if not file_result.data:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = file_result.data["file_path"]

    # Delete from storage if path exists
    if file_path:
        try:
            parts = file_path.split("/", 1)
            if len(parts) == 2:
                bucket = parts[0]
                storage_path = parts[1]
            else:
                bucket = "pdm-files"
                storage_path = file_path
            supabase.storage.from_(bucket).remove([storage_path])
        except Exception:
            pass  # Continue even if storage delete fails

    # Delete database record
    supabase.table("files").delete().eq("id", str(file_id)).execute()

    return {"message": "File deleted"}


@router.get("/assembly/{item_number}/download")
async def download_assembly_package(item_number: str):
    """
    Download assembly as a ZIP package containing:
    - Assembly STEP file
    - All child part STEP files (organized in parts/ folder)
    - BOM CSV file with hierarchy
    - README with package information

    This endpoint is useful for sharing complete assemblies without
    requiring users to download individual parts separately.
    """
    supabase = get_supabase_admin()

    clean_item_number = item_number.strip().lower()

    # 1. Get assembly item
    try:
        item_result = supabase.table("items").select("*").eq("item_number", clean_item_number).single().execute()
    except Exception:
        raise HTTPException(status_code=404, detail=f"Item {clean_item_number} not found")

    if not item_result.data:
        raise HTTPException(status_code=404, detail=f"Item {clean_item_number} not found")

    assembly_item = item_result.data

    # 2. Get BOM tree (recursive)
    # Inline BOM tree retrieval to avoid circular dependency
    def build_bom_tree(item_id: str, depth: int = 0, max_depth: int = 10) -> dict:
        """Recursively build BOM tree."""
        if depth >= max_depth:
            return {"item": None, "quantity": 0, "children": []}

        # Get item details
        item_result = supabase.table("items").select("*").eq("id", item_id).execute()
        if not item_result.data:
            return {"item": None, "quantity": 0, "children": []}

        item = item_result.data[0]

        # Get children
        bom_result = supabase.table("bom").select("child_item_id, quantity").eq("parent_item_id", item_id).execute()

        children = []
        for entry in bom_result.data:
            child_tree = build_bom_tree(entry["child_item_id"], depth + 1, max_depth)
            if child_tree["item"]:
                child_tree["quantity"] = entry["quantity"]
                children.append(child_tree)

        return {
            "item": item,
            "quantity": 1,
            "children": children
        }

    bom_tree = build_bom_tree(assembly_item["id"])

    # Check if this item has a BOM (is an assembly)
    if not bom_tree["children"]:
        raise HTTPException(
            status_code=400,
            detail=f"Item {clean_item_number} has no BOM (not an assembly). Use regular file download instead."
        )

    # 3. Collect all STEP files (assembly + children)
    files_to_package = []

    # Get all items from flattened tree
    flattened_items = flatten_bom_tree(bom_tree)

    for entry in flattened_items:
        item = entry["item"]
        item_id = item["id"]
        item_num = item["item_number"]
        level = entry["level"]

        # Get latest STEP file for this item
        step_result = supabase.table("files").select("*").eq("item_id", item_id).eq("file_type", "STEP").order("created_at", desc=True).limit(1).execute()

        if step_result.data:
            step_file = step_result.data[0]
            # Determine path in ZIP
            if level == 0:
                # Assembly goes to root
                zip_path = f"{item_num}.step"
            else:
                # Parts go to parts/ folder
                zip_path = f"parts/{item_num}.step"

            files_to_package.append({
                "zip_path": zip_path,
                "file_path": step_file["file_path"],
                "item_number": item_num,
                "level": level
            })

    if not files_to_package:
        raise HTTPException(
            status_code=404,
            detail=f"No STEP files found for assembly {clean_item_number} or its components"
        )

    # 4. Create ZIP package in memory
    zip_buffer = BytesIO()

    try:
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Add STEP files
            for file_info in files_to_package:
                file_path = file_info["file_path"]

                # Parse bucket and path
                parts = file_path.split("/", 1)
                if len(parts) == 2:
                    bucket = parts[0]
                    storage_path = parts[1]
                else:
                    bucket = "pdm-files"
                    storage_path = file_path

                # Download from Supabase Storage
                try:
                    file_bytes = supabase.storage.from_(bucket).download(storage_path)
                    zf.writestr(file_info["zip_path"], file_bytes)
                except Exception as e:
                    print(f"Warning: Could not download {file_path}: {e}")
                    # Continue with other files even if one fails

            # Add BOM CSV
            bom_csv = generate_bom_csv(bom_tree)
            zf.writestr("bom.csv", bom_csv)

            # Add README
            total_parts = len([f for f in files_to_package if f["level"] > 0])
            readme_content = f"""Assembly Package: {clean_item_number}
Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

Assembly: {assembly_item.get('name', clean_item_number)}
Revision: {assembly_item.get('revision', 'A')}
Lifecycle State: {assembly_item.get('lifecycle_state', 'Unknown')}

Contents:
- {clean_item_number}.step (assembly - {files_to_package[0]['zip_path'] if files_to_package else 'NOT FOUND'})
- parts/*.step ({total_parts} component{'s' if total_parts != 1 else ''})
- bom.csv (bill of materials with hierarchy)

Files Included:
"""
            for file_info in files_to_package:
                readme_content += f"  - {file_info['zip_path']} (Level {file_info['level']})\n"

            readme_content += f"""
Import Instructions:
1. Extract all files to a folder
2. Import {clean_item_number}.step into your CAD system
3. If your CAD system supports external references, parts will link automatically
4. Otherwise, manually import parts from the parts/ folder as needed
5. Reference bom.csv for component quantities and properties

PDM-Web System
Generated by assembly package download feature
"""
            zf.writestr("README.txt", readme_content)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating assembly package: {str(e)}")

    # 5. Return as streaming response
    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={clean_item_number}_assembly.zip"
        }
    )


@router.post("/compare-step/{item_number}")
async def compare_step_file(
    item_number: str,
    file: UploadFile = File(...)
):
    """
    Compare an uploaded STEP file against the existing one in PDM.

    Returns fingerprint comparison showing if files are geometrically equivalent.
    Use this before uploading to check if a file actually changed.

    Returns:
        - match: bool - True if files are geometrically equivalent
        - differences: dict - What changed (entity counts, bounding box)
        - fingerprints: dict - Full fingerprint data for both files
    """
    from ..services.step_compare import parse_step_fingerprint, StepFingerprint

    supabase = get_supabase_admin()

    # Normalize item number
    clean_item_number = item_number.lower().strip()

    # Get existing STEP file for this item
    item_result = supabase.table("items").select("id").eq(
        "item_number", clean_item_number
    ).execute()

    if not item_result.data:
        raise HTTPException(status_code=404, detail=f"Item {clean_item_number} not found")

    item_id = item_result.data[0]["id"]

    # Find existing STEP file
    file_result = supabase.table("files").select("id, file_path, file_name").eq(
        "item_id", item_id
    ).or_("file_type.eq.STP,file_type.eq.STEP").execute()

    if not file_result.data:
        # No existing STEP file - return fingerprint of uploaded file only
        content = await file.read()
        new_fp = parse_step_fingerprint(content, len(content))
        return {
            "match": False,
            "reason": "no_existing_file",
            "message": f"No existing STEP file for {clean_item_number}",
            "new_fingerprint": new_fp.to_dict(),
            "existing_fingerprint": None,
            "differences": {}
        }

    existing_file = file_result.data[0]
    file_path = existing_file["file_path"]

    # Download existing file from storage
    parts = file_path.split("/", 1)
    if len(parts) == 2:
        bucket = parts[0]
        storage_path = parts[1]
    else:
        bucket = "pdm-files"
        storage_path = file_path

    try:
        existing_content = supabase.storage.from_(bucket).download(storage_path)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Could not download existing file: {str(e)}"
        )

    # Parse both fingerprints
    new_content = await file.read()
    existing_fp = parse_step_fingerprint(existing_content, len(existing_content))
    new_fp = parse_step_fingerprint(new_content, len(new_content))

    # Compare
    is_match = existing_fp.matches(new_fp)
    differences = existing_fp.diff(new_fp)

    return {
        "match": is_match,
        "item_number": clean_item_number,
        "existing_file": existing_file["file_name"],
        "uploaded_file": file.filename,
        "existing_fingerprint": existing_fp.to_dict(),
        "new_fingerprint": new_fp.to_dict(),
        "differences": differences,
        "summary": "Files are geometrically equivalent" if is_match else f"Files differ: {list(differences.keys())}"
    }


@router.post("/compare-step-batch")
async def compare_step_files_batch(
    files: list[UploadFile] = File(...)
):
    """
    Compare multiple STEP files against existing ones in PDM.

    Expects files named like: csp00110.step, csp00120.step, etc.
    Returns comparison results for each file.
    """
    from ..services.step_compare import parse_step_fingerprint

    supabase = get_supabase_admin()
    results = []

    for upload_file in files:
        # Extract item number from filename
        filename = upload_file.filename or ""
        match = re.match(r'^([a-z]{3}\d+)', filename.lower())
        if not match:
            results.append({
                "filename": filename,
                "error": "Could not extract item number from filename"
            })
            continue

        item_number = match.group(1)

        # Get existing file
        item_result = supabase.table("items").select("id").eq(
            "item_number", item_number
        ).execute()

        if not item_result.data:
            results.append({
                "filename": filename,
                "item_number": item_number,
                "match": False,
                "reason": "item_not_found"
            })
            continue

        item_id = item_result.data[0]["id"]

        file_result = supabase.table("files").select("file_path").eq(
            "item_id", item_id
        ).or_("file_type.eq.STP,file_type.eq.STEP").execute()

        if not file_result.data:
            new_content = await upload_file.read()
            await upload_file.seek(0)
            new_fp = parse_step_fingerprint(new_content)
            results.append({
                "filename": filename,
                "item_number": item_number,
                "match": False,
                "reason": "no_existing_file",
                "new_fingerprint": new_fp.to_dict()
            })
            continue

        # Download and compare
        file_path = file_result.data[0]["file_path"]
        parts = file_path.split("/", 1)
        bucket = parts[0] if len(parts) == 2 else "pdm-files"
        storage_path = parts[1] if len(parts) == 2 else file_path

        try:
            existing_content = supabase.storage.from_(bucket).download(storage_path)
            new_content = await upload_file.read()
            await upload_file.seek(0)

            existing_fp = parse_step_fingerprint(existing_content)
            new_fp = parse_step_fingerprint(new_content)

            is_match = existing_fp.matches(new_fp)
            differences = existing_fp.diff(new_fp)

            results.append({
                "filename": filename,
                "item_number": item_number,
                "match": is_match,
                "differences": differences if not is_match else {}
            })
        except Exception as e:
            results.append({
                "filename": filename,
                "item_number": item_number,
                "error": str(e)
            })

    # Summary
    matched = sum(1 for r in results if r.get("match"))
    changed = sum(1 for r in results if not r.get("match") and "error" not in r)
    errors = sum(1 for r in results if "error" in r)

    return {
        "summary": {
            "total": len(results),
            "matched": matched,
            "changed": changed,
            "errors": errors
        },
        "results": results
    }
