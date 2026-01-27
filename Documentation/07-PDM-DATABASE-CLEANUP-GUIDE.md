# PDM Database Cleanup Tool - Usage Guide

## Overview

This tool scans the PDM database for references to files that no longer exist on disk and removes those database entries. Perfect for cleaning up after manually deleting mis-generated DXFs, SVGs, PDFs, or other files.

## Features

✅ Scans for missing files in the database
✅ Removes orphaned file entries
✅ Removes orphaned items (items with no files)
✅ Cleans up BOM references to orphaned items
✅ Supports dry-run mode (preview without changes)
✅ Filter by file type
✅ Detailed logging
✅ Statistics before and after

## Safety Features

- **Dry Run Mode**: Preview what would be deleted without making changes
- **Confirmation Prompts**: Asks for confirmation before deleting
- **Detailed Logging**: All operations logged with timestamps
- **Statistics**: Shows counts before and after cleanup

## Usage

### Basic Usage (All File Types)

```powershell
.\PDM-Database-Cleanup.ps1
```

This will:
1. Scan all files in the database
2. Check if they exist on disk
3. Prompt for confirmation
4. Remove orphaned entries

### Dry Run (Preview Only)

```powershell
.\PDM-Database-Cleanup.ps1 -DryRun
```

Shows what would be deleted without making any changes. **Always run this first!**

### Filter by File Type

```powershell
# Only check/clean DXF files
.\PDM-Database-Cleanup.ps1 -FileType DXF

# Only check/clean SVG files
.\PDM-Database-Cleanup.ps1 -FileType SVG

# Only check/clean PDF files
.\PDM-Database-Cleanup.ps1 -FileType PDF

# Only check/clean STEP files
.\PDM-Database-Cleanup.ps1 -FileType STEP

# Only check/clean CAD files
.\PDM-Database-Cleanup.ps1 -FileType CAD
```

### Verbose Output

```powershell
.\PDM-Database-Cleanup.ps1 -Verbose
```

Shows every file checked (exists or missing), not just missing files.

### Combined Parameters

```powershell
# Dry run for DXF files with verbose output
.\PDM-Database-Cleanup.ps1 -DryRun -FileType DXF -Verbose

# Clean only SVG files with verbose logging
.\PDM-Database-Cleanup.ps1 -FileType SVG -Verbose
```

## Common Workflows

### Workflow 1: Clean Up Bad DXF Files

You generated some DXFs that came out wrong and manually deleted them from the CADData folder.

```powershell
# 1. Preview what will be cleaned
.\PDM-Database-Cleanup.ps1 -DryRun -FileType DXF

# 2. If it looks good, run the cleanup
.\PDM-Database-Cleanup.ps1 -FileType DXF

# 3. Type "yes" to confirm
```

### Workflow 2: Clean Up Old SVG Files

You manually deleted some old SVG drawings from the vault.

```powershell
# Preview
.\PDM-Database-Cleanup.ps1 -DryRun -FileType SVG

# Clean
.\PDM-Database-Cleanup.ps1 -FileType SVG
```

### Workflow 3: Full Database Cleanup

You've done a lot of manual file cleanup and want to clean everything.

```powershell
# Preview everything
.\PDM-Database-Cleanup.ps1 -DryRun -Verbose

# Clean everything
.\PDM-Database-Cleanup.ps1

# Confirm when prompted
```

### Workflow 4: Audit Without Changes

Just see what's missing without cleaning anything.

```powershell
.\PDM-Database-Cleanup.ps1 -DryRun -Verbose > audit-report.txt
```

## What Gets Cleaned

### 1. Orphaned File Entries
Files in the database that no longer exist on disk:
- CAD files (.prt, .asm, .drw)
- STEP files (.step, .stp)
- DXF files (.dxf)
- SVG files (.svg)
- PDF files (.pdf)

### 2. Orphaned Items
Items that have no files associated with them (after file cleanup):
- Item record removed from `items` table
- BOM references removed from `bom` table
- Prevents "ghost" items with no actual files

## Output Example

```
[2025-12-31 22:15:00] [INFO] ========================================
[2025-12-31 22:15:00] [INFO] PDM Database Cleanup Tool
[2025-12-31 22:15:00] [INFO] ========================================
[2025-12-31 22:15:00] [INFO] Database: D:\PDM_Vault\pdm.sqlite
[2025-12-31 22:15:00] [INFO] Log File: D:\PDM_Vault\Logs\database-cleanup-2025-12-31_22-15-00.log

[2025-12-31 22:15:00] [INFO] Database Statistics:
[2025-12-31 22:15:00] [INFO]   Total Items : 250
[2025-12-31 22:15:00] [INFO]   Total Files : 1247
[2025-12-31 22:15:00] [INFO]   CAD Files : 250
[2025-12-31 22:15:00] [INFO]   STEP Files : 250
[2025-12-31 22:15:00] [INFO]   DXF Files : 243
[2025-12-31 22:15:00] [INFO]   SVG Files : 248
[2025-12-31 22:15:00] [INFO]   PDF Files : 256
[2025-12-31 22:15:00] [INFO]   BOM Entries : 450
[2025-12-31 22:15:00] [INFO]   Pending Tasks : 0

[2025-12-31 22:15:01] [INFO] Querying database for files...
[2025-12-31 22:15:02] [INFO] Scanned 1247 files, found 15 missing
[2025-12-31 22:15:02] [WARN] Found 15 orphaned file entries

WARNING: About to delete 15 database entries!
Files to be removed from database:
  DXF: 8 files
  SVG: 5 files
  PDF: 2 files

Continue with deletion? (yes/no): yes

[2025-12-31 22:15:05] [INFO] Removing orphaned file entries...
[2025-12-31 22:15:05] [SUCCESS] Deleted: [DXF] xxa00100 - D:\PDM_Vault\CADData\DXF\xxa00100.dxf
[2025-12-31 22:15:05] [SUCCESS] Deleted: [DXF] xxp00200 - D:\PDM_Vault\CADData\DXF\xxp00200.dxf
...
[2025-12-31 22:15:06] [SUCCESS] Cleanup complete: 15 deleted, 0 failed

[2025-12-31 22:15:06] [INFO] Checking for items with no files...
[2025-12-31 22:15:06] [INFO] No orphaned items found

[2025-12-31 22:15:06] [INFO] Final Statistics:
[2025-12-31 22:15:06] [INFO]   Total Items : 250
[2025-12-31 22:15:06] [INFO]   Total Files : 1232
[2025-12-31 22:15:06] [INFO]   DXF Files : 235
[2025-12-31 22:15:06] [INFO]   SVG Files : 243
[2025-12-31 22:15:06] [INFO]   PDF Files : 254

[2025-12-31 22:15:06] [SUCCESS] ========================================
[2025-12-31 22:15:06] [SUCCESS] Cleanup Complete
[2025-12-31 22:15:06] [SUCCESS] ========================================
[2025-12-31 22:15:06] [INFO] Log saved to: D:\PDM_Vault\Logs\database-cleanup-2025-12-31_22-15-00.log
```

## Logs

Logs are saved to:
```
D:\PDM_Vault\Logs\database-cleanup-YYYY-MM-DD_HH-mm-ss.log
```

Each run creates a new log file with timestamp.

## When to Use This Tool

✅ After manually deleting mis-generated DXF files
✅ After manually deleting bad SVG drawings
✅ After manually deleting old PDF documentation
✅ After manually removing files from the vault
✅ Periodic maintenance to keep database in sync with filesystem
✅ Before database backups to clean up unnecessary entries

## Safety Notes

1. **Always run with -DryRun first** to see what will be deleted
2. **Backup your database** before running (optional but recommended):
   ```powershell
   Copy-Item D:\PDM_Vault\pdm.sqlite D:\PDM_Vault\pdm.sqlite.backup
   ```
3. **Stop services** if they're running to avoid conflicts (optional)
4. **Review the log file** after cleanup to verify results

## Requirements

- SQLite3.exe must be in PATH
- Database: `D:\PDM_Vault\pdm.sqlite`
- PowerShell 5.1 or later
- Administrator privileges (for database access)

## Troubleshooting

### sqlite3.exe not found
Download SQLite tools from: https://www.sqlite.org/download.html
Add to PATH or place in a directory that's in your PATH.

### Access denied
Run PowerShell as Administrator.

### Database locked
Stop PDM services that might be accessing the database:
```powershell
Stop-Service CheckIn-Watcher
Stop-Service BOM-Watcher
Stop-Service Release-Watcher
Stop-Service Worker-Processor
```

Run cleanup, then restart services:
```powershell
Start-Service CheckIn-Watcher
Start-Service BOM-Watcher
Start-Service Release-Watcher
Start-Service Worker-Processor
```

## Integration with Workflow

This tool is meant to be run **manually** as an admin task when you:
1. Notice files are missing but still referenced in database
2. Have manually deleted files and want to clean up
3. Want to audit database integrity

It's **not** meant to run automatically - you want control over what gets deleted from the database.

## Future Enhancements

Possible additions:
- [ ] Web UI for cleanup
- [ ] Schedule automatic scans (with email reports)
- [ ] Vacuum database after cleanup
- [ ] Export orphaned file list to CSV
- [ ] Restore from backup if cleanup goes wrong
