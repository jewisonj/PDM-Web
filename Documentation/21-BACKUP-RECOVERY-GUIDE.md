# PDM-Web - Backup and Recovery Guide

**Data Protection and Disaster Recovery Procedures**
**Related Docs:** [23-SYSTEM-CONFIGURATION.md](23-SYSTEM-CONFIGURATION.md), [26-SECURITY-HARDENING.md](26-SECURITY-HARDENING.md)

---

## Overview

PDM-Web uses Supabase as its cloud-managed backend for database, authentication, and file storage. Supabase handles the majority of backup operations automatically. This guide covers what is managed for you, what you should back up manually, and how to recover from various failure scenarios.

### What Supabase Manages Automatically

| Component | Backup Method | Retention |
|-----------|--------------|-----------|
| PostgreSQL Database | Daily automatic backups | 7 days (Free), 7 days (Pro), configurable (Enterprise) |
| Point-in-Time Recovery | Continuous WAL archiving | Available on Pro plan and above |
| Auth User Data | Included in database backups | Same as database |
| Storage File Metadata | Included in database backups | Same as database |
| Storage File Blobs | Redundant cloud storage | Automatic, multi-zone redundancy |

### What You Must Back Up Manually

| Component | Location | Method |
|-----------|----------|--------|
| Application Source Code | `pdm-web/` repository | Git (hosted on GitHub/GitLab) |
| Environment Variables | `backend/.env`, `frontend/.env` | Secure offline copy |
| Upload Bridge Scripts | `scripts/pdm-upload/` | Included in git repository |
| FreeCAD Worker Scripts | `FreeCAD/Tools/`, `worker/` | Included in git repository |
| Docker Configuration | `docker-compose.yml` | Included in git repository |

---

## Supabase Automatic Backups

### Daily Backups

Supabase performs automatic daily backups of your entire PostgreSQL database. This includes all tables (items, files, bom, users, projects, work_queue, lifecycle_history, checkouts) and their data.

**To view backup status:**

1. Log in to the Supabase Dashboard at https://supabase.com/dashboard
2. Select your PDM-Web project
3. Navigate to **Settings > Database > Backups**
4. View the list of available backups with timestamps

**To restore from a daily backup:**

1. Open the Supabase Dashboard
2. Navigate to **Settings > Database > Backups**
3. Select the backup point you want to restore
4. Click **Restore** and confirm
5. Wait for the restore to complete (the project will be temporarily unavailable)
6. Verify the application is functioning correctly after restore

### Point-in-Time Recovery (Pro Plan)

On the Pro plan and above, Supabase supports point-in-time recovery (PITR), which allows you to restore the database to any specific second within the retention window. This is valuable when you need to recover from accidental data deletion or corruption at a precise moment.

**To perform point-in-time recovery:**

1. Open the Supabase Dashboard
2. Navigate to **Settings > Database > Backups > Point in Time**
3. Select the exact date and time to restore to
4. Confirm the restore operation
5. The project will restart with data as of the selected timestamp

---

## Manual Database Export

Even though Supabase handles automated backups, it is good practice to maintain independent exports for disaster recovery scenarios such as migrating to a different provider.

### Export via Supabase Dashboard

1. Open the Supabase Dashboard
2. Navigate to **SQL Editor**
3. Run an export query for each table, or use the Table Editor to export CSV data

### Export via pg_dump

Use `pg_dump` for a complete, portable database export. You can find your database connection string in the Supabase Dashboard under **Settings > Database > Connection string**.

```bash
# Full database dump (schema + data)
pg_dump "postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:5432/postgres" \
  --format=custom \
  --file=pdm_backup_$(date +%Y-%m-%d).dump

# Schema only (for migration planning)
pg_dump "postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:5432/postgres" \
  --schema-only \
  --file=pdm_schema_$(date +%Y-%m-%d).sql

# Data only (for import into existing schema)
pg_dump "postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:5432/postgres" \
  --data-only \
  --file=pdm_data_$(date +%Y-%m-%d).sql
```

**Restoring from pg_dump:**

```bash
# Restore to a new database
pg_restore --dbname="postgresql://..." --clean --if-exists pdm_backup_2025-01-15.dump

# Or restore from SQL format
psql "postgresql://..." < pdm_schema_2025-01-15.sql
```

### Scheduled Manual Export

For additional safety, you can schedule a weekly pg_dump using cron (Linux/macOS) or Task Scheduler (Windows):

```bash
# Example cron entry (weekly on Sunday at 2 AM)
0 2 * * 0 pg_dump "postgresql://..." --format=custom --file=/backups/pdm_$(date +\%Y-\%m-\%d).dump
```

```powershell
# Windows Task Scheduler - weekly export script
$connectionString = "postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:5432/postgres"
$date = Get-Date -Format "yyyy-MM-dd"
$backupPath = "C:\PDM-Backups\pdm_$date.dump"

& pg_dump $connectionString --format=custom --file=$backupPath
Write-Host "Database exported to: $backupPath"
```

---

## File Storage Backup

### Supabase Storage Redundancy

Files uploaded to Supabase Storage (buckets: `pdm-cad`, `pdm-exports`, `pdm-drawings`, `pdm-files`, `pdm-other`) are stored with automatic cloud redundancy. Supabase uses the underlying cloud provider's object storage, which provides multi-zone replication by default.

For most scenarios, this built-in redundancy is sufficient.

### Manual File Export

If you need an independent copy of all stored files (for migration or additional safety), you can download them programmatically using the Supabase client library or the Storage API.

```python
# Python script to export all files from a bucket
from supabase import create_client
import os

supabase = create_client(
    "https://lnytnxmmemdzwqburtgf.supabase.co",
    "your-service-role-key"
)

buckets = ["pdm-cad", "pdm-exports", "pdm-drawings", "pdm-files", "pdm-other"]

for bucket_name in buckets:
    output_dir = f"./file_backup/{bucket_name}"
    os.makedirs(output_dir, exist_ok=True)

    files = supabase.storage.from_(bucket_name).list()
    for file_entry in files:
        file_name = file_entry["name"]
        data = supabase.storage.from_(bucket_name).download(file_name)
        with open(os.path.join(output_dir, file_name), "wb") as f:
            f.write(data)
        print(f"Downloaded: {bucket_name}/{file_name}")
```

---

## Source Code Backup

All application code, configuration templates, and scripts are stored in the git repository. Ensure you have:

1. **Remote repository** hosted on GitHub, GitLab, or similar service
2. **Local clones** on at least one development machine
3. **Regular pushes** after any changes to the codebase

```bash
# Verify your remote is configured
git remote -v

# Push all branches and tags
git push --all origin
git push --tags origin
```

### What is in the Repository

- `frontend/` -- Vue 3 application source
- `backend/` -- FastAPI application source
- `worker/` -- FreeCAD Docker worker
- `FreeCAD/` -- FreeCAD processing scripts
- `scripts/pdm-upload/` -- Upload bridge service scripts
- `docker-compose.yml` -- Docker configuration
- `Documentation/` -- System documentation
- `.env.example` files -- Configuration templates (without secrets)

### What is NOT in the Repository

- `.env` files with actual secrets (these are in `.gitignore`)
- Supabase service role keys
- Database connection passwords

Keep a secure offline record of these values.

---

## Environment Variable Backup

Environment variables contain the secrets that connect your application to Supabase. Losing these means you cannot connect to your backend services. Store a copy securely.

**Critical variables to preserve:**

```
# Backend (.env)
SUPABASE_URL=https://lnytnxmmemdzwqburtgf.supabase.co
SUPABASE_ANON_KEY=<your-anon-key>
SUPABASE_SERVICE_KEY=<your-service-role-key>

# Frontend (.env)
VITE_SUPABASE_URL=https://lnytnxmmemdzwqburtgf.supabase.co
VITE_SUPABASE_ANON_KEY=<your-anon-key>
```

**Storage options for secrets:**

- Password manager (1Password, Bitwarden, etc.)
- Encrypted file on a separate drive
- Supabase Dashboard (keys are always available there under Settings > API)

---

## Disaster Recovery Procedures

### Scenario 1: Application Code Lost

**Impact:** Frontend and backend are unavailable.
**Recovery time:** Minutes.

1. Clone the repository from the remote:
   ```bash
   git clone <your-repo-url> pdm-web
   ```
2. Restore `.env` files from your secure backup
3. Install dependencies and start:
   ```bash
   cd pdm-web/backend && pip install -r requirements.txt
   cd pdm-web/frontend && npm install
   ```
4. Start development servers or redeploy to production

### Scenario 2: Accidental Data Deletion (Database)

**Impact:** Items, BOMs, or other records deleted.
**Recovery time:** Minutes to hours depending on plan.

**With PITR (Pro plan):**
1. Identify the timestamp just before the deletion occurred
2. Use Supabase Dashboard point-in-time recovery to restore to that moment
3. Verify data integrity after restore

**Without PITR (Free plan):**
1. Navigate to Supabase Dashboard > Settings > Database > Backups
2. Restore from the most recent daily backup
3. Any data created after the backup will be lost

**From manual pg_dump:**
1. Restore the dump to a temporary database
2. Export the specific deleted records
3. Insert them back into the production database

### Scenario 3: Accidental File Deletion (Storage)

**Impact:** CAD files, drawings, or exports are missing.
**Recovery time:** Varies.

Supabase Storage does not provide granular file-level recovery. If files are deleted from storage:

1. Check if the original files exist on local machines (e.g., the CAD workstation or `C:\PDM-Upload`)
2. Re-upload the files through the application or upload bridge script
3. If you maintain manual file backups, restore from those

### Scenario 4: Supabase Project Unavailable

**Impact:** Entire application is down.
**Recovery time:** Hours to days.

1. Check https://status.supabase.com for service outages
2. If a temporary outage, wait for Supabase to restore service
3. If a permanent issue, restore from your manual pg_dump to a new Supabase project or alternative PostgreSQL host
4. Update `.env` files with the new project URL and keys
5. Re-upload files from manual backups to new storage buckets

### Scenario 5: Environment Secrets Compromised

**Impact:** Unauthorized access to database and storage.
**Recovery time:** Minutes.

1. Immediately rotate API keys in Supabase Dashboard:
   - Navigate to **Settings > API**
   - Regenerate the anon key and service role key
2. Update `.env` files in all deployed environments
3. Restart the backend service
4. Rebuild and redeploy the frontend (anon key is embedded at build time)
5. Review Supabase Auth logs for unauthorized access
6. Review database audit logs if available

---

## Backup Verification Checklist

Perform these checks periodically to ensure your backup strategy is sound.

### Monthly

- [ ] Verify Supabase automatic backups are running (check Dashboard)
- [ ] Confirm git repository remote is accessible and up to date
- [ ] Verify you can access your stored environment secrets
- [ ] Run a manual pg_dump and confirm the export completes without errors

### Quarterly

- [ ] Test a full restore from pg_dump to a temporary database
- [ ] Verify the restored data matches production (spot-check item counts, recent records)
- [ ] Test a fresh application deployment from the git repository
- [ ] Review and update this disaster recovery documentation if the architecture has changed

---

**Last Updated:** 2025-01-29
**Version:** 3.0
**Related:** [23-SYSTEM-CONFIGURATION.md](23-SYSTEM-CONFIGURATION.md), [26-SECURITY-HARDENING.md](26-SECURITY-HARDENING.md)
