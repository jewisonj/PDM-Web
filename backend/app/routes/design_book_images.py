"""Design Book Images API routes - v2."""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Optional
from uuid import UUID
from pydantic import BaseModel

from ..services.supabase import get_supabase_admin

router = APIRouter(prefix="/design-book-images", tags=["design-book-images"])


# Pydantic models
class ImageCategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = 0


class ImageCategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None


class ImageUpdate(BaseModel):
    caption: Optional[str] = None
    notes: Optional[str] = None
    category_id: Optional[UUID] = None
    item_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    width_pct: Optional[int] = None


# ============================================================================
# Categories (all specific paths first)
# ============================================================================

@router.get("/categories")
async def list_categories():
    """List all image categories."""
    supabase = get_supabase_admin()

    result = supabase.table("design_book_image_categories")\
        .select("*")\
        .order("sort_order")\
        .execute()

    return result.data


@router.post("/categories")
async def create_category(category: ImageCategoryCreate):
    """Create a new custom image category."""
    supabase = get_supabase_admin()

    # Custom categories are never system categories
    data = {
        "name": category.name,
        "description": category.description,
        "icon": category.icon,
        "sort_order": category.sort_order or 100,  # Custom categories sort after system
        "is_system": False
    }

    try:
        result = supabase.table("design_book_image_categories").insert(data).execute()
        return result.data[0]
    except Exception as e:
        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
            raise HTTPException(status_code=400, detail=f"Category '{category.name}' already exists")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/categories/{category_id}")
async def update_category(category_id: UUID, category: ImageCategoryUpdate):
    """Update a custom category (system categories cannot be updated)."""
    supabase = get_supabase_admin()

    # Check if it's a system category
    existing = supabase.table("design_book_image_categories")\
        .select("is_system")\
        .eq("id", str(category_id))\
        .execute()

    if not existing.data:
        raise HTTPException(status_code=404, detail="Category not found")

    if existing.data[0]["is_system"]:
        raise HTTPException(status_code=403, detail="System categories cannot be modified")

    # Build update data
    update_data = {}
    if category.name is not None:
        update_data["name"] = category.name
    if category.description is not None:
        update_data["description"] = category.description
    if category.icon is not None:
        update_data["icon"] = category.icon
    if category.sort_order is not None:
        update_data["sort_order"] = category.sort_order

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = supabase.table("design_book_image_categories")\
        .update(update_data)\
        .eq("id", str(category_id))\
        .execute()

    return result.data[0]


@router.delete("/categories/{category_id}")
async def delete_category(category_id: UUID):
    """Delete a custom category (system categories cannot be deleted)."""
    supabase = get_supabase_admin()

    # Check if it's a system category
    existing = supabase.table("design_book_image_categories")\
        .select("is_system, name")\
        .eq("id", str(category_id))\
        .execute()

    if not existing.data:
        raise HTTPException(status_code=404, detail="Category not found")

    if existing.data[0]["is_system"]:
        raise HTTPException(status_code=403, detail="System categories cannot be deleted")

    # Check if any images use this category
    images = supabase.table("design_book_images")\
        .select("id")\
        .eq("category_id", str(category_id))\
        .limit(1)\
        .execute()

    if images.data:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete category '{existing.data[0]['name']}': images are using it"
        )

    supabase.table("design_book_image_categories")\
        .delete()\
        .eq("id", str(category_id))\
        .execute()

    return {"message": "Category deleted"}


# ============================================================================
# Images - SPECIFIC PATHS FIRST (before parameterized routes)
# ============================================================================

@router.get("/list")
async def list_images(
    category_id: Optional[str] = None,
    project_id: Optional[str] = None,
    item_id: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """List images with optional filtering."""
    try:
        supabase = get_supabase_admin()

        query = supabase.table("design_book_images")\
            .select("*")

        if category_id:
            query = query.eq("category_id", str(category_id))
        if project_id:
            query = query.eq("project_id", str(project_id))
        if item_id:
            query = query.eq("item_id", str(item_id))
        if search:
            # Search in caption and notes
            query = query.or_(f"caption.ilike.%{search}%,notes.ilike.%{search}%")

        query = query.order("created_at", desc=True)\
            .range(offset, offset + limit - 1)

        result = query.execute()
        return result.data
    except Exception as e:
        import traceback
        print(f"Error in list_images: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    caption: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    category_id: Optional[str] = Form(None),
    item_id: Optional[str] = Form(None),
    project_id: Optional[str] = Form(None),
    width_pct: int = Form(100)
):
    """Upload a new image with metadata."""
    supabase = get_supabase_admin()

    # Validate file type
    allowed_types = ["image/png", "image/jpeg", "image/jpg", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {file.content_type}. Allowed: PNG, JPEG, WebP"
        )

    # Validate width_pct
    if width_pct not in [25, 50, 75, 100]:
        raise HTTPException(status_code=400, detail="width_pct must be 25, 50, 75, or 100")

    # Read file content
    content = await file.read()
    file_size = len(content)

    # Max 10MB
    if file_size > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 10MB")

    # Generate storage path
    import uuid
    from datetime import datetime

    # Use project_id or item_id for organization, fall back to 'general'
    folder = "general"
    if project_id:
        folder = f"project-{project_id}"
    elif item_id:
        # Get item number for folder
        item_result = supabase.table("items").select("item_number").eq("id", item_id).execute()
        if item_result.data:
            folder = item_result.data[0]["item_number"]

    # Generate unique filename
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "jpg"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    storage_filename = f"{timestamp}_{unique_id}.{ext}"
    storage_path = f"{folder}/{storage_filename}"

    # Upload to Supabase Storage
    bucket = "design-book-images"

    try:
        # Create bucket if it doesn't exist (will fail silently if exists)
        try:
            supabase.storage.create_bucket(bucket, {"public": False})
        except Exception:
            pass  # Bucket likely exists

        supabase.storage.from_(bucket).upload(
            storage_path,
            content,
            file_options={"content-type": file.content_type}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Storage error: {str(e)}")

    # Create database record
    image_data = {
        "file_name": file.filename,
        "file_path": f"{bucket}/{storage_path}",
        "file_size": file_size,
        "mime_type": file.content_type,
        "caption": caption,
        "notes": notes,
        "width_pct": width_pct
    }

    if category_id:
        image_data["category_id"] = category_id
    if item_id:
        image_data["item_id"] = item_id
    if project_id:
        image_data["project_id"] = project_id

    result = supabase.table("design_book_images").insert(image_data).execute()

    return result.data[0]


@router.get("/by-project/{project_id}")
async def get_images_by_project(project_id: UUID):
    """Get all images for a project, organized by category."""
    supabase = get_supabase_admin()

    # Get all images for project (direct or via items)
    result = supabase.table("design_book_images")\
        .select("*, category:design_book_image_categories(id, name, icon), item:items(id, item_number, name)")\
        .eq("project_id", str(project_id))\
        .order("category_id")\
        .order("created_at", desc=True)\
        .execute()

    # Also get images linked to items in this project
    items_result = supabase.table("items")\
        .select("id")\
        .eq("project_id", str(project_id))\
        .execute()

    item_ids = [item["id"] for item in items_result.data] if items_result.data else []

    item_images = []
    if item_ids:
        for item_id in item_ids:
            img_result = supabase.table("design_book_images")\
                .select("*, category:design_book_image_categories(id, name, icon), item:items(id, item_number, name)")\
                .eq("item_id", item_id)\
                .execute()
            item_images.extend(img_result.data)

    # Combine and deduplicate
    all_images = result.data + item_images
    seen_ids = set()
    unique_images = []
    for img in all_images:
        if img["id"] not in seen_ids:
            seen_ids.add(img["id"])
            unique_images.append(img)

    # Group by category
    by_category = {}
    for img in unique_images:
        cat_name = img["category"]["name"] if img.get("category") else "Uncategorized"
        if cat_name not in by_category:
            by_category[cat_name] = []
        by_category[cat_name].append(img)

    return {
        "images": unique_images,
        "by_category": by_category
    }


# ============================================================================
# Images - PARAMETERIZED ROUTES (must be last)
# ============================================================================

@router.get("/{image_id}")
async def get_image(image_id: UUID):
    """Get a single image by ID."""
    supabase = get_supabase_admin()

    result = supabase.table("design_book_images")\
        .select("*, category:design_book_image_categories(id, name, icon), item:items(id, item_number, name)")\
        .eq("id", str(image_id))\
        .execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Image not found")

    return result.data[0]


@router.patch("/{image_id}")
async def update_image(image_id: UUID, update: ImageUpdate):
    """Update image metadata."""
    supabase = get_supabase_admin()

    # Check if image exists
    existing = supabase.table("design_book_images")\
        .select("id")\
        .eq("id", str(image_id))\
        .execute()

    if not existing.data:
        raise HTTPException(status_code=404, detail="Image not found")

    # Build update data
    update_data = {}
    if update.caption is not None:
        update_data["caption"] = update.caption
    if update.notes is not None:
        update_data["notes"] = update.notes
    if update.category_id is not None:
        update_data["category_id"] = str(update.category_id)
    if update.item_id is not None:
        update_data["item_id"] = str(update.item_id)
    if update.project_id is not None:
        update_data["project_id"] = str(update.project_id)
    if update.width_pct is not None:
        if update.width_pct not in [25, 50, 75, 100]:
            raise HTTPException(status_code=400, detail="width_pct must be 25, 50, 75, or 100")
        update_data["width_pct"] = update.width_pct

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = supabase.table("design_book_images")\
        .update(update_data)\
        .eq("id", str(image_id))\
        .execute()

    return result.data[0]


@router.delete("/{image_id}")
async def delete_image(image_id: UUID):
    """Delete an image and its storage file."""
    supabase = get_supabase_admin()

    # Get image to find storage path
    existing = supabase.table("design_book_images")\
        .select("file_path")\
        .eq("id", str(image_id))\
        .execute()

    if not existing.data:
        raise HTTPException(status_code=404, detail="Image not found")

    file_path = existing.data[0]["file_path"]

    # Delete from storage
    if file_path:
        try:
            parts = file_path.split("/", 1)
            if len(parts) == 2:
                bucket = parts[0]
                storage_path = parts[1]
                supabase.storage.from_(bucket).remove([storage_path])
        except Exception:
            pass  # Continue even if storage delete fails

    # Delete database record
    supabase.table("design_book_images")\
        .delete()\
        .eq("id", str(image_id))\
        .execute()

    return {"message": "Image deleted"}


@router.get("/{image_id}/url")
async def get_image_url(image_id: UUID):
    """Get a signed URL to view/download the image."""
    supabase = get_supabase_admin()

    # Get image
    result = supabase.table("design_book_images")\
        .select("file_path, file_name")\
        .eq("id", str(image_id))\
        .execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Image not found")

    file_path = result.data[0]["file_path"]

    if not file_path:
        raise HTTPException(status_code=404, detail="Image file not found in storage")

    # Parse bucket and path
    parts = file_path.split("/", 1)
    if len(parts) == 2:
        bucket = parts[0]
        storage_path = parts[1]
    else:
        bucket = "design-book-images"
        storage_path = file_path

    try:
        url_result = supabase.storage.from_(bucket).create_signed_url(storage_path, 3600)
        return {
            "url": url_result["signedURL"],
            "filename": result.data[0]["file_name"],
            "expires_in": 3600
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not generate URL: {str(e)}")
