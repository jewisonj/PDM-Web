"""MRP (Manufacturing Resource Planning) API routes."""

from fastapi import APIRouter, HTTPException
from uuid import UUID

from ..services.print_packet import generate_print_packet, get_existing_packet

router = APIRouter(prefix="/mrp", tags=["mrp"])


@router.post("/projects/{project_id}/print-packet")
async def create_print_packet(project_id: UUID):
    """
    Generate a new print packet for an MRP project.

    This creates a combined PDF with:
    - Cover sheet with project info and categorized parts lists
    - Each part's PDF with stamp overlays showing routing info

    Returns the download URL, storage path, and generation timestamp.
    """
    try:
        result = await generate_print_packet(str(project_id))
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate print packet: {str(e)}")


@router.get("/projects/{project_id}/print-packet")
async def get_print_packet(project_id: UUID):
    """
    Get the existing print packet for an MRP project.

    Returns the download URL if a packet exists, or 404 if not.
    """
    result = await get_existing_packet(str(project_id))

    if not result:
        raise HTTPException(status_code=404, detail="No print packet found for this project")

    return result
