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
}

# Human-readable summaries for SSE status events
TOOL_SUMMARIES = {
    "search_items": "Searching for items...",
    "get_item": "Looking up item details...",
    "get_bom_tree": "Expanding BOM tree...",
    "get_where_used": "Finding where item is used...",
    "list_item_files": "Listing files...",
    "get_file_download_link": "Generating download link...",
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

    return base
