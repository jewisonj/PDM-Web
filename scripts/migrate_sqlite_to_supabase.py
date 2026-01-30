#!/usr/bin/env python3
"""
SQLite to Supabase Migration Script
Migrates items, files, and BOM data from legacy SQLite database to Supabase PostgreSQL.
"""

import sqlite3
import os
from datetime import datetime
from supabase import create_client

# Configuration
SQLITE_PATH = os.path.join(os.path.dirname(__file__), '..', 'Legacy', 'PDM_Vault', 'pdm.sqlite')
SUPABASE_URL = "https://lnytnxmmemdzwqburtgf.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# If no service key, use anon key (will respect RLS)
if not SUPABASE_KEY:
    SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxueXRueG1tZW1kendxYnVydGdmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njk0OTI3NDAsImV4cCI6MjA4NTA2ODc0MH0.No2VDrRq5JypOhh0Pm4_ir3cGKBTV4c7sHn34OL9SVI"


def get_file_type(file_path: str) -> str:
    """Map file extension to file_type enum."""
    ext = file_path.lower().split('.')[-1] if '.' in file_path else ''
    type_map = {
        'stp': 'STEP',
        'step': 'STEP',
        'prt': 'CAD',
        'asm': 'CAD',
        'drw': 'CAD',
        'dxf': 'DXF',
        'svg': 'SVG',
        'pdf': 'PDF',
        'png': 'IMAGE',
        'jpg': 'IMAGE',
        'jpeg': 'IMAGE',
    }
    return type_map.get(ext, 'OTHER')


def migrate():
    print("=" * 60)
    print("SQLite to Supabase Migration")
    print("=" * 60)

    # Connect to SQLite
    print(f"\nConnecting to SQLite: {SQLITE_PATH}")
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    cursor = sqlite_conn.cursor()

    # Connect to Supabase
    print(f"Connecting to Supabase: {SUPABASE_URL}")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Track mappings for foreign keys
    item_id_map = {}  # old item_number -> new UUID

    # ========== MIGRATE ITEMS ==========
    print("\n--- Migrating Items ---")
    cursor.execute("SELECT * FROM items")
    items = cursor.fetchall()
    print(f"Found {len(items)} items to migrate")

    items_migrated = 0
    items_failed = 0

    for row in items:
        item_data = {
            'item_number': row['item_number'].lower(),
            'name': row['name'],
            'revision': row['revision'] or 'A',
            'iteration': row['iteration'] or 1,
            'lifecycle_state': row['lifecycle_state'] or 'Design',
            'description': row['description'],
            'material': row['material'],
            'mass': float(row['mass']) if row['mass'] else None,
            'thickness': float(row['thickness']) if row['thickness'] else None,
            'cut_length': float(row['cut_length']) if row['cut_length'] else None,
        }

        # Check if supplier part based on item_number prefix
        prefix = item_data['item_number'][:3]
        if prefix in ('mmc', 'spn'):
            item_data['is_supplier_part'] = True

        try:
            result = supabase.table('items').insert(item_data).execute()
            if result.data:
                item_id_map[row['item_number']] = result.data[0]['id']
                items_migrated += 1
        except Exception as e:
            if 'duplicate key' in str(e).lower():
                # Item already exists, get its ID
                existing = supabase.table('items').select('id').eq('item_number', item_data['item_number']).execute()
                if existing.data:
                    item_id_map[row['item_number']] = existing.data[0]['id']
                    items_migrated += 1
            else:
                print(f"  Failed to migrate item {row['item_number']}: {e}")
                items_failed += 1

    print(f"Items: {items_migrated} migrated, {items_failed} failed")

    # ========== MIGRATE FILES ==========
    print("\n--- Migrating Files ---")
    cursor.execute("SELECT * FROM files")
    files = cursor.fetchall()
    print(f"Found {len(files)} files to migrate")

    files_migrated = 0
    files_failed = 0

    for row in files:
        item_number = row['item_number'].lower() if row['item_number'] else None

        if not item_number or item_number not in item_id_map:
            # Try to find the item
            if item_number:
                existing = supabase.table('items').select('id').eq('item_number', item_number).execute()
                if existing.data:
                    item_id_map[item_number] = existing.data[0]['id']
                else:
                    files_failed += 1
                    continue
            else:
                files_failed += 1
                continue

        # Extract filename from path
        file_path = row['file_path'] or ''
        file_name = os.path.basename(file_path) if file_path else f"unknown_{row['file_id']}"

        file_data = {
            'item_id': item_id_map[item_number],
            'file_type': row['file_type'] or get_file_type(file_path),
            'file_name': file_name,
            'file_path': None,  # Not migrating actual files to storage
            'revision': row['revision'],
            'iteration': row['iteration'] or 1,
        }

        try:
            result = supabase.table('files').insert(file_data).execute()
            if result.data:
                files_migrated += 1
        except Exception as e:
            if 'duplicate key' not in str(e).lower():
                print(f"  Failed to migrate file {file_name}: {e}")
            files_failed += 1

    print(f"Files: {files_migrated} migrated, {files_failed} failed")

    # ========== MIGRATE BOM ==========
    print("\n--- Migrating BOM ---")
    cursor.execute("SELECT * FROM bom")
    bom_entries = cursor.fetchall()
    print(f"Found {len(bom_entries)} BOM entries to migrate")

    bom_migrated = 0
    bom_failed = 0

    for row in bom_entries:
        parent = row['parent_item'].lower() if row['parent_item'] else None
        child = row['child_item'].lower() if row['child_item'] else None

        if not parent or not child:
            bom_failed += 1
            continue

        # Get or find parent ID
        if parent not in item_id_map:
            existing = supabase.table('items').select('id').eq('item_number', parent).execute()
            if existing.data:
                item_id_map[parent] = existing.data[0]['id']
            else:
                bom_failed += 1
                continue

        # Get or find child ID
        if child not in item_id_map:
            existing = supabase.table('items').select('id').eq('item_number', child).execute()
            if existing.data:
                item_id_map[child] = existing.data[0]['id']
            else:
                bom_failed += 1
                continue

        bom_data = {
            'parent_item_id': item_id_map[parent],
            'child_item_id': item_id_map[child],
            'quantity': row['quantity'] or 1,
            'source_file': row['source_file'],
        }

        try:
            result = supabase.table('bom').insert(bom_data).execute()
            if result.data:
                bom_migrated += 1
        except Exception as e:
            if 'duplicate key' not in str(e).lower():
                print(f"  Failed to migrate BOM {parent} -> {child}: {e}")
            bom_failed += 1

    print(f"BOM: {bom_migrated} migrated, {bom_failed} failed")

    # ========== SUMMARY ==========
    print("\n" + "=" * 60)
    print("Migration Complete!")
    print("=" * 60)
    print(f"Items:  {items_migrated} migrated")
    print(f"Files:  {files_migrated} migrated")
    print(f"BOM:    {bom_migrated} migrated")

    sqlite_conn.close()


if __name__ == "__main__":
    migrate()
