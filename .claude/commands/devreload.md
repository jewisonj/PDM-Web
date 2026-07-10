# Dev Reload Command

Restart the backend and frontend development servers.

## Instructions

1. Kill any running background uvicorn/backend processes
2. Kill any running background frontend/vite processes
3. Start the backend: `cd backend && python -m uvicorn app.main:app --reload --port 8001`
4. Start the frontend: `cd frontend && npm run dev`
5. Both should run in background
6. Report the ports they're running on

Use KillShell to kill existing processes if needed, then start fresh with Bash run_in_background=true.
