# PDM-Web Frontend Application Guide

A desktop-first Vue 3 single-page application for browsing items, navigating Bills of Materials, managing files, and tracking manufacturing data in the PDM system.

---

## Technology Stack

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| Framework | Vue 3 | 3.5+ | Reactive UI with Composition API |
| Language | TypeScript | 5.9+ | Type-safe development |
| Build Tool | Vite | 7.x | Fast bundling and HMR dev server |
| Routing | Vue Router | 4.6+ | Client-side SPA routing with auth guards |
| State | Pinia | 3.x | Centralized state management |
| UI Library | PrimeVue | 4.5+ | Component library (Aura theme) |
| Icons | PrimeIcons | 7.x | Icon set used across the UI |
| Auth | Supabase JS | 2.93+ | Authentication and database client |
| Utilities | VueUse | 14.x | Composable utilities (debounce, etc.) |

---

## Project Structure

```
frontend/
├── public/                      # Static assets (served as-is)
├── src/
│   ├── main.ts                  # App entry point, plugin registration
│   ├── App.vue                  # Root component (auth init, router-view)
│   ├── style.css                # Global CSS variables and base styles
│   ├── router/
│   │   └── index.ts             # Route definitions and auth navigation guards
│   ├── stores/
│   │   ├── auth.ts              # Auth state, login/logout, session management
│   │   └── items.ts             # Items CRUD, BOM tree, where-used, history
│   ├── services/
│   │   ├── supabase.ts          # Supabase client init, API helper with auth
│   │   └── storage.ts           # File upload/download, signed URLs, bucket logic
│   ├── types/
│   │   └── index.ts             # TypeScript interfaces (User, Item, File, BOM, Task)
│   ├── views/
│   │   ├── LoginView.vue        # Email/password login form
│   │   ├── HomeView.vue         # Dashboard with PDM and MRP tool cards
│   │   ├── ItemsView.vue        # PDM Browser - searchable item table with detail panel
│   │   ├── ItemDetailView.vue   # Full item detail with tabs (files, BOM, where-used, history)
│   │   ├── PartNumbersView.vue  # Next available part numbers per prefix
│   │   ├── ProjectsView.vue     # Project listing
│   │   ├── TasksView.vue        # Work queue / background task monitor
│   │   ├── MrpDashboardView.vue # MRP production order overview
│   │   ├── MrpRoutingView.vue   # Production routing editor
│   │   ├── MrpShopView.vue      # Shop floor terminal interface
│   │   ├── MrpPartLookupView.vue       # Part lookup with routing ops and PDF viewer
│   │   ├── MrpProjectTrackingView.vue  # Gantt-style project progress tracking
│   │   └── MrpRawMaterialsView.vue     # Raw materials inventory management
│   └── components/
│       ├── FileCheckIn.vue      # File check-in component
│       └── HelloWorld.vue       # Template placeholder
├── .env                         # Environment variables (Supabase keys)
├── package.json                 # Dependencies and scripts
├── vite.config.ts               # Vite configuration (port, plugins)
├── tsconfig.json                # TypeScript configuration
└── index.html                   # HTML entry point
```

---

## Views

### Login (`/login`)

Email and password authentication form using Supabase Auth. On successful login, redirects to the page the user originally requested (via `?redirect=` query param) or to the home dashboard.

### Home Dashboard (`/`)

Landing page after login. Displays two sections of clickable tool cards:

**PDM Tools:**
- PDM Browser -- item browsing and search
- Part Number Generator -- next available numbers per prefix
- Projects -- project management
- Work Queue -- background task monitoring

**MRP Tools:**
- MRP Dashboard -- production order tracking
- Routing Editor -- define production routings
- Shop Terminal -- shop floor operator interface
- Part Lookup -- search parts by project with routing operations
- Project Tracking -- Gantt timeline with part hierarchy
- Raw Materials -- inventory management with inline editing

### PDM Browser (`/pdm-browser`)

The primary item browsing interface, modeled after professional PLM systems (Windchill-style). Features:

- **Controls bar** at the top with search input, lifecycle state filter dropdown, project filter dropdown, item count, and user/logout controls.
- **Sortable table** showing item number, description, project, revision, lifecycle state, material, modified date, and mass. Click any column header to sort.
- **Slide-in detail panel** on the right when an item row is clicked. Shows full item metadata, associated files (with signed URL download links), BOM children, and where-used parent assemblies. Click any BOM or where-used item to navigate directly.
- **Keyboard support**: press Escape to close the detail panel.
- Loads up to 1000 items on mount with client-side filtering for instant responsiveness.

### Item Detail (`/items/:itemNumber`)

Full-page detail view for a single item. Displays:

- Item number, lifecycle state badge, and revision
- Metadata: name, description, material, thickness, mass, cut length
- Tabbed interface:
  - **Files** -- list of associated files with type, size, and date
  - **BOM** -- child components with quantity (click to navigate)
  - **Where Used** -- parent assemblies (click to navigate)
  - **History** -- lifecycle state change log with timestamps

Engineer/admin users see Edit and Upload File action buttons.

### Part Numbers (`/part-numbers`)

Displays a table of all standard prefixes (CSA, CSP, HBL, STA, STP, XXA, XXP, WMA, WMP) with the highest existing number and count. Click to copy the next available number to clipboard for use in CAD.

### Projects (`/projects`)

Lists all projects fetched from the FastAPI backend (`/api/projects`). Shows project name, description, and status with color-coded badges.

### Tasks (`/tasks`)

Work queue monitor. Lists the most recent 50 background tasks (DXF generation, SVG generation, param sync) with status badges (pending, processing, completed, failed) and error messages.

### MRP Views

| View | Route | Purpose |
|------|-------|---------|
| MrpDashboardView | `/mrp/dashboard` | Production orders, work packets, project status |
| MrpRoutingView | `/mrp/routing` | Create/edit routings, workstation assignment |
| MrpShopView | `/mrp/shop` | Shop floor operator terminal, workstation queues |
| MrpPartLookupView | `/mrp/parts` | Part search by project, routing operations, PDF viewer |
| MrpProjectTrackingView | `/mrp/tracking` | Gantt-style progress visualization per project |
| MrpRawMaterialsView | `/mrp/materials` | Inventory tracking, inline editing, batch updates |

---

## State Management (Pinia Stores)

### Auth Store (`stores/auth.ts`)

Manages Supabase authentication state using the Composition API pattern.

**State:**
- `user` -- current user object (or null)
- `loading` -- operation in progress flag
- `error` -- last error message
- `initialized` -- whether auth has been initialized

**Computed:**
- `isAuthenticated` -- true if user is logged in
- `isEngineer` -- true if role is `engineer` or `admin`
- `isAdmin` -- true if role is `admin`

**Actions:**
- `initialize()` -- called once at app mount; gets session, fetches user profile from `/api/auth/me`, sets up `onAuthStateChange` listener for sign-in, sign-out, and token refresh events. Uses a promise guard to prevent duplicate initialization.
- `login(email, password)` -- signs in via `supabase.auth.signInWithPassword`, then fetches the user profile.
- `logout()` -- signs out via `supabase.auth.signOut` and clears user state.

### Items Store (`stores/items.ts`)

Manages items data and CRUD operations.

**State:**
- `items` -- array of all loaded items
- `currentItem` -- currently viewed item (with files)
- `loading`, `error` -- standard loading/error flags
- `searchQuery`, `lifecycleFilter`, `projectFilter` -- filter state

**Actions:**
- `fetchItems(params?)` -- queries Supabase `items` table with optional filters (lifecycle_state, project_id, search text) and joins `projects` for the project name.
- `fetchItem(itemNumber)` -- fetches a single item by item_number with its associated files.
- `createItem(item)` -- inserts a new item.
- `updateItem(itemNumber, updates)` -- patches an existing item.
- `deleteItem(itemNumber)` -- removes an item.
- `getBOMTree(itemNumber)` -- fetches BOM children for an item using foreign key joins.
- `getWhereUsed(itemNumber)` -- fetches parent assemblies where this item is used.
- `getItemHistory(itemNumber)` -- fetches lifecycle history entries.

---

## Services

### Supabase Client (`services/supabase.ts`)

Initializes the Supabase client with:
- URL and anon key from `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` environment variables
- Auth configured with persistent sessions, auto token refresh, implicit flow, and custom storage key `pdm-web-auth`

Also provides:
- `API_BASE_URL` -- dynamically resolved FastAPI backend URL:
  - If `VITE_API_URL` is set, uses that explicitly.
  - In production (`import.meta.env.PROD`), uses `window.location.origin/api` (same-origin, single container).
  - In development, uses `{protocol}//{hostname}:8001/api` (separate backend port).
- `apiCall<T>(endpoint, options, retry)` -- authenticated fetch wrapper that:
  - Gets the current session token from Supabase
  - Adds `Authorization: Bearer {token}` header
  - On 401 response, attempts session refresh and retries once
  - Parses JSON responses and throws on errors

### Storage Service (`services/storage.ts`)

Manages file operations with Supabase Storage. Key functions:
- `getBucketForFile(filename)` -- maps file extensions to buckets (`pdm-cad`, `pdm-exports`, `pdm-drawings`, `pdm-other`)
- `getSignedUrl(bucket, path)` and `getSignedUrlFromPath(fullPath)` -- generates time-limited download URLs
- `uploadFile(file, itemNumber, revision, iteration)` -- uploads to the correct bucket using the path convention `{item_number}/{revision}/{iteration}/{filename}`
- `uploadFileWithRecord(...)` -- uploads and creates the database record in one operation
- `downloadFileToDevice(bucket, path, filename)` -- triggers browser download
- `deleteFile(fileId, storagePath)` -- removes from storage and database

Storage buckets:
| Extension | Bucket | Category |
|-----------|--------|----------|
| `.prt`, `.asm` | `pdm-cad` | Native CAD files |
| `.step`, `.stp`, `.dxf`, `.svg` | `pdm-exports` | Export formats |
| `.pdf` | `pdm-drawings` | Drawings and documents |
| Other | `pdm-other` | Miscellaneous files |

---

## Routing and Auth Flow

### Route Definitions

All routes are lazy-loaded using dynamic imports for code splitting:

```typescript
{
  path: '/pdm-browser',
  name: 'pdm-browser',
  component: () => import('../views/ItemsView.vue'),
  meta: { requiresAuth: true }
}
```

### Navigation Guards

The router has a `beforeEach` guard that:
1. Waits for `authStore.initialize()` to complete (ensures session is checked before any route decision).
2. If the route requires auth (`meta.requiresAuth: true`) and the user is not authenticated, redirects to `/login` with the original path as a `redirect` query parameter.
3. If the user is already authenticated and navigates to `/login`, redirects to `/` (home).

### Auth Flow Sequence

```
1. User opens any URL
   |
2. Router beforeEach fires
   |
3. authStore.initialize() called
   |  - Gets current session from Supabase (auto-refreshes expired tokens)
   |  - If session exists, fetches user profile from /api/auth/me
   |  - Sets up onAuthStateChange listener
   |
4. Guard checks: requiresAuth && !isAuthenticated?
   |-- Yes --> Redirect to /login?redirect={originalPath}
   |-- No  --> Continue to requested route
   |
5. On /login page, user submits email + password
   |
6. authStore.login() calls supabase.auth.signInWithPassword()
   |  - Supabase returns session with JWT
   |  - Fetches user profile from backend
   |
7. Redirect to original path (or /)
```

---

## TypeScript Types

Defined in `types/index.ts`:

| Interface | Key Fields |
|-----------|------------|
| `User` | `id`, `username`, `email`, `role` (`admin` / `engineer` / `viewer`) |
| `Project` | `id`, `name`, `description`, `status` (`active` / `archived` / `completed`) |
| `Item` | `id`, `item_number`, `name`, `revision`, `iteration`, `lifecycle_state`, `material`, `mass`, `thickness`, `cut_length`, `files?` |
| `FileInfo` | `id`, `item_id`, `file_type`, `file_name`, `file_path`, `file_size`, `revision`, `iteration` |
| `BOMEntry` | `id`, `parent_item_id`, `child_item_id`, `quantity`, `source_file` |
| `BOMTreeNode` | `item` (Item), `quantity`, `children` (BOMTreeNode[]) |
| `Task` | `id`, `item_id`, `file_id`, `task_type`, `status`, `error_message` |
| `LifecycleEntry` | `id`, `item_id`, `old_state`, `new_state`, `changed_by`, `changed_at` |

---

## Setup Instructions

### Prerequisites

- Node.js 20+ (LTS recommended)
- npm 9+
- Access to the Supabase project (URL and anon key)
- FastAPI backend running (see Deployment Guide)

### Installation

```bash
cd frontend
npm install
```

### Environment Configuration

Create or edit `frontend/.env`:

```env
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your_anon_key_here
# Optional: override auto-detected backend URL
# VITE_API_URL=http://localhost:8001/api
```

The `VITE_API_URL` variable is optional. By default, the frontend detects the backend URL automatically:
- In development: `http://{current-hostname}:8001/api`
- In production: `{current-origin}/api` (same container)

### Development Server

```bash
cd frontend
npm run dev
```

Starts the Vite dev server on `http://localhost:5174` with hot module replacement. The server listens on all interfaces (`host: true` in vite.config.ts) so it is accessible via LAN/Tailnet IP addresses.

### Production Build

```bash
cd frontend
npm run build
```

Runs TypeScript checking (`vue-tsc -b`) then builds optimized static files to `frontend/dist/`. The output can be deployed to any static file host or served by the FastAPI backend in production.

### Preview Production Build

```bash
cd frontend
npm run preview
```

Serves the built `dist/` folder locally using Vite's preview server.

---

## Users

| User | Email | Role | Access |
|------|-------|------|--------|
| Jack | jack@pdm.local | admin | Full access -- CRUD, file upload, all tools |
| Dan | dan@pdm.local | engineer | View and track projects, engineering access |
| Shop | shop@pdm.local | viewer | View drawings, BOMs, shop terminal |

---

## Browser Compatibility

Tested and supported on modern desktop browsers:
- Chrome (recommended)
- Edge
- Firefox

The interface is designed for desktop and large tablet screens. It is not optimized for mobile devices.
