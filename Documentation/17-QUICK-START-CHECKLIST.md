# PDM System - Quick Start Checklist

**Time to Complete:** 15-30 minutes
**Target Audience:** New users and system administrators
**Related Docs:** [README.md](README.md), [01-PDM-SYSTEM-MAP.md](01-PDM-SYSTEM-MAP.md), [COMMON-WORKFLOWS.md](COMMON-WORKFLOWS.md)

---

## ✅ Pre-Requisites Check

Before starting, verify you have:

- [ ] Windows Server 2016+ or Windows 10/11
- [ ] PowerShell 5.1 or higher
- [ ] Node.js LTS (for web server)
- [ ] FreeCAD 0.20+ (for DXF/SVG generation)
- [ ] SQLite 3.x
- [ ] Creo Parametric (optional, for native file support)
- [ ] Administrator access to the system
- [ ] 8GB RAM minimum
- [ ] 500GB disk space available

**Verify PowerShell Version:**
```powershell
$PSVersionTable.PSVersion
```

**Verify Node.js Installation:**
```powershell
node --version
npm --version
```

---

## 📁 System Folder Structure Check

Verify these folders exist on D: drive:

- [ ] `D:\PDM_Vault\` - Core system data
- [ ] `D:\PDM_Vault\CADData\` - Ingested CAD files
- [ ] `D:\PDM_Vault\CADData\CheckIn\` - Drop zone for new files
- [ ] `D:\PDM_Vault\CADData\BOM\` - Bill of Materials exports
- [ ] `D:\PDM_Vault\CADData\STEP\` - 3D models
- [ ] `D:\PDM_Vault\CADData\DXF\` - Flat patterns
- [ ] `D:\PDM_Vault\CADData\SVG\` - Technical drawings
- [ ] `D:\PDM_Vault\Released\` - Released items
- [ ] `D:\PDM_Vault\logs\` - System logs
- [ ] `D:\PDM_PowerShell\` - Automation scripts
- [ ] `D:\PDM_WebServer\` - Web interface
- [ ] `D:\FreeCAD\Tools\` - DXF/SVG generation scripts
- [ ] `D:\Documentation\` - This documentation

**Verify database exists:**
- [ ] `D:\PDM_Vault\pdm.sqlite`

---

## 🔧 Installation & Configuration

### Step 1: Database Setup
- [ ] Verify SQLite database: `D:\PDM_Vault\pdm.sqlite` exists
- [ ] Check database is readable:
  ```powershell
  Test-Path "D:\PDM_Vault\pdm.sqlite"
  ```
- [ ] Test database connection:
  ```powershell
  sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT COUNT(*) FROM items;"
  ```

### Step 2: PowerShell Configuration
- [ ] PowerShell execution policy set to allow scripts:
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  ```
- [ ] Verify PDM-Library.ps1 exists:
  ```powershell
  Test-Path "D:\PDM_PowerShell\PDM-Library.ps1"
  ```

### Step 3: FreeCAD Setup
- [ ] FreeCAD installed at: `C:\Program Files\FreeCAD 0.21\bin\`
- [ ] FreeCAD batch files exist:
  ```powershell
  Test-Path "D:\FreeCAD\Tools\flatten_sheetmetal.bat"
  Test-Path "D:\FreeCAD\Tools\create_bend_drawing.bat"
  ```

### Step 4: Node.js Web Server Setup
- [ ] Navigate to web server folder:
  ```powershell
  cd D:\PDM_WebServer
  ```
- [ ] Install dependencies (if not already done):
  ```powershell
  npm install
  ```
- [ ] Verify installation:
  ```powershell
  Test-Path "D:\PDM_WebServer\node_modules"
  ```

---

## 🚀 Service Startup (Development Mode)

For testing and development, start services in separate PowerShell windows:

### Terminal 1: File Ingestion (CheckIn-Watcher)
- [ ] Open PowerShell
- [ ] Navigate: `cd D:\PDM_PowerShell`
- [ ] Run: `.\CheckIn-Watcher.ps1`
- [ ] Verify output shows "Watching: D:\PDM_Vault\CADData\CheckIn"

### Terminal 2: Task Processing (Worker-Processor)
- [ ] Open PowerShell
- [ ] Navigate: `cd D:\PDM_PowerShell`
- [ ] Run: `.\Worker-Processor.ps1`
- [ ] Verify output shows "Worker-Processor started"

### Terminal 3: BOM Processing (BOM-Watcher)
- [ ] Open PowerShell
- [ ] Navigate: `cd D:\PDM_PowerShell`
- [ ] Run: `.\BOM-Watcher.ps1`
- [ ] Verify output shows "BOM-Watcher started"

### Terminal 4: Web Server
- [ ] Open PowerShell
- [ ] Navigate: `cd D:\PDM_WebServer`
- [ ] Run: `node server.js`
- [ ] Verify: "PDM Browser Server running on http://localhost:3000"

---

## ✔️ Verification Steps

Once all services are running, verify functionality:

### Check Services Are Running
```powershell
# In a new PowerShell window
Get-Process | Select-Object Name | Where-Object {$_.Name -match "node|powershell"}
```

### Test File Ingestion
- [ ] Copy a test file to: `D:\PDM_Vault\CADData\CheckIn\test.txt`
- [ ] Wait 2 seconds
- [ ] Verify it moved to: `D:\PDM_Vault\CADData\Archive\test.txt`
- [ ] Check logs:
  ```powershell
  Get-Content "D:\PDM_Vault\logs\pdm.log" -Tail 10
  ```

### Test Database Query
```powershell
sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT COUNT(*) as item_count FROM items;"
```

### Test Web Server
- [ ] Open browser to: `http://localhost:3000`
- [ ] Verify page loads and shows items (if any exist)

### Test Log Files
- [ ] Check logs created: `D:\PDM_Vault\logs\pdm.log`
- [ ] Verify recent entries with timestamps

---

## 📋 First Time Operations

Once basic setup is verified, try these operations:

### 1. Add Your First Item
- [ ] Create a simple test CAD file (or use existing)
- [ ] Copy to: `D:\PDM_Vault\CADData\CheckIn\`
- [ ] Monitor in CheckIn-Watcher terminal for processing
- [ ] Verify file moved to appropriate subfolder
- [ ] Query database for new item:
  ```powershell
  sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT item_number FROM items LIMIT 1;"
  ```

### 2. Test BOM Processing
- [ ] Export BOM from Creo as `.txt` file
- [ ] Place in: `D:\PDM_Vault\CADData\BOM\`
- [ ] Monitor in BOM-Watcher terminal
- [ ] Verify BOM table updated:
  ```powershell
  sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT COUNT(*) as bom_count FROM bom;"
  ```

### 3. Test Web Server
- [ ] Open: `http://localhost:3000`
- [ ] Verify items appear in table
- [ ] Click an item to see details
- [ ] Verify BOM relationships display

### 4. Test Cost Calculation
- [ ] Update some item prices in database
- [ ] Run BOM cost tool:
  ```powershell
  cd D:\PDM_PowerShell
  .\Get-BOMCost.ps1 -Assembly "your_item_number"
  ```

---

## 🪟 Windows Service Installation (Production)

Once verified in development mode, install as Windows services:

### For Each Service (use NSSM):

1. **Download NSSM** from https://nssm.cc/download
2. **Open PowerShell as Administrator**
3. **For CheckIn-Watcher:**
   ```powershell
   C:\Tools\nssm\nssm.exe install PDM_CheckInWatcher "powershell.exe" "-ExecutionPolicy Bypass -File D:\PDM_PowerShell\CheckIn-Watcher.ps1"
   C:\Tools\nssm\nssm.exe start PDM_CheckInWatcher
   ```

4. **For Worker-Processor:**
   ```powershell
   C:\Tools\nssm\nssm.exe install PDM_WorkerProcessor "powershell.exe" "-ExecutionPolicy Bypass -File D:\PDM_PowerShell\Worker-Processor.ps1"
   C:\Tools\nssm\nssm.exe start PDM_WorkerProcessor
   ```

5. **For BOM-Watcher:**
   ```powershell
   C:\Tools\nssm\nssm.exe install PDM_BOMWatcher "powershell.exe" "-ExecutionPolicy Bypass -File D:\PDM_PowerShell\BOM-Watcher.ps1"
   C:\Tools\nssm\nssm.exe start PDM_BOMWatcher
   ```

6. **For Web Server (Node.js):**
   ```powershell
   C:\Tools\nssm\nssm.exe install PDM-Browser "C:\Program Files\nodejs\node.exe" "D:\PDM_WebServer\server.js"
   C:\Tools\nssm\nssm.exe set PDM-Browser AppDirectory "D:\PDM_WebServer"
   C:\Tools\nssm\nssm.exe start PDM-Browser
   ```

### Verify Services Running
```powershell
Get-Service | Where-Object {$_.Name -like "PDM_*" -or $_.Name -eq "PDM-Browser"}
```

---

## 🔍 Troubleshooting First-Time Setup

### Service Won't Start
- [ ] Check PowerShell version: `$PSVersionTable.PSVersion` (need 5.1+)
- [ ] Check execution policy: `Get-ExecutionPolicy`
- [ ] Review logs: `Get-Content "D:\PDM_Vault\logs\pdm.log" -Tail 20`
- [ ] Check folder exists and is readable: `Test-Path "D:\PDM_Vault\CADData\CheckIn"`

### Database Connection Error
- [ ] Verify database file exists: `Test-Path "D:\PDM_Vault\pdm.sqlite"`
- [ ] Check file permissions (should be readable)
- [ ] Test with sqlite3: `sqlite3.exe D:\PDM_Vault\pdm.sqlite ".tables"`
- [ ] Verify no locked files: `Get-Process | Select-Object Name` (look for sqlite3)

### Files Not Being Processed
- [ ] Verify CheckIn-Watcher is running (check terminal)
- [ ] Check folder exists: `Test-Path "D:\PDM_Vault\CADData\CheckIn"`
- [ ] Look in logs: `Get-Content "D:\PDM_Vault\logs\pdm.log" -Wait -Tail 20`
- [ ] Verify file naming (must start with item number like ABC####)

### Web Server Won't Load
- [ ] Check port 3000 isn't in use: `Get-NetTCPConnection -LocalPort 3000`
- [ ] Verify Node.js running: `Get-Process | Where-Object Name -eq "node"`
- [ ] Check server output for errors
- [ ] Try different port by editing: `D:\PDM_WebServer\server.js` line 5

### FreeCAD Generation Failing
- [ ] Verify FreeCAD installed: `Test-Path "C:\Program Files\FreeCAD 0.21\bin\FreeCAD.exe"`
- [ ] Test batch file manually: `D:\FreeCAD\Tools\flatten_sheetmetal.bat`
- [ ] Check work queue: `sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT * FROM work_queue WHERE status='Failed';"`
- [ ] Review FreeCAD output: Check `$env:TEMP\dxf_stdout.txt` and `$env:TEMP\dxf_stderr.txt`

---

## 📚 Next Steps After Setup

Once basic setup is complete:

1. **Learn Daily Operations:** Read [COMMON-WORKFLOWS.md](COMMON-WORKFLOWS.md)
2. **Understand the System:** Read [02-PDM-COMPLETE-OVERVIEW.md](02-PDM-COMPLETE-OVERVIEW.md)
3. **Learn File Locations:** Reference [01-PDM-SYSTEM-MAP.md](01-PDM-SYSTEM-MAP.md)
4. **For Issues:** Use [TROUBLESHOOTING-DECISION-TREE.md](TROUBLESHOOTING-DECISION-TREE.md)
5. **For Tools:** See specific tool guides (BOM Cost, Cleanup, etc.)

---

## 💾 Backup Before Production

Once everything is working, create a backup:

```powershell
# Create backup directory
$backupDate = Get-Date -Format "yyyy-MM-dd"
$backupPath = "D:\PDM_Backups\$backupDate"
New-Item -ItemType Directory -Path $backupPath -Force

# Backup database
Copy-Item "D:\PDM_Vault\pdm.sqlite" "$backupPath\pdm.sqlite"

# Backup scripts
Copy-Item "D:\PDM_PowerShell" "$backupPath\PDM_PowerShell" -Recurse

Write-Host "Backup created at: $backupPath"
```

---

## ✅ Setup Complete Checklist

- [ ] All prerequisites verified
- [ ] Folder structure verified
- [ ] Database working
- [ ] Services running (development mode)
- [ ] File ingestion tested
- [ ] BOM processing tested
- [ ] Web server working
- [ ] First item successfully created
- [ ] Backup created
- [ ] Windows services installed (if going production)

---

**Status:** ✅ Ready to Use
**Time to Complete:** 15-30 minutes
**Next Step:** Read [COMMON-WORKFLOWS.md](COMMON-WORKFLOWS.md) for daily operations

For detailed setup instructions, see [08-PDM-WEBSERVER-README.md](08-PDM-WEBSERVER-README.md) and [02-PDM-COMPLETE-OVERVIEW.md](02-PDM-COMPLETE-OVERVIEW.md)
