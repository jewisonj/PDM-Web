# Workspace Comparison Tool - Development Session Notes

## Critical Fixes & Lessons Learned

### 1. Creo Multiple File Opening - Window Management
**THE BIG ONE:** When opening multiple files in Creo, windows were closing after each file opened.

**Root Cause:** `session.CurrentModel = model` closes other windows!

**Solution:**
```javascript
// BAD - Closes other windows
session.CurrentModel = model;
model.Display();
window.Activate();

// GOOD - Keeps all windows open
var window = session.GetModelWindow(model);
if (window == null) {
    window = session.CreateModelWindow(model);
}
// Don't set CurrentModel, don't activate!
```

### 2. Database Issues Fixed

#### Suffix Removal in Item Numbers
**Problem:** STEP files like `stp00200_prt.stp` were creating items with `_prt` suffix.

**Fix:** Updated `Extract-ItemNumber` function in CheckIn-Watcher.ps1:
```powershell
$baseName = $baseName -replace '_prt$', ''
$baseName = $baseName -replace '_asm$', ''
$baseName = $baseName -replace '_drw$', ''
$baseName = $baseName -replace '_flat$', ''
$baseName = $baseName -replace '_drawing$', ''
```

**Also needed:** Restart services after updating code! Services run old code until restarted.

#### 4-Digit vs 5-Digit Item Numbers
**Problem:** Old code matched 4 digits (`stp0100`) instead of full 5-6 digits (`stp01000`).

**Fix:** Changed regex priority in Extract-ItemNumber:
```powershell
# Try longest match first
if ($baseName -match '^([a-z]{3}\d{6})') { return $matches[1] }  # 6 digits
elseif ($baseName -match '^([a-z]{3}\d{5})') { return $matches[1] }  # 5 digits
elseif ($baseName -match '^([a-z]{3}\d{4})') {  # 4 digits - pad to 5
    $prefix = $matches[1].Substring(0, 3)
    $number = $matches[1].Substring(3)
    return "$prefix$($number.PadLeft(5, '0'))"
}
```

### 3. BOM Cost Rollup Tool - Get-BOMCost.ps1

**Created:** Recursive BOM cost calculator that reads `price_est` from items table.

**Features:**
- Recursively traverses BOM tree
- Multiplies quantities at each level
- Handles circular references using parent chain (NOT global visited hashtable)
- Top-down display (assembly first, then children)
- Subtotals show: `Total = Assembly Cost + Children Cost`

**Key Fix:** Changed from global visited hashtable to parent chain for circular detection.
```powershell
# BAD - Flags normal part reuse as circular
[hashtable]$Visited = @{}  # Shared across entire tree

# GOOD - Only detects true circular references
[System.Collections.ArrayList]$ParentChain = @()  # Only current branch
```

**Format:**
```
[ASM] sta01000 x1 @ $3.16
  [PART] stp01000 x7 @ $3.31 = $23.16
  Subtotal: $23.16 = $0.00 (Assembly) + $23.16 (Children)
```

### 4. Files Table vs Items Table

**CRITICAL:** Database has TWO tables with item numbers:
- `items` - One record per part (has `price_est`, `description`)
- `files` - Multiple records per part (CAD, STEP, DXF, SVG, PDF)

**Common mistake:** Fixing `items` table but forgetting `files` table still has bad data.

**Fix scripts created:**
- `Fix-STEP-Item-Numbers.ps1` - Cleans items table
- `Fix-Files-Table-Suffixes.ps1` - Cleans files table

### 5. Workspace Comparison Tool Features

#### Completed Features:
- ✅ Checkboxes for bulk selection
- ✅ Bulk "Open Selected" action (opens files without closing windows!)
- ✅ Status colors: Up To Date (green), Modified Locally (yellow), Out of Date (cyan), New (red)
- ✅ Custom Creo file type icons (PRT/ASM/DRW)
- ✅ File type filters
- ✅ Search functionality
- ✅ Description from database
- ✅ Timestamp comparison with 2-second tolerance
- ✅ Works both in Creo (via CreoJS) and standalone

#### Bulk Actions Infrastructure:
```javascript
// Select all checkbox in header
<input type="checkbox" id="selectAll" onchange="toggleSelectAll()">

// Individual checkboxes
<input type="checkbox" class="file-checkbox" data-filename="part.prt">

// Bulk action toolbar (shows when files selected)
<div id="bulkActionsBar">
    <span id="selectedCount">0 selected</span>
    <button onclick="openSelected()">Open Selected</button>
</div>
```

### 6. Service Management

**All PDM Services:**
- `PDM-CheckInWatcher` - File ingestion
- `BOM-Watcher` - BOM processing
- `PDM-WorkerProcessor` - Task execution
- `PDM-ReleaseWatcher` - Release workflow
- `PDM-ReviseWatcher` - Revision management
- `Part-Parameter-Watcher` - Parameter sync
- `Workspace-Compare` - Web service on port 8082

**Important:** After updating .ps1 files, ALWAYS restart services:
```powershell
Restart-Service PDM-CheckInWatcher
```

### 7. Database Column Names

**WATCH OUT:** Column name is `price_est` NOT `est_price`!

```sql
-- WRONG
SELECT est_price FROM items;

-- RIGHT
SELECT price_est FROM items;
```

## UI Design Direction

**User wants:** Clean, compact, minimalist interface like Windchill/PLM systems:
- Tight spacing (4-6px padding)
- Small font (11px)
- No gradients or fancy colors
- Gray/white professional palette
- Sticky headers when scrolling
- Toolbar with search, actions dropdown, filters inline
- Table fills available space

**In Progress:** Compact redesign was started but had bugs. Original working version exists.

## File Locations

**Server (DATASERVER):**
- Database: `D:\PDM_Vault\pdm.sqlite`
- Scripts: `D:\PDM_PowerShell\`
- Logs: `D:\PDM_PowerShell\Logs\`

**Creo Installation:**
- CreoJS apps: `C:\Program Files\PTC\Creo 10.0.0.0\Common Files\apps\creojs\creojsweb\`
- Place HTML files here to run in Creo browser

**Key Files:**
- `workspace_compare.html` - Working version with all features
- `CompareWorkspace.ps1` - Windows service (port 8082)
- `Get-BOMCost.ps1` - Cost rollup tool
- `CheckIn-Watcher.ps1` - File processing (has Extract-ItemNumber function)

## Common Patterns

### CreoJS File Opening
```javascript
function openFileInCreo(filename) {
    var session = pfcGetCurrentSession();
    var modelType = /* determine from extension */;
    var descr = pfcModelDescriptor.Create(modelType, filename, "");
    var model = session.RetrieveModel(descr);
    
    if (model != null) {
        var window = session.GetModelWindow(model);
        if (window == null) {
            window = session.CreateModelWindow(model);
        }
        return {success: true};
    }
}
```

### CreoJS Workspace Scanning
```javascript
function getWorkspaceFiles() {
    var session = pfcGetCurrentSession();
    var workingDir = session.GetCurrentDirectory();
    var allModels = session.ListModels();
    
    for (var i = 0; i < allModels.getarraysize(); i++) {
        var model = allModels.get(i);
        var filename = model.GetFileName();
        var fullPath = model.GetOrigin();
        // Get timestamp via pfcAsyncConnection.pfcFileSystem_Create()
    }
}
```

### SQLite Queries from PowerShell
```powershell
# Query
$result = & sqlite3.exe $DBPath "SELECT * FROM items WHERE item_number = 'stp00100';"

# Execute
& sqlite3.exe $DBPath "UPDATE items SET price_est = 10.50 WHERE item_number = 'stp00100';"
```

## Debug Patterns

**Always add debug logging when things break:**
```javascript
function debugLog(message, type = 'info') {
    const color = type === 'error' ? '#ff6b6b' : 
                  type === 'success' ? '#51cf66' : '#74c0fc';
    console.log(`[${new Date().toLocaleTimeString()}] ${message}`);
    // Also display in UI debug console
}
```

**Check:**
1. Services running? `Get-Service | Where-Object { $_.Name -like "*PDM*" }`
2. Port open? `Test-NetConnection -ComputerName localhost -Port 8082`
3. Firewall? `New-NetFirewallRule -DisplayName "..." -LocalPort 8082`
4. Browser console? F12 to see JavaScript errors
5. Service logs? `Get-Content "D:\PDM_PowerShell\Logs\*.log" -Tail 50`

## Migration Tools Created

**For clean slate:**
- `Pre-Migration-Backup.ps1` - Creates timestamped backup
- `Clear-PDM-Data.ps1` - Destructive cleanup (requires backup)
- `Validate-File-Names.ps1` - Checks naming conventions
- `Fix-STEP-Item-Numbers.ps1` - Merges suffixed items
- `Fix-Files-Table-Suffixes.ps1` - Cleans files table

## Next Steps / TODO

**Workspace Comparison:**
- [ ] Finish compact UI redesign (debug why it hangs)
- [ ] Add more bulk actions: Check-In, Pull, Download
- [ ] Add filtering by status (show only Modified, etc.)
- [ ] Add "Select All Modified" quick action

**System Improvements:**
- [ ] Auto-populate `price_est` from supplier data
- [ ] BOM cost tracking over time
- [ ] Alert when costs change significantly

**CreoJS Skill:**
- [ ] Document all CreoJS API patterns discovered
- [ ] Window management best practices
- [ ] File handling patterns

## Important Reminders

1. **Restart services after code changes!** Code stays cached until restart.
2. **Don't set CurrentModel** when bulk opening files - it closes other windows.
3. **Check both items AND files tables** when fixing data issues.
4. **Parent chain, not global visited** for circular reference detection in tree traversal.
5. **Port 8082 needs firewall rule** for Workspace-Compare service.
6. **Column is `price_est`** not `est_price` - this trips you up every time!
7. **Suffix stripping** - Always remove `_prt`, `_asm`, `_drw` from filenames before extracting item numbers.
8. **Debug console visibility** - Make sure it's outside hidden divs so you can see what's breaking!

## Code Quality Patterns

**When writing PowerShell services:**
- Use consistent logging with timestamps and color coding
- Handle errors gracefully with try/catch
- Log to files for troubleshooting
- Use `-ErrorAction SilentlyContinue` for non-critical operations

**When writing CreoJS:**
- Always wrap in try/catch
- Return `{success: boolean, error?: string}` pattern
- Use Promises for async operations
- Add debug logging at key points

**When writing database queries:**
- Always use parameterized queries (though SQLite via command line makes this hard)
- Sanitize inputs
- Use transactions for bulk operations
- Check for existence before inserting

## Performance Notes

- SQLite queries are fast enough for this scale
- File operations can be slow over network - consider local caching
- CreoJS operations have overhead - add small delays (100-200ms) between bulk operations
- Don't overwhelm Creo with too many simultaneous file opens

## User Preferences

- Direct, concise communication
- Efficient problem-solving
- Technical expertise appreciated
- Values working code over perfect code
- Prefers to see results quickly then iterate
