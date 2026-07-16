"""Master Design Book routes — rev-controlled section booklets.

See Documentation/36-MASTER-DESIGN-BOOK-PLAN.md. The frontend computes the
book model + section descriptors (frontend/src/utils/masterDesignBook.ts) and
POSTs them here; this layer diffs, renders, versions, and serves.

All PDF byte responses are plain Response — never StreamingResponse(BytesIO)
(Starlette iterates BytesIO line-by-line, glacial).
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mrp/design-books", tags=["design-books"])


class DesignBookMeta(BaseModel):
    title: Optional[str] = None
    product_item_number: Optional[str] = None
    template_project_code: Optional[str] = None
    create: bool = False
    rebaseline: bool = False
    expected_book_rev: Optional[int] = None
    allow_qty_mismatch: bool = False


class DesignBookPayload(BaseModel):
    """meta + section descriptors from masterSections() (masterDesignBook.ts)."""
    meta: DesignBookMeta
    sections: list[dict[str, Any]]


def _handle(book_code: str, fn, *args):
    """Common service-exception mapping."""
    from ..services.master_design_book import BookNotFound, BookConflict, QtyGateError
    try:
        return fn(*args)
    except BookNotFound as e:
        raise HTTPException(status_code=404, detail=f"Not found: {e}")
    except BookConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except QtyGateError as e:
        raise HTTPException(status_code=400, detail={
            "message": "Template quantities do not match the BOM rollup — fix the data or set allow_qty_mismatch",
            "mismatches": e.mismatches,
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Design book operation failed for {book_code}")
        raise HTTPException(status_code=500, detail="Design book operation failed")


@router.get("")
async def list_design_books():
    from ..services.master_design_book import list_books
    return _handle("*", lambda: {"books": list_books()})


@router.get("/{book_code}")
async def get_design_book(book_code: str):
    from ..services.master_design_book import get_book_detail
    return _handle(book_code, get_book_detail, book_code)


@router.post("/{book_code}/check")
async def check_design_book(book_code: str, payload: DesignBookPayload):
    """Dry run: resolve prints (no downloads), hash, diff, derive reasons. No writes."""
    from ..services.master_design_book import check_master_book
    return _handle(book_code, check_master_book, book_code, payload.model_dump())


@router.post("/{book_code}/update")
async def update_design_book(book_code: str, payload: DesignBookPayload):
    """Commit: render changed sections, upload, bump revs, issue the change notice."""
    from ..services.master_design_book import update_master_book
    return _handle(book_code, update_master_book, book_code, payload.model_dump())


@router.post("/{book_code}/full")
async def full_design_book(book_code: str):
    """Merged full book by byte-concat of the current stored section PDFs."""
    from ..services.master_design_book import build_full_book
    result = _handle(book_code, build_full_book, book_code)
    filename = f"{result['book_code']}-master-design-book-rev{result['book_rev']}.pdf"
    return Response(
        content=result["pdf"],
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Pages": str(result["pages"]),
            "X-Sections": str(result["sections"]),
            "X-Stored-Path": result["stored_path"] or "",
        },
    )


@router.get("/{book_code}/sections/{section_code}/url")
async def section_url(book_code: str, section_code: str):
    from ..services.master_design_book import get_section_url
    return _handle(book_code, get_section_url, book_code, section_code)


@router.get("/{book_code}/changes/{to_rev}/url")
async def change_notice_url(book_code: str, to_rev: int):
    from ..services.master_design_book import get_change_notice_url
    return _handle(book_code, get_change_notice_url, book_code, to_rev)


@router.get("/{book_code}/purchase-list")
async def purchase_list_csv(book_code: str):
    """Download the buy list as a CSV file for ordering.

    Extracts purchased items from the spine section's buyList payload.
    Includes vendor bundles as separate entries.
    """
    from ..services.master_design_book import get_purchase_list_csv
    result = _handle(book_code, get_purchase_list_csv, book_code)
    filename = f"{book_code}-purchase-list-rev{result['book_rev']}.csv"
    return Response(
        content=result["csv"],
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Items": str(result["item_count"]),
        },
    )
