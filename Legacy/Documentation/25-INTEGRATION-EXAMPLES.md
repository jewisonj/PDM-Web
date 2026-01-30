# PDM System - Integration & Extension Examples

**How to Customize, Extend, and Integrate PDM with Other Systems**
**Related Docs:** [README.md](README.md), [05-POWERSHELL-SCRIPTS-INDEX.md](05-POWERSHELL-SCRIPTS-INDEX.md), [08-PDM-WEBSERVER-README.md](08-PDM-WEBSERVER-README.md)

---

## 🔌 Adding a New PowerShell Service

### **Example: Custom Item Validator Service**

Create `D:\PDM_PowerShell\Item-Validator.ps1`:

```powershell
# Load shared library
. "$PSScriptRoot\PDM-Library.ps1"

# Configuration
$ValidationPath = "D:\PDM_Vault\CADData\Validation\"
$WatcherDelay = 800

Write-Log "Item Validator Service Started"

# FileSystemWatcher setup
$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $ValidationPath
$watcher.Filter = "*.txt"
$watcher.IncludeSubdirectories = $false
$watcher.EnableRaisingEvents = $true

# Event handler
$action = {
    $file = $Event.SourceEventArgs.FullPath
    Start-Sleep -Milliseconds $WatcherDelay

    if (Test-Path $file) {
        $content = Get-Content $file
        Validate-Item -FilePath $file -Content $content
    }
}

Register-ObjectEvent -InputObject $watcher -EventName "Created" -Action $action

# Main loop
while ($true) {
    Start-Sleep -Seconds 10
}

function Validate-Item {
    param(
        [string]$FilePath,
        [string]$Content
    )

    Write-Log "Validating: $FilePath"

    # Your custom validation logic
    if ($Content -match "^[a-z]{3}\d{4,6}") {
        Write-Log "VALID: Item follows naming convention"
        Move-Item $FilePath "$(Split-Path $FilePath)\Valid\"
    } else {
        Write-Log "INVALID: Item number format incorrect"
        Move-Item $FilePath "$(Split-Path $FilePath)\Invalid\"
    }
}
```

### **Install as Windows Service**

```powershell
# Using NSSM
nssm.exe install PDM_ItemValidator "powershell.exe" "-ExecutionPolicy Bypass -File D:\PDM_PowerShell\Item-Validator.ps1"
nssm.exe start PDM_ItemValidator
```

---

## 🌐 Adding Web Server API Endpoints

### **Example: Custom Cost Report Endpoint**

Edit `D:\PDM_WebServer\server.js`:

```javascript
// Add new endpoint
app.get('/api/cost-report', (req, res) => {
    const itemNumber = req.query.item;

    if (!itemNumber) {
        return res.status(400).json({ error: 'Item number required' });
    }

    // Query database
    const query = `
        SELECT
            i.item_number,
            i.price_est,
            COUNT(f.file_id) as file_count,
            SUM(CASE WHEN b.child_item IS NOT NULL THEN 1 ELSE 0 END) as component_count
        FROM items i
        LEFT JOIN files f ON i.item_number = f.item_number
        LEFT JOIN bom b ON i.item_number = b.parent_item
        WHERE i.item_number = ?
        GROUP BY i.item_number
    `;

    db.get(query, [itemNumber.toLowerCase()], (err, row) => {
        if (err) {
            return res.status(500).json({ error: err.message });
        }

        if (!row) {
            return res.status(404).json({ error: 'Item not found' });
        }

        res.json(row);
    });
});

// Usage: http://localhost:3000/api/cost-report?item=csp0030
```

### **Test New Endpoint**

```powershell
# Test API endpoint
$response = Invoke-WebRequest -Uri "http://localhost:3000/api/cost-report?item=csp0030"
$response.Content | ConvertFrom-Json
```

---

## 🔗 Integrating with ERP System

### **Example: Export Items to CSV for ERP**

Create `D:\PDM_PowerShell\Export-To-ERP.ps1`:

```powershell
# Load library
. "$PSScriptRoot\PDM-Library.ps1"

# Configuration
$OutputPath = "D:\PDM_Exports\ERP_Items.csv"
$OutputDir = Split-Path $OutputPath

# Create output directory
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

# Query database for all items
$query = @"
SELECT
    item_number,
    name,
    description,
    revision,
    iteration,
    lifecycle_state,
    price_est,
    material,
    mass,
    thickness
FROM items
ORDER BY item_number
"@

$result = Query-SQL -Query $query

# Export to CSV
$items = @()
foreach ($line in $result) {
    if ($line -and $line.Trim().Length -gt 0) {
        $fields = $line -split '\|'
        $items += @{
            ItemNumber = $fields[0]
            Name = $fields[1]
            Description = $fields[2]
            Revision = $fields[3]
            Iteration = $fields[4]
            LifecycleState = $fields[5]
            EstimatedPrice = $fields[6]
            Material = $fields[7]
            Mass = $fields[8]
            Thickness = $fields[9]
        }
    }
}

$items | Export-Csv -Path $OutputPath -NoTypeInformation

Write-Log "Exported $($items.Count) items to ERP: $OutputPath"
Write-Host "File saved to: $OutputPath"
```

### **Run Export**

```powershell
cd D:\PDM_PowerShell
.\Export-To-ERP.ps1
```

---

## 📊 MRP System Integration

### **Example: Sync BOM to MRP Database**

```powershell
# Load libraries
. "D:\PDM_PowerShell\PDM-Library.ps1"
# . "D:\MRP_System\MRP-Library.ps1"  # If MRP has its own library

# Get all assemblies from PDM
$query = "SELECT DISTINCT parent_item FROM bom;"
$assemblies = Query-SQL -Query $query

# Sync each assembly to MRP
foreach ($asm in $assemblies) {
    if ($asm -and $asm.Trim().Length -gt 0) {
        $assembly = $asm.Trim()

        # Query PDM BOM
        $bomQuery = "SELECT child_item, quantity FROM bom WHERE parent_item='$assembly';"
        $bomData = Query-SQL -Query $bomQuery

        # Write to MRP database (example)
        # Exec-SQL-MRP "INSERT INTO mrp_bom (parent_id, child_id, qty) VALUES ..."

        Write-Log "Synced BOM for assembly: $assembly"
    }
}
```

---

## 🔄 Automated Workflows

### **Example: Auto-Release Items After Approval**

Create workflow script:

```powershell
# Watch for approval folder
$approvalPath = "D:\PDM_Vault\CADData\Approval\"

# Monitor for approval files
while ($true) {
    $approvalFiles = Get-ChildItem $approvalPath -Filter "*.approved" -ErrorAction SilentlyContinue

    foreach ($file in $approvalFiles) {
        $itemNumber = $file.BaseName -replace "\.approved$", ""

        # Update item lifecycle
        Exec-SQL "UPDATE items SET lifecycle_state='Released' WHERE item_number='$itemNumber';"

        # Log action
        Write-Log "Auto-released item: $itemNumber"

        # Archive approval file
        Move-Item $file "D:\PDM_Vault\CADData\Approval\archive\"
    }

    Start-Sleep -Seconds 30
}
```

---

## 📧 Email Notifications

### **Example: Notify on Failed Tasks**

```powershell
# Add to monitoring script (run hourly)
. "$PSScriptRoot\PDM-Library.ps1"

$failedTasks = Query-SQL "SELECT COUNT(*) as count FROM work_queue WHERE status='Failed';"

if ($failedTasks -gt 0) {
    # Send email
    $EmailParams = @{
        To = "admin@company.com"
        From = "pdm-system@company.com"
        Subject = "PDM System Alert: $failedTasks Failed Tasks"
        Body = "There are $failedTasks failed tasks in the PDM work queue. Please investigate."
        SmtpServer = "mail.company.com"
        Port = 587
    }

    Send-MailMessage @EmailParams

    Write-Log "Notification email sent"
}
```

---

## 🎨 Custom Web UI Components

### **Example: Custom Dashboard Widget**

Add to `D:\PDM_WebServer\public\index.html`:

```html
<!-- Custom Widget -->
<div id="custom-metrics" style="border: 1px solid #ccc; padding: 10px; margin: 10px;">
    <h3>System Health</h3>
    <p>Items: <span id="item-count">-</span></p>
    <p>Pending Tasks: <span id="pending-count">-</span></p>
    <p>Database Size: <span id="db-size">-</span> MB</p>
</div>

<script>
// Load custom metrics
async function loadMetrics() {
    try {
        // Fetch items
        const itemsResp = await fetch('/api/items');
        const items = await itemsResp.json();
        document.getElementById('item-count').textContent = items.length;

        // Fetch pending tasks (would need API endpoint)
        // const tasksResp = await fetch('/api/pending-tasks');
        // const tasks = await tasksResp.json();
        // document.getElementById('pending-count').textContent = tasks.length;

    } catch (error) {
        console.error('Error loading metrics:', error);
    }
}

// Load on page load
document.addEventListener('DOMContentLoaded', loadMetrics);
```

---

## 🔐 Adding Authentication

### **Example: Simple API Key Authentication**

Edit `D:\PDM_WebServer\server.js`:

```javascript
// Middleware for API key validation
const apiKeyAuth = (req, res, next) => {
    const apiKey = req.headers['x-api-key'];
    const validKey = 'your-secret-key-here';  // In production, use environment variable

    if (!apiKey || apiKey !== validKey) {
        return res.status(401).json({ error: 'Unauthorized' });
    }

    next();
};

// Apply to API endpoints
app.get('/api/items', apiKeyAuth, (req, res) => {
    // ... existing code
});

// Usage
// curl -H "x-api-key: your-secret-key-here" http://localhost:3000/api/items
```

---

## 🧪 Testing Custom Extensions

### **Testing Checklist**

- [ ] Service starts without errors
- [ ] Service connects to database
- [ ] Logging works correctly
- [ ] Processing files correctly
- [ ] Error handling works
- [ ] No database locks
- [ ] Service restarts cleanly
- [ ] Logs are readable

**Test Script:**

```powershell
# Run before deploying custom service
Write-Host "Testing custom service..."

# 1. Check service runs
& "powershell.exe" -File "D:\PDM_PowerShell\Custom-Service.ps1" &
$pid = $PID
Start-Sleep 5
if (Get-Process -Id $pid -ErrorAction SilentlyContinue) {
    Write-Host "✓ Service started successfully"
} else {
    Write-Host "✗ Service failed to start"
}

# 2. Check logs
if (Test-Path "D:\PDM_Vault\logs\pdm.log") {
    $logs = Get-Content "D:\PDM_Vault\logs\pdm.log" -Tail 5
    Write-Host "✓ Logs written: $logs"
} else {
    Write-Host "✗ No logs found"
}

# 3. Stop service
Stop-Process -Id $pid
Write-Host "Test complete"
```

---

## 📚 Extension Resources

- **PowerShell Docs:** https://learn.microsoft.com/powershell/
- **SQLite Docs:** https://www.sqlite.org/docs.html
- **Node.js/Express:** https://expressjs.com/
- **FreeCAD API:** https://wiki.freecadweb.org/API

---

**Last Updated:** 2025-01-03
**Version:** 2.0
**Related:** [05-POWERSHELL-SCRIPTS-INDEX.md](05-POWERSHELL-SCRIPTS-INDEX.md), [08-PDM-WEBSERVER-README.md](08-PDM-WEBSERVER-README.md)
