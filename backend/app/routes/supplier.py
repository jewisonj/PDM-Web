"""Supplier Portal API routes."""

from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Optional
from uuid import UUID

from ..services.supabase import get_supabase_admin
from ..services.supplier_auth import (
    verify_password,
    create_supplier_token,
    decode_supplier_token,
)
from ..models.supplier_schemas import (
    SupplierLogin,
    SupplierTokenResponse,
    Supplier,
    SupplierItemView,
    SupplierFileView,
    Comment,
    CommentCreate,
)

router = APIRouter(prefix="/supplier", tags=["supplier-portal"])


async def get_current_supplier(authorization: Optional[str] = Header(None)) -> dict:
    """Dependency to get current supplier from JWT token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = authorization.split(" ")[1]
    payload = decode_supplier_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Verify supplier still exists and is active
    supabase = get_supabase_admin()
    result = supabase.table("suppliers")\
        .select("*")\
        .eq("id", payload["sub"])\
        .eq("is_active", True)\
        .single()\
        .execute()

    if not result.data:
        raise HTTPException(status_code=401, detail="Supplier account not found or inactive")

    return result.data


@router.post("/login", response_model=SupplierTokenResponse)
async def supplier_login(credentials: SupplierLogin):
    """Authenticate supplier and return JWT token."""
    supabase = get_supabase_admin()

    # Find supplier by email
    result = supabase.table("suppliers")\
        .select("*")\
        .eq("login_email", credentials.email.lower())\
        .eq("is_active", True)\
        .single()\
        .execute()

    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    supplier = result.data

    # Verify password
    if not verify_password(credentials.password, supplier["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Create token
    token = create_supplier_token(supplier["id"], supplier["login_email"])

    # Remove password_hash from response
    del supplier["password_hash"]

    return {
        "access_token": token,
        "token_type": "bearer",
        "supplier": supplier,
    }


@router.get("/me", response_model=Supplier)
async def get_supplier_profile(supplier: dict = Depends(get_current_supplier)):
    """Get current supplier profile."""
    # Remove password_hash
    supplier.pop("password_hash", None)
    return supplier


@router.get("/items", response_model=list[SupplierItemView])
async def get_supplier_items(supplier: dict = Depends(get_current_supplier)):
    """Get all items the supplier has access to."""
    supabase = get_supabase_admin()
    supplier_id = supplier["id"]

    # Get item access records with item details
    result = supabase.table("supplier_item_access")\
        .select("*, items(*)")\
        .eq("supplier_id", supplier_id)\
        .execute()

    items = []
    for access in result.data or []:
        item_data = access.get("items")
        if not item_data:
            continue

        # Get allowed file types
        allowed_types = access.get("file_types", ["PDF", "STEP", "IMAGE"])

        # Get files matching allowed types
        files_result = supabase.table("files")\
            .select("*")\
            .eq("item_id", item_data["id"])\
            .in_("file_type", allowed_types)\
            .order("created_at", desc=True)\
            .execute()

        files = [
            SupplierFileView(
                id=f["id"],
                file_type=f["file_type"],
                file_name=f["file_name"],
                file_size=f.get("file_size"),
                revision=f.get("revision"),
                created_at=f["created_at"],
            )
            for f in (files_result.data or [])
        ]

        # Get unread comment count for this item
        unread_result = supabase.table("supplier_comments")\
            .select("id", count="exact")\
            .eq("supplier_id", supplier_id)\
            .eq("item_id", item_data["id"])\
            .eq("author_type", "admin")\
            .eq("is_read", False)\
            .execute()

        items.append(SupplierItemView(
            id=item_data["id"],
            item_number=item_data["item_number"],
            name=item_data.get("name"),
            revision=item_data.get("revision", "A"),
            lifecycle_state=item_data.get("lifecycle_state", "Design"),
            material=item_data.get("material"),
            thickness=item_data.get("thickness"),
            mass=item_data.get("mass"),
            allowed_file_types=allowed_types,
            files=files,
            unread_comments=unread_result.count or 0,
        ))

    return items


@router.get("/items/{item_number}", response_model=SupplierItemView)
async def get_supplier_item(item_number: str, supplier: dict = Depends(get_current_supplier)):
    """Get a specific item the supplier has access to."""
    supabase = get_supabase_admin()
    supplier_id = supplier["id"]

    # Get item
    item_result = supabase.table("items")\
        .select("*")\
        .eq("item_number", item_number.lower())\
        .single()\
        .execute()

    if not item_result.data:
        raise HTTPException(status_code=404, detail="Item not found")

    item_data = item_result.data

    # Check access
    access_result = supabase.table("supplier_item_access")\
        .select("*")\
        .eq("supplier_id", supplier_id)\
        .eq("item_id", item_data["id"])\
        .single()\
        .execute()

    if not access_result.data:
        raise HTTPException(status_code=403, detail="Access denied to this item")

    allowed_types = access_result.data.get("file_types", ["PDF", "STEP", "IMAGE"])

    # Get files
    files_result = supabase.table("files")\
        .select("*")\
        .eq("item_id", item_data["id"])\
        .in_("file_type", allowed_types)\
        .order("created_at", desc=True)\
        .execute()

    files = [
        SupplierFileView(
            id=f["id"],
            file_type=f["file_type"],
            file_name=f["file_name"],
            file_size=f.get("file_size"),
            revision=f.get("revision"),
            created_at=f["created_at"],
        )
        for f in (files_result.data or [])
    ]

    # Get unread comment count
    unread_result = supabase.table("supplier_comments")\
        .select("id", count="exact")\
        .eq("supplier_id", supplier_id)\
        .eq("item_id", item_data["id"])\
        .eq("author_type", "admin")\
        .eq("is_read", False)\
        .execute()

    return SupplierItemView(
        id=item_data["id"],
        item_number=item_data["item_number"],
        name=item_data.get("name"),
        revision=item_data.get("revision", "A"),
        lifecycle_state=item_data.get("lifecycle_state", "Design"),
        material=item_data.get("material"),
        thickness=item_data.get("thickness"),
        mass=item_data.get("mass"),
        allowed_file_types=allowed_types,
        files=files,
        unread_comments=unread_result.count or 0,
    )


@router.get("/items/{item_number}/files/{file_id}/download")
async def download_supplier_file(
    item_number: str,
    file_id: UUID,
    supplier: dict = Depends(get_current_supplier)
):
    """Get signed download URL for a file."""
    supabase = get_supabase_admin()
    supplier_id = supplier["id"]

    # Get item
    item_result = supabase.table("items")\
        .select("id")\
        .eq("item_number", item_number.lower())\
        .single()\
        .execute()

    if not item_result.data:
        raise HTTPException(status_code=404, detail="Item not found")

    item_id = item_result.data["id"]

    # Check access
    access_result = supabase.table("supplier_item_access")\
        .select("file_types")\
        .eq("supplier_id", supplier_id)\
        .eq("item_id", item_id)\
        .single()\
        .execute()

    if not access_result.data:
        raise HTTPException(status_code=403, detail="Access denied")

    allowed_types = access_result.data.get("file_types", ["PDF", "STEP", "IMAGE"])

    # Get file
    file_result = supabase.table("files")\
        .select("*")\
        .eq("id", str(file_id))\
        .eq("item_id", item_id)\
        .single()\
        .execute()

    if not file_result.data:
        raise HTTPException(status_code=404, detail="File not found")

    file_data = file_result.data

    # Check file type allowed
    if file_data["file_type"] not in allowed_types:
        raise HTTPException(status_code=403, detail="File type not allowed for your account")

    file_path = file_data.get("file_path")
    if not file_path:
        raise HTTPException(status_code=404, detail="File not in storage")

    # Parse bucket and path
    parts = file_path.split("/", 1)
    bucket = parts[0] if len(parts) == 2 else "pdm-files"
    storage_path = parts[1] if len(parts) == 2 else file_path

    try:
        url_result = supabase.storage.from_(bucket).create_signed_url(storage_path, 3600)
        return {
            "url": url_result["signedURL"],
            "filename": file_data["file_name"],
            "expires_in": 3600,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download error: {str(e)}")


# === Comments ===
@router.get("/items/{item_number}/comments", response_model=list[Comment])
async def get_item_comments(
    item_number: str,
    supplier: dict = Depends(get_current_supplier)
):
    """Get comments for an item."""
    supabase = get_supabase_admin()
    supplier_id = supplier["id"]

    # Get item
    item_result = supabase.table("items")\
        .select("id")\
        .eq("item_number", item_number.lower())\
        .single()\
        .execute()

    if not item_result.data:
        raise HTTPException(status_code=404, detail="Item not found")

    item_id = item_result.data["id"]

    # Check access
    access_result = supabase.table("supplier_item_access")\
        .select("id")\
        .eq("supplier_id", supplier_id)\
        .eq("item_id", item_id)\
        .single()\
        .execute()

    if not access_result.data:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get comments
    comments_result = supabase.table("supplier_comments")\
        .select("*")\
        .eq("supplier_id", supplier_id)\
        .eq("item_id", item_id)\
        .order("created_at")\
        .execute()

    # Mark admin replies as read
    admin_comment_ids = [
        c["id"] for c in (comments_result.data or [])
        if c["author_type"] == "admin" and not c["is_read"]
    ]
    if admin_comment_ids:
        supabase.table("supplier_comments")\
            .update({"is_read": True})\
            .in_("id", admin_comment_ids)\
            .execute()

    return comments_result.data or []


@router.post("/items/{item_number}/comments", response_model=Comment)
async def create_supplier_comment(
    item_number: str,
    comment: CommentCreate,
    supplier: dict = Depends(get_current_supplier)
):
    """Create a new comment on an item."""
    supabase = get_supabase_admin()
    supplier_id = supplier["id"]

    # Get item
    item_result = supabase.table("items")\
        .select("id")\
        .eq("item_number", item_number.lower())\
        .single()\
        .execute()

    if not item_result.data:
        raise HTTPException(status_code=404, detail="Item not found")

    item_id = item_result.data["id"]

    # Check access
    access_result = supabase.table("supplier_item_access")\
        .select("id")\
        .eq("supplier_id", supplier_id)\
        .eq("item_id", item_id)\
        .single()\
        .execute()

    if not access_result.data:
        raise HTTPException(status_code=403, detail="Access denied")

    # Create comment
    comment_data = {
        "supplier_id": supplier_id,
        "item_id": item_id,
        "author_type": "supplier",
        "author_name": supplier["company_name"],
        "content": comment.content,
        "is_read": False,  # Admin hasn't read it yet
    }

    result = supabase.table("supplier_comments")\
        .insert(comment_data)\
        .execute()

    return result.data[0]


# === Model Annotations for Suppliers ===
@router.get("/items/{item_number}/files/{file_id}/annotations")
async def get_supplier_file_annotations(
    item_number: str,
    file_id: UUID,
    supplier: dict = Depends(get_current_supplier)
):
    """Get annotations for a file (supplier access)."""
    supabase = get_supabase_admin()
    supplier_id = supplier["id"]

    # Verify supplier has access to this item
    item_result = supabase.table("items")\
        .select("id")\
        .eq("item_number", item_number.lower())\
        .single()\
        .execute()

    if not item_result.data:
        raise HTTPException(status_code=404, detail="Item not found")

    item_id = item_result.data["id"]

    access = supabase.table("supplier_item_access")\
        .select("id")\
        .eq("supplier_id", supplier_id)\
        .eq("item_id", item_id)\
        .single()\
        .execute()

    if not access.data:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get annotations
    result = supabase.table("model_annotations")\
        .select("*")\
        .eq("file_id", str(file_id))\
        .order("created_at")\
        .execute()

    return result.data or []


@router.post("/items/{item_number}/files/{file_id}/annotations")
async def create_supplier_annotation(
    item_number: str,
    file_id: UUID,
    position_x: float,
    position_y: float,
    position_z: float,
    content: str,
    normal_x: Optional[float] = None,
    normal_y: Optional[float] = None,
    normal_z: Optional[float] = None,
    supplier: dict = Depends(get_current_supplier)
):
    """Create annotation on a file (supplier access)."""
    supabase = get_supabase_admin()
    supplier_id = supplier["id"]

    # Verify access
    item_result = supabase.table("items")\
        .select("id")\
        .eq("item_number", item_number.lower())\
        .single()\
        .execute()

    if not item_result.data:
        raise HTTPException(status_code=404, detail="Item not found")

    item_id = item_result.data["id"]

    access = supabase.table("supplier_item_access")\
        .select("id")\
        .eq("supplier_id", supplier_id)\
        .eq("item_id", item_id)\
        .single()\
        .execute()

    if not access.data:
        raise HTTPException(status_code=403, detail="Access denied")

    data = {
        "file_id": str(file_id),
        "item_id": item_id,
        "position_x": position_x,
        "position_y": position_y,
        "position_z": position_z,
        "normal_x": normal_x,
        "normal_y": normal_y,
        "normal_z": normal_z,
        "content": content,
        "author_type": "supplier",
        "author_id": supplier_id,
        "author_name": supplier.get("company_name", "Supplier"),
    }

    result = supabase.table("model_annotations")\
        .insert(data)\
        .execute()

    return result.data[0]
