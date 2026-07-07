"""Query multi-level where-used for csa00090."""

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

def get_where_used_recursive(item_number, depth=0, max_depth=5, multiplier=1):
    """Recursively find where an item is used and calculate rolled-up quantities."""
    if depth >= max_depth:
        return []

    # Get item ID
    item_result = supabase.table("items").select("id, item_number, name").eq("item_number", item_number.lower()).execute()

    if not item_result.data:
        return []

    item_id = item_result.data[0]["id"]
    item_data = item_result.data[0]

    # Get direct parents
    bom_result = supabase.table("bom").select(
        "id, quantity, parent_item:items!bom_parent_item_id_fkey(id, item_number, name)"
    ).eq("child_item_id", item_id).execute()

    results = []

    for entry in bom_result.data:
        parent = entry["parent_item"]
        direct_qty = entry["quantity"]
        rolled_up_qty = direct_qty * multiplier

        result = {
            "level": depth,
            "child_item": item_number,
            "parent_item": parent["item_number"],
            "parent_name": parent["name"],
            "direct_quantity": direct_qty,
            "rolled_up_quantity": rolled_up_qty,
            "multiplier": multiplier
        }
        results.append(result)

        # Recursively find where the parent is used
        parent_uses = get_where_used_recursive(
            parent["item_number"],
            depth + 1,
            max_depth,
            multiplier * direct_qty
        )
        results.extend(parent_uses)

    return results

print("=" * 80)
print("Multi-Level Where-Used Analysis for csa00090")
print("=" * 80)

all_uses = get_where_used_recursive("csa00090")

if not all_uses:
    print("\n[X] No parent assemblies found for csa00090")
else:
    print(f"\n[OK] Found {len(all_uses)} where-used entries (all levels):\n")

    for i, use in enumerate(all_uses, 1):
        indent = "  " * use["level"]
        print(f"{i}. {indent}Level {use['level']}: {use['child_item']} -> {use['parent_item']} ({use['parent_name']})")
        print(f"{indent}   Direct Qty: {use['direct_quantity']}")
        print(f"{indent}   Rolled-Up Qty: {use['rolled_up_quantity']} (multiplier: {use['multiplier']})")
        print()

    # Group by top-level assemblies
    print("=" * 80)
    print("Summary by Top-Level Assembly:")
    print("=" * 80)

    top_level_assemblies = {}
    for use in all_uses:
        if use["level"] == 0:
            # This is a direct parent
            top_level_assemblies[use["parent_item"]] = {
                "name": use["parent_name"],
                "direct_qty": use["direct_quantity"]
            }
        else:
            # This is an indirect parent (csa00090 is used through a subassembly)
            if use["parent_item"] not in top_level_assemblies:
                top_level_assemblies[use["parent_item"]] = {
                    "name": use["parent_name"],
                    "rolled_up_qty": use["rolled_up_quantity"]
                }

    if top_level_assemblies:
        print("\nTop-level assemblies that use csa00090:")
        for asm_number, data in top_level_assemblies.items():
            print(f"\n  {asm_number} - {data['name']}")
            if "direct_qty" in data:
                print(f"    Direct usage: {data['direct_qty']} units")
            if "rolled_up_qty" in data:
                print(f"    Rolled-up usage: {data['rolled_up_qty']} units")

print("\n" + "=" * 80)
print("Analysis complete!")
print("=" * 80)
