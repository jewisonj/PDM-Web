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
    },
    {
        "name": "audit_project",
        "description": (
            "Run a pre-flight audit on an MRP project. Finds parts with no routing, parts missing "
            "prints (PDF) or flat patterns (DXF), supplier parts with no unit price (these show as "
            "$0 in cost estimates), and parts with no raw material assigned. Call this when the "
            "user asks if a project is ready, what's missing, or before releasing a job to the shop."
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
        "name": "get_time_analysis",
        "description": (
            "Compare estimated routing times against actual logged shop time for an MRP project. "
            "Returns per item+station: estimated min/part, quantity completed, total actual minutes, "
            "and actual min/part. Call this when the user asks how accurate time estimates are, "
            "which operations are over/under estimate, or how much time was logged."
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
        "name": "list_low_stock_materials",
        "description": (
            "List raw materials at or below their reorder point (considering on-hand plus on-order). "
            "Call this when the user asks what needs to be ordered or what's running low."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "query_database",
        "description": (
            "Run a read-only SQL SELECT query against the PDM database for questions the other "
            "tools can't answer (cross-table aggregates, custom filters, counts, sums). "
            "Use the other purpose-built tools first when they fit. "
            "Postgres syntax. Results are capped at 200 rows; always aggregate or LIMIT rather "
            "than dumping raw tables. Writes are blocked at the database level.\n"
            "Tables (key columns):\n"
            "- items(id, item_number, name, revision, lifecycle_state, project_id, material, mass, "
            "thickness, cut_length, is_supplier_part, unit_price)\n"
            "- files(id, item_id, file_type, file_name, revision, iteration, created_at)\n"
            "- bom(parent_item_id, child_item_id, quantity)\n"
            "- projects(id, name, status) -- PDM design projects\n"
            "- mrp_projects(id, project_code, description, customer, status, start_date, due_date, top_assembly_id)\n"
            "- mrp_project_parts(project_id, item_id, quantity)\n"
            "- routing(item_id, station_id, sequence, est_time_min, cost_override)\n"
            "- workstations(id, station_code, station_name, hourly_rate, is_outsourced, outsourced_cost_default)\n"
            "- routing_materials(item_id, material_id, qty_required)\n"
            "- raw_materials(id, material_code, material_type, description, profile, weight_lb_per_ft, "
            "price_per_unit, qty_on_hand, qty_on_order, reorder_point)\n"
            "- time_logs(project_id, item_id, station_id, worker, time_min, logged_at)\n"
            "- part_completion(project_id, item_id, station_id, qty_complete, completed_by, completed_at)\n"
            "- work_queue(id, item_id, file_id, task_type, status, error_message, created_at, completed_at)\n"
            "- cost_settings(setting_key, setting_value, description)\n"
            "- lifecycle_history(item_id, old_state, new_state, changed_by, changed_at)"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "A single SELECT statement (Postgres). No semicolons, no writes."
                },
                "max_rows": {
                    "type": "integer",
                    "description": "Row cap (default 200, max 500)",
                    "default": 200
                }
            },
            "required": ["sql"]
        }
    }
]


# =============================================================================
# Action Tools (write operations - require user approval before execution)
# =============================================================================
#
# When Claude calls one of these, the backend does NOT execute it. Instead it
# stores a pending action, emits an `action` SSE event, and tells Claude the
# action is awaiting user approval. The frontend renders Approve/Decline
# buttons; approval executes the action via POST /assistant/actions/{id}.

ACTION_TOOL_DEFINITIONS = [
    {
        "name": "requeue_failed_task",
        "description": (
            "Propose re-queuing a failed work queue task so the worker retries it (e.g., a failed "
            "DXF flatten). The user must approve before it executes. Get the task id from "
            "list_work_queue_tasks first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The work queue task ID (UUID) from list_work_queue_tasks"
                }
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "update_material_price",
        "description": (
            "Propose updating the price_per_unit of a raw material. The user must approve before "
            "it executes. For sheet metal (SM) the price is $/lb; for tube it is $/ft."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "material_code": {
                    "type": "string",
                    "description": "The raw material code (from list_raw_materials)"
                },
                "new_price": {
                    "type": "number",
                    "description": "The new price per unit"
                }
            },
            "required": ["material_code", "new_price"]
        }
    },
    {
        "name": "update_routing_time",
        "description": (
            "Propose changing the estimated time of one routing step. The user must approve before "
            "it executes. Identify the step by item number and sequence (from get_item_routing)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "item_number": {
                    "type": "string",
                    "description": "The item whose routing step to change"
                },
                "sequence": {
                    "type": "integer",
                    "description": "The routing step sequence number"
                },
                "new_time_min": {
                    "type": "number",
                    "description": "The new estimated time in minutes"
                }
            },
            "required": ["item_number", "sequence", "new_time_min"]
        }
    },
    {
        "name": "update_cost_setting",
        "description": (
            "Propose changing a global cost setting (e.g., default_labor_rate, overhead_multiplier, "
            "default_cs_price_per_lb). The user must approve before it executes. See "
            "get_pricing_settings for current values and available keys."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "setting_key": {
                    "type": "string",
                    "description": "The cost setting key"
                },
                "new_value": {
                    "type": "number",
                    "description": "The new numeric value"
                }
            },
            "required": ["setting_key", "new_value"]
        }
    }
]

ACTION_TOOL_NAMES = {t["name"] for t in ACTION_TOOL_DEFINITIONS}


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
        "id, task_type, status, error_message, created_at, started_at, completed_at, "
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


def audit_project(project_code: str) -> dict[str, Any]:
    """Pre-flight audit: find missing routing, files, prices, and materials."""
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

    parts_result = supabase.table("mrp_project_parts").select(
        "item_id, quantity, items(item_number, name, thickness, is_supplier_part, unit_price)"
    ).eq("project_id", pid).execute()

    parts = parts_result.data or []
    if not parts:
        return {"error": f"Project '{project['project_code']}' has no parts"}

    item_ids = [p["item_id"] for p in parts]

    # Which items have routing?
    routing_result = supabase.table("routing").select("item_id").in_("item_id", item_ids).execute()
    routed_ids = {r["item_id"] for r in (routing_result.data or [])}

    # Which items have raw materials assigned?
    rm_result = supabase.table("routing_materials").select("item_id").in_("item_id", item_ids).execute()
    material_ids = {r["item_id"] for r in (rm_result.data or [])}

    # File types per item
    files_result = supabase.table("files").select("item_id, file_type").in_("item_id", item_ids).execute()
    file_types_by_item: dict[str, set] = {}
    for f in (files_result.data or []):
        file_types_by_item.setdefault(f["item_id"], set()).add(f.get("file_type"))

    missing_routing = []
    missing_pdf = []
    missing_dxf = []
    missing_material = []
    unpriced_supplier_parts = []

    for part in parts:
        item = part.get("items") or {}
        item_id = part["item_id"]
        ref = {"item_number": item.get("item_number"), "name": item.get("name")}
        file_types = file_types_by_item.get(item_id, set())

        if item.get("is_supplier_part"):
            if not item.get("unit_price"):
                unpriced_supplier_parts.append(ref)
            continue

        if item_id not in routed_ids:
            missing_routing.append(ref)
        if item_id not in material_ids:
            missing_material.append(ref)
        if "PDF" not in file_types:
            missing_pdf.append(ref)
        # Sheet metal parts (thickness set) should have a DXF flat pattern
        if item.get("thickness") and "DXF" not in file_types:
            missing_dxf.append(ref)

    return {
        "project_code": project["project_code"],
        "part_line_count": len(parts),
        "issues": {
            "parts_missing_routing": missing_routing,
            "parts_missing_pdf_print": missing_pdf,
            "sheet_metal_parts_missing_dxf": missing_dxf,
            "parts_missing_raw_material": missing_material,
            "supplier_parts_with_no_unit_price": unpriced_supplier_parts,
        },
        "issue_counts": {
            "missing_routing": len(missing_routing),
            "missing_pdf": len(missing_pdf),
            "missing_dxf": len(missing_dxf),
            "missing_raw_material": len(missing_material),
            "unpriced_supplier_parts": len(unpriced_supplier_parts),
        },
        "clean": not any([missing_routing, missing_pdf, missing_dxf,
                          missing_material, unpriced_supplier_parts]),
    }


def get_time_analysis(project_code: str) -> dict[str, Any]:
    """Compare estimated routing times vs actual logged time per item+station."""
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

    logs_result = supabase.table("time_logs").select(
        "item_id, station_id, time_min, items(item_number, name), "
        "workstations(station_code, station_name)"
    ).eq("project_id", pid).execute()

    logs = logs_result.data or []
    if not logs:
        return {
            "project_code": project["project_code"],
            "message": "No shop time has been logged for this project yet.",
            "rows": []
        }

    # Actual minutes per (item, station)
    actual: dict[tuple, dict] = {}
    for log in logs:
        key = (log["item_id"], log["station_id"])
        if key not in actual:
            item = log.get("items") or {}
            ws = log.get("workstations") or {}
            actual[key] = {
                "item_number": item.get("item_number"),
                "name": item.get("name"),
                "station": ws.get("station_name") or ws.get("station_code"),
                "actual_total_min": 0.0,
            }
        actual[key]["actual_total_min"] += float(log.get("time_min") or 0)

    item_ids = list({k[0] for k in actual})

    # Estimated min/part per (item, station)
    routing_result = supabase.table("routing").select(
        "item_id, station_id, est_time_min"
    ).in_("item_id", item_ids).execute()
    est_map = {
        (r["item_id"], r["station_id"]): float(r.get("est_time_min") or 0)
        for r in (routing_result.data or [])
    }

    # Quantity completed per (item, station)
    completion_result = supabase.table("part_completion").select(
        "item_id, station_id, qty_complete"
    ).eq("project_id", pid).execute()
    qty_map: dict[tuple, int] = {}
    for c in (completion_result.data or []):
        key = (c["item_id"], c["station_id"])
        qty_map[key] = qty_map.get(key, 0) + (c.get("qty_complete") or 0)

    rows = []
    for key, row in actual.items():
        est_per_part = est_map.get(key)
        qty = qty_map.get(key, 0)
        actual_total = row["actual_total_min"]
        actual_per_part = round(actual_total / qty, 2) if qty > 0 else None
        rows.append({
            **row,
            "est_min_per_part": est_per_part,
            "qty_completed": qty,
            "actual_total_min": round(actual_total, 2),
            "actual_min_per_part": actual_per_part,
        })

    rows.sort(key=lambda r: (r["item_number"] or "", r["station"] or ""))

    return {
        "project_code": project["project_code"],
        "rows": rows,
        "note": (
            "est_min_per_part comes from routing; actual_min_per_part = logged time / qty "
            "completed at that station. Comparison is only meaningful where qty_completed > 0."
        )
    }


def list_low_stock_materials() -> dict[str, Any]:
    """List raw materials at or below reorder point (on-hand + on-order)."""
    supabase = get_supabase_admin()

    result = supabase.table("raw_materials").select(
        "material_code, material_type, description, qty_on_hand, qty_on_order, "
        "reorder_point, price_per_unit"
    ).not_.is_("reorder_point", "null").execute()

    low = []
    for m in result.data or []:
        on_hand = m.get("qty_on_hand") or 0
        on_order = m.get("qty_on_order") or 0
        reorder = m.get("reorder_point") or 0
        if on_hand + on_order <= reorder:
            m["available_plus_on_order"] = on_hand + on_order
            low.append(m)

    return {"count": len(low), "materials": low}


# SQL keywords that should never appear in a read-only query. The database
# function and read-only role are the real enforcement; this is a fast-fail.
_SQL_FORBIDDEN = (
    "insert", "update", "delete", "drop", "alter", "create", "truncate",
    "grant", "revoke", "vacuum", "copy", "call", "do", "set", "reset",
    "listen", "notify", "refresh", "reindex", "cluster", "comment",
)


def query_database(sql: str, max_rows: int = 200) -> dict[str, Any]:
    """Run a read-only SELECT via the assistant_query database function."""
    import re

    supabase = get_supabase_admin()

    stripped = sql.strip().rstrip(";").strip()
    if not re.match(r"^(select|with)\b", stripped, re.IGNORECASE):
        return {"error": "Only SELECT queries are allowed"}
    if ";" in stripped:
        return {"error": "Multiple statements are not allowed"}

    words = set(re.findall(r"[a-z_]+", stripped.lower()))
    forbidden = words & set(_SQL_FORBIDDEN)
    if forbidden:
        return {"error": f"Query contains forbidden keywords: {sorted(forbidden)}"}

    max_rows = min(max(max_rows, 1), 500)

    try:
        result = supabase.rpc("assistant_query", {
            "sql": stripped,
            "max_rows": max_rows
        }).execute()
    except Exception as e:
        return {"error": f"Query failed: {str(e)}"}

    rows = result.data if result.data is not None else []
    return {"row_count": len(rows), "rows": rows}


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
# Action Executors (run only after explicit user approval)
# =============================================================================

def _execute_requeue_failed_task(task_id: str) -> dict[str, Any]:
    supabase = get_supabase_admin()

    result = supabase.table("work_queue").update({
        "status": "pending",
        "error_message": None,
        "started_at": None,
        "completed_at": None,
    }).eq("id", task_id).eq("status", "failed").execute()

    if not result.data:
        return {"error": "Task not found or is not in 'failed' state"}
    return {"status": "requeued", "task_id": task_id}


def _execute_update_material_price(material_code: str, new_price: float) -> dict[str, Any]:
    supabase = get_supabase_admin()

    result = supabase.table("raw_materials").update({
        "price_per_unit": new_price
    }).eq("material_code", material_code).execute()

    if not result.data:
        return {"error": f"Material '{material_code}' not found"}
    return {"status": "updated", "material_code": material_code, "new_price": new_price}


def _execute_update_routing_time(item_number: str, sequence: int, new_time_min: float) -> dict[str, Any]:
    supabase = get_supabase_admin()

    normalized = item_number.lower().strip()

    try:
        item_result = supabase.table("items").select("id").eq(
            "item_number", normalized
        ).single().execute()
    except Exception:
        return {"error": f"Item '{item_number}' not found"}

    if not item_result.data:
        return {"error": f"Item '{item_number}' not found"}

    result = supabase.table("routing").update({
        "est_time_min": new_time_min
    }).eq("item_id", item_result.data["id"]).eq("sequence", sequence).execute()

    if not result.data:
        return {"error": f"No routing step with sequence {sequence} on '{normalized}'"}
    return {
        "status": "updated",
        "item_number": normalized,
        "sequence": sequence,
        "new_time_min": new_time_min
    }


def _execute_update_cost_setting(setting_key: str, new_value: float) -> dict[str, Any]:
    supabase = get_supabase_admin()

    result = supabase.table("cost_settings").update({
        "setting_value": new_value
    }).eq("setting_key", setting_key).execute()

    if not result.data:
        return {"error": f"Cost setting '{setting_key}' not found"}
    return {"status": "updated", "setting_key": setting_key, "new_value": new_value}


ACTION_EXECUTORS = {
    "requeue_failed_task": _execute_requeue_failed_task,
    "update_material_price": _execute_update_material_price,
    "update_routing_time": _execute_update_routing_time,
    "update_cost_setting": _execute_update_cost_setting,
}


def describe_action(name: str, arguments: dict[str, Any]) -> str:
    """Human-readable description of a proposed action, shown on the approval card."""
    if name == "requeue_failed_task":
        return f"Re-queue failed task {arguments.get('task_id', '?')}"
    if name == "update_material_price":
        return (f"Set price of material {arguments.get('material_code', '?')} "
                f"to ${arguments.get('new_price', '?')}")
    if name == "update_routing_time":
        return (f"Set routing step {arguments.get('sequence', '?')} on "
                f"{arguments.get('item_number', '?')} to "
                f"{arguments.get('new_time_min', '?')} min")
    if name == "update_cost_setting":
        return (f"Set cost setting '{arguments.get('setting_key', '?')}' "
                f"to {arguments.get('new_value', '?')}")
    return f"{name}({json.dumps(arguments)})"


def execute_action(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute an approved action. Only called from the approval endpoint."""
    if name not in ACTION_EXECUTORS:
        return {"error": f"Unknown action: {name}"}
    try:
        return ACTION_EXECUTORS[name](**arguments)
    except Exception as e:
        return {"error": f"Action '{name}' failed: {str(e)}"}


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
    "audit_project": audit_project,
    "get_time_analysis": get_time_analysis,
    "list_low_stock_materials": list_low_stock_materials,
    "query_database": query_database,
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
    "audit_project": "Auditing project...",
    "get_time_analysis": "Comparing estimated vs actual time...",
    "list_low_stock_materials": "Checking stock levels...",
    "query_database": "Running database query...",
    "requeue_failed_task": "Proposing task re-queue...",
    "update_material_price": "Proposing price update...",
    "update_routing_time": "Proposing routing time update...",
    "update_cost_setting": "Proposing cost setting update...",
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
    elif name == "audit_project" and "project_code" in arguments:
        return f"Auditing project {arguments['project_code']}..."
    elif name == "get_time_analysis" and "project_code" in arguments:
        return f"Analyzing time for {arguments['project_code']}..."

    return base
