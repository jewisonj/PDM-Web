# Quick Start Commands

## Start Backend (Port 8001)

```powershell
cd J:\PDM-Web\backend
python -m uvicorn app.main:app --reload --port 8001
```

Expected output:
```
INFO: Uvicorn running on http://127.0.0.1:8001 (Press CTRL+C to quit)
```

## Start Frontend (Port 5174)

```powershell
cd J:\PDM-Web\frontend
npm run dev
```

Expected output:
```
VITE v7.3.1 ready in 500ms
Local: http://localhost:5174/
```

## Verify Everything is Running

```powershell
# Check backend health
curl http://localhost:8001/health

# Check frontend
curl http://localhost:5174

# Check backend API docs
# Open browser: http://localhost:8001/docs
```

## Common Issues

### Backend starts on port 8000 instead of 8001
**Fix:** Always include `--port 8001` flag when starting backend

### Frontend shows "localhost refused to connect"
**Fix:** Make sure backend is running on port 8001

### Port already in use
```powershell
# Find process on port
netstat -ano | findstr :5174
netstat -ano | findstr :8001

# Kill process
taskkill /F /PID <pid>
```
