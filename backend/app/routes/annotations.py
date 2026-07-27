"""3D Model Annotations API routes."""

from fastapi import APIRouter, HTTPException, Depends, Header
from uuid import UUID
from typing import Optional

from ..models.schemas import Annotation, AnnotationCreate
from ..services.supabase import get_supabase_admin, get_supabase_client

router = APIRouter(prefix="/files", tags=["annotations"])


async def get_current_user(authorization: Optional[str] = Header(None)):
    """Dependency to get current authenticated user."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = authorization.split(" ")[1]
    supabase = get_supabase_client()
    admin = get_supabase_admin()

    try:
        # Verify token and get user
        auth_user = supabase.auth.get_user(token)

        if not auth_user or not auth_user.user:
            raise HTTPException(status_code=401, detail="Invalid token")

        auth_id = auth_user.user.id

        # Get user from our users table by auth_id (use admin to bypass RLS)
        user_result = admin.table("users").select("*").eq("auth_id", auth_id).execute()

        if user_result.data and len(user_result.data) > 0:
            return user_result.data[0]

        raise HTTPException(status_code=404, detail="User not found")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication error: {str(e)}")


@router.get("/{file_id}/annotations", response_model=list[Annotation])
async def get_file_annotations(
    file_id: UUID,
    user: dict = Depends(get_current_user)
):
    """Get all annotations for a file."""
    supabase = get_supabase_admin()

    result = supabase.table("model_annotations")\
        .select("*")\
        .eq("file_id", str(file_id))\
        .order("created_at")\
        .execute()

    return result.data or []


@router.post("/{file_id}/annotations", response_model=Annotation)
async def create_annotation(
    file_id: UUID,
    annotation: AnnotationCreate,
    user: dict = Depends(get_current_user)
):
    """Create a new annotation on a file."""
    supabase = get_supabase_admin()

    # Get file to find item_id
    file_result = supabase.table("files")\
        .select("item_id")\
        .eq("id", str(file_id))\
        .single()\
        .execute()

    if not file_result.data:
        raise HTTPException(status_code=404, detail="File not found")

    data = {
        "file_id": str(file_id),
        "item_id": file_result.data["item_id"],
        "position_x": annotation.position_x,
        "position_y": annotation.position_y,
        "position_z": annotation.position_z,
        "normal_x": annotation.normal_x,
        "normal_y": annotation.normal_y,
        "normal_z": annotation.normal_z,
        "content": annotation.content,
        "author_type": "user",
        "author_id": str(user["id"]),
        "author_name": user.get("username", "Unknown User"),
    }

    result = supabase.table("model_annotations")\
        .insert(data)\
        .execute()

    return result.data[0]


@router.delete("/annotations/{annotation_id}")
async def delete_annotation(
    annotation_id: UUID,
    user: dict = Depends(get_current_user)
):
    """Delete an annotation (author only)."""
    supabase = get_supabase_admin()

    # Check ownership
    check = supabase.table("model_annotations")\
        .select("author_id, author_type")\
        .eq("id", str(annotation_id))\
        .single()\
        .execute()

    if not check.data:
        raise HTTPException(status_code=404, detail="Annotation not found")

    if check.data["author_type"] == "user" and str(check.data["author_id"]) != str(user["id"]):
        raise HTTPException(status_code=403, detail="Not authorized to delete this annotation")

    supabase.table("model_annotations")\
        .delete()\
        .eq("id", str(annotation_id))\
        .execute()

    return {"success": True}
