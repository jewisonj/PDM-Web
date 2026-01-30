# PDM-Web - System Configuration Reference

**Centralized Configuration Settings for All System Components**
**Related Docs:** [22-PERFORMANCE-TUNING-GUIDE.md](22-PERFORMANCE-TUNING-GUIDE.md), [26-SECURITY-HARDENING.md](26-SECURITY-HARDENING.md)

---

## Configuration Architecture

PDM-Web uses environment variables for all deployment-specific configuration. Secrets and service URLs are never hardcoded in the source code. Configuration is loaded at startup from `.env` files (development) or environment variables (production).

```
pdm-web/
  backend/
    .env              # Backend secrets and settings (git-ignored)
    .env.example      # Template with placeholder values (committed)
    app/
      config.py       # Pydantic Settings class (loads from .env)
  frontend/
    .env              # Frontend config (git-ignored)
  scripts/
    pdm-upload/
      PDM-Upload-Config.ps1  # Upload bridge configuration
  docker-compose.yml  # FreeCAD worker configuration
```

---

## Backend Configuration

### Environment Variables

The backend loads configuration via Pydantic Settings from `backend/.env`. All variables can also be set as OS environment variables, which take precedence over the `.env` file.

**File:** `backend/.env`

| Variable | Description | Required | Default | Example |
|----------|-------------|----------|---------|---------|
| `SUPABASE_URL` | Supabase project API URL | Yes | `https://lnytnxmmemdzwqburtgf.supabase.co` | `https://<ref>.supabase.co` |
| `SUPABASE_ANON_KEY` | Supabase anonymous/public API key | Yes | (empty) | `eyJhbGci...` (JWT) |
| `SUPABASE_SERVICE_KEY` | Supabase service role key (admin) | Yes | (empty) | `eyJhbGci...` (JWT) |
| `API_HOST` | Host address for the API server | No | `0.0.0.0` | `0.0.0.0`, `127.0.0.1` |
| `API_PORT` | Port for the API server | No | `8080` | `8001` (dev), `8080` (prod) |
| `DEBUG` | Enable debug mode (auto-reload) | No | `false` | `true`, `false` |
| `CORS_ALLOW_ALL` | Allow all CORS origins | No | `false` | `true` (dev only) |

**Example `.env` file (development):**

```ini
# Supabase Configuration
SUPABASE_URL=https://lnytnxmmemdzwqburtgf.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# API Configuration (Development)
API_HOST=0.0.0.0
API_PORT=8001
DEBUG=true
CORS_ALLOW_ALL=true
```

**Example `.env` file (production):**

```ini
# Supabase Configuration
SUPABASE_URL=https://lnytnxmmemdzwqburtgf.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# API Configuration (Production)
API_HOST=0.0.0.0
API_PORT=8080
DEBUG=false
CORS_ALLOW_ALL=false
```

### Settings Class

The backend configuration is managed by Pydantic Settings in `backend/app/config.py`:

```python
class Settings(BaseSettings):
    # Supabase
    supabase_url: str = "https://lnytnxmmemdzwqburtgf.supabase.co"
    supabase_anon_key: str = ""
    supabase_service_key: str = ""

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    debug: bool = False

    # CORS
    cors_origins: list[str] = [
        "http://localhost:5174",
        "http://localhost:3000",
        "http://100.106.248.91:5174",  # Tailnet
    ]
    cors_allow_all: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
```

Settings are cached using `@lru_cache` via the `get_settings()` function. Changes to `.env` require restarting the backend server.

### Finding Your Supabase Keys

1. Log in to https://supabase.com/dashboard
2. Select your PDM-Web project
3. Navigate to **Settings > API**
4. Copy the **Project URL** for `SUPABASE_URL`
5. Copy the **anon public** key for `SUPABASE_ANON_KEY`
6. Copy the **service_role** key for `SUPABASE_SERVICE_KEY`

---

## Frontend Configuration

### Environment Variables

The frontend uses Vite's environment variable system. Variables must be prefixed with `VITE_` to be accessible in client-side code.

**File:** `frontend/.env`

| Variable | Description | Required | Default | Example |
|----------|-------------|----------|---------|---------|
| `VITE_SUPABASE_URL` | Supabase project API URL | Yes | (fallback in code) | `https://<ref>.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | Supabase anonymous/public API key | Yes | (empty) | `eyJhbGci...` (JWT) |
| `VITE_API_URL` | FastAPI backend URL (override) | No | (auto-detected) | `http://localhost:8001/api` |

**Example `.env` file:**

```ini
VITE_SUPABASE_URL=https://lnytnxmmemdzwqburtgf.supabase.co
VITE_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
# VITE_API_URL - leave commented for auto-detection (works for localhost + Tailnet)
# VITE_API_URL=http://localhost:8001/api
```

### API URL Auto-Detection

The frontend automatically determines the backend API URL based on the environment. This is configured in `frontend/src/services/supabase.ts`:

```typescript
function getApiBaseUrl(): string {
  // 1. Explicit override via env var
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL
  }

  // 2. Production: API is served from same origin (single container)
  if (import.meta.env.PROD) {
    return `${window.location.origin}/api`
  }

  // 3. Development: use current hostname with backend port 8001
  const protocol = window.location.protocol
  const hostname = window.location.hostname
  return `${protocol}//${hostname}:8001/api`
}
```

This means:
- **Local development:** `http://localhost:8001/api` (auto-detected)
- **Tailnet access:** `http://100.106.248.91:8001/api` (auto-detected from hostname)
- **Production (single container):** `https://your-domain.com/api` (same origin)
- **Custom backend:** Set `VITE_API_URL` explicitly

### Supabase Client Configuration

The Supabase client is initialized in `frontend/src/services/supabase.ts`:

```typescript
export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    persistSession: true,        // Keep session in localStorage
    autoRefreshToken: true,      // Auto-refresh expired tokens
    detectSessionInUrl: true,    // Handle auth redirects
    flowType: 'implicit',        // OAuth flow type
    storageKey: 'pdm-web-auth'   // localStorage key for session
  }
})
```

### Build-Time vs. Runtime Configuration

Frontend environment variables are embedded at build time by Vite. This means:

- Changing `VITE_SUPABASE_URL` requires rebuilding the frontend (`npm run build`)
- The API URL auto-detection logic runs at runtime, so it adapts to the current hostname
- The anon key is safe to embed in the frontend (it is a public key designed for client use)

---

## CORS Configuration

Cross-Origin Resource Sharing (CORS) is configured in the FastAPI backend middleware.

### Development Configuration

For development, set `CORS_ALLOW_ALL=true` in `backend/.env`. This allows requests from any origin:

```python
# In backend/app/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.cors_allow_all else settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Production Configuration

For production, set `CORS_ALLOW_ALL=false` (the default) and configure `cors_origins` in `backend/app/config.py` to include only your allowed origins:

```python
cors_origins: list[str] = [
    "http://localhost:5174",         # Local dev frontend
    "http://localhost:3000",         # Alternative dev port
    "http://100.106.248.91:5174",   # Tailnet access
]
```

To add additional allowed origins, either:
1. Edit the `cors_origins` list in `config.py` and restart the backend
2. Set `CORS_ALLOW_ALL=true` for internal/Tailnet deployments where all access is trusted

### Single Container Deployment

In production with a single container (FastAPI serves both API and static frontend), CORS is not needed because the API and frontend share the same origin. The backend serves the Vue SPA at `/` and the API at `/api/`.

---

## Docker Configuration

### FreeCAD Worker

The FreeCAD Docker worker is configured in `docker-compose.yml`:

```yaml
services:
  freecad-worker:
    build:
      context: .
      dockerfile: worker/Dockerfile
    container_name: pdm-freecad-worker
    volumes:
      - ./files:/data/files                              # File I/O
      - ./FreeCAD/Tools:/scripts/tools:ro                # Processing scripts
      - ./worker/scripts:/scripts/worker:ro              # Worker helpers
      - ./FreeCAD/Mod/sheetmetal:/root/.FreeCAD/Mod/sheetmetal:ro  # SheetMetal addon
    environment:
      - PYTHONPATH=/usr/local/lib:/root/.FreeCAD/Mod/sheetmetal:/scripts/worker
    working_dir: /data
    command: ["tail", "-f", "/dev/null"]  # Keep container running
```

**Volume mounts:**

| Host Path | Container Path | Purpose | Mode |
|-----------|---------------|---------|------|
| `./files` | `/data/files` | Input/output files | Read/Write |
| `./FreeCAD/Tools` | `/scripts/tools` | FreeCAD processing scripts | Read-only |
| `./worker/scripts` | `/scripts/worker` | Worker helper scripts | Read-only |
| `./FreeCAD/Mod/sheetmetal` | `/root/.FreeCAD/Mod/sheetmetal` | SheetMetal addon | Read-only |

**Docker commands:**

```bash
# Start the FreeCAD worker
docker-compose up -d freecad-worker

# Run a FreeCAD script
docker exec pdm-freecad-worker python3 /scripts/worker/flatten_sheetmetal.py /data/files/part.stp

# View worker logs
docker logs pdm-freecad-worker

# Rebuild after changes to Dockerfile
docker-compose build freecad-worker
docker-compose up -d freecad-worker

# Stop the worker
docker-compose down
```

---

## Upload Bridge Script Configuration

The upload bridge script runs on the CAD workstation and watches a local folder for files to upload to the PDM-Web API.

### Configuration File

**File:** `scripts/pdm-upload/PDM-Upload-Config.ps1`

```powershell
$Config = @{
    # PDM-Web API URL
    ApiUrl       = "http://localhost:8000/api"
    # Production:
    # ApiUrl     = "https://pdm-web.fly.dev/api"

    # Local folder to watch for uploads
    WatchFolder  = "C:\PDM-Upload"

    # Log file location
    LogFile      = "C:\PDM-Upload\pdm-upload.log"

    # Delay (ms) after file detected before processing
    PollInterval = 500

    # Maximum log file size (bytes) before rotation
    MaxLogSize   = 10MB
}
```

| Setting | Description | Default | Notes |
|---------|-------------|---------|-------|
| `ApiUrl` | FastAPI backend API URL | `http://localhost:8000/api` | Change for production or Tailnet access |
| `WatchFolder` | Local folder monitored for new files | `C:\PDM-Upload` | Created automatically if missing |
| `LogFile` | Path to the upload service log | `C:\PDM-Upload\pdm-upload.log` | Auto-rotates at MaxLogSize |
| `PollInterval` | Delay before processing a detected file (ms) | `500` | Increase for slow file writes |
| `MaxLogSize` | Maximum log file size before rotation | `10MB` | Archived with timestamp suffix |

### Supported File Actions

The upload bridge determines how to process each file based on its name and extension:

| File Pattern | Action | Description |
|-------------|--------|-------------|
| `*.step`, `*.stp`, `*.pdf`, `*.dxf`, `*.svg` | Upload | Upload file to PDM-Web API for the extracted item number |
| `BOM.txt` | BOM | Parse single-level BOM and upload to bulk BOM endpoint |
| `MLBOM.txt` | MLBOM | Parse multi-level BOM and upload to bulk BOM endpoint |
| `param.txt` | Parameters | Parse item parameters and update item properties |
| `zzz*` | Skip | Reference items are skipped |
| `~*`, `.*` | Skip | Temporary files are skipped |

### Running the Upload Bridge

```powershell
# Start the upload service
powershell -ExecutionPolicy Bypass -File "scripts\pdm-upload\PDM-Upload-Service.ps1"

# Or run from the script directory
cd scripts\pdm-upload
.\PDM-Upload-Service.ps1
```

The service:
1. Processes any existing files in the watch folder
2. Starts a FileSystemWatcher for new files
3. Waits 3 seconds after file creation before processing (allows CAD software to finish writing)
4. On success, deletes the processed file
5. On failure, moves the file to `C:\PDM-Upload\Failed\`

---

## Supabase Project Settings

These settings are managed in the Supabase Dashboard, not in local configuration files.

### Authentication Settings

Navigate to **Authentication > Configuration** in the Supabase Dashboard:

| Setting | Recommended Value | Notes |
|---------|------------------|-------|
| Site URL | `http://localhost:5174` (dev) or your production URL | Used for auth redirects |
| Redirect URLs | `http://localhost:5174/**`, `http://100.106.248.91:5174/**` | Allowed OAuth redirect targets |
| JWT Expiry | `3600` (1 hour) | How long access tokens are valid |
| Enable Email Auth | `true` | Password-based login |
| Enable Email Confirmations | `false` (small team) | Skip email verification for trusted users |

### Storage Buckets

The following storage buckets should exist in **Storage** in the Supabase Dashboard:

| Bucket Name | Public | Purpose |
|-------------|--------|---------|
| `pdm-cad` | No | CAD native files (.prt, .asm) |
| `pdm-exports` | No | Export files (.step, .stp, .dxf, .svg) |
| `pdm-drawings` | No | Drawing files (.pdf) |
| `pdm-files` | No | Files uploaded via the bridge script |
| `pdm-other` | No | Other file types |

All buckets should be private (not public). Files are accessed via signed URLs.

### Database

The database schema is managed through Supabase migrations. Key tables:

- `users` -- Application users linked to Supabase Auth
- `items` -- PDM items with metadata
- `files` -- File records with storage paths
- `bom` -- Bill of materials relationships
- `projects` -- Project groupings
- `work_queue` -- Background task queue
- `lifecycle_history` -- Item state change audit trail
- `checkouts` -- Item checkout tracking

---

## Development vs. Production Settings

### Development

| Component | Setting | Value |
|-----------|---------|-------|
| Backend | `API_PORT` | `8001` |
| Backend | `DEBUG` | `true` |
| Backend | `CORS_ALLOW_ALL` | `true` |
| Frontend | `VITE_API_URL` | (auto-detected, uses port `8001`) |
| Frontend | Vite dev server | Port `5174`, HMR enabled |
| Upload Bridge | `ApiUrl` | `http://localhost:8001/api` |

**Start development:**

```bash
# Terminal 1: Backend
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# Terminal 2: Frontend
cd frontend
npm run dev

# Terminal 3: Upload bridge (optional, on CAD workstation)
powershell -File scripts\pdm-upload\PDM-Upload-Service.ps1

# Terminal 4: FreeCAD worker (optional)
docker-compose up -d freecad-worker
```

### Production

| Component | Setting | Value |
|-----------|---------|-------|
| Backend | `API_PORT` | `8080` |
| Backend | `DEBUG` | `false` |
| Backend | `CORS_ALLOW_ALL` | `false` |
| Frontend | Built static files | Served by FastAPI at `/` |
| Upload Bridge | `ApiUrl` | Production URL (e.g., `https://pdm-web.fly.dev/api`) |

**Build for production:**

```bash
# Build frontend
cd frontend && npm run build

# Copy built files to backend static directory
cp -r frontend/dist/* backend/static/

# Run with gunicorn
cd backend
gunicorn app.main:app --worker-class uvicorn.workers.UvicornWorker --workers 4 --bind 0.0.0.0:8080
```

In production mode, FastAPI serves both the API (`/api/*`) and the Vue SPA (`/`) from a single process.

---

## Configuration Checklist

### New Deployment

- [ ] Create a Supabase project (or use existing)
- [ ] Copy API keys from Supabase Dashboard to `.env` files
- [ ] Create `backend/.env` with `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`
- [ ] Create `frontend/.env` with `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`
- [ ] Create required storage buckets in Supabase Dashboard
- [ ] Configure auth redirect URLs in Supabase Dashboard
- [ ] Install backend dependencies: `pip install -r requirements.txt`
- [ ] Install frontend dependencies: `npm install`
- [ ] Verify backend starts: `uvicorn app.main:app`
- [ ] Verify frontend starts: `npm run dev`
- [ ] Verify API health check: `GET /health`

### Adding Upload Bridge to CAD Workstation

- [ ] Copy `scripts/pdm-upload/` to the CAD workstation
- [ ] Edit `PDM-Upload-Config.ps1` to set the correct `ApiUrl`
- [ ] Create the watch folder (`C:\PDM-Upload`)
- [ ] Test with a sample file drop
- [ ] Configure to run at startup via Task Scheduler (optional)

### Common Configuration Issues

**Backend fails to start with empty key errors:**
Ensure `SUPABASE_ANON_KEY` and `SUPABASE_SERVICE_KEY` are set in `backend/.env`. Copy from Supabase Dashboard > Settings > API.

**Frontend cannot reach backend:**
Check that the backend port matches what the frontend expects (8001 in development). If using a custom backend URL, set `VITE_API_URL` in `frontend/.env`.

**CORS errors in browser console:**
In development, set `CORS_ALLOW_ALL=true` in `backend/.env`. In production, ensure `cors_origins` in `config.py` includes your frontend's origin.

**Upload bridge "item not found" errors:**
The item must exist in the database before files can be uploaded for it. BOM uploads auto-create items, but file uploads require the item to already exist.

---

**Last Updated:** 2025-01-29
**Version:** 3.0
**Related:** [22-PERFORMANCE-TUNING-GUIDE.md](22-PERFORMANCE-TUNING-GUIDE.md), [26-SECURITY-HARDENING.md](26-SECURITY-HARDENING.md)
