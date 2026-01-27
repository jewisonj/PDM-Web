# PDM System - Troubleshooting Decision Tree

**Diagnostic Guide for Common Issues**
**Related Docs:** [README.md](README.md), [04-SERVICES-REFERENCE.md](04-SERVICES-REFERENCE.md), [05-POWERSHELL-SCRIPTS-INDEX.md](05-POWERSHELL-SCRIPTS-INDEX.md)

---

## 🎯 Start Here - Choose Your Problem

### **PROBLEM CATEGORIES**

1. [🔴 Service Not Running](#service-not-running)
2. [📁 Files Not Being Processed](#files-not-being-processed)
3. [💾 Database Issues](#database-issues)
4. [🌐 Web Server Problems](#web-server-problems)
5. [🖨️ DXF/SVG Generation Failing](#dxfsvg-generation-failing)
6. [⚙️ Performance Issues](#performance-issues)
7. [🔒 Permission / Access Issues](#permission--access-issues)
8. [📊 Data Issues](#data-issues)

---

## 🔴 Service Not Running

**Symptom:** Service doesn't start or crashes immediately

### Step 1: Verify Service Type
- **Is it a Windows Service?**
  ```powershell
  Get-Service | Where-Object {$_.Name -like "PDM_*" -or $_.Name -eq "PDM-Browser"}
  ```
  - If not listed → [Install as Windows Service](#install-as-windows-service)
  - If listed but stopped → [Check Service Status](#check-service-status)
  - If running → [Check Service Output](#check-service-output)

- **Is it a manual PowerShell script?**
  → [Check PowerShell Configuration](#check-powershell-configuration)

### Step 2: Check PowerShell Configuration

**Error: "Cannot execute script"**
```powershell
# Check execution policy
Get-ExecutionPolicy
# Should return: RemoteSigned or Unrestricted

# If restricted, allow scripts
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
```

**Error: "PDM-Library.ps1 not found"**
```powershell
# Verify library exists
Test-Path "D:\PDM_PowerShell\PDM-Library.ps1"

# If not found, verify scripts are in correct location
ls "D:\PDM_PowerShell\" | grep -i library
```

### Step 3: Check Service Status

**For Windows Services (NSSM):**
```powershell
# Check all PDM services
Get-Service | Where-Object {$_.Name -like "PDM_*"}

# Check specific service
Get-Service -Name "PDM_CheckInWatcher" | Select-Object Name, Status, StartType

# Try to start it
Start-Service -Name "PDM_CheckInWatcher"

# Check if it stays running (wait 5 seconds)
Start-Sleep 5
Get-Service -Name "PDM_CheckInWatcher"
```

**If Status = "Stopped":**
- Try restarting: `Restart-Service -Name "PDM_CheckInWatcher"`
- Check logs: See [Check Service Output](#check-service-output)

**If Status = "Running":**
- Check output: See [Check Service Output](#check-service-output)

### Step 4: Check Service Output

**View Recent Logs:**
```powershell
# Last 50 lines
Get-Content "D:\PDM_Vault\logs\pdm.log" -Tail 50

# Follow log in real-time
Get-Content "D:\PDM_Vault\logs\pdm.log" -Wait -Tail 20

# Search for errors
Select-String -Path "D:\PDM_Vault\logs\pdm.log" -Pattern "ERROR|Exception|Failed" | Select-Object -Last 10
```

**Common Error Messages:**

| Error | Cause | Solution |
|-------|-------|----------|
| "Cannot find path" | Folder doesn't exist | Create folder or verify path |
| "Database is locked" | Another process using DB | Stop all services, check for zombie processes |
| "Access denied" | Permission issue | Run as Administrator or fix NTFS permissions |
| "FileNotFound" | Missing dependency | Verify all required files exist |

### Step 5: Install as Windows Service

If service isn't installed:
```powershell
# Download NSSM from https://nssm.cc/download
# Extract to C:\Tools\nssm\

# Open PowerShell as Administrator
cd "C:\Tools\nssm"

# Install service
.\nssm.exe install PDM_CheckInWatcher "powershell.exe" "-ExecutionPolicy Bypass -File D:\PDM_PowerShell\CheckIn-Watcher.ps1"

# Set to auto-start
.\nssm.exe set PDM_CheckInWatcher Start SERVICE_AUTO_START

# Start service
.\nssm.exe start PDM_CheckInWatcher

# Verify
Get-Service PDM_CheckInWatcher
```

---

## 📁 Files Not Being Processed

**Symptom:** Files dropped in CheckIn folder don't move to subfolders

### Step 1: Verify Service Running
```powershell
Get-Service -Name "PDM_CheckInWatcher" | Select-Object Status
```
- If stopped → See [Service Not Running](#service-not-running)
- If running → Continue to Step 2

### Step 2: Verify Folder Exists
```powershell
# Check folders exist
Test-Path "D:\PDM_Vault\CADData\CheckIn"
Test-Path "D:\PDM_Vault\CADData\STEP"
Test-Path "D:\PDM_Vault\CADData\DXF"

# If any return False, create them
New-Item -ItemType Directory -Path "D:\PDM_Vault\CADData\CheckIn" -Force
```

### Step 3: Check File Naming
- **Requirement:** Filename must start with item number (3 letters + 4-6 digits)
- **Valid:** `csp0030.step`, `wma20120.txt`, `stp01000.dxf`
- **Invalid:** `part1.step`, `test.step`, `new_file.step`

**Test with valid filename:**
```powershell
# Copy test file with valid item number
Copy-Item "some_file.step" "D:\PDM_Vault\CADData\CheckIn\csp0030.step"

# Wait 2 seconds
Start-Sleep 2

# Check if moved
Test-Path "D:\PDM_Vault\CADData\CheckIn\csp0030.step"  # Should be False (moved away)
Test-Path "D:\PDM_Vault\CADData\STEP\csp0030.step"      # Should be True (moved here)
```

### Step 4: Check Logs
```powershell
# Monitor logs in real-time
Get-Content "D:\PDM_Vault\logs\pdm.log" -Wait -Tail 50 | Select-String "csp0030|CheckIn|ERROR"
```

**Look for:**
- "Processing file: csp0030.step" - file detected
- "Moving to STEP folder" - classification successful
- "Registered in database" - database entry created

### Step 5: Verify Database
```powershell
# Check if item created
sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT * FROM items WHERE item_number='csp0030';"

# Check if file registered
sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT * FROM files WHERE item_number='csp0030';"
```

---

## 💾 Database Issues

**Symptom:** "Database is locked" or "Cannot open database"

### Step 1: Check Database File
```powershell
# Verify database exists and is accessible
Test-Path "D:\PDM_Vault\pdm.sqlite"

# Check file size (should be > 0)
(Get-Item "D:\PDM_Vault\pdm.sqlite").Length

# Check if locked
Get-Process | Where-Object {$_.Name -match "sqlite|powershell" -and $_.Name -ne "explorer"}
```

### Step 2: Stop All Services
```powershell
# Stop all PDM services
Stop-Service -Name "PDM_CheckInWatcher", "PDM_WorkerProcessor", "PDM_BOMWatcher", "PDM_PartParameterWatcher" -ErrorAction SilentlyContinue

# Wait for proper shutdown
Start-Sleep 3

# Check for zombie processes
Get-Process | Where-Object {$_.Name -eq "sqlite3"}

# Kill any stuck processes (careful!)
Get-Process sqlite3 | Stop-Process -Force
```

### Step 3: Test Database Connection
```powershell
# Test SQLite directly
sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT COUNT(*) FROM items;"

# If error, database may be corrupted
# If success, database is OK
```

### Step 4: Restart Services
```powershell
# Start services one at a time
Start-Service -Name "PDM_CheckInWatcher"
Start-Sleep 2

Start-Service -Name "PDM_BOMWatcher"
Start-Sleep 2

Start-Service -Name "PDM_WorkerProcessor"
Start-Sleep 2

# Verify all running
Get-Service | Where-Object {$_.Name -like "PDM_*"}
```

### Step 5: If Database Corrupted

**Check corruption:**
```powershell
sqlite3.exe D:\PDM_Vault\pdm.sqlite "PRAGMA integrity_check;"
```

**Recovery options:**
1. **Restore from backup** (recommended)
   ```powershell
   Copy-Item "D:\PDM_Backups\latest\pdm.sqlite" "D:\PDM_Vault\pdm.sqlite" -Force
   ```

2. **Repair database:**
   ```powershell
   sqlite3.exe D:\PDM_Vault\pdm.sqlite ".recover" | sqlite3.exe "D:\PDM_Vault\pdm_recovered.sqlite"
   # Then rename recovered database
   ```

3. **Reset database** (destructive - loses all data):
   ```powershell
   Remove-Item "D:\PDM_Vault\pdm.sqlite"
   # PDM will recreate on next run (may need manual initialization)
   ```

---

## 🌐 Web Server Problems

**Symptom:** Web server won't start or page doesn't load

### Step 1: Check Server Running
```powershell
# Check if Node.js process running
Get-Process | Where-Object {$_.Name -eq "node"}

# Test port listening
Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue

# If nothing, try to start
cd D:\PDM_WebServer
node server.js
```

### Step 2: Check Port Conflict
```powershell
# Check if port 3000 in use
Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue

# If in use, either:
# 1. Kill other process: Get-Process -Id <PID> | Stop-Process -Force
# 2. Change port in server.js line 5

# Alternative port
$env:PORT = 3001
node server.js
```

### Step 3: Check Dependencies
```powershell
# Verify npm packages installed
Test-Path "D:\PDM_WebServer\node_modules"

# If missing, install
cd D:\PDM_WebServer
npm install
```

### Step 4: Check Database Configuration
```powershell
# Verify database path in server.js
grep "DB_PATH\|PDM_DB_PATH" "D:\PDM_WebServer\server.js"

# Check database exists
Test-Path "D:\PDM_Vault\pdm.sqlite"

# Test database manually
sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT COUNT(*) FROM items;"
```

### Step 5: Browser Access
```powershell
# Try accessing in browser
# http://localhost:3000

# Or test with PowerShell
$response = Invoke-WebRequest -Uri "http://localhost:3000" -ErrorAction SilentlyContinue
$response.StatusCode  # Should be 200
```

---

## 🖨️ DXF/SVG Generation Failing

**Symptom:** DXF/SVG files not created; tasks stuck in work_queue

### Step 1: Verify Worker-Processor Running
```powershell
Get-Service -Name "PDM_WorkerProcessor" | Select-Object Status

# Check logs
Get-Content "D:\PDM_Vault\logs\pdm.log" -Tail 20 | Select-String "GENERATE_DXF|GENERATE_SVG|ERROR"
```

### Step 2: Check FreeCAD Installation
```powershell
# Verify FreeCAD exists
Test-Path "C:\Program Files\FreeCAD 0.21\bin\FreeCAD.exe"

# Test FreeCAD headless
& "C:\Program Files\FreeCAD 0.21\bin\FreeCAD.exe" --version

# Check batch files exist
Test-Path "D:\FreeCAD\Tools\flatten_sheetmetal.bat"
Test-Path "D:\FreeCAD\Tools\create_bend_drawing.bat"
```

### Step 3: Test Batch File Manually
```powershell
cd D:\FreeCAD\Tools

# Test DXF generation
.\flatten_sheetmetal.bat "D:\PDM_Vault\CADData\STEP\csp0030.step" "D:\PDM_Vault\CADData\CheckIn\csp0030_test.dxf"

# Check output
ls "D:\PDM_Vault\CADData\CheckIn\csp0030_test.dxf"
```

### Step 4: Check Work Queue
```powershell
# View pending tasks
sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT * FROM work_queue WHERE status='Pending' LIMIT 5;"

# View failed tasks
sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT * FROM work_queue WHERE status='Failed' LIMIT 5;"

# Check task details
sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT task_id, item_number, task_type, status, completed_at FROM work_queue ORDER BY created_at DESC LIMIT 10;"
```

### Step 5: Check Output Files
```powershell
# FreeCAD batch scripts write to temp
Get-Content "$env:TEMP\dxf_stdout.txt" -ErrorAction SilentlyContinue
Get-Content "$env:TEMP\dxf_stderr.txt" -ErrorAction SilentlyContinue
Get-Content "$env:TEMP\svg_stdout.txt" -ErrorAction SilentlyContinue
Get-Content "$env:TEMP\svg_stderr.txt" -ErrorAction SilentlyContinue
```

### Step 6: Manual Task Creation
```powershell
# If tasks missing, manually insert
sqlite3.exe D:\PDM_Vault\pdm.sqlite "INSERT INTO work_queue (item_number, file_path, task_type, status) VALUES ('csp0030', 'D:\PDM_Vault\CADData\STEP\csp0030.step', 'GENERATE_DXF', 'Pending');"

# Check task was created
sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT * FROM work_queue WHERE status='Pending';"

# Wait for Worker-Processor to pick it up
Start-Sleep 10

# Check result
sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT * FROM work_queue WHERE item_number='csp0030' ORDER BY created_at DESC LIMIT 1;"
```

---

## ⚙️ Performance Issues

**Symptom:** System running slow, files processing slowly

### Step 1: Check Disk Space
```powershell
# Check D: drive space
Get-PSDrive D | Select-Object Name, Used, Free

# Should have at least 100GB free
# If < 50GB, consider cleanup
```

### Step 2: Check Database Size
```powershell
# Check database file size
(Get-Item "D:\PDM_Vault\pdm.sqlite").Length / 1GB  # Size in GB

# If > 2GB, may need optimization
# Run database optimization
sqlite3.exe D:\PDM_Vault\pdm.sqlite "VACUUM;"
```

### Step 3: Monitor Service CPU/Memory
```powershell
# Check resource usage
Get-Process | Where-Object {$_.Name -like "powershell|node|FreeCAD"} | Select-Object Name, CPU, WorkingSet

# If CPU > 80% or Memory > 1GB, restart service
```

### Step 4: Increase Worker Poll Interval
```powershell
# Edit Worker-Processor.ps1
# Find: $Global:PollInterval = 5
# Change to: $Global:PollInterval = 10 (process every 10 seconds instead of 5)

# Reduces database load
```

### Step 5: Archive Old Items
```powershell
# Move obsolete items to archive
# See COMMON-WORKFLOWS.md for archive procedures
```

---

## 🔒 Permission / Access Issues

**Symptom:** "Access denied" errors in logs

### Step 1: Check Service Account
```powershell
# Services typically run as Local System
# Verify account has permissions to D:\PDM_Vault

# Test access
Test-Path "D:\PDM_Vault"
Test-Path "D:\PDM_Vault\CADData\CheckIn"

# If access denied, may need to run as Administrator
```

### Step 2: Check File Permissions
```powershell
# Get NTFS permissions
Get-Acl "D:\PDM_Vault" | Select-Object -ExpandProperty Access

# Should allow: Modify, Read, Write for service account
# If not, run PowerShell as Administrator and fix
```

### Step 3: Fix Permissions
```powershell
# Run as Administrator
$Acl = Get-Acl "D:\PDM_Vault"
$Rule = New-Object System.Security.AccessControl.FileSystemAccessRule("SYSTEM","Modify","ContainerInherit,ObjectInherit","None","Allow")
$Acl.AddAccessRule($Rule)
Set-Acl "D:\PDM_Vault" $Acl

# Recursively fix if needed
(Get-ChildItem "D:\PDM_Vault" -Recurse) | Set-Acl $Acl
```

---

## 📊 Data Issues

**Symptom:** Incorrect data in database, items missing, etc.

### Step 1: Verify Data Integrity
```powershell
# Check for orphaned files (in database but not on disk)
sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT COUNT(*) FROM files WHERE NOT EXISTS(SELECT 1 FROM files f WHERE f.file_path = files.file_path AND EXISTS(SELECT 1 FROM items WHERE files.file_path LIKE '%' || items.item_number || '%'));"
```

### Step 2: Cleanup Orphaned Files
```powershell
# Use PDM Database Cleanup tool
cd D:\PDM_PowerShell
.\PDM-Database-Cleanup.ps1 -DryRun  # Preview changes

# Then execute
.\PDM-Database-Cleanup.ps1 -Confirm
```

### Step 3: Verify Item Numbers
```powershell
# Check for invalid item numbers
sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT item_number FROM items WHERE NOT (item_number REGEXP '^[a-z]{3}\d{4,6}$');"

# Should return empty (no invalid items)
```

---

## 🆘 Still Having Issues?

If none of the above helps:

1. **Collect diagnostic information:**
   ```powershell
   # Get system info
   $diagnostics = @{
       "PSVersion" = $PSVersionTable.PSVersion
       "OS" = (Get-WmiObject win32_operatingsystem).caption
       "Services" = Get-Service | Where-Object {$_.Name -like "PDM_*"}
       "Node" = & node --version
       "Database" = if (Test-Path "D:\PDM_Vault\pdm.sqlite") { "OK" } else { "MISSING" }
       "Logs" = Get-Item "D:\PDM_Vault\logs\pdm.log" | Select-Object Length, LastWriteTime
   }
   $diagnostics
   ```

2. **Check logs for patterns:**
   ```powershell
   Select-String -Path "D:\PDM_Vault\logs\pdm.log" -Pattern "ERROR" | Group-Object -Property Line | Sort-Object -Descending Count | Select-Object -First 5
   ```

3. **Review related documentation:**
   - Service issues: [05-POWERSHELL-SCRIPTS-INDEX.md](05-POWERSHELL-SCRIPTS-INDEX.md)
   - Database: [03-DATABASE-SCHEMA.md](03-DATABASE-SCHEMA.md)
   - Web server: [08-PDM-WEBSERVER-README.md](08-PDM-WEBSERVER-README.md)

---

**Last Updated:** 2025-01-03
**Version:** 2.0
**Related:** [README.md](README.md), [COMMON-WORKFLOWS.md](COMMON-WORKFLOWS.md)
