"""Workspace comparison API routes.

Compares local Creo workspace files against the PDM vault (Supabase).
Called by workspace.html running inside Creo's embedded browser.
"""

import re

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

from ..services.supabase import get_supabase_admin

router = APIRouter(prefix="/workspace", tags=["workspace"])


class WorkspaceFile(BaseModel):
    filename: str
    fullPath: Optional[str] = None
    lastWriteTime: Optional[str] = None


class WorkspaceCompareRequest(BaseModel):
    workspacePath: Optional[str] = None
    files: list[WorkspaceFile]


class CompareResult(BaseModel):
    file: str
    status: str
    description: str = ""
    workspaceTime: str = ""
    vaultTime: str = ""


class WorkspaceCompareResponse(BaseModel):
    upToDate: list[CompareResult] = []
    needCheckIn: list[CompareResult] = []
    needUpdate: list[CompareResult] = []
    notInVault: list[CompareResult] = []


def strip_creo_version(filename: str) -> str:
    """Strip Creo version number from filename.

    Creo's ListFiles returns versioned filenames like:
        stp02810.prt.3 -> stp02810.prt
        xxa00010.asm.27 -> xxa00010.asm
        sta01050.prt -> sta01050.prt  (no version, unchanged)
    """
    return re.sub(r"\.\d+$", "", filename)


def extract_item_number(filename: str) -> str:
    """Extract item_number from a Creo filename.

    Handles versioned filenames (Creo appends .version):
        stp02810.prt.3 -> stp02810
        stp02810.prt -> stp02810
        mmc93337a110.prt -> mmc93337a110
        xxa00010.asm.27 -> xxa00010
        spnca3102e14s-2pb.prt -> spnca3102e14s-2pb
    """
    base = strip_creo_version(filename).lower()

    # Strip known Creo/CAD extensions
    base = re.sub(r"\.(prt|asm|drw|stp|step|dxf|svg|pdf)$", "", base)

    # Check special prefixes FIRST (they contain mixed alpha+digits after the prefix)
    # McMaster pattern: mmc + alphanumeric (e.g., mmc93337a110, mmc3006t426)
    match = re.match(r"^(mmc[a-z0-9]+)", base)
    if match:
        return match.group(1)

    # Supplier pattern: spn + alphanumeric (may include dashes/underscores)
    match = re.match(r"^(spn[a-z0-9_-]+)", base)
    if match:
        return match.group(1)

    # Reference pattern: zzz + alphanumeric
    match = re.match(r"^(zzz[a-z0-9]+)", base)
    if match:
        return match.group(1)

    # Standard pattern: 3 letters + 4-6 digits (e.g., stp02810, sta01050)
    match = re.match(r"^([a-z]{3}\d{4,6})", base)
    if match:
        return match.group(1)

    # Fallback: return the base without extension
    return base


def parse_local_timestamp(time_str: str) -> Optional[datetime]:
    """Parse a local timestamp string from the browser/PowerShell.

    Handles formats like:
        '1/15/2025, 3:04:25 PM'
        '12/29/2025, 5:51:48 PM'
        'M/d/yyyy, h:mm:ss tt'
    """
    if not time_str or time_str == "Unknown":
        return None
    formats = [
        "%m/%d/%Y, %I:%M:%S %p",
        "%m/%d/%Y, %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(time_str.strip(), fmt)
        except ValueError:
            continue
    return None


def parse_vault_timestamp(time_str: str) -> Optional[datetime]:
    """Parse an ISO timestamp from Supabase and convert UTC to local time.

    Supabase stores timestamps in UTC. Local file times from PowerShell
    are in the machine's local timezone. Convert vault times to local
    so comparisons are apples-to-apples.
    """
    if not time_str:
        return None
    try:
        dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        # Convert to local time, then strip tzinfo for naive comparison
        local_dt = dt.astimezone()
        return local_dt.replace(tzinfo=None)
    except (ValueError, AttributeError):
        return None


def format_vault_time(time_str: str) -> str:
    """Format a Supabase ISO timestamp for display."""
    dt = parse_vault_timestamp(time_str)
    if not dt:
        return ""
    # Use manual formatting for cross-platform compatibility
    # (%-m is Linux-only, %#m is Windows-only)
    hour = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{dt.month}/{dt.day}/{dt.year}, {hour}:{dt.minute:02d}:{dt.second:02d} {ampm}"


@router.post("/compare", response_model=WorkspaceCompareResponse)
async def compare_workspace(data: WorkspaceCompareRequest):
    """Compare workspace files against the PDM vault.

    For each file in the workspace:
    - Extract item_number from filename
    - Look up item and associated files in the database
    - Compare timestamps to determine status
    - Return categorized results
    """
    supabase = get_supabase_admin()

    if not data.files:
        return WorkspaceCompareResponse()

    # Extract unique item numbers
    filename_to_item = {}
    for f in data.files:
        item_num = extract_item_number(f.filename)
        filename_to_item[f.filename] = item_num

    unique_item_numbers = list(set(filename_to_item.values()))

    # Batch lookup: get all items at once
    items_by_number = {}
    # Supabase .in_() has a practical limit, batch in groups of 100
    for i in range(0, len(unique_item_numbers), 100):
        batch = unique_item_numbers[i : i + 100]
        result = (
            supabase.table("items")
            .select("id, item_number, name, description, updated_at")
            .in_("item_number", batch)
            .execute()
        )
        for item in result.data:
            items_by_number[item["item_number"]] = item

    # Batch lookup: get all files for found items
    item_ids = [item["id"] for item in items_by_number.values()]
    files_by_item_and_name = {}
    if item_ids:
        for i in range(0, len(item_ids), 100):
            batch_ids = item_ids[i : i + 100]
            files_result = (
                supabase.table("files")
                .select("id, item_id, file_name, file_size, created_at, updated_at")
                .in_("item_id", batch_ids)
                .execute()
            )
            for file_rec in files_result.data:
                key = (file_rec["item_id"], file_rec["file_name"].lower())
                # Keep the latest file record
                existing = files_by_item_and_name.get(key)
                if not existing or (file_rec.get("updated_at") or file_rec.get("created_at") or "") > (
                    existing.get("updated_at") or existing.get("created_at") or ""
                ):
                    files_by_item_and_name[key] = file_rec

    # Build comparison results
    response = WorkspaceCompareResponse()

    for ws_file in data.files:
        filename = ws_file.filename
        item_number = filename_to_item[filename]
        local_time_str = ws_file.lastWriteTime or ""

        item = items_by_number.get(item_number)

        if not item:
            # Item doesn't exist in vault at all
            response.notInVault.append(
                CompareResult(
                    file=filename,
                    status="Not In Vault",
                    description="",
                    workspaceTime=local_time_str,
                    vaultTime="",
                )
            )
            continue

        description = item.get("name") or item.get("description") or ""

        # Look up the specific file (strip Creo version number for matching)
        clean_filename = strip_creo_version(filename).lower()
        file_key = (item["id"], clean_filename)
        vault_file = files_by_item_and_name.get(file_key)

        if not vault_file:
            # Item exists but this specific file hasn't been uploaded
            response.notInVault.append(
                CompareResult(
                    file=filename,
                    status="Not In Vault",
                    description=description,
                    workspaceTime=local_time_str,
                    vaultTime="",
                )
            )
            continue

        # Both exist - determine status by comparing timestamps
        vault_time_raw = vault_file.get("updated_at") or vault_file.get("created_at") or ""
        vault_time_display = format_vault_time(vault_time_raw)

        local_dt = parse_local_timestamp(local_time_str)
        vault_dt = parse_vault_timestamp(vault_time_raw)

        if local_dt and vault_dt:
            diff_seconds = (local_dt - vault_dt).total_seconds()
            if abs(diff_seconds) < 120:
                # Within 2 minutes - consider up to date
                response.upToDate.append(
                    CompareResult(
                        file=filename,
                        status="Up To Date",
                        description=description,
                        workspaceTime=local_time_str,
                        vaultTime=vault_time_display,
                    )
                )
            elif diff_seconds > 0:
                # Local is newer
                response.needCheckIn.append(
                    CompareResult(
                        file=filename,
                        status="Modified Locally",
                        description=description,
                        workspaceTime=local_time_str,
                        vaultTime=vault_time_display,
                    )
                )
            else:
                # Vault is newer
                response.needUpdate.append(
                    CompareResult(
                        file=filename,
                        status="Out of Date",
                        description=description,
                        workspaceTime=local_time_str,
                        vaultTime=vault_time_display,
                    )
                )
        else:
            # Can't compare timestamps - default to "In Vault"
            response.upToDate.append(
                CompareResult(
                    file=filename,
                    status="In Vault",
                    description=description,
                    workspaceTime=local_time_str,
                    vaultTime=vault_time_display,
                )
            )

    return response
