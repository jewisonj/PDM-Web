"""Admin Supplier Management API routes."""

from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Optional
from uuid import UUID

from ..services.supabase import get_supabase_admin, get_supabase_client
from ..services.supplier_auth import hash_password
from ..models.supplier_schemas import (
    Supplier,
    SupplierCreate,
    SupplierUpdate,
    SupplierWithUnread,
    ItemAccess,
    ItemAccessCreate,
    ItemAccessUpdate,
    Comment,
    CommentCreate,
    UnreadCount,
    PasswordReset,
)

router = APIRouter(prefix="/admin/suppliers", tags=["admin-suppliers"])


async def get_current_admin_user(authorization: Optional[str] = Header(None)) -> dict:
    """Verify the request is from an authenticated admin user."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = authorization.split(" ")[1]
    supabase = get_supabase_client()
    admin = get_supabase_admin()

    try:
        auth_user = supabase.auth.get_user(token)
        if not auth_user or not auth_user.user:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Get user from users table
        user_result = admin.table("users")\
            .select("*")\
            .eq("auth_id", auth_user.user.id)\
            .single()\
            .execute()

        if not user_result.data:
            raise HTTPException(status_code=401, detail="User not found")

        # Check admin role
        if user_result.data.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")

        return user_result.data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Auth error: {str(e)}")


@router.get("/comments/unread", response_model=UnreadCount)
async def get_unread_count(user: dict = Depends(get_current_admin_user)):
    """Get total unread comment count for dashboard badge."""
    supabase = get_supabase_admin()

    result = supabase.table("supplier_comments")\
        .select("id", count="exact")\
        .eq("author_type", "supplier")\
        .eq("is_read", False)\
        .execute()

    return {"count": result.count or 0}


@router.get("", response_model=list[SupplierWithUnread])
async def list_suppliers(user: dict = Depends(get_current_admin_user)):
    """List all suppliers with unread counts."""
    supabase = get_supabase_admin()

    # Get suppliers
    result = supabase.table("suppliers")\
        .select("*")\
        .order("company_name")\
        .execute()

    suppliers = []
    for s in result.data or []:
        # Get unread count for this supplier
        unread = supabase.table("supplier_comments")\
            .select("id", count="exact")\
            .eq("supplier_id", s["id"])\
            .eq("author_type", "supplier")\
            .eq("is_read", False)\
            .execute()

        s.pop("password_hash", None)
        s["unread_count"] = unread.count or 0
        suppliers.append(s)

    return suppliers


@router.post("", response_model=Supplier)
async def create_supplier(
    supplier: SupplierCreate,
    user: dict = Depends(get_current_admin_user)
):
    """Create a new supplier."""
    supabase = get_supabase_admin()

    # Check email uniqueness
    existing = supabase.table("suppliers")\
        .select("id")\
        .eq("login_email", supplier.login_email.lower())\
        .execute()

    if existing.data:
        raise HTTPException(status_code=400, detail="Email already in use")

    # Create supplier
    data = {
        "company_name": supplier.company_name,
        "contact_name": supplier.contact_name,
        "contact_email": supplier.contact_email,
        "phone": supplier.phone,
        "login_email": supplier.login_email.lower(),
        "password_hash": hash_password(supplier.password),
        "is_active": supplier.is_active,
        "notes": supplier.notes,
        "created_by": user["id"],
    }

    result = supabase.table("suppliers").insert(data).execute()

    supplier_data = result.data[0]
    supplier_data.pop("password_hash", None)
    return supplier_data


@router.get("/{supplier_id}", response_model=Supplier)
async def get_supplier(supplier_id: UUID, user: dict = Depends(get_current_admin_user)):
    """Get supplier details."""
    supabase = get_supabase_admin()

    result = supabase.table("suppliers")\
        .select("*")\
        .eq("id", str(supplier_id))\
        .single()\
        .execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Supplier not found")

    result.data.pop("password_hash", None)
    return result.data


@router.patch("/{supplier_id}", response_model=Supplier)
async def update_supplier(
    supplier_id: UUID,
    updates: SupplierUpdate,
    user: dict = Depends(get_current_admin_user)
):
    """Update supplier details."""
    supabase = get_supabase_admin()

    data = updates.model_dump(exclude_unset=True)
    if "login_email" in data and data["login_email"]:
        data["login_email"] = data["login_email"].lower()

    if not data:
        raise HTTPException(status_code=400, detail="No updates provided")

    result = supabase.table("suppliers")\
        .update(data)\
        .eq("id", str(supplier_id))\
        .execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Supplier not found")

    result.data[0].pop("password_hash", None)
    return result.data[0]


@router.delete("/{supplier_id}")
async def delete_supplier(supplier_id: UUID, user: dict = Depends(get_current_admin_user)):
    """Soft delete (deactivate) a supplier."""
    supabase = get_supabase_admin()

    result = supabase.table("suppliers")\
        .update({"is_active": False})\
        .eq("id", str(supplier_id))\
        .execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Supplier not found")

    return {"message": "Supplier deactivated"}


@router.post("/{supplier_id}/reset-password")
async def reset_supplier_password(
    supplier_id: UUID,
    password_data: PasswordReset,
    user: dict = Depends(get_current_admin_user)
):
    """Reset supplier password."""
    supabase = get_supabase_admin()

    result = supabase.table("suppliers")\
        .update({"password_hash": hash_password(password_data.new_password)})\
        .eq("id", str(supplier_id))\
        .execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Supplier not found")

    return {"message": "Password reset successfully"}


# === Item Access Management ===
@router.get("/{supplier_id}/items", response_model=list[ItemAccess])
async def get_supplier_item_access(
    supplier_id: UUID,
    user: dict = Depends(get_current_admin_user)
):
    """Get all item access for a supplier."""
    supabase = get_supabase_admin()

    result = supabase.table("supplier_item_access")\
        .select("*, items(item_number, name)")\
        .eq("supplier_id", str(supplier_id))\
        .execute()

    items = []
    for access in result.data or []:
        item_data = access.pop("items", {}) or {}
        access["item_number"] = item_data.get("item_number")
        access["item_name"] = item_data.get("name")
        items.append(access)

    return items


@router.post("/{supplier_id}/items", response_model=ItemAccess)
async def grant_item_access(
    supplier_id: UUID,
    access: ItemAccessCreate,
    user: dict = Depends(get_current_admin_user)
):
    """Grant supplier access to an item."""
    supabase = get_supabase_admin()

    # Verify supplier exists
    supplier_check = supabase.table("suppliers")\
        .select("id")\
        .eq("id", str(supplier_id))\
        .single()\
        .execute()

    if not supplier_check.data:
        raise HTTPException(status_code=404, detail="Supplier not found")

    # Verify item exists
    item_check = supabase.table("items")\
        .select("id, item_number, name")\
        .eq("id", str(access.item_id))\
        .single()\
        .execute()

    if not item_check.data:
        raise HTTPException(status_code=404, detail="Item not found")

    data = {
        "supplier_id": str(supplier_id),
        "item_id": str(access.item_id),
        "file_types": access.file_types,
        "notes": access.notes,
        "granted_by": user["id"],
    }

    try:
        result = supabase.table("supplier_item_access").insert(data).execute()
    except Exception as e:
        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
            raise HTTPException(status_code=400, detail="Access already granted for this item")
        raise

    access_data = result.data[0]
    access_data["item_number"] = item_check.data.get("item_number")
    access_data["item_name"] = item_check.data.get("name")
    return access_data


@router.patch("/{supplier_id}/items/{item_id}", response_model=ItemAccess)
async def update_item_access(
    supplier_id: UUID,
    item_id: UUID,
    updates: ItemAccessUpdate,
    user: dict = Depends(get_current_admin_user)
):
    """Update item access (file types, notes)."""
    supabase = get_supabase_admin()

    data = updates.model_dump(exclude_unset=True)

    if not data:
        raise HTTPException(status_code=400, detail="No updates provided")

    result = supabase.table("supplier_item_access")\
        .update(data)\
        .eq("supplier_id", str(supplier_id))\
        .eq("item_id", str(item_id))\
        .execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Access not found")

    return result.data[0]


@router.delete("/{supplier_id}/items/{item_id}")
async def revoke_item_access(
    supplier_id: UUID,
    item_id: UUID,
    user: dict = Depends(get_current_admin_user)
):
    """Revoke supplier access to an item."""
    supabase = get_supabase_admin()

    supabase.table("supplier_item_access")\
        .delete()\
        .eq("supplier_id", str(supplier_id))\
        .eq("item_id", str(item_id))\
        .execute()

    return {"message": "Access revoked"}


# === Admin Comments ===
@router.get("/{supplier_id}/comments", response_model=list[Comment])
async def get_supplier_comments(
    supplier_id: UUID,
    user: dict = Depends(get_current_admin_user)
):
    """Get all comments for a supplier across all items."""
    supabase = get_supabase_admin()

    result = supabase.table("supplier_comments")\
        .select("*")\
        .eq("supplier_id", str(supplier_id))\
        .order("created_at", desc=True)\
        .execute()

    return result.data or []


@router.get("/{supplier_id}/items/{item_id}/comments", response_model=list[Comment])
async def get_supplier_item_comments(
    supplier_id: UUID,
    item_id: UUID,
    user: dict = Depends(get_current_admin_user)
):
    """Get comments for a specific item from a supplier."""
    supabase = get_supabase_admin()

    result = supabase.table("supplier_comments")\
        .select("*")\
        .eq("supplier_id", str(supplier_id))\
        .eq("item_id", str(item_id))\
        .order("created_at")\
        .execute()

    # Mark supplier comments as read
    supplier_comment_ids = [
        c["id"] for c in (result.data or [])
        if c["author_type"] == "supplier" and not c["is_read"]
    ]
    if supplier_comment_ids:
        supabase.table("supplier_comments")\
            .update({"is_read": True})\
            .in_("id", supplier_comment_ids)\
            .execute()

    return result.data or []


@router.post("/{supplier_id}/items/{item_id}/comments", response_model=Comment)
async def create_admin_comment(
    supplier_id: UUID,
    item_id: UUID,
    comment: CommentCreate,
    user: dict = Depends(get_current_admin_user)
):
    """Create an admin reply to a supplier comment thread."""
    supabase = get_supabase_admin()

    data = {
        "supplier_id": str(supplier_id),
        "item_id": str(item_id),
        "author_type": "admin",
        "author_name": user["username"],
        "author_user_id": user["id"],
        "content": comment.content,
        "is_read": True,  # Admin's own comment is marked read
    }

    result = supabase.table("supplier_comments").insert(data).execute()
    return result.data[0]


@router.patch("/comments/{comment_id}/read")
async def mark_comment_read(
    comment_id: UUID,
    user: dict = Depends(get_current_admin_user)
):
    """Mark a comment as read."""
    supabase = get_supabase_admin()

    supabase.table("supplier_comments")\
        .update({"is_read": True})\
        .eq("id", str(comment_id))\
        .execute()

    return {"message": "Marked as read"}
