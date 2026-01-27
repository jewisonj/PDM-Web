# Local_PDM_Services.ps1 - Usage Guide

## Overview

This service handles check-in operations for the workspace tool. It copies files from your workspace (J:\) to the PDM CheckIn folder (D:\PDM_Vault\CADData\CheckIn).

**Note:** File timestamps are handled by the browser using `file:///` protocol directly - no service needed!

## Quick Start

### Option 1: Run Directly (Development/Testing)

```powershell
cd C:\PTC_Data\Powershell
.\Local_PDM_Services.ps1
```

Leave the PowerShell window open. Press Ctrl+C to stop.

### Option 2: Install as Windows Service (Production)

```powershell
# Install the service
.\Local_PDM_Services.ps1 -InstallService

# Start the service
.\Local_PDM_Services.ps1 -StartService

# Or use Windows services
Start-Service Local-PDM-Services
```

The service will auto-start with Windows.

## Service Management Commands

### Install Service
```powershell
.\Local_PDM_Services.ps1 -InstallService
```
Creates a Windows service that auto-starts on boot.

### Start Service
```powershell
.\Local_PDM_Services.ps1 -StartService
# Or
Start-Service Local-PDM-Services
```

### Stop Service
```powershell
.\Local_PDM_Services.ps1 -StopService
# Or
Stop-Service Local-PDM-Services
```

### Restart Service
```powershell
.\Local_PDM_Services.ps1 -RestartService
# Or
Restart-Service Local-PDM-Services
```

### Uninstall Service
```powershell
.\Local_PDM_Services.ps1 -UninstallService
```
Stops and removes the Windows service.

## What It Provides

### API Endpoints

**Port:** `localhost:8083`

#### 1. Health Check
```
GET http://localhost:8083/api/health
```

Returns:
```json
{
  "status": "ok",
  "service": "Local-PDM-Services",
  "port": 8083,
  "checkinPath": "D:\\PDM_Vault\\CADData\\CheckIn",
  "timestamp": "2025-12-31 14:30:00"
}
```

#### 2. Check-In Files
```
POST http://localhost:8083/api/checkin
Content-Type: application/json

{
  "files": [
    {
      "filename": "part1.prt",
      "fullPath": "J:\\Project\\part1.prt"
    },
    {
      "filename": "asm1.asm",
      "fullPath": "J:\\Project\\asm1.asm"
    }
  ]
}
```

Returns:
```json
{
  "results": [
    {
      "filename": "part1.prt",
      "success": true,
      "message": "Copied to CheckIn folder"
    }
  ],
  "summary": {
    "total": 1,
    "succeeded": 1,
    "failed": 0
  }
}
```

## Testing

### Test Health Check
```powershell
Invoke-RestMethod -Uri "http://localhost:8083/api/health"
```

Should return service status.

### Test Check-In
```powershell
$testData = @{
    files = @(
        @{
            filename = "test.prt"
            fullPath = "J:\Path\To\test.prt"
        }
    )
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8083/api/checkin" -Method POST -Body $testData -ContentType "application/json"
```

## Workspace Tool Integration

Update workspace.html with this JavaScript function:

```javascript
async function checkInSelected(files) {
    if (!files || files.length === 0) {
        alert('No files selected');
        return;
    }
    
    const confirmMsg = `Copy ${files.length} file(s) to CheckIn folder?\n\n` +
                       files.map(f => f.filename).join('\n') +
                       `\n\nFiles will be copied (not moved) to:\nD:\\PDM_Vault\\CADData\\CheckIn`;
    
    if (!confirm(confirmMsg)) {
        return;
    }
    
    debugLog(`Checking in ${files.length} files...`, 'info');
    
    try {
        const response = await fetch('http://localhost:8083/api/checkin', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ files: files })
        });
        
        if (!response.ok) {
            throw new Error(`Server responded with ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        const summary = data.summary;
        let message = `Check-In Complete:\n\n`;
        message += `✓ ${summary.succeeded} file(s) copied successfully\n`;
        if (summary.failed > 0) {
            message += `✗ ${summary.failed} file(s) failed\n\n`;
            message += `Failed files:\n`;
            data.results.filter(r => !r.success).forEach(r => {
                message += `  - ${r.filename}: ${r.error}\n`;
            });
        } else {
            message += `\nAll files copied to D:\\PDM_Vault\\CADData\\CheckIn`;
        }
        
        alert(message);
        debugLog(`Check-in complete: ${summary.succeeded} succeeded, ${summary.failed} failed`, 'success');
        
        // Clear selection after successful check-in
        if (summary.succeeded > 0) {
            clearSelection();
        }
        
    } catch (error) {
        debugLog(`Check-in error: ${error.message}`, 'error');
        alert(`Check-In Failed:\n\n${error.message}\n\nMake sure Local_PDM_Services is running on localhost:8083`);
    }
}
```

## Requirements

### For Running Directly
- PowerShell 5.1 or later
- Administrator privileges (for first run to bind to port)

### For Installing as Service
- NSSM (Non-Sucking Service Manager)
- Download from: https://nssm.cc/download
- Install to: `C:\PTC_Data\Tools\nssm.exe` (or update path in script)
- Administrator privileges

## Configuration

Edit these variables at the top of the script if needed:

```powershell
$Global:Port = 8083                              # Change port if needed
$Global:CheckInPath = "D:\PDM_Vault\CADData\CheckIn"  # CheckIn folder
$Global:NSSMPath = "C:\PTC_Data\Tools\nssm.exe"       # NSSM location
```

## Logging

When running directly, all logs appear in the PowerShell console.

When running as a service, use Windows Event Viewer or check NSSM logs:
```powershell
# View service logs with NSSM
nssm.exe dump Local-PDM-Services
```

## Troubleshooting

### Port Already in Use
```
Failed to start listener: Access is denied
```

**Solution:** Another service is using port 8083. Either:
1. Stop the other service
2. Change `$Global:Port` in the script

Check what's using the port:
```powershell
netstat -ano | findstr ":8083"
```

### Service Won't Start
```
Service failed to start
```

**Solution:** Check Windows Event Viewer for errors, or run manually to see error messages:
```powershell
.\Local_PDM_Services.ps1
```

### CheckIn Folder Not Created
```
Access denied creating CheckIn folder
```

**Solution:** Ensure the script has permission to create folders in `D:\PDM_Vault\CADData\`

### Files Not Copying
Check the PowerShell console or service logs for:
- "File not found" - Source file doesn't exist
- "Access denied" - Permission issues
- Path errors - Check file paths are correct

## What Happens After Check-In

1. Files are copied to `D:\PDM_Vault\CADData\CheckIn\`
2. CheckIn-Watcher service (running on DATASERVER or locally) detects them
3. Files are processed and moved to appropriate folders
4. Database is updated
5. Original files in workspace remain untouched

## Startup Options

### Manual Startup (Development)
Run the script when you need it, close when done.

### Auto-Start (Production)
Install as Windows service - always running, starts on boot.

### Hybrid
Install as service but set to manual start:
```powershell
sc config Local-PDM-Services start= demand
```

Then start manually when needed:
```powershell
Start-Service Local-PDM-Services
```

## Uninstalling

If you no longer need the service:

```powershell
# Stop and remove service
.\Local_PDM_Services.ps1 -UninstallService

# Delete the script file
Remove-Item C:\PTC_Data\Powershell\Local_PDM_Services.ps1
```
