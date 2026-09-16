"""Shop Notes API - the Shop Companion app.

Shop-floor workers (on their own phones) pick a project, optionally the assembly
and part they are working on, type/dictate a note and attach photos. Engineering
reviews the notes on /mrp/shop-notes.

Auth:
  * Workers: shared PIN -> long-lived "shop" JWT (see services/shop_auth.py).
  * Reviewers: normal Supabase session token (staff login).
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel

from ..services.shop_auth import create_shop_token, decode_shop_token, verify_pin
from ..services.supabase import get_supabase_admin, get_supabase_client

router = APIRouter(prefix="/shop-notes", tags=["shop-notes"])

BUCKET = "shop-note-photos"
MAX_PHOTO_BYTES = 12 * 1024 * 1024
MAX_PHOTOS_PER_NOTE = 10
ALLOWED_MIME = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/heic", "image/heif"}
STATUSES = ("new", "reviewed", "resolved")
SIGNED_URL_SECONDS = 3600


# ---------------------------------------------------------------------------
# Auth dependencies
# ---------------------------------------------------------------------------

def _bearer(authorization: Optional[str]) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return authorization.split(" ", 1)[1].strip()


def _is_staff_token(token: str) -> bool:
    """True if the token is a valid Supabase session for a staff user."""
    try:
        res = get_supabase_client().auth.get_user(token)
        return bool(res and res.user)
    except Exception:
        return False


async def require_shop_or_staff(authorization: Optional[str] = Header(None)) -> dict:
    """Accept a shop device token or a staff Supabase token."""
    token = _bearer(authorization)
    payload = decode_shop_token(token)
    if payload:
        return {"kind": "shop"}
    if _is_staff_token(token):
        return {"kind": "staff"}
    raise HTTPException(status_code=401, detail="Invalid or expired token")


async def require_staff(authorization: Optional[str] = Header(None)) -> dict:
    """Reviewer endpoints: staff Supabase session only."""
    token = _bearer(authorization)
    if _is_staff_token(token):
        return {"kind": "staff"}
    raise HTTPException(status_code=401, detail="Staff login required")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class PinLogin(BaseModel):
    pin: str


class NoteUpdate(BaseModel):
    status: Optional[str] = None
    note: Optional[str] = None
    project_id: Optional[UUID] = None
    assembly_item_id: Optional[UUID] = None
    part_item_id: Optional[UUID] = None
    assembly_text: Optional[str] = None
    part_text: Optional[str] = None
    reviewer_notes: Optional[str] = None
    # Explicitly clear a link (PATCH semantics can't distinguish "unset" from "null")
    clear_assembly: bool = False
    clear_part: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOTE_SELECT = (
    "*, "
    "project:mrp_projects(id, project_code, description), "
    "assembly:items!shop_notes_assembly_item_id_fkey(id, item_number, name), "
    "part:items!shop_notes_part_item_id_fkey(id, item_number, name), "
    "photos:shop_note_photos(id, file_path, file_size, mime_type, sort_order, created_at)"
)


def _sign_photo(supabase, file_path: str) -> Optional[str]:
    """file_path is '<bucket>/<path>'. Returns a signed URL or None."""
    try:
        bucket, path = file_path.split("/", 1)
        res = supabase.storage.from_(bucket).create_signed_url(path, SIGNED_URL_SECONDS)
        return res.get("signedURL") or res.get("signedUrl")
    except Exception:
        return None


def _decorate(supabase, note: dict) -> dict:
    photos = sorted(note.get("photos") or [], key=lambda p: (p.get("sort_order", 0), p.get("created_at", "")))
    for p in photos:
        p["url"] = _sign_photo(supabase, p["file_path"])
    note["photos"] = photos
    return note


def _fetch_note(supabase, note_id: str) -> dict:
    res = supabase.table("shop_notes").select(NOTE_SELECT).eq("id", note_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Note not found")
    return _decorate(supabase, res.data[0])


def _ensure_bucket(supabase) -> None:
    try:
        supabase.storage.create_bucket(BUCKET, {"public": False})
    except Exception:
        pass  # already exists


# ---------------------------------------------------------------------------
# Worker endpoints
# ---------------------------------------------------------------------------

@router.post("/login")
async def pin_login(body: PinLogin):
    """Exchange the shared shop PIN for a long-lived device token."""
    if not verify_pin(body.pin):
        raise HTTPException(status_code=401, detail="Wrong PIN")
    token, exp = create_shop_token()
    return {"token": token, "expires_at": exp.isoformat()}


@router.get("/projects")
async def list_projects(auth: dict = Depends(require_shop_or_staff)):
    """Projects a worker can file a note against (non-complete first, newest first)."""
    supabase = get_supabase_admin()
    res = supabase.table("mrp_projects") \
        .select("id, project_code, description, customer, status") \
        .order("project_code", desc=True) \
        .execute()
    rows = res.data or []
    open_rows = [r for r in rows if (r.get("status") or "") != "Complete"]
    done_rows = [r for r in rows if (r.get("status") or "") == "Complete"]
    return open_rows + done_rows


@router.get("/projects/{project_id}/items")
async def project_items(project_id: UUID, auth: dict = Depends(require_shop_or_staff)):
    """Items in a project's BOM, split into assemblies and parts, with a child->parent map.

    - assemblies: items that have children in the BOM (weldments, sub-assemblies, top assembly)
    - parts: every item in the project (a weldment can itself be the thing being worked on)
    - parent map lives on each part as parent_ids so the phone can auto-fill the assembly
    """
    supabase = get_supabase_admin()
    pid = str(project_id)

    proj = supabase.table("mrp_projects").select("id, project_code, top_assembly_id").eq("id", pid).execute()
    if not proj.data:
        raise HTTPException(status_code=404, detail="Project not found")
    top_id = proj.data[0].get("top_assembly_id")

    parts_res = supabase.table("mrp_project_parts") \
        .select("item_id, quantity, items(id, item_number, name, description, thickness, is_supplier_part)") \
        .eq("project_id", pid).execute()

    items: dict[str, dict] = {}
    for row in parts_res.data or []:
        it = row.get("items") or {}
        if not it.get("id"):
            continue
        num = (it.get("item_number") or "").lower()
        if num.startswith("zzz"):
            continue  # reference-only
        items[it["id"]] = {
            "id": it["id"],
            "item_number": it.get("item_number"),
            "name": it.get("name") or it.get("description") or "",
            "quantity": row.get("quantity"),
            "is_supplier_part": bool(it.get("is_supplier_part")),
            "parent_ids": [],
        }

    if top_id and top_id not in items:
        top_res = supabase.table("items").select("id, item_number, name, description").eq("id", top_id).execute()
        if top_res.data:
            t = top_res.data[0]
            items[t["id"]] = {
                "id": t["id"],
                "item_number": t.get("item_number"),
                "name": t.get("name") or t.get("description") or "",
                "quantity": 1,
                "is_supplier_part": False,
                "parent_ids": [],
            }

    ids = list(items.keys())
    parent_ids: set[str] = set()
    if ids:
        bom_res = supabase.table("bom") \
            .select("parent_item_id, child_item_id") \
            .in_("parent_item_id", ids).execute()
        for b in bom_res.data or []:
            p, c = b.get("parent_item_id"), b.get("child_item_id")
            if p in items:
                parent_ids.add(p)
            if c in items and p and p not in items[c]["parent_ids"]:
                items[c]["parent_ids"].append(p)

    if top_id in items:
        parent_ids.add(top_id)

    def sort_key(i: dict):
        return (i.get("item_number") or "")

    all_items = sorted(items.values(), key=sort_key)
    assemblies = [
        {"id": i["id"], "item_number": i["item_number"], "name": i["name"], "is_top": i["id"] == top_id}
        for i in all_items if i["id"] in parent_ids
    ]
    return {
        "project_id": pid,
        "project_code": proj.data[0].get("project_code"),
        "assemblies": assemblies,
        "parts": all_items,
    }


@router.post("")
async def create_note(
    note: str = Form(""),
    author_name: Optional[str] = Form(None),
    project_id: Optional[str] = Form(None),
    assembly_item_id: Optional[str] = Form(None),
    part_item_id: Optional[str] = Form(None),
    assembly_text: Optional[str] = Form(None),
    part_text: Optional[str] = Form(None),
    photos: list[UploadFile] = File(default=[]),
    auth: dict = Depends(require_shop_or_staff),
):
    """Create a note with zero or more photos (multipart)."""
    note = (note or "").strip()
    if not note and not photos:
        raise HTTPException(status_code=400, detail="Add a note or a photo")
    if len(photos) > MAX_PHOTOS_PER_NOTE:
        raise HTTPException(status_code=400, detail=f"Max {MAX_PHOTOS_PER_NOTE} photos per note")

    supabase = get_supabase_admin()

    row = {
        "note": note,
        "author_name": (author_name or "").strip() or None,
        "project_id": project_id or None,
        "assembly_item_id": assembly_item_id or None,
        "part_item_id": part_item_id or None,
        "assembly_text": (assembly_text or "").strip() or None,
        "part_text": (part_text or "").strip() or None,
        "status": "new",
    }
    created = supabase.table("shop_notes").insert(row).execute()
    if not created.data:
        raise HTTPException(status_code=500, detail="Failed to save note")
    note_id = created.data[0]["id"]

    if photos:
        _ensure_bucket(supabase)
        folder = f"project-{project_id}" if project_id else "general"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        for idx, up in enumerate(photos):
            content = await up.read()
            if not content:
                continue
            if len(content) > MAX_PHOTO_BYTES:
                raise HTTPException(status_code=400, detail=f"Photo {up.filename} is too large")
            mime = (up.content_type or "image/jpeg").lower()
            if mime not in ALLOWED_MIME:
                raise HTTPException(status_code=400, detail=f"Unsupported image type: {mime}")
            ext = (up.filename or "").rsplit(".", 1)[-1].lower() if "." in (up.filename or "") else "jpg"
            path = f"{folder}/{note_id}/{stamp}_{idx:02d}_{uuid.uuid4().hex[:6]}.{ext}"
            try:
                supabase.storage.from_(BUCKET).upload(path, content, file_options={"content-type": mime})
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Photo upload failed: {e}")
            supabase.table("shop_note_photos").insert({
                "note_id": note_id,
                "file_path": f"{BUCKET}/{path}",
                "file_size": len(content),
                "mime_type": mime,
                "sort_order": idx,
            }).execute()

    return _fetch_note(supabase, note_id)


# ---------------------------------------------------------------------------
# Reviewer endpoints
# ---------------------------------------------------------------------------

@router.get("/summary")
async def summary(auth: dict = Depends(require_staff)):
    """Counts per status for the dashboard badge."""
    supabase = get_supabase_admin()
    res = supabase.table("shop_notes").select("status").execute()
    counts = {s: 0 for s in STATUSES}
    for r in res.data or []:
        counts[r.get("status", "new")] = counts.get(r.get("status", "new"), 0) + 1
    return counts


@router.get("")
async def list_notes(
    status: Optional[str] = None,
    project_id: Optional[UUID] = None,
    limit: int = 200,
    auth: dict = Depends(require_staff),
):
    supabase = get_supabase_admin()
    q = supabase.table("shop_notes").select(NOTE_SELECT)
    if status and status != "all":
        if status not in STATUSES:
            raise HTTPException(status_code=400, detail="Bad status")
        q = q.eq("status", status)
    if project_id:
        q = q.eq("project_id", str(project_id))
    res = q.order("created_at", desc=True).limit(max(1, min(limit, 500))).execute()
    return [_decorate(supabase, n) for n in (res.data or [])]


@router.get("/{note_id}")
async def get_note(note_id: UUID, auth: dict = Depends(require_staff)):
    return _fetch_note(get_supabase_admin(), str(note_id))


@router.patch("/{note_id}")
async def update_note(note_id: UUID, body: NoteUpdate, auth: dict = Depends(require_staff)):
    supabase = get_supabase_admin()
    patch: dict = {}

    if body.status is not None:
        if body.status not in STATUSES:
            raise HTTPException(status_code=400, detail="Bad status")
        patch["status"] = body.status
        patch["reviewed_at"] = None if body.status == "new" else datetime.now(timezone.utc).isoformat()
    if body.note is not None:
        patch["note"] = body.note
    if body.project_id is not None:
        patch["project_id"] = str(body.project_id)
    if body.assembly_item_id is not None:
        patch["assembly_item_id"] = str(body.assembly_item_id)
        patch["assembly_text"] = None
    if body.part_item_id is not None:
        patch["part_item_id"] = str(body.part_item_id)
        patch["part_text"] = None
    if body.assembly_text is not None:
        patch["assembly_text"] = body.assembly_text or None
    if body.part_text is not None:
        patch["part_text"] = body.part_text or None
    if body.reviewer_notes is not None:
        patch["reviewer_notes"] = body.reviewer_notes or None
    if body.clear_assembly:
        patch["assembly_item_id"] = None
    if body.clear_part:
        patch["part_item_id"] = None

    if not patch:
        raise HTTPException(status_code=400, detail="Nothing to update")

    res = supabase.table("shop_notes").update(patch).eq("id", str(note_id)).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Note not found")
    return _fetch_note(supabase, str(note_id))


@router.delete("/{note_id}")
async def delete_note(note_id: UUID, auth: dict = Depends(require_staff)):
    supabase = get_supabase_admin()
    photos = supabase.table("shop_note_photos").select("file_path").eq("note_id", str(note_id)).execute()
    paths = []
    for p in photos.data or []:
        try:
            _, path = p["file_path"].split("/", 1)
            paths.append(path)
        except ValueError:
            pass
    if paths:
        try:
            supabase.storage.from_(BUCKET).remove(paths)
        except Exception:
            pass  # orphaned objects are harmless; the DB row is the record
    res = supabase.table("shop_notes").delete().eq("id", str(note_id)).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"deleted": str(note_id)}
