#!/usr/bin/env python3
"""
Migrate remaining data from SQLite to Supabase:
- item_routing -> routing
- projects -> mrp_projects
- project_parts -> mrp_project_parts
- routing_materials
- time_logs
- part_completion
"""

import sqlite3
import os
from supabase import create_client

# Configuration
SQLITE_PATH = os.path.join(os.path.dirname(__file__), '..', 'PDM_Vault', 'pdm.sqlite')
SUPABASE_URL = 'https://lnytnxmmemdzwqburtgf.supabase.co'
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxueXRueG1tZW1kendxYnVydGdmIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2OTQ5Mjc0MCwiZXhwIjoyMDg1MDY4NzQwfQ.CtVmuoHbAjKN-GICUb6TEQaBS0nS5N8aZr3AZJbnvrY')


def migrate():
    print("=" * 60)
    print("SQLite to Supabase Migration - Remaining Data")
    print("=" * 60)

    # Connect to SQLite
    print(f"\nConnecting to SQLite: {SQLITE_PATH}")
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    cursor = sqlite_conn.cursor()

    # Connect to Supabase
    print(f"Connecting to Supabase: {SUPABASE_URL}")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Build item_number -> UUID mapping
    print("\nBuilding item mapping...")
    result = supabase.table('items').select('id, item_number').execute()
    item_map = {row['item_number']: row['id'] for row in result.data}
    print(f"  Mapped {len(item_map)} items")

    # Build station_code -> UUID mapping
    print("Building workstation mapping...")
    result = supabase.table('workstations').select('id, station_code').execute()
    station_map = {row['station_code']: row['id'] for row in result.data}
    print(f"  Mapped {len(station_map)} workstations")
    print(f"  Station codes: {list(station_map.keys())}")

    # Build raw_material mapping via part_number
    print("Building raw materials mapping...")
    result = supabase.table('raw_materials').select('id, part_number').execute()
    supabase_materials = {row['part_number']: row['id'] for row in result.data}

    cursor.execute('SELECT material_id, part_number FROM raw_materials')
    material_map = {}
    for row in cursor.fetchall():
        sqlite_id = row['material_id']
        part_number = row['part_number']
        if part_number in supabase_materials:
            material_map[sqlite_id] = supabase_materials[part_number]
    print(f"  Mapped {len(material_map)} materials")

    # ========== MIGRATE ROUTING ==========
    print("\n" + "=" * 50)
    print("MIGRATING ROUTING (item_routing -> routing)")
    print("=" * 50)

    # Check if routing already has data
    existing_routing = supabase.table('routing').select('id', count='exact').execute()
    if existing_routing.count and existing_routing.count > 0:
        print(f"  Routing table already has {existing_routing.count} entries, clearing...")
        supabase.table('routing').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()

    cursor.execute('SELECT * FROM item_routing')
    routing_rows = cursor.fetchall()
    print(f"Found {len(routing_rows)} routing entries to migrate")

    migrated = 0
    skipped = 0
    failed = 0

    for row in routing_rows:
        item_number = row['item_number'].lower()
        station_code = row['station_code']

        if item_number not in item_map:
            skipped += 1
            continue

        if station_code not in station_map:
            print(f"  Station {station_code} not found for item {item_number}")
            failed += 1
            continue

        routing_data = {
            'item_id': item_map[item_number],
            'station_id': station_map[station_code],
            'sequence': row['sequence'],
            'est_time_min': int(row['est_time_min']) if row['est_time_min'] else 0,
            'notes': row['notes'] or None
        }

        try:
            supabase.table('routing').insert(routing_data).execute()
            migrated += 1
        except Exception as e:
            if 'duplicate' in str(e).lower():
                skipped += 1
            else:
                print(f"  Error: {e}")
                failed += 1

    print(f"Routing: {migrated} migrated, {skipped} skipped, {failed} failed")

    # ========== MIGRATE PROJECTS ==========
    print("\n" + "=" * 50)
    print("MIGRATING PROJECTS")
    print("=" * 50)

    # Clear existing mrp_projects
    supabase.table('mrp_project_parts').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()
    supabase.table('mrp_projects').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()
    print("Cleared existing mrp_projects and mrp_project_parts")

    cursor.execute('SELECT * FROM projects')
    project_rows = cursor.fetchall()
    print(f"Found {len(project_rows)} projects to migrate")

    project_map = {}  # project_code -> UUID

    for row in project_rows:
        project_code = row['project_code']
        top_assembly = row['top_assembly'].lower() if row['top_assembly'] else None

        project_data = {
            'project_code': project_code,
            'description': row['description'],
            'customer': row['customer'],
            'due_date': row['due_date'] if row['due_date'] else None,
            'status': row['status'] or 'Setup',
            'top_assembly_id': item_map.get(top_assembly) if top_assembly else None,
        }

        try:
            result = supabase.table('mrp_projects').insert(project_data).execute()
            if result.data:
                project_map[project_code] = result.data[0]['id']
                print(f"  Migrated project: {project_code}")
        except Exception as e:
            print(f"  Error migrating {project_code}: {e}")

    print(f"Projects: {len(project_map)} migrated")

    # ========== MIGRATE PROJECT PARTS ==========
    print("\n" + "=" * 50)
    print("MIGRATING PROJECT PARTS")
    print("=" * 50)

    cursor.execute('SELECT * FROM project_parts')
    parts_rows = cursor.fetchall()
    print(f"Found {len(parts_rows)} project parts to migrate")

    migrated = 0
    skipped = 0

    for row in parts_rows:
        project_code = row['project_code']
        item_number = row['item_number'].lower()

        if project_code not in project_map:
            skipped += 1
            continue

        if item_number not in item_map:
            skipped += 1
            continue

        part_data = {
            'project_id': project_map[project_code],
            'item_id': item_map[item_number],
            'quantity': row['quantity'] or 1
        }

        try:
            supabase.table('mrp_project_parts').insert(part_data).execute()
            migrated += 1
        except Exception as e:
            if 'duplicate' not in str(e).lower():
                print(f"  Error: {e}")
            skipped += 1

    print(f"Project parts: {migrated} migrated, {skipped} skipped")

    # ========== MIGRATE ROUTING MATERIALS ==========
    print("\n" + "=" * 50)
    print("MIGRATING ROUTING MATERIALS")
    print("=" * 50)

    # Clear existing
    supabase.table('routing_materials').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()

    cursor.execute('SELECT * FROM routing_materials')
    rm_rows = cursor.fetchall()
    print(f"Found {len(rm_rows)} routing materials to migrate")

    migrated = 0
    skipped = 0

    for row in rm_rows:
        item_number = row['item_number'].lower()
        material_id = row['material_id']

        if item_number not in item_map:
            print(f"  Item {item_number} not found")
            skipped += 1
            continue

        if material_id not in material_map:
            print(f"  Material ID {material_id} not found")
            skipped += 1
            continue

        rm_data = {
            'item_id': item_map[item_number],
            'material_id': material_map[material_id],
            'qty_required': row['qty_required']
        }

        try:
            supabase.table('routing_materials').insert(rm_data).execute()
            migrated += 1
        except Exception as e:
            if 'duplicate' not in str(e).lower():
                print(f"  Error: {e}")
            skipped += 1

    print(f"Routing materials: {migrated} migrated, {skipped} skipped")

    # ========== MIGRATE TIME LOGS ==========
    print("\n" + "=" * 50)
    print("MIGRATING TIME LOGS")
    print("=" * 50)

    # Clear existing
    supabase.table('time_logs').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()

    cursor.execute('SELECT * FROM time_logs')
    time_rows = cursor.fetchall()
    print(f"Found {len(time_rows)} time logs to migrate")

    migrated = 0
    skipped = 0

    for row in time_rows:
        project_code = row['project_code']
        item_number = row['item_number'].lower()
        station_code = row['station_code']

        if project_code not in project_map:
            skipped += 1
            continue
        if item_number not in item_map:
            skipped += 1
            continue
        if station_code not in station_map:
            skipped += 1
            continue

        log_data = {
            'project_id': project_map[project_code],
            'item_id': item_map[item_number],
            'station_id': station_map[station_code],
            'worker': row['worker'],
            'time_min': int(row['time_min']) if row['time_min'] else 0
        }

        try:
            supabase.table('time_logs').insert(log_data).execute()
            migrated += 1
        except Exception as e:
            if 'duplicate' not in str(e).lower():
                print(f"  Error: {e}")
            skipped += 1

    print(f"Time logs: {migrated} migrated, {skipped} skipped")

    # ========== MIGRATE PART COMPLETION ==========
    print("\n" + "=" * 50)
    print("MIGRATING PART COMPLETION")
    print("=" * 50)

    # Clear existing
    supabase.table('part_completion').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()

    cursor.execute('SELECT * FROM part_completion')
    completion_rows = cursor.fetchall()
    print(f"Found {len(completion_rows)} part completions to migrate")

    migrated = 0
    skipped = 0

    for row in completion_rows:
        project_code = row['project_code']
        item_number = row['item_number'].lower()
        station_code = row['station_code']

        if project_code not in project_map:
            skipped += 1
            continue
        if item_number not in item_map:
            skipped += 1
            continue
        if station_code not in station_map:
            skipped += 1
            continue

        comp_data = {
            'project_id': project_map[project_code],
            'item_id': item_map[item_number],
            'station_id': station_map[station_code],
            'qty_complete': row['qty_complete'] or 0,
            'completed_by': row['completed_by']
        }

        try:
            supabase.table('part_completion').insert(comp_data).execute()
            migrated += 1
        except Exception as e:
            if 'duplicate' not in str(e).lower():
                print(f"  Error: {e}")
            skipped += 1

    print(f"Part completion: {migrated} migrated, {skipped} skipped")

    # ========== SUMMARY ==========
    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE!")
    print("=" * 60)

    sqlite_conn.close()


if __name__ == "__main__":
    migrate()
