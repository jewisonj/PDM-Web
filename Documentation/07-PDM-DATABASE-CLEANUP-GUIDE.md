# PDM Database Maintenance Guide

## Overview

This guide covers database maintenance procedures for the PDM system running on Supabase PostgreSQL. As a managed cloud database, Supabase handles low-level maintenance (vacuuming, connection pooling, backups) automatically. This guide focuses on application-level maintenance: identifying orphaned records, cleaning up the work queue, monitoring database health, and running common maintenance queries.

---

## Supabase Dashboard

The Supabase Dashboard provides built-in tools for database monitoring and maintenance:

- **Table Editor** -- Browse and edit table data directly.
- **SQL Editor** -- Run arbitrary SQL queries against the database.
- **Database Health** -- View connection counts, query performance, and resource usage.
- **Logs** -- View API, PostgreSQL, and Auth logs.
- **Advisors** -- Security and performance recommendations (linting).

Access the dashboard at: `https://supabase.com/dashboard/project/<project-ref>`

All maintenance queries in this guide can be run in the Supabase SQL Editor or through the FastAPI backend's Supabase client.

---

## Database Health Monitoring

### Check Table Sizes and Row Counts

```sql
SELECT
    relname AS table_name,
    n_live_tup AS row_count,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY n_live_tup DESC;
```

### Check Index Usage

Verify that indexes are being used by queries:

```sql
SELECT
    indexrelname AS index_name,
    relname AS table_name,
    idx_scan AS times_used,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan DESC;
```

Indexes with very low `times_used` counts may be unnecessary and could be removed to save storage.

### Check for Long-Running Queries

```sql
SELECT
    pid,
    now() - pg_stat_activity.query_start AS duration,
    query,
    state
FROM pg_stat_activity
WHERE state != 'idle'
  AND query NOT ILIKE '%pg_stat_activity%'
ORDER BY duration DESC;
```

### Database Statistics Summary

Get a snapshot of the current database state:

```sql
SELECT 'items' AS table_name, COUNT(*) AS row_count FROM items
UNION ALL SELECT 'files', COUNT(*) FROM files
UNION ALL SELECT 'bom', COUNT(*) FROM bom
UNION ALL SELECT 'work_queue', COUNT(*) FROM work_queue
UNION ALL SELECT 'lifecycle_history', COUNT(*) FROM lifecycle_history
UNION ALL SELECT 'checkouts', COUNT(*) FROM checkouts
UNION ALL SELECT 'users', COUNT(*) FROM users
UNION ALL SELECT 'projects', COUNT(*) FROM projects
UNION ALL SELECT 'mrp_projects', COUNT(*) FROM mrp_projects
UNION ALL SELECT 'workstations', COUNT(*) FROM workstations
UNION ALL SELECT 'routing', COUNT(*) FROM routing
UNION ALL SELECT 'mrp_project_parts', COUNT(*) FROM mrp_project_parts
UNION ALL SELECT 'raw_materials', COUNT(*) FROM raw_materials
UNION ALL SELECT 'routing_materials', COUNT(*) FROM routing_materials
UNION ALL SELECT 'time_logs', COUNT(*) FROM time_logs
UNION ALL SELECT 'part_completion', COUNT(*) FROM part_completion
ORDER BY table_name;
```

---

## Identifying Orphaned Records

### Orphaned Files (files with no matching item)

Files whose `item_id` references an item that no longer exists. This should not happen due to foreign key constraints, but is worth checking:

```sql
SELECT f.id, f.file_name, f.file_type, f.file_path, f.created_at
FROM files f
LEFT JOIN items i ON f.item_id = i.id
WHERE i.id IS NULL;
```

### Orphaned BOM Entries

BOM entries referencing items that no longer exist:

```sql
-- BOM entries where parent item is missing
SELECT b.id, b.parent_item_id, b.child_item_id, b.quantity
FROM bom b
LEFT JOIN items i ON b.parent_item_id = i.id
WHERE i.id IS NULL;

-- BOM entries where child item is missing
SELECT b.id, b.parent_item_id, b.child_item_id, b.quantity
FROM bom b
LEFT JOIN items i ON b.child_item_id = i.id
WHERE i.id IS NULL;
```

### Items with No Files

Items that exist in the database but have no associated files. These may be legitimate (items created via BOM upload that have not had files uploaded yet) or may be orphaned:

```sql
SELECT i.item_number, i.name, i.lifecycle_state, i.created_at
FROM items i
LEFT JOIN files f ON i.id = f.item_id
WHERE f.id IS NULL
ORDER BY i.created_at DESC;
```

To distinguish between legitimate and orphaned items, check if they appear in any BOM:

```sql
-- Items with no files AND not referenced in any BOM
SELECT i.item_number, i.name, i.created_at
FROM items i
LEFT JOIN files f ON i.id = f.item_id
LEFT JOIN bom b_parent ON i.id = b_parent.parent_item_id
LEFT JOIN bom b_child ON i.id = b_child.child_item_id
WHERE f.id IS NULL
  AND b_parent.id IS NULL
  AND b_child.id IS NULL
ORDER BY i.created_at DESC;
```

### Files with Invalid Storage Paths

Files where the `file_path` is null or empty, which means they cannot be downloaded:

```sql
SELECT f.id, f.file_name, f.file_type, i.item_number, f.created_at
FROM files f
JOIN items i ON f.item_id = i.id
WHERE f.file_path IS NULL OR f.file_path = ''
ORDER BY f.created_at DESC;
```

### Orphaned Lifecycle History

History entries referencing items that no longer exist:

```sql
SELECT lh.id, lh.item_id, lh.old_state, lh.new_state, lh.changed_at
FROM lifecycle_history lh
LEFT JOIN items i ON lh.item_id = i.id
WHERE i.id IS NULL;
```

### Stale Checkouts

Items that have been checked out for an unusually long time (more than 7 days):

```sql
SELECT
    c.item_id,
    i.item_number,
    u.username,
    c.checked_out_at,
    NOW() - c.checked_out_at AS duration
FROM checkouts c
JOIN items i ON c.item_id = i.id
JOIN users u ON c.user_id = u.id
WHERE c.checked_out_at < NOW() - INTERVAL '7 days'
ORDER BY c.checked_out_at ASC;
```

---

## Work Queue Cleanup

The `work_queue` table accumulates completed and failed tasks over time. Regular cleanup keeps it manageable.

### View Work Queue Status

```sql
SELECT
    status,
    task_type,
    COUNT(*) AS count,
    MIN(created_at) AS oldest,
    MAX(created_at) AS newest
FROM work_queue
GROUP BY status, task_type
ORDER BY status, task_type;
```

### Clean Up Completed Tasks

Remove completed tasks older than 30 days:

```sql
DELETE FROM work_queue
WHERE status = 'completed'
  AND completed_at < NOW() - INTERVAL '30 days';
```

### Clean Up Failed Tasks

Review failed tasks before removing them:

```sql
-- View failed tasks with error details
SELECT
    wq.id,
    i.item_number,
    wq.task_type,
    wq.error_message,
    wq.created_at,
    wq.completed_at
FROM work_queue wq
LEFT JOIN items i ON wq.item_id = i.id
WHERE wq.status = 'failed'
ORDER BY wq.completed_at DESC;
```

Remove failed tasks older than 30 days:

```sql
DELETE FROM work_queue
WHERE status = 'failed'
  AND completed_at < NOW() - INTERVAL '30 days';
```

### Reset Stuck Tasks

Tasks stuck in `processing` state (started but never completed) may indicate a worker crash. Reset them to `pending` for retry:

```sql
-- Find stuck tasks (processing for more than 1 hour)
SELECT
    wq.id,
    i.item_number,
    wq.task_type,
    wq.started_at,
    NOW() - wq.started_at AS stuck_duration
FROM work_queue wq
LEFT JOIN items i ON wq.item_id = i.id
WHERE wq.status = 'processing'
  AND wq.started_at < NOW() - INTERVAL '1 hour';

-- Reset stuck tasks back to pending
UPDATE work_queue
SET status = 'pending', started_at = NULL
WHERE status = 'processing'
  AND started_at < NOW() - INTERVAL '1 hour';
```

### Remove Orphaned Tasks

Tasks referencing items or files that no longer exist:

```sql
DELETE FROM work_queue
WHERE item_id IS NOT NULL
  AND item_id NOT IN (SELECT id FROM items);

DELETE FROM work_queue
WHERE file_id IS NOT NULL
  AND file_id NOT IN (SELECT id FROM files);
```

---

## Cleanup Procedures

### Remove Orphaned BOM Entries

After confirming orphaned records exist (using the queries above):

```sql
-- Remove BOM entries where parent item is missing
DELETE FROM bom
WHERE parent_item_id NOT IN (SELECT id FROM items);

-- Remove BOM entries where child item is missing
DELETE FROM bom
WHERE child_item_id NOT IN (SELECT id FROM items);
```

### Remove Orphaned File Records

```sql
DELETE FROM files
WHERE item_id NOT IN (SELECT id FROM items);
```

### Remove Truly Orphaned Items

Only remove items that have no files, no BOM references, and no MRP references:

```sql
-- Preview first
SELECT i.item_number, i.name, i.created_at
FROM items i
WHERE NOT EXISTS (SELECT 1 FROM files f WHERE f.item_id = i.id)
  AND NOT EXISTS (SELECT 1 FROM bom b WHERE b.parent_item_id = i.id OR b.child_item_id = i.id)
  AND NOT EXISTS (SELECT 1 FROM mrp_project_parts mpp WHERE mpp.item_id = i.id)
  AND NOT EXISTS (SELECT 1 FROM routing r WHERE r.item_id = i.id)
  AND NOT EXISTS (SELECT 1 FROM work_queue wq WHERE wq.item_id = i.id);

-- Delete (run only after reviewing the preview)
DELETE FROM items i
WHERE NOT EXISTS (SELECT 1 FROM files f WHERE f.item_id = i.id)
  AND NOT EXISTS (SELECT 1 FROM bom b WHERE b.parent_item_id = i.id OR b.child_item_id = i.id)
  AND NOT EXISTS (SELECT 1 FROM mrp_project_parts mpp WHERE mpp.item_id = i.id)
  AND NOT EXISTS (SELECT 1 FROM routing r WHERE r.item_id = i.id)
  AND NOT EXISTS (SELECT 1 FROM work_queue wq WHERE wq.item_id = i.id);
```

### Clear Stale Checkouts

Release checkouts older than a specified number of days:

```sql
-- Preview
SELECT i.item_number, u.username, c.checked_out_at
FROM checkouts c
JOIN items i ON c.item_id = i.id
JOIN users u ON c.user_id = u.id
WHERE c.checked_out_at < NOW() - INTERVAL '7 days';

-- Remove stale checkouts
DELETE FROM checkouts
WHERE checked_out_at < NOW() - INTERVAL '7 days';
```

---

## Supabase Storage Cleanup

### Find Storage Files Not Tracked in Database

Files may exist in Supabase Storage but not be tracked in the `files` table (e.g., if a database record was deleted but the storage object was not). This must be checked through the Supabase Dashboard or Storage API:

1. Go to Supabase Dashboard > Storage > `pdm-files` bucket.
2. Browse folders and compare against database records.
3. Use the Storage API to list objects programmatically if needed.

### Find Database Records Pointing to Missing Storage Files

This requires checking each `file_path` against Supabase Storage, which is best done programmatically:

```python
from supabase import create_client

supabase = create_client(url, key)

# Get all file records with storage paths
files = supabase.table("files").select("id, file_name, file_path").not_.is_("file_path", "null").execute()

missing = []
for f in files.data:
    path = f["file_path"]
    # Remove bucket prefix if present
    bucket = "pdm-files"
    storage_path = path.replace(f"{bucket}/", "", 1) if path.startswith(f"{bucket}/") else path

    try:
        # Attempt to create a signed URL (will fail if file doesn't exist)
        supabase.storage.from_(bucket).create_signed_url(storage_path, 60)
    except Exception:
        missing.append(f)

print(f"Found {len(missing)} file records with missing storage objects")
for f in missing:
    print(f"  {f['file_name']} -> {f['file_path']}")
```

---

## Supabase Security Advisors

Supabase provides automated security and performance advisors. Check these regularly, especially after schema changes:

1. Go to Supabase Dashboard > Advisors.
2. Review all warnings and recommendations.
3. Key items to watch for:
   - **Missing RLS policies** -- Tables with RLS enabled but no policies.
   - **Overly permissive policies** -- Policies using `true` for INSERT/UPDATE/DELETE.
   - **Mutable search path** -- Functions without explicit `search_path` set.
   - **Leaked password protection** -- Should be enabled for Auth security.

Run the advisors via API:

```
GET /rest/v1/rpc/lint
```

Or use the Supabase MCP tool: `get_advisors(type: "security")` and `get_advisors(type: "performance")`.

---

## Routine Maintenance Schedule

### Weekly

- **Check work queue** -- Review and clean up completed/failed tasks.
- **Review stuck tasks** -- Reset any tasks stuck in `processing` state.

### Monthly

- **Run orphaned record checks** -- Identify and clean up orphaned files, BOM entries, and items.
- **Check database statistics** -- Review table sizes and row counts.
- **Review Supabase advisors** -- Check for new security or performance warnings.

### After Major Operations

After bulk BOM uploads, large file imports, or schema changes:

- Run the orphan detection queries to verify data integrity.
- Check the Supabase advisors for any new warnings (especially RLS-related).
- Review index usage to confirm queries are performing well.

---

## Backup and Recovery

### Automatic Backups

Supabase automatically creates daily backups of the PostgreSQL database. The retention period depends on the Supabase plan:

- **Free plan:** 7 days
- **Pro plan:** 14 days
- **Enterprise:** Custom retention

Backups can be downloaded from the Supabase Dashboard under Settings > Database > Backups.

### Point-in-Time Recovery

On Pro and Enterprise plans, Supabase supports Point-in-Time Recovery (PITR), allowing restoration to any second within the backup window.

### Manual Export

For additional safety, export critical data periodically:

```sql
-- Export items to CSV (run in SQL Editor, copy results)
SELECT * FROM items ORDER BY item_number;

-- Export BOM relationships
SELECT
    i_parent.item_number AS parent,
    i_child.item_number AS child,
    b.quantity,
    b.source_file
FROM bom b
JOIN items i_parent ON b.parent_item_id = i_parent.id
JOIN items i_child ON b.child_item_id = i_child.id
ORDER BY i_parent.item_number, i_child.item_number;
```

---

## Data Integrity Checks

### Verify Foreign Key Consistency

While PostgreSQL enforces foreign keys, run these periodically for confidence:

```sql
-- Items referencing non-existent projects
SELECT i.item_number, i.project_id
FROM items i
WHERE i.project_id IS NOT NULL
  AND i.project_id NOT IN (SELECT id FROM projects);

-- Files referencing non-existent items
SELECT f.id, f.file_name, f.item_id
FROM files f
WHERE f.item_id NOT IN (SELECT id FROM items);

-- BOM referencing non-existent items
SELECT b.id, b.parent_item_id, b.child_item_id
FROM bom b
WHERE b.parent_item_id NOT IN (SELECT id FROM items)
   OR b.child_item_id NOT IN (SELECT id FROM items);
```

If foreign keys are working correctly, all these queries should return zero rows.

### Check for Duplicate Item Numbers

The `UNIQUE` constraint should prevent this, but verify:

```sql
SELECT item_number, COUNT(*) AS count
FROM items
GROUP BY item_number
HAVING COUNT(*) > 1;
```

### Check for Self-Referencing BOM Entries

```sql
SELECT b.id, i.item_number, b.quantity
FROM bom b
JOIN items i ON b.parent_item_id = i.id
WHERE b.parent_item_id = b.child_item_id;
```

### Verify RLS is Enabled

```sql
SELECT
    tablename,
    rowsecurity
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;
```

All tables should show `rowsecurity = true`.

---

## Troubleshooting

### High Connection Count

**Problem:** Supabase shows high number of active connections.

**Solution:**
- Check for connection leaks in the FastAPI backend (ensure Supabase clients are cached with `@lru_cache`).
- Review the Supabase connection pooling settings in the Dashboard.
- Use the PgBouncer connection string for pooled connections.

### Slow Queries

**Problem:** API responses are slow.

**Solution:**
- Check the Supabase SQL Editor for slow query logs.
- Run `EXPLAIN ANALYZE` on the slow query to see the execution plan.
- Verify indexes exist on filtered/joined columns (see index list in `03-DATABASE-SCHEMA.md`).
- For BOM tree queries, ensure `idx_bom_parent` and `idx_bom_child` indexes exist.

### RLS Policy Errors

**Problem:** API returns 403 or empty results unexpectedly.

**Solution:**
- Check if the operation requires the admin client (service role key) rather than the anon key.
- Review RLS policies in the Supabase Dashboard under Authentication > Policies.
- For bulk operations from the PDM Upload Service, confirm the backend is using `get_supabase_admin()`.

### Storage Quota Exceeded

**Problem:** File uploads fail with storage errors.

**Solution:**
- Check storage usage in the Supabase Dashboard.
- Clean up old file versions that are no longer needed.
- Consider upgrading the Supabase plan if storage limits are consistently reached.

---

## Related Documentation

- **Database Schema:** `Documentation/03-DATABASE-SCHEMA.md` -- Full table definitions and relationships
- **BOM and Cost Rollup:** `Documentation/06-BOM-COST-ROLLUP-GUIDE.md` -- BOM management procedures
- **Supabase Dashboard:** `https://supabase.com/dashboard`

---

**Last Updated:** 2026-01-29
