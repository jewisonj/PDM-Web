# PDM-Web Frontend Architecture Overview

High-level overview of the Vue 3 frontend architecture, component patterns, state management, routing, authentication, and API communication.

---

## System Diagram

```
                        Browser
                          |
                   Vue 3 SPA (Vite)
                          |
          +---------------+---------------+
          |               |               |
     Vue Router      Pinia Stores     Supabase JS
     (Auth Guards)   (auth, items)    (Client SDK)
          |               |               |
          |        +------+------+   +----+----+
          |        |             |   |         |
          |    Supabase      FastAPI |   Supabase
          |    Client        apiCall |   Storage
          |    (direct DB)   (fetch) |   (signed URLs)
          |        |             |   |         |
          +--------+------+------+---+---------+
                          |
             Supabase Cloud (PostgreSQL)
             - Database (items, bom, files, etc.)
             - Auth (JWT sessions)
             - Storage (pdm-cad, pdm-exports, pdm-drawings)
```

**Two data paths exist:**
1. **Supabase Client (direct)** -- The items store and several MRP views query the Supabase database directly using the `@supabase/supabase-js` client SDK with Row Level Security.
2. **FastAPI Backend (API calls)** -- Auth endpoints, projects, tasks, MRP print packets, and operations requiring server-side logic use the `apiCall()` helper to communicate with the FastAPI backend at `/api/*`.

---

## Vue 3 Single File Components

All components use the Vue 3 Composition API with `<script setup lang="ts">`:

```vue
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useItemsStore } from '../stores/items'

const itemsStore = useItemsStore()
const searchQuery = ref('')

const filteredItems = computed(() => {
  // reactive filtering logic
})

onMounted(() => {
  itemsStore.fetchItems()
})
</script>

<template>
  <div class="view-container">
    <!-- template uses refs and computed directly -->
  </div>
</template>

<style scoped>
/* component-scoped styles */
</style>
```

Key patterns:
- **`<script setup>`** eliminates boilerplate (no explicit `export default`, `setup()` function, or `defineComponent`)
- **TypeScript** is used throughout (`lang="ts"`) with interfaces defined in `types/index.ts`
- **Scoped styles** (`<style scoped>`) keep CSS isolated per component
- **No Options API** -- all components use the Composition API exclusively

---

## Pinia State Management

Pinia stores use the Composition API (setup function) pattern rather than the Options API pattern:

```typescript
export const useItemsStore = defineStore('items', () => {
  // State as refs
  const items = ref<Item[]>([])
  const loading = ref(false)

  // Computed (getters)
  const filteredItems = computed(() => items.value)

  // Actions as functions
  async function fetchItems() { /* ... */ }

  // Return public API
  return { items, loading, filteredItems, fetchItems }
})
```

### Store Architecture

```
Pinia
├── auth store
│   ├── State: user, loading, error, initialized
│   ├── Computed: isAuthenticated, isEngineer, isAdmin
│   └── Actions: initialize(), login(), logout()
│
└── items store
    ├── State: items[], currentItem, loading, error, filters
    ├── Computed: filteredItems
    └── Actions: fetchItems(), fetchItem(), createItem(),
                 updateItem(), deleteItem(), getBOMTree(),
                 getWhereUsed(), getItemHistory()
```

### Data Flow

```
User Action (click, type, navigate)
        |
        v
Vue Component (calls store action)
        |
        v
Pinia Store Action (async function)
        |
        v
Supabase Client or apiCall()
        |
        v
Network Request (Supabase REST API or FastAPI)
        |
        v
Response updates ref state
        |
        v
Vue reactivity re-renders template
```

Components access stores via composable functions:

```typescript
const itemsStore = useItemsStore()
// Directly use: itemsStore.items, itemsStore.loading, itemsStore.fetchItems()
```

---

## Vue Router Configuration

### Route Structure

Routes are organized into three groups:

**Authentication:**
| Path | Name | View | Auth Required |
|------|------|------|---------------|
| `/login` | login | LoginView | No |

**PDM Tools:**
| Path | Name | View | Auth Required |
|------|------|------|---------------|
| `/` | home | HomeView | Yes |
| `/pdm-browser` | pdm-browser | ItemsView | Yes |
| `/items/:itemNumber` | item-detail | ItemDetailView | Yes |
| `/part-numbers` | part-numbers | PartNumbersView | Yes |
| `/projects` | projects | ProjectsView | Yes |
| `/tasks` | tasks | TasksView | Yes |

**MRP Tools:**
| Path | Name | View | Auth Required |
|------|------|------|---------------|
| `/mrp/dashboard` | mrp-dashboard | MrpDashboardView | Yes |
| `/mrp/routing` | mrp-routing | MrpRoutingView | Yes |
| `/mrp/shop` | mrp-shop | MrpShopView | Yes |
| `/mrp/parts` | mrp-parts | MrpPartLookupView | Yes |
| `/mrp/tracking` | mrp-tracking | MrpProjectTrackingView | Yes |
| `/mrp/materials` | mrp-materials | MrpRawMaterialsView | Yes |

### Lazy Loading

All route components use dynamic imports for automatic code splitting:

```typescript
component: () => import('../views/ItemsView.vue')
```

Vite produces separate chunks for each view, reducing the initial bundle size. Views are loaded on demand when the user navigates to them.

### History Mode

The router uses `createWebHistory()` (HTML5 History API) for clean URLs without hash fragments. This requires server-side support to serve `index.html` for all non-API paths. The FastAPI backend handles this with a catch-all route in production.

---

## Authentication Flow

### Supabase Auth Integration

Authentication is handled entirely by Supabase Auth. The frontend uses the `@supabase/supabase-js` SDK for session management:

```
Supabase Auth
├── signInWithPassword(email, password)  --> Returns JWT session
├── getSession()                         --> Returns current session (auto-refreshes)
├── refreshSession()                     --> Forces token refresh
├── signOut()                            --> Clears session
└── onAuthStateChange(callback)          --> Fires on login, logout, token refresh
```

### Session Lifecycle

```
App Starts
    |
    v
App.vue onMounted() --> authStore.initialize()
    |
    v
supabase.auth.getSession()
    |-- Session found --> fetchUser() from /api/auth/me
    |-- No session    --> user remains null
    |
    v
onAuthStateChange listener registered
    |-- SIGNED_IN    --> fetchUser()
    |-- SIGNED_OUT   --> user = null
    |-- TOKEN_REFRESHED --> fetchUser()
```

### Token Handling

- Supabase sessions are stored in `localStorage` under the key `pdm-web-auth`
- The `autoRefreshToken: true` setting automatically refreshes expired tokens
- The `apiCall()` helper reads the access token from the current session
- On a 401 response, `apiCall()` attempts one session refresh and retries

### Navigation Guard Logic

```
Router beforeEach(to)
    |
    v
await authStore.initialize()  // Ensures session is resolved
    |
    v
Is route requiresAuth?
    |-- Yes, and NOT authenticated --> redirect to /login?redirect={to.fullPath}
    |-- Yes, and authenticated     --> allow
    |
    v
Is route /login?
    |-- Already authenticated --> redirect to /
    |-- Not authenticated     --> allow
```

The guard always waits for `initialize()` to finish before making decisions. This prevents flashing the login page on reload when a valid session exists.

---

## API Communication Patterns

### Pattern 1: Direct Supabase Client

Used by the items store and MRP views for database queries:

```typescript
const { data, error } = await supabase
  .from('items')
  .select('*, projects(name)')
  .eq('lifecycle_state', 'Released')
  .order('item_number')
```

Advantages: Real-time-capable, uses Supabase Row Level Security, no backend code needed.

Used for: Items CRUD, BOM queries, file metadata, lifecycle history, part numbers, MRP data.

### Pattern 2: FastAPI Backend via apiCall()

Used for operations requiring server-side logic:

```typescript
const user = await apiCall<User>('/auth/me')
const projects = await apiCall<Project[]>('/projects')
```

The `apiCall()` function:
1. Gets the current Supabase session token
2. Adds it as a `Bearer` token in the `Authorization` header
3. Sends the request to `{API_BASE_URL}{endpoint}`
4. Handles 401 with automatic retry after token refresh
5. Parses JSON response or throws on error

Used for: Authentication, projects, tasks, MRP print packets, file upload/download endpoints.

### Pattern 3: Supabase Storage

Used for file operations (upload, download, signed URLs):

```typescript
const { data } = await supabase.storage
  .from('pdm-exports')
  .createSignedUrl('csp0030/A/1/csp0030.step', 3600)
```

The storage service (`services/storage.ts`) abstracts bucket selection and path construction.

---

## Component Hierarchy

```
App.vue
└── <router-view />
    ├── LoginView.vue
    │   └── (self-contained login form)
    │
    ├── HomeView.vue
    │   └── Tool cards grid (PDM + MRP sections)
    │
    ├── ItemsView.vue (PDM Browser)
    │   ├── Controls bar (search, filters, stats)
    │   ├── Sortable data table
    │   └── Slide-in detail panel
    │       ├── Item information grid
    │       ├── Files list (with signed URL links)
    │       ├── BOM children list (navigable)
    │       └── Where-used list (navigable)
    │
    ├── ItemDetailView.vue
    │   ├── Header (back button, action buttons)
    │   ├── Item metadata display
    │   └── Tabbed content
    │       ├── Files tab
    │       ├── BOM tab
    │       ├── Where Used tab
    │       └── History tab
    │
    ├── PartNumbersView.vue
    │   └── Prefix table with copy-to-clipboard
    │
    ├── ProjectsView.vue
    │   └── Project list with status badges
    │
    ├── TasksView.vue
    │   └── Task queue table with status badges
    │
    └── MRP Views (6 views)
        ├── MrpDashboardView.vue
        ├── MrpRoutingView.vue
        ├── MrpShopView.vue
        ├── MrpPartLookupView.vue
        ├── MrpProjectTrackingView.vue
        └── MrpRawMaterialsView.vue
```

---

## Styling Architecture

### Global Styles (`style.css`)

CSS custom properties define the design system:

```css
:root {
  --primary: #e94560;
  --bg-dark: #0f0f1a;
  --bg-card: #16213e;
  --border: #1a1a2e;
  --text: #e0e0e0;
  --text-muted: #888;
  --accent: #64b5f6;
}
```

### Per-Component Styles

Each view has its own `<style scoped>` block. The PDM Browser (ItemsView) and Home Dashboard use a light theme with professional PLM-style layouts. The Item Detail view uses a dark card theme.

### PrimeVue

PrimeVue with the Aura theme is registered globally and available for use. PrimeIcons are used for tool card icons (e.g., `pi pi-folder-open`, `pi pi-search`).

### Design Approach

- Desktop-first layout (not responsive/mobile-first)
- Compact data density similar to professional PLM tools
- Fixed-height viewport layouts with scrollable content regions
- CSS Grid for table layouts and card grids
- Minimal animation (panel slide-in transition, card hover effects)

---

## Build and Bundle

### Vite Configuration

```typescript
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5174,
    host: true,  // Listen on all interfaces
  },
})
```

### Build Process

1. `vue-tsc -b` -- TypeScript type checking (skipped in Docker build)
2. `vite build` -- Bundles and minifies:
   - Tree-shakes unused code
   - Code-splits by route (lazy-loaded views)
   - Hashes filenames for cache busting
   - Outputs to `dist/`

### Plugin Registration (`main.ts`)

```typescript
const app = createApp(App)
app.use(createPinia())    // State management
app.use(router)           // Client-side routing
app.use(PrimeVue, {       // UI component library
  theme: { preset: Aura, options: { darkModeSelector: '.dark-mode' } }
})
app.mount('#app')
```

---

## Key Design Decisions

1. **Composition API exclusively** -- No Options API usage. All components use `<script setup>` for minimal boilerplate and better TypeScript inference.

2. **Direct Supabase queries from frontend** -- The items store queries Supabase directly rather than routing everything through FastAPI. This reduces backend code and leverages Supabase's built-in security (Row Level Security). Backend endpoints are used only where server-side logic is required.

3. **Client-side filtering** -- The PDM Browser loads up to 1000 items and filters/sorts entirely in the browser for instant responsiveness. This matches the dataset size (hundreds to low thousands of items).

4. **Lazy-loaded routes** -- Every view is loaded on demand to keep the initial bundle small.

5. **Single container deployment** -- In production, FastAPI serves the Vue static files. This simplifies deployment (one container, one port) and eliminates CORS concerns.

6. **Dynamic API URL detection** -- The frontend determines the backend URL at runtime based on the current hostname, enabling seamless access from localhost, LAN IPs, and Tailnet addresses without configuration changes.

7. **Token retry on 401** -- The `apiCall()` helper handles expired tokens transparently by refreshing the session and retrying once, avoiding forced logouts during normal use.
