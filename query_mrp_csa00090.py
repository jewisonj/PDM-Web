"""Check MRP project usage of csa00090."""

import os
from supabase import create_client

# Load from environment
SUPABASE_URL = "https://lnytnxmmemdzwqburtgf.supabase.co"
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_SERVICE_KEY:
    print("ERROR: SUPABASE_SERVICE_KEY environment variable not set")
    exit(1)

# Create client (using service key to bypass RLS)
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

print("=" * 80)
print("MRP Project Usage Analysis for csa00090")
print("=" * 80)

# Get item ID
item_result = supabase.table("items").select("id, item_number, name").eq("item_number", "csa00090").execute()

if not item_result.data:
    print("\n[X] Item csa00090 not found")
    exit(1)

item_id = item_result.data[0]["id"]
item = item_result.data[0]

print(f"\nItem: {item['item_number']} - {item['name']}")
print(f"ID: {item_id}")

# Check mrp_project_parts table
print("\n" + "=" * 80)
print("Checking MRP Project Parts...")
print("=" * 80)

mrp_parts_result = supabase.table("mrp_project_parts").select(
    "id, required_qty, project:mrp_projects!mrp_project_parts_project_id_fkey(id, project_code, description, status, top_assembly_id, top_assembly:items!mrp_projects_top_assembly_id_fkey(item_number, name))"
).eq("item_id", item_id).execute()

if not mrp_parts_result.data:
    print("\n[X] No MRP project parts entries found for csa00090")
else:
    print(f"\n[OK] Found {len(mrp_parts_result.data)} MRP project entries:\n")

    for entry in mrp_parts_result.data:
        project = entry["project"]
        top_asm = project.get("top_assembly")

        print(f"Project: {project['project_code']} - {project['description']}")
        print(f"  Status: {project['status']}")
        if top_asm:
            print(f"  Top Assembly: {top_asm['item_number']} - {top_asm['name']}")
        print(f"  Required Qty for csa00090: {entry['required_qty']}")
        print(f"  Entry ID: {entry['id']}")
        print()

# Also check if there are any active MRP projects
print("=" * 80)
print("All Active MRP Projects:")
print("=" * 80)

active_projects = supabase.table("mrp_projects").select(
    "id, project_code, description, status, top_assembly:items!mrp_projects_top_assembly_id_fkey(item_number, name)"
).in_("status", ["Setup", "Released", "On Hold"]).execute()

if active_projects.data:
    print(f"\n[OK] Found {len(active_projects.data)} active MRP projects:\n")
    for proj in active_projects.data:
        top_asm = proj.get("top_assembly")
        print(f"  {proj['project_code']} - {proj['description']}")
        print(f"    Status: {proj['status']}")
        if top_asm:
            print(f"    Top Assembly: {top_asm['item_number']} - {top_asm['name']}")
        print()
else:
    print("\n[X] No active MRP projects found")

print("=" * 80)
print("Analysis complete!")
print("=" * 80)
