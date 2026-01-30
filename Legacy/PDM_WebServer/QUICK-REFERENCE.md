# PDM Browser - Quick Reference Card

## Installation (One-Time Setup)

```powershell
# 1. Create directory
New-Item -ItemType Directory -Path "D:\PDM_WebServer" -Force

# 2. Copy all files to D:\PDM_WebServer\

# 3. Install dependencies
cd D:\PDM_WebServer
npm install

# 4. Test run
node server.js

# 5. Open browser
Start http://localhost:3000
```

## Daily Use

### Start Server (Manual)
```powershell
cd D:\PDM_WebServer
node server.js
```
OR double-click `start.bat`

### Stop Server
Press `Ctrl+C` in the PowerShell window

### Access Browser
```
http://localhost:3000
```

## Service Mode (Always Running)

### Install as Service (One-Time)
```powershell
# Download NSSM from https://nssm.cc/download
# Extract to C:\Tools\nssm\
# Run as Administrator:
cd D:\PDM_WebServer
.\Install-Service.ps1
```

### Start/Stop Service
```powershell
Start-Service PDM-Browser
Stop-Service PDM-Browser
Restart-Service PDM-Browser
Get-Service PDM-Browser
```

## Common Tasks

### Search for Item
1. Type in search box at top
2. Results filter instantly
3. Works on: item number, description, project

### Filter by State
1. Click "State" dropdown
2. Select: Design, Released, or Obsolete
3. Table updates automatically

### View Item Details
1. Click any row in table
2. Detail panel slides in from right
3. Shows: files, BOM, where-used, history

### Navigate BOM
1. Open item detail panel
2. Scroll to "Bill of Materials"
3. Click child item to view its details
4. Click parent in "Where Used" to go back up

### Sort Table
1. Click any column header
2. Click again to reverse sort
3. Triangle shows current sort direction

### Close Detail Panel
- Click X button
- Press Escape key
- Click outside panel

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Escape | Close detail panel |
| Ctrl+C | Stop server (in terminal) |
| F5 | Refresh browser |
| Ctrl+F | Browser search (not PDM search) |

## Troubleshooting

### Server Won't Start
```powershell
# Check if Node.js is installed
node --version

# Check if port 3000 is in use
netstat -ano | findstr :3000

# Try different port (edit server.js)
```

### Can't See Items
```powershell
# Verify database exists
Test-Path D:\PDM_Vault\pdm.sqlite

# Check database has items
sqlite3 D:\PDM_Vault\pdm.sqlite "SELECT COUNT(*) FROM items;"

# Check browser console (F12)
```

### Service Not Starting
```powershell
# Check service status
Get-Service PDM-Browser

# View service logs
Get-Content D:\PDM_WebServer\logs\service-stderr.log -Tail 20

# Try manual start to see errors
node D:\PDM_WebServer\server.js
```

## Configuration Quick Edits

### Change Port
**File:** `server.js` line 5
```javascript
const PORT = 3001; // Change to your preferred port
```

### Change Database Location
**File:** `server.js` line 8
```javascript
const DB_PATH = 'C:\\Your\\Path\\pdm.sqlite';
```

## API Endpoints (For Advanced Use)

```
GET  /api/items                    - All items
GET  /api/items/:itemNumber        - Item details
GET  /api/files/info?path=<path>   - File info
GET  /api/health                   - Server status
```

### Example API Call
```powershell
# Get all items as JSON
Invoke-RestMethod http://localhost:3000/api/items

# Get specific item
Invoke-RestMethod http://localhost:3000/api/items/csp0030
```

## File Locations

```
D:\PDM_WebServer\
├── server.js           # Main server file
├── package.json        # Dependencies
├── start.bat          # Quick launcher
├── Install-Service.ps1 # Service installer
├── public\
│   └── index.html     # Web interface
└── logs\              # Created after service install
    ├── service-stdout.log
    └── service-stderr.log
```

## Network Access

### Allow Other Computers
```powershell
# Run as Administrator
New-NetFirewallRule -DisplayName "PDM Browser" `
                    -Direction Inbound `
                    -LocalPort 3000 `
                    -Protocol TCP `
                    -Action Allow
```

### Find Your IP
```powershell
ipconfig | findstr IPv4
```

### Share URL
```
http://YOUR-COMPUTER-NAME:3000
# or
http://192.168.1.XXX:3000
```

## Maintenance

### Update Node.js Packages
```powershell
cd D:\PDM_WebServer
npm update
```

### View Logs (Service Mode)
```powershell
Get-Content D:\PDM_WebServer\logs\service-stdout.log -Tail 50
Get-Content D:\PDM_WebServer\logs\service-stderr.log -Tail 50
```

### Backup
```powershell
# Backup server files
Copy-Item D:\PDM_WebServer -Destination D:\Backups\PDM_WebServer -Recurse

# Database is separate - backup with PDM system
```

## Best Practices

✓ Run as Windows service for 24/7 access
✓ Bookmark http://localhost:3000
✓ Use search instead of scrolling
✓ Filter by project for large datasets
✓ Navigate BOM by clicking items
✓ Check "Where Used" before making changes

✗ Don't expose to internet without VPN
✗ Don't modify server.js while running
✗ Don't delete node_modules folder
✗ Don't run multiple instances on same port

## Performance Tips

- **Slow loading?** Check database file size
- **Search laggy?** Clear browser cache
- **High memory?** Restart service weekly
- **Timeout errors?** Check database locks

## Support Resources

1. **README.md** - Full documentation
2. **DEPLOYMENT.md** - Setup checklist
3. **OVERVIEW.md** - Visual guide
4. **Browser Console** - F12 for errors
5. **Server Logs** - Terminal output or service logs

## Emergency Recovery

### Reset Everything
```powershell
# Stop service
Stop-Service PDM-Browser

# Reinstall dependencies
cd D:\PDM_WebServer
Remove-Item node_modules -Recurse -Force
npm install

# Restart
Start-Service PDM-Browser
# or
node server.js
```

## Contact Points

**Service Issues:**
- Check: `Get-Service PDM-Browser`
- Logs: `D:\PDM_WebServer\logs\`

**Browser Issues:**
- Press F12 for console
- Check: http://localhost:3000/api/health

**Database Issues:**
- Verify: PDM-Library.ps1 paths
- Test: `sqlite3 D:\PDM_Vault\pdm.sqlite ".tables"`

---

**Quick Start Command:**
```powershell
cd D:\PDM_WebServer && node server.js
```

**Browser URL:**
```
http://localhost:3000
```

**That's it! Keep this card handy.**
