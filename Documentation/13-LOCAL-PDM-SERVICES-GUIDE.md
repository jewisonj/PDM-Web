# Local Development Guide

How to set up and run the PDM-Web system locally for development and testing.

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | FastAPI backend |
| Node.js | 20+ | Vue frontend build and dev server |
| npm | 9+ | Frontend dependency management |
| PowerShell | 5.1+ | Upload bridge scripts (optional) |
| Docker | 24+ | FreeCAD worker container (optional) |
| Git | 2.x | Version control |

You also need a Supabase project with:
- Database tables created (see database schema documentation).
- Auth users configured.
- A `pdm-files` storage bucket created.

---

## Project Structure

```
pdm-web/
  backend/              # FastAPI Python API
    app/
      main.py           # FastAPI app entry point
      config.py         # Settings (from .env)
      routes/           # API route handlers
      models/           # Pydantic schemas
      services/         # Supabase client, business logic
    requirements.txt    # Python dependencies
    .env                # Environment variables (not committed)
    .env.example        # Template for .env
  frontend/             # Vue 3 + Vite SPA
    src/
    package.json
    .env                # Vite environment variables
  scripts/
    pdm-upload/         # Upload bridge PowerShell scripts
  worker/               # FreeCAD Docker container
    Dockerfile
  docker-compose.yml    # Docker services (FreeCAD worker)
  Dockerfile            # Production multi-stage build
  deploy.ps1            # Fly.io deployment
```

---

## Step 1: Clone and Install

```bash
git clone <repository-url> pdm-web
cd pdm-web
```

### Backend Dependencies

```bash
cd backend
pip install -r requirements.txt
```

This installs FastAPI, Uvicorn, supabase-py, Pydantic, and related packages.

### Frontend Dependencies

```bash
cd frontend
npm install
```

This installs Vue 3, Vite, PrimeVue, Pinia, Supabase JS client, and related packages.

---

## Step 2: Environment Variables

### Backend (.env)

Copy the example and fill in your Supabase credentials:

```bash
cd backend
cp .env.example .env
```

Edit `backend/.env`:

```ini
# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key_here
SUPABASE_SERVICE_KEY=your_service_key_here

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=true
```

| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_URL` | Yes | Your Supabase project URL (from Project Settings > API) |
| `SUPABASE_ANON_KEY` | Yes | Supabase anonymous/public key (from Project Settings > API) |
| `SUPABASE_SERVICE_KEY` | Yes | Supabase service role key (from Project Settings > API). Used for admin operations that bypass RLS. |
| `API_HOST` | No | Bind address. Use `0.0.0.0` to allow access from other machines on the network. |
| `API_PORT` | No | Default `8000` for local dev. Production uses `8080`. |
| `DEBUG` | No | Set `true` for auto-reload on code changes. |
| `CORS_ALLOW_ALL` | No | Set `true` to accept requests from any origin during development. |

### Frontend (.env)

Edit `frontend/.env`:

```ini
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your_anon_key_here
# VITE_API_URL=http://localhost:8000/api
```

| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_SUPABASE_URL` | Yes | Same Supabase project URL as backend |
| `VITE_SUPABASE_ANON_KEY` | Yes | Same anon key as backend |
| `VITE_API_URL` | No | API base URL. If omitted, the frontend uses dynamic host detection (same host as the page), which works for both localhost and Tailscale access. |

**Note:** Frontend environment variables must be prefixed with `VITE_` to be exposed to the Vite build process.

---

## Step 3: Start the Backend

Open a terminal and run:

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Or equivalently:

```bash
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

The `--reload` flag enables auto-restart when Python files change.

**Verify it is running:**

```bash
curl http://localhost:8000/health
# Expected: {"status":"healthy"}

curl http://localhost:8000/api/items?limit=5
# Expected: JSON array of items (or empty array)
```

**Interactive API docs** are available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## Step 4: Start the Frontend

Open a second terminal and run:

```bash
cd frontend
npm run dev
```

Vite will print the local URL, typically:

```
  VITE v7.x.x  ready in XXXms

  > Local:   http://localhost:5174/
  > Network: http://192.168.x.x:5174/
```

Open the Local URL in a browser. The frontend communicates with the backend API and directly with Supabase for authentication.

**Note:** The default Vite port may vary. Check the terminal output for the actual port.

---

## Step 5: Upload Bridge (Optional)

The upload bridge is only needed if you want to test the local-to-API file upload workflow (e.g., dropping files from Creo into a watch folder).

### Configuration

Verify the API URL in `scripts/pdm-upload/PDM-Upload-Config.ps1` points to your local backend:

```powershell
$Config = @{
    ApiUrl      = "http://localhost:8000/api"
    WatchFolder = "C:\PDM-Upload"
    # ...
}
```

### Start the Upload Service

Open a PowerShell window:

```powershell
cd scripts\pdm-upload
.\PDM-Upload-Service.ps1
```

The service will:
1. Create `C:\PDM-Upload\` if it does not exist.
2. Process any files already in the folder.
3. Watch for new files.

### Test the Upload Bridge

Drop a test file into `C:\PDM-Upload\`:

```powershell
# Create a test item first (the item must exist for file upload)
Invoke-RestMethod -Uri "http://localhost:8000/api/items" -Method Post `
  -ContentType "application/json" `
  -Body '{"item_number":"tst0001","name":"Test Part"}'

# Copy a test file to the watch folder
Copy-Item "some-file.step" "C:\PDM-Upload\tst0001.step"
```

Check the PowerShell console for upload confirmation, then verify:

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/items/tst0001"
```

---

## Step 6: FreeCAD Worker (Optional)

The FreeCAD Docker container is used for generating DXF flat patterns and SVG bend drawings from STEP files. This is only needed if you are working on the CAD processing pipeline.

### Start the Worker Container

```bash
docker-compose up -d freecad-worker
```

This builds and starts the `pdm-freecad-worker` container with:
- `./files` mounted at `/data/files` for input/output.
- `./FreeCAD/Tools` mounted at `/scripts/tools` (processing scripts).
- `./worker/scripts` mounted at `/scripts/worker` (helper scripts).
- SheetMetal addon mounted for FreeCAD.

### Run a Processing Script

```bash
docker exec pdm-freecad-worker python3 /scripts/worker/flatten_sheetmetal.py /data/files/csp0030.stp
```

### Stop the Worker

```bash
docker-compose down
```

---

## Running Everything Together

For full local development, you need two terminals minimum (backend + frontend). The upload bridge and FreeCAD worker are optional depending on what you are working on.

### Terminal 1: Backend API

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### Terminal 2: Frontend Dev Server

```bash
cd frontend
npm run dev
```

### Terminal 3 (optional): Upload Bridge

```powershell
cd scripts\pdm-upload
.\PDM-Upload-Service.ps1
```

### Terminal 4 (optional): FreeCAD Worker

```bash
docker-compose up freecad-worker
```

---

## Network Access

### Accessing from Other Machines

The backend binds to `0.0.0.0` by default, making it accessible from other machines on the local network. The frontend Vite dev server also exposes itself on the network.

To access the application from another machine:

1. Find your machine's IP address.
2. Access the frontend at `http://<your-ip>:5174/`.
3. The frontend will detect the host dynamically for API calls (when `VITE_API_URL` is not set).

### Tailscale / Tailnet Access

The CORS configuration includes Tailnet IP addresses. If you access the system via Tailscale, the frontend's dynamic host detection will automatically use the correct Tailnet IP for API calls.

---

## Building for Production Locally

### Frontend Build

```bash
cd frontend
npm run build
```

This produces optimized static files in `frontend/dist/`.

### Docker Build

To test the production Docker image locally:

```bash
docker build \
  --build-arg VITE_SUPABASE_URL=https://your-project.supabase.co \
  --build-arg VITE_SUPABASE_ANON_KEY=your_anon_key \
  -t pdm-web .
```

Run it:

```bash
docker run -p 8080:8080 \
  -e SUPABASE_URL=https://your-project.supabase.co \
  -e SUPABASE_ANON_KEY=your_anon_key \
  -e SUPABASE_SERVICE_KEY=your_service_key \
  pdm-web
```

Access at http://localhost:8080. This serves both the API and the frontend from a single container.

### Deploy to Fly.io

```powershell
.\deploy.ps1
```

See `deploy.ps1` for details. Requires the Fly.io CLI (`flyctl`) and valid credentials in `backend/.env`.

---

## Common Development Tasks

### Adding a New API Endpoint

1. Add the route function in the appropriate file under `backend/app/routes/`.
2. If needed, add Pydantic models in `backend/app/models/schemas.py`.
3. The `--reload` flag on uvicorn will pick up changes automatically.
4. Test with curl, the Swagger UI at `/docs`, or from the frontend.

### Adding a Frontend Page

1. Create a new view component under `frontend/src/views/`.
2. Add a route in the Vue Router configuration.
3. Vite hot-reloads changes automatically.

### Resetting Data

Data lives entirely in Supabase. To reset:
- Use the Supabase Dashboard SQL editor to truncate tables.
- Or use the Supabase Table Editor to delete rows.

There is no local database to manage.

---

## Troubleshooting

### Backend fails to start

**"ModuleNotFoundError"** -- Missing Python dependency. Run `pip install -r requirements.txt` from the `backend/` directory.

**"Connection refused" from Supabase** -- Check that `SUPABASE_URL` in `backend/.env` is correct and accessible.

**"Invalid API key"** -- Verify `SUPABASE_ANON_KEY` and `SUPABASE_SERVICE_KEY` in `backend/.env` are correct. The anon key is the public key; the service key is the secret service role key from Supabase Project Settings > API.

### Frontend fails to start

**"Cannot find module"** -- Run `npm install` in the `frontend/` directory.

**Blank page / no data** -- Check the browser developer console for errors. Verify `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` in `frontend/.env` are correct.

### CORS errors in browser

If the browser shows CORS errors when the frontend calls the backend:

1. Verify the backend is running and accessible.
2. Set `CORS_ALLOW_ALL=true` in `backend/.env` for development.
3. Or add your frontend URL to the `cors_origins` list in `backend/app/config.py`.
4. Restart the backend after changing environment variables.

### Upload bridge cannot connect

**"Connection refused"** -- The backend is not running, or the `ApiUrl` in `PDM-Upload-Config.ps1` does not match the backend's actual host and port.

**"404 Item not found"** -- The item must exist in the database before files can be uploaded. Create the item via the web UI, BOM upload, or parameter upload first.

### Docker / FreeCAD worker issues

**"Cannot connect to Docker daemon"** -- Ensure Docker Desktop is running.

**Container build fails** -- Check `worker/Dockerfile` and ensure the base image is accessible.

---

## Environment Summary

| Service | URL | Port | Config File |
|---------|-----|------|-------------|
| Backend API | http://localhost:8000 | 8000 | `backend/.env` |
| Frontend Dev | http://localhost:5174 | 5174 (Vite default) | `frontend/.env` |
| API Docs | http://localhost:8000/docs | 8000 | -- |
| Upload Bridge | (folder watcher) | -- | `scripts/pdm-upload/PDM-Upload-Config.ps1` |
| FreeCAD Worker | (Docker container) | -- | `docker-compose.yml` |
| Supabase | https://your-project.supabase.co | -- | Supabase Dashboard |
| Production | https://pdm-web.fly.dev | 8080 | Fly.io secrets + `deploy.ps1` |

---

**Last Updated:** 2026-01-29
