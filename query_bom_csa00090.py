"""Query BOM table for all usages of csa00090."""

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

# First, get the item ID for csa00090
print("=" * 80)
print("Looking up item ID for csa00090...")
print("=" * 80)

item_response = supabase.table("items").select("id, item_number, name, revision").eq("item_number", "csa00090").execute()

if not item_response.data:
    print("ERROR: Item csa00090 not found in items table")
    exit(1)

item = item_response.data[0]
item_id = item["id"]
print(f"\nFound item:")
print(f"  ID: {item_id}")
print(f"  Number: {item['item_number']}")
print(f"  Name: {item['name']}")
print(f"  Revision: {item['revision']}")

# Query BOM table where csa00090 is the child
print("\n" + "=" * 80)
print("Querying BOM entries where csa00090 is used as a child component...")
print("=" * 80)

bom_response = supabase.table("bom").select(
    "id, quantity, source_file, created_at, parent_item:items!bom_parent_item_id_fkey(id, item_number, name, revision)"
).eq("child_item_id", item_id).execute()

if not bom_response.data:
    print("\n[X] No BOM entries found where csa00090 is used as a child.")
else:
    print(f"\n[OK] Found {len(bom_response.data)} BOM entries:\n")

    total_qty = 0
    for entry in bom_response.data:
        parent = entry["parent_item"]
        qty = entry["quantity"]
        total_qty += qty

        print(f"Parent Assembly: {parent['item_number']} - {parent['name']}")
        print(f"  Revision: {parent['revision']}")
        print(f"  Quantity: {qty}")
        print(f"  Source File: {entry['source_file'] or 'N/A'}")
        print(f"  BOM ID: {entry['id']}")
        print(f"  Created: {entry['created_at']}")
        print()

    print(f"Total direct usage quantity: {total_qty}")

print("\n" + "=" * 80)
print("Query complete!")
print("=" * 80)
print("\nNote: The BOM table stores direct parent-child relationships.")
print("For multi-level assemblies, you would need to use recursive queries")
print("or the backend's BOM tree expansion endpoint to see flattened quantities.")
