# PDM-Web Port Configuration

## ⚠️ CRITICAL RULES

1. **Frontend is ALWAYS on port 5174** - Never change this
2. **Backend is ALWAYS on port 8001** - Never assume 8000
3. **Always use relative URLs in frontend** (`/api/...` not `http://localhost:8001/api/...`)
4. **Always start backend with explicit port:** `--port 8001`

## Development Ports

### Frontend (Vue 3 + Vite)
- **Port:** `5174` ⚠️ FIXED - DO NOT CHANGE
- **URL:** http://localhost:5174
- **Config:** `frontend/vite.config.ts` line 8
- **Start:** `cd frontend && npm run dev`

### Backend (FastAPI + Python)
- **Port:** `8001` ⚠️ FIXED - DO NOT CHANGE
- **URL:** http://localhost:8001
- **Config:** `backend/.env` (API_PORT=8001)
- **Start (CORRECT):** `cd backend && python -m uvicorn app.main:app --reload --port 8001`
- **Start (WRONG):** ❌ `uvicorn app.main:app --reload` (defaults to 8000!)
- **API Docs:** http://localhost:8001/docs

### Vite Dev Proxy
- Frontend automatically proxies `/api/*` requests to backend
- Config: `frontend/vite.config.ts` line 10-14
- Example: `fetch('/api/items')` → `http://127.0.0.1:8001/api/items`

## Why Port 5174?

Port 5174 is used instead of Vite's default 5173 to avoid conflicts with other development projects running simultaneously.

## Testing URLs

**Frontend:**
- Home: http://localhost:5174/
- Items List: http://localhost:5174/items
- Item Detail: http://localhost:5174/items/csp0030

**Backend (Direct):**
- Health Check: http://localhost:8001/health
- API Docs: http://localhost:8001/docs
- Assembly Download: http://localhost:8001/api/files/assembly/csp0030/download

**Backend (via Vite Proxy - Recommended):**
- Health Check: http://localhost:5174/health
- Assembly Download: http://localhost:5174/api/files/assembly/csp0030/download

## Frontend API Calls

Always use relative URLs in frontend code to leverage the Vite proxy:

✅ **Correct:**
```javascript
fetch('/api/items')
fetch('/api/files/assembly/csp0030/download')
```

❌ **Wrong:**
```javascript
fetch('http://localhost:8000/api/items')  // Wrong port!
fetch('http://localhost:8001/api/items')  // Bypasses proxy, CORS issues
```

## Production

In production, both frontend and backend run on the same port via FastAPI serving static files:
- Combined service runs on configurable port (default: 8000)
- No proxy needed - FastAPI serves both frontend and API

## Other Services

### FreeCAD Worker (Docker)
- Runs as a Docker container
- No exposed port (backend calls via docker exec)
- Container name: `pdm-freecad-worker`

### Supabase
- Cloud service (https://lnytnxmmemdzwqburtgf.supabase.co)
- No local port

## Troubleshooting

### Frontend won't start (port in use)
```bash
# Check what's using port 5174
netstat -ano | findstr :5174

# Kill the process if needed
taskkill /PID <pid> /F
```

### Backend won't start (port in use)
```bash
# Check what's using port 8001
netstat -ano | findstr :8001

# Kill the process if needed
taskkill /PID <pid> /F
```

### API calls failing (CORS/404)
- Verify backend is running on port 8001
- Check Vite proxy config in `frontend/vite.config.ts`
- Ensure you're using relative URLs (`/api/...`) not absolute URLs
