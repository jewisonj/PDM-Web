"""Shared links API - permanent public links for project documents.

Documents (build books, tracker sheets, print packets, design books) are
copied into the public `shared` bucket, which serves permanent public URLs -
no expiring signed links. The shared_links table is the registry the UI uses
to list, copy, and revoke links. Revoking deletes the object, which kills
the URL.

Note: uploads are subject to the Supabase project-wide upload size limit
(~50MB unless raised in Dashboard -> Project Settings -> Storage). Files
already in storage are within it by definition; oversized browser uploads
get a clear error instead of a cryptic 413.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from ..config import get_settings
from ..services.supabase import get_supabase_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/share", tags=["share"])
settings = get_settings()

SHARED_BUCKET = "shared"
VALID_KINDS = {"build_book", "tracker", "print_packet", "design_book", "other"}

# Stay under the ~50MB project-wide upload limit with margin (matches the
# build book's own storage guard).
MAX_SHARE_BYTES = 45 * 1024 * 1024

SIZE_LIMIT_MESSAGE = (
    "This PDF is larger than the Supabase project upload limit (~50MB). "
    "Options: raise the limit in Supabase Dashboard -> Project Settings -> "
    "Storage (paid plans), or share the smaller section print sets instead."
)


def _public_url(storage_path: str) -> str:
    return (
        f"{settings.supabase_url}/storage/v1/object/public/"
        f"{SHARED_BUCKET}/{quote(storage_path)}"
    )


def _safe_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_. " else "_" for ch in name)
    return cleaned.strip().replace(" ", "_")[:120] or "document.pdf"


def _register_link(kind: str, project_code: Optional[str], title: str,
                   file_name: str, storage_path: str, size_bytes: int) -> dict:
    """Upsert the shared_links row for a storage path (stable link on re-share)."""
    supabase = get_supabase_admin()

    row = {
        "kind": kind,
        "project_code": project_code,
        "title": title,
        "file_name": file_name,
        "storage_path": storage_path,
        "public_url": _public_url(storage_path),
        "size_bytes": size_bytes,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    result = supabase.table("shared_links").upsert(
        row, on_conflict="storage_path"
    ).execute()

    return result.data[0] if result.data else row


def _upload_to_shared(storage_path: str, content: bytes) -> None:
    supabase = get_supabase_admin()

    if len(content) > MAX_SHARE_BYTES:
        raise HTTPException(status_code=413, detail=SIZE_LIMIT_MESSAGE)

    try:
        supabase.storage.from_(SHARED_BUCKET).remove([storage_path])
    except Exception:
        pass

    try:
        supabase.storage.from_(SHARED_BUCKET).upload(
            storage_path, content,
            file_options={"content-type": "application/pdf", "upsert": "true"}
        )
    except Exception as e:
        msg = str(e)
        if "413" in msg or "exceeded" in msg.lower() or "too large" in msg.lower():
            raise HTTPException(status_code=413, detail=SIZE_LIMIT_MESSAGE)
        raise HTTPException(status_code=500, detail=f"Upload failed: {msg}")


# =============================================================================
# Endpoints
# =============================================================================

@router.post("")
async def share_uploaded_pdf(
    file: UploadFile = File(...),
    kind: str = Form("other"),
    project_code: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
):
    """
    Upload a PDF (e.g. a browser-printed tracker sheet or build book) and get
    a permanent public link.
    """
    if kind not in VALID_KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of {sorted(VALID_KINDS)}")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    if not content[:5] == b"%PDF-":
        raise HTTPException(status_code=400, detail="Only PDF files can be shared")

    file_name = _safe_name(file.filename or "document.pdf")
    folder = _safe_name(project_code) if project_code else "general"
    storage_path = f"{kind}/{folder}/{file_name}"

    _upload_to_shared(storage_path, content)

    link = _register_link(
        kind=kind,
        project_code=project_code,
        title=title or file_name,
        file_name=file_name,
        storage_path=storage_path,
        size_bytes=len(content),
    )
    return link


class ShareFromStorageRequest(BaseModel):
    bucket: str
    path: str
    kind: str = "other"
    project_code: Optional[str] = None
    title: Optional[str] = None


@router.post("/from-storage")
async def share_from_storage(request: ShareFromStorageRequest):
    """
    Share a file that already lives in Supabase Storage (print packet, stored
    build book, design book) by copying it into the public bucket.
    """
    if request.kind not in VALID_KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of {sorted(VALID_KINDS)}")

    supabase = get_supabase_admin()

    try:
        content = supabase.storage.from_(request.bucket).download(request.path)
    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail=f"Could not read {request.bucket}/{request.path}: {e}"
        )

    file_name = _safe_name(request.path.split("/")[-1])
    folder = _safe_name(request.project_code) if request.project_code else "general"
    storage_path = f"{request.kind}/{folder}/{file_name}"

    _upload_to_shared(storage_path, content)

    link = _register_link(
        kind=request.kind,
        project_code=request.project_code,
        title=request.title or file_name,
        file_name=file_name,
        storage_path=storage_path,
        size_bytes=len(content),
    )
    return link


@router.post("/print-packet/{project_id}")
async def share_print_packet(project_id: UUID):
    """Share a project's existing print packet with a permanent public link."""
    supabase = get_supabase_admin()

    try:
        project = supabase.table("mrp_projects").select(
            "project_code, print_packet_path"
        ).eq("id", str(project_id)).single().execute()
    except Exception:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.data or not project.data.get("print_packet_path"):
        raise HTTPException(
            status_code=404,
            detail="No print packet has been generated for this project yet"
        )

    request = ShareFromStorageRequest(
        bucket="print-packets",
        path=project.data["print_packet_path"],
        kind="print_packet",
        project_code=project.data["project_code"],
        title=f"{project.data['project_code']} print packet",
    )
    return await share_from_storage(request)


@router.get("")
async def list_shared_links(project_code: Optional[str] = None):
    """List shared links, optionally filtered by project."""
    supabase = get_supabase_admin()

    query = supabase.table("shared_links").select("*")
    if project_code:
        query = query.eq("project_code", project_code)

    result = query.order("updated_at", desc=True).limit(100).execute()
    return {"links": result.data or []}


@router.delete("/{link_id}")
async def revoke_shared_link(link_id: UUID):
    """Revoke a shared link: delete the public object (kills the URL) and the row."""
    supabase = get_supabase_admin()

    try:
        link = supabase.table("shared_links").select("storage_path").eq(
            "id", str(link_id)
        ).single().execute()
    except Exception:
        raise HTTPException(status_code=404, detail="Link not found")

    if not link.data:
        raise HTTPException(status_code=404, detail="Link not found")

    try:
        supabase.storage.from_(SHARED_BUCKET).remove([link.data["storage_path"]])
    except Exception as e:
        logger.warning(f"Could not remove shared object: {e}")

    supabase.table("shared_links").delete().eq("id", str(link_id)).execute()
    return {"message": "Link revoked"}
