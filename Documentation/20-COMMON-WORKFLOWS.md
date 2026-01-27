# PDM System - Common Workflows & Procedures

**Step-by-Step Guides for Daily Operations**
**Related Docs:** [README.md](README.md), [QUICK-START-CHECKLIST.md](17-QUICK-START-CHECKLIST.md), [COMMON-WORKFLOWS.md](COMMON-WORKFLOWS.md)

---

## 🚀 Most Common Tasks

### 1. Check In a New CAD File

**Time Required:** 2-3 minutes
**Tools Needed:** File explorer or command line
**Services Required:** CheckIn-Watcher running

**Steps:**

1. **Prepare file with correct naming:**
   - Item number must be 3 letters + 4-6 digits
   - Example: `csp0030.prt`, `wma20120.stp`
   - Lowercase recommended
   ```powershell
   # If file has wrong name, rename it
   Rename-Item "my_part.step" "csp0030.step"
   ```

2. **Copy file to CheckIn folder:**
   ```powershell
   Copy-Item "csp0030.step" "D:\PDM_Vault\CADData\CheckIn\"
   ```

3. **Wait for automatic processing:**
   - CheckIn-Watcher automatically detects file
   - Processing takes 1-3 seconds depending on file type
   - File automatically moves to appropriate subfolder (STEP\, DXF\, etc.)

4. **Verify in database:**
   ```powershell
   sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT item_number, COUNT(*) as file_count FROM files WHERE item_number='csp0030' GROUP BY item_number;"
   ```

5. **Verify in web browser:**
   - Open: `http://localhost:3000`
   - Search for item: `csp0030`
   - Should see item in table with files listed

**Troubleshooting:**
- File not moving → Check filename (must start with item number)
- Item not appearing → Wait a few seconds, refresh browser
- See [19-TROUBLESHOOTING-DECISION-TREE.md](19-TROUBLESHOOTING-DECISION-TREE.md)

---

### 2. Process a BOM (Bill of Materials)

**Time Required:** 5-10 minutes
**Tools Needed:** Creo
**Services Required:** BOM-Watcher running

**Steps:**

1. **Export BOM from Creo:**
   - Open assembly in Creo
   - Use: Tools → Table → Tree → Create Drawing
   - Export to text file
   - Include columns: Description, Project, Material, Mass, Thickness, Cut_Length, Price_Est

2. **Name file correctly:**
   - Must start with assembly item number
   - Example: `wma20120.txt` for assembly wma20120
   ```powershell
   # If named wrong, rename
   Rename-Item "bom_export.txt" "wma20120.txt"
   ```

3. **Place in BOM folder:**
   ```powershell
   Copy-Item "wma20120.txt" "D:\PDM_Vault\CADData\BOM\"
   ```

4. **Wait for automatic processing:**
   - BOM-Watcher detects and processes file (1-2 seconds)
   - Parses parent and child relationships
   - Updates database
   - Automatically deletes processed .txt file

5. **Verify in database:**
   ```powershell
   # Check BOM relationships created
   sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT child_item, SUM(quantity) as qty FROM bom WHERE parent_item='wma20120' GROUP BY child_item;"

   # Check item properties updated
   sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT item_number, material, mass FROM items WHERE item_number='wma20120';"
   ```

6. **Verify in web browser:**
   - Open: `http://localhost:3000`
   - Find assembly: `wma20120`
   - Click to see detail panel
   - "Bill of Materials" section should show children

**Troubleshooting:**
- BOM not processed → Check filename matches assembly item number
- Properties not updated → Verify columns in BOM export
- See [19-TROUBLESHOOTING-DECISION-TREE.md](19-TROUBLESHOOTING-DECISION-TREE.md)

---

### 3. Calculate BOM Cost

**Time Required:** 1 minute
**Tools Needed:** PowerShell
**Services Required:** None (runs on-demand)
**Prerequisites:** Prices must be in database

**Steps:**

1. **Open PowerShell:**
   ```powershell
   cd D:\PDM_PowerShell
   ```

2. **Run cost rollup script:**
   ```powershell
   .\Get-BOMCost.ps1 -Assembly "wma20120"
   ```

3. **View results:**
   - Script displays hierarchical cost breakdown
   - Shows assembly cost, component costs, subtotals
   - Color-coded for easy reading

4. **For multiple quantities:**
   ```powershell
   .\Get-BOMCost.ps1 -Assembly "wma20120" -Quantity 10
   # Shows total cost for 10 units
   # Shows per-unit cost
   ```

**Example Output:**
```
==================================================
  BOM Cost Rollup for wma20120
==================================================

[ASM] wma20120 x1 @ $50.00
  [PART] csp0030 x4 @ $2.50 = $10.00
  [ASM] sub_asm x2 @ $15.00
    [PART] csp0031 x2 @ $3.75 = $7.50
  Subtotal: $77.50 = $50.00 (Assembly) + $27.50 (Children)

==================================================
  Total Estimated Cost: $77.50
==================================================
```

**Troubleshooting:**
- "All prices show as 'no price'" → Need to update item prices in database
- See [06-BOM-COST-ROLLUP-GUIDE.md](06-BOM-COST-ROLLUP-GUIDE.md)

---

### 4. Generate Manufacturing Documents (DXF/SVG)

**Time Required:** 10-30 seconds (per file)
**Tools Needed:** FreeCAD (automatic)
**Services Required:** Worker-Processor running
**Prerequisites:** STEP file must exist

**Automatic Generation:**
When you check in an updated STEP file for an item that already has DXF/SVG:

1. **Check in updated STEP:**
   ```powershell
   Copy-Item "csp0030_updated.step" "D:\PDM_Vault\CADData\CheckIn\csp0030.step"
   ```

2. **CheckIn-Watcher automatically:**
   - Detects existing DXF/SVG
   - Queues GENERATE_DXF and GENERATE_SVG tasks
   - Adds tasks to work_queue

3. **Worker-Processor automatically:**
   - Picks up tasks (within 5 seconds)
   - Calls FreeCAD to generate files
   - Places DXF/SVG in CheckIn folder
   - CheckIn-Watcher registers them

4. **Verify generation:**
   ```powershell
   # Check if generation tasks completed
   sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT task_type, status FROM work_queue WHERE item_number='csp0030' AND status='Completed';"

   # Check files exist
   ls "D:\PDM_Vault\CADData\DXF\csp0030*"
   ls "D:\PDM_Vault\CADData\SVG\csp0030*"
   ```

**Manual Generation:**
If files don't auto-generate:

```powershell
# Insert task manually
sqlite3.exe D:\PDM_Vault\pdm.sqlite "INSERT INTO work_queue (item_number, file_path, task_type, status) VALUES ('csp0030', 'D:\PDM_Vault\CADData\STEP\csp0030.step', 'GENERATE_DXF', 'Pending');"

# Wait for processing
Start-Sleep 15

# Check result
sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT * FROM work_queue WHERE item_number='csp0030' ORDER BY created_at DESC LIMIT 2;"
```

---

### 5. Clean Up Orphaned Files

**Time Required:** 2-5 minutes
**Tools Needed:** PowerShell
**Services Required:** None (can run anytime)
**Safety:** Dry-run mode available

**Steps:**

1. **Preview cleanup (dry-run):**
   ```powershell
   cd D:\PDM_PowerShell
   .\PDM-Database-Cleanup.ps1 -DryRun
   ```
   - Shows what would be deleted
   - Does NOT delete anything

2. **Review results:**
   - Look for expected orphaned files
   - Verify no important files listed

3. **Execute cleanup:**
   ```powershell
   .\PDM-Database-Cleanup.ps1 -Confirm
   ```
   - Prompts for confirmation before deleting
   - Shows progress
   - Updates database

4. **Verify cleanup:**
   ```powershell
   # Should have fewer orphaned entries
   sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT COUNT(*) FROM files WHERE file_path NOT IN (SELECT file_path FROM files WHERE file_path != '');"
   ```

**Safety:**
- Dry-run mode shows what would happen
- Confirmation prompt before actual deletion
- Backup created by tool if requested
- See [07-PDM-DATABASE-CLEANUP-GUIDE.md](07-PDM-DATABASE-CLEANUP-GUIDE.md)

---

### 6. Release an Item (Future - When Multi-User Ready)

**Status:** IN DEVELOPMENT - Not yet used
**Prerequisites:** Release-Watcher service (not yet fully implemented)

**Planned Workflow:**
1. Item in Design state ready for production
2. Copy item files to Release folder: `D:\PDM_Vault\Release\`
3. Release-Watcher automatically:
   - Transitions item to Released state
   - Locks files
   - Creates audit trail entry
4. Item appears in Released folder
5. Item is read-only

**Current Workaround:**
Manually update database:
```powershell
sqlite3.exe D:\PDM_Vault\pdm.sqlite "UPDATE items SET lifecycle_state='Released' WHERE item_number='csp0030';"
```

---

### 7. Back Up Your System

**Time Required:** 5-10 minutes (first time)
**Frequency:** Daily recommended
**Tools Needed:** PowerShell

**Basic Backup:**
```powershell
# Create backup directory
$date = Get-Date -Format "yyyy-MM-dd"
$backupPath = "D:\PDM_Backups\$date"
New-Item -ItemType Directory -Path $backupPath -Force

# Backup database (most critical)
Copy-Item "D:\PDM_Vault\pdm.sqlite" "$backupPath\pdm.sqlite"

# Backup CAD files (large but important)
Copy-Item "D:\PDM_Vault\CADData" "$backupPath\CADData" -Recurse

Write-Host "Backup complete at: $backupPath"
```

**Automated Daily Backup:**
Create scheduled task:
```powershell
# Create PowerShell script: D:\PDM_Scripts\Daily-Backup.ps1
# Content:
$date = Get-Date -Format "yyyy-MM-dd"
$backupPath = "D:\PDM_Backups\$date"
New-Item -ItemType Directory -Path $backupPath -Force
Copy-Item "D:\PDM_Vault\pdm.sqlite" "$backupPath\pdm.sqlite"

# Schedule it:
# Task Scheduler → New Task → Run D:\PDM_Scripts\Daily-Backup.ps1 daily at 2 AM
```

See [21-BACKUP-RECOVERY-GUIDE.md](21-BACKUP-RECOVERY-GUIDE.md)

---

### 8. Monitor System Health

**Time Required:** 2-3 minutes daily
**Frequency:** Daily
**Tools Needed:** PowerShell, web browser

**Daily Checklist:**
```powershell
# Check all services running
Get-Service | Where-Object {$_.Name -like "PDM_*"} | Select-Object Name, Status

# Check for errors in logs
Get-Content "D:\PDM_Vault\logs\pdm.log" -Tail 50 | Select-String "ERROR"

# Check disk space
Get-PSDrive D | Select-Object Name, @{n='Used (GB)';e={[math]::Round($_.Used/1GB,2)}}, @{n='Free (GB)';e={[math]::Round($_.Free/1GB,2)}}

# Check database size
[math]::Round((Get-Item "D:\PDM_Vault\pdm.sqlite").Length / 1GB, 2)

# Check web server
Invoke-WebRequest -Uri "http://localhost:3000" -ErrorAction SilentlyContinue | Select-Object StatusCode
```

---

## 🔄 Periodic Maintenance

### Weekly
- [ ] Review error logs
- [ ] Check disk space (should be > 200GB free)
- [ ] Verify all services running
- [ ] Test web server access

### Monthly
- [ ] Clean up orphaned files
- [ ] Optimize database
- [ ] Review system performance
- [ ] Backup and verify

### Quarterly
- [ ] Full system backup and test restore
- [ ] Review and archive obsolete items
- [ ] Update documentation
- [ ] Performance analysis

---

## 📊 Database Queries for Monitoring

**Item Statistics:**
```powershell
# Count items by lifecycle state
sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT lifecycle_state, COUNT(*) FROM items GROUP BY lifecycle_state;"

# Recent items
sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT item_number, created_at FROM items ORDER BY created_at DESC LIMIT 10;"

# Items with most files
sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT item_number, COUNT(*) as file_count FROM files GROUP BY item_number ORDER BY file_count DESC LIMIT 5;"
```

**System Health:**
```powershell
# Pending tasks
sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT COUNT(*) FROM work_queue WHERE status='Pending';"

# Failed tasks
sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT COUNT(*) FROM work_queue WHERE status='Failed';"

# Currently checked out
sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT COUNT(*) FROM checkouts;"
```

---

**Last Updated:** 2025-01-03
**Version:** 2.0
**Related:** [README.md](README.md), [17-QUICK-START-CHECKLIST.md](17-QUICK-START-CHECKLIST.md), [19-TROUBLESHOOTING-DECISION-TREE.md](19-TROUBLESHOOTING-DECISION-TREE.md)
