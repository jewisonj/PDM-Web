"""Files API routes."""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Optional
from uuid import UUID

from ..services.supabase import get_supabase_client, get_supabase_admin
from ..models.schemas import FileInfo, FileCreate

router = APIRouter(prefix="/files", tags=["files"])


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
    }
    return type_map.get(ext, "OTHER")


@router.get("", response_model=list[FileInfo])
async def list_files(
    item_id: Optional[UUID] = None,
    file_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """List files with optional filtering."""
    supabase = get_supabase_client()

    query = supabase.table("files").select("*")

    if item_id:
        query = query.eq("item_id", str(item_id))
    if file_type:
        query = query.eq("file_type", file_type)

    query = query.order("created_at", desc=True).range(offset, offset + limit - 1)

    result = query.execute()
    return result.data


@router.get("/{file_id}", response_model=FileInfo)
async def get_file(file_id: UUID):
    """Get file metadata by ID."""
    supabase = get_supabase_client()

    result = supabase.table("files").select("*").eq("id", str(file_id)).single().execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="File not found")

    return result.data


@router.post("/upload", response_model=FileInfo)
async def upload_file(
    file: UploadFile = File(...),
    item_number: str = Form(...),
    revision: Optional[str] = Form(None),
):
    """Upload a file and associate it with an item.

    Uses admin client to bypass RLS for internal upload service.
    """
    supabase = get_supabase_admin()

    clean_item_number = item_number.strip().lower()
    print(f"Upload request: item_number='{clean_item_number}', filename={file.filename}")

    # Get item ID (use limit(1) instead of single() to avoid error on 0 rows)
    item_result = supabase.table("items").select("id, revision").eq("item_number", clean_item_number).limit(1).execute()

    if not item_result.data or len(item_result.data) == 0:
        print(f"Item not found: '{clean_item_number}'")
        raise HTTPException(status_code=404, detail=f"Item {clean_item_number} not found")

    item_data = item_result.data[0]
    item_id = item_data["id"]
    file_revision = revision or item_data["revision"]

    # Read file content
    content = await file.read()
    file_size = len(content)

    # Determine file type
    file_type = get_file_type(file.filename)

    # Upload to Supabase Storage
    # Use pdm-files bucket for all uploads via this service
    bucket = "pdm-files"
    path_in_bucket = f"{item_number.lower()}/{file.filename}"
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

    # Check if file record exists
    existing = supabase.table("files").select("id, iteration").eq("item_id", item_id).eq("file_name", file.filename).execute()

    if existing.data:
        # Update existing file record
        new_iteration = existing.data[0]["iteration"] + 1
        result = supabase.table("files").update({
            "file_path": storage_path,
            "file_size": file_size,
            "revision": file_revision,
            "iteration": new_iteration,
        }).eq("id", existing.data[0]["id"]).execute()
    else:
        # Create new file record
        file_data = {
            "item_id": item_id,
            "file_type": file_type,
            "file_name": file.filename,
            "file_path": storage_path,
            "file_size": file_size,
            "revision": file_revision,
            "iteration": 1,
        }
        result = supabase.table("files").insert(file_data).execute()

    file_record = result.data[0]

    # Auto-queue DXF/SVG generation for STEP files (only parts, 3rd char == 'p')
    if file_type == "STEP":
        is_part = len(clean_item_number) >= 3 and clean_item_number[2] == 'p'
        if is_part:
            file_id_for_task = file_record["id"]
            for task_type in ["GENERATE_DXF", "GENERATE_SVG"]:
                try:
                    supabase.table("work_queue").insert({
                        "item_id": item_id,
                        "file_id": file_id_for_task,
                        "task_type": task_type,
                        "payload": {"file_path": storage_path, "item_number": clean_item_number},
                        "status": "pending"
                    }).execute()
                    print(f"Queued {task_type} for {clean_item_number}")
                except Exception as e:
                    print(f"Warning: Failed to queue {task_type} for {clean_item_number}: {e}")

    return file_record


@router.get("/{file_id}/download")
async def get_download_url(file_id: UUID):
    """Get a signed download URL for a file."""
    supabase = get_supabase_client()

    # Get file record
    file_result = supabase.table("files").select("file_path, file_name").eq("id", str(file_id)).single().execute()

    if not file_result.data:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = file_result.data["file_path"]

    if not file_path:
        raise HTTPException(status_code=404, detail="File not in storage")

    # Create signed URL (valid for 1 hour)
    try:
        url_result = supabase.storage.from_("pdm-files").create_signed_url(file_path, 3600)
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
    supabase = get_supabase_client()

    # Get file path first
    file_result = supabase.table("files").select("file_path").eq("id", str(file_id)).single().execute()

    if not file_result.data:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = file_result.data["file_path"]

    # Delete from storage if path exists
    if file_path:
        try:
            supabase.storage.from_("pdm-files").remove([file_path])
        except Exception:
            pass  # Continue even if storage delete fails

    # Delete database record
    supabase.table("files").delete().eq("id", str(file_id)).execute()

    return {"message": "File deleted"}
