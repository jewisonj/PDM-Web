# PDM Web Server - Setup Guide

A production-ready Node.js web server that serves both the PDM Browser and MRP system interfaces, providing a clean web-based interface to explore items, view details, navigate BOMs, and check lifecycle history.

## Features

- **Item Table View**: Browse all items with sorting and filtering
- **Search & Filter**: Search by item number, description, or project. Filter by lifecycle state and project
- **Detail Panel**: Click any item to view:
  - Full item information (description, material, mass, dimensions)
  - All associated files (CAD, STEP, DXF, SVG, PDF)
  - Bill of Materials (child components)
  - Where-Used (parent assemblies)
  - Lifecycle history
  - Checkout status
- **BOM Navigation**: Click on child/parent items to navigate through assemblies
- **Real-time Data**: Direct SQLite database queries for current information

## PDM & MRP System Integration

The PDM Web Server serves as the unified web interface for both the PDM (Product Data Management) system and MRP (Manufacturing Resource Planning) system:

### PDM System (Primary)
- **Database:** `D:\PDM_Vault\pdm.sqlite`
- **Default Port:** `http://localhost:3000`
- **Features:**
  - Item and assembly browsing
  - BOM (Bill of Materials) tree navigation
  - File tracking (STEP, DXF, SVG, PDF)
  - Lifecycle state management
  - Where-used analysis
  - Revision/iteration history

### MRP System Integration
- **Database:** Configured via `PDM_DB_PATH` or environment variables
- **Shared Infrastructure:** Node.js/Express backend can serve multiple databases
- **Scalability:** API endpoints support custom queries for MRP data
- **Access Pattern:** Same web server infrastructure, different data sources

### Multi-Database Configuration
To serve both PDM and MRP systems simultaneously:

1. **Option A: Separate Instances**
   ```powershell
   # Terminal 1: PDM on port 3000
   $env:PDM_DB_PATH = "D:\PDM_Vault\pdm.sqlite"
   node server.js

   # Terminal 2: MRP on port 3001
   $env:PDM_DB_PATH = "D:\MRP_System\mrp.sqlite"
   $env:PORT = 3001
   node server.js
   ```

2. **Option B: Single Instance with Routing**
   Modify `server.js` to detect database path and route requests accordingly

3. **Option C: Database Switching**
   Add API endpoints to switch databases at runtime

### API Flexibility
The Node.js backend is flexible and can query any SQLite database. To extend for MRP:
- Add new API endpoints in `server.js`
- Create corresponding UI components in `public/index.html`
- Configure database connection via environment variables

---

## Installation

### 1. Choose Installation Directory

Create a folder on your D: drive for the web server:
```
D:\PDM_WebServer\
```

### 2. Copy Files

Copy these files to `D:\PDM_WebServer\`:
- `server.js`
- `package.json`

Create a `public` subdirectory:
```
D:\PDM_WebServer\public\
```

Copy this file to `D:\PDM_WebServer\public\`:
- `index.html`

Your final structure should look like:
```
D:\PDM_WebServer\
├── server.js
├── package.json
└── public\
    └── index.html
```

### 3. Install Node.js

If not already installed:
1. Download Node.js from https://nodejs.org/ (LTS version recommended)
2. Run the installer
3. Verify installation:
   ```powershell
   node --version
   npm --version
   ```

### 4. Install Dependencies

Open PowerShell in `D:\PDM_WebServer\` and run:
```powershell
npm install
```

This will install:
- `express` - Web server framework
- `sqlite3` - SQLite database driver

## Configuration

### Database Path

By default, the server looks for the database at:
```
D:\PDM_Vault\pdm.sqlite
```

To use a different path, set the `PDM_DB_PATH` environment variable:
```powershell
$env:PDM_DB_PATH = "C:\Your\Custom\Path\pdm.sqlite"
node server.js
```

Or edit `server.js` line 8:
```javascript
const DB_PATH = process.env.PDM_DB_PATH || 'D:\\PDM_Vault\\pdm.sqlite';
```

## Running the Server

### Manual Start

Open PowerShell in `D:\PDM_WebServer\` and run:
```powershell
node server.js
```

You should see:
```
PDM Browser Server running on http://localhost:3000
Database: D:\PDM_Vault\pdm.sqlite
Press Ctrl+C to stop
```

Open your web browser and navigate to:
```
http://localhost:3000
```

### Run on Startup (Windows Service)

To run the PDM Browser as a Windows service that starts automatically:

#### Option 1: Using NSSM (Non-Sucking Service Manager)

1. Download NSSM from https://nssm.cc/download
2. Extract to a folder (e.g., `C:\Tools\nssm\`)
3. Open PowerShell as Administrator
4. Install the service:
   ```powershell
   C:\Tools\nssm\nssm.exe install PDM-Browser "C:\Program Files\nodejs\node.exe" "D:\PDM_WebServer\server.js"
   C:\Tools\nssm\nssm.exe set PDM-Browser AppDirectory "D:\PDM_WebServer"
   C:\Tools\nssm\nssm.exe set PDM-Browser DisplayName "PDM Browser Web Server"
   C:\Tools\nssm\nssm.exe set PDM-Browser Description "Web interface for PDM System item browsing"
   C:\Tools\nssm\nssm.exe set PDM-Browser Start SERVICE_AUTO_START
   ```

5. Start the service:
   ```powershell
   Start-Service PDM-Browser
   ```

6. Check status:
   ```powershell
   Get-Service PDM-Browser
   ```

#### Option 2: Using node-windows

1. Install node-windows globally:
   ```powershell
   npm install -g node-windows
   ```

2. Create a service install script (`install-service.js`):
   ```javascript
   var Service = require('node-windows').Service;
   
   var svc = new Service({
     name: 'PDM Browser',
     description: 'Web interface for PDM System item browsing',
     script: 'D:\\PDM_WebServer\\server.js'
   });
   
   svc.on('install', function() {
     svc.start();
   });
   
   svc.install();
   ```

3. Run as Administrator:
   ```powershell
   node install-service.js
   ```

### Service Management Commands

Start service:
```powershell
Start-Service PDM-Browser
```

Stop service:
```powershell
Stop-Service PDM-Browser
```

Restart service:
```powershell
Restart-Service PDM-Browser
```

Check status:
```powershell
Get-Service PDM-Browser
```

Remove service (NSSM):
```powershell
C:\Tools\nssm\nssm.exe remove PDM-Browser confirm
```

## Usage

### Main Interface

1. **Search Box**: Type to filter items by number, description, or project
2. **State Filter**: Filter by lifecycle state (Design, Released, Obsolete)
3. **Project Filter**: Filter by specific project
4. **Table Headers**: Click to sort by that column (click again to reverse)
5. **Item Rows**: Click any row to open the detail panel

### Detail Panel

The right-side panel shows complete information about the selected item:

- **Item Information**: All metadata including material, mass, dimensions
- **Files**: All associated files with types (CAD, STEP, DXF, SVG, PDF)
- **Bill of Materials**: Click child items to navigate down the assembly tree
- **Where Used**: Click parent assemblies to navigate up
- **Lifecycle History**: Complete audit trail of state changes
- **Checkout Status**: Warning if item is currently checked out

### Keyboard Shortcuts

- **Escape**: Close detail panel
- **Click outside panel**: Close detail panel

## Troubleshooting

### Server won't start

**Problem**: Error about port already in use
```
Error: listen EADDRINUSE: address already in use :::3000
```

**Solution**: Either:
1. Stop the other process using port 3000
2. Change the port in `server.js` (line 5):
   ```javascript
   const PORT = 3001; // Or any other available port
   ```

### Database errors

**Problem**: Cannot open database
```
Database connection error: SQLITE_CANTOPEN
```

**Solution**: 
1. Verify database path is correct
2. Check file permissions
3. Ensure database file exists at the specified location

### No items showing

**Problem**: Table loads but shows "No items found"

**Solution**:
1. Check if database has items:
   ```powershell
   sqlite3 D:\PDM_Vault\pdm.sqlite "SELECT COUNT(*) FROM items;"
   ```
2. Check browser console (F12) for JavaScript errors
3. Verify server logs for database query errors

### Service won't start automatically

**Problem**: Service installed but doesn't start on boot

**Solution** (NSSM):
```powershell
# Check service configuration
C:\Tools\nssm\nssm.exe edit PDM-Browser

# Set to Automatic startup
C:\Tools\nssm\nssm.exe set PDM-Browser Start SERVICE_AUTO_START

# Check service status
Get-Service PDM-Browser | Select-Object Name, Status, StartType
```

## API Endpoints

The server provides these API endpoints:

- `GET /api/items` - Get all items
- `GET /api/items/:itemNumber` - Get detailed info for specific item
- `GET /api/files/info?path=<filepath>` - Get file information
- `GET /api/health` - Health check endpoint

## Development

### Development Mode with Auto-Reload

Install nodemon (already in devDependencies):
```powershell
npm install
```

Run with auto-reload:
```powershell
npm run dev
```

Server will automatically restart when you modify `server.js`.

### Customization

**Change Port**:
Edit `server.js` line 5:
```javascript
const PORT = 3001;
```

**Modify Styling**:
Edit CSS in `public/index.html` inside the `<style>` tag

**Add Features**:
- Add new API endpoints in `server.js`
- Add new UI elements in `public/index.html`
- Database queries follow standard SQLite syntax

## Security Notes

- This server is designed for local network use only
- No authentication is implemented
- Database is accessed read-only
- Do not expose to the internet without additional security measures

## Performance

- Typical load time: <1 second for 1000+ items
- Detail panel loads instantly (single query)
- No pagination needed for most datasets
- All filtering/sorting happens client-side for snappy UX

## Future Enhancements

Potential additions:
- [ ] Export to Excel/CSV
- [ ] Print-friendly views
- [ ] File preview for PDFs/images
- [ ] Advanced BOM analysis (total rollup, cost calculation)
- [ ] Comparison between revisions
- [ ] Task queue monitoring
- [ ] Recent activity feed

## Support

For issues or questions:
1. Check this documentation
2. Review browser console (F12) for errors
3. Check server console output
4. Verify database connectivity with `sqlite3.exe`

## Credits

Built using:
- Node.js & Express
- SQLite3
- Modern vanilla JavaScript (no frameworks needed!)
