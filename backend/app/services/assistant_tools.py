"""
AI Assistant Tools - Read-only tools for Claude to query PDM data.

Each tool is a function that returns JSON-serializable data, plus an Anthropic
tool definition for the API. Tools use get_supabase_admin() for data access.
"""

import json
from typing import Any, Optional

from .supabase import get_supabase_admin


# =============================================================================
# Tool Definitions (for Anthropic API)
# =============================================================================

TOOL_DEFINITIONS = [
    {
        "name": "search_items",
        "description": (
            "Search for items by item number fragment or name. Call this when the user "
            "asks to find parts, look up items, or search for something by name or number. "
            "Returns a list of matching items with their basic info."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term - matches against item_number and name (case-insensitive)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (default 20, max 50)",
                    "default": 20
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_item",
        "description": (
            "Get full details for a specific item by its item number. Call this when the user "
            "asks about a specific part's properties, revision, lifecycle state, material, etc. "
            "Returns item details including project name and list of associated files."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "item_number": {
                    "type": "string",
                    "description": "The item number (e.g., 'csp00200', 'stp02810'). Will be lowercased."
                }
            },
            "required": ["item_number"]
        }
    },
    {
        "name": "get_bom_tree",
        "description": (
            "Get the full recursive BOM (Bill of Materials) tree for an assembly. Call this when "
            "the user asks what an assembly contains, how many of a part are used, counts of "
            "components, or anything about assembly structure. Returns the full tree with quantities. "
            "To count total parts: multiply each part's quantity by all ancestor quantities, then sum."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "item_number": {
                    "type": "string",
                    "description": "The assembly item number to get BOM for"
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum recursion depth (default 10)",
                    "default": 10
                }
            },
            "required": ["item_number"]
        }
    },
    {
        "name": "get_where_used",
        "description": (
            "Get list of assemblies that contain a specific item (reverse BOM lookup). Call this "
            "when the user asks where a part is used, what assemblies contain it, or parent items."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "item_number": {
                    "type": "string",
                    "description": "The item number to find parent assemblies for"
                }
            },
            "required": ["item_number"]
        }
    },
    {
        "name": "list_item_files",
        "description": (
            "List files associated with an item. Call this when the user asks about files, "
            "drawings, prints, or documents for a part. Use file_type='PDF' to find prints/drawings."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "item_number": {
                    "type": "string",
                    "description": "The item number to list files for"
                },
                "file_type": {
                    "type": "string",
                    "description": "Filter by file type: PDF, STEP, DXF, SVG, CAD, IMAGE, or OTHER",
                    "enum": ["PDF", "STEP", "DXF", "SVG", "CAD", "IMAGE", "OTHER"]
                }
            },
            "required": ["item_number"]
        }
    },
    {
        "name": "get_file_download_link",
        "description": (
            "Get a signed download URL for a specific file. Call this after list_item_files to "
            "provide the user with a clickable download link. Returns a URL valid for 1 hour."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {
                    "type": "string",
                    "description": "The file ID (UUID) from list_item_files result"
                }
            },
            "required": ["file_id"]
        }
    },
    {
        "name": "list_mrp_projects",
        "description": (
            "List MRP (manufacturing) projects with their timelines. Call this when the user asks "
            "about projects, jobs, schedules, due dates, what's in progress, or what's shipping soon. "
            "Returns project code, customer, description, status, start date, and due date."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Optional filter by project status (e.g., 'active', 'complete')"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_mrp_project",
        "description": (
            "Get details for one MRP project by its project code, including timeline dates, "
            "top assembly, part count, and shop-floor completion progress by workstation. "
            "Call this when the user asks about a specific job/project's status or progress."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_code": {
                    "type": "string",
                    "description": "The project code (exact or partial, case-insensitive)"
                }
            },
            "required": ["project_code"]
        }
    },
    {
        "name": "get_project_cost_estimate",
        "description": (
            "Get the full cost estimate for an MRP project: labor, material, outsourced, and "
            "purchased cost totals plus overhead, and the most expensive line items. Call this "
            "when the user asks what a project costs, price breakdowns, or which parts drive cost. "
            "Uses the same calculation as the MRP cost page."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_code": {
                    "type": "string",
                    "description": "The project code (exact or partial, case-insensitive)"
                },
                "top_n": {
                    "type": "integer",
                    "description": "How many line items to include, sorted by extended cost (default 20, max 50)",
                    "default": 20
                }
            },
            "required": ["project_code"]
        }
    },
    {
        "name": "get_item_routing",
        "description": (
            "Get the manufacturing routing (operation steps) for an item: workstations in sequence, "
            "estimated time per operation, and whether steps are outsourced. Call this when the user "
            "asks how a part is made, what operations it needs, or estimated labor time."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "item_number": {
                    "type": "string",
                    "description": "The item number to get routing for"
                }
            },
            "required": ["item_number"]
        }
    },
    {
        "name": "list_work_queue_tasks",
        "description": (
            "List background work queue tasks (DXF flattening, bend drawings, etc.) with their "
            "status and any error messages. Call this when the user asks about pending/failed "
            "tasks, the work queue, or why a generated file hasn't appeared."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Optional filter by status",
                    "enum": ["pending", "processing", "completed", "failed"]
                },
                "task_type": {
                    "type": "string",
                    "description": "Optional filter by task type (e.g., 'flatten_dxf', 'bend_svg')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (default 20, max 50)",
                    "default": 20
                }
            },
            "required": []
        }
    },
    {
        "name": "get_pricing_settings",
        "description": (
            "Get current pricing configuration: cost settings (labor rate, overhead multiplier, "
            "default material $/lb), and workstation hourly rates / outsourced cost defaults. "
            "Call this when the user asks about rates, markup, overhead, or how costs are calculated."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "list_raw_materials",
        "description": (
            "List raw material stock with prices and inventory levels. Call this when the user asks "
            "about material prices, what stock is on hand or on order, or raw material specs "
            "(profile, dimensions, weight per foot)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Optional search term matched against material code, part number, and description"
                },
                "material_type": {
                    "type": "string",
                    "description": "Optional filter by material type (e.g., 'SM' for sheet metal, 'TUBE')"
                }
            },
            "required": []
        }
    }
]


# =============================================================================
# Tool Implementations
# =============================================================================

def search_items(query: str, limit: int = 20) -> dict[str, Any]:
    """Search for items by item_number or name."""
    supabase = get_supabase_admin()

    limit = min(limit, 50)  # Cap at 50

    result = supabase.table("items").select(
        "item_number, name, revision, lifecycle_state, material, thickness"
    ).or_(
        f"item_number.ilike.%{query}%,name.ilike.%{query}%"
    ).order("item_number").limit(limit).execute()

    return {
        "count": len(result.data),
        "items": result.data
    }


def get_item(item_number: str) -> dict[str, Any]:
    """Get full item details by item_number."""
    supabase = get_supabase_admin()

    normalized = item_number.lower().strip()

    try:
        result = supabase.table("items").select(
            "*, projects(name)"
        ).eq("item_number", normalized).single().execute()
    except Exception:
        return {"error": f"Item '{item_number}' not found"}

    if not result.data:
        return {"error": f"Item '{item_number}' not found"}

    item = result.data

    # Flatten project name
    project_data = item.pop("projects", None)
    item["project_name"] = project_data.get("name") if project_data else None

    # Get file list (summary only)
    files_result = supabase.table("files").select(
        "id, file_name, file_type, revision, iteration"
    ).eq("item_id", item["id"]).execute()

    item["files"] = files_result.data or []

    return item


def get_bom_tree(item_number: str, max_depth: int = 10) -> dict[str, Any]:
    """Get recursive BOM tree for an assembly."""
    supabase = get_supabase_admin()

    normalized = item_number.lower().strip()

    # Get parent item
    try:
        item_result = supabase.table("items").select(
            "id, item_number, name, lifecycle_state"
        ).eq("item_number", normalized).single().execute()
    except Exception:
        return {"error": f"Item '{item_number}' not found"}

    if not item_result.data:
        return {"error": f"Item '{item_number}' not found"}

    def build_tree(item_id: str, depth: int = 0) -> list[dict]:
        """Recursively build BOM tree (trimmed output for token efficiency)."""
        if depth >= max_depth:
            return []

        bom_result = supabase.table("bom").select(
            "child_item_id, quantity"
        ).eq("parent_item_id", item_id).execute()

        children = []
        for entry in bom_result.data:
            child_result = supabase.table("items").select(
                "id, item_number, name, lifecycle_state"
            ).eq("id", entry["child_item_id"]).maybe_single().execute()

            if child_result.data:
                child_node = {
                    "item_number": child_result.data["item_number"],
                    "name": child_result.data["name"],
                    "lifecycle_state": child_result.data["lifecycle_state"],
                    "quantity": entry["quantity"],
                    "children": build_tree(entry["child_item_id"], depth + 1)
                }
                children.append(child_node)

        return children

    root = item_result.data
    tree = {
        "item_number": root["item_number"],
        "name": root["name"],
        "lifecycle_state": root["lifecycle_state"],
        "quantity": 1,
        "children": build_tree(root["id"])
    }

    return tree


def get_where_used(item_number: str) -> dict[str, Any]:
    """Get list of parent assemblies containing this item."""
    supabase = get_supabase_admin()

    normalized = item_number.lower().strip()

    # Get item ID
    try:
        item_result = supabase.table("items").select("id").eq(
            "item_number", normalized
        ).single().execute()
    except Exception:
        return {"error": f"Item '{item_number}' not found"}

    if not item_result.data:
        return {"error": f"Item '{item_number}' not found"}

    # Get parent items
    bom_result = supabase.table("bom").select(
        "parent_item_id, quantity"
    ).eq("child_item_id", item_result.data["id"]).execute()

    parents = []
    for entry in bom_result.data:
        parent_result = supabase.table("items").select(
            "item_number, name, lifecycle_state"
        ).eq("id", entry["parent_item_id"]).maybe_single().execute()

        if parent_result.data:
            parents.append({
                "item_number": parent_result.data["item_number"],
                "name": parent_result.data["name"],
                "lifecycle_state": parent_result.data["lifecycle_state"],
                "quantity": entry["quantity"]
            })

    return {
        "item_number": normalized,
        "used_in": parents,
        "count": len(parents)
    }


def list_item_files(item_number: str, file_type: Optional[str] = None) -> dict[str, Any]:
    """List files for an item, optionally filtered by type."""
    supabase = get_supabase_admin()

    normalized = item_number.lower().strip()

    # Get item ID
    try:
        item_result = supabase.table("items").select("id").eq(
            "item_number", normalized
        ).single().execute()
    except Exception:
        return {"error": f"Item '{item_number}' not found"}

    if not item_result.data:
        return {"error": f"Item '{item_number}' not found"}

    # Get files
    query = supabase.table("files").select(
        "id, file_name, file_type, revision, iteration, created_at"
    ).eq("item_id", item_result.data["id"])

    if file_type:
        query = query.eq("file_type", file_type.upper())

    result = query.order("created_at", desc=True).execute()

    return {
        "item_number": normalized,
        "files": result.data or [],
        "count": len(result.data) if result.data else 0
    }


def get_file_download_link(file_id: str) -> dict[str, Any]:
    """Generate a signed download URL for a file."""
    supabase = get_supabase_admin()

    try:
        file_result = supabase.table("files").select(
            "file_path, file_name"
        ).eq("id", file_id).single().execute()
    except Exception:
        return {"error": f"File '{file_id}' not found"}

    if not file_result.data:
        return {"error": f"File '{file_id}' not found"}

    file_path = file_result.data["file_path"]

    if not file_path:
        return {"error": "File has no storage path"}

    # Parse bucket and path
    parts = file_path.split("/", 1)
    if len(parts) == 2:
        bucket = parts[0]
        storage_path = parts[1]
    else:
        bucket = "pdm-files"
        storage_path = file_path

    # Create signed URL (valid for 1 hour)
    try:
        url_result = supabase.storage.from_(bucket).create_signed_url(storage_path, 3600)
        return {
            "url": url_result["signedURL"],
            "filename": file_result.data["file_name"],
            "expires_in": 3600
        }
    except Exception as e:
        return {"error": f"Could not generate download URL: {str(e)}"}


def _find_mrp_project(project_code: str) -> Optional[dict[str, Any]]:
    """Find an MRP project by exact or partial project_code (case-insensitive)."""
    supabase = get_supabase_admin()

    code = project_code.strip()

    result = supabase.table("mrp_projects").select("*").ilike(
        "project_code", code
    ).execute()

    if not result.data:
        result = supabase.table("mrp_projects").select("*").ilike(
            "project_code", f"%{code}%"
        ).limit(2).execute()

    if not result.data:
        return None

    if len(result.data) > 1:
        return {"_ambiguous": [p["project_code"] for p in result.data]}

    return result.data[0]


def list_mrp_projects(status: Optional[str] = None) -> dict[str, Any]:
    """List MRP projects with timeline info."""
    supabase = get_supabase_admin()

    query = supabase.table("mrp_projects").select(
        "project_code, description, customer, status, start_date, due_date, "
        "created_at, items:top_assembly_id(item_number, name)"
    )

    if status:
        query = query.ilike("status", status)

    result = query.order("due_date", desc=False).execute()

    projects = []
    for p in result.data or []:
        top = p.pop("items", None)
        p["top_assembly"] = top.get("item_number") if top else None
        projects.append(p)

    return {"count": len(projects), "projects": projects}


def get_mrp_project(project_code: str) -> dict[str, Any]:
    """Get one MRP project with parts count and completion progress."""
    supabase = get_supabase_admin()

    project = _find_mrp_project(project_code)
    if project is None:
        return {"error": f"MRP project '{project_code}' not found"}
    if "_ambiguous" in project:
        return {
            "error": f"Multiple projects match '{project_code}'",
            "matches": project["_ambiguous"]
        }

    pid = project["id"]

    # Top assembly info
    if project.get("top_assembly_id"):
        top_result = supabase.table("items").select("item_number, name").eq(
            "id", project["top_assembly_id"]
        ).maybe_single().execute()
        if top_result and top_result.data:
            project["top_assembly"] = top_result.data

    # Parts summary
    parts_result = supabase.table("mrp_project_parts").select(
        "quantity"
    ).eq("project_id", pid).execute()
    part_lines = parts_result.data or []
    project["part_line_count"] = len(part_lines)
    project["total_part_qty"] = sum(p.get("quantity") or 0 for p in part_lines)

    # Completion progress by workstation
    completion_result = supabase.table("part_completion").select(
        "qty_complete, workstations(station_code, station_name)"
    ).eq("project_id", pid).execute()

    by_station: dict[str, int] = {}
    for row in completion_result.data or []:
        ws = row.get("workstations") or {}
        station = ws.get("station_name") or ws.get("station_code") or "Unknown"
        by_station[station] = by_station.get(station, 0) + (row.get("qty_complete") or 0)

    project["completion_by_station"] = by_station

    # Drop internal IDs to save tokens
    for key in ("id", "top_assembly_id", "print_packet_path"):
        project.pop(key, None)

    return project


def get_project_cost_estimate(project_code: str, top_n: int = 20) -> dict[str, Any]:
    """Get cost estimate for an MRP project (reuses the MRP page calculation)."""
    from .cost_estimate import compute_project_cost_estimate

    project = _find_mrp_project(project_code)
    if project is None:
        return {"error": f"MRP project '{project_code}' not found"}
    if "_ambiguous" in project:
        return {
            "error": f"Multiple projects match '{project_code}'",
            "matches": project["_ambiguous"]
        }

    estimate = compute_project_cost_estimate(project["id"])
    if estimate is None:
        return {"error": f"Project '{project['project_code']}' has no parts to estimate"}

    top_n = min(max(top_n, 1), 50)

    items = estimate.pop("items", [])
    items.sort(key=lambda i: i.get("extended_cost") or 0, reverse=True)
    for item in items:
        item.pop("item_id", None)

    estimate["project_code"] = project["project_code"]
    estimate.pop("project_id", None)
    estimate["item_count"] = len(items)
    estimate["top_items_by_cost"] = items[:top_n]
    if len(items) > top_n:
        estimate["note"] = (
            f"Showing top {top_n} of {len(items)} line items by extended cost. "
            "Totals above include ALL items."
        )

    return estimate


def get_item_routing(item_number: str) -> dict[str, Any]:
    """Get manufacturing routing steps for an item."""
    supabase = get_supabase_admin()

    normalized = item_number.lower().strip()

    try:
        item_result = supabase.table("items").select("id, item_number, name").eq(
            "item_number", normalized
        ).single().execute()
    except Exception:
        return {"error": f"Item '{item_number}' not found"}

    if not item_result.data:
        return {"error": f"Item '{item_number}' not found"}

    routing_result = supabase.table("routing").select(
        "sequence, est_time_min, notes, cost_override, "
        "workstations(station_code, station_name, is_outsourced, hourly_rate, outsourced_cost_default)"
    ).eq("item_id", item_result.data["id"]).order("sequence").execute()

    steps = []
    total_time = 0.0
    for step in routing_result.data or []:
        ws = step.get("workstations") or {}
        time_min = float(step.get("est_time_min") or 0)
        total_time += time_min
        steps.append({
            "sequence": step.get("sequence"),
            "station": ws.get("station_name") or ws.get("station_code"),
            "est_time_min": time_min,
            "is_outsourced": ws.get("is_outsourced", False),
            "cost_override": step.get("cost_override"),
            "notes": step.get("notes"),
        })

    return {
        "item_number": item_result.data["item_number"],
        "name": item_result.data["name"],
        "steps": steps,
        "step_count": len(steps),
        "total_est_time_min": total_time,
    }


def list_work_queue_tasks(
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    limit: int = 20,
) -> dict[str, Any]:
    """List background work queue tasks with item numbers."""
    supabase = get_supabase_admin()

    limit = min(limit, 50)

    query = supabase.table("work_queue").select(
        "task_type, status, error_message, created_at, started_at, completed_at, "
        "items(item_number)"
    )

    if status:
        query = query.eq("status", status)
    if task_type:
        query = query.eq("task_type", task_type)

    result = query.order("created_at", desc=True).limit(limit).execute()

    tasks = []
    for t in result.data or []:
        item = t.pop("items", None)
        t["item_number"] = item.get("item_number") if item else None
        tasks.append(t)

    return {"count": len(tasks), "tasks": tasks}


def get_pricing_settings() -> dict[str, Any]:
    """Get cost settings and workstation rates."""
    supabase = get_supabase_admin()

    settings_result = supabase.table("cost_settings").select(
        "setting_key, setting_value, description"
    ).execute()

    ws_result = supabase.table("workstations").select(
        "station_code, station_name, hourly_rate, is_outsourced, outsourced_cost_default"
    ).order("sort_order").execute()

    return {
        "cost_settings": settings_result.data or [],
        "workstations": ws_result.data or [],
    }


def list_raw_materials(
    query: Optional[str] = None,
    material_type: Optional[str] = None,
) -> dict[str, Any]:
    """List raw materials with prices and stock levels."""
    supabase = get_supabase_admin()

    q = supabase.table("raw_materials").select(
        "material_code, material_type, part_number, description, profile, "
        "dim1_in, dim2_in, wall_or_thk_in, stock_length_ft, weight_lb_per_ft, "
        "price_per_unit, qty_on_hand, qty_on_order, reorder_point"
    )

    if query:
        q = q.or_(
            f"material_code.ilike.%{query}%,"
            f"part_number.ilike.%{query}%,"
            f"description.ilike.%{query}%"
        )
    if material_type:
        q = q.eq("material_type", material_type.upper())

    result = q.order("material_code").limit(50).execute()

    return {"count": len(result.data or []), "materials": result.data or []}


# =============================================================================
# Tool Dispatcher
# =============================================================================

TOOL_FUNCTIONS = {
    "search_items": search_items,
    "get_item": get_item,
    "get_bom_tree": get_bom_tree,
    "get_where_used": get_where_used,
    "list_item_files": list_item_files,
    "get_file_download_link": get_file_download_link,
    "list_mrp_projects": list_mrp_projects,
    "get_mrp_project": get_mrp_project,
    "get_project_cost_estimate": get_project_cost_estimate,
    "get_item_routing": get_item_routing,
    "list_work_queue_tasks": list_work_queue_tasks,
    "get_pricing_settings": get_pricing_settings,
    "list_raw_materials": list_raw_materials,
}

# Human-readable summaries for SSE status events
TOOL_SUMMARIES = {
    "search_items": "Searching for items...",
    "get_item": "Looking up item details...",
    "get_bom_tree": "Expanding BOM tree...",
    "get_where_used": "Finding where item is used...",
    "list_item_files": "Listing files...",
    "get_file_download_link": "Generating download link...",
    "list_mrp_projects": "Listing MRP projects...",
    "get_mrp_project": "Looking up project details...",
    "get_project_cost_estimate": "Calculating project cost estimate...",
    "get_item_routing": "Looking up routing...",
    "list_work_queue_tasks": "Checking work queue...",
    "get_pricing_settings": "Loading pricing settings...",
    "list_raw_materials": "Listing raw materials...",
}


def run_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """
    Execute a tool by name with given arguments.

    Returns the tool result as a dict. If the tool doesn't exist or fails,
    returns an error dict that Claude can report to the user.
    """
    if name not in TOOL_FUNCTIONS:
        return {"error": f"Unknown tool: {name}"}

    try:
        return TOOL_FUNCTIONS[name](**arguments)
    except Exception as e:
        return {"error": f"Tool '{name}' failed: {str(e)}"}


def get_tool_summary(name: str, arguments: dict[str, Any]) -> str:
    """Get a human-readable summary of what a tool is doing."""
    base = TOOL_SUMMARIES.get(name, f"Running {name}...")

    # Add context for specific tools
    if name == "get_item" and "item_number" in arguments:
        return f"Looking up {arguments['item_number']}..."
    elif name == "get_bom_tree" and "item_number" in arguments:
        return f"Expanding BOM for {arguments['item_number']}..."
    elif name == "search_items" and "query" in arguments:
        return f"Searching for '{arguments['query']}'..."
    elif name == "list_item_files" and "item_number" in arguments:
        return f"Finding files for {arguments['item_number']}..."
    elif name == "get_where_used" and "item_number" in arguments:
        return f"Finding where {arguments['item_number']} is used..."
    elif name == "get_mrp_project" and "project_code" in arguments:
        return f"Looking up project {arguments['project_code']}..."
    elif name == "get_project_cost_estimate" and "project_code" in arguments:
        return f"Calculating cost estimate for {arguments['project_code']}..."
    elif name == "get_item_routing" and "item_number" in arguments:
        return f"Looking up routing for {arguments['item_number']}..."

    return base
