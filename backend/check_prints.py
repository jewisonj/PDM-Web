#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

from app.services.supabase import get_supabase_client
sb = get_supabase_client()

# Check file_types in use
print("File types in database:")
res = sb.table('files').select('file_type').limit(100).execute()
types = set(r['file_type'] for r in res.data or [])
print(f"Types: {types}")

print(f"\nTotal files: {sb.table('files').select('id', count='exact').execute().count}")
print(f"Total items: {sb.table('items').select('id', count='exact').execute().count}")

# Sample files
print("\nSample file records:")
res = sb.table('files').select('file_type, file_path, file_name').limit(10).execute()
for f in res.data or []:
    print(f"  type={f['file_type']!r}, path={f['file_path']}")
