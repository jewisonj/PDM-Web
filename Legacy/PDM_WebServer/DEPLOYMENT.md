# PDM Browser - Deployment Checklist

## Quick Setup (5 minutes)

### 1. Create Directory Structure
```
D:\PDM_WebServer\
├── server.js
├── package.json
├── start.bat
├── Install-Service.ps1 (optional)
└── public\
    └── index.html
```

### 2. Install Node.js (if needed)
- [ ] Download from https://nodejs.org/
- [ ] Install (LTS version recommended)
- [ ] Verify: `node --version`

### 3. Install Dependencies
```powershell
cd D:\PDM_WebServer
npm install
```

### 4. Test Run
```powershell
# Option A: Double-click start.bat
# Option B: Run manually
node server.js
```

### 5. Verify
- [ ] Open browser to http://localhost:3000
- [ ] Items table loads
- [ ] Click an item to open detail panel
- [ ] Search and filters work

### 6. Optional: Install as Service
```powershell
# Download NSSM from https://nssm.cc/download
# Extract to C:\Tools\nssm\
# Run as Administrator:
.\Install-Service.ps1
```

## Files Included

| File | Purpose | Required |
|------|---------|----------|
| server.js | Node.js web server | Yes |
| package.json | Dependencies definition | Yes |
| public/index.html | Frontend interface | Yes |
| start.bat | Quick launcher | Recommended |
| Install-Service.ps1 | Service installer | Optional |
| README.md | Full documentation | Recommended |

## Configuration

### Default Settings
- **Port**: 3000
- **Database**: D:\PDM_Vault\pdm.sqlite
- **Server Path**: D:\PDM_WebServer

### To Change Port
Edit `server.js` line 5:
```javascript
const PORT = 3001; // Your preferred port
```

### To Change Database Path
Edit `server.js` line 8:
```javascript
const DB_PATH = 'C:\\YourPath\\pdm.sqlite';
```

Or use environment variable:
```powershell
$env:PDM_DB_PATH = "C:\YourPath\pdm.sqlite"
node server.js
```

## Troubleshooting

### Port Already in Use
Change port in `server.js` or kill process using port 3000:
```powershell
netstat -ano | findstr :3000
taskkill /PID <PID> /F
```

### Database Not Found
1. Verify path in `server.js`
2. Check file exists: `Test-Path D:\PDM_Vault\pdm.sqlite`
3. Check permissions

### Service Won't Start
1. Check service status: `Get-Service PDM-Browser`
2. View logs: `D:\PDM_WebServer\logs\service-stderr.log`
3. Try manual start: `node server.js`

## Access Points

After installation, access PDM Browser at:

**Local Machine:**
- http://localhost:3000

**Other Computers on Network:**
- http://YOUR-COMPUTER-NAME:3000
- http://YOUR-IP-ADDRESS:3000

To find your IP:
```powershell
ipconfig | findstr IPv4
```

## Service Management

**Start:**
```powershell
Start-Service PDM-Browser
```

**Stop:**
```powershell
Stop-Service PDM-Browser
```

**Restart:**
```powershell
Restart-Service PDM-Browser
```

**Status:**
```powershell
Get-Service PDM-Browser
```

**Remove:**
```powershell
C:\Tools\nssm\nssm.exe remove PDM-Browser confirm
```

## Security Notes

⚠️ **Important:**
- This server has no authentication
- Only expose on trusted networks
- Database is read-only (no write operations)
- Do not expose to internet without additional security

## Performance Notes

- Loads 1000+ items in <1 second
- Real-time database queries
- Client-side filtering (instant)
- No server reloads needed for data updates

## Support

**Check these first:**
1. Browser console (F12) for errors
2. Server console output
3. README.md for detailed docs
4. Database connectivity: `sqlite3 D:\PDM_Vault\pdm.sqlite "SELECT COUNT(*) FROM items;"`

## Next Steps

After successful installation:

1. [ ] Bookmark http://localhost:3000
2. [ ] Test all features (search, filter, detail panel)
3. [ ] Set up as Windows service (optional)
4. [ ] Configure Windows Firewall (if accessing from other computers)
5. [ ] Share URL with team members

## Windows Firewall (Optional)

To allow access from other computers:

```powershell
# Run as Administrator
New-NetFirewallRule -DisplayName "PDM Browser" -Direction Inbound -LocalPort 3000 -Protocol TCP -Action Allow
```

## Backup

Recommended backups:
- [ ] Database: `D:\PDM_Vault\pdm.sqlite`
- [ ] Server files: `D:\PDM_WebServer\`
- [ ] Configuration in this checklist

## Updates

To update the PDM Browser:
1. Stop the server/service
2. Replace server.js or index.html
3. Restart the server/service

Dependencies usually don't need updating unless adding new features.
