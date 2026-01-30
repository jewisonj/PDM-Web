# PDM-Web Deployment Guide

Instructions for building, configuring, and deploying the PDM-Web application in development and production environments.

---

## Architecture Overview

PDM-Web is a two-tier application:

1. **Frontend** -- Vue 3 SPA built with Vite, outputs static files (`dist/`)
2. **Backend** -- FastAPI Python API server

In production, both tiers run in a single Docker container: FastAPI serves the Vue static files at `/` and the API at `/api/*`. In development, they run as separate processes on different ports.

External services (database, auth, file storage) are provided by **Supabase** (cloud-hosted PostgreSQL).

---

## Local Development Setup

### Prerequisites

- Node.js 20+ and npm 9+
- Python 3.11+
- Access to the Supabase project

### 1. Backend Setup

```bash
cd backend

# Create a virtual environment
python -m venv venv

# Activate (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

Create `backend/.env` from the example:

```bash
cp .env.example .env
```

Edit `backend/.env` with your Supabase credentials:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_KEY=your_service_key

API_HOST=0.0.0.0
API_PORT=8001
DEBUG=true
CORS_ALLOW_ALL=true
```

Start the backend:

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

The API will be available at `http://localhost:8001`. Interactive docs are at `http://localhost:8001/docs`.

### 2. Frontend Setup

```bash
cd frontend
npm install
```

Create or verify `frontend/.env`:

```env
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your_anon_key
# VITE_API_URL is auto-detected in dev (uses current hostname:8001)
```

Start the frontend:

```bash
cd frontend
npm run dev
```

The dev server starts at `http://localhost:5174` with hot module replacement.

### 3. Verify

1. Open `http://localhost:5174` in your browser
2. Log in with a valid user (e.g., `jack@pdm.local`)
3. The frontend should connect to the backend at `http://localhost:8001/api`
4. Verify items load in the PDM Browser

---

## Environment Variables

### Frontend (Vite)

All frontend environment variables must be prefixed with `VITE_` to be exposed to the browser.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VITE_SUPABASE_URL` | Yes | Hardcoded fallback | Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Yes | Empty string | Supabase anonymous/public key |
| `VITE_API_URL` | No | Auto-detected | Override the FastAPI backend URL |

Frontend variables are baked into the build at compile time. Changing them requires a rebuild.

**Auto-detection logic for `VITE_API_URL`** (when not set):
- Production build: `{window.location.origin}/api` (same-origin, single container)
- Development: `{protocol}//{hostname}:8001/api` (separate backend port, uses current hostname for LAN/Tailnet access)

### Backend (FastAPI)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SUPABASE_URL` | Yes | Hardcoded fallback | Supabase project URL |
| `SUPABASE_ANON_KEY` | Yes | Empty string | Supabase anonymous key |
| `SUPABASE_SERVICE_KEY` | Yes | Empty string | Supabase service role key (server-side only) |
| `API_HOST` | No | `0.0.0.0` | Host to bind to |
| `API_PORT` | No | `8080` | Port to listen on |
| `DEBUG` | No | `false` | Enable debug mode and auto-reload |
| `CORS_ALLOW_ALL` | No | `false` | Allow all CORS origins (set `true` for dev) |

Backend variables are read at runtime from environment or `backend/.env` file via Pydantic Settings.

---

## Building for Production

### Frontend Build

```bash
cd frontend
npm run build
```

This runs `vue-tsc -b` (TypeScript checking) followed by `vite build`. Output is written to `frontend/dist/` and includes:
- `index.html` -- SPA entry point
- `assets/` -- hashed JS and CSS bundles

To skip TypeScript checking during build (e.g., in Docker), run:

```bash
npx vite build
```

### Backend

The FastAPI backend does not require a build step. It runs directly from source:

```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

For production, use multiple workers:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 2
```

Alternatively, use Gunicorn with Uvicorn workers:

```bash
gunicorn app.main:app -w 2 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8080
```

---

## Docker Deployment (Single Container)

The production Dockerfile creates a single container that serves both the frontend and backend.

### Dockerfile Overview

The `Dockerfile` at the project root uses a multi-stage build:

**Stage 1: Frontend Builder** (Node 20 Alpine)
1. Copies `frontend/package*.json` and runs `npm ci`
2. Copies frontend source
3. Builds the Vue app with `npx vite build` (TypeScript checking is skipped)
4. Supabase keys are passed as build arguments (`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`)

**Stage 2: Production Runtime** (Python 3.11 Slim)
1. Installs Python dependencies from `requirements.txt`
2. Copies `backend/app/` to `/app/app/`
3. Copies `frontend/dist/` to `/app/static/` (from Stage 1)
4. Creates a non-root user for security
5. Exposes port 8080
6. Runs Uvicorn on port 8080

The FastAPI application (`main.py`) detects the `static/` directory at startup and:
- Mounts `/assets` for static JS/CSS bundles
- Serves `index.html` at `/`
- Handles SPA catch-all routing (all non-API paths return `index.html`)
- API endpoints remain at `/api/*`

### Build the Image

```bash
docker build \
  --build-arg VITE_SUPABASE_URL=https://your-project.supabase.co \
  --build-arg VITE_SUPABASE_ANON_KEY=your_anon_key \
  -t pdm-web .
```

### Run the Container

```bash
docker run -d \
  -p 8080:8080 \
  -e SUPABASE_URL=https://your-project.supabase.co \
  -e SUPABASE_ANON_KEY=your_anon_key \
  -e SUPABASE_SERVICE_KEY=your_service_key \
  --name pdm-web \
  pdm-web
```

Access the application at `http://localhost:8080`.

### Health Check

The container includes a health check:

```
GET http://localhost:8080/health
```

Returns `{"status": "healthy"}` when the application is running.

---

## Fly.io Deployment

The project includes a `fly.toml` configuration and a `deploy.ps1` script for deploying to Fly.io.

### Fly.io Configuration (`fly.toml`)

| Setting | Value |
|---------|-------|
| App name | `pdm-web` |
| Region | `sea` (Seattle) |
| Internal port | 8080 |
| Force HTTPS | Yes |
| Auto-stop machines | Yes (scales to zero) |
| Auto-start machines | Yes |
| VM | Shared CPU, 512 MB RAM |

### Initial Setup

```bash
# Install Fly CLI
# https://fly.io/docs/hands-on/install-flyctl/

# Create the app
fly apps create pdm-web

# Set runtime secrets (for the backend)
fly secrets set SUPABASE_URL=https://your-project.supabase.co
fly secrets set SUPABASE_ANON_KEY=your_anon_key
fly secrets set SUPABASE_SERVICE_KEY=your_service_key
```

### Deploy

Use the included PowerShell deploy script:

```powershell
.\deploy.ps1
```

The script:
1. Loads environment variables from `backend/.env`
2. Validates that `SUPABASE_URL` and `SUPABASE_ANON_KEY` are set
3. Runs `flyctl deploy` with the Supabase keys as build arguments (needed at frontend build time)

Alternatively, deploy manually:

```bash
fly deploy \
  --build-arg VITE_SUPABASE_URL=https://your-project.supabase.co \
  --build-arg VITE_SUPABASE_ANON_KEY=your_anon_key
```

### Monitor

```bash
fly logs          # View application logs
fly status        # Check deployment status
fly open          # Open the app in browser
fly ssh console   # SSH into the running machine
```

---

## Docker Compose (FreeCAD Worker)

The `docker-compose.yml` is used for the FreeCAD worker container only (not the main application). It runs a FreeCAD CLI container for processing CAD files (DXF flat patterns, SVG bend drawings).

```bash
# Start the FreeCAD worker
docker-compose up -d freecad-worker

# Execute a processing script
docker exec pdm-freecad-worker python3 /scripts/worker/flatten_sheetmetal.py /data/files/part.stp
```

The worker mounts:
- `./files` to `/data/files` -- file storage for input/output
- `./FreeCAD/Tools` to `/scripts/tools` -- processing scripts (read-only)
- `./worker/scripts` to `/scripts/worker` -- worker helper scripts (read-only)
- `./FreeCAD/Mod/sheetmetal` to SheetMetal addon path (read-only)

---

## Static Hosting (Frontend Only)

If running the backend separately (not in a single container), the frontend `dist/` folder can be deployed to any static hosting provider:

- **Vercel**: Connect the repository, set build command to `cd frontend && npm run build`, output directory to `frontend/dist`
- **Netlify**: Same approach, add a `_redirects` file for SPA routing: `/* /index.html 200`
- **nginx**: Serve `dist/` with a try_files directive for SPA fallback
- **Any HTTP server**: Serve static files with SPA-aware routing

When deploying the frontend separately, set `VITE_API_URL` to the backend's URL:

```env
VITE_API_URL=https://your-backend-host.example.com/api
```

---

## CORS Configuration

The FastAPI backend is configured with CORS middleware.

**Development** (`CORS_ALLOW_ALL=true`):
- All origins are allowed

**Production** (`CORS_ALLOW_ALL=false`):
- Allowed origins are defined in `backend/app/config.py`:
  - `http://localhost:5174` (Vite dev server)
  - `http://localhost:3000`
  - Tailnet IP addresses as configured

In the single-container deployment, CORS is not an issue because the frontend and API share the same origin.

---

## Production Checklist

- [ ] Set all Supabase secrets (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`)
- [ ] Pass Supabase keys as build arguments for the frontend (`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`)
- [ ] Set `DEBUG=false` in production
- [ ] Set `CORS_ALLOW_ALL=false` in production
- [ ] Verify health check passes: `GET /health`
- [ ] Confirm authentication works (login, session persistence, token refresh)
- [ ] Test file downloads generate valid signed URLs
- [ ] Verify API docs are accessible at `/docs` (or disable in production if desired)

---

## Troubleshooting

### Frontend cannot reach backend

- In development, verify the backend is running on port 8001
- Check browser console for CORS errors; set `CORS_ALLOW_ALL=true` during development
- If using a non-localhost hostname (e.g., Tailnet IP), the frontend auto-detects the hostname; ensure the backend accepts that origin

### Authentication fails

- Verify `SUPABASE_URL` and `SUPABASE_ANON_KEY` match between frontend and backend
- Check that the Supabase project has the user accounts created
- Inspect browser Network tab for 401 responses; the frontend retries once after refreshing the session

### Docker build fails

- Ensure Docker has enough memory allocated (the Node.js build step can be memory-intensive)
- Verify build arguments are passed correctly: `--build-arg VITE_SUPABASE_URL=...`
- If TypeScript errors block the build, the Dockerfile uses `npx vite build` (skips type checking)

### Fly.io deployment issues

- Run `fly logs` to check for startup errors
- Verify secrets are set: `fly secrets list`
- Check machine status: `fly status`
- If the machine does not start, try `fly machine restart`
