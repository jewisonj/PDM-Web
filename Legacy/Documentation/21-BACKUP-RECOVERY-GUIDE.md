# PDM System - Backup & Recovery Guide

**Data Protection and Disaster Recovery Procedures**
**Related Docs:** [README.md](README.md), [20-COMMON-WORKFLOWS.md](20-COMMON-WORKFLOWS.md), [23-SYSTEM-CONFIGURATION.md](23-SYSTEM-CONFIGURATION.md)

---

## 🎯 Quick Start - Daily Backup

**Minimum Required (5 minutes):**
```powershell
# Create daily backup
$date = Get-Date -Format "yyyy-MM-dd"
$backupPath = "D:\PDM_Backups\$date"
New-Item -ItemType Directory -Path $backupPath -Force
Copy-Item "D:\PDM_Vault\pdm.sqlite" "$backupPath\pdm.sqlite"
Write-Host "Database backed up to: $backupPath"
```

**Complete Backup (10 minutes):**
```powershell
$date = Get-Date -Format "yyyy-MM-dd"
$backupPath = "D:\PDM_Backups\$date"
New-Item -ItemType Directory -Path $backupPath -Force
Copy-Item "D:\PDM_Vault\pdm.sqlite" "$backupPath\pdm.sqlite"
Copy-Item "D:\PDM_Vault\CADData" "$backupPath\CADData" -Recurse
Copy-Item "D:\PDM_PowerShell" "$backupPath\PDM_PowerShell" -Recurse
Write-Host "Full backup complete at: $backupPath"
```

---

## 📋 What to Backup

### **CRITICAL (Must Backup)**

| Item | Location | Size | Frequency |
|------|----------|------|-----------|
| Database | D:\PDM_Vault\pdm.sqlite | 50MB-2GB | Daily |
| CAD Files | D:\PDM_Vault\CADData\ | 10GB-100GB | Daily |
| System Logs | D:\PDM_Vault\logs\ | 10MB-100MB | Weekly |

### **IMPORTANT (Should Backup)**

| Item | Location | Size |
|------|----------|------|
| PowerShell Scripts | D:\PDM_PowerShell\ | 100MB |
| Web Server | D:\PDM_WebServer\ | 50MB |
| Configuration | Various | <5MB |

### **OPTIONAL (Nice to Have)**

| Item | Location | Size |
|------|----------|------|
| Documentation | D:\Documentation\ | 300KB |
| Backups folder | D:\PDM_Backups\ | Varies |

---

## 🔄 Backup Strategies

### **Strategy 1: Daily Full Backup**
**Best for:** Small installations < 50GB
**Frequency:** Daily
**Storage:** 7+ copies (one per week)

```powershell
# Daily backup script
function Backup-PDM {
    $date = Get-Date -Format "yyyy-MM-dd"
    $backupPath = "D:\PDM_Backups\Daily\$date"

    New-Item -ItemType Directory -Path $backupPath -Force | Out-Null
    Copy-Item "D:\PDM_Vault\pdm.sqlite" "$backupPath\pdm.sqlite"
    Copy-Item "D:\PDM_Vault\CADData" "$backupPath\CADData" -Recurse

    Write-Host "Backup created: $backupPath"
}

Backup-PDM
```

### **Strategy 2: Incremental Backup**
**Best for:** Large installations > 50GB
**Frequency:** Database daily, files weekly
**Storage:** Saves space using incremental approach

```powershell
# Backup database daily (small)
$date = Get-Date -Format "yyyy-MM-dd"
Copy-Item "D:\PDM_Vault\pdm.sqlite" "D:\PDM_Backups\Database\$date.sqlite"

# Backup files weekly (large)
$week = Get-Date -Format "yyyy-MM-dd-ww"
if ((Get-Date).DayOfWeek -eq "Sunday") {
    Copy-Item "D:\PDM_Vault\CADData" "D:\PDM_Backups\Files\$week\" -Recurse
}
```

### **Strategy 3: Rotating Backup**
**Best for:** Production systems
**Frequency:** Daily
**Storage:** Keep last 30 days

```powershell
# Keep only last 30 days of backups
function Backup-PDM-Rotating {
    $date = Get-Date -Format "yyyy-MM-dd"
    $backupPath = "D:\PDM_Backups\$date"

    New-Item -ItemType Directory -Path $backupPath -Force | Out-Null
    Copy-Item "D:\PDM_Vault\pdm.sqlite" "$backupPath\pdm.sqlite"

    # Delete backups older than 30 days
    $oldBackups = Get-ChildItem "D:\PDM_Backups\" -Directory | Where-Object {
        $_.LastWriteTime -lt (Get-Date).AddDays(-30)
    }
    $oldBackups | Remove-Item -Recurse -Force

    Write-Host "Backup created: $backupPath"
}

Backup-PDM-Rotating
```

---

## ⏰ Automated Backup Schedule

### **Windows Task Scheduler Setup**

1. **Create backup script:** `D:\PDM_Scripts\Backup-Daily.ps1`
   ```powershell
   # Daily backup at 2 AM
   $date = Get-Date -Format "yyyy-MM-dd"
   $backupPath = "D:\PDM_Backups\$date"
   New-Item -ItemType Directory -Path $backupPath -Force
   Copy-Item "D:\PDM_Vault\pdm.sqlite" "$backupPath\pdm.sqlite"
   Copy-Item "D:\PDM_Vault\CADData" "$backupPath\CADData" -Recurse
   ```

2. **Create scheduled task:**
   ```powershell
   # Run as Administrator
   $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File D:\PDM_Scripts\Backup-Daily.ps1"
   $trigger = New-ScheduledTaskTrigger -Daily -At 2am
   $settings = New-ScheduledTaskSettingsSet -RunOnlyIfNetworkAvailable
   $principal = New-ScheduledTaskPrincipal -UserID "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

   Register-ScheduledTask -TaskName "PDM-Daily-Backup" -Action $action -Trigger $trigger -Settings $settings -Principal $principal
   ```

3. **Verify task created:**
   ```powershell
   Get-ScheduledTask | Where-Object {$_.TaskName -eq "PDM-Daily-Backup"}
   ```

---

## 🔍 Backup Verification

### **Check Backup Integrity**

**Before restoring, verify backup is valid:**
```powershell
# Test database backup
sqlite3.exe "D:\PDM_Backups\2025-01-03\pdm.sqlite" "SELECT COUNT(*) FROM items;"
# Should show item count without errors

# Verify file exists and has size
Get-Item "D:\PDM_Backups\2025-01-03\pdm.sqlite" | Select-Object Length, LastWriteTime

# Verify CAD data folder exists
Test-Path "D:\PDM_Backups\2025-01-03\CADData\"
```

### **Monthly Verification**
```powershell
# Every month, test restore to temporary location
$testPath = "D:\PDM_Backups\test_restore"
Copy-Item "D:\PDM_Backups\2025-01-03\pdm.sqlite" "$testPath\pdm_test.sqlite"

# Try to query
sqlite3.exe "$testPath\pdm_test.sqlite" "SELECT COUNT(*) FROM items;"

# If successful, delete test
Remove-Item $testPath -Recurse
```

---

## 🆘 Recovery Procedures

### **Quick Recovery - Database Only (10 minutes)**

If database is corrupted but files are intact:

```powershell
# 1. Stop all services
Stop-Service -Name "PDM_CheckInWatcher", "PDM_WorkerProcessor", "PDM_BOMWatcher" -ErrorAction SilentlyContinue

# 2. Restore from latest backup
$latestBackup = Get-ChildItem "D:\PDM_Backups\" -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Copy-Item "$($latestBackup.FullName)\pdm.sqlite" "D:\PDM_Vault\pdm.sqlite" -Force

# 3. Verify restored database
sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT COUNT(*) FROM items;"

# 4. Restart services
Start-Service -Name "PDM_CheckInWatcher"
Start-Service -Name "PDM_WorkerProcessor"
Start-Service -Name "PDM_BOMWatcher"

Write-Host "Recovery complete. Restored from: $($latestBackup.Name)"
```

### **Full Recovery - Database + Files (30 minutes)**

If entire PDM_Vault needs restoration:

```powershell
# 1. Stop all services
Stop-Service -Name "PDM_CheckInWatcher", "PDM_WorkerProcessor", "PDM_BOMWatcher" -ErrorAction SilentlyContinue

# 2. Find latest complete backup
$latestBackup = Get-ChildItem "D:\PDM_Backups\" -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1

# 3. Backup current state (just in case)
Copy-Item "D:\PDM_Vault" "D:\PDM_Vault.corrupt_backup" -Recurse

# 4. Remove corrupted vault
Remove-Item "D:\PDM_Vault" -Recurse -Force

# 5. Create fresh vault
New-Item -ItemType Directory -Path "D:\PDM_Vault" -Force

# 6. Restore from backup
Copy-Item "$($latestBackup.FullName)\*" "D:\PDM_Vault\" -Recurse

# 7. Verify
Test-Path "D:\PDM_Vault\pdm.sqlite"
sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT COUNT(*) FROM items;"

# 8. Restart services
Start-Service -Name "PDM_CheckInWatcher"
Start-Service -Name "PDM_WorkerProcessor"
Start-Service -Name "PDM_BOMWatcher"

Write-Host "Full recovery complete from: $($latestBackup.Name)"
```

### **Partial Recovery - Single Item**

If one item is corrupted:

```powershell
# Find item in backup
$itemNumber = "csp0030"
$latestBackup = "D:\PDM_Backups\2025-01-03"

# 1. Restore files from backup
$sourceFiles = Get-ChildItem "$latestBackup\CADData\" -Recurse | Where-Object {$_.Name -match $itemNumber}
$sourceFiles | Copy-Item -Destination "D:\PDM_Vault\CADData\" -Recurse -Force

# 2. Restore database record
# Get backup database
Copy-Item "$latestBackup\pdm.sqlite" "D:\temp_backup.sqlite"

# Export record from backup database
sqlite3.exe "D:\temp_backup.sqlite" "SELECT * FROM items WHERE item_number='$itemNumber';" > "D:\item_export.txt"

# Manually recreate in current database or restore entire backup
```

---

## 💾 Storage Recommendations

### **Backup Locations**

**Local Backup (Fast, At-Risk):**
```powershell
# On same drive as PDM
D:\PDM_Backups\  # Daily use

# Pros: Fast, immediate access
# Cons: Lost if D: fails
```

**Network Backup (Safe, Slower):**
```powershell
# On network drive
\\NAS_SERVER\PDM_Backups\  # Weekly copies

# Pros: Safe from local drive failure
# Cons: Slower, network dependent
```

**Cloud Backup (Safest, Slowest):**
```powershell
# Azure, AWS, etc.
# Upload daily backup

# Pros: Maximum protection
# Cons: Cost, internet speed
```

**Recommended Strategy:**
- Daily backup to `D:\PDM_Backups` (local, fast)
- Weekly copy to `\\NAS_SERVER\PDM_Backups` (network, safe)
- Monthly archive to cloud (maximum protection)

---

## 📊 Backup Storage Estimates

**For 1-year retention:**

| Data | Daily Size | 365 Days |
|------|-----------|----------|
| Database only | 100MB | 36GB |
| Database + Files | 1GB | 365GB |
| Database (weekly) | 100MB | 5GB |
| Files (monthly) | 50GB | 600GB |

**Recommended disk allocation:**
- 1TB for daily backups (7-10 days)
- 5TB for long-term archive (30+ days)
- Test restore procedure monthly

---

## ⚠️ Critical Considerations

### **DO:**
- ✅ Backup daily (at minimum)
- ✅ Test restore monthly
- ✅ Keep backups in multiple locations
- ✅ Document backup procedures
- ✅ Automate backup process
- ✅ Monitor backup success
- ✅ Keep old backups (30+ days)

### **DON'T:**
- ❌ Keep only 1 backup
- ❌ Store backup on same drive as PDM
- ❌ Never test restore procedures
- ❌ Forget to document backup locations
- ❌ Ignore backup errors
- ❌ Delete backups too aggressively
- ❌ Assume backup is working (test it!)

---

## 🔔 Monitoring Backups

### **Daily Check:**
```powershell
# Verify latest backup exists and has reasonable size
$latestBackup = Get-ChildItem "D:\PDM_Backups\" -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$dbSize = (Get-Item "$($latestBackup.FullName)\pdm.sqlite").Length / 1MB

Write-Host "Latest backup: $($latestBackup.Name)"
Write-Host "Database size: $([math]::Round($dbSize, 2)) MB"
Write-Host "Created: $($latestBackup.LastWriteTime)"
```

### **Weekly Test:**
```powershell
# Test backup integrity
$latestBackup = Get-ChildItem "D:\PDM_Backups\" -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$result = sqlite3.exe "$($latestBackup.FullName)\pdm.sqlite" "SELECT COUNT(*) FROM items;"

if ($result) {
    Write-Host "✓ Backup verified: $result items in database"
} else {
    Write-Host "✗ Backup test FAILED!"
}
```

---

**Last Updated:** 2025-01-03
**Version:** 2.0
**Related:** [README.md](README.md), [20-COMMON-WORKFLOWS.md](20-COMMON-WORKFLOWS.md), [23-SYSTEM-CONFIGURATION.md](23-SYSTEM-CONFIGURATION.md)
