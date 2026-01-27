# PDM System - Configuration Reference

**Centralized Configuration Settings and Customization Guide**
**Related Docs:** [README.md](README.md), [01-PDM-SYSTEM-MAP.md](01-PDM-SYSTEM-MAP.md), [QUICK-START-CHECKLIST.md](17-QUICK-START-CHECKLIST.md)

---

## 🔧 Core Configuration Files

### **PDM-Library.ps1**
**Location:** `D:\PDM_PowerShell\PDM-Library.ps1`

**Global Configuration Variables:**
```powershell
# Database
$Global:DBPath    = "D:\PDM_Vault\pdm.sqlite"
$Global:SQLiteExe = "sqlite3.exe"

# Paths
$Global:PDMRoot      = "D:\PDM_Vault"
$Global:CADDataRoot  = "D:\PDM_Vault\CADData"
$Global:CheckInPath  = "D:\PDM_Vault\CADData\CheckIn"
$Global:BOMPath      = "D:\PDM_Vault\CADData\BOM"
$Global:ReleasePath  = "D:\PDM_Vault\Release"
$Global:LogPath      = "D:\PDM_Vault\logs\pdm.log"

# Tools
$Global:FreeCADExe   = "C:\Program Files\FreeCAD 0.21\bin\FreeCAD.exe"
$Global:ToolsPath    = "D:\FreeCAD\Tools"

# Service Timing
$Global:PollInterval = 5  # seconds (Worker-Processor)
```

---

## 📍 Path Configuration

### **Changing Database Location**

**Option 1: Environment Variable (Temporary)**
```powershell
$env:PDM_DB_PATH = "C:\CustomPath\pdm.sqlite"
node D:\PDM_WebServer\server.js
```

**Option 2: Edit Configuration File (Permanent)**

Edit `D:\PDM_PowerShell\PDM-Library.ps1`:
```powershell
# OLD
$Global:DBPath = "D:\PDM_Vault\pdm.sqlite"

# NEW
$Global:DBPath = "Z:\network_drive\pdm.sqlite"
```

Then restart all services.

### **Changing Vault Location**

**Not Recommended** - Requires updating 4+ files

If necessary:
1. Edit `PDM-Library.ps1`:
   ```powershell
   $Global:PDMRoot = "E:\New_Location\PDM_Vault"
   ```

2. Update `CheckIn-Watcher.ps1`:
   ```powershell
   $Global:CheckInPath = "E:\New_Location\PDM_Vault\CADData\CheckIn"
   ```

3. Create folder structure
4. Move existing data
5. Restart all services

---

## ⚙️ Service Configuration

### **Worker-Processor Poll Interval**

**File:** `D:\PDM_PowerShell\Worker-Processor.ps1`

```powershell
# CURRENT
$Global:PollInterval = 5  # Checks every 5 seconds

# SLOWER (reduce database load)
$Global:PollInterval = 10  # Checks every 10 seconds

# FASTER (quicker task processing)
$Global:PollInterval = 2   # Checks every 2 seconds
```

**Trade-offs:**
| Setting | Processing Speed | Database Load | CPU Use |
|---------|-----------------|---------------|---------|
| 2 sec | Very Fast | High | High |
| 5 sec | Fast | Medium | Medium |
| 10 sec | Slow | Low | Low |
| 30 sec | Very Slow | Very Low | Very Low |

### **CheckIn-Watcher File Detection Delay**

**File:** `D:\PDM_PowerShell\CheckIn-Watcher.ps1`

```powershell
# Delay before processing detected file (milliseconds)
# Allows file write to complete

# CURRENT
Start-Sleep -Milliseconds 800

# FASTER
Start-Sleep -Milliseconds 300  # May process incomplete files

# SAFER
Start-Sleep -Milliseconds 2000  # Waits longer for large files
```

---

## 🌐 Web Server Configuration

### **Server Port**

**File:** `D:\PDM_WebServer\server.js`

```javascript
// CURRENT
const PORT = 3000;

// CHANGE TO
const PORT = 8080;  // Or any available port
```

Then access at: `http://localhost:8080`

### **Database Connection**

**File:** `D:\PDM_WebServer\server.js`

```javascript
// CURRENT (default)
const DB_PATH = process.env.PDM_DB_PATH || 'D:\\PDM_Vault\\pdm.sqlite';

// CHANGE TO
const DB_PATH = 'Z:\\network_drive\\pdm.sqlite';

// OR use environment variable
// Set before running: set PDM_DB_PATH=Z:\network_drive\pdm.sqlite
```

### **Multi-Database Support**

To serve multiple databases (PDM + MRP):

**Option 1: Multiple Instances**
```powershell
# Terminal 1: PDM on 3000
$env:PDM_DB_PATH = "D:\PDM_Vault\pdm.sqlite"
$env:PORT = 3000
node D:\PDM_WebServer\server.js

# Terminal 2: MRP on 3001
$env:PDM_DB_PATH = "D:\MRP_System\mrp.sqlite"
$env:PORT = 3001
node D:\PDM_WebServer\server.js
```

**Option 2: Modify server.js for routing**
```javascript
// Add conditional database selection
const dbPath = req.query.db === 'mrp' ?
    'D:\\MRP_System\\mrp.sqlite' :
    'D:\\PDM_Vault\\pdm.sqlite';

// Usage: http://localhost:3000?db=pdm or http://localhost:3000?db=mrp
```

---

## 🖨️ FreeCAD Configuration

### **FreeCAD Location**

**File:** `D:\PDM_PowerShell\CheckIn-Watcher.ps1`

```powershell
# CURRENT (0.21)
$Global:FreeCADExe = "C:\Program Files\FreeCAD 0.21\bin\FreeCAD.exe"

# ALTERNATIVE (0.20)
$Global:FreeCADExe = "C:\Program Files\FreeCAD 0.20\bin\FreeCAD.exe"

# PORTABLE VERSION
$Global:FreeCADExe = "C:\FreeCAD_Portable\FreeCAD.exe"
```

### **K-Factor Configuration**

**Files:** `D:\FreeCAD\Tools\flatten_sheetmetal.bat` and `.py`

```bash
# DEFAULT K-FACTOR
REM K-factor of 0.35 (industry standard for mild steel)

REM TO CHANGE
REM Edit the Python script to use different K-factor
REM Or pass as parameter if script supports it
```

---

## 🗄️ Database Configuration

### **SQLite Pragmas**

Optimize database behavior:

```powershell
# Enable WAL mode (faster writes)
sqlite3.exe D:\PDM_Vault\pdm.sqlite "PRAGMA journal_mode=WAL;"

# Increase cache size
sqlite3.exe D:\PDM_Vault\pdm.sqlite "PRAGMA cache_size=10000;"

# Enable foreign keys
sqlite3.exe D:\PDM_Vault\pdm.sqlite "PRAGMA foreign_keys=ON;"

# Set synchronous mode (balance speed/safety)
sqlite3.exe D:\PDM_Vault\pdm.sqlite "PRAGMA synchronous=NORMAL;"  # Faster
sqlite3.exe D:\PDM_Vault\pdm.sqlite "PRAGMA synchronous=FULL;"    # Safer
```

### **Database Backup Configuration**

**Automated Daily Backup:**

```powershell
# Create script: D:\PDM_Scripts\Backup-Config.ps1
$backupDir = "D:\PDM_Backups\$(Get-Date -Format 'yyyy-MM-dd')"
New-Item -ItemType Directory -Path $backupDir -Force
Copy-Item "D:\PDM_Vault\pdm.sqlite" "$backupDir\pdm.sqlite"
```

**Schedule with Task Scheduler:**
- Frequency: Daily at 2 AM
- Action: Run PowerShell script
- Priority: Low (doesn't interfere with operations)

---

## 👤 User & Permissions Configuration

### **Service Account**

Services typically run as "Local System"

**To change service account:**
```powershell
# For NSSM-installed services
nssm set PDM_CheckInWatcher ObjectName "DOMAIN\username" "password"
nssm restart PDM_CheckInWatcher
```

### **File Permissions**

```powershell
# Ensure service account can access PDM folder
$acl = Get-Acl "D:\PDM_Vault"
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    "SYSTEM",
    "Modify",
    "ContainerInherit,ObjectInherit",
    "None",
    "Allow"
)
$acl.AddAccessRule($rule)
Set-Acl "D:\PDM_Vault" $acl
```

---

## 📊 Logging Configuration

### **Log Location**

**Current:**
```powershell
$Global:LogPath = "D:\PDM_Vault\logs\pdm.log"
```

**Change Log Location:**

Edit `D:\PDM_PowerShell\PDM-Library.ps1`:
```powershell
# OLD
$Global:LogPath = "D:\PDM_Vault\logs\pdm.log"

# NEW (network share)
$Global:LogPath = "\\NAS_Server\PDM_Logs\pdm.log"

# NEW (network drive)
$Global:LogPath = "Z:\Logs\PDM\pdm.log"
```

### **Log Rotation**

Prevent log files from getting too large:

```powershell
# Weekly log rotation script
function Rotate-PDMLogs {
    $logPath = "D:\PDM_Vault\logs\pdm.log"
    $archivePath = "D:\PDM_Vault\logs\archive"

    if (Test-Path $logPath) {
        $date = Get-Date -Format "yyyy-MM-dd"
        Copy-Item $logPath "$archivePath\pdm_$date.log"
        Clear-Content $logPath
    }
}

# Schedule weekly
```

### **Log Level Configuration**

Adjust verbosity in PDM-Library.ps1:

```powershell
# Add logging level
function Write-Log {
    param(
        [string]$Message,
        [ValidateSet("INFO", "WARN", "ERROR", "DEBUG")]
        [string]$Level = "INFO"
    )

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$timestamp] [$Level] $Message" | Add-Content $Global:LogPath
}

# Usage
Write-Log "File processed" -Level "INFO"
Write-Log "Warning: High database load" -Level "WARN"
```

---

## 🔒 Security Configuration

### **PowerShell Execution Policy**

**Current:**
```powershell
Get-ExecutionPolicy
# Should return: RemoteSigned or Unrestricted
```

**Change if needed:**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
```

### **Database Access Control**

```powershell
# Restrict database file access
$acl = Get-Acl "D:\PDM_Vault\pdm.sqlite"
# Remove everyone except SYSTEM
# Get-Acl to review current permissions
```

---

## 📋 Configuration Checklist

When setting up or modifying PDM:

- [ ] Verify all paths exist and are accessible
- [ ] Check PowerShell execution policy
- [ ] Verify SQLite installed and in PATH
- [ ] Confirm FreeCAD installation path
- [ ] Test database connection
- [ ] Verify service account permissions
- [ ] Check disk space availability
- [ ] Configure backup location
- [ ] Set up log rotation (optional)
- [ ] Configure monitoring alerts (optional)

---

## 🚨 Common Configuration Issues

**Problem:** "Cannot find path"
```powershell
# Solution: Verify path exists
Test-Path "D:\PDM_Vault\CADData\CheckIn"
# Create if missing
New-Item -ItemType Directory -Path "D:\PDM_Vault\CADData\CheckIn" -Force
```

**Problem:** "Access denied"
```powershell
# Solution: Fix permissions
# Run PowerShell as Administrator
# Then fix folder permissions
```

**Problem:** FreeCAD not found
```powershell
# Solution: Update FreeCAD path
# Check actual install location
Get-ChildItem "C:\Program Files\" | grep -i freecad
```

---

**Last Updated:** 2025-01-03
**Version:** 2.0
**Related:** [01-PDM-SYSTEM-MAP.md](01-PDM-SYSTEM-MAP.md), [22-PERFORMANCE-TUNING-GUIDE.md](22-PERFORMANCE-TUNING-GUIDE.md)
