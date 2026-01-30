# PDM-Web -- Quick Start Checklist

**Time to Complete:** 10-15 minutes
**Target Audience:** New developers and users setting up a local development environment
**Related Docs:** [14-SKILL-DEFINITION.md](14-SKILL-DEFINITION.md), [20-COMMON-WORKFLOWS.md](20-COMMON-WORKFLOWS.md)

---

## Prerequisites

Before starting, verify you have:

- [ ] **Node.js** LTS (v18+) and npm
- [ ] **Python 3.10+** with pip
- [ ] **Git** for version control
- [ ] **Docker** (optional, only needed for FreeCAD CAD processing)
- [ ] **Supabase account** with project URL and keys (ask the team lead)

**Verify installations:**

```bash
node --version
npm --version
python --version
pip --version
git --version
docker --version    # optional
```

---

## Step 1: Clone the Repository

```bash
git clone <repository-url> pdm-web
cd pdm-web
```

Verify the project structure:

```
pdm-web/
  backend/          # FastAPI Python backend
  frontend/         # Vue 3 + Vite frontend
  worker/           # FreeCAD Docker container
  FreeCAD/          # FreeCAD scripts and addons
  scripts/          # PDM upload bridge scripts
  Documentation/    # This documentation
  docker-compose.yml
```

---

## Step 2: Set Up the Backend

### Install Python dependencies

```bash
cd backend
pip install -r requirements.txt
```

### Create the environment file

Create `backend/.env` with your Supabase credentials:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=eyJ...your-anon-key
SUPABASE_SERVICE_KEY=eyJ...your-service-key
DEBUG=true
CORS_ALLOW_ALL=true
```

You need three values from the Supabase dashboard (Settings > API):

| Variable | Where to Find |
|---|---|
| `SUPABASE_URL` | Project URL (Settings > API) |
| `SUPABASE_ANON_KEY` | `anon` / `public` key (Settings > API) |
| `SUPABASE_SERVICE_KEY` | `service_role` key (Settings > API) -- keep this secret |

### Start the backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

**Verify:** Open `http://localhost:8000/docs` in a browser. You should see the Swagger API documentation page.

- [ ] Backend starts without errors
- [ ] Swagger UI loads at `/docs`
- [ ] Health check returns OK: `http://localhost:8000/health`

---

## Step 3: Set Up the Frontend

Open a new terminal window (keep the backend running).

### Install Node dependencies

```bash
cd frontend
npm install
```

### Start the development server

```bash
npm run dev
```

The Vite dev server starts on `http://localhost:5174` (or the next available port).

**Verify:**

- [ ] Frontend compiles without errors
- [ ] Browser opens to the login page
- [ ] No console errors in the browser developer tools

---

## Step 4: Verify Login

Open the frontend URL in your browser (typically `http://localhost:5174`).

1. You should see the **Login** page
2. Enter your Supabase Auth credentials (email + password)
3. After login, you should be redirected to the **Home** page showing PDM Tools and MRP Tools cards

- [ ] Login page appears
- [ ] Login succeeds with valid credentials
- [ ] Home page loads with tool cards (PDM Browser, Part Numbers, Projects, Work Queue)
- [ ] Username and role display in the header

If you do not have login credentials, ask the team lead to create a user in the Supabase Auth dashboard.

---

## Step 5: Explore the Application

### PDM Browser

1. Click **PDM Browser** on the Home page
2. You should see a table of items (if any exist in the database)
3. Try the search bar to filter items
4. Click an item row to open the detail panel on the right
5. The detail panel shows item info, files, BOM, and where-used sections

- [ ] PDM Browser loads
- [ ] Items display in the table (or "No items found" if the database is empty)
- [ ] Detail panel opens on item click

### Part Number Generator

1. Click **Part Number Generator** on the Home page
2. Shows the next available part number for each prefix
3. Click a number to copy it to the clipboard

### Work Queue

1. Click **Work Queue** on the Home page
2. Shows background tasks (DXF/SVG generation, etc.)
3. Will be empty if no tasks have been created

---

## Step 6: Upload a Test File (Optional)

If items already exist in the database:

1. Navigate to the **PDM Browser**
2. Note an existing item number (e.g., `csp0030`)
3. Use the API directly to upload a test file:

```bash
curl -X POST http://localhost:8000/api/files/upload \
  -F "file=@test_file.pdf" \
  -F "item_number=csp0030"
```

Or use the Swagger UI at `http://localhost:8000/docs` to test the `/api/files/upload` endpoint interactively.

- [ ] File upload succeeds (HTTP 200)
- [ ] File appears in the item's detail panel under "Files"

---

## Step 7: Set Up FreeCAD Worker (Optional)

This step is only needed if you are working on DXF/SVG generation from STEP files.

### Build and start the Docker container

```bash
docker-compose up -d freecad-worker
```

### Verify the container is running

```bash
docker ps | grep pdm-freecad
```

### Test with a sample STEP file

```bash
docker exec pdm-freecad-worker freecadcmd /scripts/flatten_sheetmetal.py \
  /scripts/tools/Test\ Parts/ccp0871.stp /data/files/test_output.dxf
```

- [ ] Docker container starts successfully
- [ ] Test STEP file processes without errors
- [ ] DXF output file is created

---

## Step 8: Set Up PDM Upload Bridge (Optional)

This step is only needed on the workstation running Creo Parametric, to bridge local file exports to the web API.

### Configure the upload service

Edit `scripts/pdm-upload/PDM-Upload-Config.ps1`:

```powershell
$Config = @{
    ApiUrl       = "http://localhost:8000/api"    # or production URL
    WatchFolder  = "C:\PDM-Upload"
    LogFile      = "C:\PDM-Upload\pdm-upload.log"
}
```

### Create the watch folder

```powershell
New-Item -ItemType Directory -Path "C:\PDM-Upload" -Force
```

### Start the upload service

```powershell
cd scripts\pdm-upload
.\Start-PDMUpload.bat
```

The service monitors `C:\PDM-Upload` for new files and automatically uploads them to the API.

- [ ] Watch folder created
- [ ] Service starts and shows "File watcher started"
- [ ] Dropping a STEP file into the watch folder triggers an upload

---

## Development Commands Reference

### Backend

```bash
# Start with auto-reload
cd backend && uvicorn app.main:app --reload --port 8000

# Run on a specific host (for network access)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
# Development server
cd frontend && npm run dev

# Type check and build for production
cd frontend && npm run build

# Preview production build
cd frontend && npm run preview
```

### Docker (FreeCAD Worker)

```bash
# Start worker
docker-compose up -d freecad-worker

# Rebuild after changes
docker-compose build freecad-worker && docker-compose up -d freecad-worker

# View logs
docker logs pdm-freecad-worker

# Interactive shell
docker exec -it pdm-freecad-worker bash
```

---

## Troubleshooting

### Backend will not start

- Check that `.env` file exists in the `backend/` directory
- Verify Supabase URL and keys are correct
- Ensure Python dependencies are installed: `pip install -r requirements.txt`
- Check for port conflicts: `netstat -an | find "8000"`

### Frontend will not connect to backend

- Verify the backend is running on the expected port (default: 8000)
- Check the frontend Vite config for the correct API proxy target
- Ensure `CORS_ALLOW_ALL=true` is set in the backend `.env` for local development
- Look for CORS errors in the browser console

### Login fails

- Verify the user exists in Supabase Auth dashboard
- Check that `SUPABASE_URL` and `SUPABASE_ANON_KEY` are correct in both backend `.env` and frontend configuration
- Look for auth errors in the browser console and backend terminal

### Docker container will not start

- Ensure Docker Desktop is running
- Check for port or volume conflicts: `docker ps -a`
- Rebuild the image: `docker-compose build freecad-worker`
- Check Docker logs: `docker logs pdm-freecad-worker`

### Files not uploading

- Verify the item exists in the database before uploading a file (files must be associated with an item)
- Check the backend terminal for error messages
- Ensure the Supabase Storage bucket `pdm-files` exists and has appropriate policies

---

## Next Steps

Once setup is complete:

1. **Learn daily workflows:** Read [20-COMMON-WORKFLOWS.md](20-COMMON-WORKFLOWS.md)
2. **Understand system capabilities:** Read [14-SKILL-DEFINITION.md](14-SKILL-DEFINITION.md)
3. **FreeCAD automation:** Read [12-FREECAD-AUTOMATION.md](12-FREECAD-AUTOMATION.md)
4. **API reference:** Browse the interactive docs at `http://localhost:8000/docs`
