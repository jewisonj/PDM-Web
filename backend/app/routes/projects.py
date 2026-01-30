"""Projects API routes."""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from uuid import UUID

from ..services.supabase import get_supabase_client
from ..models.schemas import Project, ProjectCreate, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[Project])
async def list_projects(
    status: Optional[str] = None,
    limit: int = Query(50, le=100),
    offset: int = 0,
):
    """List all projects."""
    supabase = get_supabase_client()

    query = supabase.table("projects").select("*")

    if status:
        query = query.eq("status", status)
    else:
        query = query.neq("status", "archived")

    query = query.order("name").range(offset, offset + limit - 1)

    result = query.execute()
    return result.data


@router.get("/{project_id}", response_model=Project)
async def get_project(project_id: UUID):
    """Get project by ID."""
    supabase = get_supabase_client()

    result = supabase.table("projects").select("*").eq("id", str(project_id)).single().execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Project not found")

    return result.data


@router.get("/{project_id}/items")
async def get_project_items(project_id: UUID, limit: int = 100, offset: int = 0):
    """Get all items in a project."""
    supabase = get_supabase_client()

    # Verify project exists
    project = supabase.table("projects").select("id").eq("id", str(project_id)).single().execute()

    if not project.data:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get items
    items = supabase.table("items").select("*").eq("project_id", str(project_id)).order("item_number").range(offset, offset + limit - 1).execute()

    return items.data


@router.post("", response_model=Project)
async def create_project(project: ProjectCreate):
    """Create a new project."""
    supabase = get_supabase_client()

    result = supabase.table("projects").insert(project.model_dump()).execute()
    return result.data[0]


@router.patch("/{project_id}", response_model=Project)
async def update_project(project_id: UUID, project: ProjectUpdate):
    """Update a project."""
    supabase = get_supabase_client()

    update_data = {k: v for k, v in project.model_dump().items() if v is not None}

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = supabase.table("projects").update(update_data).eq("id", str(project_id)).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Project not found")

    return result.data[0]


@router.delete("/{project_id}")
async def delete_project(project_id: UUID):
    """Delete a project (items will have project_id set to null)."""
    supabase = get_supabase_client()

    result = supabase.table("projects").delete().eq("id", str(project_id)).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Project not found")

    return {"message": "Project deleted"}
