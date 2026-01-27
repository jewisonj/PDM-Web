# PDM System - Performance Tuning Guide

**Optimization Strategies for Speed and Efficiency**
**Related Docs:** [README.md](README.md), [23-SYSTEM-CONFIGURATION.md](23-SYSTEM-CONFIGURATION.md), [19-TROUBLESHOOTING-DECISION-TREE.md](19-TROUBLESHOOTING-DECISION-TREE.md)

---

## ⚡ Quick Wins (10 minutes)

### 1. Optimize Database
```powershell
# Rebuilds index and frees space - usually 10-20% faster
sqlite3.exe D:\PDM_Vault\pdm.sqlite "VACUUM;"

# Also try
sqlite3.exe D:\PDM_Vault\pdm.sqlite "PRAGMA optimize;"

# Check size before/after
(Get-Item D:\PDM_Vault\pdm.sqlite).Length / 1MB
```

### 2. Increase Service Poll Intervals
```powershell
# Edit D:\PDM_PowerShell\Worker-Processor.ps1
# Change: $Global:PollInterval = 5
# To:     $Global:PollInterval = 10

# Reduces database load by checking less frequently
# Trade-off: Tasks take longer (up to 10 sec vs 5 sec)
```

### 3. Clear Old Logs
```powershell
# Archive old logs (keep last 30 days)
$oldLogs = Get-ChildItem "D:\PDM_Vault\logs\" -File | Where-Object {
    $_.LastWriteTime -lt (Get-Date).AddDays(-30)
}
$oldLogs | Remove-Item

# Start fresh log
"[$(Get-Date)] PDM Log optimized" | Add-Content "D:\PDM_Vault\logs\pdm.log"
```

---

## 🗄️ Database Optimization

### **Index Strategy**

Create indexes for frequently queried fields:
```powershell
# Add indexes (run once)
$queries = @(
    "CREATE INDEX IF NOT EXISTS idx_item_number ON items(item_number);",
    "CREATE INDEX IF NOT EXISTS idx_files_item ON files(item_number);",
    "CREATE INDEX IF NOT EXISTS idx_bom_parent ON bom(parent_item);",
    "CREATE INDEX IF NOT EXISTS idx_bom_child ON bom(child_item);",
    "CREATE INDEX IF NOT EXISTS idx_queue_status ON work_queue(status);",
    "CREATE INDEX IF NOT EXISTS idx_checkouts_item ON checkouts(item_number);"
)

foreach ($query in $queries) {
    sqlite3.exe D:\PDM_Vault\pdm.sqlite $query
}

Write-Host "Indexes created"
```

### **Regular Maintenance**

```powershell
# Monthly maintenance script
function Optimize-PDMDatabase {
    Write-Host "Optimizing database..."

    # Analyze and optimize
    sqlite3.exe D:\PDM_Vault\pdm.sqlite "ANALYZE; PRAGMA optimize;"

    # Rebuild indexes
    sqlite3.exe D:\PDM_Vault\pdm.sqlite "REINDEX;"

    # Free space
    sqlite3.exe D:\PDM_Vault\pdm.sqlite "VACUUM;"

    Write-Host "Optimization complete"
}

Optimize-PDMDatabase
```

---

## 🚀 Service Performance

### **Tune Service Timing**

**CheckIn-Watcher:**
```powershell
# Edit: D:\PDM_PowerShell\CheckIn-Watcher.ps1
# Current: 800ms delay before processing
# Tuning options:
#   - Decrease to 300ms for faster response (more CPU use)
#   - Increase to 2000ms for batching (less CPU use)
```

**Worker-Processor:**
```powershell
# Edit: D:\PDM_PowerShell\Worker-Processor.ps1
# Current: 5 second poll interval
# Tuning options:
#   - Decrease to 2 seconds (faster task processing, more DB access)
#   - Increase to 15 seconds (slower, less database load)
```

### **Monitor Service Performance**

```powershell
# Check CPU usage
Get-Process | Where-Object {$_.Name -match "powershell|node"} | Select-Object Name, CPU, @{n='Memory(MB)';e={[math]::Round($_.WorkingSet/1MB)}}

# If CPU > 80% consistently:
# - Increase poll intervals
# - Check for stuck processes
# - Reduce concurrent operations
```

---

## 💾 Disk & Storage Optimization

### **File Organization**

```powershell
# Archive released items to separate location
$released = Get-ChildItem "D:\PDM_Vault\CADData\" -Recurse | Where-Object {
    $_.Directory.Name -match "Released"
}

# Move to slower storage if available
$released | Move-Item -Destination "D:\PDM_Archive\Released\" -ErrorAction SilentlyContinue
```

### **Disk Space Management**

```powershell
# Check disk usage
Get-PSDrive D | Select-Object Name, @{n='Used(GB)';e={[math]::Round($_.Used/1GB)}}, @{n='Free(GB)';e={[math]::Round($_.Free/1GB)}}

# If < 50GB free, clean up:
# 1. Archive old items
# 2. Delete old backups
# 3. Compress rarely-used files
```

**Compression Example:**
```powershell
# Compress old CADData folders
$oldFolders = Get-ChildItem "D:\PDM_Vault\CADData\" -Directory | Where-Object {
    $_.LastWriteTime -lt (Get-Date).AddMonths(-6)
}

foreach ($folder in $oldFolders) {
    Compress-Archive -Path $folder.FullName -DestinationPath "$($folder.FullName).zip"
    Remove-Item $folder -Recurse  # After verifying zip is OK
}
```

---

## 🌐 Web Server Performance

### **Enable Caching**

Edit `D:\PDM_WebServer\server.js`:
```javascript
// Add caching headers
res.set('Cache-Control', 'public, max-age=3600');  // Cache for 1 hour
```

### **Database Connection Pooling**

```javascript
// Consider using connection pooling for database
// Current: Single connection per request
// Better: Connection pool (requires library change)
```

### **Browser Optimization**

```javascript
// Minimize API calls
// Current: Each sort/filter refreshes from database
// Better: Cache on client, refresh periodically

// Add pagination for large datasets
// Current: Loads all items
// Better: Load 50 at a time, lazy load
```

---

## 📊 Query Optimization

### **Slow Query Detection**

```powershell
# Find slow queries in code
$scriptPath = "D:\PDM_PowerShell"
Get-ChildItem "$scriptPath\*.ps1" | ForEach-Object {
    $content = Get-Content $_.FullName
    # Look for SELECT * FROM (inefficient)
    if ($content -match "SELECT \* FROM") {
        Write-Host "Inefficient query in: $($_.Name)"
    }
}
```

### **Optimized Query Examples**

**BEFORE (Inefficient):**
```sql
-- Loads unnecessary columns
SELECT * FROM items WHERE item_number = 'csp0030';
```

**AFTER (Efficient):**
```sql
-- Only needed columns
SELECT item_number, lifecycle_state, revision, iteration FROM items WHERE item_number = 'csp0030';
```

---

## 🔄 Batch Processing Optimization

### **Batch File Ingestion**

Instead of processing files one-by-one:
```powershell
# Collect multiple files before processing
# Reduces service overhead
# Trade-off: Slightly slower individual response
```

### **BOM Processing**

```powershell
# Process multiple BOM files together
# Instead of separate service calls, batch them

# Benefits:
# - Fewer database transactions
# - Better caching
# - Reduced service overhead
```

---

## 📈 Monitoring & Metrics

### **Create Performance Baseline**

```powershell
# Benchmark current performance
function Get-PDMMetrics {
    $metrics = @{
        "Database Size" = [math]::Round((Get-Item D:\PDM_Vault\pdm.sqlite).Length / 1MB, 2)
        "Item Count" = sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT COUNT(*) FROM items;"
        "File Count" = sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT COUNT(*) FROM files;"
        "Pending Tasks" = sqlite3.exe D:\PDM_Vault\pdm.sqlite "SELECT COUNT(*) FROM work_queue WHERE status='Pending';"
        "Disk Free (GB)" = [math]::Round((Get-PSDrive D).Free / 1GB, 2)
    }
    $metrics
}

Get-PDMMetrics
```

### **Track Performance Over Time**

```powershell
# Log metrics daily
function Log-PDMMetrics {
    $metrics = Get-PDMMetrics
    $date = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

    $logFile = "D:\PDM_Metrics.csv"

    if (-not (Test-Path $logFile)) {
        "Date,DatabaseSize_MB,ItemCount,FileCount,PendingTasks,DiskFree_GB" | Add-Content $logFile
    }

    "$date,$($metrics.'Database Size'),$($metrics.'Item Count'),$($metrics.'File Count'),$($metrics.'Pending Tasks'),$($metrics.'Disk Free (GB)')" | Add-Content $logFile
}

Log-PDMMetrics
```

---

## 🎯 Tuning Recommendations by Scenario

### **Small Installation (< 10GB)**
- No special tuning needed
- Default settings optimal
- Focus on backups

### **Medium Installation (10-100GB)**
- Optimize database quarterly
- Increase poll intervals slightly
- Monitor disk space

### **Large Installation (> 100GB)**
- Monthly database optimization
- Implement indexes
- Archive old items
- Consider separate backup storage
- Monitor performance continuously

---

## ⚠️ Performance Tuning Checklist

- [ ] Run `VACUUM` and `OPTIMIZE` on database
- [ ] Create performance baseline metrics
- [ ] Archive old/obsolete items
- [ ] Clear old log files
- [ ] Create database indexes
- [ ] Review service poll intervals
- [ ] Check disk space (> 50GB free)
- [ ] Monitor CPU usage (< 80% sustained)
- [ ] Test query performance
- [ ] Backup before major changes

---

**Last Updated:** 2025-01-03
**Version:** 2.0
**Related:** [23-SYSTEM-CONFIGURATION.md](23-SYSTEM-CONFIGURATION.md), [19-TROUBLESHOOTING-DECISION-TREE.md](19-TROUBLESHOOTING-DECISION-TREE.md)
