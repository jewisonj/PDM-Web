# PDM-Web Frontend Quick Reference

Fast lookup for commands, file locations, routes, stores, API endpoints, and environment variables.

---

## Development Commands

| Command | Directory | Description |
|---------|-----------|-------------|
| `npm install` | `frontend/` | Install frontend dependencies |
| `npm run dev` | `frontend/` | Start Vite dev server (port 5174, HMR) |
| `npm run build` | `frontend/` | TypeScript check + production build to `dist/` |
| `npm run preview` | `frontend/` | Serve production build locally |
| `pip install -r requirements.txt` | `backend/` | Install backend dependencies |
| `uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload` | `backend/` | Start FastAPI dev server |
| `docker-compose up -d freecad-worker` | project root | Start FreeCAD worker container |
| `.\deploy.ps1` | project root | Deploy to Fly.io |

---

## File Locations

### Frontend Source

| File | Purpose |
|------|---------|
| `frontend/src/main.ts` | App entry point, plugin registration |
| `frontend/src/App.vue` | Root component, auth initialization |
| `frontend/src/style.css` | Global CSS variables and base styles |
| `frontend/src/router/index.ts` | Route definitions and auth guards |
| `frontend/src/stores/auth.ts` | Auth store (login, logout, session) |
| `frontend/src/stores/items.ts` | Items store (CRUD, BOM, history) |
| `frontend/src/services/supabase.ts` | Supabase client, API helper, base URL |
| `frontend/src/services/storage.ts` | File upload/download, signed URLs |
| `frontend/src/types/index.ts` | TypeScript interfaces |
| `frontend/.env` | Environment variables (Supabase keys) |
| `frontend/vite.config.ts` | Vite build configuration |
| `frontend/package.json` | Dependencies and npm scripts |

### Backend Source

| File | Purpose |
|------|---------|
| `backend/app/main.py` | FastAPI app, middleware, static serving |
| `backend/app/config.py` | Settings via Pydantic (env vars) |
| `backend/app/routes/__init__.py` | Router registration |
| `backend/app/routes/auth.py` | Auth endpoints (`/api/auth/*`) |
| `backend/app/routes/items.py` | Items endpoints (`/api/items/*`) |
| `backend/app/routes/files.py` | Files endpoints (`/api/files/*`) |
| `backend/app/routes/bom.py` | BOM endpoints (`/api/bom/*`) |
| `backend/app/routes/projects.py` | Projects endpoints (`/api/projects/*`) |
| `backend/app/routes/tasks.py` | Tasks endpoints (`/api/tasks/*`) |
| `backend/app/routes/mrp.py` | MRP endpoints (`/api/mrp/*`) |
| `backend/.env` | Backend environment variables |
| `backend/.env.example` | Template for backend env |
| `backend/requirements.txt` | Python dependencies |

### Deployment

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage build (frontend + backend) |
| `fly.toml` | Fly.io deployment configuration |
| `deploy.ps1` | PowerShell deploy script for Fly.io |
| `docker-compose.yml` | FreeCAD worker container |

---

## Routes

| Path | Route Name | View Component | Auth |
|------|-----------|----------------|------|
| `/login` | login | LoginView | No |
| `/` | home | HomeView | Yes |
| `/pdm-browser` | pdm-browser | ItemsView | Yes |
| `/items/:itemNumber` | item-detail | ItemDetailView | Yes |
| `/part-numbers` | part-numbers | PartNumbersView | Yes |
| `/projects` | projects | ProjectsView | Yes |
| `/tasks` | tasks | TasksView | Yes |
| `/mrp/dashboard` | mrp-dashboard | MrpDashboardView | Yes |
| `/mrp/routing` | mrp-routing | MrpRoutingView | Yes |
| `/mrp/shop` | mrp-shop | MrpShopView | Yes |
| `/mrp/parts` | mrp-parts | MrpPartLookupView | Yes |
| `/mrp/tracking` | mrp-tracking | MrpProjectTrackingView | Yes |
| `/mrp/materials` | mrp-materials | MrpRawMaterialsView | Yes |

---

## Pinia Store Actions

### Auth Store (`useAuthStore`)

| Action | Returns | Description |
|--------|---------|-------------|
| `initialize()` | `void` | Init session, fetch user, set up listener |
| `login(email, password)` | `boolean` | Sign in, returns true on success |
| `logout()` | `void` | Sign out, clear user state |

| Computed | Type | Description |
|----------|------|-------------|
| `isAuthenticated` | `boolean` | User is logged in |
| `isEngineer` | `boolean` | Role is engineer or admin |
| `isAdmin` | `boolean` | Role is admin |

### Items Store (`useItemsStore`)

| Action | Returns | Description |
|--------|---------|-------------|
| `fetchItems(params?)` | `void` | Load items with optional filters |
| `fetchItem(itemNumber)` | `void` | Load single item with files |
| `createItem(item)` | `Item` | Insert new item |
| `updateItem(itemNumber, updates)` | `Item` | Update item fields |
| `deleteItem(itemNumber)` | `void` | Remove item |
| `getBOMTree(itemNumber)` | `BOMTreeNode` | Get BOM children tree |
| `getWhereUsed(itemNumber)` | `Array` | Get parent assemblies |
| `getItemHistory(itemNumber)` | `Array` | Get lifecycle history |

---

## API Endpoints (FastAPI Backend)

All endpoints are prefixed with `/api`.

### Auth (`/api/auth`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/auth/me` | Get current user profile |
| GET | `/api/auth/users` | List all users |
| POST | `/api/auth/login` | Login (email + password) |
| POST | `/api/auth/logout` | Logout |

### Items (`/api/items`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/items` | List items (with query filters) |
| GET | `/api/items/{item_number}` | Get item with files |
| POST | `/api/items` | Create new item |
| PATCH | `/api/items/{item_number}` | Update item |
| DELETE | `/api/items/{item_number}` | Delete item |
| GET | `/api/items/{item_number}/history` | Get lifecycle history |

### Files (`/api/files`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/files` | List files |
| GET | `/api/files/{file_id}` | Get file info |
| POST | `/api/files/upload` | Upload file |
| GET | `/api/files/{file_id}/download` | Download file |
| DELETE | `/api/files/{file_id}` | Delete file |

### BOM (`/api/bom`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/bom/{item_number}` | Get BOM entries |
| GET | `/api/bom/{item_number}/tree` | Get BOM tree |
| GET | `/api/bom/{item_number}/where-used` | Get where-used |
| POST | `/api/bom` | Create BOM entry |
| POST | `/api/bom/bulk` | Bulk create BOM entries |
| PATCH | `/api/bom/{bom_id}` | Update BOM entry |
| DELETE | `/api/bom/{bom_id}` | Delete BOM entry |

### Projects (`/api/projects`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/projects` | List projects |
| GET | `/api/projects/{project_id}` | Get project |
| GET | `/api/projects/{project_id}/items` | Get project items |
| POST | `/api/projects` | Create project |
| PATCH | `/api/projects/{project_id}` | Update project |
| DELETE | `/api/projects/{project_id}` | Delete project |

### Tasks (`/api/tasks`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/tasks` | List tasks |
| GET | `/api/tasks/pending` | List pending tasks |
| GET | `/api/tasks/{task_id}` | Get task |
| POST | `/api/tasks` | Create task |
| POST | `/api/tasks/generate-dxf/{item_number}` | Queue DXF generation |
| POST | `/api/tasks/generate-svg/{item_number}` | Queue SVG generation |
| PATCH | `/api/tasks/{task_id}/start` | Mark task started |
| PATCH | `/api/tasks/{task_id}/complete` | Mark task completed |
| DELETE | `/api/tasks/{task_id}` | Delete task |

### MRP (`/api/mrp`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/mrp/projects/{project_id}/print-packet` | Generate print packet |
| GET | `/api/mrp/projects/{project_id}/print-packet` | Get print packet |

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check (returns `{"status": "healthy"}`) |

API documentation is auto-generated at `/docs` (Swagger UI) and `/redoc` (ReDoc).

---

## Environment Variables

### Frontend (`frontend/.env`)

```env
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your_anon_key
# VITE_API_URL=http://localhost:8001/api    # Optional override
```

### Backend (`backend/.env`)

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_KEY=your_service_key
API_HOST=0.0.0.0
API_PORT=8001         # 8001 for dev, 8080 for production
DEBUG=true            # false in production
CORS_ALLOW_ALL=true   # false in production
```

---

## TypeScript Interfaces

| Interface | Key Fields |
|-----------|------------|
| `User` | `id`, `username`, `email`, `role` |
| `Project` | `id`, `name`, `description`, `status` |
| `Item` | `id`, `item_number`, `name`, `revision`, `iteration`, `lifecycle_state`, `material`, `mass`, `thickness`, `cut_length` |
| `FileInfo` | `id`, `item_id`, `file_type`, `file_name`, `file_path`, `file_size` |
| `BOMEntry` | `id`, `parent_item_id`, `child_item_id`, `quantity` |
| `BOMTreeNode` | `item`, `quantity`, `children[]` |
| `Task` | `id`, `task_type`, `status`, `error_message` |
| `LifecycleEntry` | `id`, `item_id`, `old_state`, `new_state`, `changed_at` |

---

## Supabase Storage Buckets

| Bucket | File Types | Extension |
|--------|-----------|-----------|
| `pdm-cad` | Native CAD | `.prt`, `.asm` |
| `pdm-exports` | Exports | `.step`, `.stp`, `.dxf`, `.svg` |
| `pdm-drawings` | Drawings | `.pdf` |
| `pdm-other` | Miscellaneous | all other |

Storage path convention: `{bucket}/{item_number}/{revision}/{iteration}/{filename}`

---

## Lifecycle States

| State | Description |
|-------|-------------|
| Design | Work in progress |
| Review | Under review |
| Released | Approved for production |
| Obsolete | Deprecated |

---

## Item Number Format

- Pattern: 3 uppercase letters + 4-6 digits (e.g., `CSP0030`, `WMA20120`)
- Stored lowercase in database
- Standard prefixes: CSA, CSP, HBL, STA, STP, XXA, XXP, WMA, WMP
- Special prefixes: `mmc` (McMaster), `spn` (supplier), `zzz` (reference)

---

## User Roles

| Role | Access |
|------|--------|
| `admin` | Full CRUD, file management, all tools |
| `engineer` | Engineering access, view and edit |
| `viewer` | Read-only access, view drawings and BOMs |

---

## Ports

| Service | Dev Port | Prod Port |
|---------|----------|-----------|
| Frontend (Vite) | 5174 | N/A (static files) |
| Backend (FastAPI) | 8001 | 8080 |
| Docker container | -- | 8080 |

---

## Common Patterns

### Navigate to item detail

```typescript
router.push(`/items/${itemNumber}`)
```

### Fetch items with filters

```typescript
await itemsStore.fetchItems({
  lifecycle_state: 'Released',
  project_id: 'some-uuid',
  q: 'searchterm',
  limit: 100
})
```

### Make an authenticated API call

```typescript
import { apiCall } from '../services/supabase'
const data = await apiCall<ResponseType>('/endpoint', {
  method: 'POST',
  body: JSON.stringify(payload)
})
```

### Get a signed download URL

```typescript
import { getSignedUrlFromPath } from '../services/storage'
const url = await getSignedUrlFromPath('pdm-exports/csp0030/A/1/csp0030.step')
window.open(url, '_blank')
```

### Check user role in a component

```typescript
const authStore = useAuthStore()
if (authStore.isEngineer) {
  // show edit controls
}
```

### Query Supabase directly

```typescript
const { data, error } = await supabase
  .from('items')
  .select('*, projects(name)')
  .eq('lifecycle_state', 'Released')
  .order('item_number', { ascending: true })
  .limit(100)
```

---

## Related Documentation

| Document | Content |
|----------|---------|
| `08-PDM-WEBSERVER-README.md` | Frontend Application Guide (full detail) |
| `09-PDM-WEBSERVER-DEPLOYMENT.md` | Deployment Guide |
| `10-PDM-WEBSERVER-OVERVIEW.md` | Frontend Architecture Overview |
| `27-WEB-MIGRATION-PLAN.md` | Full migration plan and database schema |
| `03-DATABASE-SCHEMA.md` | Database table reference |
