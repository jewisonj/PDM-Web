"""Work Queue / Tasks API routes."""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from uuid import UUID
from datetime import datetime

from ..services.supabase import get_supabase_client, get_supabase_admin
from ..models.schemas import Task, TaskCreate

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[Task])
async def list_tasks(
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    item_id: Optional[UUID] = None,
    limit: int = Query(50, le=100),
    offset: int = 0,
):
    """List work queue tasks."""
    supabase = get_supabase_client()

    query = supabase.table("work_queue").select("*")

    if status:
        query = query.eq("status", status)
    if task_type:
        query = query.eq("task_type", task_type)
    if item_id:
        query = query.eq("item_id", str(item_id))

    query = query.order("created_at", desc=True).range(offset, offset + limit - 1)

    result = query.execute()
    return result.data


@router.get("/pending", response_model=list[Task])
async def get_pending_tasks(task_type: Optional[str] = None, limit: int = 10):
    """Get pending tasks for worker processing."""
    supabase = get_supabase_client()

    query = supabase.table("work_queue").select("*").eq("status", "pending")

    if task_type:
        query = query.eq("task_type", task_type)

    query = query.order("created_at").limit(limit)

    result = query.execute()
    return result.data


@router.get("/{task_id}", response_model=Task)
async def get_task(task_id: UUID):
    """Get task by ID."""
    supabase = get_supabase_client()

    result = supabase.table("work_queue").select("*").eq("id", str(task_id)).single().execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Task not found")

    return result.data


@router.post("", response_model=Task)
async def create_task(task: TaskCreate):
    """Create a new task."""
    supabase = get_supabase_client()

    task_data = task.model_dump()

    # Convert UUIDs to strings
    if task_data.get("item_id"):
        task_data["item_id"] = str(task_data["item_id"])
    if task_data.get("file_id"):
        task_data["file_id"] = str(task_data["file_id"])

    result = supabase.table("work_queue").insert(task_data).execute()
    return result.data[0]


@router.post("/generate-dxf/{item_number}")
async def queue_dxf_generation(item_number: str):
    """Queue DXF generation for an item's STEP file."""
    supabase = get_supabase_client()

    # Get item
    item_result = supabase.table("items").select("id").eq("item_number", item_number.lower()).single().execute()

    if not item_result.data:
        raise HTTPException(status_code=404, detail=f"Item {item_number} not found")

    item_id = item_result.data["id"]

    # Find STEP file
    file_result = supabase.table("files").select("id, file_path").eq("item_id", item_id).eq("file_type", "STEP").order("created_at", desc=True).limit(1).execute()

    if not file_result.data:
        raise HTTPException(status_code=404, detail=f"No STEP file found for {item_number}")

    file_id = file_result.data[0]["id"]
    file_path = file_result.data[0]["file_path"]

    # Create task
    task_data = {
        "item_id": item_id,
        "file_id": file_id,
        "task_type": "GENERATE_DXF",
        "payload": {"file_path": file_path},
        "status": "pending"
    }

    result = supabase.table("work_queue").insert(task_data).execute()
    return result.data[0]


@router.post("/generate-svg/{item_number}")
async def queue_svg_generation(item_number: str):
    """Queue SVG bend drawing generation for an item's STEP file."""
    supabase = get_supabase_client()

    # Get item
    item_result = supabase.table("items").select("id").eq("item_number", item_number.lower()).single().execute()

    if not item_result.data:
        raise HTTPException(status_code=404, detail=f"Item {item_number} not found")

    item_id = item_result.data["id"]

    # Find STEP file
    file_result = supabase.table("files").select("id, file_path").eq("item_id", item_id).eq("file_type", "STEP").order("created_at", desc=True).limit(1).execute()

    if not file_result.data:
        raise HTTPException(status_code=404, detail=f"No STEP file found for {item_number}")

    file_id = file_result.data[0]["id"]
    file_path = file_result.data[0]["file_path"]

    # Create task
    task_data = {
        "item_id": item_id,
        "file_id": file_id,
        "task_type": "GENERATE_SVG",
        "payload": {"file_path": file_path},
        "status": "pending"
    }

    result = supabase.table("work_queue").insert(task_data).execute()
    return result.data[0]


@router.patch("/{task_id}/start")
async def start_task(task_id: UUID):
    """Mark task as processing (for worker)."""
    supabase = get_supabase_admin()

    result = supabase.table("work_queue").update({
        "status": "processing",
        "started_at": datetime.utcnow().isoformat()
    }).eq("id", str(task_id)).eq("status", "pending").execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Task not found or already started")

    return result.data[0]


@router.patch("/{task_id}/complete")
async def complete_task(task_id: UUID, error_message: Optional[str] = None):
    """Mark task as completed or failed."""
    supabase = get_supabase_admin()

    update_data = {
        "status": "failed" if error_message else "completed",
        "completed_at": datetime.utcnow().isoformat()
    }

    if error_message:
        update_data["error_message"] = error_message

    result = supabase.table("work_queue").update(update_data).eq("id", str(task_id)).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Task not found")

    return result.data[0]


@router.delete("/{task_id}")
async def delete_task(task_id: UUID):
    """Delete a task."""
    supabase = get_supabase_client()

    result = supabase.table("work_queue").delete().eq("id", str(task_id)).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Task not found")

    return {"message": "Task deleted"}
